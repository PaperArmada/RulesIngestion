"""
TOC Parser — deterministic Table of Contents detection, flat entry extraction,
and LLM-assisted hierarchy reconstruction.

Phase 1 (deterministic):
  - detect_toc_pages(): scan early pages for TOC pattern
  - extract_flat_entries(): parse TOC lines into TocEntry list

Phase 2 (LLM-assisted):
  - reconstruct_hierarchy(): call mini/nano model for indent structure
  - validate_hierarchy(): strict 1:1 mapping against flat entries
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TocEntry:
    """Single flat TOC entry: title + page number."""
    title: str
    page_num: int
    raw_line: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "page_num": self.page_num, "raw_line": self.raw_line}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> TocEntry:
        return TocEntry(title=d["title"], page_num=d["page_num"], raw_line=d.get("raw_line", ""))


@dataclass
class TocNode:
    """Hierarchical TOC node with page range."""
    title: str
    page_num: int
    page_end: int = -1
    depth: int = 0
    children: list[TocNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "title": self.title,
            "page_num": self.page_num,
            "page_end": self.page_end,
            "depth": self.depth,
        }
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> TocNode:
        children = [TocNode.from_dict(c) for c in d.get("children", [])]
        return TocNode(
            title=d["title"],
            page_num=d["page_num"],
            page_end=d.get("page_end", -1),
            depth=d.get("depth", 0),
            children=children,
        )

    def ancestry_path(self) -> list[str]:
        """Return just this node's title (ancestry built during binding traversal)."""
        return [self.title]

    def all_nodes_flat(self) -> list[TocNode]:
        """Depth-first flat list of all nodes."""
        result: list[TocNode] = [self]
        for c in self.children:
            result.extend(c.all_nodes_flat())
        return result


@dataclass
class TocDetectionResult:
    """Result of TOC detection on a set of pages."""
    found: bool
    score: float
    toc_pages: list[int]
    method: str
    entries: list[TocEntry]
    confidence: str  # "high", "medium", "low", "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "score": round(self.score, 4),
            "toc_pages": self.toc_pages,
            "method": self.method,
            "entry_count": len(self.entries),
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# Phase 1: Deterministic TOC detection
# ---------------------------------------------------------------------------

_TOC_HEADING_RE = re.compile(
    r"(?:table\s+of\s+contents|contents)\s*$",
    re.IGNORECASE,
)

_DOTTED_LEADER_RE = re.compile(
    r"^(.+?)\s*\.{3,}\s*(\d+)\s*$"
)

_DASH_LEADER_RE = re.compile(
    r"^(.+?)\s+[—–-]+\s*(\d+)\s*$"
)


def _score_toc_page(raw_markdown: str, ast_dict: dict[str, Any] | None = None) -> tuple[float, list[str]]:
    """Score a single page for TOC likelihood. Returns (score, candidate_lines)."""
    score = 0.0
    lines = [ln.strip() for ln in raw_markdown.split("\n") if ln.strip()]
    if not lines:
        return 0.0, []

    for line in lines:
        clean = re.sub(r"^#{1,6}\s+", "", line).strip()
        if _TOC_HEADING_RE.match(clean):
            score += 0.5
            break

    if ast_dict:
        root = ast_dict.get("root", {})
        for child in root.get("children", []):
            if child.get("node_type") == "heading":
                text = child.get("text", "").strip()
                if _TOC_HEADING_RE.match(text):
                    score += 0.5
                    break

    score = min(score, 0.5)

    entry_lines: list[str] = []
    page_nums: list[int] = []
    for line in lines:
        clean = re.sub(r"^#{1,6}\s+", "", line).strip()
        if _TOC_HEADING_RE.match(clean):
            continue
        m = _DOTTED_LEADER_RE.match(line) or _DASH_LEADER_RE.match(line)
        if m:
            entry_lines.append(line)
            page_nums.append(int(m.group(2)))

    non_blank_content_lines = [ln for ln in lines if not _TOC_HEADING_RE.match(re.sub(r"^#{1,6}\s+", "", ln).strip())]
    if non_blank_content_lines:
        entry_ratio = len(entry_lines) / len(non_blank_content_lines)
        if entry_ratio >= 0.4:
            score += 0.3

    if len(page_nums) >= 3:
        monotonic = all(page_nums[i] <= page_nums[i + 1] for i in range(len(page_nums) - 1))
        if monotonic:
            score += 0.2

    return score, entry_lines


def detect_toc_pages(
    eval_dir: Path,
    stem: str,
    max_scan_pages: int = 13,
) -> TocDetectionResult:
    """Scan early pages for TOC pattern. Returns detection result with flat entries if found."""
    eval_dir = Path(eval_dir)
    best_score = 0.0
    best_pages: list[int] = []
    best_entry_lines: list[str] = []

    for page_idx in range(max_scan_pages):
        page_dir = eval_dir / f"{stem}_p{page_idx}"
        page_json = page_dir / "stageA.page.json"
        ast_json = page_dir / "stageA.surface.ast.json"
        if not page_json.exists():
            continue

        page_data = json.loads(page_json.read_text(encoding="utf-8"))
        raw_md = page_data.get("raw_markdown", "")
        ast_dict = None
        if ast_json.exists():
            ast_dict = json.loads(ast_json.read_text(encoding="utf-8"))

        score, entry_lines = _score_toc_page(raw_md, ast_dict)
        if score > best_score:
            best_score = score
            best_pages = [page_idx]
            best_entry_lines = entry_lines
        elif score == best_score and score > 0 and entry_lines:
            best_pages.append(page_idx)
            best_entry_lines.extend(entry_lines)

    if best_score >= 0.7:
        entries = _parse_entry_lines(best_entry_lines)
        confidence = "high" if best_score >= 0.9 else "medium"
        logger.info("TOC detected on page(s) %s (score=%.2f, entries=%d)", best_pages, best_score, len(entries))
        return TocDetectionResult(
            found=True,
            score=best_score,
            toc_pages=best_pages,
            method="deterministic",
            entries=entries,
            confidence=confidence,
        )

    logger.info("No TOC detected in first %d pages (best_score=%.2f)", max_scan_pages, best_score)
    return TocDetectionResult(
        found=False,
        score=best_score,
        toc_pages=best_pages,
        method="deterministic",
        entries=[],
        confidence="none",
    )


def _parse_entry_lines(lines: list[str]) -> list[TocEntry]:
    """Parse raw TOC lines into TocEntry objects."""
    entries: list[TocEntry] = []
    seen: set[tuple[str, int]] = set()
    for line in lines:
        m = _DOTTED_LEADER_RE.match(line.strip()) or _DASH_LEADER_RE.match(line.strip())
        if not m:
            continue
        title = m.group(1).strip()
        page_num = int(m.group(2))
        key = (title.casefold(), page_num)
        if key in seen:
            continue
        seen.add(key)
        entries.append(TocEntry(title=title, page_num=page_num, raw_line=line.strip()))
    return entries


# ---------------------------------------------------------------------------
# Phase 2: Hierarchy reconstruction (LLM-assisted)
# ---------------------------------------------------------------------------

_HIERARCHY_PROMPT = """Given this flat table of contents from a book, reconstruct the hierarchical structure using indentation.

Rules:
- Output each entry as: indent_spaces + title + " -- " + page_number
- Use 2 spaces per indent level (0 spaces = top-level chapter)
- Do not add, remove, or rename any entries
- Do not change any page numbers
- Every input entry must appear exactly once in the output

Input entries:
{entries}

Output the hierarchical table of contents:"""


def _format_entries_for_prompt(entries: list[TocEntry]) -> str:
    return "\n".join(f"{e.title} -- {e.page_num}" for e in entries)


def _parse_hierarchy_response(response: str, flat_entries: list[TocEntry]) -> list[TocNode] | None:
    """Parse LLM response into TocNode tree. Returns None if validation fails."""
    flat_lookup: dict[tuple[str, int], TocEntry] = {
        (e.title.casefold().strip(), e.page_num): e for e in flat_entries
    }
    matched: set[tuple[str, int]] = set()

    lines = [ln.rstrip() for ln in response.split("\n") if ln.strip()]
    if not lines:
        return None

    parsed: list[tuple[int, str, int]] = []
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        depth = indent // 2

        m = re.match(r"^(.+?)\s+--\s+(\d+)\s*$", stripped)
        if not m:
            m = re.match(r"^(.+?)\s*\.{3,}\s*(\d+)\s*$", stripped)
        if not m:
            m = re.match(r"^(.+?)\s+[—–-]+\s*(\d+)\s*$", stripped)
        if not m:
            continue

        title = m.group(1).strip()
        page_num = int(m.group(2))
        key = (title.casefold().strip(), page_num)
        if key not in flat_lookup:
            logger.warning("Hierarchy response contains unknown entry: %r page %d", title, page_num)
            return None
        if key in matched:
            logger.warning("Hierarchy response contains duplicate entry: %r page %d", title, page_num)
            return None
        matched.add(key)
        parsed.append((depth, title, page_num))

    if len(matched) != len(flat_entries):
        logger.warning(
            "Hierarchy response has %d entries, expected %d (missing %d)",
            len(matched), len(flat_entries), len(flat_entries) - len(matched),
        )
        return None

    return _build_tree_from_parsed(parsed)


def _build_tree_from_parsed(parsed: list[tuple[int, str, int]]) -> list[TocNode]:
    """Build TocNode tree from (depth, title, page_num) tuples."""
    if not parsed:
        return []

    root_nodes: list[TocNode] = []
    stack: list[tuple[int, TocNode]] = []

    for depth, title, page_num in parsed:
        node = TocNode(title=title, page_num=page_num, depth=depth)

        while stack and stack[-1][0] >= depth:
            stack.pop()

        if stack:
            stack[-1][1].children.append(node)
        else:
            root_nodes.append(node)

        stack.append((depth, node))

    return root_nodes


def build_flat_hierarchy(entries: list[TocEntry]) -> list[TocNode]:
    """Fallback: treat all entries as top-level (no hierarchy)."""
    return [TocNode(title=e.title, page_num=e.page_num, depth=0) for e in entries]


async def reconstruct_hierarchy_async(
    entries: list[TocEntry],
    *,
    openai_client: Any | None = None,
    model: str = "gpt-4o-mini",
) -> tuple[list[TocNode], str]:
    """Call LLM to reconstruct TOC hierarchy. Returns (nodes, method).

    Falls back to flat hierarchy if LLM call fails or validation rejects output.
    """
    if not entries:
        return [], "empty"

    from openai import AsyncOpenAI
    client = openai_client or AsyncOpenAI()

    prompt = _HIERARCHY_PROMPT.format(entries=_format_entries_for_prompt(entries))

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content or ""
        nodes = _parse_hierarchy_response(content, entries)
        if nodes is not None:
            logger.info("TOC hierarchy reconstructed via LLM (%d top-level nodes)", len(nodes))
            return nodes, "llm"
        logger.warning("LLM hierarchy validation failed; falling back to flat")
    except Exception as e:
        logger.warning("LLM hierarchy reconstruction failed: %s; falling back to flat", e)

    return build_flat_hierarchy(entries), "flat_fallback"


def reconstruct_hierarchy(
    entries: list[TocEntry],
    *,
    openai_client: Any | None = None,
    model: str = "gpt-4o-mini",
) -> tuple[list[TocNode], str]:
    """Synchronous wrapper for reconstruct_hierarchy_async."""
    import asyncio
    return asyncio.run(reconstruct_hierarchy_async(entries, openai_client=openai_client, model=model))


# ---------------------------------------------------------------------------
# Page-range computation
# ---------------------------------------------------------------------------

def compute_page_ranges(nodes: list[TocNode], total_pages: int) -> list[TocNode]:
    """Compute page_end for each node based on sibling/parent boundaries.

    Mutates nodes in place and returns the same list.
    """
    _compute_ranges_recursive(nodes, total_pages - 1)
    return nodes


def _compute_ranges_recursive(siblings: list[TocNode], parent_page_end: int) -> None:
    for i, node in enumerate(siblings):
        if i + 1 < len(siblings):
            node.page_end = siblings[i + 1].page_num - 1
        else:
            node.page_end = parent_page_end

        if node.children:
            _compute_ranges_recursive(node.children, node.page_end)


# ---------------------------------------------------------------------------
# Artifact I/O
# ---------------------------------------------------------------------------

def write_toc_artifacts(
    out_dir: Path,
    detection: TocDetectionResult,
    tree: list[TocNode] | None = None,
    hierarchy_method: str = "",
) -> None:
    """Write toc_detection.json, toc_entries.json, and toc_tree.json."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    det_path = out_dir / "toc_detection.json"
    det_path.write_text(
        json.dumps(detection.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if detection.entries:
        entries_path = out_dir / "toc_entries.json"
        entries_path.write_text(
            json.dumps([e.to_dict() for e in detection.entries], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if tree is not None:
        tree_path = out_dir / "toc_tree.json"
        tree_data = {
            "hierarchy_method": hierarchy_method,
            "node_count": sum(len(n.all_nodes_flat()) for n in tree),
            "top_level_count": len(tree),
            "nodes": [n.to_dict() for n in tree],
        }
        tree_path.write_text(
            json.dumps(tree_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    logger.info("TOC artifacts written to %s", out_dir)


def load_toc_tree(out_dir: Path) -> list[TocNode] | None:
    """Load toc_tree.json if it exists."""
    tree_path = Path(out_dir) / "toc_tree.json"
    if not tree_path.exists():
        return None
    data = json.loads(tree_path.read_text(encoding="utf-8"))
    return [TocNode.from_dict(n) for n in data.get("nodes", [])]
