"""Tests for the /history page and related utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
from fastapi.testclient import TestClient

from bgpeek.core.time_utils import timeago
from bgpeek.db.results import list_results, save_result
from bgpeek.main import app
from bgpeek.models.query import BGPRoute, QueryResponse, QueryType


def _make_response(**overrides: object) -> QueryResponse:
    defaults: dict[str, object] = {
        "device_name": "rt1",
        "query_type": QueryType.BGP_ROUTE,
        "target": "8.8.8.0/24",
        "command": "show route 8.8.8.0/24",
        "raw_output": "8.8.8.0/24 via 10.0.0.1",
        "filtered_output": "8.8.8.0/24 via 10.0.0.1",
        "runtime_ms": 42,
        "parsed_routes": [
            BGPRoute(prefix="8.8.8.0/24", next_hop="10.0.0.1", as_path="15169", best=True)
        ],
    }
    defaults.update(overrides)
    return QueryResponse(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Route tests (no DB required — history page renders with empty pool stub)
# ---------------------------------------------------------------------------


def test_history_page_renders() -> None:
    client = TestClient(app)
    response = client.get("/history")
    assert response.status_code == 200
    assert "Query History" in response.text


# ---------------------------------------------------------------------------
# DB-backed tests
# ---------------------------------------------------------------------------


async def test_history_shows_stored_results(pool: asyncpg.Pool) -> None:
    await save_result(
        pool,
        _make_response(target="1.1.1.0/24", device_name="edge1"),
        user_id=None,
        username=None,
        ttl_days=7,
    )
    results = await list_results(pool)
    assert len(results) == 1
    assert results[0].target == "1.1.1.0/24"
    assert results[0].device_name == "edge1"


async def test_pagination_offset(pool: asyncpg.Pool) -> None:
    for i in range(5):
        await save_result(
            pool,
            _make_response(target=f"{i}.0.0.0/24"),
            user_id=None,
            username=None,
            ttl_days=7,
        )

    page1 = await list_results(pool, limit=2, offset=0)
    assert len(page1) == 2

    page2 = await list_results(pool, limit=2, offset=2)
    assert len(page2) == 2

    page3 = await list_results(pool, limit=2, offset=4)
    assert len(page3) == 1

    # No overlap between pages
    all_targets = {r.target for r in page1} | {r.target for r in page2} | {r.target for r in page3}
    assert len(all_targets) == 5


# ---------------------------------------------------------------------------
# timeago filter tests
# ---------------------------------------------------------------------------


def test_timeago_just_now() -> None:
    now = datetime.now(UTC)
    assert timeago(now) == "just now"


def test_timeago_minutes() -> None:
    dt = datetime.now(UTC) - timedelta(minutes=5)
    assert timeago(dt) == "5 min ago"


def test_timeago_hours() -> None:
    dt = datetime.now(UTC) - timedelta(hours=3)
    assert timeago(dt) == "3 hours ago"


def test_timeago_single_hour() -> None:
    dt = datetime.now(UTC) - timedelta(hours=1)
    assert timeago(dt) == "1 hour ago"


def test_timeago_days() -> None:
    dt = datetime.now(UTC) - timedelta(days=2)
    assert timeago(dt) == "2 days ago"


def test_timeago_single_day() -> None:
    dt = datetime.now(UTC) - timedelta(days=1)
    assert timeago(dt) == "1 day ago"


def test_timeago_old_date() -> None:
    dt = datetime(2024, 3, 15, tzinfo=UTC)
    result = timeago(dt)
    assert result == "Mar 15"


def test_timeago_naive_datetime() -> None:
    dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    assert timeago(dt) == "10 min ago"
