#!/usr/bin/env python3
"""Enrich existing benchmark files with GoldAnchor metadata.

Additive Phase 1: adds a top-level "anchors" dict and per-query
required_anchor_ids / supporting_anchor_ids without removing any
existing fields.  Fully backward-compatible.

Usage:
    uv run python scripts/enrich_benchmarks_with_anchors.py <benchmark.json> [--dry-run]

The script is idempotent: re-running on an already-enriched file
produces the same output (deterministic anchor IDs).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrieval_lab.anchor_schema import GoldAnchor, generate_anchor_id, quote_hash


def anchor_sidecar_path(benchmark_path: Path) -> Path:
    """Return the additive sidecar path used for root-array benchmark files."""
    return benchmark_path.with_suffix(".anchors.json")


def _extract_anchor_quote(text: str, max_chars: int = 200) -> str:
    """Extract a representative quote from the full text.

    Takes the first sentence or max_chars, whichever is shorter.
    """
    if not text:
        return ""
    # Try to find end of first sentence
    for end_char in [".", "!", "?"]:
        idx = text.find(end_char)
        if 0 < idx < max_chars:
            return text[: idx + 1].strip()
    return text[:max_chars].strip()


def _dedup_key(document_id: str, page: int, structural_path: list[str]) -> str:
    """Key for deduplicating anchors across queries that reference the same evidence region."""
    path_norm = " > ".join(
        s.strip().casefold() for s in structural_path if s.strip()
    )
    return f"{document_id}|{page}|{path_norm}"


def enrich_benchmark(data: Any) -> tuple[Any, dict[str, dict[str, Any]]]:
    """Add GoldAnchor metadata to a benchmark payload.

    Supports both:
    - object roots: {"metadata": ..., "queries": [...]}
    - legacy list roots: [{...}, {...}]

    Returns a tuple of:
    - enriched benchmark payload in its original root shape
    - anchors dict keyed by anchor_id
    """
    if isinstance(data, dict):
        metadata = data.get("metadata") or {}
        queries = data.get("queries") or []
        root_kind = "object"
    elif isinstance(data, list):
        metadata = {}
        queries = data
        root_kind = "list"
    else:
        raise TypeError("Benchmark JSON must be an object or a list of queries.")

    document_id = (
        metadata.get("document_id")
        or metadata.get("pdf_source", "")
        .replace(" ", "")
        .replace("'", "")
    )
    if not document_id:
        # Fall back to any query-level document hint if the benchmark has no metadata.
        first_query = queries[0] if queries else {}
        document_id = (
            str(first_query.get("document_id") or "").strip()
            or str(first_query.get("document") or "").strip()
        )

    # Registry: dedup_key → GoldAnchor (for sharing across queries)
    anchor_registry: dict[str, GoldAnchor] = {}
    # Map from (query_id, old_gold_id) → anchor_id
    gold_to_anchor: dict[str, str] = {}

    for query in queries:
        gold_locations = query.get("gold_locations") or {}
        gold_chunks_by_id = {
            c["id"]: c for c in (query.get("gold_chunks") or []) if c.get("id")
        }

        for gold_id, loc in gold_locations.items():
            page = int(loc.get("page", -1))
            structural_path = list(loc.get("structural_path") or [])
            source_unit_ids = list(loc.get("source_unit_ids") or [])

            chunk = gold_chunks_by_id.get(gold_id, {})
            full_text = chunk.get("text", "")
            anchor_quote = _extract_anchor_quote(full_text)
            unit_type = chunk.get("unit_type", "prose")

            if not anchor_quote and not structural_path:
                continue

            dk = _dedup_key(document_id, page, structural_path)

            if dk in anchor_registry:
                existing = anchor_registry[dk]
                # Check if this is truly the same evidence region via quote overlap
                from retrieval_lab.anchor_resolver import _jaccard_tokens
                overlap = _jaccard_tokens(existing.anchor_quote, anchor_quote)
                if overlap >= 0.3:
                    gold_to_anchor[gold_id] = existing.anchor_id
                    # Merge source_unit_ids
                    for sid in source_unit_ids:
                        if sid not in existing.cached_source_unit_ids:
                            existing.cached_source_unit_ids.append(sid)
                    if gold_id not in existing.cached_unit_ids:
                        existing.cached_unit_ids.append(gold_id)
                    continue

            aid = generate_anchor_id(document_id, page, structural_path, anchor_quote)
            anchor = GoldAnchor(
                anchor_id=aid,
                document_id=document_id,
                anchor_type=unit_type if unit_type in {"prose", "table", "list", "callout", "heading"} else "prose",
                page=page,
                structural_path=structural_path,
                anchor_quote=anchor_quote,
                quote_normalized_hash=quote_hash(anchor_quote),
                cached_unit_ids=[gold_id],
                cached_source_unit_ids=list(source_unit_ids),
            )
            anchor_registry[dk] = anchor
            gold_to_anchor[gold_id] = aid

    # Build top-level anchors dict
    anchors_dict: dict[str, dict[str, Any]] = {}
    for anchor in anchor_registry.values():
        anchors_dict[anchor.anchor_id] = anchor.to_dict()

    # Enrich queries with anchor references
    enriched_queries: list[dict[str, Any]] = []
    for query in queries:
        q = dict(query)
        required_gold = q.get("required_gold") or q.get("gold_unit_ids") or []
        supporting_gold = q.get("supporting_gold") or []

        required_anchor_ids: list[str] = []
        supporting_anchor_ids: list[str] = []

        for gid in required_gold:
            aid = gold_to_anchor.get(gid)
            if aid and aid not in required_anchor_ids:
                required_anchor_ids.append(aid)

        for gid in supporting_gold:
            aid = gold_to_anchor.get(gid)
            if aid and aid not in supporting_anchor_ids and aid not in required_anchor_ids:
                supporting_anchor_ids.append(aid)

        q["required_anchor_ids"] = required_anchor_ids
        q["supporting_anchor_ids"] = supporting_anchor_ids
        enriched_queries.append(q)

    if root_kind == "object":
        result = dict(data)
        result["anchors"] = anchors_dict
        result["queries"] = enriched_queries
        return result, anchors_dict

    return enriched_queries, anchors_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich benchmark with GoldAnchors")
    parser.add_argument("benchmark", type=Path, help="Path to benchmark JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--output", type=Path, help="Write to different file (default: overwrite input)")
    args = parser.parse_args()

    if not args.benchmark.exists():
        print(f"Error: {args.benchmark} not found", file=sys.stderr)
        sys.exit(1)

    data = json.loads(args.benchmark.read_text(encoding="utf-8"))
    enriched, anchors = enrich_benchmark(data)
    queries = enriched.get("queries", []) if isinstance(enriched, dict) else enriched
    queries_with_anchors = sum(1 for q in queries if q.get("required_anchor_ids"))

    print(f"Anchors created:     {len(anchors)}")
    print(f"Queries total:       {len(queries)}")
    print(f"Queries with anchors: {queries_with_anchors}")
    print(f"Shared anchors:      {len(anchors) - queries_with_anchors + len(set().union(*(set(q.get('required_anchor_ids', []) + q.get('supporting_anchor_ids', [])) for q in queries)))}")

    if args.dry_run:
        print("\n[DRY RUN] No files written.")
        for aid, a in anchors.items():
            print(f"  {aid}: p{a['page']} {a['structural_path']} → {a['anchor_quote'][:60]}...")
        if isinstance(data, list):
            print(f"[DRY RUN] Sidecar path: {anchor_sidecar_path(args.output or args.benchmark)}")
        return

    output_path = args.output or args.benchmark
    output_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8")
    if isinstance(data, list):
        sidecar_path = anchor_sidecar_path(output_path)
        sidecar_path.write_text(
            json.dumps({"anchors": anchors}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Written sidecar: {sidecar_path}")
    print(f"\nWritten to: {output_path}")


if __name__ == "__main__":
    main()
