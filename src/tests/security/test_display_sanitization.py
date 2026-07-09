# Copyright (c) Maltego Technologies GmbH.
"""
Tests for F48 — display-field HTML sanitization (stored XSS prevention).

Verifies that:
- <script> tags are stripped from markdown-generated HTML
- inline event handlers (onerror, onclick, …) are stripped
- javascript: and data: URLs are stripped from href/src attributes
- legitimate markdown formatting (bold, links, lists, tables, code) survives
- raw HTML supplied via add_display_field_html is also sanitized
"""
import pytest

from maltego.server import MaltegoEntity, register_entity
from maltego.model.entity import MaltegoEntityConfig

pytestmark = pytest.mark.security


@register_entity
class _DisplayTestEntity(MaltegoEntity):
    TYPE_NAME = "maltego._DisplayTestEntity"
    Config = MaltegoEntityConfig(
        value_property="value",
        display_name="DisplayTestEntity",
        display_property="value",
        display_name_plural="DisplayTestEntities",
        description="Entity for display-sanitization tests",
        icon_resource="Phrase",
        category="Test",
    )
    value: str = "test"


def _get_display_html(entity: MaltegoEntity, field_name: str) -> str:
    """Return the stored HTML value for the first display item with the given name."""
    for item in entity.display_information:
        if item.name == field_name:
            return item.value
    return ""


# ---------------------------------------------------------------------------
# F48 — Markdown path: malicious payloads are stripped
# ---------------------------------------------------------------------------

class TestF48MarkdownXSSStripped:
    def test_script_tag_stripped_from_markdown(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "Hello <script>alert('xss')</script> World"
        )
        html = _get_display_html(entity, "Details")
        assert "<script>" not in html
        assert "alert" not in html
        assert "World" in html  # surrounding text preserved

    def test_img_onerror_stripped_from_markdown(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            'Some text <img src="x" onerror="alert(1)"> end'
        )
        html = _get_display_html(entity, "Details")
        assert "onerror" not in html
        assert "alert" not in html

    def test_javascript_url_stripped_from_markdown_link(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "[click me](javascript:alert('xss'))"
        )
        html = _get_display_html(entity, "Details")
        assert "javascript:" not in html

    def test_data_url_stripped_from_markdown_link(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "[click me](data:text/html,<script>alert(1)</script>)"
        )
        html = _get_display_html(entity, "Details")
        assert "data:" not in html

    def test_inline_onclick_stripped_from_markdown(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            '<span onclick="evil()">text</span>'
        )
        html = _get_display_html(entity, "Details")
        assert "onclick" not in html
        assert "evil" not in html
        # The <span> element itself and text content may or may not survive
        # depending on nh3 behaviour; what matters is the event handler is gone.


# ---------------------------------------------------------------------------
# F48 — Markdown path: legitimate markdown formatting is preserved
# ---------------------------------------------------------------------------

class TestF48MarkdownFormattingPreserved:
    def test_bold_and_italic_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "**bold** and *italic*"
        )
        html = _get_display_html(entity, "Details")
        assert "<strong>" in html or "bold" in html
        assert "<em>" in html or "italic" in html

    def test_hyperlink_with_safe_url_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "[Maltego](https://www.maltego.com)"
        )
        html = _get_display_html(entity, "Details")
        assert "https://www.maltego.com" in html
        assert "<a" in html

    def test_unordered_list_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "- item one\n- item two\n- item three"
        )
        html = _get_display_html(entity, "Details")
        assert "<ul>" in html or "<li>" in html
        assert "item one" in html
        assert "item two" in html

    def test_ordered_list_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "1. first\n2. second\n3. third"
        )
        html = _get_display_html(entity, "Details")
        assert "<ol>" in html or "<li>" in html
        assert "first" in html

    def test_table_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "| Col A | Col B |\n|-------|-------|\n| val1  | val2  |"
        )
        html = _get_display_html(entity, "Details")
        assert "<table>" in html
        assert "<td>" in html or "<th>" in html
        assert "val1" in html

    def test_inline_code_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "Use `print('hello')` to print."
        )
        html = _get_display_html(entity, "Details")
        assert "<code>" in html
        assert "print" in html

    def test_fenced_code_block_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "```python\nprint('hello')\n```"
        )
        html = _get_display_html(entity, "Details")
        assert "<pre>" in html or "<code>" in html
        assert "hello" in html

    def test_heading_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_markdown(
            "Details",
            "## My Heading\n\nSome content."
        )
        html = _get_display_html(entity, "Details")
        assert "<h2>" in html
        assert "My Heading" in html


# ---------------------------------------------------------------------------
# F48 — Raw HTML path: add_display_field_html is also sanitized
# ---------------------------------------------------------------------------

class TestF48RawHtmlSanitized:
    def test_script_tag_stripped_from_raw_html(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_html(
            "Details",
            "<p>Hello</p><script>alert('xss')</script>"
        )
        html = _get_display_html(entity, "Details")
        assert "<script>" not in html
        assert "alert" not in html
        assert "<p>" in html
        assert "Hello" in html

    def test_img_onerror_stripped_from_raw_html(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_html(
            "Details",
            '<table><tr><td>data</td></tr></table>'
            '<img src="https://example.com/img.jpg" onerror="evil()">'
        )
        html = _get_display_html(entity, "Details")
        assert "onerror" not in html
        assert "evil" not in html
        assert "<table>" in html  # table preserved

    def test_javascript_url_stripped_from_raw_html_anchor(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_html(
            "Details",
            '<a href="javascript:alert(1)">click</a>'
        )
        html = _get_display_html(entity, "Details")
        assert "javascript:" not in html

    def test_safe_html_table_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_html(
            "Details",
            '<table style="width:100%"><tr><th>Key</th><th>Value</th></tr>'
            '<tr><td>name</td><td>Alice</td></tr></table>'
        )
        html = _get_display_html(entity, "Details")
        assert "<table" in html
        assert "<th>" in html
        assert "Alice" in html

    def test_safe_html_link_preserved(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_field_html(
            "Details",
            '<a href="https://maltego.com" target="_blank">Maltego</a>'
        )
        html = _get_display_html(entity, "Details")
        assert "https://maltego.com" in html
        assert "<a" in html
        assert "Maltego" in html


# ---------------------------------------------------------------------------
# F48 — add_display_label path is also sanitized
# ---------------------------------------------------------------------------

class TestF48DisplayLabelSanitized:
    def test_script_stripped_from_display_label(self):
        entity = _DisplayTestEntity("test")
        entity.add_display_label(
            "Label",
            "<b>safe</b><script>evil()</script>",
            content_type="text/html"
        )
        html = _get_display_html(entity, "Label")
        assert "<script>" not in html
        assert "evil" not in html
        assert "<b>" in html
        assert "safe" in html
