# bgpeek deployment feedback

Issues and improvement suggestions found during first production deployment (2026-04-12).

## Deployment issues

### Migrations not included in Docker image
Dockerfile copies `src/`, `pyproject.toml`, `README.md` but not `migrations/`. First startup fails with `UndefinedTableError: relation "devices" does not exist`.

**Fix**: Add `COPY --chown=bgpeek:bgpeek migrations ./migrations` to Dockerfile runtime stage.

### No auto-migration on startup
`main.py:lifespan()` opens the DB pool but does not call `apply_migrations()`. First-time deployment requires manually exec'ing `bgpeek-migrate`.

**Fix**: Call `apply_migrations()` in lifespan after `init_pool()`, or document the manual step.

### compose.yaml + .env variable conflict
`compose.yaml` hardcodes `BGPEEK_DATABASE_URL` and `BGPEEK_REDIS_URL` in `environment:` block. Docker Compose merge order: `environment` > `env_file`, so `.env` overrides don't work.

**Fix**: Move credentials to `.env` and reference via `${VARIABLE}` in compose.yaml.

### compose.override.yaml is dev by default — breaks production
`compose.override.yaml` is committed with dev settings: `target: builder`, volume mounts, `uv sync --reload`. Docker Compose auto-loads it. Deploying via rsync + `docker compose up` produces a 724MB builder image instead of 150MB runtime.

**Fix**: Rename to `compose.dev.yaml`, use `docker compose -f compose.yaml -f compose.dev.yaml up` for development.

### Builder image lacks runtime PATH/CMD
If built with `target: builder`, the image has `/opt/venv` but system python on PATH. `python3 -m bgpeek.main` fails with `ModuleNotFoundError`.

**Fix**: Add `ENV PATH="/opt/venv/bin:$PATH"` to builder stage too.

### PG password mismatch
`compose.yaml` hardcodes `POSTGRES_PASSWORD: bgpeek`. If an override changes the password but the volume was initialized with the old one, auth fails.

**Fix**: Don't hardcode passwords in compose files. Use `.env` + `${VARIABLE}`.

### No .env.example
No reference for production env vars. Had to read `config.py` to understand all options.

**Fix**: Ship `.env.example` with all vars commented and documented.

## Code issues

### Critical

1. **ssh_key_path not passed to execute_query** (`api/query.py`): All 4 call sites omit `ssh_key_path`. `SSHClient.__init__` raises `ValueError("Either password or key_path must be provided")` on every query. Fixed locally — needs commit.

2. **Result persistence can 500 a successful query** (`api/query.py:291-293`): `_persist_result()` re-raises exceptions. If DB INSERT fails after SSH query succeeds, user gets 500 and loses the result.

3. **Webhook tasks not tracked** (`core/webhooks.py:94`): `asyncio.create_task()` without storing reference. Tasks silently dropped on shutdown.

4. **Broad `except Exception` swallows bugs** (`api/query.py:85, 196`): htmx endpoints catch all exceptions and render generic error. Masks real bugs.

### High

5. **SSH username hardcoded** (`core/query.py:138`): `username="looking-glass"` — should come from device config or `BGPEEK_SSH_USERNAME`.

6. **Connection pool may exhaust** (`db/pool.py:19-24`): max=10, but max_parallel_queries=5 + audit + device listing. Make configurable via `BGPEEK_DB_POOL_MAX`.

7. **SSH timeout not configurable** (`core/ssh.py:49, 138`): Hardcoded 30s. Traceroute on slow routers can exceed this. Add `BGPEEK_SSH_TIMEOUT`.

8. **RPKI caches failures for 1 hour** (`core/rpki.py:139-148`): Should use shorter TTL for errors (e.g. 60s).

9. **No expired results cleanup** (`db/results.py`): `query_results.expires_at` indexed but no cleanup job. Table grows forever.

### Medium

10. **No device-level access control**: Any authenticated user can query any device. Consider device groups or per-role visibility.

11. **No circuit breaker**: Dead device blocks for full SSH timeout. 5 concurrent queries = 5 slots wasted 30s each.

12. **No request correlation ID**: Hard to trace query flow through SSH → RPKI → audit → persist.

13. **No /metrics endpoint**: No Prometheus metrics. Consider `prometheus-fastapi-instrumentator`.

14. **audit_log no retention**: Table grows unbounded. Add `BGPEEK_AUDIT_TTL_DAYS` + cleanup.

15. **DB command_timeout=30** (`db/pool.py:23`): Make configurable.

### Low

16. **Alpine vs slim**: musl libc edge cases with cryptography/asyncpg. Consider `python:3.12-slim`.

17. **HTMX DOM growth** (`templates/index.html:67`): `hx-swap="afterbegin"` never cleans old results.

18. **Webhook retry without backoff**: Retries twice immediately. Add exponential backoff.

19. **Per-query-type timeouts**: traceroute needs more than 30s.

20. **Health check too simple** (`main.py:130-133`): No DB/Redis check. Add deep health option.

21. **No host key verification handling**: First SSH to new device fails. Need known_hosts or auto-accept config.

## What works well

- Clean project structure, good separation of concerns
- Multi-stage Docker build produces small image (~150MB)
- Graceful Redis degradation (cache disabled if Redis unavailable)
- Structured logging with structlog
- Good i18n support (EN/RU) with cookie persistence
- RPKI validation overlay is a nice differentiator
- Parallel multi-device queries with diff view
- Shareable results with UUID permalinks
- Comprehensive rate limiting (IP + user + API key)
- HTMX approach keeps frontend minimal (~14KB JS)
