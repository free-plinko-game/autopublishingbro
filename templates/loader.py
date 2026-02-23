"""Load and parse YAML template files."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default directories relative to the templates package
_TEMPLATES_DIR = Path(__file__).parent
BASE_DIR = _TEMPLATES_DIR / "base"
PAGES_DIR = _TEMPLATES_DIR / "pages"

# Sentinel value marking fields the LLM should generate
LLM_GENERATE = "{{LLM_GENERATE}}"


def load_base_template(layout_name: str, base_dir: Path | None = None) -> dict[str, Any]:
    """Load a base section template by layout name.

    Args:
        layout_name: ACF layout name (e.g. "BasicContent").
        base_dir: Override directory for base templates.

    Returns:
        Parsed YAML dict with layout, description, fields.

    Raises:
        FileNotFoundError: If the template file doesn't exist.
    """
    directory = base_dir or BASE_DIR
    filepath = directory / f"{layout_name}.yaml"

    if not filepath.exists():
        raise FileNotFoundError(f"Base template not found: {filepath}")

    with filepath.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data.get("layout") != layout_name:
        logger.warning(
            "Template file %s has layout=%r, expected %r",
            filepath.name,
            data.get("layout"),
            layout_name,
        )

    return data


def load_page_template(template_name: str, pages_dir: Path | None = None) -> dict[str, Any]:
    """Load a page template by name.

    Args:
        template_name: Template name without extension (e.g. "pokies_category").
        pages_dir: Override directory for page templates.

    Returns:
        Parsed YAML dict with name, variables, sections, etc.

    Raises:
        FileNotFoundError: If the template file doesn't exist.
        ValueError: If the template is missing required keys.
    """
    if not re.match(r"^[a-zA-Z0-9_-]+$", template_name):
        raise ValueError("Invalid template name")

    directory = pages_dir or PAGES_DIR
    filepath = directory / f"{template_name}.yaml"

    resolved = filepath.resolve()
    if not str(resolved).startswith(str(directory.resolve())):
        raise ValueError("Invalid template path")

    if not filepath.exists():
        raise FileNotFoundError(f"Page template not found: {filepath}")

    with filepath.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    _validate_page_template_structure(data, filepath)
    return data


def list_page_templates(pages_dir: Path | None = None) -> list[dict[str, Any]]:
    """List all available page templates with their metadata.

    Returns:
        List of dicts with name, description, variables for each template.
    """
    directory = pages_dir or PAGES_DIR
    templates = []

    for filepath in sorted(directory.glob("*.yaml")):
        try:
            with filepath.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            templates.append({
                "name": filepath.stem,
                "display_name": data.get("name", filepath.stem),
                "description": data.get("description", ""),
                "variables": list(data.get("variables", {}).keys()),
            })
        except Exception:
            logger.exception("Failed to read template %s", filepath)

    return templates


def list_base_templates(base_dir: Path | None = None) -> list[str]:
    """List all available base template layout names."""
    directory = base_dir or BASE_DIR
    return sorted(p.stem for p in directory.glob("*.yaml"))


def _validate_page_template_structure(data: dict, filepath: Path) -> None:
    """Check that a page template has the required top-level keys."""
    if "sections" not in data:
        raise ValueError(f"Page template {filepath} missing 'sections' key")

    for i, section in enumerate(data["sections"]):
        if "layout" not in section:
            raise ValueError(
                f"Section {i} in {filepath} missing 'layout' key"
            )
        if "fields" not in section:
            raise ValueError(
                f"Section {i} in {filepath} missing 'fields' key"
            )
