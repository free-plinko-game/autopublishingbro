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
    recursively, flattening the result since all Page Sections clones use
    prefix_name=0 with seamless display.

    Args:
        clone_field: A field dict with type="clone".
        index: Pre-built ACFIndex for lookups.
        visited: Immutable set of already-visited clone keys for cycle detection.
                 Uses frozenset so parallel branches don't interfere.

    Returns:
        Flat list of resolved field dicts (non-clone).

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

    return resolved


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
