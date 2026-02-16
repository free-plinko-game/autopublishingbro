"""Tests for the ACF parser module."""

import json
from pathlib import Path

import pytest

from acf.index import ACFIndex
from acf.clone_resolver import resolve_clone
from acf.field_path_builder import build_field_paths
from acf.parser import parse_acf_export, pretty_print_mapping

ACF_EXPORT_PATH = Path(__file__).parent.parent / "acf-export-2026-02-13.json"


@pytest.fixture(scope="session")
def export_data():
    with ACF_EXPORT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def index(export_data):
    return ACFIndex(export_data)


@pytest.fixture(scope="session")
def mapping():
    return parse_acf_export(ACF_EXPORT_PATH)


# --- ACFIndex tests ---


class TestACFIndex:
    def test_indexes_all_groups(self, index):
        assert len(index.groups) >= 90

    def test_page_sections_group_exists(self, index):
        assert "group_6104225bab52f" in index.groups

    def test_heading_text_field_indexed(self, index):
        assert "field_6104217816977" in index.fields

    def test_common_fields_group_exists(self, index):
        assert "group_clone_common_fields" in index.groups

    def test_heading_clone_group_exists(self, index):
        assert "group_610421312ec7b" in index.groups


# --- Clone resolver tests ---


class TestCloneResolver:
    def test_resolves_common_fields_group(self, index):
        # Build a mock clone field referencing common fields
        clone_field = {
            "key": "test_clone_1",
            "type": "clone",
            "clone": ["group_clone_common_fields"],
        }
        resolved = resolve_clone(clone_field, index)

        names = [f.get("name") for f in resolved if f.get("name")]
        assert "section_id" in names
        assert "padding_override" in names
        assert "section_width" in names

    def test_resolves_individual_field_refs(self, index):
        clone_field = {
            "key": "test_clone_2",
            "type": "clone",
            "clone": ["field_607dbe7d30c4e", "field_604fb9aff2bef"],
        }
        resolved = resolve_clone(clone_field, index)

        names = [f.get("name") for f in resolved]
        assert "section_id" in names
        assert "padding_override" in names

    def test_cycle_detection(self):
        # Two groups that clone each other
        fake_export = [
            {
                "key": "group_a",
                "title": "Group A",
                "fields": [
                    {"key": "field_clone_a", "type": "clone", "clone": ["group_b"]}
                ],
            },
            {
                "key": "group_b",
                "title": "Group B",
                "fields": [
                    {"key": "field_clone_b", "type": "clone", "clone": ["group_a"]}
                ],
            },
        ]
        fake_index = ACFIndex(fake_export)
        clone_field = {"key": "field_clone_a", "type": "clone", "clone": ["group_b"]}

        with pytest.raises(ValueError, match="Circular clone reference"):
            resolve_clone(clone_field, fake_index)

    def test_skips_missing_references(self, index):
        clone_field = {
            "key": "test_clone_3",
            "type": "clone",
            "clone": ["group_nonexistent_12345"],
        }
        resolved = resolve_clone(clone_field, index)
        assert resolved == []


# --- Field path builder tests ---


class TestFieldPathBuilder:
    def test_heading_group_produces_dot_notation(self, index):
        # Get the heading group fields directly
        heading_group = index.groups["group_610421312ec7b"]
        fields = heading_group.get("fields", [])
        paths = build_field_paths(fields, index)

        assert "heading.text" in paths
        assert "heading.level" in paths
        assert "heading.alignment.desktop" in paths
        assert "heading.alignment.mobile" in paths

    def test_heading_field_keys_correct(self, index):
        heading_group = index.groups["group_610421312ec7b"]
        fields = heading_group.get("fields", [])
        paths = build_field_paths(fields, index)

        assert paths["heading.text"] == "field_6104217816977"
        assert paths["heading.level"] == "field_6104217f16978"

    def test_ui_only_fields_skipped(self, index):
        fields = [
            {"key": "f1", "name": "", "type": "accordion"},
            {"key": "f2", "name": "real_field", "type": "text"},
        ]
        paths = build_field_paths(fields, index)

        assert len(paths) == 1
        assert "real_field" in paths


# --- Full parser tests ---


class TestParseACFExport:
    def test_parses_all_layouts(self, mapping):
        assert len(mapping["layouts"]) >= 37

    def test_flexible_content_key(self, mapping):
        assert mapping["flexible_content_key"] == "field_61042266f0b46"

    def test_basic_content_layout_exists(self, mapping):
        assert "BasicContent" in mapping["layouts"]

    def test_basic_content_heading_text(self, mapping):
        bc = mapping["layouts"]["BasicContent"]
        # Clone prefix: layout clone field_6104227ef0b47 + heading clone field_611e64259a1e0
        assert bc["fields"]["heading.text"] == (
            "field_6104227ef0b47_field_611e64259a1e0_field_6104217816977"
        )

    def test_basic_content_content_field(self, mapping):
        bc = mapping["layouts"]["BasicContent"]
        # Clone prefix: layout clone field_6104227ef0b47
        assert bc["fields"]["content"] == (
            "field_6104227ef0b47_field_611e64259a296"
        )

    def test_basic_content_common_fields(self, mapping):
        bc = mapping["layouts"]["BasicContent"]
        assert "section_id" in bc["fields"]
        assert "padding_override" in bc["fields"]
        assert "section_width" in bc["fields"]
        assert "toc_exclude" in bc["fields"]

    def test_basic_content_layout_key(self, mapping):
        bc = mapping["layouts"]["BasicContent"]
        assert bc["layout_key"] == "layout_6104226d4285a"

    def test_accordion_section_has_repeater(self, mapping):
        acc = mapping["layouts"]["AccordionSection"]
        assert "accordions[]" in acc["fields"]
        repeater = acc["fields"]["accordions[]"]
        assert isinstance(repeater, dict)
        assert "title" in repeater
        assert "content" in repeater

    def test_gambling_operators_fields(self, mapping):
        go = mapping["layouts"]["GamblingOperators"]
        assert "shortcode" in go["fields"]
        assert "content_above" in go["fields"]
        assert "content_below" in go["fields"]
        assert "call_to_action" in go["fields"]

    def test_every_layout_has_fields(self, mapping):
        for name, data in mapping["layouts"].items():
            assert data["fields"], f"Layout {name} has no fields"
            assert data["layout_key"], f"Layout {name} has no layout_key"

    def test_no_ui_only_fields_in_output(self, mapping):
        """Accordion/tab UI fields should never appear as field paths.

        Note: 'accordions[]' is a legitimate repeater field, not a UI accordion.
        """
        for name, data in mapping["layouts"].items():
            for path in data["fields"]:
                # UI-only accordion fields have no name, but the "accordions"
                # repeater is a real data field — only flag exact "accordion" type names
                bare_path = path.split(".")[0].rstrip("[]")
                assert bare_path not in ("accordion", "tab", "message"), (
                    f"UI-only field leaked into {name}: {path}"
                )


class TestPrettyPrint:
    def test_does_not_crash(self, mapping, capsys):
        pretty_print_mapping(mapping)
        captured = capsys.readouterr()
        assert "BasicContent" in captured.out
        assert "heading.text" in captured.out
        assert "Total Layouts:" in captured.out
