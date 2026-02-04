#!/usr/bin/env python3
"""
Export benchmark gold chunks to an audit file for evaluation and reboot-safe storage.

Loads all blind_eval batches and the enriched corpus; for each (query, gold_chunk_id)
resolves the chunk and emits document position + full text. Output is suitable for:
1) Human review (is this chunk a good gold? keep/trim/expand/drop + target_text)
2) Building a retrieval-reboot-safe gold reference (document_id + page + target_text).

Usage:
  uv run python blind_eval/scripts/export_gold_audit.py
  uv run python blind_eval/scripts/export_gold_audit.py --enriched path/to/merged.enriched.json --out-dir blind_eval/gold_audit --review-md
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Chunk ID format: {document_id}::/page/N/BlockType/M
CHUNK_ID_PATH_RE = re.compile(r"^(.+?)::(/page/\d+/[^/]+/\d+)$")


def parse_chunk_id(chunk_id: str) -> tuple[str, int | None, str]:
    """Extract document_id, page number, and block_path from chunk_id.
    Returns (document_id, page or None, block_path). block_path is e.g. /page/9/Text/12.
    """
    m = CHUNK_ID_PATH_RE.match(chunk_id.strip())
    if not m:
        return (chunk_id, None, "")
    doc_id, path = m.group(1), m.group(2)
    # /page/9/Text/12 -> page 9
    page_match = re.search(r"/page/(\d+)/", path)
    page = int(page_match.group(1)) if page_match else None
    return (doc_id, page, path)


def load_enriched(enriched_path: Path) -> list[dict[str, Any]]:
    """Load enriched chunks from JSON (list or dict with 'chunks' key)."""
    with open(enriched_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "chunks" in data:
        return data["chunks"]
    raise ValueError(f"Unknown format in {enriched_path}")


def load_batches(batches_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    """Load all batch_*.json files. Returns list of (batch_path.name, batch_dict)."""
    batches = []
    for p in sorted(batches_dir.glob("batch_*.json")):
        with open(p, encoding="utf-8") as f:
            batch = json.load(f)
        batches.append((p.name, batch))
    return batches


def build_audit(
    batches: list[tuple[str, dict[str, Any]]],
    chunk_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build gold_items list and gaps (missing chunk ids)."""
    gold_items: list[dict[str, Any]] = []
    gaps: list[str] = []

    for batch_name, batch in batches:
        metadata = batch.get("metadata", {})
        batch_id = metadata.get("batch_id", batch_name.replace("batch_", "").replace(".json", ""))
        queries = batch.get("queries", [])
        for q in queries:
            query_id = q.get("id", "")
            question = q.get("question", "")
            expected = q.get("expected_answer_summary", "")
            source_page = q.get("source_page")
            gold_chunk_ids = list(q.get("gold_chunk_ids", []))
            if not query_id or not question or not gold_chunk_ids:
                continue
            for cid in gold_chunk_ids:
                cid = cid.strip()
                doc_id, page, block_path = parse_chunk_id(cid)
                chunk = chunk_by_id.get(cid)
                if chunk is None:
                    gaps.append(cid)
                    gold_items.append({
                        "query_id": query_id,
                        "batch_id": batch_id,
                        "question": question,
                        "expected_answer_summary": expected,
                        "source_page": source_page,
                        "chunk_id": cid,
                        "document_id": doc_id,
                        "page": page,
                        "block_path": block_path,
                        "section_path": [],
                        "chunk_text": "",
                        "evaluation_status": "pending",
                        "target_text": None,
                        "reviewer_notes": None,
                    })
                else:
                    section_path = chunk.get("section_path") or []
                    gold_items.append({
                        "query_id": query_id,
                        "batch_id": batch_id,
                        "question": question,
                        "expected_answer_summary": expected,
                        "source_page": source_page,
                        "chunk_id": cid,
                        "document_id": chunk.get("document_id") or doc_id,
                        "page": page,
                        "block_path": block_path,
                        "section_path": section_path,
                        "chunk_text": chunk.get("text", ""),
                        "evaluation_status": "pending",
                        "target_text": None,
                        "reviewer_notes": None,
                    })
    return gold_items, gaps


def write_review_md(gold_items: list[dict[str, Any]], out_path: Path) -> None:
    """Write a human-friendly Markdown file for reviewing each (query, chunk)."""
    lines = [
        "# Gold chunk audit – review",
        "",
        "For each block: confirm the chunk is a **good** gold (supports the answer).",
        "- **keep** – Chunk clearly supports the answer; use full text as target_text or a tight substring.",
        "- **trim** – Only part of the chunk is gold; set target_text to that portion.",
        "- **expand** – Chunk is relevant but too narrow; ideal gold would include adjacent context (e.g. header + body). Note in reviewer_notes.",
        "- **drop** – Irrelevant or wrong; will not appear in gold reference.",
        "",
        "After review, set `evaluation_status` and `target_text` in `gold_audit.json` (or re-export from this workflow).",
        "",
        "---",
        "",
    ]
    current_query = None
    for i, item in enumerate(gold_items):
        qid = item.get("query_id", "")
        if qid != current_query:
            current_query = qid
            lines.append(f"## {qid}")
            lines.append("")
            lines.append(f"**Question:** {item.get('question', '')}")
            lines.append("")
            lines.append(f"**Expected answer summary:** {item.get('expected_answer_summary', '')}")
            lines.append("")
        lines.append(f"### Gold chunk {i + 1} – `{item.get('chunk_id', '')}`")
        lines.append("")
        lines.append(f"- **Document:** `{item.get('document_id', '')}` · **Page:** {item.get('page', '?')} · **Path:** `{item.get('block_path', '')}`")
        lines.append("")
        chunk_text = item.get("chunk_text", "")
        if chunk_text:
            lines.append("**Chunk text:**")
            lines.append("")
            lines.append("```")
            lines.append(chunk_text)  # full chunk; no truncation
            lines.append("```")
        else:
            lines.append("*Chunk not found in enriched (missing).*")
        lines.append("")
        status = item.get("evaluation_status") or "pending"
        notes = item.get("reviewer_notes")
        target = item.get("target_text")
        status_line = f"**Status:** {status}"
        if notes:
            status_line += f" · **Notes:** {notes}"
        if target:
            status_line += f" · **target_text:** {target!r}"
        else:
            status_line += " · **target_text:** (optional substring)"
        lines.append(status_line)
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export benchmark gold chunks to audit JSON (+ optional review Markdown); or build gold_reference from audit.",
    )
    parser.add_argument(
        "--build-reference",
        action="store_true",
        help="Build gold_reference.json from an existing gold_audit.json (after review).",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        help="Path to gold_audit.json (for --build-reference).",
    )
    parser.add_argument(
        "--batches-dir",
        type=Path,
        default=Path("blind_eval/batches"),
        help="Directory containing batch_*.json",
    )
    parser.add_argument(
        "--enriched",
        type=Path,
        default=Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json"),
        help="Path to merged.enriched.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("blind_eval/gold_audit"),
        help="Output directory for gold_audit.json and optional review.md",
    )
    parser.add_argument(
        "--review-md",
        action="store_true",
        help="Also write gold_audit_review.md for human review",
    )
    parser.add_argument(
        "--review-only",
        action="store_true",
        help="Load existing gold_audit.json and only regenerate gold_audit_review.md (does not overwrite audit)",
    )
    parser.add_argument(
        "--pdf-source",
        type=str,
        default="PZO22003_PlayerCore.pdf",
        help="PDF source name for gold_reference metadata",
    )
    args = parser.parse_args()

    if args.build_reference:
        audit_path = args.audit or (Path("blind_eval/gold_audit") / "gold_audit.json")
        if not audit_path.exists():
            raise SystemExit(f"Audit file not found: {audit_path}")
        out_path = audit_path.parent / "gold_reference.json"
        build_gold_reference(audit_path, out_path, pdf_source=args.pdf_source)
        return

    if args.review_only:
        out_dir = args.out_dir
        audit_path = out_dir / "gold_audit.json"
        if not audit_path.exists():
            raise SystemExit(f"Audit file not found: {audit_path}")
        with open(audit_path, encoding="utf-8") as f:
            audit = json.load(f)
        gold_items = audit.get("gold_items", [])
        review_path = out_dir / "gold_audit_review.md"
        write_review_md(gold_items, review_path)
        print(f"Wrote {review_path} ({len(gold_items)} items)")
        return

    # Export mode
    batches_dir = args.batches_dir
    enriched_path = args.enriched
    out_dir = args.out_dir

    if not batches_dir.exists():
        raise SystemExit(f"Batches dir not found: {batches_dir}")
    if not enriched_path.exists():
        raise SystemExit(f"Enriched file not found: {enriched_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = load_enriched(enriched_path)
    chunk_by_id = {c.get("id"): c for c in chunks if c.get("id")}
    batches = load_batches(batches_dir)
    batch_names = [b[0] for b in batches]

    gold_items, gaps = build_audit(batches, chunk_by_id)

    metadata = {
        "enriched_path": str(enriched_path),
        "batches": batch_names,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_gold_items": len(gold_items),
        "missing_chunks": len(gaps),
    }

    audit = {
        "metadata": metadata,
        "gold_items": gold_items,
        "gaps": gaps,
    }

    audit_path = out_dir / "gold_audit.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(f"Wrote {audit_path} ({len(gold_items)} gold items, {len(gaps)} missing chunks)")

    if args.review_md:
        review_path = out_dir / "gold_audit_review.md"
        write_review_md(gold_items, review_path)
        print(f"Wrote {review_path}")

    if gaps:
        print(f"Gaps (chunk ids not in enriched): {gaps[:5]}{'...' if len(gaps) > 5 else ''}")


def build_gold_reference(audit_path: Path, out_path: Path, pdf_source: str = "PZO22003_PlayerCore.pdf") -> None:
    """Read gold_audit.json; filter to evaluation_status in (keep, trim, expand); write gold_reference.json (reboot-safe)."""
    with open(audit_path, encoding="utf-8") as f:
        audit = json.load(f)
    gold_items: list[dict[str, Any]] = audit.get("gold_items", [])
    accepted = [g for g in gold_items if g.get("evaluation_status") in ("keep", "trim", "expand")]
    # Group by query_id (only accepted items)
    by_query: dict[str, list[dict[str, Any]]] = {}
    for g in accepted:
        qid = g.get("query_id", "")
        if qid not in by_query:
            by_query[qid] = []
        by_query[qid].append(g)
    # Build query-centric reference (only queries that have at least one accepted gold)
    queries_out = []
    for qid, items_for_query in by_query.items():
        first = items_for_query[0]
        gold_refs = [
            {
                "document_id": it.get("document_id"),
                "page": it.get("page"),
                "block_path": it.get("block_path"),
                "target_text": (it.get("target_text") or "").strip() or (it.get("chunk_text", "") or "").strip(),
            }
            for it in items_for_query
        ]
        queries_out.append({
            "query_id": qid,
            "batch_id": first.get("batch_id"),
            "question": first.get("question"),
            "expected_answer_summary": first.get("expected_answer_summary"),
            "source_page": first.get("source_page"),
            "gold_items": gold_refs,
        })
    ref = {
        "metadata": {
            "pdf_source": pdf_source,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "from_audit": str(audit_path),
            "queries_count": len(queries_out),
            "gold_items_count": len(accepted),
        },
        "queries": queries_out,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ref, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path} ({len(queries_out)} queries, {len(accepted)} gold items)")


if __name__ == "__main__":
    main()
