"""OIDC authentication backend using Authlib."""

from __future__ import annotations

import json
from typing import Any

import structlog
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI

from bgpeek.config import settings
from bgpeek.models.user import UserRole

logger = structlog.get_logger(__name__)

oauth = OAuth()


def setup_oidc(app: FastAPI) -> None:
    """Register OIDC provider with the OAuth client.

    Must be called during app creation (not in lifespan) so the routes
    can reference the registered client.
    """
    if not settings.oidc_enabled:
        return

    discovery_url = settings.oidc_discovery_url
    if not discovery_url:
        base = settings.oidc_server_url.rstrip("/")
        discovery_url = f"{base}/.well-known/openid-configuration"

    oauth.register(
        name="oidc",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=discovery_url,
        client_kwargs={"scope": settings.oidc_scopes},
    )

    logger.info("oidc registered", discovery_url=discovery_url)

    # Attach SessionMiddleware — needed for OAuth state parameter.
    from starlette.middleware.sessions import SessionMiddleware  # noqa: PLC0415

    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)


def get_oidc_client() -> Any | None:
    """Return the registered OIDC client, or None if OIDC is disabled."""
    if not settings.oidc_enabled:
        return None
    return oauth.oidc


def _parse_role_mapping(raw: str) -> dict[str, UserRole]:
    """Parse the JSON role-mapping string into {provider_role: UserRole}."""
    if not raw.strip():
        return {}
    mapping: dict[str, str] = json.loads(raw)
    return {k: UserRole(v) for k, v in mapping.items()}


def _get_nested(data: dict[str, object], path: str) -> object:
    """Traverse a dotted path like ``realm_access.roles`` in a nested dict."""
    parts = path.split(".")
    current: object = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def extract_role_from_token(token: dict[str, object]) -> UserRole:
    """Parse role from OIDC ID token claims using the configured claim path and mapping."""
    role_mapping = _parse_role_mapping(settings.oidc_role_mapping)
    default_role = UserRole(settings.oidc_default_role)

    claim_value = _get_nested(token, settings.oidc_role_claim)

    if claim_value is None:
        return default_role

    # claim_value can be a list of roles or a single string
    roles = [str(r) for r in claim_value] if isinstance(claim_value, list) else [str(claim_value)]

    # Pick the highest-privilege role that matches
    priority = {UserRole.ADMIN: 0, UserRole.NOC: 1, UserRole.PUBLIC: 2}
    best = default_role
    for role_name in roles:
        mapped = role_mapping.get(role_name)
        if mapped is not None and priority.get(mapped, 99) < priority.get(best, 99):
            best = mapped

    return best
