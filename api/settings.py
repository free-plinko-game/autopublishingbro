"""Settings API — manage WordPress sites and OpenAI configuration."""

from __future__ import annotations
import hmac

import logging
import os
from pathlib import Path

from dotenv import set_key
from flask import Blueprint, jsonify, request

from wordpress.auth import (
    load_site_config,
    list_sites,
    save_site_config,
    delete_site_config,
)
from wordpress.client import WordPressClient

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")


@settings_bp.before_request
def check_settings_auth():
    api_key = os.environ.get("TRANSFORM_API_KEY")
    if not api_key:
        return jsonify({"error": "Auth not configured"}), 500
    provided = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(provided, api_key):
        return jsonify({"error": "Unauthorized"}), 401

_ENV_PATH = Path(__file__).parent.parent / ".env"


def _mask(value: str, visible: int = 4) -> str:
    """Mask a secret string, showing only the last `visible` characters."""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]


# --- GET /api/settings ---


@settings_bp.route("", methods=["GET"])
def get_settings():
    """Return all settings with sensitive values masked."""
    site_names = list_sites()
    sites_data = {}
    for name in site_names:
        try:
            config = load_site_config(name)
            sites_data[name] = {
                "base_url": config.base_url,
                "username": config.username,
                "application_password": _mask(config.application_password),
                "default_author_id": config.default_author_id,
                "default_status": config.default_status,
            }
        except ValueError:
            continue

    api_key = os.environ.get("OPENAI_API_KEY", "")
    openai_info = {
        "api_key_set": bool(api_key),
        "api_key_masked": _mask(api_key) if api_key else "",
    }

    return jsonify({"sites": sites_data, "openai": openai_info})


# --- POST /api/settings/sites ---


@settings_bp.route("/sites", methods=["POST"])
def upsert_site():
    """Add or update a WordPress site configuration."""
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON"}), 400

    site_name = body.get("name", "").strip()
    if not site_name:
        return jsonify({"error": "Missing 'name' field"}), 400

    try:
        save_site_config(site_name, body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"success": True, "site": site_name}), 200


# --- DELETE /api/settings/sites/<site_name> ---


@settings_bp.route("/sites/<site_name>", methods=["DELETE"])
def remove_site(site_name: str):
    """Remove a WordPress site configuration."""
    removed = delete_site_config(site_name)
    if not removed:
        return jsonify({"error": f"Site '{site_name}' not found"}), 404
    return jsonify({"success": True, "site": site_name}), 200


# --- POST /api/settings/sites/<site_name>/test ---


@settings_bp.route("/sites/<site_name>/test", methods=["POST"])
def test_site(site_name: str):
    """Test the connection to a WordPress site."""
    try:
        config = load_site_config(site_name)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    wp_client = WordPressClient(config)
    result = wp_client.test_connection()
    status_code = 200 if result["ok"] else 502
    return jsonify(result), status_code


# --- POST /api/settings/openai ---


@settings_bp.route("/openai", methods=["POST"])
def update_openai_key():
    """Update the OpenAI API key."""
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    api_key = body.get("api_key", "").strip()
    if not api_key:
        return jsonify({"error": "Missing 'api_key' field"}), 400

    set_key(str(_ENV_PATH), "OPENAI_API_KEY", api_key)
    os.environ["OPENAI_API_KEY"] = api_key

    return jsonify({
        "success": True,
        "api_key_masked": _mask(api_key),
    }), 200
