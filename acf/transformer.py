"""Transform human-readable content to ACF REST API format.

Takes section dicts written by humans/LLMs using friendly field names
and produces the nested structure WordPress ACF Pro REST API expects.
"""

from __future__ import annotations

import logging
from typing import Any

from acf.defaults import apply_defaults
from acf.mapping_loader import FieldMapping

logger = logging.getLogger(__name__)


def transform_to_acf(
    sections: list[dict[str, Any]],
    mapping: FieldMapping,
) -> dict[str, Any]:
    """Transform a list of human-readable sections into an ACF REST API payload.

    Args:
        sections: List of section dicts, each with an "acf_fc_layout" key
                  identifying the layout and field values in nested form.
        mapping: Loaded FieldMapping for the target site.

    Returns:
        Dict ready to send as the request body, structured as:
        {"acf": {"page_sections": [...]}}
    """
    transformed_sections = []

    for i, section in enumerate(sections):
        layout_name = section.get("acf_fc_layout")
        if not layout_name:
            logger.warning("Section %d missing acf_fc_layout, skipping", i)
            continue

        if not mapping.has_layout(layout_name):
            logger.warning(
                "Unknown layout %r in section %d, skipping", layout_name, i
            )
            continue

        transformed = transform_section(section, mapping)
        transformed_sections.append(transformed)

    return {
        "acf": {
            "page_sections": transformed_sections,
        },
    }


def transform_section(
    section: dict[str, Any],
    mapping: FieldMapping,
) -> dict[str, Any]:
    """Transform a single section with defaults applied.

    Args:
        section: Human-readable section dict with acf_fc_layout.
        mapping: Loaded FieldMapping.

    Returns:
        Section dict with defaults filled in and acf_fc_layout preserved.
    """
    layout_name = section["acf_fc_layout"]
    layout_fields = mapping.get_layout_fields(layout_name)

    # Start with the layout identifier
    result: dict[str, Any] = {"acf_fc_layout": layout_name}

    # Apply defaults, then merge user-provided values on top
    section_without_layout = {
        k: v for k, v in section.items() if k != "acf_fc_layout"
    }
    merged = apply_defaults(section_without_layout, layout_fields)

    # Expand the merged content into the result
    result.update(merged)

    return result


def validate_sections(
    sections: list[dict[str, Any]],
    mapping: FieldMapping,
) -> list[str]:
    """Validate sections against the mapping, returning a list of warnings.

    Checks for:
    - Missing acf_fc_layout
    - Unknown layout names
    - Fields provided that don't exist in the mapping

    Args:
        sections: List of human-readable section dicts.
        mapping: Loaded FieldMapping.

    Returns:
        List of warning strings. Empty list means all valid.
    """
    warnings: list[str] = []

    for i, section in enumerate(sections):
        layout_name = section.get("acf_fc_layout")
        if not layout_name:
            warnings.append(f"Section {i}: missing acf_fc_layout")
            continue

        if not mapping.has_layout(layout_name):
            warnings.append(f"Section {i}: unknown layout '{layout_name}'")
            continue

        layout_fields = mapping.get_layout_fields(layout_name)
        _validate_section_fields(i, section, layout_fields, warnings)

    return warnings


def _validate_section_fields(
    index: int,
    section: dict[str, Any],
    layout_fields: dict[str, Any],
    warnings: list[str],
) -> None:
    """Check that user-provided fields exist in the layout mapping."""
    known_paths = _collect_known_paths(layout_fields)

    for key in section:
        if key == "acf_fc_layout":
            continue
        # Build all possible dot-paths for this key
        section_paths = _collect_nested_paths(key, section[key])
        for path in section_paths:
            if path not in known_paths:
                warnings.append(
                    f"Section {index} ({section['acf_fc_layout']}): "
                    f"unknown field '{path}'"
                )


def _collect_known_paths(
    layout_fields: dict[str, Any],
    prefix: str = "",
) -> set[str]:
    """Collect all valid dot-notation paths from the mapping fields."""
    paths: set[str] = set()

    for key, value in layout_fields.items():
        # Repeater fields: key ends with []
        if key.endswith("[]") and isinstance(value, dict):
            base = key[:-2]  # strip []
            full = f"{prefix}.{base}" if prefix else base
            paths.add(full)
            # Add sub-paths within the repeater
            for sub_path in _collect_known_paths(value):
                paths.add(f"{full}.{sub_path}")
        elif "." in key:
            # Dot-notation path from mapping — add the full path and all prefixes
            full = f"{prefix}.{key}" if prefix else key
            paths.add(full)
            # Also add intermediate segments as valid (for nested dict input)
            parts = key.split(".")
            for j in range(1, len(parts)):
                partial = ".".join(parts[:j])
                full_partial = f"{prefix}.{partial}" if prefix else partial
                paths.add(full_partial)
        else:
            full = f"{prefix}.{key}" if prefix else key
            paths.add(full)

    return paths


def _collect_nested_paths(key: str, value: Any, prefix: str = "") -> list[str]:
    """Collect all dot-notation paths from a nested value."""
    full = f"{prefix}.{key}" if prefix else key

    if isinstance(value, dict):
        paths = [full]  # The parent path itself is valid
        for sub_key, sub_val in value.items():
            paths.extend(_collect_nested_paths(sub_key, sub_val, full))
        return paths
    elif isinstance(value, list):
        return [full]
    else:
        return [full]
