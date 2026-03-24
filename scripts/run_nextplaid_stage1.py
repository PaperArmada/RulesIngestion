"""Run NextPlaid Stage 1 slices with a mandatory test gate.

This script is intentionally narrow for the targeted bakeoff:
- Starfinder bridge slice
- PHB compositional slice
- SWCR true-miss slice
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List

# Bootstrap repo root for `retrieval_lab` imports when invoked as a script.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from retrieval_lab.nextplaid_bakeoff import (
    build_anchor_delta,
    build_failure_explainer,
    build_phb_compositional_slice,
    build_starfinder_bridge_slice,
    build_swcr_true_miss_slice,
    stage1_go_decision,
    write_slice,
)
from retrieval_lab.gold_grounding import resolve_gold_locations_to_current_corpus
from retrieval_lab.retrievers.nextplaid import (
    NextPlaidRetriever,
    NextPlaidSearchParams,
)
from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_enrichments_into_corpus,
    merge_units_by_heading,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run NextPlaid Stage 1 targeted slices.")
    p.add_argument("--endpoint", default="http://localhost:8080")
    p.add_argument("--starfinder-index", required=True)
    p.add_argument("--phb-index", required=True)
    p.add_argument("--swcr-index", required=True)
    p.add_argument(
        "--starfinder-benchmark",
        default="evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json",
    )
    p.add_argument(
        "--phb-benchmark",
        default="evals/retrieval/PHB5e/dnd_5e_2024_rules_50q_benchmark.json",
    )
    p.add_argument(
        "--swcr-benchmark",
        default="evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json",
    )
    p.add_argument(
        "--swcr-per-query-clean-subset",
        required=True,
        help="Path to contract-valid per_query.clean_subset.json used to derive true misses.",
    )
    p.add_argument("--swcr-per-query-model-id", default="")
    p.add_argument("--exclude-swcr-query-id", action="append", default=[])
    p.add_argument("--top-k", type=int, default=20)
    p.add_argument("--n-ivf-probe", type=int, default=8)
    p.add_argument("--n-full-scores", type=int, default=4096)
    p.add_argument("--skip-test-gate", action="store_true")
    p.add_argument(
        "--allow-integrity-mismatch",
        action="store_true",
        help=(
            "Allow Stage 1 retrieval to run even when required gold IDs are missing from "
            "the active shaped corpus after gold-location resolution."
        ),
    )
    p.add_argument(
        "--test-gate-cmd",
        default="uv run pytest tests/retrieval_lab/test_nextplaid_retriever.py tests/retrieval_lab/test_nextplaid_bakeoff.py -q",
    )
    p.add_argument(
        "--output-dir",
        default="out/retrieval_lab/experiments/nextplaid_stage1",
    )
    p.add_argument(
        "--b0-anchor-signals-json",
        default="",
        help=(
            "Optional path to JSON object with baseline booleans for "
            "rescued_blind_001_04, phb_t2_completion_improved, swcr_true_miss_lift."
        ),
    )
    return p


def _run_test_gate(cmd: str) -> None:
    proc = subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "NextPlaid test gate failed.\n"
            f"Command: {cmd}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
        )


def _load_corpus_id_map(substrate_path: Path, document_id: str) -> Dict[str, Dict[str, Any]]:
    corpus = load_evidence_units(str(substrate_path.resolve()), document_id)
    corpus = fold_under_threshold_into_adjacent(corpus, 200)
    corpus = merge_units_by_heading(corpus, max_chars=2000)
    corpus = merge_enrichments_into_corpus(corpus, str(substrate_path.resolve()))
    return {str(c.get("id", "")): c for c in corpus if str(c.get("id", "")).strip()}


def _load_shaped_corpus(substrate_path: Path, document_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    folded = fold_under_threshold_into_adjacent(
        load_evidence_units(str(substrate_path.resolve()), document_id),
        200,
    )
    merged = merge_units_by_heading(folded, max_chars=2000)
    merged = merge_enrichments_into_corpus(merged, str(substrate_path.resolve()))
    return folded, merged


def _build_id_map(corpus: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(c.get("id", "")): c for c in corpus if str(c.get("id", "")).strip()}


def _extract_required_gold(query: Dict[str, Any]) -> List[str]:
    required = query.get("required_gold")
    if not isinstance(required, list) or not required:
        required = query.get("gold_unit_ids") or []
    out: List[str] = []
    for item in required:
        cid = str(item).strip()
        if cid and cid not in out:
            out.append(cid)
    return out


def _resolve_slice_gold(
    slice_payload: Dict[str, Any],
    *,
    folded_corpus: List[Dict[str, Any]],
    merged_corpus: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], Dict[str, int]]:
    queries = [q for q in slice_payload.get("queries", []) if isinstance(q, dict)]
    resolved_queries, summary = resolve_gold_locations_to_current_corpus(
        queries,
        folded_corpus=folded_corpus,
        merged_corpus=merged_corpus,
    )
    out = dict(slice_payload)
    out["queries"] = resolved_queries
    md = dict(out.get("metadata") or {})
    md["gold_resolution_summary"] = summary
    out["metadata"] = md
    return out, summary


def _slice_integrity_summary(
    *,
    slice_payload: Dict[str, Any],
    id_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    total_missing_ids = 0
    for query in [q for q in slice_payload.get("queries", []) if isinstance(q, dict)]:
        query_id = str(query.get("id", ""))
        required_gold = _extract_required_gold(query)
        missing_required = [gid for gid in required_gold if gid not in id_map]
        if missing_required:
            total_missing_ids += len(missing_required)
            rows.append(
                {
                    "query_id": query_id,
                    "required_gold_count": len(required_gold),
                    "missing_required_gold_ids": missing_required,
                    "missing_required_gold_count": len(missing_required),
                }
            )
    return {
        "query_count": len([q for q in slice_payload.get("queries", []) if isinstance(q, dict)]),
        "queries_with_missing_required_gold": len(rows),
        "missing_required_gold_total": total_missing_ids,
        "rows": rows,
    }


def _first_gold_rank(mapped_unit_ids: List[str], required_gold: List[str]) -> int | None:
    wanted = set(required_gold)
    for i, cid in enumerate(mapped_unit_ids, start=1):
        if cid in wanted:
            return i
    return None


def _required_full_set_hit_at_10(mapped_unit_ids: List[str], required_gold: List[str]) -> bool:
    if not required_gold:
        return False
    top10 = set(mapped_unit_ids[:10])
    return set(required_gold).issubset(top10)


def _run_slice(
    retriever: NextPlaidRetriever,
    *,
    index_name: str,
    slice_payload: Dict[str, Any],
    id_map: Dict[str, Dict[str, Any]],
    params: NextPlaidSearchParams,
    slice_tag: str,
) -> Dict[str, Any]:
    queries = [q for q in slice_payload.get("queries", []) if isinstance(q, dict)]
    query_texts = [str(q.get("question", "")) for q in queries]
    results = retriever.search_with_encoding(index_name, query_texts, params)
    if len(results) != len(queries):
        raise RuntimeError(f"Query/result count mismatch for {slice_tag}")

    per_query: List[Dict[str, Any]] = []
    rescued_blind_001_04 = False
    required_full_set_hits = 0
    for q, r in zip(queries, results):
        mapped = retriever.map_hits_to_unit_ids(r.hits, id_map)
        required_gold = _extract_required_gold(q)
        first_rank = _first_gold_rank(mapped["mapped_unit_ids"], required_gold)
        in_pool = first_rank is not None
        if str(q.get("id", "")) == "blind_001_04" and in_pool:
            rescued_blind_001_04 = True
        full_set_10 = _required_full_set_hit_at_10(mapped["mapped_unit_ids"], required_gold)
        if full_set_10:
            required_full_set_hits += 1
        per_query.append(
            {
                "query_id": q.get("id", ""),
                "query_text": str(q.get("question", "")),
                "slice_tag": slice_tag,
                "latency_ms": r.latency_ms,
                "raw_hit_count": len(r.hits),
                "raw_payload_keys": sorted(list(r.raw_payload.keys())),
                "raw_result_ids": mapped["raw_result_ids"],
                "mapped_unit_ids": mapped["mapped_unit_ids"],
                "missing_result_ids": mapped["missing_result_ids"],
                "required_gold": required_gold,
                "gold_entered_pool": in_pool,
                "first_gold_rank": first_rank,
                "required_full_set_hit_at_10": full_set_10,
                "result_summary": {
                    "raw_hit_count": len(r.hits),
                    "mapped_hit_count": len(mapped["mapped_unit_ids"]),
                    "missing_hit_count": len(mapped["missing_result_ids"]),
                    "first_gold_rank": first_rank,
                    "gold_entered_pool": in_pool,
                    "required_full_set_hit_at_10": full_set_10,
                },
            }
        )

    return {
        "slice_tag": slice_tag,
        "index_name": index_name,
        "query_count": len(queries),
        "rescued_blind_001_04": rescued_blind_001_04,
        "required_full_set_hit_at_10_count": required_full_set_hits,
        "required_full_set_hit_at_10_rate": (
            float(required_full_set_hits) / float(len(queries) or 1)
        ),
        "per_query": per_query,
    }


def main() -> None:
    args = _parser().parse_args()
    root = Path.cwd()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_test_gate:
        _run_test_gate(args.test_gate_cmd)

    retriever = NextPlaidRetriever(args.endpoint)
    health = retriever.health()

    sf_slice = build_starfinder_bridge_slice((root / args.starfinder_benchmark).resolve())
    phb_slice = build_phb_compositional_slice((root / args.phb_benchmark).resolve())
    sw_slice = build_swcr_true_miss_slice(
        swcr_benchmark_path=(root / args.swcr_benchmark).resolve(),
        per_query_clean_subset_path=(root / args.swcr_per_query_clean_subset).resolve(),
        retrieval_model_id=(args.swcr_per_query_model_id or None),
        excluded_query_ids=set(args.exclude_swcr_query_id or []),
    )

    sf_folded, sf_corpus = _load_shaped_corpus(root / "out/StarFinderPlayerCore", "StarFinderPlayerCore")
    phb_folded, phb_corpus = _load_shaped_corpus(root / "out/DnD_PHB_5.5", "DnD_PHB_5.5")
    sw_folded, sw_corpus = _load_shaped_corpus(
        root / "out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF",
        "Swords&Wizardry",
    )

    sf_slice, sf_gold_resolution = _resolve_slice_gold(
        sf_slice,
        folded_corpus=sf_folded,
        merged_corpus=sf_corpus,
    )
    phb_slice, phb_gold_resolution = _resolve_slice_gold(
        phb_slice,
        folded_corpus=phb_folded,
        merged_corpus=phb_corpus,
    )
    sw_slice, sw_gold_resolution = _resolve_slice_gold(
        sw_slice,
        folded_corpus=sw_folded,
        merged_corpus=sw_corpus,
    )

    write_slice(output_dir / "slice_starfinder_bridge.json", sf_slice)
    write_slice(output_dir / "slice_phb_compositional.json", phb_slice)
    write_slice(output_dir / "slice_swcr_true_miss.json", sw_slice)

    sf_map = _build_id_map(sf_corpus)
    phb_map = _build_id_map(phb_corpus)
    sw_map = _build_id_map(sw_corpus)

    integrity_preflight = {
        "starfinder_bridge": _slice_integrity_summary(slice_payload=sf_slice, id_map=sf_map),
        "phb_compositional": _slice_integrity_summary(slice_payload=phb_slice, id_map=phb_map),
        "swcr_true_miss": _slice_integrity_summary(slice_payload=sw_slice, id_map=sw_map),
    }
    (output_dir / "integrity_preflight.json").write_text(
        json.dumps(integrity_preflight, indent=2),
        encoding="utf-8",
    )
    if (
        not args.allow_integrity_mismatch
        and sum(
            int(payload.get("missing_required_gold_total", 0) or 0)
            for payload in integrity_preflight.values()
            if isinstance(payload, dict)
        )
        > 0
    ):
        raise RuntimeError(
            "Stage 1 integrity preflight failed: required gold IDs are missing from active shaped corpus. "
            "See integrity_preflight.json. Re-anchor benchmark projection or rerun with "
            "--allow-integrity-mismatch for diagnostic-only execution."
        )
    params = NextPlaidSearchParams(
        top_k=int(args.top_k),
        n_ivf_probe=int(args.n_ivf_probe),
        n_full_scores=int(args.n_full_scores),
    )

    started = time.perf_counter()
    sf_out = _run_slice(
        retriever,
        index_name=args.starfinder_index,
        slice_payload=sf_slice,
        id_map=sf_map,
        params=params,
        slice_tag="starfinder_bridge",
    )
    phb_out = _run_slice(
        retriever,
        index_name=args.phb_index,
        slice_payload=phb_slice,
        id_map=phb_map,
        params=params,
        slice_tag="phb_compositional",
    )
    sw_out = _run_slice(
        retriever,
        index_name=args.swcr_index,
        slice_payload=sw_slice,
        id_map=sw_map,
        params=params,
        slice_tag="swcr_true_miss",
    )
    elapsed = time.perf_counter() - started

    # SWCR slice is constructed from retrieval_miss baseline rows;
    # any gold_in_pool true means observed lift on that miss set.
    sw_lift = any(q["gold_entered_pool"] for q in sw_out["per_query"])
    phb_t2_improved = phb_out["required_full_set_hit_at_10_count"] > 0
    b1_signals = {
        "rescued_blind_001_04": bool(sf_out["rescued_blind_001_04"]),
        "phb_t2_completion_improved": bool(phb_t2_improved),
        "swcr_true_miss_lift": bool(sw_lift),
    }
    decision = stage1_go_decision(
        rescued_blind_001_04=b1_signals["rescued_blind_001_04"],
        phb_t2_completion_improved=b1_signals["phb_t2_completion_improved"],
        swcr_true_miss_lift=b1_signals["swcr_true_miss_lift"],
        guardrail_regression=False,
    )

    anchor_comparison: Dict[str, Any]
    if args.b0_anchor_signals_json:
        b0_payload = json.loads((root / args.b0_anchor_signals_json).read_text(encoding="utf-8"))
        if not isinstance(b0_payload, dict):
            raise RuntimeError("Invalid --b0-anchor-signals-json payload: expected JSON object")
        b0_signals = {
            "rescued_blind_001_04": bool(b0_payload.get("rescued_blind_001_04", False)),
            "phb_t2_completion_improved": bool(b0_payload.get("phb_t2_completion_improved", False)),
            "swcr_true_miss_lift": bool(b0_payload.get("swcr_true_miss_lift", False)),
        }
        anchor_comparison = {
            "available": True,
            "b0": b0_signals,
            "b1": b1_signals,
            "delta": build_anchor_delta(b0=b0_signals, b1=b1_signals),
        }
    else:
        anchor_comparison = {
            "available": False,
            "note": "Provide --b0-anchor-signals-json to compute explicit B0-vs-B1 deltas.",
            "b1": b1_signals,
        }

    report = {
        "endpoint": args.endpoint,
        "health": health,
        "params": params.to_dict(),
        "slices": {
            "starfinder_bridge": sf_out,
            "phb_compositional": phb_out,
            "swcr_true_miss": sw_out,
        },
        "gold_resolution": {
            "starfinder_bridge": sf_gold_resolution,
            "phb_compositional": phb_gold_resolution,
            "swcr_true_miss": sw_gold_resolution,
        },
        "integrity_preflight": integrity_preflight,
        "decision": decision,
        "anchor_comparison": anchor_comparison,
        "failure_explainer": build_failure_explainer(
            starfinder_slice=sf_out,
            phb_slice=phb_out,
            swcr_slice=sw_out,
            top_k=int(args.top_k),
        ),
        "wall_time_sec": elapsed,
    }
    (output_dir / "stage1_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote Stage 1 report: {output_dir / 'stage1_report.json'}")


if __name__ == "__main__":
    main()

