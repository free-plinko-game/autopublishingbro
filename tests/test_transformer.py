"""Tests for the ACF transformer module."""

from pathlib import Path

import pytest

from acf.mapping_loader import load_mapping, FieldMapping
from acf.defaults import apply_defaults, get_defaults_for_layout, _deep_merge
from acf.transformer import transform_to_acf, transform_section, validate_sections

MAPPING_PATH = Path(__file__).parent.parent / "config" / "field_mappings" / "sunvegascasino.json"


@pytest.fixture(scope="session")
def mapping():
    return load_mapping(MAPPING_PATH)


# --- Mapping loader tests ---


class TestMappingLoader:
    def test_loads_mapping(self, mapping):
        assert mapping.flexible_content_key == "field_61042266f0b46"
        assert len(mapping.layouts) >= 37

    def test_get_layout(self, mapping):
        bc = mapping.get_layout("BasicContent")
        assert bc is not None
        assert "layout_key" in bc
        assert "fields" in bc

    def test_get_layout_fields(self, mapping):
        fields = mapping.get_layout_fields("BasicContent")
        assert "heading.text" in fields
        assert "content" in fields

    def test_get_layout_key(self, mapping):
        key = mapping.get_layout_key("BasicContent")
        assert key == "layout_6104226d4285a"

    def test_unknown_layout_returns_none(self, mapping):
        assert mapping.get_layout("NonExistent") is None
        assert mapping.get_layout_fields("NonExistent") == {}

    def test_list_layouts(self, mapping):
        layouts = mapping.list_layouts()
        assert "BasicContent" in layouts
        assert "GamblingOperators" in layouts
        assert layouts == sorted(layouts)

    def test_has_layout(self, mapping):
        assert mapping.has_layout("BasicContent")
        assert not mapping.has_layout("FakeLayout")


# --- Defaults tests ---


class TestDefaults:
    def test_common_defaults_applied(self, mapping):
        fields = mapping.get_layout_fields("BasicContent")
        defaults = get_defaults_for_layout(fields)

        assert defaults["section_id"] == ""
        assert defaults["padding_override"] == "reduced-padding"
        assert defaults["section_width"] == "narrow"
        assert defaults["toc_exclude"] is False

    def test_heading_defaults_applied(self, mapping):
        fields = mapping.get_layout_fields("BasicContent")
        defaults = get_defaults_for_layout(fields)

        assert defaults["heading"]["text"] == ""
        assert defaults["heading"]["level"] == "h2"
        assert defaults["heading"]["alignment"]["desktop"] == "inherit"
        assert defaults["heading"]["alignment"]["mobile"] == "inherit"

    def test_read_more_defaults_for_operators(self, mapping):
        fields = mapping.get_layout_fields("GamblingOperators")
        defaults = get_defaults_for_layout(fields)

        assert "read_more_text" in defaults
        assert defaults["read_more_mobile_only"] is False

    def test_no_heading_defaults_for_layout_without_heading(self, mapping):
        fields = mapping.get_layout_fields("PostInfoHeader")
        defaults = get_defaults_for_layout(fields)
        assert "heading" not in defaults

    def test_apply_defaults_preserves_user_values(self, mapping):
        fields = mapping.get_layout_fields("BasicContent")
        section = {
            "heading": {"text": "My Title", "level": "h1"},
            "content": "<p>Hello</p>",
        }
        result = apply_defaults(section, fields)

        # User values preserved
        assert result["heading"]["text"] == "My Title"
        assert result["heading"]["level"] == "h1"
        assert result["content"] == "<p>Hello</p>"

        # Defaults filled in
        assert result["heading"]["alignment"]["desktop"] == "inherit"
        assert result["section_id"] == ""
        assert result["padding_override"] == "reduced-padding"

    def test_apply_defaults_partial_heading_override(self, mapping):
        fields = mapping.get_layout_fields("BasicContent")
        section = {
            "heading": {"text": "Title Only"},
        }
        result = apply_defaults(section, fields)

        assert result["heading"]["text"] == "Title Only"
        assert result["heading"]["level"] == "h2"  # default
        assert result["heading"]["alignment"]["desktop"] == "inherit"  # default

    def test_deep_merge_override_wins(self):
        base = {"a": 1, "b": {"c": 2, "d": 3}}
        override = {"a": 10, "b": {"c": 20}}
        result = _deep_merge(base, override)

        assert result["a"] == 10
        assert result["b"]["c"] == 20
        assert result["b"]["d"] == 3  # preserved from base

    def test_deep_merge_does_not_mutate(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        result = _deep_merge(base, override)

        assert "c" not in base["a"]  # base unmodified
        assert result["a"]["b"] == 1
        assert result["a"]["c"] == 2


# --- Transformer tests ---


class TestTransformSection:
    def test_basic_content_transform(self, mapping):
        section = {
            "acf_fc_layout": "BasicContent",
            "heading": {
                "text": "Welcome to Pokies",
                "level": "h2",
            },
            "content": "<p>Some HTML here</p>",
        }
        result = transform_section(section, mapping)

        assert result["acf_fc_layout"] == "BasicContent"
        # Nested heading fields flattened to clone-prefixed field keys
        assert result["field_6104227ef0b47_field_611e64259a1e0_field_6104217816977"] == "Welcome to Pokies"  # heading.text
        assert result["field_6104227ef0b47_field_611e64259a1e0_field_6104217f16978"] == "h2"  # heading.level
        assert result["field_6104227ef0b47_field_611e64259a1e0_field_611278c0063b5"] == "inherit"  # heading.alignment.desktop
        assert result["field_6104227ef0b47_field_611e64259a1e0_field_611278ea063b6"] == "inherit"  # heading.alignment.mobile
        assert result["field_6104227ef0b47_field_611e64259a296"] == "<p>Some HTML here</p>"  # content
        assert result["field_6104227ef0b47_field_611e64259a124_field_607dbe7d30c4e"] == ""  # section_id
        assert result["field_6104227ef0b47_field_611e64259a124_field_604fb9aff2bef"] == "reduced-padding"  # padding_override

    def test_gambling_operators_transform(self, mapping):
        section = {
            "acf_fc_layout": "GamblingOperators",
            "heading": {
                "text": "Best Casinos",
                "level": "h2",
            },
            "shortcode": '[cta_list id="123"]',
            "content_above": "<p>Check these out</p>",
        }
        result = transform_section(section, mapping)

        assert result["field_6127c311a1955_field_6120037c1998c"] == '[cta_list id="123"]'  # shortcode
        assert result["field_6127c311a1955_field_6120051e89b55"] == "<p>Check these out</p>"  # content_above
        assert result["field_6127c311a1955_field_612003651998a_field_611278ea063b6"] == "inherit"  # heading.alignment.mobile

    def test_section_with_repeater(self, mapping):
        section = {
            "acf_fc_layout": "AccordionSection",
            "heading": {"text": "FAQ", "level": "h2"},
            "accordions": [
                {"title": "Question 1", "content": "Answer 1"},
                {"title": "Question 2", "content": "Answer 2"},
            ],
        }
        result = transform_section(section, mapping)

        # Repeater sub-field names converted to clone-prefixed field keys
        assert result["accordions"] == [
            {"field_635beb487caf7_field_635c161a2cd0c": "Question 1", "field_635beb487caf7_field_635c16282cd0d": "Answer 1"},
            {"field_635beb487caf7_field_635c161a2cd0c": "Question 2", "field_635beb487caf7_field_635c16282cd0d": "Answer 2"},
        ]
        assert result["field_635beb487caf7_field_635be5159bd1c_field_6104217816977"] == "FAQ"  # heading.text


class TestTransformToAcf:
    def test_full_payload_structure(self, mapping):
        sections = [
            {
                "acf_fc_layout": "BasicContent",
                "heading": {"text": "Intro", "level": "h1"},
                "content": "<p>Welcome</p>",
            },
            {
                "acf_fc_layout": "GamblingOperators",
                "heading": {"text": "Top Casinos", "level": "h2"},
                "shortcode": '[cta_list id="456"]',
                "content_above": "<p>Our picks</p>",
            },
        ]
        result = transform_to_acf(sections, mapping)

        fc_key = mapping.flexible_content_key
        assert "acf" in result
        assert fc_key in result["acf"]
        assert len(result["acf"][fc_key]) == 2

        first = result["acf"][fc_key][0]
        assert first["acf_fc_layout"] == "BasicContent"
        assert first["field_6104227ef0b47_field_611e64259a1e0_field_6104217816977"] == "Intro"  # heading.text

        second = result["acf"][fc_key][1]
        assert second["acf_fc_layout"] == "GamblingOperators"
        assert second["field_6127c311a1955_field_6120037c1998c"] == '[cta_list id="456"]'  # shortcode

    def test_skips_sections_without_layout(self, mapping):
        sections = [
            {"content": "no layout specified"},
            {"acf_fc_layout": "BasicContent", "content": "<p>Valid</p>"},
        ]
        result = transform_to_acf(sections, mapping)
        fc_key = mapping.flexible_content_key
        assert len(result["acf"][fc_key]) == 1

    def test_skips_unknown_layouts(self, mapping):
        sections = [
            {"acf_fc_layout": "FakeLayout", "content": "nope"},
            {"acf_fc_layout": "BasicContent", "content": "<p>Real</p>"},
        ]
        result = transform_to_acf(sections, mapping)
        fc_key = mapping.flexible_content_key
        assert len(result["acf"][fc_key]) == 1

    def test_empty_sections_list(self, mapping):
        result = transform_to_acf([], mapping)
        fc_key = mapping.flexible_content_key
        assert result["acf"][fc_key] == []


# --- Validation tests ---


class TestValidation:
    def test_valid_sections_no_warnings(self, mapping):
        sections = [
            {
                "acf_fc_layout": "BasicContent",
                "heading": {"text": "Hello", "level": "h2"},
                "content": "<p>World</p>",
            },
        ]
        warnings = validate_sections(sections, mapping)
        assert warnings == []

    def test_missing_layout_warning(self, mapping):
        sections = [{"content": "no layout"}]
        warnings = validate_sections(sections, mapping)
        assert any("missing acf_fc_layout" in w for w in warnings)

    def test_unknown_layout_warning(self, mapping):
        sections = [{"acf_fc_layout": "Nonexistent"}]
        warnings = validate_sections(sections, mapping)
        assert any("unknown layout" in w for w in warnings)

    def test_unknown_field_warning(self, mapping):
        sections = [
            {
                "acf_fc_layout": "BasicContent",
                "heading": {"text": "Hi"},
                "totally_fake_field": "value",
            },
        ]
        warnings = validate_sections(sections, mapping)
        assert any("totally_fake_field" in w for w in warnings)
