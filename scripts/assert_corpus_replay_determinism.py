#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from retrieval_lab.config import ExperimentConfig
from retrieval_lab.corpus_fingerprint import (
    corpus_content_fingerprint_from_units,
    corpus_fingerprint_from_ids,
)
from retrieval_lab.substrate_loader import fold_under_threshold_into_adjacent, load_evidence_units, merge_units_by_heading


def _build_raw_corpus(config: ExperimentConfig) -> List[Dict[str, Any]]:
    return load_evidence_units(config.substrate_path, config.document_id)


def _build_corpus(
    config: ExperimentConfig,
    raw_corpus: List[Dict[str, Any]],
    *,
    merge_chunks_override: bool | None,
) -> List[Dict[str, Any]]:
    corpus = list(raw_corpus)
    min_chars = getattr(config, "min_chars", None)
    if min_chars is not None:
        corpus = fold_under_threshold_into_adjacent(raw_corpus, min_chars)
    merge_chunks = getattr(config, "merge_chunks", False) if merge_chunks_override is None else merge_chunks_override
    if merge_chunks:
        corpus = merge_units_by_heading(
            corpus,
            max_chars=getattr(config, "merge_max_chars", 2000),
        )
    return corpus


def _page_inversions(raw_corpus: List[Dict[str, Any]]) -> List[Dict[str, int | str]]:
    inversions: List[Dict[str, int | str]] = []
    seen_pages: List[tuple[str, int]] = []
    for unit in raw_corpus:
        parent_dir = str(unit.get("source_parent_dir") or "")
        page = int(unit.get("page", -1))
        key = (parent_dir, page)
        if not seen_pages or seen_pages[-1] != key:
            seen_pages.append(key)
    for index in range(1, len(seen_pages)):
        previous_parent, previous_page = seen_pages[index - 1]
        current_parent, current_page = seen_pages[index]
        if current_parent == previous_parent and current_page < previous_page:
            inversions.append(
                {
                    "index": index,
                    "parent_dir": current_parent,
                    "previous_page": previous_page,
                    "current_page": current_page,
                }
            )
    return inversions


def _summarize(raw_corpus: List[Dict[str, Any]], corpus: List[Dict[str, Any]]) -> Dict[str, Any]:
    ids = [str(unit.get("id", "")).strip() for unit in corpus if str(unit.get("id", "")).strip()]
    return {
        "unit_count": len(corpus),
        "corpus_fingerprint": corpus_fingerprint_from_ids(ids),
        "corpus_content_fingerprint": corpus_content_fingerprint_from_units(corpus),
        "page_inversions": _page_inversions(raw_corpus),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Assert deterministic corpus replay from a retrieval config.")
    parser.add_argument("--config", required=True, help="Experiment YAML config path")
    parser.add_argument("--out", default=None, help="Optional JSON report path")
    parser.add_argument(
        "--merge-chunks",
        dest="merge_chunks_override",
        action="store_const",
        const=True,
        default=None,
        help="Force merged-chunk replay regardless of config default.",
    )
    parser.add_argument(
        "--no-merge-chunks",
        dest="merge_chunks_override",
        action="store_const",
        const=False,
        help="Force raw/no-merge replay regardless of config default.",
    )
    args = parser.parse_args()

    config = ExperimentConfig.from_yaml(Path(args.config))
    config.resolve_paths(Path.cwd())

    first_raw_corpus = _build_raw_corpus(config)
    second_raw_corpus = _build_raw_corpus(config)
    first_summary = _summarize(
        first_raw_corpus,
        _build_corpus(config, first_raw_corpus, merge_chunks_override=args.merge_chunks_override),
    )
    second_summary = _summarize(
        second_raw_corpus,
        _build_corpus(config, second_raw_corpus, merge_chunks_override=args.merge_chunks_override),
    )
    match = (
        first_summary["corpus_fingerprint"] == second_summary["corpus_fingerprint"]
        and first_summary["corpus_content_fingerprint"] == second_summary["corpus_content_fingerprint"]
        and first_summary["page_inversions"] == second_summary["page_inversions"]
    )
    report = {
        "config": args.config,
        "merge_chunks_override": args.merge_chunks_override,
        "status": "passed" if match and not first_summary["page_inversions"] else "failed",
        "first": first_summary,
        "second": second_summary,
        "fingerprints_match": match,
    }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
