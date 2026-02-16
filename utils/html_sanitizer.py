"""Sanitize HTML output from LLMs for WordPress WYSIWYG fields."""

from __future__ import annotations

import re

# Tags allowed in WordPress WYSIWYG content
ALLOWED_TAGS = frozenset({
    "p", "br", "strong", "em", "b", "i", "u",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "a",
    "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
    "img",
})

# Attributes allowed per tag
ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title", "target", "rel"}),
    "img": frozenset({"src", "alt", "width", "height"}),
}

# Pattern to match HTML tags (opening, closing, self-closing)
_TAG_PATTERN = re.compile(
    r"<(/?)(\w+)(\s[^>]*)?>",
    re.DOTALL,
)

# Pattern to match individual attributes
_ATTR_PATTERN = re.compile(
    r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')',
)

# Patterns for common LLM output artifacts
_MARKDOWN_FENCE = re.compile(r"^```(?:html)?\s*\n?", re.MULTILINE)
_MARKDOWN_FENCE_END = re.compile(r"\n?```\s*$", re.MULTILINE)
_WRAPPER_TAGS = re.compile(
    r"</?(?:html|head|body|div|span|meta|link|script|style)\b[^>]*>",
    re.IGNORECASE,
)


def sanitize_html(html: str) -> str:
    """Clean HTML content from LLM output for WordPress WYSIWYG fields.

    Removes:
    - Markdown code fences (```html ... ```)
    - Wrapper tags (<html>, <body>, <div>, <span>, etc.)
    - Disallowed tags
    - Disallowed attributes

    Preserves:
    - Semantic content tags (<p>, <ul>, <strong>, <a>, etc.)
    - Allowed attributes (href, src, alt, etc.)

    Args:
        html: Raw HTML string from LLM output.

    Returns:
        Cleaned HTML string safe for WordPress.
    """
    # Strip markdown code fences
    text = _MARKDOWN_FENCE.sub("", html)
    text = _MARKDOWN_FENCE_END.sub("", text)

    # Remove dangerous tags AND their content (script, style)
    text = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Remove wrapper/structural tags (just the tags, not content)
    text = _WRAPPER_TAGS.sub("", text)

    # Filter remaining tags
    text = _TAG_PATTERN.sub(_filter_tag, text)

    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _filter_tag(match: re.Match) -> str:
    """Filter a single HTML tag — keep allowed tags, strip the rest."""
    closing_slash = match.group(1)
    tag_name = match.group(2).lower()
    attrs_str = match.group(3) or ""

    if tag_name not in ALLOWED_TAGS:
        return ""

    # For closing tags, no attributes needed
    if closing_slash:
        return f"</{tag_name}>"

    # Filter attributes
    allowed = ALLOWED_ATTRS.get(tag_name, frozenset())
    filtered_attrs = _filter_attributes(attrs_str, allowed)

    if filtered_attrs:
        return f"<{tag_name} {filtered_attrs}>"
    return f"<{tag_name}>"


def _filter_attributes(attrs_str: str, allowed: frozenset[str]) -> str:
    """Keep only allowed attributes from an attribute string."""
    if not allowed:
        return ""

    parts: list[str] = []
    for match in _ATTR_PATTERN.finditer(attrs_str):
        attr_name = match.group(1).lower()
        attr_value = match.group(2) if match.group(2) is not None else match.group(3)
        if attr_name in allowed:
            parts.append(f'{attr_name}="{attr_value}"')

    return " ".join(parts)


def strip_html(html: str) -> str:
    """Strip all HTML tags, returning plain text.

    Useful for fields that expect plain text (e.g. heading text).
    """
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
