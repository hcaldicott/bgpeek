"""Tests for parallel multi-device query execution."""

from __future__ import annotations

from ipaddress import IPv4Address
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from pydantic import ValidationError

from bgpeek.core.parallel import execute_parallel
from bgpeek.db import devices as device_crud
from bgpeek.models.device import DeviceCreate
from bgpeek.models.query import (
    MultiQueryRequest,
    MultiQueryResponse,
    QueryType,
)


async def _seed_device(pool: asyncpg.Pool, name: str = "rt1", address: str = "10.0.0.1") -> None:
    await device_crud.create_device(
        pool,
        DeviceCreate(
            name=name,
            address=IPv4Address(address),
            platform="juniper_junos",
        ),
    )


def _mock_ssh(output: str = "mock bgp output\n8.8.8.0/24 via 10.0.0.1") -> AsyncMock:
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.send_command = AsyncMock(return_value=output)
    return mock


@pytest.fixture(autouse=True)
def _patch_pool(pool: asyncpg.Pool) -> None:  # noqa: PT004
    import bgpeek.db.pool as pool_mod

    pool_mod._pool = pool


async def test_parallel_two_devices(pool: asyncpg.Pool) -> None:
    await _seed_device(pool, "rt1", "10.0.0.1")
    await _seed_device(pool, "rt2", "10.0.0.2")

    req = MultiQueryRequest(
        device_names=["rt1", "rt2"],
        query_type=QueryType.BGP_ROUTE,
        target="8.8.8.0/24",
    )

    with patch("bgpeek.core.query.SSHClient", return_value=_mock_ssh()):
        resp = await execute_parallel(req)

    assert isinstance(resp, MultiQueryResponse)
    assert resp.device_count == 2
    assert len(resp.results) == 2
    assert len(resp.errors) == 0
    assert resp.total_runtime_ms >= 0
    device_names = {r.device_name for r in resp.results}
    assert device_names == {"rt1", "rt2"}


async def test_parallel_single_device(pool: asyncpg.Pool) -> None:
    await _seed_device(pool, "rt1")

    req = MultiQueryRequest(
        device_names=["rt1"],
        query_type=QueryType.PING,
        target="8.8.8.8",
    )

    with patch("bgpeek.core.query.SSHClient", return_value=_mock_ssh("PING 8.8.8.8: 5 packets")):
        resp = await execute_parallel(req)

    assert resp.device_count == 1
    assert len(resp.results) == 1
    assert len(resp.errors) == 0


async def test_parallel_partial_failure(pool: asyncpg.Pool) -> None:
    await _seed_device(pool, "rt1")
    # rt-missing does NOT exist in DB

    req = MultiQueryRequest(
        device_names=["rt1", "rt-missing"],
        query_type=QueryType.PING,
        target="8.8.8.8",
    )

    with patch("bgpeek.core.query.SSHClient", return_value=_mock_ssh("PING ok")):
        resp = await execute_parallel(req)

    assert len(resp.results) == 1
    assert resp.results[0].device_name == "rt1"
    assert len(resp.errors) == 1
    assert resp.errors[0].device_name == "rt-missing"
    assert "not found" in resp.errors[0].detail


async def test_parallel_semaphore_limits_concurrency(pool: asyncpg.Pool) -> None:
    await _seed_device(pool, "rt1", "10.0.0.1")
    await _seed_device(pool, "rt2", "10.0.0.2")
    await _seed_device(pool, "rt3", "10.0.0.3")

    req = MultiQueryRequest(
        device_names=["rt1", "rt2", "rt3"],
        query_type=QueryType.PING,
        target="8.8.8.8",
    )

    with patch("bgpeek.core.query.SSHClient", return_value=_mock_ssh("PING ok")):
        resp = await execute_parallel(req, max_concurrency=1)

    assert len(resp.results) == 3
    assert len(resp.errors) == 0


async def test_parallel_bogon_rejected(pool: asyncpg.Pool) -> None:
    await _seed_device(pool, "rt1")
    await _seed_device(pool, "rt2", "10.0.0.2")

    req = MultiQueryRequest(
        device_names=["rt1", "rt2"],
        query_type=QueryType.BGP_ROUTE,
        target="10.0.0.0/8",
    )

    resp = await execute_parallel(req)

    assert len(resp.results) == 0
    assert len(resp.errors) == 2
    for err in resp.errors:
        assert "bogon" in err.detail


async def test_parallel_all_devices_not_found(pool: asyncpg.Pool) -> None:
    req = MultiQueryRequest(
        device_names=["ghost1", "ghost2"],
        query_type=QueryType.PING,
        target="8.8.8.8",
    )

    resp = await execute_parallel(req)

    assert len(resp.results) == 0
    assert len(resp.errors) == 2
    for err in resp.errors:
        assert "not found" in err.detail


async def test_multi_query_request_validation() -> None:
    with pytest.raises(ValidationError, match="too_short"):
        MultiQueryRequest(
            device_names=[],
            query_type=QueryType.PING,
            target="8.8.8.8",
        )

    with pytest.raises(ValidationError, match="too_long"):
        MultiQueryRequest(
            device_names=["d" + str(i) for i in range(11)],
            query_type=QueryType.PING,
            target="8.8.8.8",
        )

    req = MultiQueryRequest(
        device_names=["rt1"],
        query_type=QueryType.PING,
        target="8.8.8.8",
    )
    assert len(req.device_names) == 1
