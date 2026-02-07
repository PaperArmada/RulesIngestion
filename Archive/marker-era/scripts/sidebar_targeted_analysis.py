"""
Analyze fresh extraction for sidebar pruning: target sections we know had
interwoven sidebar content (pages 76, 80, 94, 114–119, 330–363).
Writes SIDEBAR-TARGETED-ANALYSIS.md into the output dir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "out" / "StarFinder2e-PlayerCore-v2"

# Sections we've been examining for sidebar interleaving (conversation + SAMPLE-CHUNKS-FOR-REVIEW)
MANUAL_REVIEW_PAGES = {76, 80, 94, 114, 115, 116, 119}
SPELLS_CHAPTER_PAGES = set(range(330, 364))
TARGET_PAGES = MANUAL_REVIEW_PAGES | SPELLS_CHAPTER_PAGES

# Sidebar-like text that should NOT appear as sole or leading content in main-column chunks
SIDEBAR_LIKE_PATTERNS = (
    "INTRODUCTION",
    "ANCESTRIES & BACKGROUNDS",
    "13TH LEVEL",
    "5TH LEVEL",
    "SKITTERMANDER",
    "Android",
    "Barathu",
    "Human",
    "Kasatha",
    "Lashunta",
    "Pahtra",
    "Shirren",
    "Skittermander",
)


def _main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR
    chunks_path = out_dir / "chunks.json"
    drop_path = out_dir / "drop_records.json"
    if not chunks_path.exists():
        print(f"Missing {chunks_path}", file=sys.stderr)
        sys.exit(1)
    if not drop_path.exists():
        print(f"Missing {drop_path}", file=sys.stderr)
        sys.exit(1)

    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)
    with open(drop_path, encoding="utf-8") as f:
        drop_records = json.load(f)

    # Drop summary by reason
    by_reason: dict[str, int] = {}
    for d in drop_records:
        r = d.get("reason_code", "unknown")
        by_reason[r] = by_reason.get(r, 0) + 1

    # Sidebar drops by page (logical page from block_reference "page=N,ord=...")
    sidebar_drops_by_page: dict[int, int] = {}
    for d in drop_records:
        if d.get("reason_code") != "sidebar":
            continue
        page = d.get("page_index")
        if page is not None:
            sidebar_drops_by_page[page] = sidebar_drops_by_page.get(page, 0) + 1

    # Chunks use logical_page_index (or page_index for legacy)
    def page_of(c: dict) -> int:
        return c.get("logical_page_index", c.get("page_index", -1))

    target_chunks = [c for c in chunks if page_of(c) in TARGET_PAGES]
    manual_chunks = [c for c in chunks if page_of(c) in MANUAL_REVIEW_PAGES]
    spells_chunks = [c for c in chunks if page_of(c) in SPELLS_CHAPTER_PAGES]

    # Chunks that look like sidebar-only (text is exactly or starts with a sidebar-like label)
    def chunk_starts_like_sidebar(c: dict) -> bool:
        text = (c.get("text") or "").strip()
        if not text:
            return False
        first_line = text.split("\n")[0].strip()
        return first_line in SIDEBAR_LIKE_PATTERNS or any(
            first_line == p or first_line.startswith(p + "\n") for p in SIDEBAR_LIKE_PATTERNS
        )

    def chunk_contains_sidebar_leading(c: dict) -> list[str]:
        """Return list of sidebar-like patterns found as leading/standalone in chunk text."""
        text = (c.get("text") or "").strip()
        if not text:
            return []
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        found = []
        for p in SIDEBAR_LIKE_PATTERNS:
            if any(line == p or line.startswith(p + " ") for line in lines[:3]):
                found.append(p)
        return found

    suspicious = [c for c in target_chunks if chunk_contains_sidebar_leading(c)]
    suspicious_standalone = [c for c in target_chunks if chunk_starts_like_sidebar(c)]

    # Build report
    lines = [
        "# Sidebar-targeted analysis (fresh extraction)",
        "",
        "**Target sections:** manual-review pages (76, 80, 94, 114, 115, 116, 119) and spells chapter (330–363).",
        "",
        "---",
        "",
        "## 1. Extraction overview",
        "",
        f"- **Total chunks:** {len(chunks)}",
        f"- **Total drop records:** {len(drop_records)}",
        "",
        "### Drop records by reason",
        "",
    ]
    for reason, count in sorted(by_reason.items(), key=lambda x: -x[1]):
        lines.append(f"- `{reason}`: {count}")
    lines.extend([
        "",
        "---",
        "",
        "## 2. Sidebar drops on target pages",
        "",
    ])
    for page in sorted(TARGET_PAGES):
        n = sidebar_drops_by_page.get(page, 0)
        lines.append(f"- **Page {page}:** {n} blocks dropped as sidebar")
    lines.extend([
        "",
        "**Total sidebar drops on target pages:** " + str(sum(sidebar_drops_by_page.get(p, 0) for p in TARGET_PAGES)),
        "",
        "---",
        "",
        "## 3. Chunks in target sections",
        "",
        f"- **Manual-review pages (76, 80, 94, 114–119):** {len(manual_chunks)} chunks",
        f"- **Spells chapter (330–363):** {len(spells_chunks)} chunks",
        f"- **All target pages:** {len(target_chunks)} chunks",
        "",
        "---",
        "",
        "## 4. Sidebar-like text in chunks (sanity check)",
        "",
        "Chunks whose **leading** text matches known sidebar labels (INTRODUCTION, ANCESTRIES & BACKGROUNDS, etc.) "
        "should be absent or rare after pruning.",
        "",
        f"- **Chunks with any sidebar-like pattern in first 3 lines:** {len(suspicious)}",
        f"- **Chunks that are effectively sidebar-only (first line = label):** {len(suspicious_standalone)}",
        "",
    ])
    if suspicious_standalone:
        lines.append("### Chunks that look sidebar-only (first line = sidebar label)")
        lines.append("")
        for c in suspicious_standalone[:20]:
            pg = page_of(c)
            preview = (c.get("text") or "")[:120].replace("\n", " ")
            lines.append(f"- Page {pg} — `{preview}...`")
        if len(suspicious_standalone) > 20:
            lines.append(f"- ... and {len(suspicious_standalone) - 20} more")
        lines.append("")
    if suspicious and len(suspicious) <= 30:
        lines.append("### Chunks containing sidebar-like leading lines")
        lines.append("")
        for c in suspicious[:15]:
            pg = page_of(c)
            hits = chunk_contains_sidebar_leading(c)
            preview = (c.get("text") or "")[:100].replace("\n", " ")
            lines.append(f"- Page {pg} — patterns: {hits} — `{preview}...`")
        lines.append("")
    lines.extend([
        "---",
        "",
        "## 5. Sample chunks — manual-review pages (76, 80, 94, 114–119)",
        "",
    ])
    for page in sorted(MANUAL_REVIEW_PAGES):
        on_page = [c for c in manual_chunks if page_of(c) == page]
        lines.append(f"### Page {page} ({len(on_page)} chunks)")
        lines.append("")
        for i, c in enumerate(on_page[:5], 1):
            text = (c.get("text") or "").strip()
            preview = text[:200] + ("..." if len(text) > 200 else "")
            block_type = c.get("block_type", "?")
            lines.append(f"**Chunk {i}** (block_type={block_type})")
            lines.append(f"- {preview}")
            lines.append("")
        if len(on_page) > 5:
            lines.append(f"*... and {len(on_page) - 5} more chunks on this page.*")
            lines.append("")
    lines.extend([
        "---",
        "",
        "## 6. Sample chunks — spells chapter (330–363)",
        "",
    ])
    # First 3 pages of spells + one from middle
    sample_spell_pages = [330, 331, 332, 340, 350]
    for page in sample_spell_pages:
        on_page = [c for c in spells_chunks if page_of(c) == page]
        if not on_page:
            continue
        lines.append(f"### Page {page} ({len(on_page)} chunks)")
        lines.append("")
        for i, c in enumerate(on_page[:4], 1):
            text = (c.get("text") or "").strip()
            preview = text[:220] + ("..." if len(text) > 220 else "")
            block_type = c.get("block_type", "?")
            lines.append(f"**Chunk {i}** (block_type={block_type})")
            lines.append(f"- {preview}")
            lines.append("")
        if len(on_page) > 4:
            lines.append(f"*... and {len(on_page) - 4} more.*")
            lines.append("")
    lines.append("---")
    lines.append("")
    report_path = out_dir / "SIDEBAR-TARGETED-ANALYSIS.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    _main()
