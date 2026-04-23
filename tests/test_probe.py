"""Tests for bgpeek.core.probe."""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import IPv4Address
from unittest.mock import AsyncMock

import asyncpg
import pytest

from bgpeek.config import settings
from bgpeek.core import probe
from bgpeek.core.ssh import SSHConnectionError
from bgpeek.db import devices as device_crud
from bgpeek.models.credential import Credential
from bgpeek.models.device import DeviceCreate


def _cred(**overrides: object) -> Credential:
    base: dict[str, object] = {
        "id": 1,
        "name": "c",
        "description": "",
        "auth_type": "key",
        "username": "noc",
        "key_name": None,
        "password": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return Credential.model_validate(base)


def test_resolve_auth_uses_credential_username() -> None:
    key_path, password, username = probe._resolve_auth(_cred(username="alice"))
    assert username == "alice"
    assert password is None
    # key_path may be None if default key file isn't present in test env
    # — asserting only on the username/password is enough here.


def test_resolve_auth_with_password() -> None:
    key_path, password, username = probe._resolve_auth(_cred(password="secret"))  # noqa: S106
    assert password == "secret"  # noqa: S105
    assert username == "noc"


def test_resolve_auth_fallback_username_when_no_cred() -> None:
    key_path, password, username = probe._resolve_auth(None)
    assert username == settings.ssh_username


def test_resolve_auth_missing_key_file_is_silently_dropped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "keys_dir", tmp_path)
    key_path, password, _ = probe._resolve_auth(_cred(key_name="nonexistent.key"))
    assert key_path is None
    assert password is None


async def test_probe_device_records_success(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful SSH connect writes a success=True probe audit row."""
    device = await device_crud.create_device(
        pool,
        DeviceCreate(
            name="rt-probe-ok",
            address=IPv4Address("10.0.0.1"),
            platform="juniper_junos",
        ),
    )

    # Force probe to run with password auth so no filesystem key lookup is needed.
    monkeypatch.setattr(probe, "_resolve_auth", lambda cred: (None, "fake", "noc"))
    monkeypatch.setattr(probe, "SSHClient", _make_ssh_stub(connect_ok=True))
    # db.pool.get_pool() is called inside probe; point it at the test pool.
    monkeypatch.setattr(probe, "get_pool", lambda: pool)

    await probe.probe_device(device.id)

    row = await pool.fetchrow(
        "SELECT action, success, device_id FROM audit_log WHERE device_id = $1",
        device.id,
    )
    assert row is not None
    assert row["action"] == "probe"
    assert row["success"] is True


async def test_probe_device_records_failure_on_ssh_error(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SSH connect that raises SSHError writes success=False with error_message."""
    device = await device_crud.create_device(
        pool,
        DeviceCreate(
            name="rt-probe-fail",
            address=IPv4Address("10.0.0.1"),
            platform="juniper_junos",
        ),
    )

    monkeypatch.setattr(probe, "_resolve_auth", lambda cred: (None, "fake", "noc"))
    monkeypatch.setattr(
        probe, "SSHClient", _make_ssh_stub(connect_ok=False, error=SSHConnectionError("boom"))
    )
    monkeypatch.setattr(probe, "get_pool", lambda: pool)

    await probe.probe_device(device.id)

    row = await pool.fetchrow(
        "SELECT success, error_message FROM audit_log WHERE device_id = $1", device.id
    )
    assert row is not None
    assert row["success"] is False
    assert row["error_message"] == "boom"


async def test_probe_failure_records_circuit_breaker(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed probe must bump the circuit-breaker count so the admin-list badge
    reflects the failure (not just the audit_log row) — parity with how a failed
    query already feeds the breaker.
    """
    device = await device_crud.create_device(
        pool,
        DeviceCreate(
            name="rt-cb-fail",
            address=IPv4Address("10.0.0.1"),
            platform="juniper_junos",
        ),
    )

    monkeypatch.setattr(probe, "_resolve_auth", lambda cred: (None, "fake", "noc"))
    monkeypatch.setattr(
        probe, "SSHClient", _make_ssh_stub(connect_ok=False, error=SSHConnectionError("timeout"))
    )
    monkeypatch.setattr(probe, "get_pool", lambda: pool)

    record_failure_spy = AsyncMock()
    record_success_spy = AsyncMock()
    monkeypatch.setattr(probe, "record_failure", record_failure_spy)
    monkeypatch.setattr(probe, "record_success", record_success_spy)

    await probe.probe_device(device.id)

    record_failure_spy.assert_awaited_once_with("rt-cb-fail")
    record_success_spy.assert_not_awaited()


async def test_probe_success_clears_circuit_breaker(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful probe must clear the breaker (same as a successful query) so
    a device that recovered doesn't keep looking partial-failed in the admin list.
    """
    device = await device_crud.create_device(
        pool,
        DeviceCreate(
            name="rt-cb-ok",
            address=IPv4Address("10.0.0.1"),
            platform="juniper_junos",
        ),
    )

    monkeypatch.setattr(probe, "_resolve_auth", lambda cred: (None, "fake", "noc"))
    monkeypatch.setattr(probe, "SSHClient", _make_ssh_stub(connect_ok=True))
    monkeypatch.setattr(probe, "get_pool", lambda: pool)

    record_failure_spy = AsyncMock()
    record_success_spy = AsyncMock()
    monkeypatch.setattr(probe, "record_failure", record_failure_spy)
    monkeypatch.setattr(probe, "record_success", record_success_spy)

    await probe.probe_device(device.id)

    record_success_spy.assert_awaited_once_with("rt-cb-ok")
    record_failure_spy.assert_not_awaited()


async def test_probe_device_skips_when_no_credentials(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When neither key nor password can be resolved, record failure without touching SSH."""
    device = await device_crud.create_device(
        pool,
        DeviceCreate(
            name="rt-probe-nocred",
            address=IPv4Address("10.0.0.1"),
            platform="juniper_junos",
        ),
    )

    monkeypatch.setattr(probe, "_resolve_auth", lambda cred: (None, None, "noc"))

    # SSHClient must NOT be constructed — sentinel class that raises on construction.
    class _ShouldNotInstantiate:
        def __init__(self, *_: object, **__: object) -> None:
            raise AssertionError("SSHClient should not be constructed when creds are missing")

    monkeypatch.setattr(probe, "SSHClient", _ShouldNotInstantiate)
    monkeypatch.setattr(probe, "get_pool", lambda: pool)

    await probe.probe_device(device.id)

    row = await pool.fetchrow(
        "SELECT success, error_message FROM audit_log WHERE device_id = $1", device.id
    )
    assert row is not None
    assert row["success"] is False
    assert "no SSH credentials" in (row["error_message"] or "")


async def test_probe_device_returns_early_for_missing_device(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probe queued for a device that's since been deleted must not write an audit row."""
    monkeypatch.setattr(probe, "get_pool", lambda: pool)
    await probe.probe_device(999999)
    count = await pool.fetchval("SELECT COUNT(*) FROM audit_log")
    assert count == 0


def _make_ssh_stub(*, connect_ok: bool, error: Exception | None = None) -> type:
    """Build a stand-in for SSHClient that matches the async connect/disconnect contract."""

    class _Stub:
        def __init__(self, **_: object) -> None:
            self.connect = AsyncMock(
                return_value=None if connect_ok else None,
                side_effect=None if connect_ok else error,
            )
            self.disconnect = AsyncMock(return_value=None)

    return _Stub
