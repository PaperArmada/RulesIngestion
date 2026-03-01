#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_PATH = ROOT / "evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json"
MAPPING_PATH = ROOT / "evals/retrieval/StarFinderPlayerCore/starfinder_player_core_blind_eval_50q_legacy_to_current_map.json"
RETRIEVED_PATH = ROOT / "out/retrieval_lab/experiments/starfinder_player_core_atomic_rules_20260228_062632/retrieved_chunks.json"
OUT_PATH = ROOT / "evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_gold_recommendations.json"


@dataclass
class ScoredChunk:
    chunk_id: str
    rank: int
    score: float
    text: str


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


def _score(a: str, b: str) -> float:
    a_n = _normalize(a)
    b_n = _normalize(b)
    if not a_n or not b_n:
        return 0.0
    jac = _jaccard(a_n, b_n)
    seq = SequenceMatcher(None, a_n, b_n).ratio()
    contains = 1.0 if (a_n in b_n or b_n in a_n) else 0.0
    return 0.55 * jac + 0.35 * seq + 0.10 * contains


def _split_facets(summary: str) -> list[str]:
    s = summary.replace(" vs ", ". ").replace(" and ", ". ")
    parts = [p.strip() for p in re.split(r"[.;:]", s) if p.strip()]
    # Keep only non-trivial facets
    return [p for p in parts if len(_tokens(p)) >= 4][:6]


def _legacy_best_scores(legacy_items: list[dict[str, Any]], retrieved: list[dict[str, Any]]) -> dict[str, float]:
    best_by_chunk: dict[str, float] = {}
    for lg in legacy_items:
        legacy_text = str(lg.get("legacy_text_excerpt", "")).strip()
        if not legacy_text:
            continue
        for c in retrieved[:20]:
            cid = str(c.get("chunk_id", "")).strip()
            text = str(c.get("text", "")).strip()
            if not cid or not text:
                continue
            s = _score(legacy_text, text)
            if s > best_by_chunk.get(cid, -1.0):
                best_by_chunk[cid] = s
    return best_by_chunk


def main() -> None:
    benchmark = _read_json(BENCHMARK_PATH)
    mapping = _read_json(MAPPING_PATH)
    retrieved = _read_json(RETRIEVED_PATH)
    by_model = retrieved.get("by_model") or {}
    model_key = "all-mpnet-base-v2" if "all-mpnet-base-v2" in by_model else next(iter(by_model.keys()), "")
    if not model_key:
        raise SystemExit("No model entries found in retrieved_chunks.json")

    reviews = by_model[model_key]
    review_by_qid = {str(r.get("query_id")): r for r in reviews}
    map_by_qid = {str(m.get("query_id")): m for m in mapping.get("queries", [])}

    out_rows: list[dict[str, Any]] = []

    for q in benchmark.get("queries", []):
        qid = str(q.get("id", ""))
        review = review_by_qid.get(qid, {})
        retrieved_chunks = review.get("retrieved") or []
        if not retrieved_chunks:
            out_rows.append(
                {
                    "query_id": qid,
                    "recommended_required_gold": [],
                    "recommended_supporting_gold": [],
                    "confidence": "low",
                    "rationale": "No retrieved chunks available for recommendation.",
                }
            )
            continue

        legacy_items = (map_by_qid.get(qid, {}) or {}).get("legacy_gold", [])
        legacy_scores = _legacy_best_scores(legacy_items, retrieved_chunks)

        facets = _split_facets(str(q.get("expected_answer_summary", "")))
        candidate_scores: list[ScoredChunk] = []
        for c in retrieved_chunks[:20]:
            cid = str(c.get("chunk_id", "")).strip()
            text = str(c.get("text", "")).strip()
            if not cid or not text:
                continue
            rank = int(c.get("rank", 999))
            legacy_component = legacy_scores.get(cid, 0.0)
            facet_component = max((_score(f, text) for f in facets), default=0.0)
            summary_component = _score(str(q.get("expected_answer_summary", "")), text)
            # Emphasize legacy-text alignment + summary fit + facet specificity.
            composite = 0.45 * legacy_component + 0.35 * summary_component + 0.20 * facet_component
            candidate_scores.append(ScoredChunk(chunk_id=cid, rank=rank, score=composite, text=text))

        candidate_scores.sort(key=lambda x: (-x.score, x.rank))
        if not candidate_scores:
            out_rows.append(
                {
                    "query_id": qid,
                    "recommended_required_gold": [],
                    "recommended_supporting_gold": [],
                    "confidence": "low",
                    "rationale": "No non-empty candidates in top-20 retrieved chunks.",
                }
            )
            continue

        # Require at least one strong anchor; add diverse support for multi-evidence answers.
        required: list[str] = [candidate_scores[0].chunk_id]
        supporting: list[str] = []
        seen = {required[0]}
        for cand in candidate_scores[1:]:
            if cand.chunk_id in seen:
                continue
            # Keep supporting when sufficiently relevant or when query clearly multi-facet.
            threshold = 0.30 if len(facets) >= 2 else 0.34
            if cand.score < threshold:
                continue
            supporting.append(cand.chunk_id)
            seen.add(cand.chunk_id)
            # Cap support to keep benchmark focused.
            if len(supporting) >= 3:
                break

        top = candidate_scores[0]
        if top.score >= 0.52:
            confidence = "high"
        elif top.score >= 0.38:
            confidence = "medium"
        else:
            confidence = "low"

        rationale = (
            f"Top anchor rank={top.rank}, composite={top.score:.3f}; "
            f"facets={len(facets)}; legacy_items={len(legacy_items)}. "
            "Supporting chunks selected for additional facet coverage from top-20 retrieval."
        )

        out_rows.append(
            {
                "query_id": qid,
                "question": q.get("question", ""),
                "recommended_required_gold": required,
                "recommended_supporting_gold": supporting,
                "confidence": confidence,
                "rationale": rationale,
            }
        )

    payload = {
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_benchmark": str(BENCHMARK_PATH.relative_to(ROOT)),
            "source_mapping": str(MAPPING_PATH.relative_to(ROOT)),
            "source_retrieved_chunks": str(RETRIEVED_PATH.relative_to(ROOT)),
            "model_key": model_key,
            "query_count": len(out_rows),
            "notes": "Recommendation-only artifact; does not modify benchmark.",
        },
        "recommendations": out_rows,
    }
    _write_json(OUT_PATH, payload)
    print(f"Wrote recommendations: {OUT_PATH}")


if __name__ == "__main__":
    main()
