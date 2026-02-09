"""
Gold grounding: map queries to EvidenceUnit IDs either by page + text overlap
(page-anchored) or by corpus-wide semantic similarity (when source_page is null).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def _jaccard_tokens(a: str, b: str) -> float:
    """Jaccard similarity between two strings (word tokens)."""
    if not a.strip() or not b.strip():
        return 0.0
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _rubric_fields(q: Dict[str, Any]) -> Dict[str, Any]:
    """Extract optional rubric fields for grounding_audit (refusal_acceptable, accept_qualified_answer, scoring_rubric)."""
    out: Dict[str, Any] = {}
    if q.get("refusal_acceptable"):
        out["refusal_acceptable"] = True
    if q.get("accept_qualified_answer"):
        out["accept_qualified_answer"] = True
    if q.get("scoring_rubric"):
        out["scoring_rubric"] = q["scoring_rubric"]
    return out


def ground_queries_page_anchored(
    queries: List[Dict[str, Any]],
    units_by_page: Dict[int, List[Dict[str, Any]]],
    threshold: float = 0.15,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    For each query with source_page set and empty gold_unit_ids, find EvidenceUnits
    on that page whose text overlaps expected_answer_summary above threshold.
    Returns (grounded_queries with gold_unit_ids populated, grounding_audit).
    """
    grounded = []
    audit = []
    for q in queries:
        q = dict(q)
        query_id = q.get("id", "")
        gold_ids = list(q.get("gold_unit_ids") or [])
        source_page = q.get("source_page")
        summary = (q.get("expected_answer_summary") or "").strip()
        if gold_ids:
            q["gold_unit_ids"] = gold_ids
            grounded.append(q)
            audit.append({
                "query_id": query_id,
                "method": "prefilled",
                "gold_unit_ids": gold_ids,
                "count": len(gold_ids),
                **_rubric_fields(q),
            })
            continue
        if source_page is None or (isinstance(source_page, str) and not str(source_page).strip()):
            grounded.append(q)
            audit.append({
                "query_id": query_id,
                "method": "page_anchored_skipped",
                "reason": "source_page is null or empty",
                "gold_unit_ids": [],
                "count": 0,
                **_rubric_fields(q),
            })
            continue
        try:
            page_num = int(source_page)
        except (TypeError, ValueError):
            grounded.append(q)
            audit.append({
                "query_id": query_id,
                "method": "page_anchored_skipped",
                "reason": "source_page not convertible to int",
                "gold_unit_ids": [],
                "count": 0,
                **_rubric_fields(q),
            })
            continue
        page_units = units_by_page.get(page_num, [])
        if not summary or not page_units:
            grounded.append(q)
            audit.append({
                "query_id": query_id,
                "method": "page_anchored",
                "gold_unit_ids": [],
                "count": 0,
                "reason": "no summary or no units on page",
                **_rubric_fields(q),
            })
            continue
        matched = []
        scores_list = []
        for u in page_units:
            score = _jaccard_tokens(summary, u.get("text", ""))
            if score >= threshold:
                matched.append(u["id"])
                scores_list.append(round(score, 4))
        q["gold_unit_ids"] = matched
        grounded.append(q)
        audit.append({
            "query_id": query_id,
            "method": "page_anchored",
            "gold_unit_ids": matched,
            "scores": scores_list,
            "count": len(matched),
            **_rubric_fields(q),
        })
    return grounded, audit


def ground_queries_corpus_semantic(
    queries: List[Dict[str, Any]],
    summary_embeddings: np.ndarray,
    corpus_embeddings: np.ndarray,
    corpus_ids: List[str],
    top_n: int = 5,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    For each query, use cosine similarity between its expected_answer_summary embedding
    and all corpus embeddings; take top_n corpus unit IDs as gold proxy.
    summary_embeddings: (n_queries, dim), same order as queries.
    corpus_embeddings: (n_corpus, dim).
    corpus_ids: list of unit_id for each corpus row.
    Returns (grounded_queries with gold_unit_ids set, grounding_audit).
    """
    if summary_embeddings.shape[0] != len(queries):
        raise ValueError("summary_embeddings row count must match len(queries)")
    if corpus_embeddings.shape[0] != len(corpus_ids):
        raise ValueError("corpus_embeddings row count must match len(corpus_ids)")
    # Normalize for cosine similarity (dot product)
    q_norm = summary_embeddings / (np.linalg.norm(summary_embeddings, axis=1, keepdims=True) + 1e-9)
    c_norm = corpus_embeddings / (np.linalg.norm(corpus_embeddings, axis=1, keepdims=True) + 1e-9)
    sim = np.dot(q_norm, c_norm.T)  # (n_queries, n_corpus)
    grounded = []
    audit = []
    for i, q in enumerate(queries):
        q = dict(q)
        query_id = q.get("id", "")
        if q.get("gold_unit_ids"):
            q["gold_unit_ids"] = list(q["gold_unit_ids"])
            grounded.append(q)
            audit.append({
                "query_id": query_id,
                "method": "prefilled",
                "gold_unit_ids": q["gold_unit_ids"],
                "count": len(q["gold_unit_ids"]),
                **_rubric_fields(q),
            })
            continue
        row = sim[i]
        top_indices = np.argsort(row)[::-1][:top_n]
        gold_ids = [corpus_ids[j] for j in top_indices]
        scores = [round(float(row[j]), 4) for j in top_indices]
        q["gold_unit_ids"] = gold_ids
        grounded.append(q)
        audit.append({
            "query_id": query_id,
            "method": "corpus_wide_semantic",
            "gold_unit_ids": gold_ids,
            "scores": scores,
            "count": len(gold_ids),
            **_rubric_fields(q),
        })
    return grounded, audit


def _normalize_query(q: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure expected_answer_summary exists; use 'answer' if present."""
    if "expected_answer_summary" not in q or q["expected_answer_summary"] is None:
        q["expected_answer_summary"] = q.get("answer") or ""
    return q


def flatten_query_batches(batch_paths: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Load one or more query batch JSON files and flatten to a single list of queries.
    Each batch file can have format { "batches": [ { "batch_id", "suite", "queries": [...] } ] }
    or legacy { "queries": [...] }.
    Returns (flat list of queries with batch_id and suite attached, list of suite names in order).
    """
    import json
    from pathlib import Path
    flat = []
    suites_seen = []
    for path in batch_paths:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Query batch not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        if "batches" in data:
            for batch in data["batches"]:
                batch_id = batch.get("batch_id", "")
                suite = batch.get("suite", "default")
                for q in batch.get("queries", []):
                    q = _normalize_query(dict(q))
                    q["_batch_id"] = batch_id
                    q["_suite"] = suite
                    flat.append(q)
                if suite not in suites_seen:
                    suites_seen.append(suite)
        elif "queries" in data:
            for q in data["queries"]:
                q = _normalize_query(dict(q))
                q["_batch_id"] = data.get("metadata", {}).get("batch_id", "")
                q["_suite"] = "default"
                flat.append(q)
            if "default" not in suites_seen:
                suites_seen.append("default")
        elif isinstance(data, list):
            for q in data:
                q = _normalize_query(dict(q))
                q["_batch_id"] = ""
                q["_suite"] = "default"
                flat.append(q)
            if "default" not in suites_seen:
                suites_seen.append("default")
        else:
            raise ValueError(f"Unknown query batch format: no 'batches', 'queries', or root array in {path}")
    return flat, suites_seen
