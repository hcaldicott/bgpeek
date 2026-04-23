"""CRUD queries for the `users` table."""

from __future__ import annotations

import hashlib

import asyncpg
import bcrypt

from bgpeek.models.user import User, UserCreate, UserCreateLocal, UserRole, UserUpdate


class IdentityProviderConflictError(Exception):
    """Raised when an external IdP upsert targets a username owned by another provider.

    Guards against the scenario where a local or LDAP user named ``alice`` already
    exists and an OIDC token (or vice versa) would otherwise silently overwrite
    the row's ``role`` / ``email``. Callers translate this to a 409 (or a neutral
    401 on interactive paths) rather than letting the overwrite happen.
    """

    def __init__(self, username: str, existing_provider: str, attempted_provider: str) -> None:
        self.username = username
        self.existing_provider = existing_provider
        self.attempted_provider = attempted_provider
        super().__init__(
            f"username {username!r} is owned by provider {existing_provider!r}; "
            f"refusing upsert as {attempted_provider!r}"
        )


def _hash_key(api_key: str) -> str:
    """SHA-256 hash of a raw API key for safe storage and lookup."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def _hash_password(password: str) -> str:
    """Bcrypt-hash a plaintext password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


async def create_user(pool: asyncpg.Pool, payload: UserCreate) -> User:
    """Insert a new API-key user. Raises `asyncpg.UniqueViolationError` on duplicate username."""
    row = await pool.fetchrow(
        """
        INSERT INTO users (username, email, role, auth_provider, api_key_hash, enabled)
        VALUES ($1, $2, $3, 'api_key', $4, $5)
        RETURNING *
        """,
        payload.username,
        payload.email,
        payload.role.value,
        _hash_key(payload.api_key),
        payload.enabled,
    )
    assert row is not None
    return User.model_validate(dict(row))


async def get_user_by_id(pool: asyncpg.Pool, user_id: int) -> User | None:
    """Fetch a single user by primary key, or None."""
    row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return User.model_validate(dict(row)) if row else None


async def get_user_by_api_key(pool: asyncpg.Pool, api_key: str) -> User | None:
    """Fetch a user by raw API key (hashed before lookup), or None."""
    row = await pool.fetchrow(
        "SELECT * FROM users WHERE api_key_hash = $1 AND enabled IS TRUE",
        _hash_key(api_key),
    )
    return User.model_validate(dict(row)) if row else None


async def list_users(pool: asyncpg.Pool) -> list[User]:
    """Return all users ordered by username."""
    rows = await pool.fetch("SELECT * FROM users ORDER BY username ASC")
    return [User.model_validate(dict(r)) for r in rows]


_UPDATABLE_COLUMNS: frozenset[str] = frozenset({"username", "email", "role", "enabled"})


async def update_user(pool: asyncpg.Pool, user_id: int, payload: UserUpdate) -> User | None:
    """Apply a partial update; returns the updated row or None if not found."""
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return await get_user_by_id(pool, user_id)

    set_clause_parts: list[str] = []
    values: list[object] = []
    for idx, (column, value) in enumerate(fields.items(), start=1):
        if column not in _UPDATABLE_COLUMNS:
            raise ValueError(f"refusing to update unknown column: {column!r}")
        set_clause_parts.append(f"{column} = ${idx}")
        values.append(value)
    set_clause = ", ".join(set_clause_parts)
    values.append(user_id)

    query = f"UPDATE users SET {set_clause} WHERE id = ${len(values)} RETURNING *"  # noqa: S608
    row = await pool.fetchrow(query, *values)
    return User.model_validate(dict(row)) if row else None


async def delete_user(pool: asyncpg.Pool, user_id: int) -> bool:
    """Delete a user. Returns True if a row was removed."""
    result: str = await pool.execute("DELETE FROM users WHERE id = $1", user_id)
    return result.endswith(" 1")


async def create_local_user(pool: asyncpg.Pool, payload: UserCreateLocal) -> User:
    """Insert a new local (password) user. Raises ``asyncpg.UniqueViolationError`` on duplicate."""
    row = await pool.fetchrow(
        """
        INSERT INTO users (username, email, role, auth_provider, password_hash, enabled)
        VALUES ($1, $2, $3, 'local', $4, TRUE)
        RETURNING *
        """,
        payload.username,
        payload.email,
        payload.role.value,
        _hash_password(payload.password),
    )
    assert row is not None
    return User.model_validate(dict(row))


async def get_user_by_username(pool: asyncpg.Pool, username: str) -> User | None:
    """Fetch a user by username, or None."""
    row = await pool.fetchrow("SELECT * FROM users WHERE username = $1", username)
    return User.model_validate(dict(row)) if row else None


async def upsert_ldap_user(
    pool: asyncpg.Pool,
    username: str,
    email: str | None,
    role: UserRole,
) -> User:
    """Create or update an LDAP-provisioned user. Updates email, role, and last_login_at on conflict.

    Raises ``IdentityProviderConflictError`` when the conflicting row belongs to a
    different ``auth_provider`` — without that guard a local user ``alice``
    could be silently mutated by an LDAP bind that returns ``role=admin``.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO users (username, email, role, auth_provider, enabled)
        VALUES ($1, $2, $3, 'ldap', TRUE)
        ON CONFLICT (username) DO UPDATE
            SET email = EXCLUDED.email,
                role = EXCLUDED.role,
                last_login_at = now()
            WHERE users.auth_provider = 'ldap'
        RETURNING *
        """,
        username,
        email,
        role.value,
    )
    if row is None:
        existing = await pool.fetchrow(
            "SELECT auth_provider FROM users WHERE username = $1", username
        )
        existing_provider = existing["auth_provider"] if existing else "unknown"
        raise IdentityProviderConflictError(username, existing_provider, "ldap")
    return User.model_validate(dict(row))


async def upsert_oidc_user(
    pool: asyncpg.Pool,
    username: str,
    email: str | None,
    role: UserRole,
    oidc_sub: str,
) -> User:
    """Create or update an OIDC-provisioned user. Updates email, role, and last_login_at on conflict.

    See :class:`IdentityProviderConflictError` — a username owned by a different
    provider is rejected rather than silently overwritten.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO users (username, email, role, auth_provider, enabled)
        VALUES ($1, $2, $3, 'oidc', TRUE)
        ON CONFLICT (username) DO UPDATE
            SET email = EXCLUDED.email,
                role = EXCLUDED.role,
                last_login_at = now()
            WHERE users.auth_provider = 'oidc'
        RETURNING *
        """,
        username,
        email,
        role.value,
    )
    if row is None:
        existing = await pool.fetchrow(
            "SELECT auth_provider FROM users WHERE username = $1", username
        )
        existing_provider = existing["auth_provider"] if existing else "unknown"
        raise IdentityProviderConflictError(username, existing_provider, "oidc")
    return User.model_validate(dict(row))


async def get_user_by_credentials(pool: asyncpg.Pool, username: str, password: str) -> User | None:
    """Authenticate a local user by username and password. Returns None on mismatch or disabled."""
    row = await pool.fetchrow(
        "SELECT * FROM users WHERE username = $1 AND auth_provider = 'local' AND enabled IS TRUE",
        username,
    )
    if row is None:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return User.model_validate(dict(row))
