"""Smoke test: health endpoint and index page render."""

from fastapi.testclient import TestClient

from bgpeek import __version__
from bgpeek.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_index_renders() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "bgpeek" in response.text.lower()
    assert "htmx" in response.text.lower()
