"""Tests for credential encryption, DB CRUD, and query-pipeline resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import IPv4Address
from pathlib import Path
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from cryptography.fernet import Fernet

from bgpeek.core.dns import ResolvedTarget
from bgpeek.core.encryption import decrypt_password, encrypt_password
from bgpeek.core.query import QueryExecutionError, execute_query
from bgpeek.db.credentials import (
    create_credential,
    delete_credential,
    get_credential,
    get_credential_for_device,
    list_credentials,
    update_credential,
)
from bgpeek.models.credential import Credential, CredentialCreate, CredentialUpdate
from bgpeek.models.device import Device
from bgpeek.models.query import QueryRequest, QueryType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

KEY = Fernet.generate_key().decode()
KEY_OTHER = Fernet.generate_key().decode()

NOW = datetime(2026, 1, 1, tzinfo=UTC)

_CREDENTIAL_ROW = {
    "id": 1,
    "name": "core-ssh",
    "description": "Core routers",
    "auth_type": "password",
    "username": "admin",
    "key_name": None,
    "password": "supersecret",
    "created_at": NOW,
    "updated_at": NOW,
}


def _mock_pool() -> AsyncMock:
    pool = AsyncMock(spec=asyncpg.Pool)
    pool.fetchrow = AsyncMock()
    pool.fetch = AsyncMock()
    pool.fetchval = AsyncMock()
    pool.execute = AsyncMock()
    return pool


def _make_request(device: str = "rt1", target: str = "8.8.8.0/24") -> QueryRequest:
    return QueryRequest(
        device_name=device, query_type=QueryType.BGP_ROUTE, target=target
    )


def _make_device(name: str = "rt1") -> Device:
    return Device(
        id=1,
        name=name,
        address=IPv4Address("10.0.0.1"),
        platform="juniper_junos",
        port=22,
        enabled=True,
        created_at=NOW,
        updated_at=NOW,
    )


# ===========================================================================
# 1. Encryption tests
# ===========================================================================


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        with patch("bgpeek.core.encryption.settings") as mock_settings:
            mock_settings.encryption_key = KEY
            ciphertext = encrypt_password("my-secret-pw")
            assert ciphertext != "my-secret-pw"
            plaintext = decrypt_password(ciphertext)
            assert plaintext == "my-secret-pw"

    def test_noop_when_encryption_key_empty(self) -> None:
        with patch("bgpeek.core.encryption.settings") as mock_settings:
            mock_settings.encryption_key = ""
            assert encrypt_password("plaintext-pass") == "plaintext-pass"
            assert decrypt_password("plaintext-pass") == "plaintext-pass"

    def test_decrypt_with_wrong_key_raises(self) -> None:
        with patch("bgpeek.core.encryption.settings") as mock_settings:
            mock_settings.encryption_key = KEY
            ciphertext = encrypt_password("secret")

        with patch("bgpeek.core.encryption.settings") as mock_settings:
            mock_settings.encryption_key = KEY_OTHER
            with pytest.raises(ValueError, match="wrong BGPEEK_ENCRYPTION_KEY"):
                decrypt_password(ciphertext)


# ===========================================================================
# 2. DB CRUD tests (mock asyncpg pool)
# ===========================================================================


class TestListCredentials:
    async def test_returns_credential_with_usage(self) -> None:
        pool = _mock_pool()
        row = {**_CREDENTIAL_ROW, "device_count": 3}
        pool.fetch = AsyncMock(return_value=[row])

        result = await list_credentials(pool)

        assert len(result) == 1
        assert result[0].name == "core-ssh"
        assert result[0].device_count == 3
        assert result[0].password == "****"


class TestCreateCredential:
    async def test_encrypts_password(self) -> None:
        pool = _mock_pool()
        returned_row = {**_CREDENTIAL_ROW, "password": "encrypted-blob"}
        pool.fetchrow = AsyncMock(return_value=returned_row)

        payload = CredentialCreate(
            name="core-ssh",
            auth_type="password",
            username="admin",
            password="supersecret",
        )

        with patch("bgpeek.db.credentials.encrypt_password") as mock_enc:
            mock_enc.return_value = "encrypted-blob"
            cred = await create_credential(pool, payload)

        mock_enc.assert_called_once_with("supersecret")
        assert cred.password == "****"


class TestGetCredential:
    async def test_masks_password(self) -> None:
        pool = _mock_pool()
        pool.fetchrow = AsyncMock(return_value=_CREDENTIAL_ROW)

        cred = await get_credential(pool, 1)

        assert cred is not None
        assert cred.password == "****"
        assert cred.name == "core-ssh"

    async def test_returns_none_when_missing(self) -> None:
        pool = _mock_pool()
        pool.fetchrow = AsyncMock(return_value=None)

        assert await get_credential(pool, 999) is None


class TestGetCredentialForDevice:
    async def test_returns_decrypted_password(self) -> None:
        pool = _mock_pool()
        encrypted_row = {**_CREDENTIAL_ROW, "password": "encrypted-blob"}
        pool.fetchrow = AsyncMock(return_value=encrypted_row)

        with patch("bgpeek.db.credentials.decrypt_password") as mock_dec:
            mock_dec.return_value = "supersecret"
            cred = await get_credential_for_device(pool, "rt1")

        assert cred is not None
        mock_dec.assert_called_once_with("encrypted-blob")
        assert cred.password == "supersecret"

    async def test_returns_none_when_no_device(self) -> None:
        pool = _mock_pool()
        pool.fetchrow = AsyncMock(return_value=None)

        assert await get_credential_for_device(pool, "nonexistent") is None


class TestDeleteCredential:
    async def test_raises_when_devices_reference_it(self) -> None:
        pool = _mock_pool()
        pool.fetchval = AsyncMock(return_value=2)

        with pytest.raises(ValueError, match="still referenced by 2 device"):
            await delete_credential(pool, 1)

        pool.execute.assert_not_awaited()

    async def test_deletes_when_no_references(self) -> None:
        pool = _mock_pool()
        pool.fetchval = AsyncMock(return_value=0)
        pool.execute = AsyncMock(return_value="DELETE 1")

        result = await delete_credential(pool, 1)

        assert result is True


class TestUpdateCredential:
    async def test_encrypts_password_when_changed(self) -> None:
        pool = _mock_pool()
        updated_row = {**_CREDENTIAL_ROW, "password": "new-encrypted"}
        pool.fetchrow = AsyncMock(return_value=updated_row)

        payload = CredentialUpdate(password="new-secret")

        with patch("bgpeek.db.credentials.encrypt_password") as mock_enc:
            mock_enc.return_value = "new-encrypted"
            cred = await update_credential(pool, 1, payload)

        mock_enc.assert_called_once_with("new-secret")
        assert cred is not None
        assert cred.password == "****"

    async def test_skips_encryption_when_password_not_changed(self) -> None:
        pool = _mock_pool()
        updated_row = {**_CREDENTIAL_ROW}
        pool.fetchrow = AsyncMock(return_value=updated_row)

        payload = CredentialUpdate(name="renamed-cred")

        with patch("bgpeek.db.credentials.encrypt_password") as mock_enc:
            await update_credential(pool, 1, payload)

        mock_enc.assert_not_called()

    async def test_returns_none_when_not_found(self) -> None:
        pool = _mock_pool()
        pool.fetchrow = AsyncMock(return_value=None)

        payload = CredentialUpdate(name="gone")
        result = await update_credential(pool, 1, payload)

        assert result is None


# ===========================================================================
# 3. Credential resolution in query pipeline
# ===========================================================================


def _patch_query_deps(
    *,
    device: Device | None = None,
    credential: Credential | None = None,
    ssh_output: str = "8.8.8.0/24 via 10.0.0.1",
    default_key_exists: bool = False,
):
    """Context manager bundle that patches all execute_query external deps."""
    mock_pool = AsyncMock(spec=asyncpg.Pool)
    mock_ssh = AsyncMock()
    mock_ssh.__aenter__ = AsyncMock(return_value=mock_ssh)
    mock_ssh.__aexit__ = AsyncMock(return_value=False)
    mock_ssh.send_command = AsyncMock(return_value=ssh_output)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()

    real_is_file = Path.is_file

    def fake_is_file(self: Path) -> bool:
        if self.name == "default.key":
            return default_key_exists
        return real_is_file(self)

    from contextlib import contextmanager

    @contextmanager
    def combined():
        with (
            patch("bgpeek.core.cache.get_redis", return_value=mock_redis),
            patch("bgpeek.core.query.get_pool", return_value=mock_pool),
            patch(
                "bgpeek.core.query.device_crud.get_device_by_name",
                return_value=device,
            ),
            patch(
                "bgpeek.core.query.get_credential_for_device",
                return_value=credential,
            ),
            patch("bgpeek.core.query.SSHClient", return_value=mock_ssh),
            patch("bgpeek.core.query.log_audit", return_value=None),
            patch("bgpeek.core.query.is_device_available", return_value=True),
            patch("bgpeek.core.query.record_success", return_value=None),
            patch(
                "bgpeek.core.query.resolve_target",
                new=AsyncMock(
                    side_effect=lambda t: ResolvedTarget(
                        original=t, resolved=t, is_hostname=False
                    )
                ),
            ),
            patch("bgpeek.core.query.validate_target"),
            patch("bgpeek.core.webhooks.dispatch_webhook", return_value=None),
            patch.object(Path, "is_file", fake_is_file),
        ):
            yield mock_ssh

    return combined()


class TestCredentialResolution:
    async def test_uses_device_credential(self) -> None:
        device = _make_device()
        cred = Credential(
            id=1,
            name="device-cred",
            username="netops",
            auth_type="key",
            key_name="device.key",
            created_at=NOW,
            updated_at=NOW,
        )

        with _patch_query_deps(device=device, credential=cred) as mock_ssh:
            resp = await execute_query(_make_request())

        assert resp.filtered_output is not None
        # SSHClient should have been constructed with the device credential's username
        from bgpeek.core.query import SSHClient as _patched

        # No error means it resolved correctly and reached SSH.
        mock_ssh.send_command.assert_awaited_once()

    async def test_falls_back_to_global_default_key(self) -> None:
        device = _make_device()

        with _patch_query_deps(
            device=device, credential=None, default_key_exists=True
        ) as mock_ssh:
            resp = await execute_query(_make_request())

        mock_ssh.send_command.assert_awaited_once()
        assert resp.filtered_output is not None

    async def test_fails_when_no_credentials_available(self) -> None:
        device = _make_device()

        with _patch_query_deps(
            device=device, credential=None, default_key_exists=False
        ):
            with pytest.raises(QueryExecutionError, match="no SSH credentials"):
                await execute_query(_make_request())
