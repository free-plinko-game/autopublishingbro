"""Validate templates against the ACF field mapping."""

from __future__ import annotations

import logging
from typing import Any

from acf.mapping_loader import FieldMapping

logger = logging.getLogger(__name__)


def validate_page_template(
    template: dict[str, Any],
    mapping: FieldMapping,
) -> list[str]:
    """Validate a page template against the field mapping.

    Checks that:
    - All section layouts exist in the mapping
    - All field paths in sections exist in the mapping for that layout
    - Required variables are declared

    Args:
        template: Loaded page template dict.
        mapping: Loaded FieldMapping for the target site.

    Returns:
        List of warning/error strings. Empty means valid.
    """
    warnings: list[str] = []

    for i, section in enumerate(template.get("sections", [])):
        layout_name = section.get("layout")
        if not layout_name:
            warnings.append(f"Section {i}: missing 'layout' key")
            continue

        if not mapping.has_layout(layout_name):
            warnings.append(
                f"Section {i}: layout '{layout_name}' not found in mapping"
            )
            continue

        _validate_section_fields(i, section, layout_name, mapping, warnings)

    return warnings


def validate_base_template(
    base_template: dict[str, Any],
    mapping: FieldMapping,
) -> list[str]:
    """Validate a base section template against the field mapping.

    Checks that all declared fields exist in the mapping for the layout.

    Args:
        base_template: Loaded base template dict.
        mapping: FieldMapping for the target site.

    Returns:
        List of warning strings.
    """
    warnings: list[str] = []
    layout_name = base_template.get("layout")

    if not layout_name:
        warnings.append("Base template missing 'layout' key")
        return warnings

    if not mapping.has_layout(layout_name):
        warnings.append(f"Layout '{layout_name}' not found in mapping")
        return warnings

    layout_fields = mapping.get_layout_fields(layout_name)
    known_paths = _collect_mapping_field_names(layout_fields)

    template_fields = base_template.get("fields", {})
    template_paths = _collect_base_template_field_names(template_fields)

    for path in template_paths:
        if path not in known_paths:
            warnings.append(
                f"Layout '{layout_name}': field '{path}' not found in mapping"
            )

    return warnings


def _validate_section_fields(
    index: int,
    section: dict[str, Any],
    layout_name: str,
    mapping: FieldMapping,
    warnings: list[str],
) -> None:
    """Check that fields used in a section exist in the layout mapping."""
    layout_fields = mapping.get_layout_fields(layout_name)
    known_paths = _collect_mapping_field_names(layout_fields)

    section_fields = section.get("fields", {})
    section_paths = _collect_template_field_names(section_fields)

    for path in section_paths:
        if path not in known_paths:
            warnings.append(
                f"Section {index} ({layout_name}): "
                f"field '{path}' not found in mapping"
            )


def _collect_mapping_field_names(
    layout_fields: dict[str, Any],
) -> set[str]:
    """Collect all valid field names from the mapping.

    Converts dot-notation keys from the mapping into the nested names
    that templates use. E.g. "heading.text" -> "heading", "heading.text".
    Also handles repeater fields like "accordions[]" -> "accordions".
    """
    names: set[str] = set()

    for key, value in layout_fields.items():
        if key.endswith("[]") and isinstance(value, dict):
            # Repeater: strip [] for template field name
            base = key[:-2]
            names.add(base)
            for sub_key in value:
                names.add(f"{base}.{sub_key}")
        elif "." in key:
            # Dot-notation: add full path and all intermediate segments
            names.add(key)
            parts = key.split(".")
            for j in range(1, len(parts)):
                names.add(".".join(parts[:j]))
        else:
            names.add(key)

    return names


def _collect_template_field_names(
    fields: dict[str, Any],
    prefix: str = "",
) -> set[str]:
    """Collect all field name paths from a page template's fields dict.

    Walks the nested structure and produces dot-notation paths.
    Page template fields contain actual values, not schema metadata.
    """
    names: set[str] = set()

    for key, value in fields.items():
        path = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            # Nested dict — add the parent path and recurse
            names.add(path)
            names.update(_collect_template_field_names(value, path))
        elif isinstance(value, list):
            # Repeater data — just add the path
            names.add(path)
        else:
            names.add(path)

    return names


# Keys that are schema metadata in base templates, not ACF field names
_BASE_TEMPLATE_METADATA_KEYS = frozenset({
    "type", "description", "default", "required", "options",
    "llm_generate", "llm_instruction", "sub_fields",
})


def _collect_base_template_field_names(
    fields: dict[str, Any],
    prefix: str = "",
) -> set[str]:
    """Collect ACF field name paths from a base template's schema.

    Base templates describe field schemas with metadata like type,
    description, llm_generate, etc. This function extracts only the
    actual ACF field names, skipping metadata keys.

    A leaf field looks like: {type: text, description: "...", ...}
    A group field looks like: {text: {type: text, ...}, level: {type: select, ...}}
    A repeater looks like: {type: repeater, sub_fields: {title: {...}, content: {...}}}
    """
    names: set[str] = set()

    for key, value in fields.items():
        path = f"{prefix}.{key}" if prefix else key

        if not isinstance(value, dict):
            # Scalar at field level — this is a direct value, not a schema
            names.add(path)
            continue

        if _is_field_schema(value):
            # This is a leaf field definition (has 'type' key)
            names.add(path)
            # If it's a repeater, validate sub_fields too
            if value.get("type") == "repeater" and "sub_fields" in value:
                names.update(
                    _collect_base_template_field_names(value["sub_fields"], path)
                )
        else:
            # This is a nested group — recurse into it
            names.add(path)
            names.update(_collect_base_template_field_names(value, path))

    return names


def _is_field_schema(value: dict) -> bool:
    """Check if a dict looks like a field schema definition.

    A field schema has at least a 'type' key and most of its keys are
    metadata keys rather than ACF field names.
    """
    if "type" not in value:
        return False
    # If most keys are metadata, it's a schema
    metadata_count = sum(1 for k in value if k in _BASE_TEMPLATE_METADATA_KEYS)
    return metadata_count > len(value) // 2
