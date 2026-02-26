"""Flask application entry point."""
from __future__ import annotations
import os
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

from api.routes import api_bp
from api.settings import settings_bp


def create_app(config: dict | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config: Optional config dict to override defaults.

    Returns:
        Configured Flask app instance.
    """
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    # Defaults
    app.config["FIELD_MAPPING_PATH"] = os.environ.get(
        "FIELD_MAPPING_PATH", "config/field_mappings/sunvegascasino.json"
    )

    # Apply overrides
    if config:
        app.config.update(config)

    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(settings_bp)

    @app.route("/")
    def index():
        return jsonify({"error": "UI disabled. Use API endpoints only."}), 403

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=False, port=5010)
