"""
Build a Markdown sampling document for Stage B evidence chunks (manual review).
Reads evidence_chunks.json and ungrouped_records.json; writes EVIDENCE-CHUNKS-SAMPLE.md.

Usage:
  uv run python scripts/build_evidence_chunks_sample.py [out/DocName ...]
  If no dirs given, runs for the five diverse-PDF output dirs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_OUT_DIRS = [
    "out/DnD5e-PHB",
    "out/StarFinder2e-AlienCore",
    "out/FateCore-CoreRules",
    "out/SwordsAndWizardry-CoreRules",
    "out/StarFinder2e-PlayerCore-v2",
]

FIRST_N = 15
EVERY_NTH = 40


def _build_sample_md(out_dir: Path) -> str:
    evidence_path = out_dir / "evidence_chunks.json"
    if not evidence_path.exists():
        return ""

    with open(evidence_path, encoding="utf-8") as f:
        data = json.load(f)
    chunks = data.get("evidence_chunks", data) if isinstance(data, dict) else data
    if not chunks:
        chunks = []

    ungrouped_path = out_dir / "ungrouped_records.json"
    ungrouped_count = 0
    if ungrouped_path.exists():
        with open(ungrouped_path, encoding="utf-8") as f:
            ungrouped = json.load(f)
        ungrouped_count = len(ungrouped) if isinstance(ungrouped, list) else 0

    kind_counts: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    for c in chunks:
        k = c.get("kind", "?")
        kind_counts[k] = kind_counts.get(k, 0) + 1
        r = c.get("grouping_rule_id", "?")
        rule_counts[r] = rule_counts.get(r, 0) + 1

    # Sample indices: first N, then every Nth
    total = len(chunks)
    indices = set(range(min(FIRST_N, total)))
    for i in range(0, total, EVERY_NTH):
        indices.add(i)
    sampled = sorted(indices)

    lines = [
        f"# Evidence Chunks Sample: {out_dir.name}",
        "",
        "Stage B output: grouped evidence chunks for retrieval/grounding. Use this doc to manually review grouping quality and content.",
        "",
        "## Counts",
        "",
        f"- **Evidence chunks:** {total}",
        f"- **Ungrouped records:** {ungrouped_count}",
        f"- **Kind:** " + ", ".join(f"{k}={v}" for k, v in sorted(kind_counts.items())),
        f"- **Grouping rule:** " + ", ".join(f"{r}={v}" for r, v in sorted(rule_counts.items())),
        "",
        "## Sampled evidence chunks",
        "",
        f"Showing: first {FIRST_N}, then every {EVERY_NTH}th. Full text (no truncation).",
        "",
    ]

    for idx in sampled:
        if idx >= total:
            continue
        c = chunks[idx]
        eid = (c.get("evidence_chunk_id") or "")[:14]
        kind = c.get("kind", "?")
        rule = c.get("grouping_rule_id", "?")
        stop = c.get("grouping_stop_reason", "?")
        section_path = c.get("section_path") or []
        sp = " → ".join(section_path) if section_path else "(none)"
        page_indices = c.get("page_indices") or []
        source_ids = c.get("source_chunk_ids") or []
        text = (c.get("text") or "").strip()
        structural_meta = c.get("structural_metadata") or {}
        meta_flags = ", ".join(f"{k}={v}" for k, v in structural_meta.items()) if structural_meta else ""

        lines.append("---")
        lines.append("")
        lines.append(f"### [{idx + 1}] `{eid}`")
        lines.append("")
        lines.append(f"- **Kind:** {kind}  **Rule:** {rule}  **Stop:** {stop}")
        lines.append(f"- **Section:** `{sp}`")
        lines.append(f"- **Pages:** {page_indices}  **Source chunks:** {len(source_ids)}")
        if meta_flags:
            lines.append(f"- **Structural flags:** {meta_flags}")
        lines.append("")
        lines.append(text)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*End of sample. Full data: evidence_chunks.json, ungrouped_records.json.*")
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
        md = _build_sample_md(out_dir)
        if not md:
            print(f"Skip (no evidence_chunks.json): {out_dir}", file=sys.stderr)
            continue
        out_path = out_dir / "EVIDENCE-CHUNKS-SAMPLE.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
