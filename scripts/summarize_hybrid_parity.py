#!/usr/bin/env python3
"""Summarize hybrid parity sweep outputs into CSV/JSON."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from retrieval_lab.artifact_resolution import load_resolved_json_artifact


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_rows(manifest_path: Path) -> List[Dict[str, Any]]:
    manifest = _load_json(manifest_path)
    rows: List[Dict[str, Any]] = []
    for item in manifest.get("runs", []):
        out_dir = Path(item.get("output_dir", ""))
        metrics = load_resolved_json_artifact(out_dir, "metrics")
        if not isinstance(metrics, dict):
            continue
        for model_id, model_metrics in metrics.items():
            row = {
                "track": item.get("track", ""),
                "variant": item.get("variant", ""),
                "model": model_id,
                "normalization": item.get("normalization", ""),
                "lambda": item.get("lambda", ""),
                "budget": item.get("budget", ""),
                "bm25_enrichment_profile": item.get("bm25_enrichment_profile", ""),
                "output_dir": str(out_dir),
                "mrr": _to_float(model_metrics.get("mrr", 0.0)),
                "r10": _to_float((model_metrics.get("recall_at_k") or {}).get("10", 0.0)),
                "h10": _to_float((model_metrics.get("hit_at_k") or {}).get("10", 0.0)),
                "req_fsh10": _to_float((model_metrics.get("required_full_set_hit_at_k") or {}).get("10", 0.0)),
            }
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize hybrid parity sweep results")
    parser.add_argument("--manifest", required=True, help="Path to sweep manifest JSON")
    parser.add_argument("--out-csv", required=True, help="Path to output CSV")
    parser.add_argument("--out-json", required=True, help="Path to output JSON")
    args = parser.parse_args()

    rows = build_rows(Path(args.manifest))
    rows.sort(
        key=lambda r: (
            r["track"],
            r["model"],
            r["variant"],
            str(r["normalization"]),
            str(r["lambda"]),
            str(r["budget"]),
            str(r["bm25_enrichment_profile"]),
        )
    )

    out_json = Path(args.out_json)
    out_csv = Path(args.out_csv)
    out_json.write_text(json.dumps({"rows": rows}, indent=2), encoding="utf-8")

    fieldnames = [
        "track",
        "variant",
        "model",
        "normalization",
        "lambda",
        "budget",
        "bm25_enrichment_profile",
        "mrr",
        "r10",
        "h10",
        "req_fsh10",
        "output_dir",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_csv}")
    print(f"Wrote JSON to {out_json}")


if __name__ == "__main__":
    main()
