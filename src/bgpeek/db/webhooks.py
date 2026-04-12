"""CRUD queries for the ``webhooks`` table."""

from __future__ import annotations

import asyncpg

from bgpeek.models.webhook import Webhook, WebhookCreate, WebhookEvent, WebhookUpdate


async def create_webhook(pool: asyncpg.Pool, payload: WebhookCreate) -> Webhook:
    """Insert a new webhook and return the persisted row."""
    row = await pool.fetchrow(
        """
        INSERT INTO webhooks (name, url, secret, events, enabled)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        payload.name,
        payload.url,
        payload.secret,
        [e.value for e in payload.events],
        payload.enabled,
    )
    assert row is not None
    return Webhook.model_validate(dict(row))


async def get_webhook(pool: asyncpg.Pool, webhook_id: int) -> Webhook | None:
    """Fetch a single webhook by primary key, or None."""
    row = await pool.fetchrow("SELECT * FROM webhooks WHERE id = $1", webhook_id)
    return Webhook.model_validate(dict(row)) if row else None


async def list_webhooks(pool: asyncpg.Pool) -> list[Webhook]:
    """Return all webhooks ordered by name."""
    rows = await pool.fetch("SELECT * FROM webhooks ORDER BY name ASC")
    return [Webhook.model_validate(dict(r)) for r in rows]


async def list_webhooks_for_event(pool: asyncpg.Pool, event: WebhookEvent) -> list[Webhook]:
    """Return only enabled webhooks whose events array contains the given event."""
    rows = await pool.fetch(
        "SELECT * FROM webhooks WHERE enabled IS TRUE AND $1 = ANY(events)",
        event.value,
    )
    return [Webhook.model_validate(dict(r)) for r in rows]


_UPDATABLE_COLUMNS: frozenset[str] = frozenset({"name", "url", "secret", "events", "enabled"})


async def update_webhook(
    pool: asyncpg.Pool, webhook_id: int, payload: WebhookUpdate
) -> Webhook | None:
    """Apply a partial update; returns the updated row or None if not found."""
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return await get_webhook(pool, webhook_id)

    set_clause_parts: list[str] = []
    values: list[object] = []
    for idx, (column, value) in enumerate(fields.items(), start=1):
        if column not in _UPDATABLE_COLUMNS:
            raise ValueError(f"refusing to update unknown column: {column!r}")
        if column == "events" and value is not None:
            value = [e.value if isinstance(e, WebhookEvent) else e for e in value]
        set_clause_parts.append(f"{column} = ${idx}")
        values.append(value)
    set_clause_parts.append("updated_at = now()")
    set_clause = ", ".join(set_clause_parts)
    values.append(webhook_id)

    query = f"UPDATE webhooks SET {set_clause} WHERE id = ${len(values)} RETURNING *"  # noqa: S608
    row = await pool.fetchrow(query, *values)
    return Webhook.model_validate(dict(row)) if row else None


async def delete_webhook(pool: asyncpg.Pool, webhook_id: int) -> bool:
    """Delete a webhook. Returns True if a row was removed."""
    result: str = await pool.execute("DELETE FROM webhooks WHERE id = $1", webhook_id)
    return result.endswith(" 1")
