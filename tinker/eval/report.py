"""Pretty-print eval harness results."""

from __future__ import annotations

import collections
import statistics
from typing import Iterable

from tinker.eval.harness import QueryEvalResult, aggregate


_METRIC_ORDER = (
    "mrr_required",
    "recall_at_1",
    "recall_at_5",
    "recall_at_10",
    "recall_at_20",
    "strict_required_at_10",
)


def _fmt(v: float) -> str:
    return f"{v:.3f}"


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[max(0, min(len(s) - 1, int(q * len(s)) - 1))]


def print_summary(results: dict[str, list[QueryEvalResult]]) -> None:
    """Side-by-side aggregate metrics across modes."""
    modes = sorted(results.keys())
    print()
    print("=" * 80)
    print(f"{'metric':<28s}" + "".join(f"  {m:>14s}" for m in modes))
    print("-" * 80)
    aggs = {m: aggregate(results[m]) for m in modes}
    for key in _METRIC_ORDER:
        row = f"{key:<28s}"
        for m in modes:
            row += f"  {_fmt(aggs[m].get(key, 0.0)):>14s}"
        print(row)
    print()


def print_per_bucket(results: list[QueryEvalResult]) -> None:
    """Router-mode-only: break out metrics per chosen bucket."""
    by_bucket: dict[str, list[QueryEvalResult]] = collections.defaultdict(list)
    for r in results:
        if r.chosen_bucket is None:
            continue
        by_bucket[r.chosen_bucket].append(r)
    print("Per-bucket (router):")
    print(
        f"  {'bucket':<28s} {'n':>4s} {'mrr':>8s} {'r@5':>8s} "
        f"{'r@10':>8s} {'r@20':>8s} {'strict@10':>10s}"
    )
    for bucket, items in sorted(by_bucket.items(), key=lambda kv: -len(kv[1])):
        agg = aggregate(items)
        print(
            f"  {bucket:<28s} {len(items):>4d} "
            f"{_fmt(agg.get('mrr_required', 0)):>8s} "
            f"{_fmt(agg.get('recall_at_5', 0)):>8s} "
            f"{_fmt(agg.get('recall_at_10', 0)):>8s} "
            f"{_fmt(agg.get('recall_at_20', 0)):>8s} "
            f"{_fmt(agg.get('strict_required_at_10', 0)):>10s}"
        )
    print()


def print_latency(results: dict[str, list[QueryEvalResult]]) -> None:
    print("Latency per mode (ms):")
    for mode, items in results.items():
        if not items:
            continue
        totals = [r.latency_ms.get("total_ms", 0.0) for r in items]
        print(
            f"  {mode:<14s}  "
            f"p50={_percentile(totals, 0.50):>7.0f}  "
            f"p95={_percentile(totals, 0.95):>7.0f}  "
            f"max={max(totals):>7.0f}  "
            f"mean={statistics.mean(totals):>7.0f}"
        )
    print()


def print_differences(results: dict[str, list[QueryEvalResult]], top_n: int = 8) -> None:
    """Show queries where router and raw_dense disagree most on MRR."""
    if "router" not in results or "raw_dense" not in results:
        return
    pairs = []
    rt_by_id = {r.query_id: r for r in results["router"]}
    rd_by_id = {r.query_id: r for r in results["raw_dense"]}
    for qid in rt_by_id.keys() & rd_by_id.keys():
        rt = rt_by_id[qid]
        rd = rd_by_id[qid]
        delta = rt.metrics["mrr_required"] - rd.metrics["mrr_required"]
        pairs.append((qid, delta, rt, rd))
    pairs.sort(key=lambda x: abs(x[1]), reverse=True)
    print(f"Top {top_n} biggest MRR differences (router - raw_dense):")
    for qid, delta, rt, rd in pairs[:top_n]:
        sign = "+" if delta > 0 else "-"
        print(
            f"  {qid}  delta={sign}{abs(delta):.3f}  "
            f"router_bucket={rt.chosen_bucket}  "
            f"router_mrr={rt.metrics['mrr_required']:.3f}  "
            f"raw_mrr={rd.metrics['mrr_required']:.3f}"
        )
        print(f"    Q: {rt.question[:130]}")
    print()
