"""Helpers for NextPlaid targeted bakeoff slices and gating decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set


STARFINDER_BRIDGE_QUERY_IDS: List[str] = [
    "blind_001_01",
    "blind_001_02",
    "blind_001_03",
    "blind_001_04",
]


def _read_json(path: Path) -> Any:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload


def _extract_queries(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [q for q in payload if isinstance(q, dict)]
    queries = payload.get("queries")
    if not isinstance(queries, list):
        raise ValueError("Benchmark payload missing `queries` list")
    return [q for q in queries if isinstance(q, dict)]


def _subset_benchmark(
    benchmark_path: Path,
    query_ids: Sequence[str],
) -> Dict[str, Any]:
    payload = _read_json(benchmark_path)
    queries = _extract_queries(payload)
    wanted = {qid.strip() for qid in query_ids if qid.strip()}
    selected = [q for q in queries if str(q.get("id", "")).strip() in wanted]
    missing = sorted(wanted - {str(q.get("id", "")).strip() for q in selected})
    if missing:
        raise ValueError(f"Missing benchmark query ids in {benchmark_path}: {missing}")
    out: Dict[str, Any]
    if isinstance(payload, list):
        out = {"queries": selected}
    elif isinstance(payload, dict):
        out = dict(payload)
        out["queries"] = selected
    else:
        raise ValueError(f"Unsupported benchmark JSON shape at {benchmark_path}")
    md = dict(out.get("metadata") or {})
    md["query_count"] = len(selected)
    md["slice_query_ids"] = [str(q.get("id", "")) for q in selected]
    out["metadata"] = md
    return out


def build_starfinder_bridge_slice(starfinder_benchmark_path: Path) -> Dict[str, Any]:
    """Build fixed 4-query Starfinder bridge slice."""
    return _subset_benchmark(starfinder_benchmark_path, STARFINDER_BRIDGE_QUERY_IDS)


def build_phb_compositional_slice(phb_benchmark_path: Path) -> Dict[str, Any]:
    """Build PHB compositional slice (T2 queries)."""
    payload = _read_json(phb_benchmark_path)
    queries = _extract_queries(payload)
    selected = [q for q in queries if str(q.get("tier", "")).strip().upper() == "T2"]
    if not selected:
        raise ValueError("PHB compositional slice empty (no tier T2 queries found)")
    out = dict(payload)
    out["queries"] = selected
    md = dict(out.get("metadata") or {})
    md["query_count"] = len(selected)
    md["slice_selector"] = "tier == T2"
    out["metadata"] = md
    return out


def derive_swcr_true_miss_query_ids(
    per_query_clean_subset_path: Path,
    retrieval_model_id: Optional[str] = None,
    excluded_query_ids: Optional[Set[str]] = None,
) -> List[str]:
    """Extract SWCR true-miss query ids from a clean-subset per-query artifact."""
    payload = _read_json(per_query_clean_subset_path)
    if retrieval_model_id:
        rows = payload.get(retrieval_model_id)
    else:
        rows = payload.get(next(iter(payload.keys()), ""), [])
    if not isinstance(rows, list):
        raise ValueError("per_query artifact does not contain expected model rows")
    excluded = excluded_query_ids or set()
    out: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("failure_type", "")).strip() != "retrieval_miss":
            continue
        qid = str(row.get("query_id", "")).strip()
        if not qid or qid in excluded:
            continue
        out.append(qid)
    return sorted(set(out))


def build_swcr_true_miss_slice(
    swcr_benchmark_path: Path,
    per_query_clean_subset_path: Path,
    retrieval_model_id: Optional[str] = None,
    excluded_query_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    query_ids = derive_swcr_true_miss_query_ids(
        per_query_clean_subset_path=per_query_clean_subset_path,
        retrieval_model_id=retrieval_model_id,
        excluded_query_ids=excluded_query_ids,
    )
    if not query_ids:
        raise ValueError("SWCR true-miss slice empty")
    out = _subset_benchmark(swcr_benchmark_path, query_ids)
    md = dict(out.get("metadata") or {})
    md["slice_selector"] = "clean_subset failure_type == retrieval_miss"
    out["metadata"] = md
    return out


def write_slice(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def stage1_go_decision(
    *,
    rescued_blind_001_04: bool,
    phb_t2_completion_improved: bool,
    swcr_true_miss_lift: bool,
    guardrail_regression: bool,
) -> Dict[str, Any]:
    positive = rescued_blind_001_04 or phb_t2_completion_improved or swcr_true_miss_lift
    go = bool(positive and not guardrail_regression)
    reasons = {
        "rescued_blind_001_04": rescued_blind_001_04,
        "phb_t2_completion_improved": phb_t2_completion_improved,
        "swcr_true_miss_lift": swcr_true_miss_lift,
        "guardrail_regression": guardrail_regression,
    }
    return {"go_stage2": go, "positive_signal": positive, "reasons": reasons}


def build_anchor_delta(
    *,
    b0: Dict[str, bool],
    b1: Dict[str, bool],
) -> Dict[str, Any]:
    """Build explicit per-signal B0 vs B1 delta summary."""
    keys = (
        "rescued_blind_001_04",
        "phb_t2_completion_improved",
        "swcr_true_miss_lift",
    )
    deltas: Dict[str, Any] = {}
    for key in keys:
        b0_val = bool(b0.get(key, False))
        b1_val = bool(b1.get(key, False))
        delta = int(b1_val) - int(b0_val)
        if delta > 0:
            direction = "improved"
        elif delta < 0:
            direction = "regressed"
        else:
            direction = "flat"
        deltas[key] = {
            "b0": b0_val,
            "b1": b1_val,
            "delta": delta,
            "changed": b0_val != b1_val,
            "direction": direction,
        }
    return {"signals": deltas}


def build_failure_explainer(
    *,
    starfinder_slice: Dict[str, Any],
    phb_slice: Dict[str, Any],
    swcr_slice: Dict[str, Any],
    top_k: int,
) -> Dict[str, Any]:
    """Summarize how far each Stage 1 gate is from passing."""
    sf_queries = [q for q in starfinder_slice.get("per_query", []) if isinstance(q, dict)]
    phb_queries = [q for q in phb_slice.get("per_query", []) if isinstance(q, dict)]
    sw_queries = [q for q in swcr_slice.get("per_query", []) if isinstance(q, dict)]

    blind = next((q for q in sf_queries if str(q.get("query_id", "")) == "blind_001_04"), None)
    blind_rank = blind.get("first_gold_rank") if isinstance(blind, dict) else None
    distance_to_topk = None
    if isinstance(blind_rank, int):
        distance_to_topk = max(0, int(blind_rank) - int(top_k))

    best_phb = None
    best_phb_missing = None
    for q in phb_queries:
        required = [str(x).strip() for x in (q.get("required_gold") or []) if str(x).strip()]
        if not required:
            continue
        mapped_top10 = set((q.get("mapped_unit_ids") or [])[:10])
        covered = sum(1 for rid in required if rid in mapped_top10)
        missing = len(required) - covered
        row = {
            "query_id": q.get("query_id", ""),
            "covered_at_10": covered,
            "required_total": len(required),
            "missing_for_full_set_at_10": missing,
        }
        if best_phb is None or missing < best_phb["missing_for_full_set_at_10"]:
            best_phb = row
        if best_phb_missing is None or missing < best_phb_missing:
            best_phb_missing = missing

    best_sw_rank = None
    best_sw_query_id = ""
    for q in sw_queries:
        rank = q.get("first_gold_rank")
        if isinstance(rank, int) and (best_sw_rank is None or rank < best_sw_rank):
            best_sw_rank = rank
            best_sw_query_id = str(q.get("query_id", ""))

    return {
        "starfinder_blind_001_04": {
            "gate_passed": bool(starfinder_slice.get("rescued_blind_001_04", False)),
            "first_gold_rank": blind_rank,
            "threshold_top_k": int(top_k),
            "distance_to_top_k": distance_to_topk,
        },
        "phb_t2_completion": {
            "gate_passed": bool(phb_slice.get("required_full_set_hit_at_10_count", 0) > 0),
            "threshold": "at least one query with required_full_set_hit_at_10 == true",
            "best_query": best_phb,
            "distance_missing_required_gold_to_first_pass": best_phb_missing,
        },
        "swcr_true_miss_lift": {
            "gate_passed": any(bool(q.get("gold_entered_pool")) for q in sw_queries),
            "threshold": "at least one query with gold_entered_pool == true",
            "best_first_gold_rank": best_sw_rank,
            "best_query_id": best_sw_query_id,
            "distance_to_first_lift_query": 0 if best_sw_rank is not None else 1,
        },
    }

