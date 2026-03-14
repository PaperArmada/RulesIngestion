#!/usr/bin/env python3
"""Bootstrap confidence intervals for hybrid-vs-dense deltas."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mrr_from_rank(rank: Any) -> float:
    try:
        r = int(rank)
    except Exception:
        return 0.0
    return 1.0 / r if r > 0 else 0.0


def _r10_from_row(row: Dict[str, Any]) -> float:
    recall = row.get("recall_at_k") or {}
    return float(recall.get("10", 0.0))


def _bootstrap_mean_ci(values: List[float], samples: int, seed: int) -> Tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means: List[float] = []
    for _ in range(samples):
        acc = 0.0
        for _ in range(n):
            acc += values[rng.randrange(n)]
        means.append(acc / n)
    means.sort()
    lo_idx = int(0.025 * (samples - 1))
    hi_idx = int(0.975 * (samples - 1))
    point = sum(values) / n
    return point, means[lo_idx], means[hi_idx]


def _load_model_per_query(output_dir: Path, model: str) -> Dict[str, Dict[str, Any]]:
    path = output_dir / "per_query.json"
    if not path.exists():
        return {}
    payload = _load_json(path)
    rows = payload.get(model) if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        qid = str(row.get("query_id", ""))
        if qid:
            out[qid] = row
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap CIs for hybrid-vs-dense deltas")
    parser.add_argument("--manifest", required=True, help="Sweep manifest path")
    parser.add_argument("--track", default="swcr", help="Track to bootstrap (default: swcr)")
    parser.add_argument("--samples", type=int, default=2000, help="Bootstrap samples")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out-json", required=True, help="Output bootstrap JSON path")
    args = parser.parse_args()

    manifest = _load_json(Path(args.manifest))
    runs = manifest.get("runs", [])
    dense_by_model: Dict[str, Path] = {}
    for run in runs:
        if run.get("track") == args.track and run.get("variant") == "dense":
            dense_by_model[str(run.get("model", ""))] = Path(str(run.get("output_dir", "")))

    results: List[Dict[str, Any]] = []
    for run in runs:
        if run.get("track") != args.track or run.get("variant") == "dense":
            continue
        model = str(run.get("model", ""))
        dense_dir = dense_by_model.get(model)
        if not dense_dir:
            continue
        cur_dir = Path(str(run.get("output_dir", "")))
        base_rows = _load_model_per_query(dense_dir, model)
        cur_rows = _load_model_per_query(cur_dir, model)
        qids = sorted(set(base_rows.keys()) & set(cur_rows.keys()))
        if not qids:
            continue

        delta_mrr: List[float] = []
        delta_r10: List[float] = []
        for qid in qids:
            b = base_rows[qid]
            c = cur_rows[qid]
            delta_mrr.append(_mrr_from_rank(c.get("first_gold_rank")) - _mrr_from_rank(b.get("first_gold_rank")))
            delta_r10.append(_r10_from_row(c) - _r10_from_row(b))

        mrr_point, mrr_lo, mrr_hi = _bootstrap_mean_ci(delta_mrr, args.samples, args.seed)
        r10_point, r10_lo, r10_hi = _bootstrap_mean_ci(delta_r10, args.samples, args.seed + 1)
        results.append(
            {
                "track": args.track,
                "model": model,
                "normalization": run.get("normalization", ""),
                "lambda": run.get("lambda", ""),
                "budget": run.get("budget", ""),
                "bm25_enrichment_profile": run.get("bm25_enrichment_profile", ""),
                "output_dir": str(cur_dir),
                "n_queries": len(qids),
                "delta_mrr_mean": mrr_point,
                "delta_mrr_ci95_lo": mrr_lo,
                "delta_mrr_ci95_hi": mrr_hi,
                "delta_r10_mean": r10_point,
                "delta_r10_ci95_lo": r10_lo,
                "delta_r10_ci95_hi": r10_hi,
            }
        )

    out = {
        "track": args.track,
        "samples": args.samples,
        "seed": args.seed,
        "rows": sorted(
            results,
            key=lambda r: (
                r["model"],
                str(r["normalization"]),
                str(r["lambda"]),
                str(r["budget"]),
                str(r["bm25_enrichment_profile"]),
            ),
        ),
    }
    out_path = Path(args.out_json)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote bootstrap rows: {len(out['rows'])} -> {out_path}")


if __name__ == "__main__":
    main()
