"""Default values for optional ACF fields.

These defaults are applied to sections before sending to the WordPress
REST API, ensuring all expected fields are present even when the LLM
or template doesn't specify them.
"""

from __future__ import annotations

from typing import Any

# Default values for common fields shared across most layouts.
# These are the fields from group_clone_common_fields.
COMMON_FIELD_DEFAULTS: dict[str, Any] = {
    "section_id": "",
    "padding_override": "reduced-padding",
    "section_width": "narrow",
    "toc_exclude": False,
    "background_color": "",
    "background_image": "",
}

# Default values for the heading clone group.
# Applied as nested structure matching the dot-notation paths.
HEADING_DEFAULTS: dict[str, Any] = {
    "heading": {
        "text": "",
        "level": "h2",
        "alignment": {
            "desktop": "inherit",
            "mobile": "inherit",
        },
    },
}

# Default values for the read_more clone group.
READ_MORE_DEFAULTS: dict[str, Any] = {
    "read_more_text": "",
    "read_less_text": "",
    "read_more_content": "",
    "read_more_mobile_only": False,
}


def get_defaults_for_layout(layout_fields: dict[str, Any]) -> dict[str, Any]:
    """Build a defaults dict for a layout based on which fields it has.

    Inspects the layout's field mapping to determine which default groups
    apply, then merges them into a single defaults dict.

    Args:
        layout_fields: The fields dict from the mapping (dot-notation keys).

    Returns:
        Nested dict of default values matching the layout's field structure.
    """
    defaults: dict[str, Any] = {}

    # Apply common field defaults if the layout has any of them
    if "section_id" in layout_fields:
        defaults.update(COMMON_FIELD_DEFAULTS)

    # Apply heading defaults if the layout has heading fields
    if "heading.text" in layout_fields:
        defaults.update(_deep_copy_dict(HEADING_DEFAULTS))

    # Apply read_more defaults if the layout has those fields
    if "read_more_text" in layout_fields:
        defaults.update(READ_MORE_DEFAULTS)

    return defaults


def apply_defaults(section: dict[str, Any], layout_fields: dict[str, Any]) -> dict[str, Any]:
    """Apply default values to a section, filling in missing optional fields.

    User-provided values take precedence over defaults. Nested dicts
    are merged recursively so partial heading overrides work correctly.

    Args:
        section: The human-readable section dict (may be partial).
        layout_fields: The fields dict from the mapping.

    Returns:
        New section dict with defaults applied (original not modified).
    """
    defaults = get_defaults_for_layout(layout_fields)
    return _deep_merge(defaults, section)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override values win."""
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _deep_copy_dict(d: dict) -> dict:
    """Simple deep copy for nested dicts of primitives."""
    result = {}
    for key, value in d.items():
        if isinstance(value, dict):
            result[key] = _deep_copy_dict(value)
        else:
            result[key] = value
    return result
