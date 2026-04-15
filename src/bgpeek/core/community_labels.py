"""In-memory cache and lookup for community labels.

The community_labels table is small and read-heavy (hit on every
rendered BGP result), so keep a process-local snapshot and invalidate
it whenever the API mutates a row.
"""

from __future__ import annotations

import asyncio

import structlog

from bgpeek.db import community_labels as crud
from bgpeek.db.pool import get_pool
from bgpeek.models.community_label import CommunityLabel, MatchType

log = structlog.get_logger(__name__)

_cache: list[CommunityLabel] = []
_lock = asyncio.Lock()
_loaded = False


async def refresh_cache() -> None:
    """Reload the snapshot from PostgreSQL."""
    global _cache, _loaded
    async with _lock:
        try:
            _cache = await crud.list_labels(get_pool())
            _loaded = True
        except Exception:
            log.warning("community_labels_cache_refresh_failed", exc_info=True)


async def ensure_loaded() -> None:
    """Load the cache once per process if it hasn't been yet."""
    if not _loaded:
        await refresh_cache()


def get_labels() -> list[CommunityLabel]:
    """Return the current cached snapshot (may be empty before first load)."""
    return list(_cache)


def _match(community: str, entry: CommunityLabel) -> bool:
    if entry.match_type is MatchType.EXACT:
        return community == entry.pattern
    return community.startswith(entry.pattern)


def annotate(community: str) -> str:
    """Return the community string with its label appended, if any.

    Exact matches win over prefix matches; among prefix matches, the
    longest pattern wins.
    """
    exact_label: str | None = None
    prefix_label: str | None = None
    prefix_len = -1
    for entry in _cache:
        if not _match(community, entry):
            continue
        if entry.match_type is MatchType.EXACT:
            exact_label = entry.label
            break
        if len(entry.pattern) > prefix_len:
            prefix_label = entry.label
            prefix_len = len(entry.pattern)

    label = exact_label or prefix_label
    return f"{community} ({label})" if label else community
