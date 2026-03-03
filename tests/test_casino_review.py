"""Tests for the casino review field mapping and page template."""

import json
from pathlib import Path

import pytest

from acf.mapping_loader import load_mapping
from templates.loader import load_page_template, LLM_GENERATE
from templates.renderer import render_page_template
from templates.validator import validate_page_template


REVIEW_MAPPING_PATH = (
    Path(__file__).parent.parent
    / "config"
    / "field_mappings"
    / "sunvegascasino_casino_review.json"
)

FULL_MAPPING_PATH = (
    Path(__file__).parent.parent
    / "config"
    / "field_mappings"
    / "sunvegascasino.json"
)

REFERENCE_PATH = (
    Path(__file__).parent.parent / "acf-layouts-reference.md"
)


@pytest.fixture(scope="session")
def review_mapping():
    return load_mapping(REVIEW_MAPPING_PATH)


@pytest.fixture(scope="session")
def full_mapping():
    return load_mapping(FULL_MAPPING_PATH)


@pytest.fixture(scope="session")
def casino_review_template():
    return load_page_template("casino_review")


# ---------------------------------------------------------------------------
# Field mapping tests
# ---------------------------------------------------------------------------


class TestCasinoReviewMapping:
    def test_loads_successfully(self, review_mapping):
        assert review_mapping.flexible_content_key == "field_61042266f0b46"

    def test_has_exactly_eight_layouts(self, review_mapping):
        assert len(review_mapping.layouts) == 8

    def test_expected_layouts_present(self, review_mapping):
        expected = [
            "ProsAndCons",
            "MediaCarousel",
            "ExpandableCards",
            "BasicContent",
            "TrustBadgeSection",
            "RelatedCasinos",
            "UserReviewsFreeText",
            "AllReviewsInterlink",
        ]
        for layout in expected:
            assert review_mapping.has_layout(layout), f"Missing layout: {layout}"

    def test_layout_keys_match_reference(self, review_mapping):
        expected_keys = {
            "ProsAndCons": "layout_62f141f7b73c7",
            "MediaCarousel": "layout_64de4aea6942d",
            "ExpandableCards": "layout_63207c6dd5c1a",
            "BasicContent": "layout_6104226d4285a",
            "TrustBadgeSection": "layout_63989e476456b",
            "RelatedCasinos": "layout_655c98ba8c8c0",
            "UserReviewsFreeText": "layout_66adf454b0ef6",
            "AllReviewsInterlink": "layout_655a1bd924b45",
        }
        for layout_name, expected_key in expected_keys.items():
            assert review_mapping.get_layout_key(layout_name) == expected_key

    def test_fields_match_full_mapping(self, review_mapping, full_mapping):
        """Every layout and field key in the review mapping must match the
        full sunvegascasino.json source exactly."""
        for layout_name in review_mapping.list_layouts():
            review_fields = review_mapping.get_layout_fields(layout_name)
            full_fields = full_mapping.get_layout_fields(layout_name)
            assert review_fields == full_fields, (
                f"{layout_name} fields differ from full mapping"
            )

    def test_flexible_content_key_matches_full(self, review_mapping, full_mapping):
        assert (
            review_mapping.flexible_content_key == full_mapping.flexible_content_key
        )

    def test_pros_and_cons_has_repeater_fields(self, review_mapping):
        fields = review_mapping.get_layout_fields("ProsAndCons")
        assert "pros[]" in fields
        assert "cons[]" in fields
        assert "pro" in fields["pros[]"]
        assert "con" in fields["cons[]"]

    def test_expandable_cards_has_cards_repeater(self, review_mapping):
        fields = review_mapping.get_layout_fields("ExpandableCards")
        assert "cards[]" in fields
        cards = fields["cards[]"]
        for sub_field in ["url", "icon", "title", "subtitle", "content_excerpt", "content"]:
            assert sub_field in cards, f"Missing cards sub-field: {sub_field}"

    def test_media_carousel_has_media_repeater(self, review_mapping):
        fields = review_mapping.get_layout_fields("MediaCarousel")
        assert "media[]" in fields
        assert "image" in fields["media[]"]
        assert "link" in fields["media[]"]

    def test_trust_badge_has_title_fields(self, review_mapping):
        fields = review_mapping.get_layout_fields("TrustBadgeSection")
        assert "title.heading" in fields
        assert "title.text" in fields
        assert "content" in fields
        assert "badge" in fields
        assert "variant" in fields

    def test_user_reviews_free_text_has_section_fields_only(self, review_mapping):
        fields = review_mapping.get_layout_fields("UserReviewsFreeText")
        assert "section_id" in fields
        assert "background_color" in fields
        # Should not have heading or content fields
        assert "heading.text" not in fields
        assert "content" not in fields

    def test_all_reviews_interlink_has_heading(self, review_mapping):
        fields = review_mapping.get_layout_fields("AllReviewsInterlink")
        assert "heading.text" in fields
        assert "heading.level" in fields

    def test_related_casinos_has_cta_fields(self, review_mapping):
        fields = review_mapping.get_layout_fields("RelatedCasinos")
        assert "content_above" in fields
        assert "cta_button_text" in fields
        assert "cta_button_url" in fields

    def test_json_is_valid(self):
        """Sanity check that the file is valid JSON."""
        with open(REVIEW_MAPPING_PATH) as f:
            data = json.load(f)
        assert "flexible_content_key" in data
        assert "layouts" in data


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


class TestCasinoReviewTemplate:
    def test_loads_successfully(self, casino_review_template):
        assert casino_review_template["name"] == "Casino Review Page"

    def test_has_14_sections(self, casino_review_template):
        assert len(casino_review_template["sections"]) == 14

    def test_has_required_variables(self, casino_review_template):
        variables = casino_review_template["variables"]
        assert "brand_name" in variables
        assert "brand_slug" in variables
        assert "target_keywords" in variables

    def test_all_sections_have_layout_and_fields(self, casino_review_template):
        for i, section in enumerate(casino_review_template["sections"]):
            assert "layout" in section, f"Section {i}: missing 'layout'"
            assert "fields" in section, f"Section {i}: missing 'fields'"

    def test_section_layout_order(self, casino_review_template):
        layouts = [s["layout"] for s in casino_review_template["sections"]]
        assert layouts == [
            "ProsAndCons",          # 1
            "MediaCarousel",        # 2
            "ExpandableCards",      # 3
            "ExpandableCards",      # 4
            "MediaCarousel",        # 5
            "ExpandableCards",      # 6
            "BasicContent",         # 7
            "TrustBadgeSection",    # 8
            "ProsAndCons",          # 9
            "BasicContent",         # 10
            "RelatedCasinos",       # 11
            "BasicContent",         # 12
            "UserReviewsFreeText",  # 13
            "AllReviewsInterlink",  # 14
        ]

    def test_validates_against_mapping(self, casino_review_template, review_mapping):
        warnings = validate_page_template(casino_review_template, review_mapping)
        assert warnings == [], f"Validation warnings: {warnings}"

    def test_validates_against_full_mapping(self, casino_review_template, full_mapping):
        """Template should also validate against the full site mapping."""
        warnings = validate_page_template(casino_review_template, full_mapping)
        assert warnings == [], f"Validation warnings: {warnings}"


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------


class TestCasinoReviewRenderer:
    VARIABLES = {
        "brand_name": "Sun Vegas Casino",
        "brand_slug": "sun-vegas-casino",
        "target_keywords": "sun vegas review, sun vegas casino bonus",
    }

    def test_renders_all_14_sections(self, casino_review_template):
        rendered = render_page_template(casino_review_template, self.VARIABLES)
        assert len(rendered) == 14

    def test_acf_fc_layout_set_correctly(self, casino_review_template):
        rendered = render_page_template(casino_review_template, self.VARIABLES)
        assert rendered[0]["acf_fc_layout"] == "ProsAndCons"
        assert rendered[1]["acf_fc_layout"] == "MediaCarousel"
        assert rendered[6]["acf_fc_layout"] == "BasicContent"
        assert rendered[7]["acf_fc_layout"] == "TrustBadgeSection"
        assert rendered[10]["acf_fc_layout"] == "RelatedCasinos"
        assert rendered[12]["acf_fc_layout"] == "UserReviewsFreeText"
        assert rendered[13]["acf_fc_layout"] == "AllReviewsInterlink"

    def test_variable_substitution_in_headings(self, casino_review_template):
        rendered = render_page_template(casino_review_template, self.VARIABLES)

        # Section 3: Expandable Cards heading
        assert rendered[2]["fields"]["heading"]["text"] == "Sun Vegas Casino Bonuses and Promotions"
        # Section 7: BasicContent heading
        assert rendered[6]["fields"]["heading"]["text"] == "Sun Vegas Casino Mobile Compatibility"
        # Section 8: TrustBadge title
        assert rendered[7]["fields"]["title"]["heading"] == "Is Sun Vegas Casino Safe?"

    def test_variable_substitution_in_llm_context(self, casino_review_template):
        rendered = render_page_template(casino_review_template, self.VARIABLES)
        assert "Sun Vegas Casino" in rendered[0]["llm_context"]
        assert "sun vegas review" in rendered[0]["llm_context"]

    def test_llm_generate_markers_preserved(self, casino_review_template):
        rendered = render_page_template(casino_review_template, self.VARIABLES)

        # Section 1 (ProsAndCons): content, pros, cons
        assert rendered[0]["fields"]["content"] == LLM_GENERATE
        assert rendered[0]["fields"]["pros"] == LLM_GENERATE
        assert rendered[0]["fields"]["cons"] == LLM_GENERATE

    def test_llm_fields_identified(self, casino_review_template):
        rendered = render_page_template(casino_review_template, self.VARIABLES)

        # Section 1: content, pros, cons
        assert "content" in rendered[0]["llm_fields"]
        assert "pros" in rendered[0]["llm_fields"]
        assert "cons" in rendered[0]["llm_fields"]

        # Section 2: description_above
        assert "description_above" in rendered[1]["llm_fields"]

        # Section 7: BasicContent content
        assert "content" in rendered[6]["llm_fields"]

    def test_sections_without_llm_fields(self, casino_review_template):
        rendered = render_page_template(casino_review_template, self.VARIABLES)

        # Section 13: UserReviewsFreeText has no LLM fields
        assert rendered[12]["llm_fields"] == []
        # Section 14: AllReviewsInterlink has no LLM fields
        assert rendered[13]["llm_fields"] == []

    def test_missing_required_variable_raises(self, casino_review_template):
        incomplete_vars = {"brand_name": "Test Casino"}
        with pytest.raises(ValueError, match="Missing required variables"):
            render_page_template(casino_review_template, incomplete_vars)

    def test_purpose_preserved(self, casino_review_template):
        rendered = render_page_template(casino_review_template, self.VARIABLES)
        assert "pros and cons" in rendered[0]["purpose"].lower()
        assert "bonuses" in rendered[2]["purpose"].lower()
        assert "mobile" in rendered[6]["purpose"].lower()


# ---------------------------------------------------------------------------
# Cross-validation: field keys match reference document
# ---------------------------------------------------------------------------


class TestFieldKeysMatchReference:
    """Verify that specific ACF field keys in the mapping match the
    acf-layouts-reference.md document exactly."""

    def test_pros_and_cons_heading_text(self, review_mapping):
        fields = review_mapping.get_layout_fields("ProsAndCons")
        assert fields["heading.text"] == "field_62f1420eb73c9_field_62f65a1c03db8_field_6104217816977"

    def test_pros_and_cons_content(self, review_mapping):
        fields = review_mapping.get_layout_fields("ProsAndCons")
        assert fields["content"] == "field_62f1420eb73c9_field_62f140836e2f4"

    def test_media_carousel_description_above(self, review_mapping):
        fields = review_mapping.get_layout_fields("MediaCarousel")
        assert fields["description_above"] == "field_64de4b016942e_field_64de4a3c9853f"

    def test_media_carousel_media_image(self, review_mapping):
        fields = review_mapping.get_layout_fields("MediaCarousel")
        assert fields["media[]"]["image"] == "field_64de4b016942e_field_64de4a7d98542"

    def test_expandable_cards_cards_title(self, review_mapping):
        fields = review_mapping.get_layout_fields("ExpandableCards")
        assert fields["cards[]"]["title"] == "field_63207c75d5c1b_field_630cf16577732"

    def test_basic_content_content(self, review_mapping):
        fields = review_mapping.get_layout_fields("BasicContent")
        assert fields["content"] == "field_6104227ef0b47_field_611e64259a296"

    def test_trust_badge_content(self, review_mapping):
        fields = review_mapping.get_layout_fields("TrustBadgeSection")
        assert fields["content"] == "field_63989efd6456c_field_63989d840cfeb"

    def test_trust_badge_badge(self, review_mapping):
        fields = review_mapping.get_layout_fields("TrustBadgeSection")
        assert fields["badge"] == "field_63989efd6456c_field_63989d6d985c3"

    def test_related_casinos_cta_button_text(self, review_mapping):
        fields = review_mapping.get_layout_fields("RelatedCasinos")
        assert fields["cta_button_text"] == "field_655c98c98c8c1_field_65f43a04b8223"

    def test_all_reviews_interlink_heading_text(self, review_mapping):
        fields = review_mapping.get_layout_fields("AllReviewsInterlink")
        assert fields["heading.text"] == "field_655a1c0124b46_field_655a1b24fafc7_field_6104217816977"

    def test_user_reviews_free_text_section_id(self, review_mapping):
        fields = review_mapping.get_layout_fields("UserReviewsFreeText")
        assert fields["section_id"] == "field_66adf460b0ef9_field_66adf4eaed2fd_field_607dbe7d30c4e"
