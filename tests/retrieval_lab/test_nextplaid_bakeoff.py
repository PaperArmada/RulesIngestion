from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from retrieval_lab.nextplaid_bakeoff import (
    STARFINDER_BRIDGE_QUERY_IDS,
    build_anchor_delta,
    build_failure_explainer,
    build_phb_compositional_slice,
    build_starfinder_bridge_slice,
    build_swcr_true_miss_slice,
    derive_swcr_true_miss_query_ids,
    stage1_go_decision,
    write_slice,
)
from scripts.run_nextplaid_stage1 import _slice_integrity_summary


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_starfinder_bridge_slice_requires_all_ids(tmp_path: Path) -> None:
    benchmark = {
        "metadata": {"query_count": 4},
        "queries": [{"id": qid, "question": qid} for qid in STARFINDER_BRIDGE_QUERY_IDS],
    }
    path = tmp_path / "sf.json"
    _write_json(path, benchmark)

    sliced = build_starfinder_bridge_slice(path)
    ids = [q["id"] for q in sliced["queries"]]
    assert ids == STARFINDER_BRIDGE_QUERY_IDS
    assert sliced["metadata"]["query_count"] == 4


def test_phb_compositional_slice_filters_t2(tmp_path: Path) -> None:
    benchmark = {
        "metadata": {"query_count": 3},
        "queries": [
            {"id": "a", "tier": "T1"},
            {"id": "b", "tier": "T2"},
            {"id": "c", "tier": "T2"},
        ],
    }
    path = tmp_path / "phb.json"
    _write_json(path, benchmark)

    sliced = build_phb_compositional_slice(path)
    assert [q["id"] for q in sliced["queries"]] == ["b", "c"]
    assert sliced["metadata"]["slice_selector"] == "tier == T2"


def test_swcr_true_miss_slice_derivation(tmp_path: Path) -> None:
    benchmark = {
        "metadata": {"query_count": 3},
        "queries": [{"id": "q1"}, {"id": "q2"}, {"id": "q3"}],
    }
    per_query = {
        "all-mpnet-base-v2": [
            {"query_id": "q1", "failure_type": "retrieval_miss"},
            {"query_id": "q2", "failure_type": "hit"},
            {"query_id": "q3", "failure_type": "retrieval_miss"},
        ]
    }
    bench_path = tmp_path / "sw.json"
    per_query_path = tmp_path / "per_query.clean_subset.json"
    _write_json(bench_path, benchmark)
    _write_json(per_query_path, per_query)

    ids = derive_swcr_true_miss_query_ids(
        per_query_path,
        retrieval_model_id="all-mpnet-base-v2",
        excluded_query_ids={"q3"},
    )
    assert ids == ["q1"]

    sliced = build_swcr_true_miss_slice(
        bench_path,
        per_query_path,
        retrieval_model_id="all-mpnet-base-v2",
        excluded_query_ids={"q3"},
    )
    assert [q["id"] for q in sliced["queries"]] == ["q1"]


def test_stage1_go_decision_logic() -> None:
    no_go = stage1_go_decision(
        rescued_blind_001_04=False,
        phb_t2_completion_improved=False,
        swcr_true_miss_lift=False,
        guardrail_regression=False,
    )
    assert no_go["go_stage2"] is False

    go = stage1_go_decision(
        rescued_blind_001_04=True,
        phb_t2_completion_improved=False,
        swcr_true_miss_lift=False,
        guardrail_regression=False,
    )
    assert go["go_stage2"] is True

    blocked = stage1_go_decision(
        rescued_blind_001_04=True,
        phb_t2_completion_improved=False,
        swcr_true_miss_lift=False,
        guardrail_regression=True,
    )
    assert blocked["go_stage2"] is False


def test_build_anchor_delta() -> None:
    delta = build_anchor_delta(
        b0={
            "rescued_blind_001_04": False,
            "phb_t2_completion_improved": True,
            "swcr_true_miss_lift": False,
        },
        b1={
            "rescued_blind_001_04": True,
            "phb_t2_completion_improved": True,
            "swcr_true_miss_lift": False,
        },
    )
    assert delta["signals"]["rescued_blind_001_04"]["direction"] == "improved"
    assert delta["signals"]["rescued_blind_001_04"]["delta"] == 1
    assert delta["signals"]["phb_t2_completion_improved"]["direction"] == "flat"
    assert delta["signals"]["swcr_true_miss_lift"]["direction"] == "flat"


def test_build_failure_explainer() -> None:
    explainer = build_failure_explainer(
        starfinder_slice={
            "rescued_blind_001_04": False,
            "per_query": [{"query_id": "blind_001_04", "first_gold_rank": 27}],
        },
        phb_slice={
            "required_full_set_hit_at_10_count": 0,
            "per_query": [
                {
                    "query_id": "phb_q1",
                    "required_gold": ["a", "b"],
                    "mapped_unit_ids": ["a", "x"],
                }
            ],
        },
        swcr_slice={
            "per_query": [
                {"query_id": "sw_q1", "gold_entered_pool": False, "first_gold_rank": None},
                {"query_id": "sw_q2", "gold_entered_pool": True, "first_gold_rank": 12},
            ]
        },
        top_k=20,
    )
    sf = explainer["starfinder_blind_001_04"]
    assert sf["distance_to_top_k"] == 7
    phb = explainer["phb_t2_completion"]
    assert phb["best_query"]["missing_for_full_set_at_10"] == 1
    sw = explainer["swcr_true_miss_lift"]
    assert sw["gate_passed"] is True
    assert sw["best_first_gold_rank"] == 12


def test_write_slice_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "slice.json"
    payload = {"queries": [{"id": "x"}]}
    write_slice(out, payload)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == payload


def test_stage1_runner_enforces_test_gate() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_nextplaid_stage1.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--starfinder-index",
            "sf",
            "--phb-index",
            "phb",
            "--swcr-index",
            "swcr",
            "--swcr-per-query-clean-subset",
            "dummy.json",
            "--test-gate-cmd",
            f"{sys.executable} -c \"import sys; sys.exit(2)\"",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "NextPlaid test gate failed" in (proc.stderr + proc.stdout)


def test_slice_integrity_summary_flags_missing_required_gold() -> None:
    payload = {
        "queries": [
            {"id": "q1", "required_gold": ["alive", "dead"]},
            {"id": "q2", "required_gold": ["alive"]},
            {"id": "q3", "gold_unit_ids": ["legacy_only"]},
        ]
    }
    id_map = {"alive": {"id": "alive"}, "legacy_only": {"id": "legacy_only"}}
    summary = _slice_integrity_summary(slice_payload=payload, id_map=id_map)
    assert summary["queries_with_missing_required_gold"] == 1
    assert summary["missing_required_gold_total"] == 1
    assert summary["rows"][0]["query_id"] == "q1"
    assert summary["rows"][0]["missing_required_gold_ids"] == ["dead"]

