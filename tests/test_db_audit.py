"""Tests for bgpeek.db.audit against a real PostgreSQL container."""

from __future__ import annotations

import asyncio
from ipaddress import IPv4Address, IPv6Address

import asyncpg

from bgpeek.db import audit as crud
from bgpeek.models.audit import AuditAction, AuditEntryCreate


def _entry(**overrides: object) -> AuditEntryCreate:
    base: dict[str, object] = {
        "action": AuditAction.QUERY,
        "success": True,
    }
    base.update(overrides)
    return AuditEntryCreate(**base)  # type: ignore[arg-type]


def _full_entry() -> AuditEntryCreate:
    return AuditEntryCreate(
        action=AuditAction.QUERY,
        success=True,
        user_id=None,
        username="alice",
        user_role="noc",
        source_ip=IPv4Address("192.0.2.10"),
        user_agent="curl/8.0",
        device_id=None,
        device_name="rt-edge-1",
        query_type="bgp_route",
        query_target="203.0.113.0/24",
        error_message=None,
        runtime_ms=42,
        response_bytes=1024,
    )


async def test_insert_minimal(pool: asyncpg.Pool) -> None:
    row = await crud.log_audit(pool, _entry())
    assert row.id > 0
    assert row.timestamp is not None
    assert row.action == AuditAction.QUERY
    assert row.success is True
    assert row.user_id is None
    assert row.username is None
    assert row.source_ip is None
    assert row.device_id is None
    assert row.query_target is None
    assert row.runtime_ms is None


async def test_insert_full(pool: asyncpg.Pool) -> None:
    payload = _full_entry()
    row = await crud.log_audit(pool, payload)
    assert row.username == "alice"
    assert row.user_role == "noc"
    assert row.source_ip == IPv4Address("192.0.2.10")
    assert row.user_agent == "curl/8.0"
    assert row.device_name == "rt-edge-1"
    assert row.query_type == "bgp_route"
    assert row.query_target == "203.0.113.0/24"
    assert row.runtime_ms == 42
    assert row.response_bytes == 1024


async def test_timestamp_auto(pool: asyncpg.Pool) -> None:
    a = await crud.log_audit(pool, _entry())
    await asyncio.sleep(0.01)
    b = await crud.log_audit(pool, _entry())
    assert b.timestamp >= a.timestamp
    assert b.id > a.id


async def test_list_empty(pool: asyncpg.Pool) -> None:
    assert await crud.list_audit_entries(pool) == []


async def test_list_orders_newest_first(pool: asyncpg.Pool) -> None:
    first = await crud.log_audit(pool, _entry(query_target="first"))
    await asyncio.sleep(0.01)
    second = await crud.log_audit(pool, _entry(query_target="second"))
    await asyncio.sleep(0.01)
    third = await crud.log_audit(pool, _entry(query_target="third"))

    rows = await crud.list_audit_entries(pool)
    assert [r.id for r in rows] == [third.id, second.id, first.id]


async def test_list_pagination(pool: asyncpg.Pool) -> None:
    created = []
    for i in range(5):
        created.append(await crud.log_audit(pool, _entry(query_target=f"q{i}")))
        await asyncio.sleep(0.005)

    page = await crud.list_audit_entries(pool, limit=2, offset=2)
    # newest-first order: created[4], created[3], created[2], created[1], created[0]
    # offset 2 skips the first two -> [created[2], created[1]]
    assert [r.id for r in page] == [created[2].id, created[1].id]


async def test_filter_by_action(pool: asyncpg.Pool) -> None:
    await crud.log_audit(pool, _entry(action=AuditAction.QUERY))
    await crud.log_audit(pool, _entry(action=AuditAction.LOGIN))
    await crud.log_audit(pool, _entry(action=AuditAction.QUERY))

    rows = await crud.list_audit_entries(pool, action=AuditAction.QUERY)
    assert len(rows) == 2
    assert all(r.action == AuditAction.QUERY for r in rows)


async def test_filter_by_user_id(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        uid1 = await conn.fetchval(
            "INSERT INTO users (username, auth_provider) VALUES ($1, $2) RETURNING id",
            "u1",
            "local",
        )
        uid2 = await conn.fetchval(
            "INSERT INTO users (username, auth_provider) VALUES ($1, $2) RETURNING id",
            "u2",
            "local",
        )

    await crud.log_audit(pool, _entry(user_id=uid1))
    await crud.log_audit(pool, _entry(user_id=uid2))
    await crud.log_audit(pool, _entry(user_id=uid1))

    rows = await crud.list_audit_entries(pool, user_id=uid1)
    assert len(rows) == 2
    assert all(r.user_id == uid1 for r in rows)


async def test_filter_by_device_id(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        did1 = await conn.fetchval(
            "INSERT INTO devices (name, address, platform) VALUES ($1, $2, $3) RETURNING id",
            "rt-a",
            "10.0.0.1",
            "juniper_junos",
        )
        did2 = await conn.fetchval(
            "INSERT INTO devices (name, address, platform) VALUES ($1, $2, $3) RETURNING id",
            "rt-b",
            "10.0.0.2",
            "juniper_junos",
        )

    await crud.log_audit(pool, _entry(device_id=did1))
    await crud.log_audit(pool, _entry(device_id=did2))
    await crud.log_audit(pool, _entry(device_id=did1))

    rows = await crud.list_audit_entries(pool, device_id=did1)
    assert len(rows) == 2
    assert all(r.device_id == did1 for r in rows)


async def test_filter_by_success(pool: asyncpg.Pool) -> None:
    await crud.log_audit(pool, _entry(success=True))
    await crud.log_audit(pool, _entry(success=False, error_message="boom"))
    await crud.log_audit(pool, _entry(success=True))

    ok = await crud.list_audit_entries(pool, success=True)
    fail = await crud.list_audit_entries(pool, success=False)
    assert len(ok) == 2
    assert len(fail) == 1
    assert fail[0].error_message == "boom"


async def test_filter_combination(pool: asyncpg.Pool) -> None:
    await crud.log_audit(pool, _entry(action=AuditAction.QUERY, success=True))
    await crud.log_audit(pool, _entry(action=AuditAction.QUERY, success=False))
    await crud.log_audit(pool, _entry(action=AuditAction.LOGIN, success=True))

    rows = await crud.list_audit_entries(pool, action=AuditAction.QUERY, success=True)
    assert len(rows) == 1
    assert rows[0].action == AuditAction.QUERY
    assert rows[0].success is True


async def test_count_matches_list_length(pool: asyncpg.Pool) -> None:
    await crud.log_audit(pool, _entry(action=AuditAction.QUERY, success=True))
    await crud.log_audit(pool, _entry(action=AuditAction.QUERY, success=False))
    await crud.log_audit(pool, _entry(action=AuditAction.LOGIN, success=True))
    await crud.log_audit(pool, _entry(action=AuditAction.LOGOUT, success=True))

    rows = await crud.list_audit_entries(pool, limit=1000)
    assert await crud.count_audit_entries(pool) == len(rows)

    q_rows = await crud.list_audit_entries(pool, action=AuditAction.QUERY, limit=1000)
    assert await crud.count_audit_entries(pool, action=AuditAction.QUERY) == len(q_rows)

    combo_rows = await crud.list_audit_entries(
        pool, action=AuditAction.QUERY, success=False, limit=1000
    )
    combo_count = await crud.count_audit_entries(pool, action=AuditAction.QUERY, success=False)
    assert combo_count == len(combo_rows)


async def test_insert_with_ipv6_source(pool: asyncpg.Pool) -> None:
    row = await crud.log_audit(pool, _entry(source_ip=IPv6Address("2001:db8::1")))
    assert row.source_ip == IPv6Address("2001:db8::1")


async def test_insert_with_ipv4_source(pool: asyncpg.Pool) -> None:
    row = await crud.log_audit(pool, _entry(source_ip=IPv4Address("10.0.0.1")))
    assert row.source_ip == IPv4Address("10.0.0.1")


async def test_action_enum_string_value(pool: asyncpg.Pool) -> None:
    await crud.log_audit(pool, _entry(action=AuditAction.QUERY))
    raw = await pool.fetchval("SELECT action FROM audit_log LIMIT 1")
    assert raw == "query"
