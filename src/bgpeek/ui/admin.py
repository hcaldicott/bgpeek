"""Admin panel SSR routes (admin role only)."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address

import asyncpg
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

from bgpeek import __version__
from bgpeek.core.auth import require_role
from bgpeek.core.cache import invalidate_device
from bgpeek.core.commands import supported_platforms
from bgpeek.core.templates import templates
from bgpeek.db import credentials as credential_crud
from bgpeek.db import devices as device_crud
from bgpeek.db import users as user_crud
from bgpeek.db import webhooks as webhook_crud
from bgpeek.db.pool import get_pool
from bgpeek.models.device import DeviceCreate, DeviceUpdate
from bgpeek.models.user import User, UserRole

router = APIRouter(prefix="/admin", tags=["admin-ui"])

_admin = require_role(UserRole.ADMIN)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    user: User = Depends(_admin),  # noqa: B008
) -> Response:
    """Admin dashboard — aggregate counts."""
    pool = get_pool()
    devices = await device_crud.list_devices(pool)
    users = await user_crud.list_users(pool)
    credentials = await credential_crud.list_credentials(pool)
    webhooks = await webhook_crud.list_webhooks(pool)
    stats = {
        "devices": len(devices),
        "users": len(users),
        "credentials": len(credentials),
        "webhooks": len(webhooks),
    }
    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={
            "version": __version__,
            "user": user,
            "stats": stats,
            "t": request.state.t,
            "lang": request.state.lang,
        },
    )


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------


def _parse_optional_ip(raw: str | None, version: int) -> IPv4Address | IPv6Address | None:
    """Return ip_address(raw) of the expected version, or None for blank input."""
    if raw is None or raw.strip() == "":
        return None
    addr = ip_address(raw.strip())
    if version == 4 and not isinstance(addr, IPv4Address):
        raise ValueError("expected an IPv4 address")
    if version == 6 and not isinstance(addr, IPv6Address):
        raise ValueError("expected an IPv6 address")
    return addr


def _parse_int_or_none(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


async def _render_device_form(
    request: Request,
    *,
    title: str,
    form_action: str,
    form: dict[str, object],
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    pool = get_pool()
    creds = await credential_crud.list_credentials(pool)
    return templates.TemplateResponse(
        request=request,
        name="admin/devices_form.html",
        context={
            "version": __version__,
            "t": request.state.t,
            "lang": request.state.lang,
            "title": title,
            "form_action": form_action,
            "form": form,
            "error": error,
            "platforms": supported_platforms(),
            "credentials": creds,
        },
        status_code=status_code,
    )


@router.get("/devices", response_class=HTMLResponse)
async def devices_list(
    request: Request,
    _user: User = Depends(_admin),  # noqa: B008
) -> Response:
    pool = get_pool()
    devices = await device_crud.list_devices(pool)
    creds = await credential_crud.list_credentials(pool)
    credential_names = {c.id: c.name for c in creds}
    return templates.TemplateResponse(
        request=request,
        name="admin/devices_list.html",
        context={
            "version": __version__,
            "t": request.state.t,
            "lang": request.state.lang,
            "devices": devices,
            "credential_names": credential_names,
        },
    )


@router.get("/devices/new", response_class=HTMLResponse)
async def devices_new(
    request: Request,
    _user: User = Depends(_admin),  # noqa: B008
) -> Response:
    form: dict[str, object] = {"port": 22, "enabled": True, "restricted": False}
    return await _render_device_form(
        request,
        title=request.state.t["admin_devices_new"],
        form_action="/admin/devices",
        form=form,
    )


@router.post("/devices")
async def devices_create(
    request: Request,
    _user: User = Depends(_admin),  # noqa: B008
    name: str = Form(...),
    address: str = Form(...),
    platform: str = Form(...),
    port: int = Form(22),
    credential_id: str | None = Form(None),
    description: str | None = Form(None),
    location: str | None = Form(None),
    region: str | None = Form(None),
    source4: str | None = Form(None),
    source6: str | None = Form(None),
    enabled: str | None = Form(None),
    restricted: str | None = Form(None),
) -> Response:
    raw = {
        "name": name,
        "address": address,
        "platform": platform,
        "port": port,
        "credential_id": credential_id,
        "description": description,
        "location": location,
        "region": region,
        "source4": source4,
        "source6": source6,
        "enabled": enabled == "1",
        "restricted": restricted == "1",
    }
    try:
        payload = DeviceCreate(
            name=name,
            address=ip_address(address.strip()),
            port=port,
            platform=platform,
            description=description or None,
            location=location or None,
            region=region or None,
            enabled=enabled == "1",
            restricted=restricted == "1",
            credential_id=_parse_int_or_none(credential_id),
            source4=_parse_optional_ip(source4, 4),  # type: ignore[arg-type]
            source6=_parse_optional_ip(source6, 6),  # type: ignore[arg-type]
        )
    except (ValidationError, ValueError) as exc:
        return await _render_device_form(
            request,
            title=request.state.t["admin_devices_new"],
            form_action="/admin/devices",
            form=raw,
            error=str(exc),
            status_code=400,
        )

    try:
        await device_crud.create_device(get_pool(), payload)
    except asyncpg.UniqueViolationError:
        return await _render_device_form(
            request,
            title=request.state.t["admin_devices_new"],
            form_action="/admin/devices",
            form=raw,
            error=f"device with name {name!r} already exists",
            status_code=409,
        )
    return RedirectResponse("/admin/devices", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/devices/{device_id}/edit", response_class=HTMLResponse)
async def devices_edit(
    device_id: int,
    request: Request,
    _user: User = Depends(_admin),  # noqa: B008
) -> Response:
    device = await device_crud.get_device_by_id(get_pool(), device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="device not found")
    form = device.model_dump()
    return await _render_device_form(
        request,
        title=request.state.t["admin_devices_edit"],
        form_action=f"/admin/devices/{device_id}",
        form=form,
    )


@router.post("/devices/{device_id}")
async def devices_update(
    device_id: int,
    request: Request,
    _user: User = Depends(_admin),  # noqa: B008
    name: str = Form(...),
    address: str = Form(...),
    platform: str = Form(...),
    port: int = Form(22),
    credential_id: str | None = Form(None),
    description: str | None = Form(None),
    location: str | None = Form(None),
    region: str | None = Form(None),
    source4: str | None = Form(None),
    source6: str | None = Form(None),
    enabled: str | None = Form(None),
    restricted: str | None = Form(None),
) -> Response:
    raw = {
        "name": name,
        "address": address,
        "platform": platform,
        "port": port,
        "credential_id": _parse_int_or_none(credential_id),
        "description": description,
        "location": location,
        "region": region,
        "source4": source4,
        "source6": source6,
        "enabled": enabled == "1",
        "restricted": restricted == "1",
    }
    try:
        payload = DeviceUpdate(
            name=name,
            address=ip_address(address.strip()),
            port=port,
            platform=platform,
            description=description or None,
            location=location or None,
            region=region or None,
            enabled=enabled == "1",
            restricted=restricted == "1",
            credential_id=_parse_int_or_none(credential_id),
            source4=_parse_optional_ip(source4, 4),  # type: ignore[arg-type]
            source6=_parse_optional_ip(source6, 6),  # type: ignore[arg-type]
        )
    except (ValidationError, ValueError) as exc:
        return await _render_device_form(
            request,
            title=request.state.t["admin_devices_edit"],
            form_action=f"/admin/devices/{device_id}",
            form=raw,
            error=str(exc),
            status_code=400,
        )

    try:
        device = await device_crud.update_device(get_pool(), device_id, payload)
    except asyncpg.UniqueViolationError:
        return await _render_device_form(
            request,
            title=request.state.t["admin_devices_edit"],
            form_action=f"/admin/devices/{device_id}",
            form=raw,
            error=f"device with name {name!r} already exists",
            status_code=409,
        )
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="device not found")
    await invalidate_device(device.name)
    return RedirectResponse("/admin/devices", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/devices/{device_id}/delete")
async def devices_delete(
    device_id: int,
    _user: User = Depends(_admin),  # noqa: B008
) -> Response:
    device = await device_crud.get_device_by_id(get_pool(), device_id)
    deleted = await device_crud.delete_device(get_pool(), device_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="device not found")
    if device is not None:
        await invalidate_device(device.name)
    return RedirectResponse("/admin/devices", status_code=status.HTTP_303_SEE_OTHER)
