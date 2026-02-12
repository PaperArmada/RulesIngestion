"""Per-query diagnostics and bucketed scoreboard for retrieval-lab runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def _load_per_query(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("per_query.json must contain model->query list mapping")
    return data


def _scoreboard(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    by_bucket: Dict[str, int] = {}
    by_tier: Dict[str, Dict[str, int]] = {}
    for r in rows:
        bucket = r.get("failure_bucket", "unknown")
        by_bucket[bucket] = by_bucket.get(bucket, 0) + 1
        tier = r.get("tier", "T1")
        if tier not in by_tier:
            by_tier[tier] = {}
        by_tier[tier][bucket] = by_tier[tier].get(bucket, 0) + 1

    no_gold = by_bucket.get("no_gold_defined", 0)
    effective_den = max(n - no_gold, 0)
    not_in_candidates = by_bucket.get("gold_not_in_candidates", 0)
    true_ceiling = 1.0 - (not_in_candidates / effective_den) if effective_den else 0.0
    return {
        "total_queries": n,
        "failure_buckets": by_bucket,
        "by_tier": by_tier,
        "effective_queries_excluding_no_gold": effective_den,
        "gold_in_candidates_true_ceiling": round(true_ceiling, 4),
    }


def _markdown(model: str, sb: Dict[str, Any]) -> str:
    lines = [
        f"# Retrieval Diagnostics: {model}",
        "",
        f"- Total queries: {sb['total_queries']}",
        f"- Effective queries (excluding no_gold_defined): {sb['effective_queries_excluding_no_gold']}",
        f"- Gold-in-candidates (true ceiling): {sb['gold_in_candidates_true_ceiling']}",
        "",
        "## Failure Buckets",
        "",
        "| Bucket | Count |",
        "|--------|-------|",
    ]
    for key in (
        "no_gold_defined",
        "gold_not_in_candidates",
        "gold_in_candidates_but_low_rank",
        "grounding_or_answer_failure_after_retrieval",
        "success",
    ):
        lines.append(f"| {key} | {sb['failure_buckets'].get(key, 0)} |")
    lines.extend(["", "## Tier Breakdown", "", "| Tier | no_gold_defined | gold_not_in_candidates | low_rank | post_retrieval_failure | success |", "|------|------------------|------------------------|----------|------------------------|---------|"])
    for tier in sorted(sb["by_tier"].keys()):
        d = sb["by_tier"][tier]
        lines.append(
            f"| {tier} | {d.get('no_gold_defined', 0)} | {d.get('gold_not_in_candidates', 0)} | "
            f"{d.get('gold_in_candidates_but_low_rank', 0)} | {d.get('grounding_or_answer_failure_after_retrieval', 0)} | {d.get('success', 0)} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate retrieval diagnostics from per_query.json")
    parser.add_argument("--per-query", required=True, help="Path to per_query.json artifact")
    parser.add_argument("--output-dir", required=True, help="Output directory for diagnostics artifacts")
    args = parser.parse_args()

    per_query_path = Path(args.per_query)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = _load_per_query(per_query_path)
    all_out: Dict[str, Any] = {}
    for model, rows in data.items():
        sb = _scoreboard(rows)
        all_out[model] = sb
        md = _markdown(model, sb)
        (out_dir / f"DIAGNOSTICS_{model}.md").write_text(md, encoding="utf-8")
    (out_dir / "diagnostics_summary.json").write_text(json.dumps(all_out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

