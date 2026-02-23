"""Tests for the templates system — loader, renderer, and validator."""

from pathlib import Path

import pytest

from acf.mapping_loader import load_mapping
from templates.loader import (
    load_page_template,
    load_base_template,
    list_page_templates,
    list_base_templates,
    LLM_GENERATE,
)
from templates.renderer import render_page_template, _find_llm_fields
from templates.validator import (
    validate_page_template,
    validate_base_template,
)

MAPPING_PATH = Path(__file__).parent.parent / "config" / "field_mappings" / "sunvegascasino.json"


@pytest.fixture(scope="session")
def mapping():
    return load_mapping(MAPPING_PATH)


@pytest.fixture(scope="session")
def pokies_template():
    return load_page_template("pokies_category")


@pytest.fixture(scope="session")
def basic_content_base():
    return load_base_template("BasicContent")


# --- Loader tests ---


class TestLoader:
    def test_load_page_template(self, pokies_template):
        assert pokies_template["name"] == "Pokies Category Page"
        assert "sections" in pokies_template
        assert len(pokies_template["sections"]) == 6

    def test_page_template_has_variables(self, pokies_template):
        variables = pokies_template["variables"]
        assert "category_name" in variables
        assert "category_slug" in variables
        assert "target_keywords" in variables
        assert "cta_list_id" in variables

    def test_page_template_sections_have_layout(self, pokies_template):
        for section in pokies_template["sections"]:
            assert "layout" in section
            assert "fields" in section

    def test_page_template_section_layouts(self, pokies_template):
        layouts = [s["layout"] for s in pokies_template["sections"]]
        assert layouts == [
            "BasicContent",
            "GamblingOperators",
            "BasicContent",
            "AllSlotsInterlink",
            "BasicContent",
            "BasicContent",
        ]

    def test_load_base_template(self, basic_content_base):
        assert basic_content_base["layout"] == "BasicContent"
        assert "fields" in basic_content_base
        assert "heading" in basic_content_base["fields"]
        assert "content" in basic_content_base["fields"]

    def test_base_template_llm_generate_markers(self, basic_content_base):
        content_field = basic_content_base["fields"]["content"]
        assert content_field.get("llm_generate") is True

    def test_load_missing_template_raises(self):
        with pytest.raises(FileNotFoundError):
            load_page_template("nonexistent_template")

    @pytest.mark.parametrize("bad_name", [
        "../../etc/passwd",
        "../secrets",
        "foo/bar",
        "template.yaml",
        "hello world",
        "",
    ])
    def test_path_traversal_rejected(self, bad_name):
        with pytest.raises(ValueError, match="Invalid template name"):
            load_page_template(bad_name)

    def test_valid_template_names_accepted(self):
        """Sanity check that the regex allows legit names."""
        # These should not raise ValueError (may raise FileNotFoundError)
        for name in ["pokies_category", "my-template", "Template01"]:
            try:
                load_page_template(name)
            except FileNotFoundError:
                pass  # expected for non-existent but validly-named templates

    def test_load_missing_base_raises(self):
        with pytest.raises(FileNotFoundError):
            load_base_template("NonexistentLayout")

    def test_list_page_templates(self):
        templates = list_page_templates()
        names = [t["name"] for t in templates]
        assert "pokies_category" in names

    def test_list_page_templates_metadata(self):
        templates = list_page_templates()
        pokies = next(t for t in templates if t["name"] == "pokies_category")
        assert pokies["display_name"] == "Pokies Category Page"
        assert "category_name" in pokies["variables"]

    def test_list_base_templates(self):
        bases = list_base_templates()
        assert "BasicContent" in bases
        assert "GamblingOperators" in bases
        assert "AccordionSection" in bases
        assert "AllSlotsInterlink" in bases


# --- Renderer tests ---


class TestRenderer:
    VARIABLES = {
        "category_name": "Single-Reel Pokies",
        "category_slug": "single-reel-pokies",
        "target_keywords": "classic pokies, 3-reel slots, retro pokies",
        "cta_list_id": "123",
    }

    def test_renders_all_sections(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)
        assert len(rendered) == 6

    def test_section_has_acf_fc_layout(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)
        assert rendered[0]["acf_fc_layout"] == "BasicContent"
        assert rendered[1]["acf_fc_layout"] == "GamblingOperators"

    def test_variable_substitution_in_fields(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)

        # Section 0: intro heading should have category name
        intro = rendered[0]
        assert intro["fields"]["heading"]["text"] == "Single-Reel Pokies"

    def test_variable_substitution_in_shortcode(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)

        # Section 1: GamblingOperators shortcode
        operators = rendered[1]
        assert operators["fields"]["shortcode"] == '[cta_list id="123"]'

    def test_variable_substitution_in_llm_context(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)

        intro = rendered[0]
        assert "Single-Reel Pokies" in intro["llm_context"]
        assert "classic pokies" in intro["llm_context"]

    def test_llm_generate_markers_preserved(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)

        intro = rendered[0]
        assert intro["fields"]["content"] == LLM_GENERATE

    def test_llm_fields_identified(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)

        # Section 0: content should be LLM-generated
        intro = rendered[0]
        assert "content" in intro["llm_fields"]

        # Section 1: content_above should be LLM-generated
        operators = rendered[1]
        assert "content_above" in operators["llm_fields"]

    def test_section_without_llm_fields(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)

        # Section 3: AllSlotsInterlink has no LLM fields
        interlink = rendered[3]
        assert interlink["llm_fields"] == []

    def test_purpose_preserved(self, pokies_template):
        rendered = render_page_template(pokies_template, self.VARIABLES)
        assert rendered[0]["purpose"] != ""
        assert "Introduction" in rendered[0]["purpose"]

    def test_missing_required_variable_raises(self, pokies_template):
        incomplete_vars = {"category_name": "Test"}  # missing others
        with pytest.raises(ValueError, match="Missing required variables"):
            render_page_template(pokies_template, incomplete_vars)

    def test_find_llm_fields_nested(self):
        fields = {
            "heading": {
                "text": "fixed",
                "level": "h2",
            },
            "content": LLM_GENERATE,
        }
        result = _find_llm_fields(fields)
        assert result == ["content"]

    def test_find_llm_fields_empty(self):
        fields = {"heading": {"text": "fixed"}, "shortcode": "[cta]"}
        result = _find_llm_fields(fields)
        assert result == []


# --- Validator tests ---


class TestValidator:
    def test_pokies_template_valid(self, pokies_template, mapping):
        warnings = validate_page_template(pokies_template, mapping)
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_base_template_basic_content_valid(self, basic_content_base, mapping):
        warnings = validate_base_template(basic_content_base, mapping)
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_base_template_gambling_operators_valid(self, mapping):
        base = load_base_template("GamblingOperators")
        warnings = validate_base_template(base, mapping)
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_base_template_accordion_valid(self, mapping):
        base = load_base_template("AccordionSection")
        warnings = validate_base_template(base, mapping)
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_base_template_all_slots_valid(self, mapping):
        base = load_base_template("AllSlotsInterlink")
        warnings = validate_base_template(base, mapping)
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_invalid_layout_warns(self, mapping):
        bad_template = {
            "sections": [
                {"layout": "FakeLayout", "fields": {"content": "test"}}
            ]
        }
        warnings = validate_page_template(bad_template, mapping)
        assert any("not found in mapping" in w for w in warnings)

    def test_invalid_field_warns(self, mapping):
        bad_template = {
            "sections": [
                {
                    "layout": "BasicContent",
                    "fields": {"totally_fake_field": "value"},
                }
            ]
        }
        warnings = validate_page_template(bad_template, mapping)
        assert any("totally_fake_field" in w for w in warnings)

    def test_invalid_base_layout_warns(self, mapping):
        bad_base = {"layout": "FakeLayout", "fields": {"x": "y"}}
        warnings = validate_base_template(bad_base, mapping)
        assert any("not found in mapping" in w for w in warnings)
