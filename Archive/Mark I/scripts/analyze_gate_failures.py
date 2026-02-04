from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_gate_summary(path: Path) -> Dict[str, Any]:
    payload = _load_json(path)
    gates = payload.get("gates", {})
    candidate_path = _resolve_candidate_path(path)
    return {
        "document": payload.get("document"),
        "gates": gates,
        "gate_failures": gates.get("gate_failures", []),
        "path": str(path),
        "candidate_path": str(candidate_path) if candidate_path else None,
    }


def _load_candidates(path: Path) -> Dict[str, Any]:
    payload = _load_json(path)
    return {
        "document": payload.get("document"),
        "summary": payload.get("summary", {}),
        "candidates": payload.get("candidates", []),
        "path": str(path),
    }


def _iter_files(root: Path, suffix: str) -> List[Path]:
    if root.is_file():
        return [root] if root.name.endswith(suffix) else []
    return sorted(root.rglob(f"*{suffix}"))


def _resolve_candidate_path(gate_path: Path) -> Path | None:
    name = gate_path.name
    if not name.endswith(".edge_gates.json"):
        return None
    candidate_name = name[: -len(".edge_gates.json")] + ".edge_candidates.json"
    candidate_path = gate_path.with_name(candidate_name)
    return candidate_path if candidate_path.exists() else candidate_path


def _summarize_candidates(
    candidates: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
    relation_counts: Counter = Counter()
    content_kinds: Counter = Counter()
    resolution_buckets: Counter = Counter()
    for candidate in candidates:
        relation_counts[candidate.get("relation", "unknown")] += 1
        content_kinds[candidate.get("content_kind", "unknown")] += 1
        resolution_buckets[str(candidate.get("resolution_count", "unknown"))] += 1
    return dict(relation_counts), dict(content_kinds), dict(resolution_buckets)


def _summarize_pages(candidates: List[Dict[str, Any]]) -> Dict[int, int]:
    pages: Counter = Counter()
    for candidate in candidates:
        page = candidate.get("page")
        if isinstance(page, int):
            pages[page] += 1
    return dict(pages)


def _filter_candidates(
    candidates: List[Dict[str, Any]],
    relation: str | None,
    resolution_count: int | None,
    content_kind: str | None,
) -> List[Dict[str, Any]]:
    filtered = candidates
    if relation:
        filtered = [c for c in filtered if c.get("relation") == relation]
    if resolution_count is not None:
        filtered = [
            c for c in filtered if int(c.get("resolution_count", -1)) == resolution_count
        ]
    if content_kind:
        filtered = [c for c in filtered if c.get("content_kind") == content_kind]
    return filtered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze deterministic edge candidates that failed OCR/spelling gates."
    )
    parser.add_argument(
        "root",
        help="Enriched run directory or a single .edge_gates.json file",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write combined gate failure report JSON to this path",
    )
    parser.add_argument(
        "--relation",
        default=None,
        help="Filter candidates by relation (e.g., references_page)",
    )
    parser.add_argument(
        "--resolution-count",
        type=int,
        default=None,
        help="Filter candidates by resolution_count (e.g., 0 or 1)",
    )
    parser.add_argument(
        "--content-kind",
        default=None,
        help="Filter candidates by content_kind (e.g., narrative)",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=25,
        help="Max candidates to show per document",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    gate_paths = _iter_files(root, ".edge_gates.json")
    if not gate_paths:
        raise SystemExit(f"No gate summaries found under {root}")

    gate_summaries = [_load_gate_summary(path) for path in gate_paths]
    failed = [summary for summary in gate_summaries if summary.get("gate_failures")]
    if not failed:
        print("✅ No gate failures found.")
        return

    print(f"🧪 Gate failures: {len(failed)} documents")

    combined: Dict[str, Any] = {
        "run_root": str(root),
        "failed_documents": [],
    }
    for summary in failed:
        doc_id = summary.get("document") or "unknown"
        failures = summary.get("gate_failures") or []
        print(f"\n📄 {doc_id}")
        for failure in failures:
            print(f"  - {failure}")

        candidate_path_raw = summary.get("candidate_path")
        candidate_path = Path(candidate_path_raw) if candidate_path_raw else None
        if not candidate_path or not candidate_path.exists():
            print(f"  ⚠️  Missing candidates: {candidate_path}")
            continue

        candidate_payload = _load_candidates(candidate_path)
        candidates = candidate_payload.get("candidates", [])
        filtered = _filter_candidates(
            candidates,
            relation=args.relation,
            resolution_count=args.resolution_count,
            content_kind=args.content_kind,
        )

        relation_counts, content_kinds, resolution_buckets = _summarize_candidates(
            filtered
        )
        pages = _summarize_pages(filtered)

        print(f"  candidates: {len(filtered)} (filtered)")
        if relation_counts:
            print(f"  relation_counts: {relation_counts}")
        if content_kinds:
            print(f"  content_kinds: {content_kinds}")
        if resolution_buckets:
            print(f"  resolution_counts: {resolution_buckets}")
        if pages:
            top_pages = dict(sorted(pages.items(), key=lambda x: x[1], reverse=True)[:5])
            print(f"  top_pages: {top_pages}")

        combined["failed_documents"].append(
            {
                "document": doc_id,
                "gate_failures": failures,
                "gate_summary": summary.get("gates", {}),
                "candidate_path": str(candidate_path),
                "relation_counts": relation_counts,
                "content_kinds": content_kinds,
                "resolution_counts": resolution_buckets,
                "top_pages": dict(sorted(pages.items(), key=lambda x: x[1], reverse=True)),
                "candidates": filtered,
            }
        )

        for idx, candidate in enumerate(filtered[: args.max_candidates]):
            cue = candidate.get("cue") or ""
            cue_title = candidate.get("cue_title") or ""
            parsed_target = candidate.get("parsed_target", {})
            print(
                "  - "
                f"[{idx + 1}] {candidate.get('relation')} page={candidate.get('page')} "
                f"resolutions={candidate.get('resolution_count')} cue={cue!r} "
                f"target={parsed_target.get('label')}"
            )
            if cue_title:
                print(f"      cue_title={cue_title!r}")

    output_path = None
    if args.output:
        output_path = Path(args.output).resolve()
    elif root.is_dir():
        output_path = root / "gate_failures_combined.json"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(combined, handle, indent=2)
        print(f"\n💾 Wrote combined report: {output_path}")


if __name__ == "__main__":
    main()
