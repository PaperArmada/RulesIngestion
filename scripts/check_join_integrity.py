#!/usr/bin/env python3
"""Diff per-page Stage B units against joined corpus coverage.

Detects pages/units present in page-level `stageB.evidence_units.json` that do not
appear in `joined.evidence_units.json`, using both:
  1) page fingerprint presence
  2) unit_id presence
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_page_dirs(run_dir: Path) -> list[Path]:
    return sorted(
        [
            p.parent
            for p in run_dir.rglob("stageB.evidence_units.json")
            if p.name == "stageB.evidence_units.json" and p.parent.is_dir()
        ],
        key=lambda d: d.name,
    )


def _collect_join_index(joined_units: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    join_unit_ids: set[str] = set()
    join_fingerprints: set[str] = set()
    for unit in joined_units:
        uid = unit.get("unit_id")
        if uid:
            join_unit_ids.add(uid)
        for sid in unit.get("source_unit_ids") or []:
            if sid:
                join_unit_ids.add(sid)
        fp = unit.get("page_fingerprint")
        if fp:
            join_fingerprints.add(fp)
        for multi_fp in unit.get("page_fingerprints") or []:
            if multi_fp:
                join_fingerprints.add(multi_fp)
    return join_unit_ids, join_fingerprints


def build_integrity_report(run_dir: Path) -> dict[str, Any]:
    joined_path = run_dir / "joined.evidence_units.json"
    if not joined_path.exists():
        raise FileNotFoundError(f"Missing joined artifact: {joined_path}")

    joined_data = _load_json(joined_path)
    joined_units = joined_data.get("units", [])
    join_unit_ids, join_fingerprints = _collect_join_index(joined_units)

    page_reports: list[dict[str, Any]] = []
    total_stageb_units = 0
    total_missing_units = 0
    pages_missing_by_fp = 0

    for page_dir in _iter_page_dirs(run_dir):
        stageb_path = page_dir / "stageB.evidence_units.json"
        if not stageb_path.exists():
            continue
        page_data = _load_json(stageb_path)
        units = page_data.get("units", [])
        if not units:
            continue

        total_stageb_units += len(units)
        fps = {u.get("page_fingerprint") for u in units if u.get("page_fingerprint")}
        missing_unit_ids = [u.get("unit_id") for u in units if u.get("unit_id") not in join_unit_ids]
        page_missing_by_fp = all(fp not in join_fingerprints for fp in fps) if fps else False
        if page_missing_by_fp:
            pages_missing_by_fp += 1

        total_missing_units += len(missing_unit_ids)
        if page_missing_by_fp or missing_unit_ids:
            page_reports.append(
                {
                    "page_dir": page_dir.name,
                    "stageb_unit_count": len(units),
                    "stageb_page_fingerprints": sorted(fps),
                    "page_missing_by_fingerprint": page_missing_by_fp,
                    "missing_unit_id_count": len(missing_unit_ids),
                    "missing_unit_ids": missing_unit_ids,
                }
            )

    return {
        "run_dir": str(run_dir),
        "joined_path": str(joined_path),
        "summary": {
            "joined_unit_count": len(joined_units),
            "joined_unique_unit_id_count": len(join_unit_ids),
            "joined_unique_fingerprint_count": len(join_fingerprints),
            "stageb_total_unit_count": total_stageb_units,
            "stageb_missing_unit_id_count": total_missing_units,
            "pages_missing_by_fingerprint_count": pages_missing_by_fp,
            "pages_with_any_integrity_issue_count": len(page_reports),
        },
        "pages_with_issues": page_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check integrity between per-page stageB units and joined corpus.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Path to one Mark III run output directory containing joined.evidence_units.json",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Optional output path for full JSON report.",
    )
    parser.add_argument(
        "--show-units",
        action="store_true",
        help="Print missing unit IDs for each page issue.",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    report = build_integrity_report(run_dir)
    summary = report["summary"]

    print("== Join Integrity Report ==")
    print(f"run_dir: {report['run_dir']}")
    print(f"joined_units: {summary['joined_unit_count']}")
    print(f"stageb_total_units: {summary['stageb_total_unit_count']}")
    print(f"missing_unit_ids_total: {summary['stageb_missing_unit_id_count']}")
    print(f"pages_missing_by_fingerprint: {summary['pages_missing_by_fingerprint_count']}")
    print(f"pages_with_any_issue: {summary['pages_with_any_integrity_issue_count']}")
    print()

    for page in report["pages_with_issues"]:
        print(
            f"- {page['page_dir']}: missing_units={page['missing_unit_id_count']} "
            f"missing_by_fp={page['page_missing_by_fingerprint']}"
        )
        if args.show_units and page["missing_unit_ids"]:
            for uid in page["missing_unit_ids"]:
                print(f"  - {uid}")

    if args.out_json is not None:
        out_path = args.out_json.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print()
        print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
