"""Evaluate the classifier against a hand-labeled gold set.

Reports overall accuracy, per-bucket precision/recall, confusion matrix,
and latency percentiles. Also runs in a "predict-only" mode (--no-gold)
that just reports the bucket distribution of classifier predictions on a
benchmark, useful before any hand-labeling exists.

Usage:
  uv run python -m tinker.scripts.eval_classifier \\
      --benchmark evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_atomic_rules_benchmark.v3_swcr_merged2000_min100.json \\
      --gold out/tinker/swcr/classifier_gold.json \\
      --out out/tinker/swcr/runs/<ts>/classifier_eval.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.cache import TinkerCache  # noqa: E402
from tinker.routing.buckets import BUCKET_IDS  # noqa: E402
from tinker.routing.classifier import (  # noqa: E402
    classify_query,
    classify_query_qrofs,
)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[max(0, min(len(s) - 1, int(q * len(s)) - 1))]


def _print_confusion_matrix(matrix: dict[tuple[str, str], int]) -> None:
    buckets = list(BUCKET_IDS)
    print("Confusion matrix (rows=gold, cols=predicted):")
    name_width = max(len(b) for b in buckets) + 2
    header = " " * name_width + " ".join(f"{b[:6]:>6}" for b in buckets)
    print(header)
    for gold in buckets:
        row = [f"{matrix.get((gold, pred), 0):>6}" for pred in buckets]
        total = sum(matrix.get((gold, pred), 0) for pred in buckets)
        if total == 0:
            continue
        print(f"{gold:<{name_width}}" + " ".join(row))
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate classifier vs gold.")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument(
        "--gold",
        type=Path,
        default=None,
        help="JSON dict {query_id: bucket_id} written by label_classifier_sample.",
    )
    parser.add_argument(
        "--no-gold",
        action="store_true",
        help="Run classifier and only report the bucket distribution.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("out/tinker/classifier_eval_cache.sqlite"),
        help="Cache file for classifier responses.",
    )
    parser.add_argument(
        "--self-portrait",
        type=Path,
        default=None,
        help="Optional path to corpus_self_portrait.json for prompt context.",
    )
    parser.add_argument(
        "--qrofs",
        action="store_true",
        help="Use the q-rung orthopair classifier (per-bucket mu/nu/pi).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override the Ollama model used by the classifier (default: qwen3:4b).",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path.")
    args = parser.parse_args()

    raw = json.loads(args.benchmark.read_text())
    queries = raw if isinstance(raw, list) else raw.get("queries") or raw.get("benchmark") or []
    if not isinstance(queries, list) or not queries:
        print("ERROR: benchmark queries not found (expected list at top level "
              "or under key 'queries'/'benchmark')", file=sys.stderr)
        return 2

    gold: dict[str, str] = {}
    if not args.no_gold:
        if args.gold is None:
            print("ERROR: --gold is required unless --no-gold is set", file=sys.stderr)
            return 2
        if not args.gold.is_file():
            print(f"ERROR: gold file not found: {args.gold}", file=sys.stderr)
            return 2
        gold = json.loads(args.gold.read_text())

    cache = TinkerCache(args.cache)
    self_portrait_summary = None
    if args.self_portrait is not None and args.self_portrait.is_file():
        sp = json.loads(args.self_portrait.read_text())
        cluster_descs = [
            f"cluster_{c['cluster_id']}: {c.get('description', '')}"
            for c in sp.get("clusters", {}).get("clusters", [])
        ]
        self_portrait_summary = "Cluster shapes:\n" + "\n".join(cluster_descs[:8])

    predictions: list[dict[str, Any]] = []
    mode_name = "q-ROFS" if args.qrofs else "single-label"
    print(f"Classifying {len(queries)} queries ({mode_name})...")
    t0 = time.perf_counter()
    for i, q in enumerate(queries):
        qid = q.get("id") or f"q{i}"
        question = q.get("question", "")
        if args.qrofs:
            qresult = classify_query_qrofs(
                question,
                self_portrait_summary=self_portrait_summary,
                cache=cache,
                **({"model": args.model} if args.model else {}),
            )
            entry: dict[str, Any] = {
                "id": qid,
                "question": question,
                "predicted": qresult.chosen_bucket,
                "confidence": qresult.chosen_mu,
                "chosen_mu": qresult.chosen_mu,
                "chosen_nu": qresult.chosen_nu,
                "chosen_pi": qresult.chosen_pi,
                "second_bucket": qresult.second_bucket,
                "second_mu": qresult.second_mu,
                "margin": qresult.margin,
                "memberships": {
                    bid: {
                        "mu": m.mu,
                        "nu": m.nu,
                        "pi": m.pi,
                        "reason": m.reason,
                    }
                    for bid, m in qresult.memberships.items()
                },
                "reason": qresult.memberships[qresult.chosen_bucket].reason,
                "latency_ms": qresult.latency_ms,
                "cached": qresult.cached,
                "gold": gold.get(qid),
            }
            predictions.append(entry)
            cache_marker = "C" if qresult.cached else " "
            mu = qresult.chosen_mu
            pi = qresult.chosen_pi
            extra = f" mu={mu:.2f} pi={pi:.2f} margin={qresult.margin:+.2f}"
            if not args.no_gold:
                g = gold.get(qid, "—")
                mark = "✓" if qresult.chosen_bucket == g else "✗"
                print(
                    f"  [{i + 1:3d}/{len(queries)}] {cache_marker} {mark} "
                    f"{qresult.chosen_bucket:<26s} gold={g:<26s}"
                    f"{extra}  ({qresult.latency_ms:5.0f}ms)"
                )
            else:
                print(
                    f"  [{i + 1:3d}/{len(queries)}] {cache_marker} "
                    f"{qresult.chosen_bucket:<26s}"
                    f"{extra}  ({qresult.latency_ms:5.0f}ms)"
                )
            continue

        result = classify_query(
            question,
            self_portrait_summary=self_portrait_summary,
            cache=cache,
            **({"model": args.model} if args.model else {}),
        )
        predictions.append(
            {
                "id": qid,
                "question": question,
                "predicted": result.bucket,
                "confidence": result.confidence,
                "reason": result.reason,
                "latency_ms": result.latency_ms,
                "cached": result.cached,
                "gold": gold.get(qid),
            }
        )
        cache_marker = "C" if result.cached else " "
        if not args.no_gold:
            g = gold.get(qid, "—")
            mark = "✓" if result.bucket == g else "✗"
            print(
                f"  [{i + 1:3d}/{len(queries)}] {cache_marker} {mark} "
                f"{result.bucket:<26s} gold={g:<26s} ({result.latency_ms:5.0f}ms)"
            )
        else:
            print(
                f"  [{i + 1:3d}/{len(queries)}] {cache_marker} "
                f"{result.bucket:<26s} ({result.latency_ms:5.0f}ms)"
            )
    total_elapsed = time.perf_counter() - t0

    print()
    print(f"Total time: {total_elapsed:.1f}s")

    bucket_counts = collections.Counter(p["predicted"] for p in predictions)
    print("Predicted bucket distribution:")
    for b in BUCKET_IDS:
        n = bucket_counts.get(b, 0)
        if n:
            print(f"  {b:<28s} {n:3d} ({n / len(predictions):5.1%})")

    report: dict[str, Any] = {
        "benchmark": str(args.benchmark),
        "query_count": len(queries),
        "total_elapsed_sec": round(total_elapsed, 3),
        "predicted_distribution": dict(bucket_counts),
        "predictions": predictions,
        "latency_ms_p50": round(_percentile(
            [p["latency_ms"] for p in predictions if not p["cached"]], 0.5
        ), 1),
        "latency_ms_p95": round(_percentile(
            [p["latency_ms"] for p in predictions if not p["cached"]], 0.95
        ), 1),
    }

    if gold:
        labeled = [p for p in predictions if p["gold"] is not None]
        n_labeled = len(labeled)
        correct = sum(1 for p in labeled if p["predicted"] == p["gold"])
        per_bucket_tp: collections.Counter[str] = collections.Counter()
        per_bucket_fp: collections.Counter[str] = collections.Counter()
        per_bucket_fn: collections.Counter[str] = collections.Counter()
        confusion: dict[tuple[str, str], int] = collections.Counter()
        for p in labeled:
            confusion[(p["gold"], p["predicted"])] += 1
            if p["predicted"] == p["gold"]:
                per_bucket_tp[p["gold"]] += 1
            else:
                per_bucket_fp[p["predicted"]] += 1
                per_bucket_fn[p["gold"]] += 1
        accuracy = correct / max(n_labeled, 1)
        print()
        print(f"Accuracy: {correct}/{n_labeled} = {accuracy:.1%}")
        print()
        print("Per-bucket precision/recall (labeled subset):")
        for b in BUCKET_IDS:
            tp = per_bucket_tp[b]
            fp = per_bucket_fp[b]
            fn = per_bucket_fn[b]
            if tp + fp + fn == 0:
                continue
            prec = tp / max(tp + fp, 1)
            rec = tp / max(tp + fn, 1)
            print(
                f"  {b:<28s} P={prec:.2f} R={rec:.2f}  "
                f"(tp={tp}, fp={fp}, fn={fn})"
            )
        print()
        _print_confusion_matrix(confusion)

        report["accuracy"] = round(accuracy, 4)
        report["correct"] = correct
        report["labeled_subset_size"] = n_labeled
        report["per_bucket"] = {
            b: {
                "tp": per_bucket_tp[b],
                "fp": per_bucket_fp[b],
                "fn": per_bucket_fn[b],
            }
            for b in BUCKET_IDS
        }

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"Report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
