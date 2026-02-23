"""Flask API routes — ties all components together."""

from __future__ import annotations

import functools
import hmac
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

from acf.mapping_loader import load_mapping, FieldMapping
from acf.transformer import transform_to_acf, validate_sections
from llm.client import LLMClient, LLMConfig, LLMError
from llm.generator import generate_page_content
from templates.loader import load_page_template, list_page_templates
from templates.renderer import render_page_template
from templates.validator import validate_page_template
from wordpress.auth import load_site_config, list_sites, SiteConfig
from wordpress.client import WordPressClient, WordPressAPIError

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Default mapping path — can be overridden via app config
_DEFAULT_MAPPING = "config/field_mappings/sunvegascasino.json"


def require_api_key(f):
    """Decorator that checks X-API-Key header against TRANSFORM_API_KEY env var."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        api_key = os.environ.get("TRANSFORM_API_KEY")
        if not api_key:
            logger.error("TRANSFORM_API_KEY not configured")
            return jsonify({"error": "Server misconfiguration: API key not set"}), 500

        provided = request.headers.get("X-API-Key", "")
        if not provided:
            return jsonify({"error": "Missing X-API-Key header"}), 401

        if not hmac.compare_digest(provided, api_key):
            return jsonify({"error": "Invalid API key"}), 403

        return f(*args, **kwargs)
    return decorated


def _get_mapping() -> FieldMapping:
    """Load the field mapping, using app config override if available."""
    from flask import current_app
    path = current_app.config.get("FIELD_MAPPING_PATH", _DEFAULT_MAPPING)
    return load_mapping(path)


def _get_llm_client() -> LLMClient:
    """Create an LLM client from app config or env vars."""
    from flask import current_app
    config_overrides = current_app.config.get("LLM_CONFIG")
    if config_overrides and isinstance(config_overrides, LLMConfig):
        return LLMClient(config_overrides)
    return LLMClient()


# --- Health ---


@api_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "auto-publishing-bro"})


# --- Templates ---


@api_bp.route("/templates", methods=["GET"])
def get_templates():
    """List all available page templates."""
    templates = list_page_templates()
    return jsonify(templates)


# --- Sites ---


@api_bp.route("/sites", methods=["GET"])
def get_sites():
    """List all configured WordPress sites."""
    sites = list_sites()
    return jsonify({"sites": sites})


# --- Preview ---

@api_bp.route("/preview", methods=["POST"])
@require_api_key
def preview():
    """Generate content from a template WITHOUT publishing.

    Request body:
    {
        "template": "pokies_category",
        "variables": {"category_name": "...", ...},
        "site": "sunvegascasino"  (optional, for validation only)
    }

    Returns the generated sections and the ACF payload that would be sent.
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required fields
    template_name = body.get("template")
    if not template_name:
        return jsonify({"error": "Missing 'template' field"}), 400

    variables = body.get("variables", {})

    # Load and render template
    try:
        template = load_page_template(template_name)
    except FileNotFoundError:
        return jsonify({"error": f"Template '{template_name}' not found"}), 404

    # Validate template against mapping
    try:
        mapping = _get_mapping()
        template_warnings = validate_page_template(template, mapping)
    except Exception as e:
        return jsonify({"error": f"Failed to load field mapping: {e}"}), 500

    try:
        rendered = render_page_template(template, variables)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Generate LLM content
    try:
        llm_client = _get_llm_client()
        completed = generate_page_content(rendered, llm_client, variables)
    except LLMError as e:
        return jsonify({"error": f"LLM generation failed: {e}"}), 502
    except ValueError as e:
        return jsonify({"error": f"LLM config error: {e}"}), 500

    # Build ACF payload
    sections_for_transform = _sections_to_transform_input(completed)
    acf_payload = transform_to_acf(sections_for_transform, mapping)

    # Build response
    response = {
        "template": template_name,
        "variables": variables,
        "sections": completed,
        "acf_payload": acf_payload,
        "warnings": template_warnings,
    }

    return jsonify(response)


# --- Publish ---

@api_bp.route("/publish", methods=["POST"])
@require_api_key
def publish():
    """Generate content and publish to WordPress.

    Request body:
    {
        "site": "sunvegascasino",
        "template": "pokies_category",
        "variables": {"category_name": "...", ...},
        "post_type": "post",
        "status": "draft",
        "title": "Optional override title",
        "slug": "optional-override-slug"
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required fields
    errors = _validate_publish_request(body)
    if errors:
        return jsonify({"error": errors}), 400

    site_name = body["site"]
    template_name = body["template"]
    variables = body.get("variables", {})
    post_type = body.get("post_type", "post")
    status = body.get("status", None)

    # Load site config
    try:
        site_config = load_site_config(site_name)
    except ValueError as e:
        return jsonify({"error": f"Site config error: {e}"}), 400

    # Load and render template
    try:
        template = load_page_template(template_name)
    except FileNotFoundError:
        return jsonify({"error": f"Template '{template_name}' not found"}), 404

    try:
        mapping = _get_mapping()
    except Exception as e:
        return jsonify({"error": f"Failed to load field mapping: {e}"}), 500

    try:
        rendered = render_page_template(template, variables)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Generate content
    try:
        llm_client = _get_llm_client()
        completed = generate_page_content(rendered, llm_client, variables)
    except LLMError as e:
        return jsonify({"error": f"LLM generation failed: {e}"}), 502
    except ValueError as e:
        return jsonify({"error": f"LLM config error: {e}"}), 500

    # Transform to ACF format
    sections_for_transform = _sections_to_transform_input(completed)
    acf_payload = transform_to_acf(sections_for_transform, mapping)

    # Build WordPress post data
    post_data: dict[str, Any] = {
        "acf": acf_payload["acf"],
    }

    # Title: explicit override > first heading > template name
    if body.get("title"):
        post_data["title"] = body["title"]
    elif variables.get("category_name"):
        post_data["title"] = variables["category_name"]

    # Slug
    slug = body.get("slug")
    if not slug and "slug_pattern" in template:
        slug = template["slug_pattern"].format(**variables)
    if slug:
        post_data["slug"] = slug

    # Yoast SEO meta fields
    meta_title = body.get("meta_title")
    meta_description = body.get("meta_description")
    if meta_title:
        post_data["yoast_wpseo_title"] = meta_title
    if meta_description:
        post_data["yoast_wpseo_metadesc"] = meta_description

    # Publish to WordPress
    try:
        wp_client = WordPressClient(site_config)
        result = wp_client.create_post(post_data, post_type=post_type, status=status)
    except WordPressAPIError as e:
        return jsonify({
            "error": f"WordPress API error: {e}",
            "status_code": e.status_code,
        }), 502

    return jsonify({
        "success": True,
        "post_id": result.get("id"),
        "link": result.get("link", ""),
        "status": result.get("status", ""),
        "site": site_name,
        "template": template_name,
    }), 201


# --- Transform (AirOps hybrid) ---


@api_bp.route("/transform", methods=["POST"])
@require_api_key
def transform():
    """Transform pre-generated content sections to WordPress ACF format.

    Receives content already generated by AirOps/LLM and converts it
    to the nested ACF REST API structure using field mappings.
    Does NOT publish — returns the payload for AirOps to send to WordPress.

    Request body:
    {
        "site": "sunvegascasino",
        "template": "pokies_category",
        "variables": {"category_name": "...", "category_slug": "...", ...},
        "sections": [
            {"layout": "BasicContent", "heading": "Title", "heading_level": "h1", "content": "<p>...</p>"},
            ...
        ],
        "status": "draft"
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON"}), 400

    errors = _validate_transform_request(body)
    if errors:
        return jsonify({"error": errors}), 400

    site_name = body["site"]
    variables = body.get("variables", {})
    raw_sections = body.get("sections", [])
    status = body.get("status", "draft")

    # Load site-specific mapping
    try:
        mapping = _get_mapping_for_site(site_name)
    except Exception as e:
        return jsonify({"error": f"Failed to load field mapping: {e}"}), 500

    # Normalize AirOps flat format -> transformer nested format
    normalized_sections = _normalize_airops_sections(raw_sections)
    logger.debug(
        "Normalized %d sections for site %s: %s",
        len(normalized_sections),
        site_name,
        json.dumps(normalized_sections, default=str)[:2000],
    )

    # Validate sections against mapping
    warnings = validate_sections(normalized_sections, mapping)

    # Transform to ACF format
    acf_payload = transform_to_acf(normalized_sections, mapping)

    # Build WordPress-ready payload
    payload: dict[str, Any] = {
        "status": status,
        "acf": acf_payload["acf"],
    }

    # Title: from variables or first section heading
    if variables.get("category_name"):
        payload["title"] = variables["category_name"]
    elif raw_sections and raw_sections[0].get("heading"):
        payload["title"] = raw_sections[0]["heading"]

    # Slug: from variables
    if variables.get("category_slug"):
        payload["slug"] = variables["category_slug"]

    # Yoast SEO meta fields (pass through to WordPress payload)
    meta_title = body.get("meta_title")
    meta_description = body.get("meta_description")
    if meta_title:
        payload["yoast_wpseo_title"] = meta_title
    if meta_description:
        payload["yoast_wpseo_metadesc"] = meta_description

    return jsonify({
        "success": True,
        "payload": payload,
        "warnings": warnings,
    })


# --- Helpers ---


def _validate_publish_request(body: dict) -> str:
    """Validate the publish request body, return error string or empty."""
    missing = []
    if not body.get("site"):
        missing.append("site")
    if not body.get("template"):
        missing.append("template")
    if missing:
        return f"Missing required fields: {', '.join(missing)}"
    return ""


def _sections_to_transform_input(
    completed_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert generator output to transformer input format.

    The generator returns {acf_fc_layout, fields: {...}}.
    The transformer expects {acf_fc_layout, field1, field2, ...} (flat).
    """
    result = []
    for section in completed_sections:
        flat = {"acf_fc_layout": section["acf_fc_layout"]}
        flat.update(section.get("fields", {}))
        result.append(flat)
    return result


def _get_mapping_for_site(site_name: str) -> FieldMapping:
    """Load the field mapping for a specific site.

    Looks for config/field_mappings/{site_name}.json first.
    Falls back to the default mapping path from app config.
    """
    if not re.match(r"^[a-zA-Z0-9_-]+$", site_name):
        raise ValueError("Invalid site name")

    from flask import current_app
    site_path = Path(f"config/field_mappings/{site_name}.json")
    if site_path.exists():
        return load_mapping(str(site_path))
    path = current_app.config.get("FIELD_MAPPING_PATH", _DEFAULT_MAPPING)
    return load_mapping(path)


def _normalize_airops_sections(
    raw_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert AirOps flat section format to the nested format
    expected by transform_to_acf().

    AirOps sends:  {"layout": "X", "heading": "text", "heading_level": "h2", ...}
    Transformer expects: {"acf_fc_layout": "X", "heading": {"text": "text", "level": "h2"}, ...}
    """
    _HANDLED_KEYS = {"layout", "heading", "heading_level"}
    normalized = []

    for section in raw_sections:
        result: dict[str, Any] = {
            "acf_fc_layout": section.get("layout", ""),
        }

        heading_text = section.get("heading")
        heading_level = section.get("heading_level")

        if isinstance(heading_text, dict):
            # Already nested — pass through unchanged
            result["heading"] = heading_text
        elif heading_text is not None or heading_level is not None:
            result["heading"] = {}
            if heading_text is not None:
                result["heading"]["text"] = heading_text
            if heading_level is not None:
                result["heading"]["level"] = heading_level

        for key, value in section.items():
            if key not in _HANDLED_KEYS:
                result[key] = value

        normalized.append(result)

    return normalized


def _validate_transform_request(body: dict) -> str:
    """Validate the transform request body, return error string or empty."""
    missing = []
    if not body.get("site"):
        missing.append("site")
    if "sections" not in body:
        missing.append("sections")
    if missing:
        return f"Missing required fields: {', '.join(missing)}"
    if not isinstance(body.get("sections"), list):
        return "'sections' must be a list"
    return ""
