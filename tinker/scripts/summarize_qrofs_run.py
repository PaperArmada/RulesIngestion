"""Summarize a q-ROFS classifier run.

Prints per-bucket mean(mu)/mean(nu)/p95(mu), hesitation and margin
distributions, and a list of low-margin (ambiguous) queries that the
router may want to handle with a multi-path strategy.

Usage:
  uv run python -m tinker.scripts.summarize_qrofs_run \\
      out/tinker/swcr/runs/m2_qrofs/classifier_predict_qrofs.json
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[max(0, min(len(s) - 1, int(q * len(s)) - 1))]


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a q-ROFS classifier run.")
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--ambiguous-margin",
        type=float,
        default=0.15,
        help="Margin threshold below which a query is flagged as ambiguous (default 0.15).",
    )
    args = parser.parse_args()

    data = json.loads(args.report.read_text())
    preds = data["predictions"]
    print(f"Report: {args.report}")
    print(f"Queries: {len(preds)}")
    if "model" in data:
        print(f"Model:   {data['model']}")
    print(f"Total elapsed: {data.get('total_elapsed_sec', '?')}s")
    print()

    by_bucket_mu: dict[str, list[float]] = collections.defaultdict(list)
    by_bucket_nu: dict[str, list[float]] = collections.defaultdict(list)
    for p in preds:
        for bid, m in p.get("memberships", {}).items():
            by_bucket_mu[bid].append(m["mu"])
            by_bucket_nu[bid].append(m["nu"])

    print(f"{'bucket':<30s} mean_mu  mean_nu  p95_mu")
    print("-" * 60)
    for bid in sorted(by_bucket_mu, key=lambda b: -statistics.mean(by_bucket_mu[b])):
        mu_list = by_bucket_mu[bid]
        nu_list = by_bucket_nu[bid]
        print(
            f"  {bid:<28s} {statistics.mean(mu_list):.3f}    "
            f"{statistics.mean(nu_list):.3f}    {_percentile(mu_list, 0.95):.2f}"
        )

    print()
    pis = [p["chosen_pi"] for p in preds]
    margins = [p["margin"] for p in preds]
    latencies = [p["latency_ms"] for p in preds if not p.get("cached")]
    print("Hesitation (chosen bucket):")
    print(
        f"  mean={statistics.mean(pis):.3f}  median={statistics.median(pis):.3f}  "
        f"min={min(pis):.3f}  max={max(pis):.3f}"
    )
    print("Margin (chosen mu - second mu):")
    print(
        f"  mean={statistics.mean(margins):.3f}  median={statistics.median(margins):.3f}  "
        f"min={min(margins):.3f}  max={max(margins):.3f}"
    )
    if latencies:
        print("Latency (uncached, ms):")
        print(
            f"  p50={_percentile(latencies, 0.50):.0f}  "
            f"p95={_percentile(latencies, 0.95):.0f}  "
            f"max={max(latencies):.0f}"
        )

    print()
    print("Bucket distribution (chosen):")
    dist = collections.Counter(p["predicted"] for p in preds)
    for bid, n in dist.most_common():
        print(f"  {bid:<28s} {n:3d} ({n / len(preds):5.1%})")

    print()
    ambiguous = [p for p in preds if p["margin"] <= args.ambiguous_margin]
    print(f"Ambiguous queries (margin <= {args.ambiguous_margin}): {len(ambiguous)}")
    for p in ambiguous:
        print(
            f"  margin={p['margin']:+.2f}  pi={p['chosen_pi']:.2f}  "
            f"chosen={p['predicted']} ({p['chosen_mu']:.2f}) vs "
            f"{p['second_bucket']} ({p['second_mu']:.2f})"
        )
        print(f"    Q: {p['question'][:140]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
