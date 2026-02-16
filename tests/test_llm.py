"""Tests for the LLM content generation system."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from llm.client import LLMClient, LLMConfig, LLMError
from llm.prompts import (
    SYSTEM_PROMPT,
    build_section_prompt,
    build_repeater_prompt,
    _describe_existing_fields,
)
from llm.generator import (
    generate_page_content,
    generate_single_section,
    _get_field_instruction,
    _get_field_type,
    _set_nested_value,
    _walk_base_template,
)
from utils.html_sanitizer import sanitize_html, strip_html
from templates.loader import load_page_template, load_base_template, LLM_GENERATE
from templates.renderer import render_page_template


# --- Mock LLM Client ---


class MockLLMClient:
    """Drop-in replacement for LLMClient that returns canned responses."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []
        self._default = "<p>This is mock generated content for testing.</p>"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        })
        # Return a matching response if the prompt contains a known key
        for key, response in self.responses.items():
            if key in user_prompt:
                return response
        return self._default


# --- HTML Sanitizer Tests ---


class TestHTMLSanitizer:
    def test_strips_markdown_fences(self):
        html = '```html\n<p>Hello</p>\n```'
        assert sanitize_html(html) == "<p>Hello</p>"

    def test_strips_wrapper_tags(self):
        html = "<html><body><p>Content</p></body></html>"
        assert sanitize_html(html) == "<p>Content</p>"

    def test_strips_div_and_span(self):
        html = '<div class="wrapper"><span>Text</span></div>'
        assert sanitize_html(html) == "Text"

    def test_preserves_allowed_tags(self):
        html = "<p>Hello <strong>world</strong></p>"
        assert sanitize_html(html) == "<p>Hello <strong>world</strong></p>"

    def test_preserves_links(self):
        html = '<p><a href="https://example.com" title="Ex">Link</a></p>'
        result = sanitize_html(html)
        assert 'href="https://example.com"' in result
        assert 'title="Ex"' in result

    def test_strips_inline_styles(self):
        html = '<p style="color: red;">Text</p>'
        result = sanitize_html(html)
        assert "style" not in result
        assert "<p>" in result

    def test_strips_class_attributes(self):
        html = '<p class="intro">Text</p>'
        result = sanitize_html(html)
        assert "class" not in result

    def test_preserves_lists(self):
        html = "<ul><li>One</li><li>Two</li></ul>"
        assert sanitize_html(html) == html

    def test_preserves_headings(self):
        html = "<h2>Title</h2><p>Body</p>"
        assert sanitize_html(html) == html

    def test_strips_script_tags(self):
        html = "<p>Safe</p><script>alert('xss')</script>"
        result = sanitize_html(html)
        assert "<script>" not in result
        assert "alert" not in result

    def test_empty_input(self):
        assert sanitize_html("") == ""

    def test_plain_text_passthrough(self):
        assert sanitize_html("Just text") == "Just text"

    def test_strip_html_returns_plain_text(self):
        html = "<p>Hello <strong>world</strong></p>"
        assert strip_html(html) == "Hello world"

    def test_strip_html_empty(self):
        assert strip_html("") == ""


# --- Prompts Tests ---


class TestPrompts:
    def test_system_prompt_exists(self):
        assert len(SYSTEM_PROMPT) > 100
        assert "Australian" in SYSTEM_PROMPT
        assert "HTML" in SYSTEM_PROMPT

    def test_build_section_prompt_basic(self):
        section = {
            "acf_fc_layout": "BasicContent",
            "purpose": "Introduction to pokies",
            "llm_context": "Write about Single-Reel Pokies.",
            "fields": {
                "heading": {"text": "Single-Reel Pokies", "level": "h1"},
                "content": LLM_GENERATE,
            },
        }
        prompt = build_section_prompt(
            section=section,
            field_path="content",
            field_instruction="Write 150-300 words of engaging content.",
        )

        assert "Introduction to pokies" in prompt
        assert "Single-Reel Pokies" in prompt
        assert "Write about Single-Reel Pokies" in prompt
        assert "150-300 words" in prompt
        assert "'content'" in prompt

    def test_build_section_prompt_with_page_context(self):
        section = {
            "acf_fc_layout": "BasicContent",
            "purpose": "Test",
            "llm_context": "",
            "fields": {"content": LLM_GENERATE},
        }
        prompt = build_section_prompt(
            section=section,
            field_path="content",
            field_instruction="",
            page_context={"category_name": "Megaways Pokies"},
        )

        assert "Megaways Pokies" in prompt

    def test_build_section_prompt_shows_existing_fields(self):
        section = {
            "acf_fc_layout": "GamblingOperators",
            "purpose": "Casino table",
            "llm_context": "",
            "fields": {
                "heading": {"text": "Best Casinos"},
                "shortcode": '[cta_list id="123"]',
                "content_above": LLM_GENERATE,
            },
        }
        prompt = build_section_prompt(
            section=section,
            field_path="content_above",
            field_instruction="Write intro for table",
        )

        assert "Best Casinos" in prompt
        assert "cta_list" in prompt

    def test_describe_existing_fields_excludes_target(self):
        fields = {
            "heading": {"text": "Title"},
            "content": LLM_GENERATE,
        }
        result = _describe_existing_fields(fields, "content")
        assert "Title" in result
        assert LLM_GENERATE not in result

    def test_build_repeater_prompt(self):
        section = {
            "acf_fc_layout": "AccordionSection",
            "purpose": "FAQ section",
            "llm_context": "Write FAQs about pokies.",
            "fields": {},
        }
        prompt = build_repeater_prompt(
            section=section,
            field_path="accordions",
            field_instruction="Generate 5-8 items",
            sub_field_descriptions={"title": "Question", "content": "Answer"},
        )

        assert "FAQ section" in prompt
        assert "title" in prompt
        assert "content" in prompt
        assert "---ITEM---" in prompt


# --- Generator Tests (with mocked LLM) ---


class TestGenerator:
    VARIABLES = {
        "category_name": "Single-Reel Pokies",
        "category_slug": "single-reel-pokies",
        "target_keywords": "classic pokies, 3-reel slots",
        "cta_list_id": "123",
    }

    @pytest.fixture
    def mock_client(self):
        return MockLLMClient(responses={
            "'content'": "<p>Generated content about pokies.</p>",
            "'content_above'": "<p>These casinos are great for pokies.</p>",
        })

    @pytest.fixture
    def rendered_sections(self):
        template = load_page_template("pokies_category")
        return render_page_template(template, self.VARIABLES)

    def test_generates_content_for_llm_fields(self, rendered_sections, mock_client):
        result = generate_page_content(
            rendered_sections, mock_client, self.VARIABLES
        )

        # All 6 sections should be returned
        assert len(result) == 6

        # Section 0 (intro) should have generated content, not the marker
        intro = result[0]
        assert intro["fields"]["content"] != LLM_GENERATE
        assert "<p>" in intro["fields"]["content"]

    def test_preserves_non_llm_fields(self, rendered_sections, mock_client):
        result = generate_page_content(
            rendered_sections, mock_client, self.VARIABLES
        )

        # Section 0 heading should still be the original
        intro = result[0]
        assert intro["fields"]["heading"]["text"] == "Single-Reel Pokies"
        assert intro["fields"]["heading"]["level"] == "h1"

    def test_preserves_sections_without_llm_fields(self, rendered_sections, mock_client):
        result = generate_page_content(
            rendered_sections, mock_client, self.VARIABLES
        )

        # Section 3 (AllSlotsInterlink) has no LLM fields
        interlink = result[3]
        assert interlink["acf_fc_layout"] == "AllSlotsInterlink"

    def test_operators_shortcode_preserved(self, rendered_sections, mock_client):
        result = generate_page_content(
            rendered_sections, mock_client, self.VARIABLES
        )

        operators = result[1]
        assert operators["fields"]["shortcode"] == '[cta_list id="123"]'

    def test_llm_called_for_each_field(self, rendered_sections, mock_client):
        generate_page_content(
            rendered_sections, mock_client, self.VARIABLES
        )

        # 5 sections have LLM fields: sections 0,1,2,4,5 each have 1 content field
        assert len(mock_client.calls) == 5

    def test_system_prompt_used(self, rendered_sections, mock_client):
        generate_page_content(
            rendered_sections, mock_client, self.VARIABLES
        )

        for c in mock_client.calls:
            assert c["system_prompt"] == SYSTEM_PROMPT

    def test_output_has_acf_fc_layout(self, rendered_sections, mock_client):
        result = generate_page_content(
            rendered_sections, mock_client, self.VARIABLES
        )

        for section in result:
            assert "acf_fc_layout" in section
            assert "fields" in section

    def test_metadata_stripped_from_output(self, rendered_sections, mock_client):
        result = generate_page_content(
            rendered_sections, mock_client, self.VARIABLES
        )

        for section in result:
            assert "purpose" not in section
            assert "llm_context" not in section
            assert "llm_fields" not in section

    def test_generate_single_section(self, rendered_sections, mock_client):
        result = generate_single_section(
            rendered_sections[0], mock_client, self.VARIABLES
        )

        assert result["acf_fc_layout"] == "BasicContent"
        assert result["fields"]["content"] != LLM_GENERATE

    def test_html_sanitized_in_output(self):
        dirty_html = '```html\n<div><p>Content</p></div>\n```'
        client = MockLLMClient()
        client._default = dirty_html
        client.responses = {}  # No pattern matches, always use _default

        section = {
            "acf_fc_layout": "BasicContent",
            "fields": {"content": LLM_GENERATE, "heading": {"text": "Hi", "level": "h2"}},
            "purpose": "",
            "llm_context": "",
            "llm_fields": ["content"],
        }

        result = generate_single_section(section, client)
        # div and markdown fences should be stripped
        assert "```" not in result["fields"]["content"]
        assert "<div>" not in result["fields"]["content"]
        assert "<p>Content</p>" in result["fields"]["content"]


# --- Base template instruction extraction ---


class TestFieldInstructionExtraction:
    @pytest.fixture
    def basic_base(self):
        return load_base_template("BasicContent")

    def test_get_content_instruction(self, basic_base):
        instruction = _get_field_instruction(basic_base, "content")
        assert "engaging" in instruction.lower() or "html" in instruction.lower()

    def test_get_heading_text_instruction(self, basic_base):
        instruction = _get_field_instruction(basic_base, "heading.text")
        assert "heading" in instruction.lower()

    def test_get_content_type(self, basic_base):
        assert _get_field_type(basic_base, "content") == "wysiwyg"

    def test_get_heading_text_type(self, basic_base):
        assert _get_field_type(basic_base, "heading.text") == "text"

    def test_missing_field_returns_empty(self, basic_base):
        assert _get_field_instruction(basic_base, "nonexistent") == ""

    def test_none_base_template(self):
        assert _get_field_instruction(None, "content") == ""
        assert _get_field_type(None, "content") == "wysiwyg"


class TestSetNestedValue:
    def test_simple_path(self):
        d = {"content": "old"}
        _set_nested_value(d, "content", "new")
        assert d["content"] == "new"

    def test_nested_path(self):
        d = {"heading": {"text": "old", "level": "h2"}}
        _set_nested_value(d, "heading.text", "new")
        assert d["heading"]["text"] == "new"
        assert d["heading"]["level"] == "h2"

    def test_creates_intermediate_dicts(self):
        d = {}
        _set_nested_value(d, "heading.text", "value")
        assert d["heading"]["text"] == "value"
