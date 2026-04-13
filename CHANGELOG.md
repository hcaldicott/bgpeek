# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-13

Initial public release.

### Querying

- Multi-vendor SSH support (Juniper JunOS, Cisco IOS/XE/XR, Arista EOS, Huawei VRP)
- BGP route, ping, and traceroute queries
- Structured BGP output parsing (prefix, next-hop, AS path, communities, origin, MED, local-pref)
- RPKI validation overlay via Cloudflare API (valid/invalid/not-found badges)
- Parallel multi-device queries with side-by-side diff view
- DNS resolution for hostname targets
- Shareable query results via UUID permalinks (configurable TTL)
- Query history with pagination
- Per-query-type SSH timeouts (120s for traceroute, 30s default)

### SSH Credential Management

- Credentials as a first-class entity (per-device SSH authentication)
- Support for key, password, and key+password auth types
- Fernet encryption for stored SSH passwords
- Configurable keys directory (`BGPEEK_KEYS_DIR`)
- Credential resolution chain: device-level → global default → clear error
- SSH connectivity test endpoint (`POST /api/credentials/{id}/test`)
- Auto-create default credential from global config on first startup
- Configurable host key policy (auto-accept or strict)

### Authentication & Authorization

- API key, local password (bcrypt), LDAP, OIDC (Keycloak) authentication
- JWT tokens with configurable expiry
- Cookie-based auth for web UI
- Role-based access: admin, NOC (sees all routes), public (filtered)
- Per-role output filtering — hides /25-/32 prefixes from public users
- Device-level access control (restricted devices hidden from public)

### Security

- Rate limiting per-IP, per-user, per-API-key (Redis sliding window)
- Circuit breaker for SSH connections (configurable threshold and cooldown)
- Webhook notifications with HMAC-SHA256 signatures
- Audit log in PostgreSQL (queries, logins, device changes, credential changes)
- Configurable audit log retention with automatic cleanup

### Observability

- Prometheus metrics endpoint (`/metrics`)
- Request correlation via `X-Request-ID` header
- Deep health check (`GET /api/health?deep=true` — DB + Redis connectivity)
- Structured JSON logging via structlog
- Periodic cleanup for expired results and old audit entries

### API

- Full REST API with OpenAPI/Swagger documentation
- Device inventory CRUD
- Credential CRUD with usage tracking
- Webhook CRUD with test endpoint
- User management (local, LDAP, OIDC)

### UI

- Server-rendered HTML with HTMX + Tailwind CSS (no SPA, no npm, ~14 KB JS)
- Two-column sidebar + results layout
- Dark/light theme with persistent toggle
- Internationalization (English and Russian)
- Loading spinner with abort button
- DOM growth limit (capped at 20 results)

### Deployment

- Single `docker compose up` (PostgreSQL + Redis included)
- Debian slim-based Docker image, non-root container, tini init
- Auto-migration on startup
- `.env.example` with all settings documented
- SSH keys mounted as read-only volume
- Compose uses env var references (no hardcoded credentials)
- Separate `compose.dev.yaml` for development (not auto-loaded in production)

### Documentation

- Configuration reference (all 60+ settings)
- Production deployment guide (proxy, TLS, backups, monitoring)
- SSH credential management guide
- REST API reference with curl examples

[1.0.0]: https://github.com/xeonerix/bgpeek/releases/tag/v1.0.0
