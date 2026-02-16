"""Main ACF export parser — extracts Page Sections layout mappings."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from acf.index import ACFIndex
from acf.clone_resolver import resolve_clone
from acf.field_path_builder import build_field_paths

logger = logging.getLogger(__name__)

# The Page Sections group and its flexible_content field
PAGE_SECTIONS_GROUP_KEY = "group_6104225bab52f"
PAGE_SECTIONS_FIELD_KEY = "field_61042266f0b46"


def parse_acf_export(filepath: str | Path) -> dict[str, Any]:
    """Parse an ACF export JSON file and return the Page Sections field mapping.

    Args:
        filepath: Path to the ACF export JSON file.

    Returns:
        Mapping dict with structure:
        {
            "flexible_content_key": "field_...",
            "layouts": {
                "LayoutName": {
                    "layout_key": "layout_...",
                    "fields": { "dot.path": "field_key", ... }
                }
            }
        }
    """
    filepath = Path(filepath)

    with filepath.open("r", encoding="utf-8") as f:
        export_data = json.load(f)

    if not isinstance(export_data, list):
        raise ValueError("ACF export must be a JSON array of field groups")

    return extract_page_sections_layouts(export_data)


def extract_page_sections_layouts(export_data: list[dict]) -> dict[str, Any]:
    """Extract all Page Sections layouts with resolved field mappings.

    Builds an index of the full export, locates the Page Sections
    flexible_content field, then iterates each layout — resolving
    clone references and building dot-notation field paths.
    """
    index = ACFIndex(export_data)

    # Find the Page Sections group
    ps_group = index.groups.get(PAGE_SECTIONS_GROUP_KEY)
    if ps_group is None:
        raise ValueError(
            f"Page Sections group ({PAGE_SECTIONS_GROUP_KEY}) not found in export"
        )

    # Find the flexible_content field within it
    fc_field = _find_flexible_content_field(ps_group)
    layouts_dict = fc_field.get("layouts", {})

    result_layouts: dict[str, dict] = {}

    for layout_key, layout in layouts_dict.items():
        layout_name = layout["name"]

        try:
            field_paths = _process_layout(layout, index)
        except Exception:
            logger.exception("Failed to process layout %s", layout_name)
            continue

        result_layouts[layout_name] = {
            "layout_key": layout_key,
            "fields": field_paths,
        }

    logger.info("Parsed %d layouts from Page Sections", len(result_layouts))

    return {
        "flexible_content_key": PAGE_SECTIONS_FIELD_KEY,
        "layouts": result_layouts,
    }


def _find_flexible_content_field(ps_group: dict) -> dict:
    """Locate the flexible_content field within the Page Sections group."""
    for field in ps_group.get("fields", []):
        if field.get("key") == PAGE_SECTIONS_FIELD_KEY:
            if field.get("type") != "flexible_content":
                raise ValueError(
                    f"Expected flexible_content, got {field.get('type')}"
                )
            return field

    raise ValueError(
        f"Flexible content field ({PAGE_SECTIONS_FIELD_KEY}) "
        f"not found in Page Sections group"
    )


def _process_layout(layout: dict, index: ACFIndex) -> dict[str, Any]:
    """Process a single layout: resolve its clone and build field paths."""
    sub_fields = layout.get("sub_fields", [])

    if not sub_fields:
        logger.warning("Layout %s has no sub_fields", layout.get("name"))
        return {}

    # Each layout typically has one clone sub_field pointing to a component group.
    # Resolve all sub_fields (handles edge cases where there might be more).
    all_resolved: list[dict] = []

    for sf in sub_fields:
        if sf.get("type") == "clone":
            all_resolved.extend(resolve_clone(sf, index))
        else:
            all_resolved.append(sf)

    return build_field_paths(all_resolved, index)


def pretty_print_mapping(mapping: dict[str, Any]) -> None:
    """Print a human-readable summary of the parsed ACF mapping."""
    print(f"Flexible Content Key: {mapping['flexible_content_key']}")
    print(f"Total Layouts: {len(mapping['layouts'])}")
    print("=" * 70)

    for layout_name, layout_data in sorted(mapping["layouts"].items()):
        print(f"\n  {layout_name}  ({layout_data['layout_key']})")
        print("  " + "-" * 50)
        _print_fields(layout_data["fields"], indent=4)


def _print_fields(fields: dict, indent: int = 0) -> None:
    """Recursively print field paths, handling repeater sub-dicts."""
    prefix = " " * indent
    for path, value in sorted(fields.items()):
        if isinstance(value, dict):
            print(f"{prefix}{path}  [repeater]")
            _print_fields(value, indent + 4)
        else:
            print(f"{prefix}{path}  ->  {value}")
