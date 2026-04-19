"""Tests for the configurable prefix-length cutoff (max_prefix_v4/v6)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from bgpeek.api.query import _friendly_error
from bgpeek.config import Settings


def test_max_prefix_defaults_match_historical_behavior() -> None:
    s = Settings()
    assert s.max_prefix_v4 == 24
    assert s.max_prefix_v6 == 48


@pytest.mark.parametrize("v4", [8, 16, 24, 27, 31, 32])
def test_max_prefix_v4_accepts_valid_range(v4: int) -> None:
    s = Settings(max_prefix_v4=v4)
    assert s.max_prefix_v4 == v4


@pytest.mark.parametrize("v4", [0, 7, 33, 64])
def test_max_prefix_v4_rejects_out_of_range(v4: int) -> None:
    with pytest.raises(ValidationError):
        Settings(max_prefix_v4=v4)


@pytest.mark.parametrize("v6", [16, 48, 64, 127, 128])
def test_max_prefix_v6_accepts_valid_range(v6: int) -> None:
    s = Settings(max_prefix_v6=v6)
    assert s.max_prefix_v6 == v6


@pytest.mark.parametrize("v6", [0, 15, 129, 256])
def test_max_prefix_v6_rejects_out_of_range(v6: int) -> None:
    with pytest.raises(ValidationError):
        Settings(max_prefix_v6=v6)


def test_friendly_error_formats_cutoff_values() -> None:
    t = {"error_prefix_too_specific": "Prefix too specific (max /{v4} for IPv4, /{v6} for IPv6)"}
    with patch("bgpeek.api.query.settings") as mock_settings:
        mock_settings.max_prefix_v4 = 27
        mock_settings.max_prefix_v6 = 56
        msg = _friendly_error("prefix too specific", t)
    assert "/27" in msg
    assert "/56" in msg


def test_friendly_error_survives_missing_placeholders() -> None:
    """Older translations without {v4}/{v6} placeholders should still render."""
    t = {"error_prefix_too_specific": "Prefix too specific"}
    with patch("bgpeek.api.query.settings") as mock_settings:
        mock_settings.max_prefix_v4 = 24
        mock_settings.max_prefix_v6 = 48
        msg = _friendly_error("prefix too specific", t)
    assert msg == "Prefix too specific"
