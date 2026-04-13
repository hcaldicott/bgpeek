# SSH Credential Management

## Overview

bgpeek supports per-device SSH credentials stored in PostgreSQL with encrypted
passwords and file-based private keys. Each device can reference a named
credential, allowing different authentication parameters (username, key, password)
for different routers, while a global default covers the common single-key setup.

## Data Model

The `credentials` table holds named authentication profiles:

| Column       | Type         | Description                                    |
|--------------|--------------|------------------------------------------------|
| `id`         | `serial`     | Primary key                                    |
| `name`       | `varchar`    | Unique human-readable name (e.g. `"juniper-prod"`) |
| `description`| `text`       | Optional notes                                 |
| `auth_type`  | `varchar`    | One of `key`, `password`, `key+password`       |
| `username`   | `varchar`    | SSH username                                   |
| `key_name`   | `varchar`    | Filename inside the keys directory (nullable)  |
| `password`   | `text`       | Fernet-encrypted password (nullable)           |
| `created_at` | `timestamptz`| Row creation time                              |
| `updated_at` | `timestamptz`| Last modification time                         |

Devices reference credentials via `devices.credential_id` (foreign key, nullable).

## Setup

### Keys Directory

SSH private key files are read from a dedicated directory. The default path is
`/etc/bgpeek/keys/`; override it with the `BGPEEK_KEYS_DIR` environment variable.

Mount your keys as a read-only volume in Docker Compose:

```yaml
services:
  bgpeek:
    volumes:
      - ./secrets:/etc/bgpeek/keys:ro
```

Key files must have restrictive permissions:

```bash
chmod 600 secrets/*.key
chown 1000:1000 secrets/*.key   # uid 1000 = bgpeek user inside the container
```

### Password Encryption

Stored passwords are encrypted with Fernet symmetric encryption. Generate a key
and set it in your environment:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the output to your `.env` file:

```
BGPEEK_ENCRYPTION_KEY=your-fernet-key-here
```

Without `BGPEEK_ENCRYPTION_KEY`, passwords are stored as plaintext. This is
acceptable for local development but must not be used in production.

### Creating Credentials

**Key-only authentication:**

```bash
curl -s -X POST http://localhost:8000/api/credentials \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "juniper-prod",
    "auth_type": "key",
    "username": "looking-glass",
    "key_name": "juniper.key"
  }'
```

**Password-only authentication:**

```bash
curl -s -X POST http://localhost:8000/api/credentials \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "huawei-legacy",
    "auth_type": "password",
    "username": "readonly",
    "password": "s3cret"
  }'
```

**Key + password (key with passphrase or password fallback):**

```bash
curl -s -X POST http://localhost:8000/api/credentials \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cisco-datacenter",
    "auth_type": "key+password",
    "username": "bgpeek",
    "key_name": "cisco_dc.key",
    "password": "enable-secret"
  }'
```

### Assigning to Devices

Assign a credential to a device by updating its `credential_id`:

```bash
curl -s -X PATCH http://localhost:8000/api/devices/3 \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"credential_id": 1}'
```

For bulk assignment (e.g. all Juniper devices to credential id 2):

```sql
UPDATE devices SET credential_id = 2 WHERE platform = 'juniper_junos';
```

## Credential Resolution

When bgpeek executes a query, SSH credentials are resolved in this order:

1. **Device-level credential** -- if the device has `credential_id` set, the
   corresponding row from `credentials` provides the username, key file, and/or
   password.

2. **Global default** -- if no credential is assigned, bgpeek falls back to
   `BGPEEK_SSH_USERNAME` (default: `looking-glass`) and looks for
   `default.key` in the keys directory.

3. **Error** -- if neither source provides a usable key or password, the query
   fails with `"no SSH credentials configured for device '<name>'"`.

Privileged roles (admin, NOC) and public users all follow the same resolution
chain. Credential choice is per-device, not per-user.

## Migration from v1.0

Deployments that used a single global SSH key require no configuration changes.
On startup, bgpeek automatically:

1. Checks if a credential named `"default"` exists.
2. If not, scans the keys directory for `default.key` or `id_rsa`.
3. Creates a `"default"` credential using the discovered key and the value of
   `BGPEEK_SSH_USERNAME`.
4. Assigns the new credential to every device where `credential_id IS NULL`.

This means existing single-key setups continue working with zero manual steps.

## Security

- **Encrypted at rest** -- passwords are Fernet-encrypted when `BGPEEK_ENCRYPTION_KEY`
  is set. The encryption key itself must be managed via environment variables or a
  secrets manager; it is never stored in the database.

- **Never exposed via API** -- key file contents are never served through the API.
  Only the `key_name` (filename) is returned. Passwords are masked to `"****"` in
  all API responses.

- **Read-only mount** -- the keys directory should be mounted `:ro` in Docker to
  prevent the application from modifying key files.

- **Audit trail** -- credential creation, modification, and deletion are logged to
  the audit table with the acting user and timestamp.

- **Deletion safety** -- a credential cannot be deleted while devices still
  reference it (returns HTTP 409).

## Testing Credentials

Verify that a credential can establish an SSH connection to a specific device:

```bash
curl -s -X POST "http://localhost:8000/api/credentials/1/test?device_id=3" \
  -H "X-API-Key: $API_KEY"
```

Response on success:

```json
{"success": true, "message": "SSH connection successful"}
```

Response on failure:

```json
{"success": false, "message": "Authentication failed (key rejected)"}
```

The test endpoint connects, authenticates, and immediately disconnects. It does
not execute any commands on the device.
