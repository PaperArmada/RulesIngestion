#!/usr/bin/env python3
"""One-off: export gold_reference.json to OLD_GOLD_REFERENCE.md for manual matching."""
import json
from pathlib import Path

REF_PATH = Path(__file__).resolve().parent.parent.parent.parent / "Archive/marker-era/blind_eval/gold_audit/gold_reference.json"
OUT_PATH = Path(__file__).resolve().parent / "OLD_GOLD_REFERENCE.md"

def main():
    ref = json.loads(REF_PATH.read_text(encoding="utf-8"))
    out = []
    out.append("# Old gold chunks (marker-era) — for manual match to Mark III EvidenceUnits")
    out.append("")
    out.append("Source: `Archive/marker-era/blind_eval/gold_audit/gold_reference.json`")
    out.append("Use this text + context to identify which **retrieved** chunk (in `retrieved_chunks.json`) corresponds to each old gold item.")
    out.append("")
    for q in ref["queries"]:
        out.append(f"## {q['query_id']}")
        out.append("")
        out.append(f"**Question:** {q.get('question', '')}")
        out.append("")
        out.append(f"**Expected answer summary:** {q.get('expected_answer_summary', '')}")
        out.append("")
        out.append(f"**Source page (PDF):** {q.get('source_page', '')}")
        out.append("")
        out.append("### Old gold items")
        out.append("")
        for i, g in enumerate(q.get("gold_items", []), 1):
            doc_id = g.get("document_id", "")
            block_path = g.get("block_path", "")
            old_id = f"{doc_id}::{block_path}"
            target = (g.get("target_text") or "").strip()
            out.append(f"#### Gold {i} — `{old_id}`")
            out.append("")
            out.append(f"- **Document:** `{doc_id}` · **Page (in chapter):** {g.get('page', '')} · **Path:** `{block_path}`")
            out.append("")
            out.append("**Target text (match this to a retrieved chunk):**")
            out.append("")
            out.append("```")
            out.append(target)
            out.append("```")
            out.append("")
        out.append("---")
        out.append("")
    OUT_PATH.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"Queries: {len(ref['queries'])}, gold items: {ref['metadata'].get('gold_items_count', '?')}")

if __name__ == "__main__":
    main()
