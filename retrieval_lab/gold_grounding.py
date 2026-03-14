"""
Gold grounding: map queries to EvidenceUnit IDs either by page + text overlap
(page-anchored) or by corpus-wide semantic similarity (when source_page is null).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
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


def _normalize_gold_fields(q: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy/new gold fields onto a stable, backward-compatible shape."""
    required = [str(x).strip() for x in (q.get("required_gold") or []) if str(x).strip()]
    supporting = [str(x).strip() for x in (q.get("supporting_gold") or []) if str(x).strip()]
    legacy = [str(x).strip() for x in (q.get("gold_unit_ids") or []) if str(x).strip()]
    mode = str(q.get("mode") or "").strip() or None

    merged = list(dict.fromkeys(required + supporting + legacy))
    if merged:
        q["gold_unit_ids"] = merged
    else:
        q["gold_unit_ids"] = []

    if required:
        q["required_gold"] = list(dict.fromkeys(required))
    elif "required_gold" in q:
        q["required_gold"] = []

    if supporting:
        q["supporting_gold"] = list(dict.fromkeys(supporting))
    elif "supporting_gold" in q:
        q["supporting_gold"] = []

    if mode:
        q["mode"] = mode

    # Internal normalized fields used by metrics/reporting contract.
    q["_required_gold"] = q.get("required_gold") or list(q["gold_unit_ids"])
    q["_supporting_gold"] = q.get("supporting_gold") or []
    q["_mode"] = q.get("mode") or "single_cite"
    return q


def _path_key(unit: Dict[str, Any]) -> Tuple[int, str]:
    page = int(unit.get("page", -1))
    structural_path = unit.get("structural_path") or []
    return page, _normalize_structural_path(structural_path)


def _normalize_structural_path(structural_path: Any) -> str:
    """Normalize structural_path for robust benchmark→corpus matching.

    Mark III substrates may have OCR-case variance (e.g. ALL CAPS headings) and
    inconsistent whitespace. Benchmarks may use title case. We normalize to a
    case-insensitive, whitespace-collapsed join key.
    """
    if not structural_path:
        return ""
    return " > ".join(_normalize_structural_path_parts(structural_path))


def _normalize_structural_path_parts(structural_path: Any) -> list[str]:
    if not structural_path:
        return []
    raw_parts = structural_path if isinstance(structural_path, list) else [structural_path]
    parts: list[str] = []
    for raw in raw_parts:
        s = re.sub(r"\s+", " ", str(raw)).strip()
        if s:
            parts.append(s.casefold())
    return parts


def _is_suffix_path(shorter: list[str], longer: list[str]) -> bool:
    if not shorter:
        return False
    if len(shorter) > len(longer):
        return False
    return longer[-len(shorter) :] == shorter


def build_original_to_merged(
    folded_corpus: List[Dict[str, Any]],
    merged_corpus: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Map original unit IDs to merged chunk IDs for the active corpus."""
    folded_by_id = {u.get("id", ""): u for u in folded_corpus if u.get("id")}
    original_to_merged: Dict[str, str] = {}
    for merged in merged_corpus:
        merged_id = str(merged.get("id", "")).strip()
        if not merged_id:
            continue
        folded_ids = [str(x).strip() for x in (merged.get("source_unit_ids") or []) if str(x).strip()]
        for folded_id in folded_ids:
            folded_unit = folded_by_id.get(folded_id)
            if folded_unit is None:
                continue
            original_ids = [str(x).strip() for x in (folded_unit.get("source_unit_ids") or [folded_unit.get("id", "")]) if str(x).strip()]
            for original_id in original_ids:
                original_to_merged[original_id] = merged_id
    return original_to_merged


def resolve_gold_ids_for_query(
    query: Dict[str, Any],
    original_to_merged: Dict[str, str],
    merged_by_id: Dict[str, Dict[str, Any]],
) -> Tuple[List[str], List[str], List[str], Dict[str, Dict[str, Any]], Dict[str, str]]:
    """
    Resolve required/supporting/legacy gold IDs to current merged IDs using gold_locations.
    """
    required = [str(x).strip() for x in (query.get("required_gold") or []) if str(x).strip()]
    supporting = [str(x).strip() for x in (query.get("supporting_gold") or []) if str(x).strip()]
    legacy = [str(x).strip() for x in (query.get("gold_unit_ids") or []) if str(x).strip()]
    gold_locations = query.get("gold_locations") or {}
    old_rationale = query.get("required_gold_rationale") or {}
    if not required and not supporting:
        required = list(legacy or list(gold_locations.keys()))

    seen_new: set[str] = set()
    new_required: List[str] = []
    new_supporting: List[str] = []
    new_gold_locations: Dict[str, Dict[str, Any]] = {}
    new_rationale: Dict[str, str] = {}

    def resolve_one(old_id: str) -> List[str]:
        # Direct passthrough when benchmark already has active merged IDs.
        if old_id in merged_by_id:
            return [old_id]
        # Support original-id style references.
        if old_id in original_to_merged:
            return [original_to_merged[old_id]]

        loc = gold_locations.get(old_id) or {}
        source_ids = [str(x).strip() for x in (loc.get("source_unit_ids") or []) if str(x).strip()]
        if source_ids:
            out: List[str] = []
            for source_id in source_ids:
                merged_id = original_to_merged.get(source_id)
                if merged_id:
                    out.append(merged_id)
            if out:
                return list(dict.fromkeys(out))
            # source_unit_ids exist but none mapped — fall through to page+path

        page = loc.get("page")
        structural_path = loc.get("structural_path") or []
        if page is None:
            return []
        target_page = int(page)
        target_parts = _normalize_structural_path_parts(structural_path)
        if not target_parts:
            # No structural_path — return unheaded units on this page
            return [
                unit_id
                for unit_id, unit in merged_by_id.items()
                if int(unit.get("page", -1)) == target_page
                and not _normalize_structural_path_parts(unit.get("structural_path") or [])
            ]
        matches: list[str] = []
        for unit_id, unit in merged_by_id.items():
            if int(unit.get("page", -1)) != target_page:
                continue
            unit_parts = _normalize_structural_path_parts(unit.get("structural_path") or [])
            if not unit_parts:
                continue
            if unit_parts == target_parts:
                matches.append(unit_id)
                continue
            # Substrate often has fewer structural_path levels than benchmarks
            # (e.g. ["DICE"] vs ["Player Guide", "DICE"]).
            if _is_suffix_path(unit_parts, target_parts) or _is_suffix_path(target_parts, unit_parts):
                matches.append(unit_id)
        if matches:
            return matches
        # Fallback: some substrates produce units with no heading parent at all on a page
        # (structural_path=[]). If the benchmark provides a heading but we can't match it,
        # prefer returning the unheaded units on that page rather than returning nothing.
        return [
            unit_id
            for unit_id, unit in merged_by_id.items()
            if int(unit.get("page", -1)) == target_page
            and not _normalize_structural_path_parts(unit.get("structural_path") or [])
        ]

    def add_chunk(new_id: str, old_id: str) -> None:
        if new_id in seen_new:
            return
        seen_new.add(new_id)
        unit = merged_by_id.get(new_id)
        if unit is not None:
            location: Dict[str, Any] = {
                "page": unit.get("page"),
                "structural_path": unit.get("structural_path") or [],
            }
            source_ids = unit.get("source_unit_ids") or []
            if source_ids:
                location["source_unit_ids"] = source_ids
            new_gold_locations[new_id] = location
        if old_id in old_rationale and new_id not in new_rationale:
            new_rationale[new_id] = old_rationale[old_id]

    for old_id in required:
        for new_id in resolve_one(old_id):
            add_chunk(new_id, old_id)
            new_required.append(new_id)
    new_required = list(dict.fromkeys(new_required))

    for old_id in supporting:
        for new_id in resolve_one(old_id):
            add_chunk(new_id, old_id)
            new_supporting.append(new_id)
    new_supporting = list(dict.fromkeys(new_supporting))

    new_gold = new_required + [unit_id for unit_id in new_supporting if unit_id not in set(new_required)]
    return new_gold, new_required, new_supporting, new_gold_locations, new_rationale


def resolve_gold_locations_to_current_corpus(
    queries: List[Dict[str, Any]],
    folded_corpus: List[Dict[str, Any]],
    merged_corpus: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Resolve gold_locations to active merged chunk IDs for queries that provide them.
    Returns (resolved_queries, summary_counts).
    """
    merged_by_id = {u.get("id", ""): u for u in merged_corpus if u.get("id")}
    original_to_merged = build_original_to_merged(folded_corpus, merged_corpus)

    summary = {
        "queries_total": len(queries),
        "queries_with_gold_locations": 0,
        "queries_resolved_nonempty": 0,
        "queries_resolved_empty": 0,
        "queries_legacy_only": 0,
    }

    resolved_queries: List[Dict[str, Any]] = []
    for query in queries:
        query_copy = dict(query)
        gold_locations = query_copy.get("gold_locations") or {}
        if not gold_locations:
            summary["queries_legacy_only"] += 1
            resolved_queries.append(query_copy)
            continue

        summary["queries_with_gold_locations"] += 1
        gold_ids, required, supporting, new_locations, new_rationale = resolve_gold_ids_for_query(
            query_copy,
            original_to_merged,
            merged_by_id,
        )
        query_copy["gold_unit_ids"] = gold_ids
        query_copy["required_gold"] = required
        query_copy["supporting_gold"] = supporting
        # When resolution produced chunks, use new_locations; else keep original so canonical def is preserved
        if gold_ids:
            query_copy["gold_locations"] = new_locations
        query_copy["required_gold_rationale"] = new_rationale
        if gold_ids:
            summary["queries_resolved_nonempty"] += 1
        else:
            summary["queries_resolved_empty"] += 1
        resolved_queries.append(query_copy)

    return resolved_queries, summary


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
        q = _normalize_gold_fields(dict(q))
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
        q = _normalize_gold_fields(dict(q))
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
    """Ensure expected_answer_summary exists; use 'answer' if present.
    Ensure tier exists for R8 taxonomy; default T1 if absent."""
    if "expected_answer_summary" not in q or q["expected_answer_summary"] is None:
        q["expected_answer_summary"] = q.get("answer") or ""
    if "tier" not in q or q["tier"] is None or str(q["tier"]).strip() == "":
        q["tier"] = "T1"
    q = _normalize_gold_fields(q)
    return q


def flatten_query_batches(batch_paths: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Load one or more query batch JSON files and flatten to a single list of queries.
    Each batch file can have format { "batches": [ { "batch_id", "suite", "queries": [...] } ] }
    or legacy { "queries": [...] }.
    Returns (flat list of queries with batch_id and suite attached, list of suite names in order).
    """
    flat = []
    suites_seen = []
    for path in batch_paths:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Query batch not found: {p}")
        source_path = str(p.resolve())
        data = json.loads(p.read_text(encoding="utf-8"))
        if "batches" in data:
            for batch in data["batches"]:
                batch_id = batch.get("batch_id", "")
                suite = batch.get("suite", "default")
                for q in batch.get("queries", []):
                    q = _normalize_query(dict(q))
                    q["_batch_id"] = batch_id
                    q["_suite"] = suite
                    q["_tier"] = q.get("tier", "T1")
                    q["_source_path"] = source_path
                    flat.append(q)
                if suite not in suites_seen:
                    suites_seen.append(suite)
        elif "queries" in data:
            for q in data["queries"]:
                q = _normalize_query(dict(q))
                q["_batch_id"] = data.get("metadata", {}).get("batch_id", "")
                q["_suite"] = "default"
                q["_tier"] = q.get("tier", "T1")
                q["_source_path"] = source_path
                flat.append(q)
            if "default" not in suites_seen:
                suites_seen.append("default")
        elif isinstance(data, list):
            for q in data:
                q = _normalize_query(dict(q))
                q["_batch_id"] = ""
                q["_suite"] = "default"
                q["_tier"] = q.get("tier", "T1")
                q["_source_path"] = source_path
                flat.append(q)
            if "default" not in suites_seen:
                suites_seen.append("default")
        else:
            raise ValueError(f"Unknown query batch format: no 'batches', 'queries', or root array in {path}")
    return flat, suites_seen


INTERNAL_QUERY_KEYS = frozenset({"_source_path", "_batch_id", "_suite", "_tier"})


def apply_gold_recommendations_to_queries(
    flat_queries: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Apply reviewed gold recommendations onto flattened queries.

    Recommendations are expected to contain `query_id`, `proposed_required_gold`,
    `proposed_supporting_gold`, `required_gold_rationale`, `gold_locations`, and
    `applyable`.
    """
    rec_by_qid = {
        str(rec.get("query_id") or ""): rec
        for rec in recommendations
        if str(rec.get("query_id") or "").strip()
    }
    applied = 0
    skipped = 0
    updated_queries: List[Dict[str, Any]] = []
    for query in flat_queries:
        qid = str(query.get("id") or "")
        rec = rec_by_qid.get(qid)
        if not rec or not rec.get("applyable"):
            updated_queries.append(_normalize_query(dict(query)))
            if rec is not None:
                skipped += 1
            continue
        required = [str(x).strip() for x in (rec.get("proposed_required_gold") or []) if str(x).strip()]
        supporting = [
            str(x).strip()
            for x in (rec.get("proposed_supporting_gold") or [])
            if str(x).strip() and str(x).strip() not in set(required)
        ]
        updated = dict(query)
        updated["required_gold"] = required
        updated["supporting_gold"] = supporting
        updated["gold_unit_ids"] = list(dict.fromkeys(required + supporting))
        updated["gold_locations"] = dict(rec.get("gold_locations") or {})
        updated["required_gold_rationale"] = dict(rec.get("required_gold_rationale") or {})
        updated_queries.append(_normalize_query(updated))
        applied += 1
    return updated_queries, {
        "queries_total": len(flat_queries),
        "queries_with_recommendations": len(rec_by_qid),
        "queries_applied": applied,
        "queries_skipped": skipped,
    }


def _strip_internal_query_keys(q: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of the query with internal keys removed for persistence. Keeps _gold_note etc."""
    out = {k: v for k, v in q.items() if k not in INTERNAL_QUERY_KEYS}
    return out


def persist_resolved_gold_to_batch_files(
    batch_paths: List[str],
    flat_queries: List[Dict[str, Any]],
    cwd: Path,
) -> int:
    """
    Write resolved gold (gold_unit_ids, required_gold, supporting_gold, gold_locations,
    required_gold_rationale) back to each query batch file. Preserves file structure
    (root list, {"queries": [...]}, or {"batches": [...]}). Returns number of files updated.
    """
    updated = 0
    for path in batch_paths:
        resolved_path = (cwd / path).resolve()
        if not resolved_path.exists():
            continue
        from_this_file = [q for q in flat_queries if q.get("_source_path") == str(resolved_path)]
        if not from_this_file:
            continue
        data = json.loads(resolved_path.read_text(encoding="utf-8"))
        stripped = [_strip_internal_query_keys(q) for q in from_this_file]
        if isinstance(data, list):
            resolved_path.write_text(json.dumps(stripped, indent=2), encoding="utf-8")
            updated += 1
        elif "queries" in data:
            out = {**data, "queries": stripped}
            resolved_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
            updated += 1
        elif "batches" in data:
            batch_id_to_queries: Dict[str, List[Dict[str, Any]]] = {}
            for q in from_this_file:
                bid = q.get("_batch_id", "")
                if bid not in batch_id_to_queries:
                    batch_id_to_queries[bid] = []
                batch_id_to_queries[bid].append(_strip_internal_query_keys(q))
            new_batches = []
            for batch in data["batches"]:
                bid = batch.get("batch_id", "")
                new_batches.append({**batch, "queries": batch_id_to_queries.get(bid, [])})
            out = {**data, "batches": new_batches}
            resolved_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
            updated += 1
    return updated
