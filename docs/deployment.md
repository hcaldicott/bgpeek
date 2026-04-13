# Deployment

Production deployment guide for bgpeek.

---

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- A server with SSH access to your network devices
- (Optional) A reverse proxy (nginx, Caddy, Traefik) for TLS termination

## Quick Start

```bash
git clone https://github.com/yourusername/bgpeek.git
cd bgpeek
cp .env.example .env
```

Edit `.env` and set the required values (see below), then:

```bash
docker compose up -d
```

bgpeek will be available at `http://your-server:8000`.

## Required Environment Variables

Four variables **must** be set before first boot:

```bash
# Strong random password for PostgreSQL
POSTGRES_PASSWORD=your-db-password-here

# JWT signing secret — generate with:
#   python -c "import secrets; print(secrets.token_hex(32))"
BGPEEK_JWT_SECRET=your-jwt-secret-here

# Session secret (required for OIDC, recommended for all deployments)
BGPEEK_SESSION_SECRET=your-session-secret-here

# Fernet key for encrypting stored SSH passwords — generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
BGPEEK_ENCRYPTION_KEY=your-fernet-key-here
```

All other variables have sensible defaults. See [configuration.md](configuration.md) for the full reference.

## SSH Keys Setup

bgpeek reads SSH private keys from a directory mounted into the container.

```bash
# Create the keys directory
mkdir -p secrets

# Copy your SSH private keys
cp ~/.ssh/id_rsa_looking_glass secrets/

# Set strict permissions
chmod 700 secrets
chmod 600 secrets/*
```

The `compose.yaml` mounts `./secrets` to `/etc/bgpeek/keys` inside the container (read-only). To change the host path:

```bash
# In .env
BGPEEK_KEYS_DIR=./path/to/your/keys
```

When adding a device credential via the API, reference the key by filename (e.g. `id_rsa_looking_glass`). bgpeek resolves it relative to the keys directory.

## Device Credentials

After first boot, add devices and credentials via the REST API. The interactive API docs are at `http://your-server:8000/docs`.

A default admin user is created on first startup if no users exist. Check the container logs for the initial credentials:

```bash
docker compose logs bgpeek | grep -i "default\|admin\|password"
```

Change the default password immediately.

## Reverse Proxy

bgpeek uses server-side rendering with HTMX — no WebSocket support is needed. A simple HTTP proxy is sufficient.

### nginx

```nginx
server {
    listen 443 ssl http2;
    server_name lg.example.com;

    ssl_certificate     /etc/letsencrypt/live/lg.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lg.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;

        # Some commands (traceroute) can take up to 2 minutes
        proxy_read_timeout 180s;
    }
}

server {
    listen 80;
    server_name lg.example.com;
    return 301 https://$host$request_uri;
}
```

### Caddy

```
lg.example.com {
    reverse_proxy localhost:8000 {
        header_up X-Request-ID {http.request.uuid}
    }
}
```

Caddy handles TLS automatically via Let's Encrypt.

## TLS / HTTPS

Options:

1. **Let's Encrypt via Caddy or certbot** — simplest for public-facing deployments.
2. **Behind a load balancer** (AWS ALB, Cloudflare Tunnel, etc.) — terminate TLS there, proxy HTTP to bgpeek.
3. **Self-signed** — for internal NOC access only.

bgpeek itself does not terminate TLS. Always run it behind a reverse proxy in production.

## Upgrading

```bash
cd /path/to/bgpeek
docker compose pull        # pull latest images
docker compose up -d       # recreate containers
```

Database migrations run automatically on startup (`BGPEEK_AUTO_MIGRATE=true` by default). To disable auto-migration and run manually:

```bash
BGPEEK_AUTO_MIGRATE=false docker compose up -d
docker compose exec bgpeek python -m bgpeek.db.migrate
```

Always back up the database before upgrading.

## Backup

### Database

```bash
docker compose exec postgres pg_dump -U bgpeek bgpeek > backup_$(date +%Y%m%d).sql
```

Restore:

```bash
cat backup_20260412.sql | docker compose exec -T postgres psql -U bgpeek bgpeek
```

### SSH Keys

Back up the `secrets/` directory. These are the private keys used to connect to your devices — losing them means re-deploying keys on all routers.

```bash
tar czf bgpeek-keys-backup.tar.gz secrets/
```

### Encryption Key

If you lose `BGPEEK_ENCRYPTION_KEY`, all stored SSH passwords become unrecoverable. Store the key in a secure vault (e.g. HashiCorp Vault, AWS Secrets Manager, or a password manager).

## Monitoring

### Health Check

```bash
# Liveness (fast, no backend checks)
curl -s http://localhost:8000/api/health

# Readiness (checks PostgreSQL and Redis connectivity)
curl -s http://localhost:8000/api/health?deep=true
```

Use the deep health check in Docker/Kubernetes readiness probes. The liveness endpoint is suitable for simple up/down checks.

### Prometheus

bgpeek exposes Prometheus metrics at `/metrics`. Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: bgpeek
    static_configs:
      - targets: ["bgpeek-host:8000"]
```

### Logs

bgpeek uses `structlog` for structured JSON logging. Each log entry includes a correlation ID that matches the `X-Request-ID` header.

View logs:

```bash
docker compose logs -f bgpeek
```

For log aggregation (Loki, ELK, etc.), parse the JSON-formatted stdout output directly.

## Troubleshooting

### Container won't start: "Set POSTGRES_PASSWORD in .env"

`POSTGRES_PASSWORD` is required. Set it in your `.env` file.

### "Connection refused" to PostgreSQL

bgpeek depends on PostgreSQL being healthy before starting. If postgres takes too long to initialize, bgpeek may fail on first boot. Restart it:

```bash
docker compose restart bgpeek
```

### SSH connection timeout

- Verify the device is reachable from the Docker host: `docker compose exec bgpeek python -c "import socket; socket.create_connection(('DEVICE_IP', 22), timeout=5)"`
- Check that the SSH key has correct permissions (600) and is mounted into the container.
- Increase `BGPEEK_SSH_TIMEOUT` if your devices are slow to respond.

### "Permission denied" on SSH keys

The container runs as UID 1000 (`bgpeek` user). Ensure your key files are readable by that user:

```bash
chown 1000:1000 secrets/*
chmod 600 secrets/*
```

### Rate limiting blocks legitimate users

Disable temporarily for debugging:

```bash
BGPEEK_RATE_LIMIT_ENABLED=false docker compose up -d
```

Or increase the limits in `.env`. Rate limiting requires Redis — if Redis is down, rate limiting is silently disabled.

### Circuit breaker trips on a working device

A device marked as "down" by the circuit breaker will auto-recover after the cooldown period (default 300 seconds). To reset immediately, restart the bgpeek container.

### Redis connection errors in logs

Redis is optional. If Redis is unavailable, bgpeek continues to work without caching, rate limiting, or circuit breaker state. The errors are informational.

### Database migrations fail

Check the PostgreSQL logs:

```bash
docker compose logs postgres
```

Ensure the database user has permissions to create tables and run DDL. The default `compose.yaml` setup grants full privileges to the `bgpeek` user.
