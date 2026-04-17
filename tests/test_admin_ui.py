"""Tests for the admin panel UI (SSR routes)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from bgpeek.main import app
from bgpeek.models.user import User, UserRole

_NOW = datetime.now(tz=UTC)

_ADMIN = User(
    id=1,
    username="admin",
    email="admin@example.com",
    role=UserRole.ADMIN,
    auth_provider="api_key",
    api_key_hash="h",
    enabled=True,
    created_at=_NOW,
)

_NOC = User(
    id=2,
    username="noc",
    email=None,
    role=UserRole.NOC,
    auth_provider="api_key",
    api_key_hash="h2",
    enabled=True,
    created_at=_NOW,
)


def test_admin_index_no_auth_returns_401() -> None:
    client = TestClient(app)
    response = client.get("/admin")
    assert response.status_code == 401


def test_admin_index_noc_user_returns_403() -> None:
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_NOC),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
    ):
        client = TestClient(app)
        response = client.get("/admin", headers={"X-API-Key": "any"})
    assert response.status_code == 403


def test_admin_index_admin_renders_dashboard() -> None:
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch(
            "bgpeek.ui.admin.device_crud.list_devices",
            new=AsyncMock(return_value=[1, 2, 3]),
        ),
        patch(
            "bgpeek.ui.admin.user_crud.list_users",
            new=AsyncMock(return_value=[_ADMIN, _NOC]),
        ),
        patch(
            "bgpeek.ui.admin.credential_crud.list_credentials",
            new=AsyncMock(return_value=[1]),
        ),
        patch(
            "bgpeek.ui.admin.webhook_crud.list_webhooks",
            new=AsyncMock(return_value=[]),
        ),
        patch("bgpeek.ui.admin.get_pool", return_value=object()),
    ):
        client = TestClient(app)
        response = client.get("/admin", headers={"X-API-Key": "any"})

    assert response.status_code == 200
    body = response.text
    assert "Dashboard" in body
    # Stat counts rendered
    assert ">3<" in body  # devices
    assert ">2<" in body  # users
    assert ">1<" in body  # credentials
    assert ">0<" in body  # webhooks
    # Sidebar nav present
    assert "/admin/devices" in body
    assert "/admin/users" in body


def test_admin_link_shown_for_admin_in_main_navbar() -> None:
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.main.get_pool", return_value=object()),
        patch("bgpeek.main.device_crud.list_devices", new=AsyncMock(return_value=[])),
    ):
        client = TestClient(app)
        response = client.get("/", headers={"X-API-Key": "any"})

    assert response.status_code == 200
    assert 'href="/admin"' in response.text


def test_admin_link_hidden_for_noc_in_main_navbar() -> None:
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_NOC),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.main.get_pool", return_value=object()),
        patch("bgpeek.main.device_crud.list_devices", new=AsyncMock(return_value=[])),
    ):
        client = TestClient(app)
        response = client.get("/", headers={"X-API-Key": "any"})

    assert response.status_code == 200
    assert 'href="/admin"' not in response.text


# ---------------------------------------------------------------------------
# Admin devices CRUD
# ---------------------------------------------------------------------------


_DEVICE_ROW = {
    "id": 1,
    "name": "rt1",
    "address": "192.0.2.1",
    "port": 22,
    "platform": "juniper_junos",
    "description": "",
    "location": "SYD",
    "region": "AU",
    "enabled": True,
    "restricted": False,
    "credential_id": None,
    "source4": None,
    "source6": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}


def _admin_auth_patches() -> list:
    return [
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.ui.admin.get_pool", return_value=object()),
    ]


def test_devices_list_renders() -> None:
    from bgpeek.models.device import Device

    device = Device.model_validate(_DEVICE_ROW)
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.ui.admin.get_pool", return_value=object()),
        patch(
            "bgpeek.ui.admin.device_crud.list_devices",
            new=AsyncMock(return_value=[device]),
        ),
        patch(
            "bgpeek.ui.admin.credential_crud.list_credentials",
            new=AsyncMock(return_value=[]),
        ),
    ):
        client = TestClient(app)
        response = client.get("/admin/devices", headers={"X-API-Key": "any"})

    assert response.status_code == 200
    assert "rt1" in response.text
    assert "192.0.2.1" in response.text
    assert "juniper_junos" in response.text
    assert "/admin/devices/new" in response.text
    assert "/admin/devices/1/edit" in response.text


def test_devices_list_noc_returns_403() -> None:
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_NOC),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
    ):
        client = TestClient(app)
        response = client.get("/admin/devices", headers={"X-API-Key": "any"})

    assert response.status_code == 403


def test_devices_new_form_renders() -> None:
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.ui.admin.get_pool", return_value=object()),
        patch(
            "bgpeek.ui.admin.credential_crud.list_credentials",
            new=AsyncMock(return_value=[]),
        ),
    ):
        client = TestClient(app)
        response = client.get("/admin/devices/new", headers={"X-API-Key": "any"})

    assert response.status_code == 200
    assert 'name="name"' in response.text
    assert 'name="address"' in response.text
    assert 'name="platform"' in response.text
    # Platforms datalist populated from supported_platforms()
    assert "juniper_junos" in response.text


def test_devices_create_redirects_and_calls_crud() -> None:
    create_mock = AsyncMock()
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.ui.admin.get_pool", return_value=object()),
        patch("bgpeek.ui.admin.device_crud.create_device", new=create_mock),
    ):
        client = TestClient(app)
        response = client.post(
            "/admin/devices",
            headers={"X-API-Key": "any"},
            data={
                "name": "rt1",
                "address": "192.0.2.1",
                "platform": "juniper_junos",
                "port": "22",
                "enabled": "1",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/devices"
    create_mock.assert_awaited_once()
    payload = create_mock.await_args.args[1]
    assert payload.name == "rt1"
    assert str(payload.address) == "192.0.2.1"
    assert payload.enabled is True


def test_devices_create_invalid_address_rerenders_form() -> None:
    create_mock = AsyncMock()
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.ui.admin.get_pool", return_value=object()),
        patch(
            "bgpeek.ui.admin.credential_crud.list_credentials",
            new=AsyncMock(return_value=[]),
        ),
        patch("bgpeek.ui.admin.device_crud.create_device", new=create_mock),
    ):
        client = TestClient(app)
        response = client.post(
            "/admin/devices",
            headers={"X-API-Key": "any"},
            data={
                "name": "rt1",
                "address": "not-an-ip",
                "platform": "juniper_junos",
                "port": "22",
            },
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert 'name="name"' in response.text  # form re-rendered
    create_mock.assert_not_awaited()


def test_devices_edit_form_prefilled() -> None:
    from bgpeek.models.device import Device

    device = Device.model_validate(_DEVICE_ROW)
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.ui.admin.get_pool", return_value=object()),
        patch(
            "bgpeek.ui.admin.device_crud.get_device_by_id",
            new=AsyncMock(return_value=device),
        ),
        patch(
            "bgpeek.ui.admin.credential_crud.list_credentials",
            new=AsyncMock(return_value=[]),
        ),
    ):
        client = TestClient(app)
        response = client.get(
            "/admin/devices/1/edit",
            headers={"X-API-Key": "any"},
        )

    assert response.status_code == 200
    assert 'value="rt1"' in response.text
    assert 'value="192.0.2.1"' in response.text
    assert 'action="/admin/devices/1"' in response.text


def test_devices_delete_redirects_and_calls_crud() -> None:
    from bgpeek.models.device import Device

    device = Device.model_validate(_DEVICE_ROW)
    delete_mock = AsyncMock(return_value=True)
    with (
        patch(
            "bgpeek.core.auth.user_crud.get_user_by_api_key",
            new=AsyncMock(return_value=_ADMIN),
        ),
        patch("bgpeek.core.auth.get_pool", return_value=object()),
        patch("bgpeek.ui.admin.get_pool", return_value=object()),
        patch(
            "bgpeek.ui.admin.device_crud.get_device_by_id",
            new=AsyncMock(return_value=device),
        ),
        patch("bgpeek.ui.admin.device_crud.delete_device", new=delete_mock),
        patch("bgpeek.ui.admin.invalidate_device", new=AsyncMock()),
    ):
        client = TestClient(app)
        response = client.post(
            "/admin/devices/1/delete",
            headers={"X-API-Key": "any"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/devices"
    delete_mock.assert_awaited_once()
