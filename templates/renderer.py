"""Render page templates by substituting variables and identifying LLM fields."""

from __future__ import annotations

import logging
import re
from typing import Any

from templates.loader import LLM_GENERATE

logger = logging.getLogger(__name__)

# Pattern for template variables: {variable_name}
# Matches {word} but NOT {{word}} (double-brace is the LLM sentinel)
_VAR_PATTERN = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


def render_page_template(
    template: dict[str, Any],
    variables: dict[str, str],
) -> list[dict[str, Any]]:
    """Render a page template into a list of section specs ready for the LLM.

    Substitutes {variable} placeholders in all string fields.
    Preserves {{LLM_GENERATE}} markers for the content generator to find.

    Args:
        template: Loaded page template dict.
        variables: Variable values to substitute (e.g. category_name, cta_list_id).

    Returns:
        List of rendered section dicts, each containing:
        - acf_fc_layout: The layout name
        - fields: Dict of field values (with variables substituted)
        - purpose: What this section is for (from template)
        - llm_context: Instructions for the LLM (with variables substituted)
        - llm_fields: List of field paths that need LLM generation

    Raises:
        ValueError: If required variables are missing.
    """
    _check_required_variables(template, variables)

    rendered_sections: list[dict[str, Any]] = []

    for section in template.get("sections", []):
        rendered = _render_section(section, variables)
        rendered_sections.append(rendered)

    return rendered_sections


def _check_required_variables(
    template: dict[str, Any],
    variables: dict[str, str],
) -> None:
    """Validate that all required variables have been provided."""
    template_vars = template.get("variables", {})
    missing = []

    for var_name, var_config in template_vars.items():
        if isinstance(var_config, dict) and var_config.get("required", False):
            if var_name not in variables or not variables[var_name]:
                missing.append(var_name)

    if missing:
        raise ValueError(
            f"Missing required variables: {', '.join(missing)}"
        )


def _render_section(
    section: dict[str, Any],
    variables: dict[str, str],
) -> dict[str, Any]:
    """Render a single section, substituting variables."""
    fields = _substitute_variables(section.get("fields", {}), variables)
    llm_fields = _find_llm_fields(fields)

    rendered = {
        "acf_fc_layout": section["layout"],
        "fields": fields,
        "purpose": section.get("purpose", ""),
        "llm_context": _substitute_string(
            section.get("llm_context", ""), variables
        ),
        "llm_fields": llm_fields,
    }

    return rendered


def _substitute_variables(value: Any, variables: dict[str, str]) -> Any:
    """Recursively substitute {variable} placeholders in a value."""
    if isinstance(value, str):
        return _substitute_string(value, variables)
    elif isinstance(value, dict):
        return {k: _substitute_variables(v, variables) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_variables(item, variables) for item in value]
    return value


def _substitute_string(text: str, variables: dict[str, str]) -> str:
    """Substitute {variable} placeholders in a string.

    Does NOT touch {{LLM_GENERATE}} — double-braces are preserved.
    """
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in variables:
            return str(variables[var_name])
        logger.warning("Unresolved variable {%s} in template", var_name)
        return match.group(0)  # leave as-is

    return _VAR_PATTERN.sub(replacer, text)


def _find_llm_fields(fields: dict[str, Any], prefix: str = "") -> list[str]:
    """Find all field paths whose value is {{LLM_GENERATE}}.

    Returns dot-notation paths like ["content", "heading.text"].
    """
    llm_fields: list[str] = []

    for key, value in fields.items():
        path = f"{prefix}.{key}" if prefix else key

        if isinstance(value, str) and value == LLM_GENERATE:
            llm_fields.append(path)
        elif isinstance(value, dict):
            llm_fields.extend(_find_llm_fields(value, path))

    return llm_fields
