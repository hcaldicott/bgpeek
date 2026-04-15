"""Tests for community label lookup and annotation."""

from __future__ import annotations

from datetime import datetime

from bgpeek.core import community_labels as cl
from bgpeek.models.community_label import CommunityLabel, MatchType


def _make(pattern: str, match_type: MatchType, label: str, label_id: int = 1) -> CommunityLabel:
    now = datetime.now()
    return CommunityLabel(
        id=label_id,
        pattern=pattern,
        match_type=match_type,
        label=label,
        created_at=now,
        updated_at=now,
    )


def _install(entries: list[CommunityLabel]) -> None:
    cl._cache = list(entries)


def test_annotate_no_labels_loaded() -> None:
    _install([])
    assert cl.annotate("64500:100") == "64500:100"


def test_annotate_exact_match() -> None:
    _install([_make("64500:100", MatchType.EXACT, "customer route")])
    assert cl.annotate("64500:100") == "64500:100 (customer route)"


def test_annotate_prefix_match() -> None:
    _install([_make("64500:1", MatchType.PREFIX, "from upstream")])
    assert cl.annotate("64500:1234") == "64500:1234 (from upstream)"


def test_annotate_no_match_when_pattern_not_prefix() -> None:
    _install([_make("64500:5", MatchType.PREFIX, "from peering")])
    assert cl.annotate("64500:100") == "64500:100"


def test_exact_match_beats_prefix() -> None:
    _install(
        [
            _make("64500:1", MatchType.PREFIX, "short prefix", 1),
            _make("64500:100", MatchType.EXACT, "exact tag", 2),
        ]
    )
    assert cl.annotate("64500:100") == "64500:100 (exact tag)"


def test_longest_prefix_wins() -> None:
    _install(
        [
            _make("64500:1", MatchType.PREFIX, "short", 1),
            _make("64500:12", MatchType.PREFIX, "specific", 2),
        ]
    )
    assert cl.annotate("64500:123") == "64500:123 (specific)"


def test_large_community_annotated_by_exact_match() -> None:
    _install([_make("large:64500:1:2", MatchType.EXACT, "Custom tag")])
    assert cl.annotate("large:64500:1:2") == "large:64500:1:2 (Custom tag)"
