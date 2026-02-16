"""Recursively resolve ACF clone fields to their constituent data fields."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acf.index import ACFIndex

logger = logging.getLogger(__name__)


def resolve_clone(
    clone_field: dict,
    index: ACFIndex,
    visited: frozenset[str] | None = None,
) -> list[dict]:
    """Resolve a clone field to the list of actual data fields it represents.

    ACF clone fields reference either entire field groups (group_xxx) or
    individual fields (field_xxx). This function follows those references
    recursively, flattening the result.

    Resolved field keys are prefixed with the clone field's key using the
    ACF format: {clone_field_key}_{original_field_key}. For nested clones,
    prefixes accumulate (inner clones are resolved and prefixed first).

    Args:
        clone_field: A field dict with type="clone".
        index: Pre-built ACFIndex for lookups.
        visited: Immutable set of already-visited clone keys for cycle detection.
                 Uses frozenset so parallel branches don't interfere.

    Returns:
        Flat list of resolved field dicts (non-clone) with prefixed keys.

    Raises:
        ValueError: If a circular clone reference is detected.
    """
    if visited is None:
        visited = frozenset()

    field_key = clone_field.get("key", "")
    if field_key in visited:
        raise ValueError(
            f"Circular clone reference detected at {field_key}. "
            f"Chain: {' -> '.join(visited)} -> {field_key}"
        )

    visited = visited | {field_key}
    refs = clone_field.get("clone", [])
    resolved: list[dict] = []

    for ref in refs:
        if ref in index.groups:
            resolved.extend(_resolve_group_ref(ref, index, visited))
        elif ref in index.fields:
            resolved.extend(_resolve_field_ref(ref, index, visited))
        else:
            logger.warning("Clone reference %r not found in index, skipping", ref)

    return _prefix_keys(resolved, field_key)


def _resolve_group_ref(
    group_key: str,
    index: ACFIndex,
    visited: frozenset[str],
) -> list[dict]:
    """Resolve a clone reference to a full field group."""
    group = index.groups[group_key]
    resolved: list[dict] = []

    for field in group.get("fields", []):
        if field.get("type") == "clone":
            resolved.extend(resolve_clone(field, index, visited))
        else:
            resolved.append(field)

    return resolved


def _resolve_field_ref(
    field_key: str,
    index: ACFIndex,
    visited: frozenset[str],
) -> list[dict]:
    """Resolve a clone reference to an individual field."""
    field = index.fields[field_key]

    if field.get("type") == "clone":
        return resolve_clone(field, index, visited)

    return [field]


def _prefix_keys(fields: list[dict], clone_key: str) -> list[dict]:
    """Create copies of fields with keys prefixed by the clone field's key.

    ACF clone fields store data using composite keys in the format
    {clone_field_key}_{original_field_key}. This function applies that
    prefix to all field keys, recursing into sub_fields for groups
    and repeaters.
    """
    if not clone_key:
        return fields

    prefixed: list[dict] = []
    for field in fields:
        new_field = dict(field)  # shallow copy
        if "key" in new_field:
            new_field["key"] = f"{clone_key}_{new_field['key']}"
        # Recursively prefix sub_fields (groups, repeaters)
        if isinstance(new_field.get("sub_fields"), list):
            new_field["sub_fields"] = _prefix_keys(
                new_field["sub_fields"], clone_key
            )
        prefixed.append(new_field)
    return prefixed
