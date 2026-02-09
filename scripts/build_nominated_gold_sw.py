#!/usr/bin/env python3
"""
Build nominated-gold file for Swords & Wizardry from a retrieval lab run.

Usage:
  uv run python scripts/build_nominated_gold_sw.py out/retrieval_lab/experiments/swords_wizardry_baseline_<timestamp>

Reads retrieved_chunks.json from the experiment dir, takes the first model's
per-query retrieved list (up to 50 chunks), and writes
evals/retrieval/SwordsandWizardy/nominated_gold_per_query.json for manual review.
Each query gets: query_id, question, expected_answer_summary, nominated chunks
(rank, chunk_id, score, text_snippet), and empty gold_unit_ids to fill after review.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SNIPPET_LEN = 2200  # Slightly above merge_max_chars so merged chunks are shown in full
OUT_PATH = Path("evals/retrieval/SwordsandWizardy/nominated_gold_per_query.json")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: build_nominated_gold_sw.py <experiment_dir>", file=sys.stderr)
        sys.exit(1)
    exp_dir = Path(sys.argv[1])
    if not exp_dir.is_dir():
        print(f"Not a directory: {exp_dir}", file=sys.stderr)
        sys.exit(1)
    chunks_path = exp_dir / "retrieved_chunks.json"
    if not chunks_path.exists():
        print(f"Missing {chunks_path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(chunks_path.read_text(encoding="utf-8"))
    by_model = data.get("by_model", {})
    if not by_model:
        print("No by_model in retrieved_chunks.json", file=sys.stderr)
        sys.exit(1)
    model_id = next(iter(by_model))
    query_reviews = by_model[model_id]

    out_queries = []
    for qr in query_reviews:
        nominated = []
        for r in qr.get("retrieved", []):
            text = r.get("text", "")
            snippet = (text[:SNIPPET_LEN] + "…") if len(text) > SNIPPET_LEN else text
            nominated.append({
                "rank": r.get("rank"),
                "chunk_id": r.get("chunk_id"),
                "score": r.get("score"),
                "text_snippet": snippet,
            })
        out_queries.append({
            "query_id": qr.get("query_id", ""),
            "question": qr.get("question", ""),
            "expected_answer_summary": qr.get("expected_answer_summary", ""),
            "nominated": nominated,
            "gold_unit_ids": [],
        })

    out_doc = {
        "source_experiment_dir": str(exp_dir.resolve()),
        "model_id": model_id,
        "instructions": "Fill gold_unit_ids per query with chunk_ids that are true gold; then run: uv run python scripts/apply_nominated_gold_sw.py",
        "queries": out_queries,
    }

    out_path = Path(OUT_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_doc, indent=2), encoding="utf-8")
    n_nom = len(out_queries[0]["nominated"]) if out_queries else 0
    print(f"Wrote {out_path} ({len(out_queries)} queries, up to {n_nom} nominated per query)")

    # Write REVIEW_INSTRUCTIONS into the experiment dir for this run
    review_md = exp_dir / "REVIEW_INSTRUCTIONS.md"
    review_md.write_text(
        "# Swords & Wizardry: nominated gold review\n\n"
        "This run retrieved **50 chunks per query** for gold nomination.\n\n"
        "1. **Nominated file (fill gold there):**  \n"
        f"   `{out_path}`  \n"
        "   For each query, set `gold_unit_ids` to the list of `chunk_id` values that are true gold (copy from the `nominated` list).\n\n"
        "2. **Full instructions:**  \n"
        "   `evals/retrieval/SwordsandWizardy/MANUAL_REVIEW.md`\n\n"
        "3. **Apply gold to benchmark:**  \n"
        "   `uv run python scripts/apply_nominated_gold_sw.py`\n\n"
        "4. **Re-run retrieval** with the same config and run-id for benchmark metrics.\n",
        encoding="utf-8",
    )
    print(f"Wrote {review_md}")


if __name__ == "__main__":
    main()
