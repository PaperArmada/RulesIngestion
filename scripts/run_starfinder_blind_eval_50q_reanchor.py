#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_units_by_heading,
)


ROOT = Path(__file__).resolve().parent.parent

BATCH_FILES = [
    ROOT / "Archive/marker-era/blind_eval/StarFinderPlayerCore/batch_001.json",
    ROOT / "Archive/marker-era/blind_eval/StarFinderPlayerCore/batch_002_state.json",
    ROOT / "Archive/marker-era/blind_eval/StarFinderPlayerCore/batch_003_grounding.json",
    ROOT / "Archive/marker-era/blind_eval/StarFinderPlayerCore/batch_004_temporal.json",
    ROOT / "Archive/marker-era/blind_eval/StarFinderPlayerCore/batch_005_constraints.json",
    ROOT / "Archive/marker-era/blind_eval/StarFinderPlayerCore/batch_006_conceptual.json",
]
GOLD_AUDIT_PATH = ROOT / "Archive/marker-era/blind_eval/gold_audit/gold_audit.json"
BENCHMARK_PATH = ROOT / "evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json"
MAPPING_PATH = ROOT / "evals/retrieval/StarFinderPlayerCore/starfinder_player_core_blind_eval_50q_legacy_to_current_map.json"
EXPERIMENTS_DIR = ROOT / "out/retrieval_lab/experiments"
CONFIG_PATH = ROOT / "retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml"
RUN_ID = "retrieval_lab_StarFinderPlayerCore_3c35ef696820"
EXPERIMENT_NAME = "starfinder_player_core_50q"
SUBSTRATE_DIR = ROOT / "out/StarFinderPlayerCore"
MIN_CHARS = 200
MERGE_CHUNKS = True
MERGE_MAX_CHARS = 2000


@dataclass
class Match:
    chunk_id: str
    score: float
    rank: int
    text: str
    reason: str


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9'\-]*", _normalize(text)))


def _jaccard(a: str, b: str) -> float:
    ta = _tokens(a)
    tb = _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _combined_score(a: str, b: str) -> tuple[float, str]:
    a_n = _normalize(a)
    b_n = _normalize(b)
    if not a_n or not b_n:
        return 0.0, "empty_text"

    jac = _jaccard(a_n, b_n)
    ratio = SequenceMatcher(None, a_n, b_n).ratio()
    contains = 1.0 if (a_n in b_n or b_n in a_n) else 0.0
    score = 0.55 * jac + 0.35 * ratio + 0.10 * contains
    reason = f"jac={jac:.3f}, seq={ratio:.3f}, contains={contains:.1f}"
    return score, reason


def build_merged_benchmark() -> dict[str, Any]:
    queries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for batch_path in BATCH_FILES:
        batch = _read_json(batch_path)
        for q in batch.get("queries", []):
            qid = str(q.get("id", "")).strip()
            if not qid:
                continue
            if qid in seen_ids:
                raise ValueError(f"Duplicate query id while merging: {qid}")
            seen_ids.add(qid)
            merged_q = {
                "id": qid,
                "tier": q.get("tier") or "T2",
                "question_type": "blind_eval",
                "question": q.get("question", ""),
                "expected_answer_summary": q.get("expected_answer_summary", ""),
                "source_page": q.get("source_page"),
                "notes": q.get("notes", ""),
                "legacy_gold_chunk_ids": list(q.get("gold_chunk_ids") or []),
                "gold_unit_ids": [],
                "required_gold": [],
                "supporting_gold": [],
                "_required_gold": [],
                "_supporting_gold": [],
                "gold_locations": {},
            }
            queries.append(merged_q)

    merged = {
        "metadata": {
            "batch_ids": ["001", "002", "003", "004", "005", "006"],
            "source": "marker-era blind_eval StarFinderPlayerCore",
            "merged_at": datetime.now(timezone.utc).isoformat(),
            "query_count": len(queries),
            "current_run_id": RUN_ID,
        },
        "queries": queries,
    }
    if len(queries) != 50:
        raise ValueError(f"Expected 50 queries after merge, found {len(queries)}")
    _write_json(BENCHMARK_PATH, merged)
    return merged


def run_eval_only() -> Path:
    command = [
        "uv",
        "run",
        "python",
        "-m",
        "retrieval_lab.run_experiment",
        "--config",
        str(CONFIG_PATH.relative_to(ROOT)),
        "--experiment-name",
        EXPERIMENT_NAME,
        "--batches",
        str(BENCHMARK_PATH.relative_to(ROOT)),
        "--run-id",
        RUN_ID,
    ]
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"Eval command failed with exit code {proc.returncode}")

    match = re.search(r"Done\. Experiment ID:\s*([A-Za-z0-9_\-]+)", proc.stdout)
    if not match:
        raise RuntimeError("Could not parse experiment id from run_experiment output")
    experiment_id = match.group(1)
    output_dir = EXPERIMENTS_DIR / experiment_id
    if not output_dir.exists():
        raise RuntimeError(f"Output directory not found for experiment {experiment_id}")
    return output_dir


def build_corpus_id_set() -> set[str]:
    corpus = load_evidence_units(SUBSTRATE_DIR, "StarFinderPlayerCore")
    if MIN_CHARS > 0:
        corpus = fold_under_threshold_into_adjacent(corpus, min_chars=MIN_CHARS)
    if MERGE_CHUNKS:
        corpus = merge_units_by_heading(corpus, max_chars=MERGE_MAX_CHARS)
    return {str(item.get("id", "")).strip() for item in corpus if str(item.get("id", "")).strip()}


def reanchor_gold(output_dir: Path, merged: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    gold_audit = _read_json(GOLD_AUDIT_PATH)
    retrieved = _read_json(output_dir / "retrieved_chunks.json")
    by_model = retrieved.get("by_model") or {}
    model_key = "all-mpnet-base-v2" if "all-mpnet-base-v2" in by_model else next(iter(by_model.keys()), "")
    if not model_key:
        raise RuntimeError("retrieved_chunks.json has no by_model entries")
    reviews = by_model.get(model_key) or []
    reviews_by_qid = {str(r.get("query_id")): r for r in reviews}

    gold_by_qid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in gold_audit.get("gold_items", []):
        qid = str(item.get("query_id", ""))
        if qid:
            gold_by_qid[qid].append(item)

    map_rows: list[dict[str, Any]] = []
    updated_queries: list[dict[str, Any]] = []

    for q in merged.get("queries", []):
        qid = str(q.get("id", ""))
        legacy_items = gold_by_qid.get(qid, [])
        review = reviews_by_qid.get(qid, {})
        candidates = (review.get("retrieved") or [])[:20]

        best_by_chunk: dict[str, Match] = {}
        unmapped = 0
        for legacy in legacy_items:
            legacy_text = str(legacy.get("chunk_text") or "")
            if not legacy_text.strip():
                unmapped += 1
                continue
            best: Match | None = None
            for c in candidates:
                chunk_id = str(c.get("chunk_id", "")).strip()
                cand_text = str(c.get("text") or "")
                if not chunk_id or not cand_text.strip():
                    continue
                score, reason = _combined_score(legacy_text, cand_text)
                rank = int(c.get("rank", 999))
                m = Match(chunk_id=chunk_id, score=score, rank=rank, text=cand_text, reason=reason)
                if (best is None) or (m.score > best.score) or (m.score == best.score and m.rank < best.rank):
                    best = m
            if best is None or best.score < 0.30:
                unmapped += 1
                continue
            cur = best_by_chunk.get(best.chunk_id)
            if cur is None or best.score > cur.score:
                best_by_chunk[best.chunk_id] = best

        ranked = sorted(best_by_chunk.values(), key=lambda m: (-m.score, m.rank))
        required: list[str] = []
        supporting: list[str] = []
        confidence = "low"
        rationale = "No reliable current-corpus equivalent found in top-20 retrieved chunks."
        if ranked:
            required = [ranked[0].chunk_id]
            supporting = [m.chunk_id for m in ranked[1:] if m.score >= 0.38]
            top = ranked[0]
            if top.score >= 0.55 and unmapped == 0:
                confidence = "high"
            elif top.score >= 0.40:
                confidence = "medium"
            rationale = (
                "Selected by highest text overlap between legacy gold chunk_text and current retrieved chunks; "
                f"top match rank={top.rank}, score={top.score:.3f} ({top.reason})."
            )

        dedup = list(dict.fromkeys(required + supporting))
        q["required_gold"] = required
        q["supporting_gold"] = [x for x in supporting if x not in set(required)]
        q["gold_unit_ids"] = dedup
        q["_required_gold"] = list(q["required_gold"])
        q["_supporting_gold"] = list(q["supporting_gold"])
        if "gold_locations" not in q or q["gold_locations"] is None:
            q["gold_locations"] = {}
        updated_queries.append(q)

        map_rows.append(
            {
                "query_id": qid,
                "legacy_gold": [
                    {
                        "legacy_chunk_id": str(g.get("chunk_id", "")),
                        "legacy_text_excerpt": str(g.get("chunk_text", ""))[:240],
                    }
                    for g in legacy_items
                ],
                "current_selected_required": list(q["required_gold"]),
                "current_selected_supporting": list(q["supporting_gold"]),
                "selection_rationale": rationale,
                "confidence": confidence,
                "unmapped_legacy_gold_count": int(unmapped),
            }
        )

    merged["queries"] = updated_queries
    mapping_payload = {
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_id": RUN_ID,
            "retrieved_chunks_path": str((output_dir / "retrieved_chunks.json").relative_to(ROOT)),
            "model_key": model_key,
            "query_count": len(map_rows),
        },
        "queries": map_rows,
    }
    return merged, mapping_payload


def enforce_integrity(merged: dict[str, Any], corpus_ids: set[str]) -> None:
    queries = merged.get("queries", [])
    if len(queries) != 50:
        raise ValueError(f"Expected 50 queries, found {len(queries)}")
    ids = [str(q.get("id", "")) for q in queries]
    if len(set(ids)) != 50:
        raise ValueError("Query IDs are not unique after processing")

    invalid_ids: list[tuple[str, str]] = []
    for q in queries:
        qid = str(q.get("id", ""))
        req = [str(x) for x in (q.get("required_gold") or []) if str(x).strip()]
        sup = [str(x) for x in (q.get("supporting_gold") or []) if str(x).strip()]
        all_ids = [str(x) for x in (q.get("gold_unit_ids") or []) if str(x).strip()]
        expected = list(dict.fromkeys(req + sup))

        if all_ids != expected:
            raise ValueError(f"{qid}: gold_unit_ids != required+supporting")
        if q.get("_required_gold") != req:
            raise ValueError(f"{qid}: _required_gold mismatch")
        if q.get("_supporting_gold") != sup:
            raise ValueError(f"{qid}: _supporting_gold mismatch")
        if len(req) != len(set(req)) or len(sup) != len(set(sup)):
            raise ValueError(f"{qid}: duplicate IDs in required/supporting")
        for uid in req:
            if uid not in corpus_ids:
                invalid_ids.append((qid, uid))
    if invalid_ids:
        preview = ", ".join([f"{qid}:{uid}" for qid, uid in invalid_ids[:8]])
        raise ValueError(f"required_gold IDs missing from current corpus index ({len(invalid_ids)}): {preview}")


def main() -> None:
    print("Building merged benchmark...")
    merged = build_merged_benchmark()
    print(f"Wrote benchmark: {BENCHMARK_PATH.relative_to(ROOT)} ({len(merged['queries'])} queries)")

    print("Running eval-only retrieval...")
    output_dir = run_eval_only()
    print(f"Eval output: {output_dir.relative_to(ROOT)}")

    print("Re-anchoring legacy gold to current corpus IDs...")
    merged, mapping = reanchor_gold(output_dir, merged)

    print("Validating integrity constraints...")
    corpus_ids = build_corpus_id_set()
    enforce_integrity(merged, corpus_ids)

    _write_json(BENCHMARK_PATH, merged)
    _write_json(MAPPING_PATH, mapping)
    print(f"Wrote mapping: {MAPPING_PATH.relative_to(ROOT)}")

    print("Done.")


if __name__ == "__main__":
    main()
