"""Tests for extraction.normalize: block-type map, text normalization."""

import pytest

from extraction.normalize import (
    build_section_path,
    extract_text_from_html,
    is_empty_structural_content,
    is_form_part,
    is_structural_container,
    is_table_like_text,
    normalize_block_type,
    normalize_text,
    NORMALIZED_BLOCK_TYPES,
)


def test_normalize_block_type_closed_set() -> None:
    assert normalize_block_type("Text") == "Text"
    assert normalize_block_type("SectionHeader") == "Heading"
    assert normalize_block_type("Title") == "Heading"
    assert normalize_block_type("Table") == "Table"
    assert normalize_block_type("Picture") == "Figure"
    assert normalize_block_type("List") == "List"
    assert normalize_block_type("Footnote") == "Footnote"
    assert normalize_block_type("UnknownType") == "Unknown"
    assert normalize_block_type("") == "Unknown"
    assert normalize_block_type("  ") == "Unknown"


def test_normalize_block_type_all_in_set() -> None:
    for raw in ["Text", "SectionHeader", "Title", "Table", "Picture", "List", "Footnote"]:
        out = normalize_block_type(raw)
        assert out in NORMALIZED_BLOCK_TYPES


def test_normalize_text() -> None:
    assert normalize_text("  foo  bar  ") == "foo bar"
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_extract_text_from_html() -> None:
    assert "hello" in extract_text_from_html("<p>hello</p>")
    assert extract_text_from_html("") == ""
    assert "&" in extract_text_from_html("a &amp; b") or "&" in extract_text_from_html("a & b")


def test_is_empty_structural_content() -> None:
    assert is_empty_structural_content("TableCell", "") is True
    assert is_empty_structural_content("Text", "  ") is True
    assert is_empty_structural_content("Text", "x") is False
    assert is_empty_structural_content("TableCell", "cell") is False
    assert is_empty_structural_content("Figure", "") is False
    assert is_empty_structural_content("", "") is False


def test_is_table_like_text() -> None:
    assert is_table_like_text("Armor 10  5  4  4  4  —  —") is True
    assert is_table_like_text("Short heading") is False
    assert is_table_like_text("") is False


def test_build_section_path() -> None:
    assert build_section_path(None) == []
    assert build_section_path({}) == []
    h = {"title": "Chapter 1", "children": [{"title": "Section A"}]}
    path = build_section_path(h)
    assert "Chapter 1" in path
    assert "Section A" in path


def test_is_structural_container() -> None:
    assert is_structural_container("Page") is True
    assert is_structural_container("ListGroup") is True
    assert is_structural_container("TableGroup") is True
    assert is_structural_container("FigureGroup") is True
    assert is_structural_container("TableOfContents") is True
    assert is_structural_container("Form") is True
    assert is_structural_container("Text") is False
    assert is_structural_container("") is False
    assert is_structural_container(None) is False


def test_is_form_part() -> None:
    assert is_form_part("PZO22001 Starfinder Character Sheet") is True
    assert is_form_part("Character Sheet") is True
    assert is_form_part("PZO22001 Starfinder Player Core 001-013") is False
    assert is_form_part("") is False
    assert is_form_part(None) is False
