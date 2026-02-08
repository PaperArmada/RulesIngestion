"""
AST Parser — convert raw DeepSeek markdown into a SurfaceAST.

The parser is deliberately structural and dumb:
  - Classify each line by surface markers (heading, table, list, image ref, blockquote, etc.)
  - Build a tree where headings create nesting and leaf nodes are prose/table/list/callout blocks.
  - Record source line ranges for provenance back to the raw markdown.

No semantic interpretation.  No paraphrasing.  No inference.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

import blake3

from extraction.schemas import SurfaceAST, SurfaceASTNode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Line classification
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_ITEM_RE = re.compile(r"^(\s*)[•\-\*]\s+(.*)$")
_IMAGE_REF_RE = re.compile(r"^!\[.*?\]\(.*?\)\s*$")
_HTML_TABLE_OPEN_RE = re.compile(r"<table\b", re.IGNORECASE)
_HTML_TABLE_CLOSE_RE = re.compile(r"</table>", re.IGNORECASE)
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)")
_HR_RE = re.compile(r"^-{3,}$|^\*{3,}$|^_{3,}$")

LineKind = Literal[
    "heading",
    "list_item",
    "image_ref",
    "table_line",
    "blockquote",
    "hr",
    "blank",
    "text",
]


def _classify_line(line: str) -> LineKind:
    """Classify a single line by its surface markers."""
    stripped = line.strip()
    if not stripped:
        return "blank"
    if _HEADING_RE.match(stripped):
        return "heading"
    if _HR_RE.match(stripped):
        return "hr"
    if _IMAGE_REF_RE.match(stripped):
        return "image_ref"
    if _LIST_ITEM_RE.match(stripped):
        return "list_item"
    if _BLOCKQUOTE_RE.match(stripped):
        return "blockquote"
    # table_line is handled at block level, not per-line
    return "text"


# ---------------------------------------------------------------------------
# Block segmentation
# ---------------------------------------------------------------------------

def _segment_blocks(
    lines: list[str],
) -> list[tuple[str, int, int, str]]:
    """Segment raw lines into typed blocks.

    Returns list of (block_type, start_line, end_line_exclusive, text).
    block_type is one of the SurfaceASTNode node_type values.
    """
    blocks: list[tuple[str, int, int, str]] = []
    n = len(lines)
    i = 0

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # -- HTML table block (may span many lines) --------------------------
        if _HTML_TABLE_OPEN_RE.search(stripped):
            start = i
            depth = 0
            table_lines: list[str] = []
            while i < n:
                table_lines.append(lines[i])
                depth += len(_HTML_TABLE_OPEN_RE.findall(lines[i]))
                depth -= len(_HTML_TABLE_CLOSE_RE.findall(lines[i]))
                i += 1
                if depth <= 0:
                    break
            blocks.append(("table", start, i, "\n".join(table_lines)))
            continue

        kind = _classify_line(line)

        # -- blank / hr: skip (structural separators, not content) -----------
        if kind in ("blank", "hr"):
            i += 1
            continue

        # -- heading ---------------------------------------------------------
        if kind == "heading":
            blocks.append(("heading", i, i + 1, stripped))
            i += 1
            continue

        # -- image ref -------------------------------------------------------
        if kind == "image_ref":
            blocks.append(("image_ref", i, i + 1, stripped))
            i += 1
            continue

        # -- blockquote (consecutive > lines form one callout) ---------------
        if kind == "blockquote":
            start = i
            bq_parts: list[str] = []
            while i < n and _classify_line(lines[i]) == "blockquote":
                m = _BLOCKQUOTE_RE.match(lines[i].strip())
                bq_parts.append(m.group(1) if m else lines[i].strip())
                i += 1
            blocks.append(("callout", start, i, "\n".join(bq_parts)))
            continue

        # -- list (consecutive list items) -----------------------------------
        if kind == "list_item":
            start = i
            list_parts: list[str] = []
            while i < n and _classify_line(lines[i]) == "list_item":
                m = _LIST_ITEM_RE.match(lines[i].strip())
                list_parts.append(m.group(2) if m else lines[i].strip())
                i += 1
            blocks.append(("list", start, i, "\n".join(list_parts)))
            continue

        # -- paragraph (consecutive text lines) ------------------------------
        if kind == "text":
            start = i
            para_parts: list[str] = []
            while i < n:
                lk = _classify_line(lines[i])
                if lk != "text":
                    break
                # Also break if next line starts an HTML table
                if _HTML_TABLE_OPEN_RE.search(lines[i].strip()):
                    break
                para_parts.append(lines[i].strip())
                i += 1
            blocks.append(("paragraph", start, i, "\n".join(para_parts)))
            continue

        # Fallback: consume line as paragraph
        blocks.append(("paragraph", i, i + 1, stripped))
        i += 1

    return blocks


# ---------------------------------------------------------------------------
# Tree construction
# ---------------------------------------------------------------------------

def _heading_level(text: str) -> int:
    """Extract heading level from a markdown heading line."""
    m = _HEADING_RE.match(text.strip())
    return len(m.group(1)) if m else 0


def _heading_text(text: str) -> str:
    """Extract heading text (without the # prefix)."""
    m = _HEADING_RE.match(text.strip())
    return m.group(2).strip() if m else text.strip()


def _build_tree(
    blocks: list[tuple[str, int, int, str]],
) -> SurfaceASTNode:
    """Build a heading-nested tree from a flat list of blocks.

    Headings create nesting: an H2 contains everything until the next H2 or
    higher.  Non-heading blocks become children of the most recent heading
    at their depth, or of root if no heading precedes them.
    """
    root = SurfaceASTNode(
        node_type="root",
        level=0,
        text="",
        children=[],
        source_line_start=0,
        source_line_end=0,
    )

    # Stack of (heading_level, node).  Root is level 0.
    stack: list[tuple[int, SurfaceASTNode]] = [(0, root)]

    for block_type, start, end, text in blocks:
        if block_type == "heading":
            level = _heading_level(text)
            heading_text = _heading_text(text)
            node = SurfaceASTNode(
                node_type="heading",
                level=level,
                text=heading_text,
                children=[],
                source_line_start=start,
                source_line_end=end,
            )
            # Pop stack until we find a parent with strictly lower level
            while len(stack) > 1 and stack[-1][0] >= level:
                stack.pop()
            stack[-1][1].children.append(node)
            stack.append((level, node))
        else:
            node = SurfaceASTNode(
                node_type=block_type,  # type: ignore[arg-type]
                level=0,
                text=text,
                children=[],
                source_line_start=start,
                source_line_end=end,
            )
            stack[-1][1].children.append(node)

    # Update root's source_line_end to cover all content
    if blocks:
        root.source_line_end = blocks[-1][2]

    return root


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_markdown_to_ast(
    raw_markdown: str,
    page_fingerprint: str,
) -> SurfaceAST:
    """Parse raw DeepSeek markdown into a SurfaceAST.

    Args:
        raw_markdown: Verbatim model output (markdown string).
        page_fingerprint: blake3 hex digest of the source page image.

    Returns:
        SurfaceAST with structural tree and content hash.
    """
    lines = raw_markdown.split("\n")
    blocks = _segment_blocks(lines)
    root = _build_tree(blocks)

    all_nodes = root.all_nodes()
    node_count = len(all_nodes)
    table_count = sum(1 for n in all_nodes if n.node_type == "table")

    # Deterministic content hash: serialise the tree, then blake3.
    tree_json = json.dumps(root.to_dict(), sort_keys=True, ensure_ascii=False)
    content_hash = blake3.blake3(tree_json.encode("utf-8")).hexdigest()

    logger.info(
        "AST parsed: %d nodes, %d tables, hash=%s",
        node_count,
        table_count,
        content_hash[:16],
    )

    return SurfaceAST(
        page_fingerprint=page_fingerprint,
        content_hash=content_hash,
        root=root,
        node_count=node_count,
        table_count=table_count,
    )
