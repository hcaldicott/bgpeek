"""Fire-and-forget SSH reachability probe triggered by admin device save.

The admin devices list renders a device as `Healthy`/`Down`/`Unknown` based on
whether the device has any successful `query` or `probe` audit entry on
record. Without a probe, a newly-added device stays `Unknown` until an
operator manually runs a query — which means a typo in the address is only
surfaced at the worst possible time. A lightweight background probe after
save records one successful or failed `probe` entry so the list reflects
reality within seconds.

The probe opens and closes an SSH session using the device's resolved
credential. It is intentionally *not* awaited by the HTTP handler — form
save stays instant, and the probe runs on the event loop in the
background. All exceptions are swallowed and translated into a failure
audit entry.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import structlog

from bgpeek.config import settings
from bgpeek.core.circuit_breaker import record_failure, record_success
from bgpeek.core.ssh import SSHClient, SSHError
from bgpeek.db import devices as device_crud
from bgpeek.db.audit import log_audit
from bgpeek.db.credentials import get_credential_for_device
from bgpeek.db.pool import get_pool
from bgpeek.models.audit import AuditAction, AuditEntryCreate
from bgpeek.models.credential import Credential
from bgpeek.models.device import Device

log = structlog.get_logger(__name__)

_pending_tasks: set[asyncio.Task[None]] = set()


async def probe_device(device_id: int) -> None:
    """Attempt to open and close an SSH session, recording the outcome to audit_log."""
    pool = get_pool()
    device = await device_crud.get_device_by_id(pool, device_id)
    if device is None:
        return  # deleted between save and probe — nothing to record

    key_path, password, username = _resolve_auth(await get_credential_for_device(pool, device.name))
    if key_path is None and password is None:
        await _record(device, success=False, error="no SSH credentials configured", runtime_ms=0)
        return

    client = SSHClient(
        host=str(device.address),
        username=username,
        platform=device.platform,
        port=device.port,
        password=password,
        key_path=key_path,
        timeout=settings.ssh_timeout,
    )
    started = time.monotonic()
    success = False
    error: str | None = None
    try:
        await client.connect()
        success = True
    except SSHError as exc:
        error = str(exc)
    except Exception as exc:
        error = f"unexpected probe error: {exc}"
        log.warning("probe_unexpected_error", device=device.name, exc_info=True)
    finally:
        await client.disconnect()

    runtime_ms = int((time.monotonic() - started) * 1000)
    await _record(device, success=success, error=error, runtime_ms=runtime_ms)
    # Feed the circuit breaker so the admin-list badge reflects a probe failure
    # the same way it already reflects a query failure. Without this, a device
    # with any prior successful session kept showing "Healthy" even right after
    # a visible ssh-connect-timeout in the logs (reported 2026-04-20).
    if success:
        await record_success(device.name)
    else:
        await record_failure(device.name)


def schedule_probe(device_id: int) -> None:
    """Kick off a probe without awaiting it. Tracks the task so shutdown can drain it."""
    task = asyncio.create_task(_guard(device_id))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


async def shutdown() -> None:
    """Cancel and await all pending probe tasks on application shutdown."""
    if not _pending_tasks:
        return
    log.info("cancelling pending probe tasks", count=len(_pending_tasks))
    for task in _pending_tasks:
        task.cancel()
    await asyncio.gather(*_pending_tasks, return_exceptions=True)
    _pending_tasks.clear()


async def _guard(device_id: int) -> None:
    """Wrap `probe_device` so a raised exception can't escape into the event loop."""
    try:
        await probe_device(device_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.warning("probe_task_crashed", device_id=device_id, exc_info=True)


def _resolve_auth(cred: Credential | None) -> tuple[Path | None, str | None, str]:
    """Pick username / key path / password for the probe, with global-key fallback."""
    username = settings.ssh_username
    key_path: Path | None = None
    password: str | None = None

    if cred is not None:
        username = cred.username
        if cred.key_name:
            candidate = settings.keys_dir / cred.key_name
            if candidate.is_file():
                key_path = candidate
        if cred.password:
            password = cred.password

    if key_path is None and password is None:
        default_key = settings.keys_dir / "default.key"
        if default_key.is_file():
            key_path = default_key

    return key_path, password, username


async def _record(device: Device, *, success: bool, error: str | None, runtime_ms: int) -> None:
    """Insert an AuditAction.PROBE row tying the probe outcome to the device."""
    pool = get_pool()
    await log_audit(
        pool,
        AuditEntryCreate(
            action=AuditAction.PROBE,
            success=success,
            device_id=device.id,
            device_name=device.name,
            error_message=error,
            runtime_ms=runtime_ms,
        ),
    )
