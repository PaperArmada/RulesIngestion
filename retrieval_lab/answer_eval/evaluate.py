from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

from retrieval_lab.answer_eval.schema import AnswerResponse


class AnswerGenerator(Protocol):
    def generate(
        self,
        *,
        question: str,
        evidence: List[Dict[str, Any]],
        expected_answer_summary: str = "",
    ) -> AnswerResponse: ...


def _stable_query_subset(
    query_ids: Iterable[str],
    *,
    max_queries: int,
) -> List[str]:
    ids = sorted([str(qid) for qid in query_ids if str(qid)])
    if max_queries <= 0:
        return ids
    return ids[:max_queries]


def evaluate_answers_for_model(
    *,
    query_reviews: List[Dict[str, Any]],
    grounded_queries: List[Dict[str, Any]],
    top_k: int,
    generator: AnswerGenerator,
    max_queries: int = 20,
    max_chars_per_unit: int = 1200,
) -> Dict[str, Any]:
    """Run answer generation and compute lightweight rubric proxies.

    This is intentionally minimal and deterministic in which queries are selected
    (sorted by query_id, then truncated to max_queries).
    """
    q_by_id = {str(q.get("id", "")): q for q in grounded_queries if q.get("id")}
    review_by_id = {str(r.get("query_id", "")): r for r in query_reviews if r.get("query_id")}

    selected_ids = _stable_query_subset(review_by_id.keys(), max_queries=max_queries)
    per_query: List[Dict[str, Any]] = []

    for qid in selected_ids:
        q = q_by_id.get(qid, {})
        review = review_by_id.get(qid, {})

        retrieved = (review.get("retrieved") or [])[: max(0, int(top_k))]
        evidence: List[Dict[str, Any]] = []
        for r in retrieved:
            cid = str(r.get("chunk_id") or "")
            txt = str(r.get("text") or "")
            if max_chars_per_unit > 0 and len(txt) > max_chars_per_unit:
                txt = txt[: max_chars_per_unit].rstrip() + "…"
            evidence.append({"chunk_id": cid, "text": txt, "rank": int(r.get("rank") or 0)})

        required_gold = [str(x).strip() for x in (q.get("_required_gold") or []) if str(x).strip()]
        required_set = set(required_gold)
        top_ids = [e.get("chunk_id", "") for e in evidence if e.get("chunk_id")]
        top_set = set(top_ids)

        required_all_in_topk = bool(required_set) and required_set.issubset(top_set)
        should_refuse = bool(required_set) and not required_all_in_topk

        resp = generator.generate(
            question=str(review.get("question") or q.get("question") or ""),
            evidence=evidence,
            expected_answer_summary=str(review.get("expected_answer_summary") or q.get("expected_answer_summary") or ""),
        )
        cited = [str(x).strip() for x in (resp.citations or []) if str(x).strip()]
        # Unique, stable order.
        cited_unique: List[str] = list(dict.fromkeys(cited))
        cited_set = set(cited_unique)
        invalid_citations = [c for c in cited_unique if c not in top_set]

        required_cited_rate = (len(required_set & cited_set) / len(required_set)) if required_set else None
        invalid_citation_rate = (len(invalid_citations) / len(cited_unique)) if cited_unique else 0.0

        per_query.append(
            {
                "query_id": qid,
                "top_k": int(top_k),
                "required_gold": required_gold,
                "required_all_in_topk": required_all_in_topk if required_set else None,
                "should_refuse": should_refuse if required_set else None,
                "response": resp.to_dict(),
                "citations_unique": cited_unique,
                "invalid_citations": invalid_citations,
                "required_cited_rate": required_cited_rate,
                "invalid_citation_rate": invalid_citation_rate,
                "refusal_correct": (resp.refusal == should_refuse) if required_set else None,
            }
        )

    refusal_correct_vals = [p["refusal_correct"] for p in per_query if p.get("refusal_correct") is not None]
    required_cited_vals = [p["required_cited_rate"] for p in per_query if isinstance(p.get("required_cited_rate"), (int, float))]
    invalid_cite_vals = [p["invalid_citation_rate"] for p in per_query if isinstance(p.get("invalid_citation_rate"), (int, float))]
    refusals = [bool(p.get("response", {}).get("refusal")) for p in per_query]

    summary = {
        "n_queries": len(per_query),
        "top_k": int(top_k),
        "refusal_rate": (sum(1 for r in refusals if r) / len(refusals)) if refusals else 0.0,
        "refusal_accuracy": (sum(1 for v in refusal_correct_vals if v) / len(refusal_correct_vals)) if refusal_correct_vals else None,
        "required_cited_rate_mean": (sum(required_cited_vals) / len(required_cited_vals)) if required_cited_vals else None,
        "invalid_citation_rate_mean": (sum(invalid_cite_vals) / len(invalid_cite_vals)) if invalid_cite_vals else 0.0,
        "issue_counts": dict(
            Counter(
                "invalid_citations_present"
                for p in per_query
                if p.get("invalid_citations")
            )
        ),
    }
    return {"summary": summary, "per_query": per_query, "selected_query_ids": selected_ids}

