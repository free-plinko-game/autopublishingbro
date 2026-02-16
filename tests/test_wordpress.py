"""Tests for the WordPress client — all API calls mocked."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests

from wordpress.auth import SiteConfig, load_site_config, list_sites, save_site_config, delete_site_config
from wordpress.client import WordPressClient, WordPressAPIError


# --- Fixtures ---


@pytest.fixture
def site_config():
    return SiteConfig(
        name="testsite",
        base_url="https://www.example.com/wp",
        username="api-user",
        application_password="test pass word 1234",
        default_author_id=5,
        default_status="draft",
    )


@pytest.fixture
def client(site_config):
    return WordPressClient(site_config)


@pytest.fixture
def mock_response():
    """Factory for creating mock response objects."""
    def _make(status_code=200, json_data=None, ok=True, reason="OK"):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = status_code
        resp.ok = ok
        resp.reason = reason
        resp.text = json.dumps(json_data or {})
        resp.json.return_value = json_data or {}
        return resp
    return _make


# --- SiteConfig tests ---


class TestSiteConfig:
    def test_api_url(self, site_config):
        assert site_config.api_url == "https://www.example.com/wp/wp-json/wp/v2"

    def test_api_url_strips_trailing_slash(self):
        config = SiteConfig(
            name="test",
            base_url="https://example.com/wp/",
            username="u",
            application_password="p",
        )
        assert config.api_url == "https://example.com/wp/wp-json/wp/v2"

    def test_auth_tuple(self, site_config):
        assert site_config.auth_tuple == ("api-user", "test pass word 1234")

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("WP_BASE_URL", "https://test.com/wp")
        monkeypatch.setenv("WP_USERNAME", "admin")
        monkeypatch.setenv("WP_APP_PASSWORD", "secret pass")
        monkeypatch.setenv("WP_DEFAULT_AUTHOR_ID", "3")
        monkeypatch.setenv("WP_DEFAULT_STATUS", "publish")

        config = SiteConfig.from_env("mysite")
        assert config.name == "mysite"
        assert config.base_url == "https://test.com/wp"
        assert config.username == "admin"
        assert config.application_password == "secret pass"
        assert config.default_author_id == 3
        assert config.default_status == "publish"

    def test_from_env_missing_raises(self, monkeypatch):
        monkeypatch.delenv("WP_BASE_URL", raising=False)
        monkeypatch.delenv("WP_USERNAME", raising=False)
        monkeypatch.delenv("WP_APP_PASSWORD", raising=False)
        with pytest.raises(ValueError, match="Missing WordPress env vars"):
            SiteConfig.from_env()

    def test_default_status(self):
        config = SiteConfig(
            name="test",
            base_url="https://test.com",
            username="u",
            application_password="p",
        )
        assert config.default_status == "draft"


class TestLoadSiteConfig:
    def test_load_from_yaml(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text(
            """
sites:
  mysite:
    base_url: "https://mysite.com/wp"
    username: "editor"
    application_password: "abcd efgh ijkl mnop"
    default_author_id: 7
    default_status: "pending"
"""
        )
        config = load_site_config("mysite", config_path=config_file)
        assert config.name == "mysite"
        assert config.base_url == "https://mysite.com/wp"
        assert config.username == "editor"
        assert config.application_password == "abcd efgh ijkl mnop"
        assert config.default_author_id == 7

    def test_load_missing_site_falls_back_to_env(self, tmp_path, monkeypatch):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text("sites:\n  other: {base_url: x, username: y, application_password: z}\n")

        monkeypatch.setenv("WP_BASE_URL", "https://env.com")
        monkeypatch.setenv("WP_USERNAME", "envuser")
        monkeypatch.setenv("WP_APP_PASSWORD", "envpass")

        config = load_site_config("nonexistent", config_path=config_file)
        assert config.base_url == "https://env.com"

    def test_list_sites(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text(
            """
sites:
  alpha:
    base_url: "https://a.com"
    username: u
    application_password: p
  beta:
    base_url: "https://b.com"
    username: u
    application_password: p
"""
        )
        sites = list_sites(config_path=config_file)
        assert sites == ["alpha", "beta"]

    def test_list_sites_no_file(self, tmp_path):
        assert list_sites(config_path=tmp_path / "nope.yaml") == []


# --- WordPressClient tests ---


class TestClientEndpoints:
    def test_post_endpoint(self, client):
        assert client._endpoint("post").endswith("/posts")

    def test_page_endpoint(self, client):
        assert client._endpoint("page").endswith("/pages")

    def test_custom_post_type_endpoint(self, client):
        assert client._endpoint("casino_review").endswith("/casino_review")


class TestCreatePost:
    def test_creates_post(self, client, mock_response):
        resp = mock_response(json_data={"id": 42, "link": "https://example.com/?p=42"})

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            result = client.create_post(
                {"title": "Test Post", "acf": {"page_sections": []}},
            )

        assert result["id"] == 42
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert "/posts" in call_args[0][1]

        payload = call_args[1]["json"]
        assert payload["title"] == "Test Post"
        assert payload["status"] == "draft"  # default
        assert payload["author"] == 5  # default_author_id

    def test_creates_page(self, client, mock_response):
        resp = mock_response(json_data={"id": 99})

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            client.create_post({"title": "About Us"}, post_type="page")

        assert "/pages" in mock_req.call_args[0][1]

    def test_custom_status(self, client, mock_response):
        resp = mock_response(json_data={"id": 1})

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            client.create_post({"title": "Live Post"}, status="publish")

        assert mock_req.call_args[1]["json"]["status"] == "publish"

    def test_status_in_data_wins(self, client, mock_response):
        resp = mock_response(json_data={"id": 1})

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            client.create_post({"title": "X", "status": "pending"}, status="publish")

        assert mock_req.call_args[1]["json"]["status"] == "pending"


class TestUpdatePost:
    def test_updates_post(self, client, mock_response):
        resp = mock_response(json_data={"id": 42, "title": {"rendered": "Updated"}})

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            result = client.update_post(42, {"title": "Updated"})

        assert result["id"] == 42
        assert "/posts/42" in mock_req.call_args[0][1]
        assert mock_req.call_args[0][0] == "POST"  # WP uses POST for updates

    def test_updates_acf_fields(self, client, mock_response):
        acf_data = {"acf": {"page_sections": [{"acf_fc_layout": "BasicContent"}]}}
        resp = mock_response(json_data={"id": 10})

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            client.update_post(10, acf_data)

        payload = mock_req.call_args[1]["json"]
        assert "acf" in payload


class TestGetPost:
    def test_gets_post_with_acf(self, client, mock_response):
        post_data = {
            "id": 42,
            "title": {"rendered": "My Post"},
            "slug": "my-post",
            "status": "publish",
            "acf": {"page_sections": []},
        }
        resp = mock_response(json_data=post_data)

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            result = client.get_post(42)

        assert result["id"] == 42
        assert "acf" in result
        assert mock_req.call_args[0][0] == "GET"
        assert "acf" in mock_req.call_args[1]["params"]["_fields"]


class TestSearchPosts:
    def test_search(self, client, mock_response):
        resp = mock_response(json_data=[
            {"id": 1, "title": {"rendered": "Match 1"}},
            {"id": 2, "title": {"rendered": "Match 2"}},
        ])

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            results = client.search_posts("pokies")

        assert len(results) == 2
        assert mock_req.call_args[1]["params"]["search"] == "pokies"


class TestDeletePost:
    def test_trash(self, client, mock_response):
        resp = mock_response(json_data={"id": 42, "status": "trash"})

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            client.delete_post(42)

        assert mock_req.call_args[0][0] == "DELETE"
        assert mock_req.call_args[1]["params"]["force"] is False

    def test_force_delete(self, client, mock_response):
        resp = mock_response(json_data={"id": 42, "deleted": True})

        with patch.object(client._session, "request", return_value=resp) as mock_req:
            client.delete_post(42, force=True)

        assert mock_req.call_args[1]["params"]["force"] is True


class TestUploadMedia:
    def test_upload(self, client, mock_response, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        resp = mock_response(json_data={"id": 55, "source_url": "https://example.com/test.png"})

        with patch.object(client._session, "post", return_value=resp):
            with patch.object(client, "_request", return_value={"id": 55}) as mock_update:
                result = client.upload_media(img, alt_text="Test image")

        assert result["id"] == 55

    def test_upload_missing_file(self, client):
        with pytest.raises(FileNotFoundError):
            client.upload_media("/nonexistent/file.png")


class TestTestConnection:
    def test_success(self, client, mock_response):
        resp = mock_response(json_data={"id": 1, "name": "Content API"})

        with patch.object(client._session, "request", return_value=resp):
            result = client.test_connection()

        assert result["ok"] is True
        assert result["user"] == "Content API"

    def test_auth_failure(self, client, mock_response):
        resp = mock_response(
            status_code=401,
            ok=False,
            json_data={"code": "rest_not_logged_in", "message": "Not authenticated"},
            reason="Unauthorized",
        )

        with patch.object(client._session, "request", return_value=resp):
            result = client.test_connection()

        assert result["ok"] is False
        assert result["status_code"] == 401


class TestErrorHandling:
    def test_api_error_raised(self, client, mock_response):
        resp = mock_response(
            status_code=404,
            ok=False,
            json_data={"code": "rest_post_invalid_id", "message": "Invalid post ID."},
            reason="Not Found",
        )

        with patch.object(client._session, "request", return_value=resp):
            with pytest.raises(WordPressAPIError) as exc_info:
                client.get_post(99999)

        assert exc_info.value.status_code == 404
        assert "Invalid post ID" in str(exc_info.value)

    def test_api_error_with_non_json_response(self, client):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        resp.ok = False
        resp.reason = "Internal Server Error"
        resp.text = "Something broke"
        resp.json.side_effect = ValueError("No JSON")

        with patch.object(client._session, "request", return_value=resp):
            with pytest.raises(WordPressAPIError) as exc_info:
                client.get_post(1)

        assert exc_info.value.status_code == 500
        assert "Something broke" in str(exc_info.value)

    def test_api_error_attributes(self):
        err = WordPressAPIError(
            message="Test error",
            status_code=403,
            error_code="forbidden",
            response_body='{"detail": "nope"}',
        )
        assert err.status_code == 403
        assert err.error_code == "forbidden"
        assert err.response_body == '{"detail": "nope"}'


class TestSaveSiteConfig:
    def test_save_new_site(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text("sites:\n  existing: {base_url: x, username: y, application_password: z}\n")

        save_site_config("newsite", {
            "base_url": "https://new.com/wp",
            "username": "admin",
            "application_password": "pass word",
            "default_author_id": 3,
            "default_status": "publish",
        }, config_path=config_file)

        import yaml
        data = yaml.safe_load(config_file.read_text())
        assert "newsite" in data["sites"]
        assert data["sites"]["newsite"]["base_url"] == "https://new.com/wp"
        assert data["sites"]["newsite"]["default_author_id"] == 3

    def test_update_existing_site(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text("sites:\n  mysite: {base_url: old, username: u, application_password: p}\n")

        save_site_config("mysite", {
            "base_url": "https://updated.com",
            "username": "newuser",
            "application_password": "newpass",
        }, config_path=config_file)

        import yaml
        data = yaml.safe_load(config_file.read_text())
        assert data["sites"]["mysite"]["base_url"] == "https://updated.com"

    def test_creates_file_if_missing(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        save_site_config("fresh", {
            "base_url": "https://fresh.com",
            "username": "u",
            "application_password": "p",
        }, config_path=config_file)

        assert config_file.exists()
        import yaml
        data = yaml.safe_load(config_file.read_text())
        assert "fresh" in data["sites"]

    def test_missing_required_fields(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        with pytest.raises(ValueError, match="Missing required fields"):
            save_site_config("bad", {"base_url": "x"}, config_path=config_file)

    def test_preserves_other_sites(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text(
            "sites:\n  alpha: {base_url: a, username: u, application_password: p}\n"
            "  beta: {base_url: b, username: u, application_password: p}\n"
        )
        save_site_config("alpha", {
            "base_url": "https://updated.com",
            "username": "u",
            "application_password": "p",
        }, config_path=config_file)

        import yaml
        data = yaml.safe_load(config_file.read_text())
        assert "beta" in data["sites"]
        assert data["sites"]["beta"]["base_url"] == "b"


class TestDeleteSiteConfig:
    def test_delete_existing(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text("sites:\n  target: {base_url: x, username: y, application_password: z}\n")

        result = delete_site_config("target", config_path=config_file)
        assert result is True

        import yaml
        data = yaml.safe_load(config_file.read_text())
        assert "target" not in data.get("sites", {})

    def test_delete_nonexistent(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text("sites:\n  other: {base_url: x, username: y, application_password: z}\n")

        result = delete_site_config("nope", config_path=config_file)
        assert result is False

    def test_delete_no_file(self, tmp_path):
        result = delete_site_config("nope", config_path=tmp_path / "nope.yaml")
        assert result is False

    def test_preserves_other_sites(self, tmp_path):
        config_file = tmp_path / "wordpress_sites.yaml"
        config_file.write_text(
            "sites:\n  keep: {base_url: a, username: u, application_password: p}\n"
            "  remove: {base_url: b, username: u, application_password: p}\n"
        )
        delete_site_config("remove", config_path=config_file)

        import yaml
        data = yaml.safe_load(config_file.read_text())
        assert "keep" in data["sites"]
        assert "remove" not in data["sites"]
