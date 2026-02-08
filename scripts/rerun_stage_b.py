#!/usr/bin/env python3
"""
Rerun Stage B only on existing Stage A AST artifacts.

Reads stageA.surface.ast.json from each page dir, runs the current Stage B
segmenter + gates, writes new stageB.* artifacts, and produces a comparison
report against the old Stage B output (if present).

Usage (from RulesIngestion root):
  uv run python scripts/rerun_stage_b.py --run-dir out/mark3_evaluation/DnD5eBrutalChapters
  uv run python scripts/rerun_stage_b.py --run-dir out/mark3_evaluation/DnD_PHB_5.5

Outputs per page dir:
  stageB.evidence_units.json       — new Stage B output (overwrites)
  stageB.gate_diagnostics.json     — new gate diagnostics (overwrites)
  pipeline_summary.json            — updated with new Stage B results

Outputs in run dir:
  stage_b_comparison.json          — before/after metrics
  STAGE_B_COMPARISON.md            — human-readable comparison
"""
from __future__ import annotations

import json
import logging
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.gates_b import run_stage_b_gates
from extraction.schemas import SurfaceAST
from extraction.stage_b import run_stage_b

logger = logging.getLogger(__name__)


def _collect_page_dirs(run_dir: Path) -> list[Path]:
    """Find all page dirs (contain stageA.surface.ast.json)."""
    dirs = sorted(
        d for d in run_dir.iterdir()
        if d.is_dir() and (d / "stageA.surface.ast.json").exists()
    )
    return dirs


def _snapshot_old_stage_b(page_dir: Path) -> dict | None:
    """Read old Stage B metrics from existing evidence_units file."""
    old_path = page_dir / "stageB.evidence_units.json"
    if not old_path.exists():
        return None
    raw = json.loads(old_path.read_text(encoding="utf-8"))
    units = raw.get("units", [])
    return {
        "unit_count": len(units),
        "heading_units": sum(1 for u in units if u.get("unit_type") == "heading"),
        "undersized": sum(1 for u in units if "undersized" in u.get("anomaly_flags", [])),
        "oversized": sum(1 for u in units if "oversized" in u.get("anomaly_flags", [])),
        "no_heading_parent": sum(1 for u in units if "no_heading_parent" in u.get("anomaly_flags", [])),
        "salvage_score": raw.get("salvage_score", 1.0),
        "gates_passed": raw.get("gates_passed", True),
    }


def _snapshot_new_stage_b(units_dicts: list[dict], gates_passed: bool, salvage: float, is_index: bool = False) -> dict:
    """Compute metrics from new Stage B output."""
    return {
        "unit_count": len(units_dicts),
        "heading_units": sum(1 for u in units_dicts if u.get("unit_type") == "heading"),
        "undersized": sum(1 for u in units_dicts if "undersized" in u.get("anomaly_flags", [])),
        "oversized": sum(1 for u in units_dicts if "oversized" in u.get("anomaly_flags", [])),
        "no_heading_parent": sum(1 for u in units_dicts if "no_heading_parent" in u.get("anomaly_flags", [])),
        "unabsorbed_heading": sum(1 for u in units_dicts if "unabsorbed_heading" in u.get("anomaly_flags", [])),
        "salvage_score": salvage,
        "gates_passed": gates_passed,
        "is_index_page": is_index,
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Rerun Stage B on existing Stage A ASTs.")
    parser.add_argument("--run-dir", type=Path, required=True, help="Run output directory with page subdirs.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    run_dir = args.run_dir.resolve()
    if not run_dir.exists():
        print(f"Error: {run_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    page_dirs = _collect_page_dirs(run_dir)
    if not page_dirs:
        print(f"Error: no page dirs with stageA.surface.ast.json found in {run_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Rerunning Stage B on {len(page_dirs)} pages in {run_dir.name}")
    print("=" * 70)

    old_totals: dict[str, list] = {
        "unit_count": [], "heading_units": [], "undersized": [],
        "oversized": [], "no_heading_parent": [], "salvage_score": [],
    }
    new_totals: dict[str, list] = {
        "unit_count": [], "heading_units": [], "undersized": [],
        "oversized": [], "no_heading_parent": [], "unabsorbed_heading": [],
        "salvage_score": [],
    }
    per_page: list[dict] = []
    t0 = time.perf_counter()

    for i, page_dir in enumerate(page_dirs):
        label = page_dir.name

        # Snapshot old
        old = _snapshot_old_stage_b(page_dir)

        # Load Stage A AST
        ast_path = page_dir / "stageA.surface.ast.json"
        ast_dict = json.loads(ast_path.read_text(encoding="utf-8"))
        ast = SurfaceAST.from_dict(ast_dict)

        # Determine page index from label (e.g. "DnD5eBrutalChapters_p3" -> 3)
        page_index = 0
        parts = label.rsplit("_p", 1)
        if len(parts) == 2 and parts[1].isdigit():
            page_index = int(parts[1])

        # Run Stage B
        b_result = run_stage_b(ast, out_dir=None)

        # Run gates (preserve any diagnostics already set by run_stage_b, e.g. index_page)
        diagnostics = run_stage_b_gates(
            b_result.units,
            ast_dict=ast_dict,
            is_standalone=(page_index == 0),
        )
        b_result.gate_diagnostics = b_result.gate_diagnostics + diagnostics

        # Write new artifacts
        page_dir.mkdir(parents=True, exist_ok=True)
        units_path = page_dir / "stageB.evidence_units.json"
        units_path.write_text(
            json.dumps(b_result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        diag_path = page_dir / "stageB.gate_diagnostics.json"
        diag_path.write_text(
            json.dumps([g.to_dict() for g in b_result.gate_diagnostics], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Update pipeline_summary.json if it exists
        summary_path = page_dir / "pipeline_summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["stage_b"] = {
                "units": [u.to_dict() for u in b_result.units],
                "gates_passed": b_result.gates_passed,
                "gate_details": [g.to_dict() for g in b_result.gate_diagnostics],
                "salvage_score": round(b_result.salvage_score, 4),
            }
            summary["all_gates_passed"] = (
                summary.get("stage_a", {}).get("gates_passed", True)
                and b_result.gates_passed
            )
            summary_path.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        # Detect if index page was classified
        is_index = any(
            g.gate_name == "index_page"
            for g in b_result.gate_diagnostics
        )

        # Snapshot new
        new = _snapshot_new_stage_b(
            [u.to_dict() for u in b_result.units],
            b_result.gates_passed,
            round(b_result.salvage_score, 4),
            is_index=is_index,
        )

        # Accumulate
        if old:
            for k in old_totals:
                if k in old:
                    old_totals[k].append(old[k])
        for k in new_totals:
            if k in new:
                new_totals[k].append(new[k])

        per_page.append({"label": label, "old": old, "new": new})

        tag = "INDEX" if is_index else ("PASS" if b_result.gates_passed else "FAIL")
        old_units = old["unit_count"] if old else "?"
        print(f"[{i+1}/{len(page_dirs)}] {label}  {old_units} → {new['unit_count']} units  {tag}")

    elapsed = time.perf_counter() - t0

    # Build comparison report
    def _sum_or_na(vals: list) -> int | str:
        return sum(vals) if vals else "n/a"

    def _mean_or_na(vals: list) -> float | str:
        return round(statistics.mean(vals), 4) if vals else "n/a"

    comparison = {
        "run_dir": str(run_dir),
        "pages": len(page_dirs),
        "elapsed_sec": round(elapsed, 2),
        "before": {
            "total_units": _sum_or_na(old_totals["unit_count"]),
            "heading_units": _sum_or_na(old_totals["heading_units"]),
            "undersized": _sum_or_na(old_totals["undersized"]),
            "oversized": _sum_or_na(old_totals["oversized"]),
            "no_heading_parent": _sum_or_na(old_totals["no_heading_parent"]),
            "mean_salvage": _mean_or_na(old_totals["salvage_score"]),
        },
        "after": {
            "total_units": _sum_or_na(new_totals["unit_count"]),
            "heading_units": _sum_or_na(new_totals["heading_units"]),
            "undersized": _sum_or_na(new_totals["undersized"]),
            "oversized": _sum_or_na(new_totals["oversized"]),
            "no_heading_parent": _sum_or_na(new_totals["no_heading_parent"]),
            "unabsorbed_heading": _sum_or_na(new_totals["unabsorbed_heading"]),
            "index_pages_dropped": sum(1 for p in per_page if p["new"].get("is_index_page", False)),
            "index_units_dropped": sum(
                (p["old"] or {}).get("unit_count", 0)
                for p in per_page
                if p["new"].get("is_index_page", False)
            ),
            "mean_salvage": _mean_or_na(new_totals["salvage_score"]),
        },
        "per_page": per_page,
    }

    comp_json = run_dir / "stage_b_comparison.json"
    comp_json.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown report
    b = comparison["before"]
    a = comparison["after"]
    md = [
        "# Stage B Rerun Comparison",
        "",
        f"**Run:** `{run_dir.name}`",
        f"**Pages:** {len(page_dirs)}",
        f"**Elapsed:** {elapsed:.1f}s",
        "",
        "## Before / After",
        "",
        "| Metric | Before | After | Delta |",
        "|--------|--------|-------|-------|",
    ]
    for key in ["total_units", "heading_units", "undersized", "oversized", "no_heading_parent"]:
        bv = b.get(key, "n/a")
        av = a.get(key, "n/a")
        if isinstance(bv, (int, float)) and isinstance(av, (int, float)):
            delta = av - bv
            sign = "+" if delta > 0 else ""
            md.append(f"| {key} | {bv} | {av} | {sign}{delta} |")
        else:
            md.append(f"| {key} | {bv} | {av} | — |")
    if a.get("unabsorbed_heading", 0):
        md.append(f"| unabsorbed_heading | — | {a['unabsorbed_heading']} | new |")
    md.extend([
        f"| mean_salvage | {b.get('mean_salvage', 'n/a')} | {a.get('mean_salvage', 'n/a')} | — |",
        "",
    ])

    comp_md = run_dir / "STAGE_B_COMPARISON.md"
    comp_md.write_text("\n".join(md), encoding="utf-8")

    print(f"\nComparison JSON: {comp_json}")
    print(f"Comparison MD:   {comp_md}")
    print("=" * 70)


if __name__ == "__main__":
    main()
