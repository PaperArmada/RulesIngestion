#!/usr/bin/env python3
"""Emit candidate diagnostics for unresolved/target anchors.

Writes a JSON artifact with top nearby candidates and quote/path scores so
resolver behavior can be audited deterministically.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retrieval_lab.anchor_resolver import _jaccard_tokens, _token_overlap_recall
from retrieval_lab.anchor_schema import GoldAnchor
from retrieval_lab.config import ExperimentConfig
from retrieval_lab.orchestration.config_access import read_run_flags
from retrieval_lab.run_experiment import _load_and_ground_queries, _prepare_experiment_corpus_context


def _load_anchors(benchmark_path: Path) -> dict[str, GoldAnchor]:
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("anchors")
    if not isinstance(raw, dict):
        return {}
    anchors: dict[str, GoldAnchor] = {}
    for aid, anchor_payload in raw.items():
        if isinstance(anchor_payload, dict):
            anchors[aid] = GoldAnchor.from_dict(anchor_payload)
    return anchors


def _top_candidates(
    anchor: GoldAnchor,
    corpus: list[dict[str, Any]],
    *,
    page_window: int,
    top_n: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    min_page = anchor.page - page_window
    max_page = anchor.page + page_window
    for unit in corpus:
        page = unit.get("page")
        if page is None:
            continue
        page = int(page)
        if page < min_page or page > max_page:
            continue
        text = str(unit.get("text") or "")
        jaccard = _jaccard_tokens(anchor.anchor_quote, text)
        recall = _token_overlap_recall(anchor.anchor_quote, text)
        if jaccard <= 0 and recall <= 0:
            continue
        rows.append(
            {
                "unit_id": str(unit.get("id") or ""),
                "page": page,
                "structural_path": list(unit.get("structural_path") or []),
                "quote_jaccard": jaccard,
                "quote_recall": recall,
                "score": max(jaccard, recall),
                "text_preview": text[:220],
            }
        )
    rows.sort(key=lambda row: (row["score"], row["quote_recall"], row["quote_jaccard"]), reverse=True)
    return rows[:top_n]


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose anchor-to-corpus candidate matches.")
    parser.add_argument("--config", required=True, help="Experiment config YAML used to build corpus context.")
    parser.add_argument("--benchmark", required=True, help="Benchmark JSON with anchors.")
    parser.add_argument("--min-chars", type=int, default=None, help="Override min_chars for corpus shaping.")
    parser.add_argument(
        "--anchor-ids",
        nargs="*",
        default=[],
        help="Anchor IDs to inspect. Defaults to unresolved anchors in current run context.",
    )
    parser.add_argument("--page-window", type=int, default=1, help="Inspect candidates within +/- this page window.")
    parser.add_argument("--top-n", type=int, default=12, help="Number of candidates per anchor.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    args = parser.parse_args()

    root = Path.cwd()
    config = ExperimentConfig.from_yaml((root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config))
    benchmark_path = (root / args.benchmark).resolve() if not Path(args.benchmark).is_absolute() else Path(args.benchmark).resolve()
    config.query_batches = [str(benchmark_path)]
    if args.min_chars is not None:
        config.min_chars = int(args.min_chars)
    config.resolve_paths(root)

    flags = read_run_flags(config)
    ctx = _prepare_experiment_corpus_context(config, flags, eval_only_run_id=None)
    grounding = _load_and_ground_queries(
        config,
        config.retrieval_mode,
        ctx["folded_corpus"],
        ctx["canonical_corpus"],
        ctx["grounding_units_by_page_map"],
    )
    summary = ((grounding.get("anchor_resolution_audit") or {}).get("summary") or {})
    unresolved_ids = list(summary.get("unresolved_anchors") or [])
    target_anchor_ids = list(args.anchor_ids) if args.anchor_ids else unresolved_ids

    anchors = _load_anchors(benchmark_path)
    diagnostics: list[dict[str, Any]] = []
    for anchor_id in target_anchor_ids:
        anchor = anchors.get(anchor_id)
        if anchor is None:
            diagnostics.append(
                {"anchor_id": anchor_id, "error": "anchor_not_found_in_benchmark"}
            )
            continue
        diagnostics.append(
            {
                "anchor_id": anchor.anchor_id,
                "page": anchor.page,
                "structural_path": list(anchor.structural_path),
                "anchor_quote": anchor.anchor_quote,
                "candidates": _top_candidates(
                    anchor,
                    ctx["canonical_corpus"],
                    page_window=int(args.page_window),
                    top_n=int(args.top_n),
                ),
            }
        )

    out = {
        "version": "anchor_candidate_diagnostic_v1",
        "benchmark_path": str(benchmark_path),
        "min_chars": flags.min_chars,
        "merge_chunks": bool(flags.merge_chunks),
        "merge_max_chars": int(flags.merge_max_chars),
        "anchor_resolution_summary": summary,
        "requested_anchor_ids": target_anchor_ids,
        "diagnostics": diagnostics,
    }
    output_path = (root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
