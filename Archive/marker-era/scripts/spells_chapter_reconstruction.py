"""
Build a full Markdown reconstruction of the spells chapter (pages 330–363) from
extraction chunks, then append a review for column/sidebar interleaving.
Output: SPELLS-CHAPTER-RECONSTRUCTION.md in the given output dir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "out" / "StarFinder2e-PlayerCore-v2"
SPELLS_PAGES = set(range(330, 364))

# Sidebar / TOC labels that indicate interleaving if they appear as chunk start in main flow
SIDEBAR_LIKE = (
    "INTRODUCTION",
    "ANCESTRIES & BACKGROUNDS",
    "CLASSES",
    "SKILLS",
    "FEATS",
    "EQUIPMENT",
    "SPELLS",
    "PLAYING THE GAME",
    "CONDITIONS",
    "APPENDIX",
    "GLOSSARY & INDEX",
    "CHARACTER SHEET",
)


def _page_of(c: dict) -> int:
    return c.get("logical_page_index", c.get("page_index", -1))


def _sort_key(c: dict) -> tuple:
    page = _page_of(c)
    bbox = c.get("bbox") or [0, 0, 0, 0]
    y0 = bbox[1] if len(bbox) >= 2 else 0
    x0 = bbox[0] if len(bbox) >= 1 else 0
    return (page, y0, x0)


def _main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR
    chunks_path = out_dir / "chunks.json"
    if not chunks_path.exists():
        print(f"Missing {chunks_path}", file=sys.stderr)
        sys.exit(1)

    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)

    spells = [c for c in chunks if _page_of(c) in SPELLS_PAGES]
    spells.sort(key=_sort_key)

    md_lines = [
        "# Spells Chapter — Full MD Reconstruction (pages 330–363)",
        "",
        "Source: extraction chunks, ordered by page then bbox (y, x).",
        "",
        "---",
        "",
    ]

    current_page = -1
    for c in spells:
        page = _page_of(c)
        if page != current_page:
            current_page = page
            md_lines.append("")
            md_lines.append(f"<!-- Page {page} -->")
            md_lines.append("")

        block_type = c.get("block_type", "Text")
        text = (c.get("text") or "").strip()
        if not text:
            continue

        if block_type == "Heading":
            # Use ## for top-level headings (spell names etc.)
            md_lines.append(f"## {text}")
            md_lines.append("")
        elif block_type == "Table":
            md_lines.append("<details><summary>Table</summary>")
            md_lines.append("")
            md_lines.append(text.replace("\n\n", "\n\n"))
            md_lines.append("")
            md_lines.append("</details>")
            md_lines.append("")
        elif block_type == "List":
            md_lines.append(text)
            md_lines.append("")
        else:
            for para in text.split("\n\n"):
                para = para.strip()
                if para:
                    md_lines.append(para)
                    md_lines.append("")

    reconstruction = "\n".join(md_lines)

    # --- Review: detect likely interleaving ---
    review_lines = [
        "",
        "---",
        "",
        "# Review: Column / Sidebar Interleaving",
        "",
        "Automated scan for chunks whose **leading line** matches sidebar/TOC labels or that suggest column-order issues.",
        "",
    ]

    interleave_candidates = []
    for i, c in enumerate(spells):
        text = (c.get("text") or "").strip()
        if not text:
            continue
        first_line = text.split("\n")[0].strip()
        if first_line in SIDEBAR_LIKE:
            interleave_candidates.append((i, _page_of(c), first_line, text[:150]))
        # Also flag very short chunks that look like labels (possible sidebar)
        if len(first_line) < 25 and first_line.isupper() and first_line not in SIDEBAR_LIKE:
            if any(first_line.startswith(p) or p.startswith(first_line) for p in SIDEBAR_LIKE):
                interleave_candidates.append((i, _page_of(c), first_line, text[:150]))

    review_lines.append(f"**Chunks with sidebar-like leading line:** {len(interleave_candidates)}")
    review_lines.append("")
    if interleave_candidates:
        review_lines.append("| Index | Page | Leading line | Preview |")
        review_lines.append("|-------|------|--------------|---------|")
        for idx, page, lead, preview in interleave_candidates[:50]:
            preview_esc = preview.replace("|", "\\|").replace("\n", " ")[:80]
            review_lines.append(f"| {idx} | {page} | {lead} | {preview_esc} |")
        if len(interleave_candidates) > 50:
            review_lines.append(f"| ... | ... | ... | (+{len(interleave_candidates) - 50} more) |")
    else:
        review_lines.append("None detected in spells chapter.")
    review_lines.append("")

    # Adjacent chunks with very different section_path (possible column/structural break)
    path_changes = []
    for i in range(len(spells) - 1):
        a, b = spells[i], spells[i + 1]
        path_a = a.get("section_path") or []
        path_b = b.get("section_path") or []
        l1_a = path_a[0] if path_a else ""
        l1_b = path_b[0] if path_b else ""
        if l1_a != l1_b and _page_of(a) == _page_of(b):
            path_changes.append((i, _page_of(a), l1_a[:40], l1_b[:40]))
    review_lines.append(f"**Same-page adjacent chunks with different L1 section_path:** {len(path_changes)}")
    review_lines.append("")
    if path_changes:
        review_lines.append("| Index | Page | L1 (chunk i) | L1 (chunk i+1) |")
        review_lines.append("|-------|------|--------------|----------------|")
        for idx, page, l1a, l1b in path_changes[:30]:
            review_lines.append(f"| {idx} | {page} | {l1a} | {l1b} |")
        if len(path_changes) > 30:
            review_lines.append(f"| ... | ... | ... | (+{len(path_changes) - 30} more) |")
    review_lines.append("")
    review_lines.append("**Conclusion:** If sidebar-like leading lines or many same-page L1 changes appear, column or sidebar interleaving is likely. Reduce by tightening sidebar pruning (right zone, Option B) or by section-path smoothing (hypotheses in Stage A addendum).")
    review_lines.append("")

    out_path = out_dir / "SPELLS-CHAPTER-RECONSTRUCTION.md"
    # Write review first so it appears after the reconstruction when reading top-to-bottom; user asked for reconstruction then review
    full_content = reconstruction + "\n".join(review_lines)
    out_path.write_text(full_content, encoding="utf-8")
    print(f"Wrote {out_path} ({len(spells)} chunks, {len(interleave_candidates)} sidebar-like leads, {len(path_changes)} same-page L1 changes)")


if __name__ == "__main__":
    _main()
