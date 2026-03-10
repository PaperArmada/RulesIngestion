#!/usr/bin/env python3
"""
Materialize a benchmark projection for an exact evaluated run corpus without mutating source files.

This script rebuilds the fold+merge corpus from config, verifies that it matches the
target run's `corpus_index.json`, resolves benchmark gold onto that exact corpus, then
emits:

- a new re-anchored benchmark artifact,
- a machine-readable contract sidecar,
- a summary/diff artifact.

Usage (from RulesIngestion):
  uv run python scripts/resolve_sw_gold_to_corpus.py
  uv run python scripts/resolve_sw_gold_to_corpus.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path

# Run from repo root (RulesIngestion)
REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from retrieval_lab.config import ExperimentConfig
from retrieval_lab.benchmark_contract import (
    benchmark_contract_sidecar_path,
    benchmark_query_alignment_summary,
    build_benchmark_contract,
    write_benchmark_contract,
)
from retrieval_lab.corpus_fingerprint import build_corpus_index_payload
from retrieval_lab.gold_grounding import resolve_gold_locations_to_current_corpus
from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_units_by_heading,
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description="Materialize a benchmark projection against an exact run corpus")
    ap.add_argument("--dry-run", action="store_true", help="Print planned outputs but do not write artifacts")
    ap.add_argument(
        "--config",
        default="retrieval_lab/experiments/hybrid/swords_wizardry_autogold_manual_compare.yaml",
        help="Experiment config path used to rebuild the run corpus shape",
    )
    ap.add_argument(
        "--benchmark",
        default="evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json",
        help="Source benchmark JSON path to re-anchor",
    )
    ap.add_argument(
        "--corpus-index",
        default=(
            "out/retrieval_lab/experiments/"
            "embed_retrieval_lab_Swords&Wizardry_v3_swcr_merged2000_min100_recipe_standardized/"
            "embeddings/corpus_index.json"
        ),
        help="Exact run corpus_index.json to contract against",
    )
    args = ap.parse_args()

    cwd = REPO_ROOT
    config_path = cwd / args.config
    config = ExperimentConfig.from_yaml(config_path)
    config.resolve_paths(cwd)

    corpus_index_path = (cwd / args.corpus_index).resolve()
    corpus_index = json.loads(corpus_index_path.read_text(encoding="utf-8"))
    target_run_id = str(corpus_index.get("run_id") or "")
    target_substrate_version = str(corpus_index.get("substrate_version") or "")
    target_fingerprint = str(corpus_index.get("corpus_fingerprint") or "")
    target_content_fingerprint = str(corpus_index.get("corpus_content_fingerprint") or "")

    # Build corpus same as run_experiment
    corpus = load_evidence_units(config.substrate_path, config.document_id)
    min_chars = getattr(config, "min_chars", None)
    if min_chars is not None:
        folded = fold_under_threshold_into_adjacent(corpus, min_chars)
    else:
        folded = corpus
        for u in folded:
            u.setdefault("source_unit_ids", [u.get("id", "")])
    if getattr(config, "merge_chunks", False):
        merged = merge_units_by_heading(
            folded,
            max_chars=getattr(config, "merge_max_chars", 2000),
        )
    else:
        merged = folded

    corpus_index_payload = build_corpus_index_payload(
        run_id=target_run_id,
        substrate_version=target_substrate_version,
        corpus=merged,
    )
    corpus_ids = [str(unit.get("id") or "") for unit in merged if str(unit.get("id") or "").strip()]
    actual_fingerprint = str(corpus_index_payload.get("corpus_fingerprint") or "")
    actual_content_fingerprint = str(corpus_index_payload.get("corpus_content_fingerprint") or "")
    if actual_fingerprint != target_fingerprint:
        raise RuntimeError(
            "Config-built corpus does not match target corpus index: "
            f"current={actual_fingerprint} target={target_fingerprint}"
        )
    if target_content_fingerprint and actual_content_fingerprint != target_content_fingerprint:
        raise RuntimeError(
            "Config-built corpus content does not match target corpus index: "
            f"current={actual_content_fingerprint} target={target_content_fingerprint}"
        )

    print(
        f"Corpus: {len(corpus)} raw -> {len(folded)} folded -> {len(merged)} merged; "
        f"run_id={target_run_id} fingerprint={target_fingerprint[:12]} "
        f"content_fingerprint={actual_content_fingerprint[:12]}"
    )

    benchmark_path = cwd / args.benchmark
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(benchmark, list):
        raise RuntimeError(f"Expected benchmark JSON list at {benchmark_path}")

    resolved_benchmark, summary = resolve_gold_locations_to_current_corpus(
        benchmark,
        folded_corpus=folded,
        merged_corpus=merged,
    )
    updated = 0
    for before, after in zip(benchmark, resolved_benchmark):
        if (
            before.get("gold_unit_ids") != after.get("gold_unit_ids")
            or before.get("required_gold") != after.get("required_gold")
            or before.get("supporting_gold") != after.get("supporting_gold")
            or before.get("gold_locations") != after.get("gold_locations")
            or before.get("required_gold_rationale") != after.get("required_gold_rationale")
        ):
            updated += 1
            print(f"  {after.get('id', '')}: updated")
        after["_required_gold"] = list(after.get("required_gold") or [])
        after["_supporting_gold"] = list(after.get("supporting_gold") or [])
        after.pop("_gold_note", None)

    alignment_summary = benchmark_query_alignment_summary(
        resolved_benchmark,
        corpus_ids=corpus_ids,
    )
    if int(alignment_summary.get("missing_gold_ids_total", 0) or 0) > 0:
        raise RuntimeError(
            "Re-anchored benchmark still contains dead gold ids: "
            f"{alignment_summary['missing_gold_ids_total']}"
        )

    print(
        "Resolution summary: "
        f"with_locations={summary['queries_with_gold_locations']} "
        f"resolved_nonempty={summary['queries_resolved_nonempty']} "
        f"resolved_empty={summary['queries_resolved_empty']} "
        f"legacy_only={summary['queries_legacy_only']}"
    )
    print(f"Updated {updated} queries")

    output_benchmark_path = benchmark_path.with_name(
        f"{benchmark_path.stem}.reanchored.{target_substrate_version}.json"
    )
    output_summary_path = output_benchmark_path.with_suffix(".summary.json")
    output_contract_path = benchmark_contract_sidecar_path(output_benchmark_path)
    source_contract_path = benchmark_contract_sidecar_path(benchmark_path)
    rendered_benchmark = json.dumps(resolved_benchmark, indent=2)
    rendered_benchmark_sha256 = hashlib.sha256(rendered_benchmark.encode("utf-8")).hexdigest()
    contract = build_benchmark_contract(
        benchmark_path=output_benchmark_path,
        benchmark_sha256=rendered_benchmark_sha256,
        query_count=len(resolved_benchmark),
        run_id=target_run_id,
        substrate_version=target_substrate_version,
        corpus_fingerprint=target_fingerprint,
        corpus_content_fingerprint=actual_content_fingerprint,
        corpus_unit_count=len(corpus_ids),
        corpus_index_path=str(corpus_index_path),
        corpus_index_sha256=_sha256_file(corpus_index_path),
        corpus_recipe={
            "min_chars": getattr(config, "min_chars", None),
            "merge_chunks": bool(getattr(config, "merge_chunks", False)),
            "merge_max_chars": int(getattr(config, "merge_max_chars", 2000)),
        },
        benchmark_kind="reanchored_manual",
        benchmark_surface="active",
        benchmark_definition_path=str(benchmark_path),
        benchmark_definition_sha256=_sha256_file(benchmark_path),
        lineage={
            "source_benchmark_path": str(benchmark_path.resolve()),
            "source_benchmark_sha256": _sha256_file(benchmark_path),
            "source_contract_path": str(source_contract_path.resolve()) if source_contract_path.exists() else "",
            "reanchored_from_run_id": target_run_id,
            "reanchored_from_corpus_index": str(corpus_index_path),
        },
        alignment_summary=alignment_summary,
        projection_metadata={
            "projection_tool": "resolve_sw_gold_to_corpus.py",
            "resolution_summary": summary,
        },
    )
    summary_payload = {
        "version": "retrieval_lab_benchmark_projection_summary_v2",
        "source_benchmark_path": str(benchmark_path.resolve()),
        "source_benchmark_sha256": _sha256_file(benchmark_path),
        "target_run_id": target_run_id,
        "target_substrate_version": target_substrate_version,
        "target_corpus_fingerprint": target_fingerprint,
        "target_corpus_content_fingerprint": actual_content_fingerprint,
        "target_corpus_index_sha256": _sha256_file(corpus_index_path),
        "resolution_summary": summary,
        "alignment_summary": alignment_summary,
        "queries_updated": updated,
        "output_benchmark_path": str(output_benchmark_path.resolve()),
        "output_contract_path": str(output_contract_path.resolve()),
    }

    if args.dry_run:
        print(f"(dry-run) would write benchmark: {output_benchmark_path}")
        print(f"(dry-run) would write summary:   {output_summary_path}")
        print(f"(dry-run) would write contract:  {output_contract_path}")
        return

    output_benchmark_path.write_text(rendered_benchmark, encoding="utf-8")
    output_summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    write_benchmark_contract(output_contract_path, contract)
    print(f"Wrote benchmark: {output_benchmark_path}")
    print(f"Wrote summary:   {output_summary_path}")
    print(f"Wrote contract:  {output_contract_path}")


if __name__ == "__main__":
    main()
