"""Tests for the Flask API routes — all external calls mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from acf.mapping_loader import FieldMapping
from llm.client import LLMConfig, LLMError
from wordpress.auth import SiteConfig
from wordpress.client import WordPressAPIError


# --- Fixtures ---


@pytest.fixture
def mapping():
    """Minimal mapping for testing."""
    return FieldMapping({
        "flexible_content_key": "field_test",
        "layouts": {
            "BasicContent": {
                "layout_key": "layout_basic",
                "fields": {
                    "heading.text": "field_h_text",
                    "heading.level": "field_h_level",
                    "content": "field_content",
                },
            },
        },
    })


@pytest.fixture
def app(mapping, monkeypatch):
    """Create a test Flask app with mocked config."""
    monkeypatch.setenv("TRANSFORM_API_KEY", "test-api-key")
    test_config = {
        "TESTING": True,
        "FIELD_MAPPING_PATH": "test_mapping.json",
        "LLM_CONFIG": LLMConfig(api_key="test-key", model="gpt-4o"),
    }
    application = create_app(test_config)
    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def site_config():
    return SiteConfig(
        name="testsite",
        base_url="https://www.example.com/wp",
        username="api-user",
        application_password="test-pass",
        default_author_id=5,
        default_status="draft",
    )


# --- Health ---


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "auto-publishing-bro"


# --- Templates ---


class TestTemplates:
    @patch("api.routes.list_page_templates")
    def test_list_templates(self, mock_list, client):
        mock_list.return_value = [
            {"name": "pokies_category", "description": "Category page"}
        ]
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "pokies_category"


# --- Sites ---


class TestSites:
    @patch("api.routes.list_sites")
    def test_list_sites(self, mock_list, client):
        mock_list.return_value = ["sunvegascasino", "othersite"]
        resp = client.get("/api/sites")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sites"] == ["sunvegascasino", "othersite"]


# --- Preview ---


class TestPreview:
    def test_missing_json_body(self, client):
        resp = client.post("/api/preview", data="not json", content_type="text/plain")
        assert resp.status_code == 400
        assert "JSON" in resp.get_json()["error"]

    def test_missing_template_field(self, client):
        resp = client.post("/api/preview", json={"variables": {}})
        assert resp.status_code == 400
        assert "template" in resp.get_json()["error"]

    @patch("api.routes.load_page_template")
    def test_template_not_found(self, mock_load, client):
        mock_load.side_effect = FileNotFoundError("not found")
        resp = client.post("/api/preview", json={"template": "nonexistent"})
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"]

    @patch("api.routes.generate_page_content")
    @patch("api.routes.transform_to_acf")
    @patch("api.routes.validate_page_template")
    @patch("api.routes.render_page_template")
    @patch("api.routes._get_llm_client")
    @patch("api.routes._get_mapping")
    @patch("api.routes.load_page_template")
    def test_preview_success(
        self,
        mock_load_template,
        mock_get_mapping,
        mock_get_llm,
        mock_render,
        mock_validate,
        mock_transform,
        mock_generate,
        client,
        mapping,
    ):
        mock_load_template.return_value = {
            "name": "test",
            "sections": [{"layout": "BasicContent", "fields": {}}],
        }
        mock_get_mapping.return_value = mapping
        mock_get_llm.return_value = MagicMock()
        mock_validate.return_value = []
        mock_render.return_value = [
            {"acf_fc_layout": "BasicContent", "fields": {"content": "Hello"}},
        ]
        mock_generate.return_value = [
            {"acf_fc_layout": "BasicContent", "fields": {"content": "<p>Hello</p>"}},
        ]
        mock_transform.return_value = {
            "acf": {"page_sections": [{"acf_fc_layout": "BasicContent"}]},
        }

        resp = client.post("/api/preview", json={
            "template": "test",
            "variables": {"category_name": "Pokies"},
        })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["template"] == "test"
        assert data["variables"]["category_name"] == "Pokies"
        assert "sections" in data
        assert "acf_payload" in data
        assert "warnings" in data

    @patch("api.routes.validate_page_template")
    @patch("api.routes.render_page_template")
    @patch("api.routes._get_mapping")
    @patch("api.routes.load_page_template")
    def test_preview_render_error(
        self, mock_load, mock_mapping, mock_render, mock_validate, client, mapping
    ):
        mock_load.return_value = {"name": "test", "sections": []}
        mock_mapping.return_value = mapping
        mock_validate.return_value = []
        mock_render.side_effect = ValueError("Missing required variable: category_name")

        resp = client.post("/api/preview", json={"template": "test"})
        assert resp.status_code == 400
        assert "category_name" in resp.get_json()["error"]

    @patch("api.routes.generate_page_content")
    @patch("api.routes.validate_page_template")
    @patch("api.routes.render_page_template")
    @patch("api.routes._get_llm_client")
    @patch("api.routes._get_mapping")
    @patch("api.routes.load_page_template")
    def test_preview_llm_error(
        self,
        mock_load,
        mock_mapping,
        mock_get_llm,
        mock_render,
        mock_validate,
        mock_generate,
        client,
        mapping,
    ):
        mock_load.return_value = {"name": "test", "sections": []}
        mock_mapping.return_value = mapping
        mock_validate.return_value = []
        mock_get_llm.return_value = MagicMock()
        mock_render.return_value = [{"acf_fc_layout": "BasicContent", "fields": {}}]
        mock_generate.side_effect = LLMError("API timeout")

        resp = client.post("/api/preview", json={"template": "test"})
        assert resp.status_code == 502
        assert "LLM" in resp.get_json()["error"]

    @patch("api.routes._get_mapping")
    @patch("api.routes.load_page_template")
    def test_preview_mapping_error(self, mock_load, mock_mapping, client):
        mock_load.return_value = {"name": "test", "sections": []}
        mock_mapping.side_effect = Exception("File not found")

        resp = client.post("/api/preview", json={"template": "test"})
        assert resp.status_code == 500
        assert "mapping" in resp.get_json()["error"].lower()


# --- Publish ---


class TestPublish:
    def test_missing_json_body(self, client):
        resp = client.post("/api/publish", data="nope", content_type="text/plain")
        assert resp.status_code == 400

    def test_missing_required_fields(self, client):
        resp = client.post("/api/publish", json={"template": "test"})
        assert resp.status_code == 400
        assert "site" in resp.get_json()["error"]

    def test_missing_template(self, client):
        resp = client.post("/api/publish", json={"site": "testsite"})
        assert resp.status_code == 400
        assert "template" in resp.get_json()["error"]

    @patch("api.routes.load_site_config")
    def test_bad_site_config(self, mock_load_site, client):
        mock_load_site.side_effect = ValueError("Site 'bad' not found")
        resp = client.post("/api/publish", json={
            "site": "bad", "template": "test",
        })
        assert resp.status_code == 400
        assert "Site config" in resp.get_json()["error"]

    @patch("api.routes.load_page_template")
    @patch("api.routes.load_site_config")
    def test_template_not_found(self, mock_site, mock_template, client, site_config):
        mock_site.return_value = site_config
        mock_template.side_effect = FileNotFoundError("not found")

        resp = client.post("/api/publish", json={
            "site": "testsite", "template": "nonexistent",
        })
        assert resp.status_code == 404

    @patch("api.routes.WordPressClient")
    @patch("api.routes.generate_page_content")
    @patch("api.routes.transform_to_acf")
    @patch("api.routes.render_page_template")
    @patch("api.routes._get_llm_client")
    @patch("api.routes._get_mapping")
    @patch("api.routes.load_page_template")
    @patch("api.routes.load_site_config")
    def test_publish_success(
        self,
        mock_site,
        mock_load_template,
        mock_mapping,
        mock_get_llm,
        mock_render,
        mock_transform,
        mock_generate,
        mock_wp_class,
        client,
        site_config,
        mapping,
    ):
        mock_site.return_value = site_config
        mock_load_template.return_value = {
            "name": "test",
            "sections": [{"layout": "BasicContent", "fields": {}}],
        }
        mock_mapping.return_value = mapping
        mock_get_llm.return_value = MagicMock()
        mock_render.return_value = [
            {"acf_fc_layout": "BasicContent", "fields": {"content": "Hi"}},
        ]
        mock_generate.return_value = [
            {"acf_fc_layout": "BasicContent", "fields": {"content": "<p>Hi</p>"}},
        ]
        mock_transform.return_value = {
            "acf": {"page_sections": [{"acf_fc_layout": "BasicContent"}]},
        }

        mock_wp = MagicMock()
        mock_wp.create_post.return_value = {
            "id": 42, "link": "https://example.com/?p=42", "status": "draft",
        }
        mock_wp_class.return_value = mock_wp

        resp = client.post("/api/publish", json={
            "site": "testsite",
            "template": "test",
            "variables": {"category_name": "Pokies"},
        })

        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert data["post_id"] == 42
        assert data["link"] == "https://example.com/?p=42"
        assert data["site"] == "testsite"
        assert data["template"] == "test"

    @patch("api.routes.WordPressClient")
    @patch("api.routes.generate_page_content")
    @patch("api.routes.transform_to_acf")
    @patch("api.routes.render_page_template")
    @patch("api.routes._get_llm_client")
    @patch("api.routes._get_mapping")
    @patch("api.routes.load_page_template")
    @patch("api.routes.load_site_config")
    def test_publish_wp_error(
        self,
        mock_site,
        mock_load_template,
        mock_mapping,
        mock_get_llm,
        mock_render,
        mock_transform,
        mock_generate,
        mock_wp_class,
        client,
        site_config,
        mapping,
    ):
        mock_site.return_value = site_config
        mock_load_template.return_value = {"name": "test", "sections": []}
        mock_mapping.return_value = mapping
        mock_get_llm.return_value = MagicMock()
        mock_render.return_value = [
            {"acf_fc_layout": "BasicContent", "fields": {}},
        ]
        mock_generate.return_value = [
            {"acf_fc_layout": "BasicContent", "fields": {}},
        ]
        mock_transform.return_value = {"acf": {"page_sections": []}}

        mock_wp = MagicMock()
        mock_wp.create_post.side_effect = WordPressAPIError(
            message="Forbidden", status_code=403,
        )
        mock_wp_class.return_value = mock_wp

        resp = client.post("/api/publish", json={
            "site": "testsite", "template": "test",
        })
        assert resp.status_code == 502
        assert "WordPress" in resp.get_json()["error"]

    @patch("api.routes.WordPressClient")
    @patch("api.routes.generate_page_content")
    @patch("api.routes.transform_to_acf")
    @patch("api.routes.render_page_template")
    @patch("api.routes._get_llm_client")
    @patch("api.routes._get_mapping")
    @patch("api.routes.load_page_template")
    @patch("api.routes.load_site_config")
    def test_publish_with_title_and_slug(
        self,
        mock_site,
        mock_load_template,
        mock_mapping,
        mock_get_llm,
        mock_render,
        mock_transform,
        mock_generate,
        mock_wp_class,
        client,
        site_config,
        mapping,
    ):
        mock_site.return_value = site_config
        mock_load_template.return_value = {"name": "test", "sections": []}
        mock_mapping.return_value = mapping
        mock_get_llm.return_value = MagicMock()
        mock_render.return_value = []
        mock_generate.return_value = []
        mock_transform.return_value = {"acf": {"page_sections": []}}

        mock_wp = MagicMock()
        mock_wp.create_post.return_value = {"id": 1, "link": "", "status": "draft"}
        mock_wp_class.return_value = mock_wp

        resp = client.post("/api/publish", json={
            "site": "testsite",
            "template": "test",
            "title": "Custom Title",
            "slug": "custom-slug",
            "status": "publish",
        })

        assert resp.status_code == 201
        call_args = mock_wp.create_post.call_args
        post_data = call_args[0][0]
        assert post_data["title"] == "Custom Title"
        assert post_data["slug"] == "custom-slug"

    @patch("api.routes.generate_page_content")
    @patch("api.routes.render_page_template")
    @patch("api.routes._get_llm_client")
    @patch("api.routes._get_mapping")
    @patch("api.routes.load_page_template")
    @patch("api.routes.load_site_config")
    def test_publish_llm_error(
        self,
        mock_site,
        mock_load_template,
        mock_mapping,
        mock_get_llm,
        mock_render,
        mock_generate,
        client,
        site_config,
        mapping,
    ):
        mock_site.return_value = site_config
        mock_load_template.return_value = {"name": "test", "sections": []}
        mock_mapping.return_value = mapping
        mock_get_llm.return_value = MagicMock()
        mock_render.return_value = []
        mock_generate.side_effect = LLMError("Rate limited")

        resp = client.post("/api/publish", json={
            "site": "testsite", "template": "test",
        })
        assert resp.status_code == 502
        assert "LLM" in resp.get_json()["error"]


# --- Helpers ---


class TestSectionsToTransformInput:
    def test_flattens_fields(self):
        from api.routes import _sections_to_transform_input

        sections = [
            {
                "acf_fc_layout": "BasicContent",
                "fields": {"heading.text": "Hello", "content": "<p>World</p>"},
            },
        ]
        result = _sections_to_transform_input(sections)
        assert len(result) == 1
        assert result[0]["acf_fc_layout"] == "BasicContent"
        assert result[0]["heading.text"] == "Hello"
        assert result[0]["content"] == "<p>World</p>"
        assert "fields" not in result[0]

    def test_empty_sections(self):
        from api.routes import _sections_to_transform_input
        assert _sections_to_transform_input([]) == []

    def test_missing_fields_key(self):
        from api.routes import _sections_to_transform_input

        sections = [{"acf_fc_layout": "BasicContent"}]
        result = _sections_to_transform_input(sections)
        assert result[0] == {"acf_fc_layout": "BasicContent"}


# --- App factory ---


class TestCreateApp:
    def test_creates_app(self):
        app = create_app({"TESTING": True})
        assert app is not None

    def test_config_override(self):
        app = create_app({
            "TESTING": True,
            "FIELD_MAPPING_PATH": "custom/path.json",
        })
        assert app.config["FIELD_MAPPING_PATH"] == "custom/path.json"

    def test_blueprint_registered(self):
        app = create_app({"TESTING": True})
        # Check that /api/health is a registered route
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/api/health" in rules


class TestValidatePublishRequest:
    def test_valid(self):
        from api.routes import _validate_publish_request
        assert _validate_publish_request({"site": "s", "template": "t"}) == ""

    def test_missing_site(self):
        from api.routes import _validate_publish_request
        result = _validate_publish_request({"template": "t"})
        assert "site" in result

    def test_missing_template(self):
        from api.routes import _validate_publish_request
        result = _validate_publish_request({"site": "s"})
        assert "template" in result

    def test_missing_both(self):
        from api.routes import _validate_publish_request
        result = _validate_publish_request({})
        assert "site" in result
        assert "template" in result


# --- Transform ---


class TestTransform:
    """Tests for the POST /api/transform endpoint."""

    _HEADERS = {"X-API-Key": "test-api-key"}

    # --- Auth ---

    def test_missing_api_key_header(self, client):
        resp = client.post("/api/transform", json={"site": "s", "sections": []})
        assert resp.status_code == 401
        assert "X-API-Key" in resp.get_json()["error"]

    def test_invalid_api_key(self, client):
        resp = client.post(
            "/api/transform",
            json={"site": "s", "sections": []},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 403
        assert "Invalid" in resp.get_json()["error"]

    def test_server_missing_api_key_config(self, client, monkeypatch):
        monkeypatch.delenv("TRANSFORM_API_KEY", raising=False)
        resp = client.post(
            "/api/transform",
            json={"site": "s", "sections": []},
            headers=self._HEADERS,
        )
        assert resp.status_code == 500
        assert "API key not set" in resp.get_json()["error"]

    # --- Validation ---

    def test_missing_json_body(self, client):
        resp = client.post(
            "/api/transform",
            data="not json",
            content_type="text/plain",
            headers=self._HEADERS,
        )
        assert resp.status_code == 400
        assert "JSON" in resp.get_json()["error"]

    def test_missing_site_field(self, client):
        resp = client.post(
            "/api/transform",
            json={"sections": [{"layout": "BasicContent"}]},
            headers=self._HEADERS,
        )
        assert resp.status_code == 400
        assert "site" in resp.get_json()["error"]

    def test_missing_sections_field(self, client):
        resp = client.post(
            "/api/transform",
            json={"site": "sunvegascasino"},
            headers=self._HEADERS,
        )
        assert resp.status_code == 400
        assert "sections" in resp.get_json()["error"]

    def test_sections_not_a_list(self, client):
        resp = client.post(
            "/api/transform",
            json={"site": "sunvegascasino", "sections": "not-a-list"},
            headers=self._HEADERS,
        )
        assert resp.status_code == 400
        assert "list" in resp.get_json()["error"]

    # --- Success ---

    @patch("api.routes._get_mapping_for_site")
    def test_transform_success(self, mock_mapping, client, mapping):
        mock_mapping.return_value = mapping

        resp = client.post(
            "/api/transform",
            json={
                "site": "sunvegascasino",
                "template": "pokies_category",
                "variables": {
                    "category_name": "Single-Reel Pokies",
                    "category_slug": "single-reel-pokies",
                },
                "sections": [
                    {
                        "layout": "BasicContent",
                        "heading": "Single-Reel Pokies",
                        "heading_level": "h1",
                        "content": "<p>Pre-generated HTML</p>",
                    },
                ],
                "status": "draft",
            },
            headers=self._HEADERS,
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["payload"]["title"] == "Single-Reel Pokies"
        assert data["payload"]["slug"] == "single-reel-pokies"
        assert data["payload"]["status"] == "draft"
        assert "page_sections" in data["payload"]["acf"]
        assert isinstance(data["warnings"], list)

    @patch("api.routes._get_mapping_for_site")
    def test_transform_heading_normalized(self, mock_mapping, client, mapping):
        """Verify flat heading/heading_level become nested heading dict."""
        mock_mapping.return_value = mapping

        resp = client.post(
            "/api/transform",
            json={
                "site": "sunvegascasino",
                "sections": [
                    {
                        "layout": "BasicContent",
                        "heading": "Test Title",
                        "heading_level": "h1",
                        "content": "<p>Content</p>",
                    },
                ],
            },
            headers=self._HEADERS,
        )

        data = resp.get_json()
        section = data["payload"]["acf"]["page_sections"][0]
        assert section["heading"]["text"] == "Test Title"
        assert section["heading"]["level"] == "h1"
        assert section["heading"]["alignment"]["desktop"] == "inherit"

    @patch("api.routes._get_mapping_for_site")
    def test_transform_empty_sections(self, mock_mapping, client, mapping):
        """Empty sections list should be accepted."""
        mock_mapping.return_value = mapping

        resp = client.post(
            "/api/transform",
            json={"site": "sunvegascasino", "sections": []},
            headers=self._HEADERS,
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["payload"]["acf"]["page_sections"] == []

    # --- Errors ---

    @patch("api.routes._get_mapping_for_site")
    def test_transform_mapping_error(self, mock_mapping, client):
        mock_mapping.side_effect = Exception("File not found")

        resp = client.post(
            "/api/transform",
            json={"site": "badsite", "sections": [{"layout": "BasicContent"}]},
            headers=self._HEADERS,
        )

        assert resp.status_code == 500
        assert "mapping" in resp.get_json()["error"].lower()


# --- Normalize AirOps Sections ---


class TestNormalizeAiropsSections:
    def test_layout_renamed_to_acf_fc_layout(self):
        from api.routes import _normalize_airops_sections

        result = _normalize_airops_sections([{"layout": "BasicContent"}])
        assert result[0]["acf_fc_layout"] == "BasicContent"
        assert "layout" not in result[0]

    def test_heading_and_level_nested(self):
        from api.routes import _normalize_airops_sections

        result = _normalize_airops_sections([{
            "layout": "BasicContent",
            "heading": "My Title",
            "heading_level": "h1",
        }])
        assert result[0]["heading"] == {"text": "My Title", "level": "h1"}
        assert "heading_level" not in result[0]

    def test_heading_only_no_level(self):
        from api.routes import _normalize_airops_sections

        result = _normalize_airops_sections([{
            "layout": "BasicContent",
            "heading": "My Title",
        }])
        assert result[0]["heading"] == {"text": "My Title"}

    def test_heading_already_nested_passthrough(self):
        from api.routes import _normalize_airops_sections

        result = _normalize_airops_sections([{
            "layout": "BasicContent",
            "heading": {"text": "Already Nested", "level": "h2"},
        }])
        assert result[0]["heading"] == {"text": "Already Nested", "level": "h2"}

    def test_other_fields_pass_through(self):
        from api.routes import _normalize_airops_sections

        result = _normalize_airops_sections([{
            "layout": "GamblingOperators",
            "heading": "Casinos",
            "heading_level": "h2",
            "shortcode": "[cta_list]",
            "content_above": "<p>Intro</p>",
            "content_below": "",
        }])
        assert result[0]["shortcode"] == "[cta_list]"
        assert result[0]["content_above"] == "<p>Intro</p>"
        assert result[0]["content_below"] == ""

    def test_empty_sections(self):
        from api.routes import _normalize_airops_sections

        assert _normalize_airops_sections([]) == []


# --- Validate Transform Request ---


class TestValidateTransformRequest:
    def test_valid(self):
        from api.routes import _validate_transform_request

        assert _validate_transform_request({"site": "s", "sections": []}) == ""

    def test_missing_site(self):
        from api.routes import _validate_transform_request

        result = _validate_transform_request({"sections": []})
        assert "site" in result

    def test_missing_sections(self):
        from api.routes import _validate_transform_request

        result = _validate_transform_request({"site": "s"})
        assert "sections" in result

    def test_sections_not_list(self):
        from api.routes import _validate_transform_request

        result = _validate_transform_request({"site": "s", "sections": "bad"})
        assert "list" in result
