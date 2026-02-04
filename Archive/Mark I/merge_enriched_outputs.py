"""Merge enriched chunks, graphs, and queries for a run."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from cds import build_cds_for_run, summarize_cds_for_graph

EDGE_RELATIONS = {
    "references_named_section",
    "references_table",
    "references_figure",
    "references_chapter",
    "mentions_section",
    "in_section",
    "defines_term",
    "mentions_term",
}


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _collect_files(directory: Path, suffix: str) -> List[Path]:
    return sorted(
        path
        for path in directory.glob(f"*{suffix}")
        if not path.name.startswith("merged.")
    )


def _iter_edge_candidate_files(edge_candidates_dir: Path) -> List[Path]:
    return sorted(edge_candidates_dir.rglob("*.edge_candidates.json"))


def _load_edge_candidates(edge_candidates_dir: Path) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for path in _iter_edge_candidate_files(edge_candidates_dir):
        payload = _load_json(path)
        doc_id = payload.get("document") or path.stem.replace(".enriched.edge_candidates", "")
        for candidate in payload.get("candidates", []):
            relation = candidate.get("relation")
            if relation not in EDGE_RELATIONS:
                continue
            if candidate.get("is_ambiguous"):
                continue
            resolution_count = int(candidate.get("resolution_count", 0))
            if resolution_count != 1:
                continue
            source = candidate.get("from")
            if not source:
                continue
            resolved_targets = candidate.get("resolved_targets", [])
            for target in resolved_targets:
                if not target:
                    continue
                candidates.append(
                    {
                        "source": _prefix_id(doc_id, source) if "::" not in source else source,
                        "target": _prefix_id(doc_id, target) if "::" not in target else target,
                        "relation": relation,
                        "resolution_count": resolution_count,
                        "cue": candidate.get("cue"),
                        "parsed_target": candidate.get("parsed_target"),
                        "edge_source": "deterministic_candidate",
                    }
                )
    return candidates


def _prefix_id(doc_id: str, raw_id: str) -> str:
    prefix = f"{doc_id}::"
    return raw_id if raw_id.startswith(prefix) else f"{prefix}{raw_id}"


def _is_canonical_id(raw_id: Optional[str]) -> bool:
    return isinstance(raw_id, str) and raw_id.startswith("canon:")


def _resolve_node_id(doc_id: str, raw_id: str, canonical_id: Optional[str]) -> str:
    if _is_canonical_id(raw_id):
        return raw_id
    if _is_canonical_id(canonical_id):
        return canonical_id
    return _prefix_id(doc_id, raw_id)


def _merge_list(target: Dict[str, Any], key: str, values: List[Any]) -> None:
    if not values:
        return
    existing = target.get(key) or []
    merged = list({*existing, *values})
    target[key] = merged


def _merge_chunks(enriched_files: Iterable[Path]) -> Tuple[List[Dict[str, Any]], List[str]]:
    merged_chunks: List[Dict[str, Any]] = []
    doc_ids: List[str] = []

    for path in enriched_files:
        payload = _load_json(path)
        doc_id = payload.get("document") or path.stem.replace(".enriched", "")
        doc_ids.append(doc_id)
        for chunk in payload.get("chunks", []):
            chunk_id = chunk.get("id")
            if not chunk_id:
                continue
            merged_chunks.append(
                {
                    **chunk,
                    "id": _prefix_id(doc_id, chunk_id),
                    "document_id": doc_id,
                }
            )

    return merged_chunks, doc_ids


def _merge_graphs(
    graph_files: Iterable[Path],
    doc_ids: Iterable[str],
    candidate_edges: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    seen_edges = set()

    for path in graph_files:
        payload = _load_json(path)
        doc_id = payload.get("document") or path.stem.replace(".graph", "")
        local_id_map: Dict[str, str] = {}
        for node in payload.get("nodes", []):
            raw_id = node.get("id")
            if not raw_id:
                continue
            canonical_id = node.get("canonical_id")
            node_id = _resolve_node_id(doc_id, raw_id, canonical_id)
            local_id_map[raw_id] = node_id
            existing = nodes.get(node_id)
            if existing:
                _merge_list(existing, "aliases", node.get("aliases") or [])
                _merge_list(existing, "source_documents", node.get("source_documents") or [doc_id])
                _merge_list(existing, "source_chunk_ids", node.get("source_chunk_ids") or [])
                _merge_list(existing, "source_pages", node.get("source_pages") or [])
                existing.setdefault("ruleset_id", node.get("ruleset_id"))
                existing.setdefault("canonical_id", canonical_id or node_id)
            else:
                node_payload = {**node, "id": node_id}
                if _is_canonical_id(node_id):
                    node_payload.setdefault("source_documents", [])
                    if doc_id not in node_payload["source_documents"]:
                        node_payload["source_documents"].append(doc_id)
                else:
                    node_payload["document_id"] = doc_id
                nodes[node_id] = node_payload
        for edge in payload.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            if not source or not target:
                continue
            source_id = local_id_map.get(source) or _resolve_node_id(doc_id, source, edge.get("source_canonical_id"))
            target_id = local_id_map.get(target) or _resolve_node_id(doc_id, target, edge.get("target_canonical_id"))
            relation = edge.get("relation") or edge.get("type") or "related"
            key = (source_id, target_id, relation)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edge_payload = {**edge, "source": source_id, "target": target_id, "relation": relation}
            edges.append(edge_payload)

    root_id = "merged::root"
    nodes[root_id] = {"id": root_id, "type": "collection", "name": "merged"}
    for doc_id in doc_ids:
        doc_node_id = _prefix_id(doc_id, doc_id)
        if doc_node_id not in nodes:
            nodes[doc_node_id] = {"id": doc_node_id, "type": "document", "name": doc_id}
        key = (root_id, doc_node_id, "contains")
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({"source": root_id, "target": doc_node_id, "relation": "contains"})

    for edge in candidate_edges or []:
        source_id = edge.get("source")
        target_id = edge.get("target")
        relation = edge.get("relation")
        if not source_id or not target_id or not relation:
            continue
        if _is_canonical_id(source_id) and source_id not in nodes:
            nodes[source_id] = {
                "id": source_id,
                "type": "canonical",
                "name": source_id,
            }
        if _is_canonical_id(target_id) and target_id not in nodes:
            parsed_target = edge.get("parsed_target") or {}
            label = parsed_target.get("raw") or parsed_target.get("label") or target_id
            node_type = "term" if target_id.startswith("canon:term:") else "canonical"
            nodes[target_id] = {
                "id": target_id,
                "type": node_type,
                "name": label,
            }
        key = (source_id, target_id, relation)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append({**edge, "source": source_id, "target": target_id, "relation": relation})

    return {"nodes": list(nodes.values()), "edges": edges}


def _merge_queries(query_files: Iterable[Path]) -> Dict[str, Any]:
    merged_queries: List[Dict[str, Any]] = []
    for path in query_files:
        payload = _load_json(path)
        doc_id = payload.get("document") or path.stem.replace(".evaluation_queries", "")
        for query in payload.get("queries", []):
            query_id = query.get("id", "")
            merged_queries.append(
                {
                    **query,
                    "id": _prefix_id(doc_id, query_id) if query_id else query_id,
                    "expected_chunk_ids": [
                        _prefix_id(doc_id, chunk_id)
                        for chunk_id in query.get("expected_chunk_ids", [])
                    ],
                    "document_id": doc_id,
                }
            )
    return {"document": "merged", "queries": merged_queries}


def merge_outputs(
    enriched_dir: Path,
    output_prefix: str = "merged",
    edge_candidates_dir: Optional[Path] = None,
) -> Dict[str, Path]:
    enriched_files = _collect_files(enriched_dir, ".enriched.json")
    graph_files = _collect_files(enriched_dir, ".graph.json")
    query_files = _collect_files(enriched_dir, ".evaluation_queries.json")

    if not enriched_files:
        raise FileNotFoundError(f"No enriched files found in {enriched_dir}")
    if not graph_files:
        raise FileNotFoundError(f"No graph files found in {enriched_dir}")

    merged_chunks, doc_ids = _merge_chunks(enriched_files)
    candidate_edges = _load_edge_candidates(edge_candidates_dir) if edge_candidates_dir else None
    merged_graph = _merge_graphs(graph_files, doc_ids, candidate_edges=candidate_edges)
    merged_queries = _merge_queries(query_files) if query_files else None

    cds_payload = build_cds_for_run(merged_chunks)
    cds_summary = summarize_cds_for_graph(cds_payload)

    outputs = {}
    merged_enriched_path = enriched_dir / f"{output_prefix}.enriched.json"
    _write_json(merged_enriched_path, {"document": "merged", "chunks": merged_chunks})
    outputs["enriched"] = merged_enriched_path

    cds_path = enriched_dir / f"{output_prefix}.cds.json"
    _write_json(cds_path, cds_payload)
    outputs["cds"] = cds_path

    merged_graph["cds"] = {
        "path": str(cds_path),
        "summary": cds_summary,
    }

    merged_graph_path = enriched_dir / f"{output_prefix}.graph.json"
    _write_json(merged_graph_path, merged_graph)
    outputs["graph"] = merged_graph_path

    if merged_queries:
        merged_queries_path = enriched_dir / f"{output_prefix}.evaluation_queries.json"
        _write_json(merged_queries_path, merged_queries)
        outputs["queries"] = merged_queries_path

    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge enriched outputs for a run")
    parser.add_argument("--enriched-dir", required=True, help="Path to run enriched directory")
    parser.add_argument(
        "--output-prefix",
        default="merged",
        help="Prefix for merged outputs (default: merged)",
    )
    parser.add_argument(
        "--edge-eval",
        action="store_true",
        help="Run edge-restricted retrieval evaluation after merge",
    )
    parser.add_argument(
        "--edge-candidates-dir",
        default=None,
        help="Directory containing .edge_candidates.json files",
    )
    parser.add_argument(
        "--edge-eval-output",
        default=None,
        help="Optional path to write edge eval JSON",
    )
    parser.add_argument(
        "--edge-seed-max",
        type=int,
        default=500,
        help="Max edge-seeded queries to evaluate",
    )
    args = parser.parse_args()

    edge_candidates_dir = Path(args.edge_candidates_dir) if args.edge_candidates_dir else None
    outputs = merge_outputs(
        Path(args.enriched_dir),
        args.output_prefix,
        edge_candidates_dir=edge_candidates_dir,
    )
    print("✅ Merged outputs:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")

    if args.edge_eval:
        if not args.edge_candidates_dir:
            raise ValueError("--edge-candidates-dir is required when --edge-eval is set")
        script_path = Path(__file__).resolve().parent / "scripts" / "edge_restricted_retrieval_eval.py"
        spec = importlib.util.spec_from_file_location("edge_eval", script_path)
        if not spec or not spec.loader:
            raise ImportError(f"Unable to load edge eval script from {script_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        output_path = (
            Path(args.edge_eval_output)
            if args.edge_eval_output
            else Path(args.enriched_dir) / f"{args.output_prefix}.edge_eval.json"
        )
        payload = module.run_eval(
            enriched_dir=Path(args.enriched_dir),
            output_prefix=args.output_prefix,
            edge_candidates_dir=Path(args.edge_candidates_dir),
            output_path=output_path,
            edge_seed_max=args.edge_seed_max,
        )
        print(f"✅ Edge eval complete: {output_path}")


if __name__ == "__main__":
    main()
