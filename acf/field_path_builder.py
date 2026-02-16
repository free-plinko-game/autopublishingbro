"""Build dot-notation field path mappings from resolved ACF fields."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acf.clone_resolver import resolve_clone

if TYPE_CHECKING:
    from acf.index import ACFIndex

# Field types that are UI-only organizers and carry no data
UI_ONLY_TYPES = frozenset({"accordion", "tab", "message"})


def build_field_paths(
    fields: list[dict],
    index: ACFIndex,
    prefix: str = "",
    visited: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Convert a list of ACF fields into a flat dot-notation path mapping.

    Produces a dict where keys are dot-separated paths (e.g. "heading.text")
    and values are ACF field keys (e.g. "field_6104217816977").

    Special handling by field type:
        - group:    Recurse with extended prefix -> heading.alignment.desktop
        - repeater: Nested dict under "name[]" key with sub-field paths
        - clone:    Resolve first, then recurse
        - UI-only:  Skipped entirely (accordion, tab, message)

    Args:
        fields: List of field dicts (may include unresolved clones).
        index: ACFIndex for resolving any remaining clones.
        prefix: Current dot-notation prefix for recursion.
        visited: Clone cycle detection set passed through to resolve_clone.

    Returns:
        Dict mapping dot-notation paths to field keys.
        Repeater entries map to a nested dict of their sub-field paths.
    """
    if visited is None:
        visited = frozenset()

    result: dict[str, Any] = {}

    for field in fields:
        field_type = field.get("type", "")
        name = field.get("name", "")

        # Skip UI-only fields and fields with no name
        if field_type in UI_ONLY_TYPES or not name:
            continue

        path = f"{prefix}.{name}" if prefix else name

        if field_type == "clone":
            expanded = resolve_clone(field, index, visited)
            result.update(build_field_paths(expanded, index, prefix, visited))

        elif field_type == "group":
            sub_fields = field.get("sub_fields", [])
            result.update(build_field_paths(sub_fields, index, path, visited))

        elif field_type == "repeater":
            sub_fields = field.get("sub_fields", [])
            repeater_paths = build_field_paths(sub_fields, index, "", visited)
            result[f"{path}[]"] = repeater_paths

        else:
            # Leaf field — record path -> key mapping
            result[path] = field["key"]

    return result
