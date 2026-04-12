"""Utilities for human-friendly time formatting."""

from __future__ import annotations

from datetime import UTC, datetime


def timeago(dt: datetime) -> str:
    """Format *dt* as a relative time string (e.g. '2 min ago', '3 hours ago').

    Falls back to a short absolute date for anything older than 7 days.
    Naive datetimes are assumed UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    delta = now - dt

    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"

    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"

    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"

    return dt.strftime("%b %d")
