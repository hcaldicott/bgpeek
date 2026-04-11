"""CRUD queries for the `audit_log` table."""

from __future__ import annotations

import asyncpg

from bgpeek.models.audit import AuditAction, AuditEntry, AuditEntryCreate


async def log_audit(pool: asyncpg.Pool, entry: AuditEntryCreate) -> AuditEntry:
    """Insert an audit log entry and return the persisted row. Propagates DB errors."""
    row = await pool.fetchrow(
        """
        INSERT INTO audit_log (
            user_id, username, user_role, source_ip, user_agent,
            action, device_id, device_name, query_type, query_target,
            success, error_message, runtime_ms, response_bytes
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        RETURNING *
        """,
        entry.user_id,
        entry.username,
        entry.user_role,
        entry.source_ip,
        entry.user_agent,
        entry.action.value,
        entry.device_id,
        entry.device_name,
        entry.query_type,
        entry.query_target,
        entry.success,
        entry.error_message,
        entry.runtime_ms,
        entry.response_bytes,
    )
    assert row is not None
    return AuditEntry.model_validate(dict(row))


def _build_filter(
    *,
    action: AuditAction | None,
    user_id: int | None,
    device_id: int | None,
    success: bool | None,
) -> tuple[str, list[object]]:
    """Build a parameterised WHERE clause from optional filters."""
    fragments: list[str] = []
    values: list[object] = []
    if action is not None:
        values.append(action.value)
        fragments.append(f"action = ${len(values)}")
    if user_id is not None:
        values.append(user_id)
        fragments.append(f"user_id = ${len(values)}")
    if device_id is not None:
        values.append(device_id)
        fragments.append(f"device_id = ${len(values)}")
    if success is not None:
        values.append(success)
        fragments.append(f"success = ${len(values)}")
    where = f" WHERE {' AND '.join(fragments)}" if fragments else ""
    return where, values


async def list_audit_entries(
    pool: asyncpg.Pool,
    *,
    limit: int = 100,
    offset: int = 0,
    action: AuditAction | None = None,
    user_id: int | None = None,
    device_id: int | None = None,
    success: bool | None = None,
) -> list[AuditEntry]:
    """List audit entries newest-first with optional filters."""
    where, values = _build_filter(
        action=action, user_id=user_id, device_id=device_id, success=success
    )
    values.append(limit)
    limit_idx = len(values)
    values.append(offset)
    offset_idx = len(values)
    query = (
        f"SELECT * FROM audit_log{where} "  # noqa: S608
        f"ORDER BY timestamp DESC, id DESC "
        f"LIMIT ${limit_idx} OFFSET ${offset_idx}"
    )
    rows = await pool.fetch(query, *values)
    return [AuditEntry.model_validate(dict(r)) for r in rows]


async def count_audit_entries(
    pool: asyncpg.Pool,
    *,
    action: AuditAction | None = None,
    user_id: int | None = None,
    device_id: int | None = None,
    success: bool | None = None,
) -> int:
    """Count rows matching the same filter set as `list_audit_entries`."""
    where, values = _build_filter(
        action=action, user_id=user_id, device_id=device_id, success=success
    )
    query = f"SELECT COUNT(*) FROM audit_log{where}"  # noqa: S608
    result = await pool.fetchval(query, *values)
    return int(result)
