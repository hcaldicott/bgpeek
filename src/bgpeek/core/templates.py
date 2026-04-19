"""Shared Jinja2Templates instance.

Centralising this avoids the trap of registering filters on one
Jinja2Templates() and rendering through another — each instance owns
its own ``Environment``, so filters/globals don't propagate.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from bgpeek.config import settings
from bgpeek.core.community_labels import annotate as annotate_community
from bgpeek.core.community_labels import row_color as community_row_color
from bgpeek.core.time_utils import timeago


def _base_context(request: Request) -> dict[str, Any]:
    """Default context injected into every template render."""
    return {"user": getattr(request.state, "user", None)}


def _role_value(user: Any) -> str | None:
    """Return normalized role string for template user objects."""
    if user is None:
        return None
    role = getattr(user, "role", None)
    if role is None:
        return None
    return str(getattr(role, "value", role))


@pass_context
def header_links_for(
    context: Any,
    t: dict[str, str],
    user: Any,
    primary: tuple[str, str] | None = None,
    current_section: str | None = None,
) -> list[tuple[str, str]]:
    """Build consistent header links for all SSR pages."""
    if current_section is None:
        request = context.get("request")
        path = getattr(getattr(request, "url", None), "path", "") if request is not None else ""
        if path.startswith("/admin"):
            current_section = "admin"
        elif path.startswith("/history"):
            current_section = "history"

    links: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(href: str, label: str) -> None:
        if href in seen:
            return
        seen.add(href)
        links.append((href, label))

    if primary is not None:
        add(primary[0], primary[1])

    if current_section != "history":
        add("/history", t["history"])
    add("/api/docs", t["api_docs"])
    if _role_value(user) == "admin" and current_section != "admin":
        add("/admin", t["admin"])

    return links


templates = Jinja2Templates(
    directory=str(settings.templates_dir),
    context_processors=[_base_context],
)
_brand_footer = settings.brand_footer.strip()
_primary_asn = str(settings.primary_asn).strip()
_has_asn = bool(_primary_asn)
_default_site_name = f"AS{_primary_asn} bgpeek" if _has_asn else "bgpeek"
_brand_site_name = settings.brand_site_name.strip() or _default_site_name
_peeringdb_url = f"https://www.peeringdb.com/asn/{_primary_asn}" if _has_asn else ""

templates.env.filters["timeago"] = timeago
templates.env.filters["annotate_community"] = annotate_community
templates.env.globals["community_row_color"] = community_row_color
templates.env.globals["header_links_for"] = header_links_for
templates.env.globals["brand"] = {
    "site_name": _brand_site_name,
    "page_titles": settings.brand_page_titles,
    "logo_path": settings.brand_logo_path,
    "favicon_path": settings.brand_favicon_path,
    "theme_storage_key": settings.brand_theme_storage_key,
    "footer": _brand_footer,
    "primary_asn": _primary_asn,
    "peeringdb_link_enabled": settings.peeringdb_link_enabled and _has_asn,
    "peeringdb_url": _peeringdb_url,
    "custom_css": settings.brand_custom_css.strip(),
}
