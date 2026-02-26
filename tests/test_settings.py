"""Tests for the settings API endpoints."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from wordpress.auth import SiteConfig


# --- Fixtures ---


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("TRANSFORM_API_KEY", "test-api-key")
    return create_app({"TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def site_config():
    return SiteConfig(
        name="testsite",
        base_url="https://www.example.com/wp",
        username="api-user",
        application_password="abcd efgh ijkl mnop",
        default_author_id=5,
        default_status="draft",
    )


# --- Mask helper ---


class TestMask:
    def test_long_string(self):
        from api.settings import _mask
        assert _mask("abcdefghijkl") == "********ijkl"

    def test_short_string(self):
        from api.settings import _mask
        assert _mask("abc") == "***"

    def test_exact_visible_length(self):
        from api.settings import _mask
        assert _mask("abcd") == "****"

    def test_empty(self):
        from api.settings import _mask
        assert _mask("") == ""

    def test_custom_visible(self):
        from api.settings import _mask
        assert _mask("abcdefgh", visible=2) == "******gh"


# --- GET /api/settings ---


class TestGetSettings:
    _HEADERS = {"X-API-Key": "test-api-key"}

    @patch("api.settings.load_site_config")
    @patch("api.settings.list_sites")
    def test_returns_masked_data(self, mock_list, mock_load, client, site_config, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test1234567890abcdef")
        mock_list.return_value = ["testsite"]
        mock_load.return_value = site_config

        resp = client.get("/api/settings", headers=self._HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()

        assert "testsite" in data["sites"]
        site = data["sites"]["testsite"]
        assert site["base_url"] == "https://www.example.com/wp"
        assert "abcd" not in site["application_password"]  # masked
        assert site["application_password"].endswith("mnop")

        assert data["openai"]["api_key_set"] is True
        assert data["openai"]["api_key_masked"].endswith("cdef")

    @patch("api.settings.list_sites")
    def test_no_sites(self, mock_list, client, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        mock_list.return_value = []

        resp = client.get("/api/settings", headers=self._HEADERS)
        data = resp.get_json()
        assert data["sites"] == {}
        assert data["openai"]["api_key_set"] is False

    @patch("api.settings.load_site_config")
    @patch("api.settings.list_sites")
    def test_skips_broken_sites(self, mock_list, mock_load, client):
        mock_list.return_value = ["good", "broken"]
        mock_load.side_effect = [
            SiteConfig(name="good", base_url="x", username="u", application_password="pass1234"),
            ValueError("bad config"),
        ]
        resp = client.get("/api/settings", headers=self._HEADERS)
        data = resp.get_json()
        assert "good" in data["sites"]
        assert "broken" not in data["sites"]


# --- POST /api/settings/sites ---


class TestUpsertSite:
    _HEADERS = {"X-API-Key": "test-api-key"}

    @patch("api.settings.save_site_config")
    def test_add_site(self, mock_save, client):
        resp = client.post("/api/settings/sites", json={
            "name": "newsite",
            "base_url": "https://new.com/wp",
            "username": "admin",
            "application_password": "pass word",
        }, headers=self._HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        mock_save.assert_called_once()

    def test_missing_body(self, client):
        resp = client.post("/api/settings/sites", data="nope", content_type="text/plain", headers=self._HEADERS)
        assert resp.status_code == 400

    def test_missing_name(self, client):
        resp = client.post("/api/settings/sites", json={
            "base_url": "x", "username": "u", "application_password": "p",
        }, headers=self._HEADERS)
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"]

    @patch("api.settings.save_site_config")
    def test_missing_required_fields(self, mock_save, client):
        mock_save.side_effect = ValueError("Missing required fields: application_password")
        resp = client.post("/api/settings/sites", json={
            "name": "bad", "base_url": "x",
        }, headers=self._HEADERS)
        assert resp.status_code == 400


# --- DELETE /api/settings/sites/<name> ---


class TestDeleteSite:
    _HEADERS = {"X-API-Key": "test-api-key"}

    @patch("api.settings.delete_site_config")
    def test_delete_existing(self, mock_delete, client):
        mock_delete.return_value = True
        resp = client.delete("/api/settings/sites/mysite", headers=self._HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    @patch("api.settings.delete_site_config")
    def test_delete_missing(self, mock_delete, client):
        mock_delete.return_value = False
        resp = client.delete("/api/settings/sites/nope", headers=self._HEADERS)
        assert resp.status_code == 404


# --- POST /api/settings/sites/<name>/test ---


class TestTestSite:
    _HEADERS = {"X-API-Key": "test-api-key"}

    @patch("api.settings.WordPressClient")
    @patch("api.settings.load_site_config")
    def test_success(self, mock_load, mock_wp_class, client, site_config):
        mock_load.return_value = site_config
        mock_wp = MagicMock()
        mock_wp.test_connection.return_value = {"ok": True, "user": "Admin", "user_id": 1}
        mock_wp_class.return_value = mock_wp

        resp = client.post("/api/settings/sites/testsite/test", headers=self._HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    @patch("api.settings.WordPressClient")
    @patch("api.settings.load_site_config")
    def test_failure(self, mock_load, mock_wp_class, client, site_config):
        mock_load.return_value = site_config
        mock_wp = MagicMock()
        mock_wp.test_connection.return_value = {"ok": False, "error": "Unauthorized", "status_code": 401}
        mock_wp_class.return_value = mock_wp

        resp = client.post("/api/settings/sites/testsite/test", headers=self._HEADERS)
        assert resp.status_code == 502
        assert resp.get_json()["ok"] is False

    @patch("api.settings.load_site_config")
    def test_bad_site(self, mock_load, client):
        mock_load.side_effect = ValueError("Site not found")
        resp = client.post("/api/settings/sites/bad/test", headers=self._HEADERS)
        assert resp.status_code == 400


# --- POST /api/settings/openai ---


class TestUpdateOpenAIKey:
    _HEADERS = {"X-API-Key": "test-api-key"}

    @patch("api.settings.set_key")
    def test_update_key(self, mock_set_key, client, monkeypatch):
        resp = client.post("/api/settings/openai", json={"api_key": "sk-newkey12345678"}, headers=self._HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["api_key_masked"].endswith("5678")
        mock_set_key.assert_called_once()

    def test_missing_body(self, client):
        resp = client.post("/api/settings/openai", data="nope", content_type="text/plain", headers=self._HEADERS)
        assert resp.status_code == 400

    def test_missing_key(self, client):
        resp = client.post("/api/settings/openai", json={}, headers=self._HEADERS)
        assert resp.status_code == 400
        assert "api_key" in resp.get_json()["error"]


# --- Blueprint registration ---


class TestSettingsBlueprint:
    def test_routes_registered(self):
        app = create_app({"TESTING": True})
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/api/settings" in rules
        assert "/api/settings/sites" in rules
        assert "/api/settings/openai" in rules
