"""System prompts and prompt builders for casino/pokies content generation."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are a content writer for online casino and pokies websites targeting \
Australian players.

TONE: Professional but approachable, informative, trustworthy.
AUDIENCE: Australian players looking for pokies, casino games, and gambling information.

COMPLIANCE RULES:
- Never make false or misleading claims
- Use phrases like "up to" when mentioning bonuses or payout rates
- Include responsible gambling awareness where appropriate
- Do not guarantee winnings or imply that gambling is risk-free

HTML FORMATTING RULES:
- Use semantic HTML only: <p>, <ul>, <ol>, <li>, <strong>, <em>, <h2>-<h6>, <a>
- Do NOT include <html>, <head>, <body>, <div>, or <span> tags
- Do NOT use inline styles or class attributes
- Keep paragraphs short (3-4 sentences max)
- Use bullet points for lists of features or benefits

CRITICAL: Respond ONLY with the requested content. No preamble, no explanations, \
no markdown code fences. Just the raw HTML content.\
"""


def build_section_prompt(
    section: dict[str, Any],
    field_path: str,
    field_instruction: str,
    page_context: dict[str, str] | None = None,
) -> str:
    """Build a user prompt for generating a single field's content.

    Combines the section's purpose, LLM context, field-specific instructions,
    and page-level context into a focused prompt.

    Args:
        section: Rendered section dict from the template renderer.
        field_path: Dot-notation path of the field to generate (e.g. "content").
        field_instruction: The llm_instruction from the base template for this field.
        page_context: Optional dict of page-level variables for extra context.

    Returns:
        Complete user prompt string.
    """
    parts: list[str] = []

    # Page context
    if page_context:
        context_lines = [f"  {k}: {v}" for k, v in page_context.items()]
        parts.append("PAGE CONTEXT:\n" + "\n".join(context_lines))

    # Section purpose
    purpose = section.get("purpose", "")
    if purpose:
        parts.append(f"SECTION PURPOSE: {purpose}")

    # LLM context (the detailed instructions from the page template)
    llm_context = section.get("llm_context", "")
    if llm_context:
        parts.append(f"INSTRUCTIONS:\n{llm_context.strip()}")

    # Field-specific instruction from the base template
    if field_instruction:
        parts.append(f"FIELD GUIDANCE ({field_path}):\n{field_instruction.strip()}")

    # Existing field values for context (headings, etc.)
    existing = _describe_existing_fields(section.get("fields", {}), field_path)
    if existing:
        parts.append(f"EXISTING FIELDS IN THIS SECTION:\n{existing}")

    parts.append(f"Now write the content for the '{field_path}' field:")

    return "\n\n".join(parts)


def build_repeater_prompt(
    section: dict[str, Any],
    field_path: str,
    field_instruction: str,
    sub_field_descriptions: dict[str, str],
    page_context: dict[str, str] | None = None,
) -> str:
    """Build a prompt for generating repeater field content.

    Instructs the LLM to return structured items that can be parsed
    into repeater rows.

    Args:
        section: Rendered section dict.
        field_path: The repeater field path (e.g. "accordions").
        field_instruction: Instructions for the repeater.
        sub_field_descriptions: Map of sub_field name -> description.
        page_context: Optional page-level variables.

    Returns:
        Complete user prompt string.
    """
    parts: list[str] = []

    if page_context:
        context_lines = [f"  {k}: {v}" for k, v in page_context.items()]
        parts.append("PAGE CONTEXT:\n" + "\n".join(context_lines))

    purpose = section.get("purpose", "")
    if purpose:
        parts.append(f"SECTION PURPOSE: {purpose}")

    llm_context = section.get("llm_context", "")
    if llm_context:
        parts.append(f"INSTRUCTIONS:\n{llm_context.strip()}")

    if field_instruction:
        parts.append(f"FIELD GUIDANCE ({field_path}):\n{field_instruction.strip()}")

    # Describe expected output format
    sub_desc = "\n".join(
        f"  - {name}: {desc}" for name, desc in sub_field_descriptions.items()
    )
    parts.append(
        f"OUTPUT FORMAT:\n"
        f"Return items as a numbered list. For each item provide:\n{sub_desc}\n\n"
        f"Use this exact format for each item:\n"
        f"---ITEM---\n"
        + "\n".join(f"{name}: <value>" for name in sub_field_descriptions)
        + "\n---END---"
    )

    parts.append(f"Now generate the {field_path} items:")

    return "\n\n".join(parts)


def _describe_existing_fields(
    fields: dict[str, Any],
    exclude_path: str,
    prefix: str = "",
) -> str:
    """Describe non-LLM fields so the LLM has context about the section."""
    from templates.loader import LLM_GENERATE

    lines: list[str] = []

    for key, value in fields.items():
        path = f"{prefix}.{key}" if prefix else key

        if path == exclude_path:
            continue

        if isinstance(value, str):
            if value and value != LLM_GENERATE:
                lines.append(f"  {path}: {value}")
        elif isinstance(value, dict):
            nested = _describe_existing_fields(value, exclude_path, path)
            if nested:
                lines.append(nested)

    return "\n".join(lines)
