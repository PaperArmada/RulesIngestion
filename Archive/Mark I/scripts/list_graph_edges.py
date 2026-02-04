"""List edge relation types present in graph JSON files."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def _iter_graph_paths(paths: List[str], root: Path) -> Iterable[Path]:
    if paths:
        for entry in paths:
            path = Path(entry)
            if path.is_dir():
                yield from path.rglob("*.graph.json")
            else:
                yield path
        return
    if root.exists():
        yield from root.rglob("*.graph.json")


def _bucket_for_path(path: Path) -> str:
    parts = set(path.parts)
    if "GMCore" in parts:
        return "GMCore"
    if "PlayerCore" in parts:
        return "PlayerCore"
    return "unknown"


def _edge_relation(edge: Dict[str, object]) -> str:
    for key in ("relation", "type", "edge_type"):
        value = edge.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "unknown"


def _load_edges(path: Path) -> List[Dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        return []
    edges = payload.get("edges", [])
    return edges if isinstance(edges, list) else []


def summarize_edges(paths: Iterable[Path]) -> Tuple[Dict[str, Counter], Counter, Counter]:
    bucket_counts: Dict[str, Counter] = defaultdict(Counter)
    bucket_graphs: Counter = Counter()
    bucket_edges: Counter = Counter()

    for path in paths:
        bucket = _bucket_for_path(path)
        bucket_graphs[bucket] += 1
        edges = _load_edges(path)
        bucket_edges[bucket] += len(edges)
        for edge in edges:
            if isinstance(edge, dict):
                bucket_counts[bucket][_edge_relation(edge)] += 1

    return bucket_counts, bucket_graphs, bucket_edges


def _print_bucket(name: str, counts: Counter, graphs: int, edges: int) -> None:
    print(f"\n{name}")
    print(f"  graphs: {graphs}")
    print(f"  edges: {edges}")
    for relation, count in counts.most_common():
        print(f"  - {relation}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="List edge relation types in graph JSON files.")
    parser.add_argument("paths", nargs="*", help="Graph files or directories to scan")
    parser.add_argument(
        "--root",
        default=None,
        help="Root directory to scan when no paths provided (default: Rules/StarFinder2e)",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    default_root = base_dir / "Rules" / "StarFinder2e"
    root = Path(args.root) if args.root else default_root

    paths = list(_iter_graph_paths(args.paths, root))
    if not paths:
        print("No graph files found.")
        return

    bucket_counts, bucket_graphs, bucket_edges = summarize_edges(paths)
    for bucket in sorted(bucket_counts.keys()):
        _print_bucket(bucket, bucket_counts[bucket], bucket_graphs[bucket], bucket_edges[bucket])

    all_relations = Counter()
    for counts in bucket_counts.values():
        all_relations.update(counts)
    print("\nAll relations")
    for relation, count in all_relations.most_common():
        print(f"  - {relation}: {count}")


if __name__ == "__main__":
    main()
