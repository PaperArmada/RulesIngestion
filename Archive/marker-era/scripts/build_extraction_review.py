"""
Build a single Markdown review document per extraction output dir for manual review.
Reads chunks.json, logical_document.json, and metrics.json; writes EXTRACTION-REVIEW.md.

Usage:
  uv run python scripts/build_extraction_review.py [out/DocName ...]
  If no dirs given, runs for the five diverse-PDF output dirs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Default out dirs (diverse PDF run + baseline)
DEFAULT_OUT_DIRS = [
    "out/DnD5e-PHB",
    "out/StarFinder2e-AlienCore",
    "out/FateCore-CoreRules",
    "out/SwordsAndWizardry-CoreRules",
    "out/StarFinder2e-PlayerCore-v2",
]

FIRST_N_PAGES_FULL = 5
EVERY_NTH_PAGE = 20
MAX_CHARS_PER_CHUNK = 500
MAX_CHARS_TABLE = 800


def _page_of(c: dict) -> int:
    return c.get("logical_page_index", c.get("page_index", -1))


def _sort_key(c: dict) -> tuple:
    page = _page_of(c)
    bbox = c.get("bbox") or [0, 0, 0, 0]
    y0 = bbox[1] if len(bbox) >= 2 else 0
    x0 = bbox[0] if len(bbox) >= 1 else 0
    return (page, y0, x0)


def _truncate(text: str, max_len: int, suffix: str = "…") -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)].rstrip() + suffix


def _pages_to_include(total_pages: int, violation_page_indices: set[int]) -> set[int]:
    """Select pages for the sample: first N, every Nth, and any with M-A9 violations."""
    included = set()
    # First N pages
    for p in range(min(FIRST_N_PAGES_FULL, total_pages)):
        included.add(p)
    # Every Nth page
    for p in range(0, total_pages, EVERY_NTH_PAGE):
        included.add(p)
    # Violation pages (by_page keys are string indices)
    included.update(violation_page_indices)
    return included


def _build_review_md(out_dir: Path) -> str:
    chunks_path = out_dir / "chunks.json"
    if not chunks_path.exists():
        return ""
    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)
    chunks = [c for c in chunks if (c.get("text") or "").strip()]
    chunks.sort(key=_sort_key)

    logical_path = out_dir / "logical_document.json"
    doc_id = out_dir.name
    ruleset_id = book_id = ""
    if logical_path.exists():
        with open(logical_path, encoding="utf-8") as f:
            ld = json.load(f)
        doc_id = ld.get("logical_doc_id", doc_id)
        ruleset_id = ld.get("ruleset_id", "")
        book_id = ld.get("book_id", "")

    metrics_path = out_dir / "metrics.json"
    metrics = {}
    violation_page_indices: set[int] = set()
    if metrics_path.exists():
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)
        sf = metrics.get("structural_fidelity") or {}
        m9 = sf.get("M_A9_structural_continuity_violation_rate") or {}
        by_page = m9.get("by_page") or {}
        for k, v in by_page.items():
            if isinstance(v, dict) and v.get("violations", 0) > 0:
                try:
                    violation_page_indices.add(int(k))
                except ValueError:
                    pass

    pages = {_page_of(c) for c in chunks}
    total_pages = max(pages) + 1 if pages else 0
    include_pages = _pages_to_include(total_pages, violation_page_indices)

    lines = [
        f"# Extraction Review: {out_dir.name}",
        "",
        "Generated for manual review of chunk structure, section paths, and ordering.",
        "",
        "## Source & counts",
        "",
        f"- **Output dir:** `{out_dir}`",
        f"- **Logical doc id:** `{doc_id}`",
        f"- **Ruleset / book:** {ruleset_id!r} / {book_id!r}",
        f"- **Chunks (with text):** {len(chunks)}",
        f"- **Pages (pipeline indices):** 0–{total_pages - 1} ({total_pages} pages)",
        "",
    ]

    if metrics:
        lines.append("## Metrics summary")
        lines.append("")
        sf = metrics.get("structural_fidelity") or {}
        m9 = sf.get("M_A9_structural_continuity_violation_rate") or {}
        m10 = sf.get("M_A10_rule_outcome_misassignment_rate") or {}
        m11 = sf.get("M_A11_column_jump_structural_divergence") or {}
        lines.append(f"- **M-A9** (structural continuity): {m9.get('violations', '—')} violations / {m9.get('eligible_pairs', '—')} pairs → rate {m9.get('rate', '—')}")
        lines.append(f"- **M-A10** (rule outcome misassignment): {m10.get('misassigned_count', '—')} / {m10.get('outcome_chunks_with_header', '—')} → rate {m10.get('rate', '—')}")
        lines.append(f"- **M-A11** (column jump divergence): {m11.get('column_jump_and_path_change_count', '—')} / {m11.get('column_jump_count', '—')} → rate {m11.get('rate', '—')}")
        if violation_page_indices:
            lines.append(f"- **Pages with M-A9 violations:** {sorted(violation_page_indices)}")
        lines.append("")
        gates = metrics.get("gates") or {}
        if gates:
            lines.append(f"- **Gates passed:** {gates.get('passed', '—')}")
        lines.append("")

    lines.append("## Sample reconstruction (selected pages)")
    lines.append("")
    lines.append(f"Pages included: first {FIRST_N_PAGES_FULL}, every {EVERY_NTH_PAGE}th, plus any with M-A9 violations. Chunk text truncated to {MAX_CHARS_PER_CHUNK} chars.")
    lines.append("")

    current_page = -1
    for c in chunks:
        page = _page_of(c)
        if page not in include_pages:
            continue
        if page != current_page:
            current_page = page
            lines.append("")
            lines.append(f"---")
            lines.append("")
            lines.append(f"### Page {page} (pipeline index)")
            lines.append("")

        block_type = c.get("block_type", "Text")
        text = (c.get("text") or "").strip()
        section_path = c.get("section_path") or []
        sp = " → ".join(section_path) if section_path else "(none)"
        chunk_id = c.get("chunk_id", "")[:12]

        lines.append(f"**{block_type}** `{chunk_id}`  \nSection: `{sp}`")
        lines.append("")
        if block_type == "Table":
            body = _truncate(text, MAX_CHARS_TABLE)
            lines.append("<details><summary>Table</summary>")
            lines.append("")
            lines.append(body)
            lines.append("")
            lines.append("</details>")
        else:
            lines.append(_truncate(text, MAX_CHARS_PER_CHUNK))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*End of sample. Full data: chunks.json, marker_stream.json, metrics.json.*")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    if len(sys.argv) > 1:
        out_dirs = [base / d for d in sys.argv[1:]]
    else:
        out_dirs = [base / d for d in DEFAULT_OUT_DIRS]

    for out_dir in out_dirs:
        if not out_dir.is_dir():
            print(f"Skip (not a dir): {out_dir}", file=sys.stderr)
            continue
        md = _build_review_md(out_dir)
        if not md:
            print(f"Skip (no chunks.json): {out_dir}", file=sys.stderr)
            continue
        out_path = out_dir / "EXTRACTION-REVIEW.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
