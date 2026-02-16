"""Orchestrate LLM content generation for page templates.

Takes rendered template sections and fills in all {{LLM_GENERATE}} fields
by calling the LLM with context-aware prompts.
"""

from __future__ import annotations

import logging
from typing import Any

from llm.client import LLMClient
from llm.prompts import (
    SYSTEM_PROMPT,
    build_section_prompt,
    build_repeater_prompt,
)
from templates.loader import load_base_template, LLM_GENERATE
from utils.html_sanitizer import sanitize_html, strip_html

logger = logging.getLogger(__name__)


def generate_page_content(
    rendered_sections: list[dict[str, Any]],
    client: LLMClient,
    page_context: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Generate content for all LLM_GENERATE fields across all sections.

    Iterates through rendered sections, finds fields marked for generation,
    builds context-aware prompts, calls the LLM, sanitizes output, and
    replaces the markers with real content.

    Args:
        rendered_sections: Output from render_page_template().
        client: Configured LLMClient instance.
        page_context: Variables dict for page-level context in prompts.

    Returns:
        Completed sections with all LLM_GENERATE markers replaced.
        Each section has acf_fc_layout and fields ready for the transformer.
    """
    completed: list[dict[str, Any]] = []

    for i, section in enumerate(rendered_sections):
        layout = section["acf_fc_layout"]
        llm_fields = section.get("llm_fields", [])

        if not llm_fields:
            # No LLM generation needed — pass through as-is
            completed.append(_strip_metadata(section))
            continue

        logger.info(
            "Section %d (%s): generating %d field(s): %s",
            i, layout, len(llm_fields), ", ".join(llm_fields),
        )

        # Load base template for field-level instructions
        base = _load_base_safe(layout)

        fields = _deep_copy(section["fields"])

        for field_path in llm_fields:
            content = _generate_field(
                section=section,
                field_path=field_path,
                base_template=base,
                client=client,
                page_context=page_context,
            )
            _set_nested_value(fields, field_path, content)

        completed.append({
            "acf_fc_layout": layout,
            "fields": fields,
        })

    return completed


def generate_single_section(
    section: dict[str, Any],
    client: LLMClient,
    page_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate content for a single rendered section.

    Convenience wrapper for regenerating one section at a time.
    """
    results = generate_page_content([section], client, page_context)
    return results[0] if results else section


def _generate_field(
    section: dict[str, Any],
    field_path: str,
    base_template: dict[str, Any] | None,
    client: LLMClient,
    page_context: dict[str, str] | None,
) -> str:
    """Generate content for a single field."""
    field_instruction = _get_field_instruction(base_template, field_path)
    field_type = _get_field_type(base_template, field_path)

    prompt = build_section_prompt(
        section=section,
        field_path=field_path,
        field_instruction=field_instruction,
        page_context=page_context,
    )

    logger.debug("Generating field %s with prompt length %d", field_path, len(prompt))

    raw = client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
    )

    # Sanitize based on field type
    if field_type in ("wysiwyg", "html"):
        return sanitize_html(raw)
    elif field_type == "text":
        return strip_html(raw)
    else:
        return sanitize_html(raw)


def _load_base_safe(layout_name: str) -> dict[str, Any] | None:
    """Load a base template, returning None if not found."""
    try:
        return load_base_template(layout_name)
    except FileNotFoundError:
        logger.debug("No base template for layout %s", layout_name)
        return None


def _get_field_instruction(
    base_template: dict[str, Any] | None,
    field_path: str,
) -> str:
    """Extract llm_instruction for a field from the base template."""
    if base_template is None:
        return ""

    return _walk_base_template(
        base_template.get("fields", {}),
        field_path,
        "llm_instruction",
    )


def _get_field_type(
    base_template: dict[str, Any] | None,
    field_path: str,
) -> str:
    """Extract field type from the base template."""
    if base_template is None:
        return "wysiwyg"

    result = _walk_base_template(
        base_template.get("fields", {}),
        field_path,
        "type",
    )
    return result or "wysiwyg"


def _walk_base_template(
    fields: dict[str, Any],
    field_path: str,
    target_key: str,
) -> str:
    """Walk the base template field structure to find a property.

    The base template uses a nested schema structure:
    fields.heading.text.llm_instruction -> "Write a compelling heading"
    fields.content.type -> "wysiwyg"
    """
    parts = field_path.split(".")
    current = fields

    for part in parts:
        if not isinstance(current, dict):
            return ""
        if part not in current:
            return ""
        current = current[part]

    if isinstance(current, dict):
        return str(current.get(target_key, ""))
    return ""


def _set_nested_value(d: dict, path: str, value: Any) -> None:
    """Set a value in a nested dict using a dot-notation path."""
    parts = path.split(".")
    current = d

    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]

    current[parts[-1]] = value


def _strip_metadata(section: dict[str, Any]) -> dict[str, Any]:
    """Strip template metadata, keeping only acf_fc_layout and fields."""
    return {
        "acf_fc_layout": section["acf_fc_layout"],
        "fields": section["fields"],
    }


def _deep_copy(d: Any) -> Any:
    """Deep copy nested dicts/lists of primitives."""
    if isinstance(d, dict):
        return {k: _deep_copy(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [_deep_copy(item) for item in d]
    return d
