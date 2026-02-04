"""
Block-type normalization and text normalization.

Closed-world block types: Text, Heading, Table, Figure, List, Footnote, Unknown.
No silent fallthrough (A-INV-4).
"""

from __future__ import annotations

import re
from typing import Any

# Normalized block types (contract A-INV-4)
NORMALIZED_BLOCK_TYPES = frozenset({
    "Text",
    "Heading",
    "Table",
    "Figure",
    "List",
    "Footnote",
    "Unknown",
})

# Raw block types that represent structural containers, not content.
STRUCTURAL_CONTAINER_RAW_TYPES = frozenset({
    "Page",
    "ListGroup",
    "TableGroup",
    "FigureGroup",
    "TableOfContents",
    "Form",
})

# Marker raw type → normalized type (closed-world)
RAW_TO_NORMALIZED: dict[str, str] = {
    "Text": "Text",
    "SectionHeader": "Heading",
    "Title": "Heading",
    "Table": "Table",
    "TableCell": "Table",
    "Picture": "Figure",
    "Figure": "Figure",
    "List": "List",
    "ListItem": "List",
    "Footnote": "Footnote",
    "CodeBlock": "Text",
    "Interlude": "Text",
}


def normalize_block_type(raw: str) -> str:
    """Map raw extractor block type to closed set. Unknown → Unknown, no silent fallthrough."""
    if not raw or not raw.strip():
        return "Unknown"
    key = raw.strip()
    return RAW_TO_NORMALIZED.get(key, "Unknown")


def is_structural_container(raw: str | None) -> bool:
    """Return True if raw block type is a structural container (non-content)."""
    if not raw:
        return False
    return raw.strip() in STRUCTURAL_CONTAINER_RAW_TYPES


# Raw block types that are content but often have no text (empty cells, empty paras).
# Preserved in structural side-channel for markdown reconstruction; not counted as dropped.
EMPTY_STRUCTURAL_RAW_TYPES = frozenset({"TableCell", "Text"})


def is_empty_structural_content(raw_block_type: str, text: str | None) -> bool:
    """True if block is TableCell/Text with no text — preserve in side-channel, exclude from retention penalty."""
    if not raw_block_type or raw_block_type.strip() not in EMPTY_STRUCTURAL_RAW_TYPES:
        return False
    return not (text or "").strip()


# Source PDF identifiers that denote form-heavy parts (e.g. character sheets).
# M-A3 is enforced on rulebook parts only when these are present.
FORM_PART_SUBSTRINGS = ("Character Sheet",)


def is_form_part(source_pdf_id: str | None) -> bool:
    """Return True if source_pdf_id denotes a form-heavy part (excluded from M-A3 rulebook retention)."""
    if not source_pdf_id or not source_pdf_id.strip():
        return False
    s = source_pdf_id.strip()
    return any(sub in s for sub in FORM_PART_SUBSTRINGS)


def normalize_text(text: str) -> str:
    """Normalize extracted text: collapse whitespace, strip. Non-empty after norm for valid span."""
    if text is None:
        return ""
    s = str(text).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def is_table_like_text(text: str) -> bool:
    """Heuristic: table/index rows with many numbers and divider symbols."""
    if not text:
        return False
    s = normalize_text(text)
    if len(s) < 10:
        return False
    numeric_tokens = re.findall(r"\d+", s)
    if len(numeric_tokens) < 3:
        return False
    symbols = set("—-_+/")
    symbolish = sum(1 for c in s if c.isdigit() or c in symbols)
    ratio = symbolish / max(len(s), 1)
    return ratio >= 0.18


def extract_text_from_html(html: str) -> str:
    """Strip tags and extract plain text from HTML block. Fallback for Marker html."""
    if not html or not html.strip():
        return ""
    # Minimal tag strip: remove <...> and decode common entities
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    return normalize_text(text)


def build_section_path(section_hierarchy: dict[str, Any] | None) -> list[str]:
    """Build flat section path from Marker's nested section_hierarchy (titles only)."""
    if not section_hierarchy:
        return []
    path: list[str] = []

    def extract_titles(node: Any) -> None:
        if isinstance(node, dict):
            if "title" in node:
                path.append(str(node["title"]).strip())
            for key, value in node.items():
                if key != "title":
                    extract_titles(value)
        elif isinstance(node, list):
            for item in node:
                extract_titles(item)

    extract_titles(section_hierarchy)
    return [p for p in path if p]
