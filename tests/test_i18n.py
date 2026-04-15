"""Tests for the i18n module and language detection."""

from __future__ import annotations

from bgpeek.core.i18n import (
    DEFAULT_LANG,
    SUPPORTED_LANGS,
    TRANSLATIONS,
    detect_language,
    get_translations,
)


class TestGetTranslations:
    def test_returns_english(self) -> None:
        t = get_translations("en")
        assert t["network_query"] == "Network Query"

    def test_fallback_to_english_for_unknown(self) -> None:
        t = get_translations("xx")
        assert t is TRANSLATIONS["en"]

    def test_no_empty_values(self) -> None:
        for lang_code in SUPPORTED_LANGS:
            for key, value in TRANSLATIONS[lang_code].items():
                assert value, f"Empty value for {lang_code}.{key}"


class TestDetectLanguage:
    def test_query_param_wins(self) -> None:
        assert detect_language("en", None, None, "en") == "en"

    def test_default_used_when_nothing_matches(self) -> None:
        assert detect_language(None, None, None, "en") == "en"

    def test_invalid_query_param_ignored(self) -> None:
        assert detect_language("xx", None, None, "en") == "en"

    def test_invalid_cookie_ignored(self) -> None:
        assert detect_language(None, "zz", None, "en") == "en"

    def test_accept_language_ignores_unsupported(self) -> None:
        assert detect_language(None, None, "fr-FR,de;q=0.9", "en") == "en"

    def test_accept_language_partial_match(self) -> None:
        assert detect_language(None, None, "en-US,en;q=0.9", "en") == "en"

    def test_invalid_default_falls_back(self) -> None:
        assert detect_language(None, None, None, "xx") == DEFAULT_LANG


class TestI18nMiddleware:
    """Test that the middleware sets language on actual HTTP requests."""

    def test_index_defaults_to_english(self) -> None:
        from fastapi.testclient import TestClient

        from bgpeek.main import app

        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Network Query" in resp.text

    def test_html_lang_attribute(self) -> None:
        from fastapi.testclient import TestClient

        from bgpeek.main import app

        client = TestClient(app)
        resp_en = client.get("/")
        assert 'lang="en"' in resp_en.text

    def test_login_page_renders(self) -> None:
        from fastapi.testclient import TestClient

        from bgpeek.main import app

        client = TestClient(app)
        resp = client.get("/auth/login")
        assert resp.status_code == 200
        assert "Username" in resp.text
        assert "Password" in resp.text
