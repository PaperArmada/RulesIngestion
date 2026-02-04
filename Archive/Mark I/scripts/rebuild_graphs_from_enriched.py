from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from enrichment import EnrichedChunk, audit_entity_namespace, build_chunk_graph


def _load_config(path: Path) -> Optional[Any]:
    """Load ruleset config JSON and return an object with .deterministic_rules for vocabulary_match."""
    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    det = loaded.get("deterministic_rules") or {}
    # Normalize entity_type_overrides: support dict (type -> list of names) into list-of-{key, value}
    overrides = det.get("entity_type_overrides")
    if isinstance(overrides, dict):
        list_overrides = []
        for entity_type, names in overrides.items():
            for name in names if isinstance(names, list) else []:
                list_overrides.append({"key": name, "value": entity_type})
        det = {**det, "entity_type_overrides": list_overrides}
    class _Config:
        pass
    cfg = _Config()
    cfg.deterministic_rules = det
    return cfg


def _load_enriched(path: Path) -> Tuple[str, List[EnrichedChunk]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    doc_id = payload.get("document") or path.stem.replace(".enriched", "")
    valid_fields = set(EnrichedChunk.__dataclass_fields__)
    chunks: List[EnrichedChunk] = []
    for raw in payload.get("chunks", []):
        filtered = {k: v for k, v in raw.items() if k in valid_fields}
        try:
            chunks.append(EnrichedChunk(**filtered))
        except TypeError as exc:
            raise ValueError(f"Invalid chunk payload in {path}: {exc}") from exc
    return doc_id, chunks


def _write_graph(path: Path, graph_payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(graph_payload, handle, indent=2)


def rebuild_graphs(
    enriched_dir: Path,
    ruleset_id: str | None,
    resolved_config: Optional[Any] = None,
) -> List[Path]:
    enriched_files = sorted(enriched_dir.glob("*.enriched.json"))
    if not enriched_files:
        raise FileNotFoundError(f"No enriched outputs found in {enriched_dir}")
    written: List[Path] = []
    for enriched_path in enriched_files:
        doc_id, chunks = _load_enriched(enriched_path)
        graph = build_chunk_graph(
            doc_id, chunks, ruleset_id=ruleset_id, resolved_config=resolved_config
        )
        if ruleset_id is not None:
            audit_entity_namespace(graph.nodes, expected_ruleset_id=ruleset_id)
        graph_path = enriched_dir / f"{doc_id}.graph.json"
        _write_graph(graph_path, graph.to_dict())
        written.append(graph_path)
        print(f"✅ rebuilt: {graph_path}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild graph JSON files from existing enriched outputs."
    )
    parser.add_argument(
        "--enriched-dir",
        required=True,
        help="Path to enriched outputs directory (contains *.enriched.json)",
    )
    parser.add_argument(
        "--ruleset-id",
        default=None,
        help="Ruleset ID to embed in graph nodes (required for benchmarking; use --allow-infer to fall back to doc_id inference)",
    )
    parser.add_argument(
        "--allow-infer",
        action="store_true",
        help="Allow ruleset_id to be inferred from doc_id when --ruleset-id is not set (not recommended for benchmarking)",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to ruleset config JSON (enables vocabulary_match from entity_type_overrides)",
    )
    args = parser.parse_args()
    if not args.ruleset_id and not args.allow_infer:
        parser.error(
            "Entity ID namespace stabilization requires an explicit ruleset. "
            "Pass --ruleset-id RULESET (e.g. StarFinder2e) or --allow-infer to permit inference from doc_id."
        )
    enriched_dir = Path(args.enriched_dir).resolve()
    resolved_config = None
    if args.config:
        config_path = Path(args.config).resolve()
        if not config_path.is_file():
            parser.error(f"Config file not found: {config_path}")
        resolved_config = _load_config(config_path)
        print(f"Loaded config: {config_path}")
    if args.ruleset_id:
        print(f"Resolved ruleset_id: {args.ruleset_id}")
    rebuild_graphs(enriched_dir, ruleset_id=args.ruleset_id, resolved_config=resolved_config)


if __name__ == "__main__":
    main()
