"""Evaluate edge-restricted retrieval coverage from enriched outputs."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


EDGE_RELATIONS_STRICT = {
    "references_named_section",
    "references_table",
    "references_figure",
    "references_page",
    "in_section",
    "defines_term",
    "mentions_term",
}
EDGE_RELATIONS_BOUNDARY = {"references_chapter"}
EDGE_RELATIONS_HINT = {"mentions_section"}
TRAVERSAL_POLICY = {
    "references_named_section": "traversal",
    "references_table": "traversal",
    "references_figure": "traversal",
    "references_page": "traversal",
    "references_chapter": "boundary",
    "mentions_section": "hint",
    "in_section": "traversal",
    "defines_term": "traversal",
    "mentions_term": "traversal",
}


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _prefix_id(doc_id: str, raw_id: str) -> str:
    if "::" in raw_id:
        return raw_id
    prefix = f"{doc_id}::"
    return raw_id if raw_id.startswith(prefix) else f"{prefix}{raw_id}"


def _split_prefixed_id(raw_id: str) -> Tuple[Optional[str], str]:
    if "::" not in raw_id:
        return None, raw_id
    doc_id, local_id = raw_id.split("::", 1)
    return doc_id, local_id


def _normalize_title(title: str) -> str:
    cleaned = title.replace("–", "-").replace("—", "-")
    cleaned = re.sub(r"[`*_]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned.strip())
    cleaned = cleaned.strip(" .,:;()[]{}")
    return cleaned.lower()


def _extract_chapter_label(title: str) -> Optional[str]:
    if not title:
        return None
    match = re.search(r"\bChapter\s+(\d+|[IVXLC]+)\b", title, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower()


def _load_merged_outputs(enriched_dir: Path, output_prefix: str) -> Dict[str, Path]:
    enriched_path = enriched_dir / f"{output_prefix}.enriched.json"
    graph_path = enriched_dir / f"{output_prefix}.graph.json"
    queries_path = enriched_dir / f"{output_prefix}.evaluation_queries.json"
    if not enriched_path.exists():
        raise FileNotFoundError(f"Missing merged enriched output: {enriched_path}")
    if not graph_path.exists():
        raise FileNotFoundError(f"Missing merged graph output: {graph_path}")
    if not queries_path.exists():
        raise FileNotFoundError(f"Missing merged queries output: {queries_path}")
    return {
        "enriched": enriched_path,
        "graph": graph_path,
        "queries": queries_path,
    }


def _iter_edge_candidate_files(edge_candidates_dir: Path) -> Iterable[Path]:
    return sorted(edge_candidates_dir.rglob("*.edge_candidates.json"))


def _load_edge_candidates(edge_candidates_dir: Path) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for path in _iter_edge_candidate_files(edge_candidates_dir):
        payload = _load_json(path)
        doc_id = payload.get("document") or path.stem.replace(".enriched.edge_candidates", "")
        for candidate in payload.get("candidates", []):
            source = candidate.get("from")
            if not source:
                continue
            prefixed = _prefix_id(doc_id, source)
            resolved_targets = [
                _prefix_id(doc_id, target) if "::" not in target else target
                for target in candidate.get("resolved_targets", [])
            ]
            candidates.append(
                {
                    **candidate,
                    "from": prefixed,
                    "source_document": doc_id,
                    "resolved_targets": resolved_targets,
                }
            )
    return candidates


def _build_chunk_index(enriched_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    chunks = {}
    for chunk in enriched_payload.get("chunks", []):
        chunk_id = chunk.get("id")
        if not chunk_id:
            continue
        chunks[chunk_id] = chunk
    return chunks


def _build_doc_chunk_lists(enriched_payload: Dict[str, Any]) -> Dict[str, List[str]]:
    doc_chunks: Dict[str, List[str]] = defaultdict(list)
    for chunk in enriched_payload.get("chunks", []):
        chunk_id = chunk.get("id")
        doc_id = chunk.get("document_id")
        if not chunk_id or not doc_id:
            continue
        doc_chunks[doc_id].append(chunk_id)
    return doc_chunks


def _build_section_scopes(chunks_by_doc: Dict[str, List[str]], chunk_index: Dict[str, Dict[str, Any]]) -> Dict[str, Set[str]]:
    scope_map: Dict[str, Set[str]] = defaultdict(set)
    for doc_id, chunk_ids in chunks_by_doc.items():
        for chunk_id in chunk_ids:
            chunk = chunk_index.get(chunk_id, {})
            section_path = chunk.get("section_path") or []
            if not section_path:
                continue
            for idx in range(1, len(section_path) + 1):
                prefix = " > ".join(section_path[:idx])
                section_id = f"{doc_id}::section::{prefix}"
                scope_map[section_id].add(chunk_id)
    return scope_map


def _build_chapter_scopes(chunks_by_doc: Dict[str, List[str]], chunk_index: Dict[str, Dict[str, Any]]) -> Dict[str, Set[str]]:
    scope_map: Dict[str, Set[str]] = defaultdict(set)
    for doc_id, chunk_ids in chunks_by_doc.items():
        chapter_start_indices: List[int] = []
        chapter_ids: List[str] = []
        for idx, chunk_id in enumerate(chunk_ids):
            chunk = chunk_index.get(chunk_id, {})
            text = chunk.get("text", "")
            block_type = chunk.get("block_type", "")
            if block_type not in {"SectionHeader", "Title"}:
                continue
            chapter_label = _extract_chapter_label(text)
            if chapter_label:
                chapter_start_indices.append(idx)
                chapter_ids.append(f"{doc_id}::heading::{chunk_id.split('::', 1)[-1]}")
        if not chapter_start_indices:
            continue
        for i, start_idx in enumerate(chapter_start_indices):
            end_idx = chapter_start_indices[i + 1] if i + 1 < len(chapter_start_indices) else len(chunk_ids)
            chapter_id = chapter_ids[i]
            scope_map[chapter_id].update(chunk_ids[start_idx:end_idx])
    return scope_map


def _build_heading_scopes(
    chunks_by_doc: Dict[str, List[str]],
    chunk_index: Dict[str, Dict[str, Any]],
    section_scopes: Dict[str, Set[str]],
    chapter_scopes: Dict[str, Set[str]],
) -> Dict[str, Set[str]]:
    scope_map: Dict[str, Set[str]] = defaultdict(set)
    for doc_id, chunk_ids in chunks_by_doc.items():
        for chunk_id in chunk_ids:
            chunk = chunk_index.get(chunk_id, {})
            block_type = chunk.get("block_type", "")
            if block_type not in {"SectionHeader", "Title"}:
                continue
            heading_id = f"{doc_id}::heading::{chunk_id.split('::', 1)[-1]}"
            section_path = chunk.get("section_path") or []
            if section_path:
                section_key = " > ".join(section_path)
                section_id = f"{doc_id}::section::{section_key}"
                scope_map[heading_id].update(section_scopes.get(section_id, set()))
            elif heading_id in chapter_scopes:
                scope_map[heading_id].update(chapter_scopes[heading_id])
            else:
                scope_map[heading_id].add(chunk_id)
    return scope_map


def _build_target_scopes(
    enriched_payload: Dict[str, Any],
) -> Tuple[Dict[str, Set[str]], Dict[str, int]]:
    chunk_index = _build_chunk_index(enriched_payload)
    chunks_by_doc = _build_doc_chunk_lists(enriched_payload)
    section_scopes = _build_section_scopes(chunks_by_doc, chunk_index)
    chapter_scopes = _build_chapter_scopes(chunks_by_doc, chunk_index)
    heading_scopes = _build_heading_scopes(chunks_by_doc, chunk_index, section_scopes, chapter_scopes)

    target_scopes: Dict[str, Set[str]] = defaultdict(set)
    for section_id, scope in section_scopes.items():
        target_scopes[section_id].update(scope)
    for heading_id, scope in heading_scopes.items():
        target_scopes[heading_id].update(scope)
    for chunk_id, chunk in chunk_index.items():
        block_type = chunk.get("block_type", "")
        if block_type not in {"SectionHeader", "Title"}:
            continue
        doc_id = chunk.get("document_id")
        if not doc_id:
            continue
        heading_id = f"{doc_id}::heading::{chunk_id.split('::', 1)[-1]}"
        scope = heading_scopes.get(heading_id)
        if scope:
            target_scopes[chunk_id].update(scope)

    chunk_counts = {doc_id: len(chunk_ids) for doc_id, chunk_ids in chunks_by_doc.items()}
    return target_scopes, chunk_counts


def _build_edge_index(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    edges_by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        source = candidate.get("from")
        if not source:
            continue
        edges_by_source[source].append(candidate)
    return edges_by_source


def _compute_dep(candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    counts: Dict[str, Counter] = defaultdict(Counter)
    for candidate in candidates:
        relation = candidate.get("relation", "unknown")
        resolution_count = int(candidate.get("resolution_count", 0))
        if resolution_count == 1:
            counts[relation]["unique"] += 1
        elif resolution_count > 1:
            counts[relation]["multi"] += 1
        else:
            counts[relation]["zero"] += 1
    dep: Dict[str, Dict[str, float]] = {}
    for relation, counter in counts.items():
        unique = counter.get("unique", 0)
        multi = counter.get("multi", 0)
        denom = unique + multi
        dep[relation] = {
            "unique": unique,
            "multi": multi,
            "zero": counter.get("zero", 0),
            "dep": round(unique / denom, 4) if denom else 0.0,
        }
    return dep


def _count_traversal_classes(candidates: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = Counter()
    for candidate in candidates:
        relation = candidate.get("relation", "unknown")
        policy = TRAVERSAL_POLICY.get(relation, "unknown")
        counts[policy] += 1
    return dict(counts)


def _soft_signal_usefulness(
    edges_by_source: Dict[str, List[Dict[str, Any]]],
    chunk_index: Dict[str, Dict[str, Any]],
) -> Dict[str, float]:
    total = 0
    hits = 0
    for source_id, edges in edges_by_source.items():
        mentions = [edge for edge in edges if edge.get("relation") == "mentions_section"]
        if not mentions:
            continue
        chunk = chunk_index.get(source_id, {})
        section_path = chunk.get("section_path") or []
        normalized_segments = {_normalize_title(segment) for segment in section_path if segment}
        total += 1
        for mention in mentions:
            label = mention.get("parsed_target", {}).get("label", "")
            if label and _normalize_title(label) in normalized_segments:
                hits += 1
                break
    return {
        "queries_with_mentions": total,
        "mentions_hit_rate": round(hits / total, 4) if total else 0.0,
    }


def _evaluate_queries(
    queries_payload: Dict[str, Any],
    edges_by_source: Dict[str, List[Dict[str, Any]]],
    target_scopes: Dict[str, Set[str]],
    chunk_counts: Dict[str, int],
    chunk_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    queries = queries_payload.get("queries", [])
    total = 0
    with_edges = 0
    recall_hits = 0
    baseline_hits = 0
    candidate_sizes: List[int] = []

    for query in queries:
        expected_chunk_ids = query.get("expected_chunk_ids", [])
        if not expected_chunk_ids:
            continue
        expected_chunk_id = expected_chunk_ids[0]
        source_id = query.get("seed_source_id") or expected_chunk_id
        doc_id, _ = _split_prefixed_id(expected_chunk_id)
        total += 1
        edges = edges_by_source.get(source_id, [])
        if not edges:
            continue
        allowed_chunks: Set[str] = set()
        for edge in edges:
            relation = edge.get("relation")
            resolution_count = int(edge.get("resolution_count", 0))
            if relation in EDGE_RELATIONS_STRICT:
                if resolution_count != 1:
                    continue
            elif relation in EDGE_RELATIONS_BOUNDARY:
                if resolution_count < 1:
                    continue
            else:
                continue
            for target in edge.get("resolved_targets", []):
                scope = target_scopes.get(target)
                if scope:
                    allowed_chunks.update(scope)
                else:
                    allowed_chunks.add(target)
                if relation == "mentions_term":
                    allowed_chunks.add(source_id)

        if not allowed_chunks:
            continue

        with_edges += 1
        if expected_chunk_id in chunk_index:
            baseline_hits += 1
        if expected_chunk_id in allowed_chunks:
            recall_hits += 1
        if doc_id and doc_id in chunk_counts:
            candidate_sizes.append(len(allowed_chunks) / max(chunk_counts[doc_id], 1))

    recall_with_edges = round(recall_hits / with_edges, 4) if with_edges else 0.0
    baseline_recall = round(baseline_hits / with_edges, 4) if with_edges else 0.0
    tcg = round(recall_with_edges - baseline_recall, 4) if with_edges else None
    candidate_reduction = round(sum(candidate_sizes) / len(candidate_sizes), 4) if candidate_sizes else 0.0

    return {
        "queries_total": total,
        "queries_with_edges": with_edges,
        "edge_restricted_recall": recall_with_edges,
        "baseline_recall": baseline_recall,
        "edge_restricted_tcg": tcg,
        "avg_candidate_fraction": candidate_reduction,
    }


def _build_edge_seeded_queries(
    candidates: List[Dict[str, Any]],
    chunk_index: Dict[str, Dict[str, Any]],
    target_scopes: Dict[str, Set[str]],
    max_queries: int = 500,
) -> Dict[str, Any]:
    seeded_queries: List[Dict[str, Any]] = []
    seen_sources: Set[str] = set()
    for candidate in candidates:
        relation = candidate.get("relation")
        resolution_count = int(candidate.get("resolution_count", 0))
        if relation not in EDGE_RELATIONS_STRICT | EDGE_RELATIONS_BOUNDARY:
            continue
        if resolution_count < 1:
            continue
        source_id = candidate.get("from")
        if not source_id or source_id in seen_sources:
            continue
        resolved_targets = candidate.get("resolved_targets", [])
        if not resolved_targets:
            continue
        expected_chunk_id = None
        for target in resolved_targets:
            scope = target_scopes.get(target)
            if scope:
                expected_chunk_id = sorted(scope)[0]
            else:
                expected_chunk_id = target
            if expected_chunk_id:
                break
        if not expected_chunk_id:
            continue
        chunk = chunk_index.get(source_id, {})
        seeded_queries.append(
            {
                "id": f"edge-seeded::{source_id}",
                "seed_source_id": source_id,
                "query_text": (chunk.get("text") or "")[:160],
                "query_type": "edge_seeded",
                "content_kind": chunk.get("content_kind", ""),
                "expected_chunk_ids": [expected_chunk_id],
            }
        )
        seen_sources.add(source_id)
        if len(seeded_queries) >= max_queries:
            break
    return {"document": "edge_seeded", "queries": seeded_queries}


def _build_page_reference_queries(
    candidates: List[Dict[str, Any]],
    chunk_index: Dict[str, Dict[str, Any]],
    target_scopes: Dict[str, Set[str]],
    max_queries: int = 200,
    appendix_only: bool = True,
) -> Dict[str, Any]:
    seeded_queries: List[Dict[str, Any]] = []
    seen_sources: Set[str] = set()
    for candidate in candidates:
        relation = candidate.get("relation")
        resolution_count = int(candidate.get("resolution_count", 0))
        if relation != "references_page" or resolution_count != 1:
            continue
        source_id = candidate.get("from")
        if not source_id or source_id in seen_sources:
            continue
        if appendix_only:
            doc_id = candidate.get("source_document", "") or ""
            if "appendix" not in doc_id.lower():
                continue
        resolved_targets = candidate.get("resolved_targets", [])
        if not resolved_targets:
            continue
        expected_chunk_id = None
        for target in resolved_targets:
            scope = target_scopes.get(target)
            if scope:
                expected_chunk_id = sorted(scope)[0]
            else:
                expected_chunk_id = target
            if expected_chunk_id:
                break
        if not expected_chunk_id:
            continue
        chunk = chunk_index.get(source_id, {})
        query_text = candidate.get("cue") or (chunk.get("text") or "")[:160]
        seeded_queries.append(
            {
                "id": f"edge-page-ref::{source_id}",
                "seed_source_id": source_id,
                "query_text": query_text[:160],
                "query_type": "edge_page_ref",
                "content_kind": chunk.get("content_kind", ""),
                "expected_chunk_ids": [expected_chunk_id],
            }
        )
        seen_sources.add(source_id)
        if len(seeded_queries) >= max_queries:
            break
    return {
        "document": "edge_page_ref",
        "queries": seeded_queries,
        "appendix_only": appendix_only,
    }


def _evaluate_edge_seeded_queries(
    queries_payload: Dict[str, Any],
    edges_by_source: Dict[str, List[Dict[str, Any]]],
    target_scopes: Dict[str, Set[str]],
    chunk_counts: Dict[str, int],
    chunk_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    queries = queries_payload.get("queries", [])
    total = 0
    with_edges = 0
    recall_hits = 0
    baseline_hits = 0
    candidate_sizes: List[int] = []

    for query in queries:
        expected_chunk_ids = query.get("expected_chunk_ids", [])
        seed_source_id = query.get("seed_source_id")
        if not expected_chunk_ids or not seed_source_id:
            continue
        expected_chunk_id = expected_chunk_ids[0]
        doc_id, _ = _split_prefixed_id(expected_chunk_id)
        total += 1
        edges = edges_by_source.get(seed_source_id, [])
        if not edges:
            continue
        allowed_chunks: Set[str] = set()
        for edge in edges:
            relation = edge.get("relation")
            resolution_count = int(edge.get("resolution_count", 0))
            if relation in EDGE_RELATIONS_STRICT:
                if resolution_count != 1:
                    continue
            elif relation in EDGE_RELATIONS_BOUNDARY:
                if resolution_count < 1:
                    continue
            else:
                continue
            for target in edge.get("resolved_targets", []):
                scope = target_scopes.get(target)
                if scope:
                    allowed_chunks.update(scope)
                else:
                    allowed_chunks.add(target)
                if relation == "mentions_term":
                    allowed_chunks.add(seed_source_id)

        if not allowed_chunks:
            continue

        with_edges += 1
        if expected_chunk_id in chunk_index:
            baseline_hits += 1
        if expected_chunk_id in allowed_chunks:
            recall_hits += 1
        if doc_id and doc_id in chunk_counts:
            candidate_sizes.append(len(allowed_chunks) / max(chunk_counts[doc_id], 1))

    recall_with_edges = round(recall_hits / with_edges, 4) if with_edges else 0.0
    baseline_recall = round(baseline_hits / with_edges, 4) if with_edges else 0.0
    tcg = round(recall_with_edges - baseline_recall, 4) if with_edges else None
    candidate_reduction = round(sum(candidate_sizes) / len(candidate_sizes), 4) if candidate_sizes else 0.0

    return {
        "queries_total": total,
        "queries_with_edges": with_edges,
        "edge_restricted_recall": recall_with_edges,
        "baseline_recall": baseline_recall,
        "edge_restricted_tcg": tcg,
        "avg_candidate_fraction": candidate_reduction,
    }


def _merge_query_payloads(
    base_payload: Dict[str, Any],
    extra_payload: Dict[str, Any],
    max_extra: Optional[int] = None,
) -> Dict[str, Any]:
    base_queries = list(base_payload.get("queries", []))
    extra_queries = list(extra_payload.get("queries", []))
    if max_extra is not None:
        extra_queries = extra_queries[:max_extra]
    merged_queries = base_queries + extra_queries
    return {
        "document": base_payload.get("document", "merged"),
        "queries": merged_queries,
        "meta": {
            "base_queries": len(base_queries),
            "extra_queries": len(extra_queries),
            "total_queries": len(merged_queries),
        },
    }


def run_eval(
    enriched_dir: Path,
    output_prefix: str,
    edge_candidates_dir: Path,
    output_path: Optional[Path] = None,
    edge_seed_max: int = 500,
) -> Dict[str, Any]:
    merged = _load_merged_outputs(enriched_dir, output_prefix)
    enriched_payload = _load_json(merged["enriched"])
    queries_payload = _load_json(merged["queries"])

    candidates = _load_edge_candidates(edge_candidates_dir)
    edges_by_source = _build_edge_index(candidates)

    chunk_index = _build_chunk_index(enriched_payload)
    target_scopes, chunk_counts = _build_target_scopes(enriched_payload)
    term_scopes: Dict[str, Set[str]] = defaultdict(set)
    for candidate in candidates:
        if candidate.get("relation") != "defines_term":
            continue
        if int(candidate.get("resolution_count", 0)) != 1:
            continue
        source_id = candidate.get("from")
        if not source_id:
            continue
        for target in candidate.get("resolved_targets", []):
            if not target or not target.startswith("canon:term:"):
                continue
            term_scopes[target].add(source_id)
    for term_id, scope in term_scopes.items():
        target_scopes[term_id].update(scope)
    dep = _compute_dep(candidates)
    soft_signal = _soft_signal_usefulness(edges_by_source, chunk_index)
    edge_seeded_queries = _build_edge_seeded_queries(
        candidates,
        chunk_index,
        target_scopes,
        max_queries=edge_seed_max,
    )
    edge_seeded_eval = _evaluate_edge_seeded_queries(
        edge_seeded_queries,
        edges_by_source,
        target_scopes,
        chunk_counts,
        chunk_index,
    )
    page_ref_queries = _build_page_reference_queries(
        candidates,
        chunk_index,
        target_scopes,
        max_queries=min(edge_seed_max, 200),
        appendix_only=True,
    )
    merged_queries_payload = _merge_query_payloads(
        queries_payload,
        page_ref_queries,
    )
    eval_summary = _evaluate_queries(
        merged_queries_payload,
        edges_by_source,
        target_scopes,
        chunk_counts,
        chunk_index,
    )
    page_ref_eval = _evaluate_edge_seeded_queries(
        page_ref_queries,
        edges_by_source,
        target_scopes,
        chunk_counts,
        chunk_index,
    )

    payload = {
        "document": queries_payload.get("document"),
        "traversal_policy": TRAVERSAL_POLICY,
        "traversal_class_counts": _count_traversal_classes(candidates),
        "dep_by_relation": dep,
        "soft_signal_usefulness": soft_signal,
        "edge_restricted_eval": eval_summary,
        "edge_seeded_eval": edge_seeded_eval,
        "edge_page_ref_eval": page_ref_eval,
        "edge_page_ref_queries": {
            "total": len(page_ref_queries.get("queries", [])),
            "appendix_only": page_ref_queries.get("appendix_only", True),
        },
        "edge_restricted_eval_query_set": merged_queries_payload.get("meta", {}),
    }

    if output_path:
        _write_json(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate edge-restricted retrieval coverage from merged outputs."
    )
    parser.add_argument("--enriched-dir", required=True, help="Path to run enriched directory")
    parser.add_argument(
        "--output-prefix",
        default="merged",
        help="Prefix for merged outputs (default: merged)",
    )
    parser.add_argument(
        "--edge-candidates-dir",
        required=True,
        help="Directory containing .edge_candidates.json files",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path to write evaluation JSON",
    )
    parser.add_argument(
        "--edge-seed-max",
        type=int,
        default=500,
        help="Max edge-seeded queries to evaluate",
    )
    args = parser.parse_args()

    output_path = Path(args.output_path) if args.output_path else None
    payload = run_eval(
        enriched_dir=Path(args.enriched_dir),
        output_prefix=args.output_prefix,
        edge_candidates_dir=Path(args.edge_candidates_dir),
        output_path=output_path,
        edge_seed_max=args.edge_seed_max,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
