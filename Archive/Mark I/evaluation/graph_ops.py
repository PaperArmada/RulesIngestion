from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


def build_graph_adjacency(
    graph_payload: Optional[Dict[str, Any]], node_prefix: Optional[str] = None
) -> Dict[str, Set[str]]:
    if not graph_payload:
        return {}
    edges = graph_payload.get("edges") or []
    adjacency: Dict[str, Set[str]] = {}
    prefix = f"{node_prefix}::" if node_prefix else ""
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        source_id = f"{prefix}{source}"
        target_id = f"{prefix}{target}"
        adjacency.setdefault(source_id, set()).add(target_id)
        adjacency.setdefault(target_id, set()).add(source_id)
    return adjacency


def build_section_index(chunks: List[Dict[str, Any]]) -> Dict[Tuple[str, ...], List[str]]:
    index: Dict[Tuple[str, ...], List[str]] = {}
    for chunk in chunks:
        section_path = tuple(chunk.get("section_path") or [])
        if not section_path:
            continue
        index.setdefault(section_path, []).append(chunk["id"])
    return index


def expand_expected_ids(
    expected_ids: List[str],
    chunk_ids: Set[str],
    chunk_by_id: Dict[str, Dict[str, Any]],
    adjacency: Dict[str, Set[str]],
    section_index: Dict[Tuple[str, ...], List[str]],
    next_depth: int,
    include_section: bool,
    same_kind_only: bool,
    max_total: int,
) -> Tuple[List[str], Dict[str, List[str]]]:
    # NOTE: Expanded gold relaxes correctness by accepting section siblings + graph neighbors.
    # This is useful for diagnostics, but it can mask strict failures. Consider removing
    # expanded evaluation entirely, or tightening it so expansion only traverses
    # deterministic/traversable edges (compiler-style safety).
    expanded: List[str] = []
    seen: Set[str] = set()
    reasons: Dict[str, Set[str]] = {}

    def _add_candidate(candidate_id: str, reference_kind: Optional[str], reason: str) -> None:
        if candidate_id not in chunk_ids:
            return
        if same_kind_only and reference_kind:
            candidate_kind = chunk_by_id.get(candidate_id, {}).get("content_kind")
            if candidate_kind and candidate_kind != reference_kind:
                return
        reasons.setdefault(candidate_id, set()).add(reason)
        if candidate_id in seen:
            return
        seen.add(candidate_id)
        expanded.append(candidate_id)

    for chunk_id in expected_ids:
        if chunk_id not in chunk_ids:
            continue
        reference_kind = chunk_by_id.get(chunk_id, {}).get("content_kind")
        _add_candidate(chunk_id, reference_kind, "original")

        if include_section:
            section_path = tuple(chunk_by_id.get(chunk_id, {}).get("section_path") or [])
            for sibling_id in section_index.get(section_path, []):
                _add_candidate(sibling_id, reference_kind, "section")

        if next_depth > 0:
            frontier = {chunk_id}
            for depth in range(1, next_depth + 1):
                next_frontier: Set[str] = set()
                for node_id in frontier:
                    for neighbor in adjacency.get(node_id, set()):
                        _add_candidate(neighbor, reference_kind, f"graph_depth_{depth}")
                        if neighbor in seen:
                            continue
                        next_frontier.add(neighbor)
                frontier = next_frontier

        if len(expanded) >= max_total:
            break

    trimmed = expanded[:max_total]
    trimmed_reasons = {
        chunk_id: sorted(reasons.get(chunk_id, set()))
        for chunk_id in trimmed
    }
    return trimmed, trimmed_reasons
