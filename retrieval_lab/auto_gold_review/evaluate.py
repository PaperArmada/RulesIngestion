from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Protocol, Tuple

from retrieval_lab.auto_gold_review.schema import GoldReviewResponse


class GoldChunkReviewer(Protocol):
    def review(
        self,
        *,
        question: str,
        expected_answer_summary: str,
        notes: str,
        query_metadata: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> GoldReviewResponse: ...


def _dedupe_preserve(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _is_positive_query(query: Dict[str, Any]) -> bool:
    suite = str(query.get("suite") or query.get("_suite") or "").strip().lower()
    question_type = str(query.get("question_type") or "").strip().lower()
    return suite != "negative" and question_type != "negative"


def _normalize_candidate(candidate: Dict[str, Any], *, max_chars_per_chunk: int) -> Dict[str, Any]:
    text = str(candidate.get("text") or "")
    if max_chars_per_chunk > 0 and len(text) > max_chars_per_chunk:
        text = text[: max_chars_per_chunk].rstrip() + "..."
    return {
        "rank": int(candidate.get("rank") or 0),
        "chunk_id": str(candidate.get("chunk_id") or ""),
        "score": float(candidate.get("score") or 0.0),
        "text": text,
        "page": candidate.get("page"),
        "structural_path": list(candidate.get("structural_path") or []),
        "source_unit_ids": list(candidate.get("source_unit_ids") or []),
    }


def _build_gold_locations(candidate_map: Dict[str, Dict[str, Any]], chunk_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for chunk_id in chunk_ids:
        candidate = candidate_map.get(chunk_id)
        if candidate is None:
            continue
        location: Dict[str, Any] = {
            "page": candidate.get("page"),
            "structural_path": list(candidate.get("structural_path") or []),
        }
        source_unit_ids = [str(x).strip() for x in (candidate.get("source_unit_ids") or []) if str(x).strip()]
        if source_unit_ids:
            location["source_unit_ids"] = source_unit_ids
        out[chunk_id] = location
    return out


def _confidence_rank(confidence: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(str(confidence).strip().lower(), 0)


def score_review_difficulty(recommendation: Dict[str, Any]) -> Tuple[int, str]:
    required_ranks = recommendation.get("selected_required_ranks") or []
    review_flags = recommendation.get("review_flags") or []
    confidence = str(recommendation.get("confidence") or "low")
    max_rank = max((int(x) for x in required_ranks), default=0)
    difficulty = max_rank
    if len(required_ranks) > 1:
        difficulty += 4
    if "multi_part_question" in review_flags:
        difficulty += 3
    if "weak_anchor" in review_flags:
        difficulty += 2
    if "close_second_choice" in review_flags:
        difficulty += 2
    difficulty += max(0, 2 - _confidence_rank(confidence))
    return difficulty, str(recommendation.get("query_id") or "")


def _sanitize_review_response(
    *,
    query: Dict[str, Any],
    response: GoldReviewResponse,
    candidates: List[Dict[str, Any]],
    max_required_gold: int,
    max_supporting_gold: int,
) -> Dict[str, Any]:
    candidate_map = {str(c.get("chunk_id") or ""): c for c in candidates if c.get("chunk_id")}
    candidate_ids = set(candidate_map.keys())
    review_flags = _dedupe_preserve(response.review_flags or [])

    required_gold = [chunk_id for chunk_id in _dedupe_preserve(response.required_gold) if chunk_id in candidate_ids]
    supporting_gold = [
        chunk_id
        for chunk_id in _dedupe_preserve(response.supporting_gold)
        if chunk_id in candidate_ids and chunk_id not in set(required_gold)
    ]
    proposed_ids = set(_dedupe_preserve(list(response.required_gold) + list(response.supporting_gold)))
    if proposed_ids - candidate_ids:
        review_flags.append("invalid_candidate_reference")

    if len(required_gold) > max_required_gold:
        required_gold = required_gold[:max_required_gold]
        review_flags.append("required_gold_trimmed")
    if len(supporting_gold) > max_supporting_gold:
        supporting_gold = supporting_gold[:max_supporting_gold]
        review_flags.append("supporting_gold_trimmed")

    selected_required_ranks = [
        int(candidate_map[chunk_id].get("rank") or 0)
        for chunk_id in required_gold
        if chunk_id in candidate_map
    ]
    if selected_required_ranks and max(selected_required_ranks) > 3 and "weak_anchor" not in review_flags:
        review_flags.append("weak_anchor")
    if len(required_gold) > 1 and "multi_part_question" not in review_flags:
        review_flags.append("multi_part_question")

    confidence = str(response.confidence or "low").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    needs_human_review = bool(response.needs_human_review) or confidence == "low"
    positive_query = _is_positive_query(query)
    applyable = True
    if positive_query and not required_gold:
        review_flags.append("no_clear_required_anchor")
        needs_human_review = True
        applyable = False

    rationale: Dict[str, str] = {}
    for chunk_id in required_gold:
        value = str((response.required_gold_rationale or {}).get(chunk_id) or "").strip()
        rationale[chunk_id] = value or "Selected as a minimal operational anchor from the reviewed candidates."

    gold_locations = _build_gold_locations(candidate_map, list(required_gold) + list(supporting_gold))
    return {
        "query_id": str(query.get("id") or ""),
        "question": str(query.get("question") or ""),
        "expected_answer_summary": str(query.get("expected_answer_summary") or query.get("answer") or ""),
        "notes": str(query.get("notes") or ""),
        "candidate_top_k": len(candidates),
        "top_candidates": candidates,
        "proposed_required_gold": required_gold,
        "proposed_supporting_gold": supporting_gold,
        "required_gold_rationale": rationale,
        "gold_locations": gold_locations,
        "confidence": confidence,
        "review_flags": _dedupe_preserve(review_flags),
        "needs_human_review": needs_human_review,
        "applyable": applyable,
        "selected_required_ranks": selected_required_ranks,
        "notes_from_reviewer": str(response.notes or ""),
        "reviewer_metadata": dict(response.metadata or {}),
    }


def build_review_queue(
    recommendations: List[Dict[str, Any]],
    *,
    challenge_sample_size: int,
    max_required_overlap: int,
) -> List[Dict[str, Any]]:
    required_counter = Counter(
        chunk_id
        for row in recommendations
        for chunk_id in (row.get("proposed_required_gold") or [])
    )
    queue_by_qid: Dict[str, Dict[str, Any]] = {}

    def _ensure_entry(row: Dict[str, Any], reason: str) -> None:
        qid = str(row.get("query_id") or "")
        if not qid:
            return
        if qid not in queue_by_qid:
            queue_by_qid[qid] = {
                "query_id": qid,
                "question": row.get("question", ""),
                "confidence": row.get("confidence", "low"),
                "review_flags": list(row.get("review_flags") or []),
                "queue_reasons": [],
                "proposed_required_gold": list(row.get("proposed_required_gold") or []),
                "proposed_supporting_gold": list(row.get("proposed_supporting_gold") or []),
                "required_gold_rationale": dict(row.get("required_gold_rationale") or {}),
                "gold_locations": dict(row.get("gold_locations") or {}),
                "top_candidates": list(row.get("top_candidates") or []),
            }
        reasons = queue_by_qid[qid]["queue_reasons"]
        if reason not in reasons:
            reasons.append(reason)

    for row in recommendations:
        flags = set(row.get("review_flags") or [])
        if row.get("needs_human_review"):
            _ensure_entry(row, "needs_human_review")
        if str(row.get("confidence") or "low") == "low":
            _ensure_entry(row, "low_confidence")
        if len(row.get("proposed_required_gold") or []) > 1:
            _ensure_entry(row, "multiple_required_anchors")
        if "multi_part_question" in flags:
            _ensure_entry(row, "multi_part_question")
        if "no_clear_required_anchor" in flags:
            _ensure_entry(row, "no_clear_required_anchor")
        if any(required_counter.get(chunk_id, 0) > max_required_overlap for chunk_id in (row.get("proposed_required_gold") or [])):
            flags.add("overlap_risk")
            row["review_flags"] = _dedupe_preserve(list(flags))
            _ensure_entry(row, "overlap_risk")

    eligible = [row for row in recommendations if str(row.get("query_id") or "") not in queue_by_qid]
    eligible.sort(key=score_review_difficulty, reverse=True)
    for row in eligible[: max(0, int(challenge_sample_size))]:
        _ensure_entry(row, "challenge_sample")

    queue = list(queue_by_qid.values())
    queue.sort(key=lambda row: (score_review_difficulty(row)[0] * -1, str(row.get("query_id") or "")))
    return queue


def _review_one(
    *,
    query_id: str,
    query: Dict[str, Any],
    review: Dict[str, Any],
    reviewer: GoldChunkReviewer,
    candidate_top_k: int,
    max_chars_per_chunk: int,
    max_required_gold: int,
    max_supporting_gold: int,
) -> Tuple[str, Dict[str, Any]]:
    """Run a single review; returns (query_id, recommendation_dict)."""
    candidates = [
        _normalize_candidate(candidate, max_chars_per_chunk=max_chars_per_chunk)
        for candidate in (review.get("retrieved") or [])[: max(0, int(candidate_top_k))]
        if str(candidate.get("chunk_id") or "").strip()
    ]
    response = reviewer.review(
        question=str(review.get("question") or query.get("question") or ""),
        expected_answer_summary=str(review.get("expected_answer_summary") or query.get("expected_answer_summary") or ""),
        notes=str(query.get("notes") or review.get("notes") or ""),
        query_metadata={
            "query_id": query_id,
            "tier": query.get("tier") or query.get("_tier") or "",
            "suite": query.get("suite") or query.get("_suite") or "",
            "question_type": query.get("question_type") or "",
        },
        candidates=candidates,
    )
    rec = _sanitize_review_response(
        query=query,
        response=response,
        candidates=candidates,
        max_required_gold=max_required_gold,
        max_supporting_gold=max_supporting_gold,
    )
    return (query_id, rec)


def evaluate_gold_reviews(
    *,
    query_reviews: List[Dict[str, Any]],
    grounded_queries: List[Dict[str, Any]],
    reviewer: GoldChunkReviewer,
    candidate_top_k: int = 20,
    max_queries: int = 0,
    max_chars_per_chunk: int = 1600,
    max_required_gold: int = 5,
    max_supporting_gold: int = 5,
    challenge_sample_size: int = 10,
    max_required_overlap: int = 2,
    max_workers: int = 8,
) -> Dict[str, Any]:
    query_by_id = {str(q.get("id") or ""): q for q in grounded_queries if q.get("id")}
    review_by_id = {str(r.get("query_id") or ""): r for r in query_reviews if r.get("query_id")}
    ordered_review_ids = [str(review.get("query_id") or "") for review in query_reviews if review.get("query_id")]
    if max_queries > 0:
        ordered_review_ids = ordered_review_ids[:max_queries]

    work: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    for query_id in ordered_review_ids:
        query = query_by_id.get(query_id)
        review = review_by_id.get(query_id)
        if query is None or review is None:
            continue
        work.append((query_id, query, review))

    use_parallel = max_workers > 1 and len(work) > 1
    recommendations: List[Dict[str, Any]] = []
    selected_query_ids: List[str] = []

    if use_parallel:
        results_by_qid: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _review_one,
                    query_id=qid,
                    query=query,
                    review=review,
                    reviewer=reviewer,
                    candidate_top_k=candidate_top_k,
                    max_chars_per_chunk=max_chars_per_chunk,
                    max_required_gold=max_required_gold,
                    max_supporting_gold=max_supporting_gold,
                ): qid
                for qid, query, review in work
            }
            for fut in as_completed(futures):
                qid, rec = fut.result()
                results_by_qid[qid] = rec
        for qid in ordered_review_ids:
            if qid in results_by_qid:
                recommendations.append(results_by_qid[qid])
                selected_query_ids.append(qid)
    else:
        for query_id, query, review in work:
            _, rec = _review_one(
                query_id=query_id,
                query=query,
                review=review,
                reviewer=reviewer,
                candidate_top_k=candidate_top_k,
                max_chars_per_chunk=max_chars_per_chunk,
                max_required_gold=max_required_gold,
                max_supporting_gold=max_supporting_gold,
            )
            recommendations.append(rec)
            selected_query_ids.append(query_id)

    review_queue = build_review_queue(
        recommendations,
        challenge_sample_size=challenge_sample_size,
        max_required_overlap=max_required_overlap,
    )
    summary = {
        "queries_reviewed": len(recommendations),
        "queries_applyable": sum(1 for row in recommendations if row.get("applyable")),
        "queries_needing_human_review": sum(1 for row in recommendations if row.get("needs_human_review")),
        "queue_size": len(review_queue),
        "confidence_counts": dict(Counter(str(row.get("confidence") or "low") for row in recommendations)),
        "flag_counts": dict(
            Counter(
                flag
                for row in recommendations
                for flag in (row.get("review_flags") or [])
            )
        ),
        "selected_query_ids": selected_query_ids,
    }
    return {
        "summary": summary,
        "recommendations": recommendations,
        "review_queue": review_queue,
    }
