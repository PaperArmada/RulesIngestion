#!/usr/bin/env python3
"""Refresh benchmark contract hashes after benchmark enrichment.

This script updates contract fields that are expected to change when a benchmark
definition file is edited in place (for example, adding anchors), while
preserving run/corpus contract fields for strict ratification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _query_count(payload: Any) -> int:
    if isinstance(payload, dict):
        queries = payload.get("queries")
        return len(queries) if isinstance(queries, list) else 0
    if isinstance(payload, list):
        return len(payload)
    return 0


def _path_matches(left: str, right: str) -> bool:
    a = str(left or "").strip().replace("\\", "/")
    b = str(right or "").strip().replace("\\", "/")
    if not a or not b:
        return False
    return a == b or a.endswith(f"/{b}") or b.endswith(f"/{a}")


def _eligible_for_refresh(benchmark_path: Path, payload: Any) -> bool:
    if isinstance(payload, dict):
        anchors = payload.get("anchors")
        return isinstance(anchors, dict) and bool(anchors)
    if isinstance(payload, list):
        sidecar = benchmark_path.with_suffix(".anchors.json")
        return sidecar.exists()
    return False


def refresh_one(benchmark_path: Path) -> bool:
    benchmark_path = benchmark_path.resolve()
    contract_path = benchmark_path.with_suffix(".contract.json")
    if not contract_path.exists() or not benchmark_path.exists():
        return False

    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not _eligible_for_refresh(benchmark_path, payload):
        return False

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    benchmark_sha = _sha256_file(benchmark_path)
    count = _query_count(payload)

    contract["benchmark_sha256"] = benchmark_sha
    contract["query_count"] = int(count)

    benchmark_definition = contract.get("benchmark_definition")
    if isinstance(benchmark_definition, dict):
        definition_path = str(benchmark_definition.get("path") or "")
        if _path_matches(definition_path, str(benchmark_path)):
            benchmark_definition["sha256"] = benchmark_sha

    benchmark_projection = contract.get("benchmark_projection")
    if isinstance(benchmark_projection, dict):
        projection_path = str(benchmark_projection.get("path") or "")
        if _path_matches(projection_path, str(benchmark_path)):
            benchmark_projection["sha256"] = benchmark_sha
            benchmark_projection["query_count"] = int(count)

    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh benchmark contract hashes for enriched benchmarks.")
    parser.add_argument(
        "--root",
        type=str,
        default="evals/retrieval",
        help="Root directory to scan for benchmark JSON files.",
    )
    parser.add_argument(
        "--benchmarks",
        type=str,
        nargs="*",
        default=[],
        help="Optional explicit benchmark files. If omitted, scans --root recursively.",
    )
    args = parser.parse_args()

    base = Path.cwd()
    candidates: list[Path]
    if args.benchmarks:
        candidates = [((base / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()) for path in args.benchmarks]
    else:
        scan_root = (base / args.root).resolve() if not Path(args.root).is_absolute() else Path(args.root).resolve()
        candidates = sorted(
            p for p in scan_root.rglob("*.json")
            if not p.name.endswith(".contract.json") and not p.name.endswith(".anchors.json")
        )

    refreshed: list[Path] = []
    for benchmark_path in candidates:
        if refresh_one(benchmark_path):
            refreshed.append(benchmark_path)

    print(f"Refreshed contracts: {len(refreshed)}")
    for path in refreshed:
        print(f"- {path}")


if __name__ == "__main__":
    main()
