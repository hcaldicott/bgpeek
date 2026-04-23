"""Tests for `SecurityHeadersMiddleware` — CSP, fingerprint strip, HSTS gate.

Uses a minimal local FastAPI app that mounts only the middleware, so the
assertions don't depend on the main app's DB pool (other test modules may
leave the shared `bgpeek.db.pool._pool` closed on teardown, and the real
index route queries it).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from bgpeek.main import SecurityHeadersMiddleware


def _minimal_app() -> FastAPI:
    """FastAPI with only the middleware under test and a cheap echo route."""
    app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/echo", response_class=PlainTextResponse)
    async def echo() -> str:
        return "ok"

    return app


class TestContentSecurityPolicy:
    def test_csp_present_on_plain_route(self) -> None:
        client = TestClient(_minimal_app())
        resp = client.get("/echo")
        csp = resp.headers.get("content-security-policy")
        assert csp is not None
        # Load-bearing directives — downstream alerts key on these names.
        for directive in (
            "default-src 'self'",
            "script-src 'self'",
            "frame-ancestors 'none'",
            "form-action 'self'",
        ):
            assert directive in csp, f"missing {directive!r} in {csp!r}"

    def test_csp_skipped_on_swagger_ui(self) -> None:
        """FastAPI's Swagger UI loads JS from a CDN. Our strict `script-src
        'self'` would break it, so `/api/docs` is deliberately exempt from CSP.
        The docs surface is already gated by `BGPEEK_DOCS_ENABLED`."""
        client = TestClient(_minimal_app())
        resp = client.get("/api/docs")
        assert resp.status_code == 200
        assert "content-security-policy" not in {k.lower() for k in resp.headers}

    def test_csp_present_on_openapi_json(self) -> None:
        """JSON responses are loaded by same-origin XHR and browsers ignore
        most CSP directives on non-HTML; keeping the header keeps the rule
        simple (exempt Swagger UI only)."""
        client = TestClient(_minimal_app())
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200
        assert resp.headers.get("content-security-policy") is not None


class TestServerFingerprintStripped:
    """`server: uvicorn` narrows the version range for CVE scanning; remove it."""

    @pytest.mark.parametrize("path", ["/echo", "/api/docs", "/api/openapi.json"])
    def test_server_header_absent(self, path: str) -> None:
        client = TestClient(_minimal_app())
        resp = client.get(path)
        assert "server" not in {k.lower() for k in resp.headers}


class TestBaselineSecurityHeaders:
    """Guard the existing security headers alongside the new CSP logic so a
    future middleware refactor doesn't drop them silently."""

    def test_x_frame_options(self) -> None:
        client = TestClient(_minimal_app())
        resp = client.get("/echo")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_x_content_type_options(self) -> None:
        client = TestClient(_minimal_app())
        resp = client.get("/echo")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_permissions_policy(self) -> None:
        client = TestClient(_minimal_app())
        resp = client.get("/echo")
        policy = resp.headers.get("permissions-policy", "")
        for directive in ("camera=()", "microphone=()", "geolocation=()"):
            assert directive in policy


class TestUvicornServerHeaderDisabled:
    """The `server: uvicorn` header is injected by uvicorn's HTTP protocol
    layer AFTER ASGI middleware runs, so stripping it in
    `SecurityHeadersMiddleware` alone is not enough in production (TestClient
    bypasses the protocol layer, so the middleware test passes but the real
    response still carries the header — reported 2026-04-23). The fix lives
    on the `uvicorn.run(..., server_header=False)` call. This contract test
    asserts that call site stays intact.
    """

    def test_run_passes_server_header_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock

        import bgpeek.main as main_mod

        fake_uvicorn = MagicMock()
        # uvicorn is imported inside `run()`, so inject via sys.modules.
        monkeypatch.setitem(__import__("sys").modules, "uvicorn", fake_uvicorn)
        main_mod.run()
        fake_uvicorn.run.assert_called_once()
        kwargs = fake_uvicorn.run.call_args.kwargs
        assert kwargs.get("server_header") is False, (
            f"server_header must be False in uvicorn.run(), got {kwargs.get('server_header')!r}"
        )


class TestNoInlineJavaScriptInTemplates:
    """CSP ``script-src 'self'`` blocks inline ``<script>`` blocks and inline
    event-handler attributes (``onclick=``, ``onsubmit=``, etc.). Both would
    silently no-op in the browser — the site renders but interactivity dies.

    This test scans the shipped Jinja templates so a future PR that adds back
    an inline handler trips CI instead of shipping to prod.
    """

    TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "src" / "bgpeek" / "templates"

    # <script> tags without a src= attribute
    _INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
    # on<event>= attribute on any tag
    _INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)

    def test_no_inline_script_tags(self) -> None:
        offenders = []
        for path in self.TEMPLATE_DIR.rglob("*.html"):
            content = path.read_text(encoding="utf-8")
            # Strip HTML and Jinja comments — they legitimately mention
            # "<script>" in prose documentation.
            content_wo_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
            content_wo_comments = re.sub(r"{#.*?#}", "", content_wo_comments, flags=re.DOTALL)
            if self._INLINE_SCRIPT.search(content_wo_comments):
                offenders.append(path.relative_to(self.TEMPLATE_DIR))
        assert not offenders, (
            f"inline <script> blocks found (CSP script-src 'self' blocks them): "
            f"{[str(p) for p in offenders]}. "
            "Move JS to src/bgpeek/static/js/ and reference via <script src='...'>."
        )

    def test_no_inline_event_handlers(self) -> None:
        offenders = []
        for path in self.TEMPLATE_DIR.rglob("*.html"):
            content = path.read_text(encoding="utf-8")
            for match in self._INLINE_HANDLER.finditer(content):
                # Exclude Jinja macros / other non-event-handler attributes that
                # happen to start with `on` (e.g. ``once=``, ``only=``). The
                # real offenders all look like `on<letters>=`.
                start = max(0, match.start() - 20)
                snippet = content[start : match.end() + 20]
                offenders.append(f"{path.relative_to(self.TEMPLATE_DIR)}: {snippet.strip()}")
        assert not offenders, (
            f"inline event handlers found (CSP blocks them — use data-action + "
            f"delegated listener in static/js/ui-handlers.js): {offenders}"
        )
