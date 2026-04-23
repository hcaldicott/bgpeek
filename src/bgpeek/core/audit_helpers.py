"""Small context helpers for populating `AuditEntryCreate` from request/user state.

The admin panel, REST API, and auth endpoints all want the same five
fields on every audit row — source IP, user agent, user id, username and
role — so writing them out inline in every handler produces ~60 lines of
near-identical boilerplate. The two helpers here return `**kwargs` dicts
that slot straight into `AuditEntryCreate(...)`, keeping each call site a
one-liner.

Guest users (synthetic `guest_user()` with `id=0`) get `user_id=None` so
the FK on `audit_log.user_id` is never violated; the textual username is
still recorded for log correlation.
"""

from __future__ import annotations

from ipaddress import ip_address
from typing import TYPE_CHECKING, Any

from bgpeek.core.rate_limit import get_client_ip

if TYPE_CHECKING:
    from fastapi import Request

    from bgpeek.models.user import User


def request_ctx(request: Request | None) -> dict[str, Any]:
    """Pull source_ip + user_agent from a FastAPI Request for audit rows.

    `source_ip` is normalised through `ipaddress.ip_address` so the Pydantic
    `IPAddress` field accepts it. Non-parseable values (e.g. TestClient's
    synthetic `testclient` host) fall back to None — the audit row still
    lands, just without the IP column.
    """
    if request is None:
        return {"source_ip": None, "user_agent": None}
    raw: str | None
    try:
        raw = get_client_ip(request)
    except Exception:
        raw = None
    source_ip: str | None
    try:
        source_ip = str(ip_address(raw)) if raw else None
    except ValueError:
        source_ip = None
    return {
        "source_ip": source_ip,
        "user_agent": request.headers.get("user-agent"),
    }


def user_ctx(user: User | None) -> dict[str, Any]:
    """Pull user_id / username / user_role from an authenticated User for audit rows.

    Guest users have the synthetic id=0, which would violate the `audit_log.user_id`
    foreign key. We record the username verbatim but drop the id in that case.
    """
    if user is None:
        return {"user_id": None, "username": None, "user_role": None}
    user_id = user.id if user.id > 0 else None
    return {
        "user_id": user_id,
        "username": user.username,
        "user_role": user.role.value,
    }
