#!/usr/bin/env python3
"""
Convert blind_eval batch JSONs to harness evaluation_queries format and prepare
a run directory with merged.evaluation_queries.json + merged.enriched.json so the
ruleslawyer evaluation harness can run on the same 50 queries as rule_fact_benchmark_eval.

Usage:
  cd RulesIngestion && uv run python scripts/convert_blind_eval_to_harness_queries.py

Output:
  blind_eval/harness_50q/merged.evaluation_queries.json
  blind_eval/harness_50q/merged.enriched.json (copy or symlink from PlayerCore run)
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    batches_dir = repo / "blind_eval" / "batches"
    out_dir = repo / "blind_eval" / "harness_50q"
    out_dir.mkdir(parents=True, exist_ok=True)

    batch_files = [
        "batch_001.json",
        "batch_002_state.json",
        "batch_003_grounding.json",
        "batch_004_temporal.json",
        "batch_005_constraints.json",
        "batch_006_conceptual.json",
    ]

    queries: list[dict] = []
    for name in batch_files:
        path = batches_dir / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for q in data.get("queries", []):
            queries.append({
                "id": q.get("id", ""),
                "query_text": q.get("question", ""),
                "query_text_short": (q.get("question") or "")[:200],
                "expected_chunk_ids": list(q.get("gold_chunk_ids", [])),
                "document_id": "merged",
            })

    eval_payload = {
        "document": "merged",
        "queries": queries,
    }
    queries_path = out_dir / "merged.evaluation_queries.json"
    with open(queries_path, "w", encoding="utf-8") as f:
        json.dump(eval_payload, f, indent=2)
    print(f"Wrote {len(queries)} queries to {queries_path}")

    # Enriched chunks: use same corpus as rule_fact_benchmark_eval default base-path
    enriched_src = repo / "Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json"
    enriched_dst = out_dir / "merged.enriched.json"
    if enriched_src.exists():
        shutil.copy2(enriched_src, enriched_dst)
        print(f"Copied enriched chunks to {enriched_dst}")
    else:
        print(f"Warning: {enriched_src} not found; create merged.enriched.json in {out_dir} manually")

    print(f"Harness run dir: {out_dir}")
    print("Run with: --run-outputs-dir " + str(out_dir.absolute()))


if __name__ == "__main__":
    main()
