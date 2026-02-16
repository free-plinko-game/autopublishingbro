"""Pre-computed index of all ACF groups and fields for O(1) lookup."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ACFIndex:
    """Indexes all groups by key and all fields by key from an ACF export.

    This enables fast lookup during clone resolution, where clones can
    reference either entire groups (group_xxx) or individual fields (field_xxx).
    """

    def __init__(self, export_data: list[dict]):
        self.groups: dict[str, dict] = {}
        self.fields: dict[str, dict] = {}
        self._build(export_data)

    def _build(self, export_data: list[dict]) -> None:
        for group in export_data:
            key = group.get("key", "")
            if not key:
                continue
            self.groups[key] = group
            self._index_fields(group.get("fields", []))

        logger.debug(
            "Indexed %d groups and %d fields",
            len(self.groups),
            len(self.fields),
        )

    def _index_fields(self, fields: list[dict]) -> None:
        """Recursively index all fields, including those nested in groups,
        repeaters, and flexible content layouts."""
        for field in fields:
            key = field.get("key", "")
            if key:
                self.fields[key] = field

            # Recurse into sub_fields (group, repeater, clone)
            sub_fields = field.get("sub_fields")
            if isinstance(sub_fields, list):
                self._index_fields(sub_fields)

            # Recurse into flexible_content layouts
            layouts = field.get("layouts")
            if isinstance(layouts, dict):
                for layout in layouts.values():
                    layout_subs = layout.get("sub_fields")
                    if isinstance(layout_subs, list):
                        self._index_fields(layout_subs)
