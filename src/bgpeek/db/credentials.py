"""CRUD queries for the `credentials` table."""

from __future__ import annotations

import asyncpg

from bgpeek.core.encryption import decrypt_password, encrypt_password
from bgpeek.models.credential import (
    Credential,
    CredentialCreate,
    CredentialUpdate,
    CredentialWithUsage,
)


def _mask_password(row: dict[str, object]) -> dict[str, object]:
    """Replace the password value with ``****`` if it is not None."""
    if row.get("password") is not None:
        row["password"] = "****"  # noqa: S105
    return row


async def list_credentials(pool: asyncpg.Pool) -> list[CredentialWithUsage]:
    """Return all credentials with the number of devices referencing each one."""
    rows = await pool.fetch(
        """
        SELECT c.*, COUNT(d.id) AS device_count
        FROM credentials c
        LEFT JOIN devices d ON d.credential_id = c.id
        GROUP BY c.id
        ORDER BY c.name ASC
        """
    )
    return [CredentialWithUsage.model_validate(_mask_password(dict(r))) for r in rows]


async def get_credential(pool: asyncpg.Pool, credential_id: int) -> Credential | None:
    """Fetch a single credential by primary key, or ``None``."""
    row = await pool.fetchrow("SELECT * FROM credentials WHERE id = $1", credential_id)
    if row is None:
        return None
    return Credential.model_validate(_mask_password(dict(row)))


async def get_credential_by_name(pool: asyncpg.Pool, name: str) -> Credential | None:
    """Fetch a single credential by unique name, or ``None``."""
    row = await pool.fetchrow("SELECT * FROM credentials WHERE name = $1", name)
    if row is None:
        return None
    return Credential.model_validate(_mask_password(dict(row)))


async def create_credential(pool: asyncpg.Pool, payload: CredentialCreate) -> Credential:
    """Insert a new credential.

    The password (if provided) is encrypted before storage.
    Raises ``asyncpg.UniqueViolationError`` on duplicate name.
    """
    stored_password: str | None = None
    if payload.password is not None:
        stored_password = encrypt_password(payload.password)

    row = await pool.fetchrow(
        """
        INSERT INTO credentials (name, description, auth_type, username, key_name, password)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        payload.name,
        payload.description,
        payload.auth_type,
        payload.username,
        payload.key_name,
        stored_password,
    )
    assert row is not None
    return Credential.model_validate(_mask_password(dict(row)))


# Whitelist of columns the API may update.  Pydantic enforces this on the
# CredentialUpdate model, but we double-check here so the dynamic SQL builder
# below can never see an attacker-controlled column name.
_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"name", "description", "auth_type", "username", "key_name", "password"}
)


async def update_credential(
    pool: asyncpg.Pool,
    credential_id: int,
    payload: CredentialUpdate,
) -> Credential | None:
    """Apply a partial update; returns the updated row or ``None`` if not found."""
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return await get_credential(pool, credential_id)

    # Encrypt password when it is being changed.
    if "password" in fields and fields["password"] is not None:
        fields["password"] = encrypt_password(fields["password"])

    set_clause_parts: list[str] = []
    values: list[object] = []
    for idx, (column, value) in enumerate(fields.items(), start=1):
        if column not in _UPDATABLE_COLUMNS:
            raise ValueError(f"refusing to update unknown column: {column!r}")
        set_clause_parts.append(f"{column} = ${idx}")
        values.append(value)
    set_clause_parts.append("updated_at = now()")
    set_clause = ", ".join(set_clause_parts)
    values.append(credential_id)

    query = f"UPDATE credentials SET {set_clause} WHERE id = ${len(values)} RETURNING *"  # noqa: S608
    row = await pool.fetchrow(query, *values)
    if row is None:
        return None
    return Credential.model_validate(_mask_password(dict(row)))


async def delete_credential(pool: asyncpg.Pool, credential_id: int) -> bool:
    """Delete a credential.

    Returns ``True`` if a row was removed.
    Raises ``ValueError`` if any device still references this credential.
    """
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM devices WHERE credential_id = $1", credential_id
    )
    if count:
        raise ValueError(f"credential {credential_id} is still referenced by {count} device(s)")
    result: str = await pool.execute("DELETE FROM credentials WHERE id = $1", credential_id)
    return result.endswith(" 1")


async def get_credential_raw(pool: asyncpg.Pool, credential_id: int) -> Credential | None:
    """Fetch a credential with the password **decrypted** (not masked).

    This is for internal use (e.g. SSH test) and must never be exposed directly.
    """
    row = await pool.fetchrow("SELECT * FROM credentials WHERE id = $1", credential_id)
    if row is None:
        return None
    data = dict(row)
    if data.get("password") is not None:
        data["password"] = decrypt_password(data["password"])
    return Credential.model_validate(data)


async def get_credential_for_device(pool: asyncpg.Pool, device_name: str) -> Credential | None:
    """Return the credential linked to a device, with the password **decrypted**.

    This is for internal SSH use only and must never be exposed via the API.
    """
    row = await pool.fetchrow(
        """
        SELECT c.*
        FROM credentials c
        JOIN devices d ON d.credential_id = c.id
        WHERE d.name = $1
        """,
        device_name,
    )
    if row is None:
        return None
    data = dict(row)
    if data.get("password") is not None:
        data["password"] = decrypt_password(data["password"])
    return Credential.model_validate(data)
