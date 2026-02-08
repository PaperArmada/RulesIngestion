#!/usr/bin/env python3
"""
Mark III Pipeline Evaluation — run AST parser + Stage A/B gates on existing
DeepSeek OCR output from the brutal suite.

No GPU required — uses pre-existing *_ocr.json markdown.

Usage (from RulesIngestion root):
  uv run python scripts/evaluate_mark3_pipeline.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

import blake3

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.ast_parser import parse_markdown_to_ast  # noqa: E402
from extraction.gates_a import run_stage_a_gates          # noqa: E402
from extraction.gates_b import run_stage_b_gates          # noqa: E402
from extraction.orphan_header import run_orphan_header_pass  # noqa: E402
from extraction.schemas import EvidenceUnit               # noqa: E402
from extraction.stage_b import run_stage_b                # noqa: E402

OCR_BRUTAL_DIR = REPO_ROOT / "out" / "deepseek_ocr2_brutal"
OUT_DIR = REPO_ROOT / "out" / "mark3_evaluation"


def _load_env_development() -> None:
    """Load .env.development from repo root if present."""
    env_path = REPO_ROOT.parent / ".env.development"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value


def _recompute_unit_id(text: str, structural_path: list[str]) -> str:
    path_str = " > ".join(structural_path)
    return blake3.blake3(f"{text}|{path_str}".encode()).hexdigest()


def load_ocr_markdown(ocr_json_path: Path) -> tuple[str, dict]:
    """Load raw markdown and metadata from a DeepSeek OCR JSON."""
    data = json.loads(ocr_json_path.read_text(encoding="utf-8"))
    return data.get("markdown", ""), data


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Discover all OCR JSON files
    ocr_jsons = sorted(OCR_BRUTAL_DIR.rglob("*_ocr.json"))
    if not ocr_jsons:
        print(f"No OCR JSON files found in {OCR_BRUTAL_DIR}", file=sys.stderr)
        sys.exit(1)

    print("=" * 90)
    print("Mark III Pipeline Evaluation — Brutal Pages Suite")
    print(f"Source: {OCR_BRUTAL_DIR}")
    print(f"Pages:  {len(ocr_jsons)}")
    print("=" * 90)
    print()

    results: list[dict] = []
    page_data: dict[str, dict] = {}  # stem → {ast_dict, units, md}

    for ocr_json in ocr_jsons:
        stem = ocr_json.parent.name
        md, meta = load_ocr_markdown(ocr_json)

        if not md.strip():
            results.append({
                "stem": stem,
                "empty": True,
                "error": "Empty markdown",
            })
            continue

        # ── Stage A: Parse + Gates ─────────────────────────────────────
        try:
            ast = parse_markdown_to_ast(md, f"eval_{stem}")
            a_gates = run_stage_a_gates(md, ast)
        except Exception as e:
            results.append({
                "stem": stem,
                "empty": False,
                "error": f"Stage A parse error: {e}",
            })
            continue

        # ── Stage B: Segment + Gates ───────────────────────────────────
        try:
            b_result = run_stage_b(ast)
            ast_dict = ast.to_dict()
            b_gates = run_stage_b_gates(b_result.units, ast_dict=ast_dict, is_standalone=True)
        except Exception as e:
            results.append({
                "stem": stem,
                "empty": False,
                "error": f"Stage B error: {e}",
                "stage_a": {
                    "node_count": ast.node_count,
                    "table_count": ast.table_count,
                    "gates": {g.gate_name: g.passed for g in a_gates},
                },
            })
            continue

        # ── Collect metrics ────────────────────────────────────────────
        unit_types = {}
        for u in b_result.units:
            unit_types[u.unit_type] = unit_types.get(u.unit_type, 0) + 1

        unit_sizes = [len(u.text) for u in b_result.units]
        anomaly_counts: dict[str, int] = {}
        for u in b_result.units:
            for flag in u.anomaly_flags:
                anomaly_counts[flag] = anomaly_counts.get(flag, 0) + 1

        results.append({
            "stem": stem,
            "empty": False,
            "error": None,
            "raw_md_chars": len(md),
            "raw_md_lines": len(md.split("\n")),
            "stage_a": {
                "node_count": ast.node_count,
                "table_count": ast.table_count,
                "content_hash": ast.content_hash[:16],
                "gates": {g.gate_name: g.passed for g in a_gates},
                "gate_details": {g.gate_name: g.detail for g in a_gates},
            },
            "stage_b": {
                "unit_count": len(b_result.units),
                "unit_types": unit_types,
                "unit_size_min": min(unit_sizes) if unit_sizes else 0,
                "unit_size_max": max(unit_sizes) if unit_sizes else 0,
                "unit_size_mean": round(statistics.mean(unit_sizes), 1) if unit_sizes else 0,
                "unit_size_median": round(statistics.median(unit_sizes), 1) if unit_sizes else 0,
                "anomaly_counts": anomaly_counts,
                "salvage_score": round(b_result.salvage_score, 4),
                "gates": {g.gate_name: g.passed for g in b_gates},
                "gate_details": {g.gate_name: g.detail for g in b_gates},
            },
        })

        # Write per-page artifacts for orphan header pass
        page_dir = OUT_DIR / f"{stem}_p0"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "stageA.surface.md").write_text(md, encoding="utf-8")
        (page_dir / "stageA.surface.ast.json").write_text(
            json.dumps(ast_dict, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        page_data[stem] = {"ast_dict": ast_dict, "units": b_result.units}

    # ── Orphan header pass ─────────────────────────────────────────────
    _load_env_development()
    orphan_header_results: list[dict] = []
    prompt_path = OUT_DIR / "DnD5eBrutalChapters" / "ORPHAN_HEADER_PROMPT.md"
    if not prompt_path.exists():
        prompt_path = OUT_DIR / "ORPHAN_HEADER_PROMPT.md"
    if os.environ.get("OPENAI_API_KEY"):
        try:
            orphan_header_results = run_orphan_header_pass(OUT_DIR, prompt_path=prompt_path)
            assigned = {
                r["label"]: r["heading"]
                for r in orphan_header_results
                if r.get("status") == "assigned" and r.get("heading")
            }
            for result in results:
                if result.get("error"):
                    continue
                stem = result["stem"]
                label = f"{stem}_p0"
                if label not in assigned or stem not in page_data:
                    continue
                heading = assigned[label]
                units = page_data[stem]["units"]
                path = [heading]
                updated_units = []
                for u in units:
                    updated_units.append(EvidenceUnit(
                        unit_id=_recompute_unit_id(u.text, path),
                        unit_type=u.unit_type,
                        text=u.text,
                        structural_path=path,
                        ordering_key=u.ordering_key,
                        page_fingerprint=u.page_fingerprint,
                        content_hash=u.content_hash,
                        source_line_start=u.source_line_start,
                        source_line_end=u.source_line_end,
                        anomaly_flags=[f for f in u.anomaly_flags if f != "no_heading_parent"],
                    ))
                # Re-gate with updated units
                b_gates = run_stage_b_gates(
                    updated_units,
                    ast_dict=page_data[stem]["ast_dict"],
                    is_standalone=True,
                )
                result["stage_b"]["gates"] = {g.gate_name: g.passed for g in b_gates}
                result["stage_b"]["gate_details"] = {g.gate_name: g.detail for g in b_gates}
                new_anomaly_counts: dict[str, int] = {}
                for u in updated_units:
                    for flag in u.anomaly_flags:
                        new_anomaly_counts[flag] = new_anomaly_counts.get(flag, 0) + 1
                result["stage_b"]["anomaly_counts"] = new_anomaly_counts
                print(f"[LLM] {label} → {heading!r}")
        except Exception as e:
            print(f"Orphan header pass failed: {e}")
    else:
        print("Orphan header pass: skipped (OPENAI_API_KEY not set)")
    print()

    # ══════════════════════════════════════════════════════════════════
    # REPORT
    # ══════════════════════════════════════════════════════════════════
    valid = [r for r in results if not r.get("error")]
    errors = [r for r in results if r.get("error")]
    empties = [r for r in results if r.get("empty")]

    print(f"Total pages processed: {len(results)}")
    print(f"  Valid:  {len(valid)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Empty:  {len(empties)}")
    print()

    # ── Stage A Gate Summary ───────────────────────────────────────
    print("-" * 70)
    print("STAGE A GATE RESULTS")
    print("-" * 70)
    a_gate_names = ["coverage", "ordering", "table_parse"]
    for gn in a_gate_names:
        passed = sum(1 for r in valid if r["stage_a"]["gates"].get(gn, False))
        total = len(valid)
        rate = passed / total if total else 0
        print(f"  {gn:20s}: {passed:3d}/{total:3d} ({rate:6.1%})")

    # Coverage ratio distribution
    coverage_ratios = [
        r["stage_a"]["gate_details"]["coverage"]["ratio"]
        for r in valid
        if "coverage" in r["stage_a"]["gate_details"]
    ]
    if coverage_ratios:
        print()
        print(f"  Coverage ratio distribution:")
        print(f"    min={min(coverage_ratios):.4f}  max={max(coverage_ratios):.4f}  "
              f"mean={statistics.mean(coverage_ratios):.4f}  "
              f"median={statistics.median(coverage_ratios):.4f}")
        below_threshold = [r for r in coverage_ratios if r < 0.95]
        if below_threshold:
            print(f"    Below 0.95 threshold: {len(below_threshold)} pages")
            for r in valid:
                ratio = r["stage_a"]["gate_details"]["coverage"]["ratio"]
                if ratio < 0.95:
                    print(f"      {r['stem']}: ratio={ratio:.4f}")

    # Table parse details
    table_pages = [r for r in valid if r["stage_a"]["table_count"] > 0]
    if table_pages:
        print()
        print(f"  Pages with tables: {len(table_pages)}/{len(valid)}")
        for r in table_pages:
            td = r["stage_a"]["gate_details"]["table_parse"]
            passed = r["stage_a"]["gates"]["table_parse"]
            status = "PASS" if passed else "FAIL"
            print(f"    {r['stem']}: {td['raw_table_count']} tables, "
                  f"{sum(td['raw_row_counts'])} rows  [{status}]")

    # ── Stage B Gate Summary ───────────────────────────────────────
    print()
    print("-" * 70)
    print("STAGE B GATE RESULTS")
    print("-" * 70)
    b_gate_names = ["orphan", "bleed", "table_integrity", "unit_size"]
    for gn in b_gate_names:
        passed = sum(1 for r in valid if r["stage_b"]["gates"].get(gn, False))
        total = len(valid)
        rate = passed / total if total else 0
        print(f"  {gn:20s}: {passed:3d}/{total:3d} ({rate:6.1%})")

    # ── EvidenceUnit Statistics ────────────────────────────────────
    print()
    print("-" * 70)
    print("EVIDENCE UNIT STATISTICS")
    print("-" * 70)
    all_unit_counts = [r["stage_b"]["unit_count"] for r in valid]
    all_sizes = []
    total_type_counts: dict[str, int] = {}
    total_anomalies: dict[str, int] = {}

    for r in valid:
        for ut, count in r["stage_b"]["unit_types"].items():
            total_type_counts[ut] = total_type_counts.get(ut, 0) + count
        for flag, count in r["stage_b"]["anomaly_counts"].items():
            total_anomalies[flag] = total_anomalies.get(flag, 0) + count
        # Reconstruct sizes from min/max/mean/count for approximation
        all_sizes.append(r["stage_b"]["unit_size_mean"])

    total_units = sum(all_unit_counts)
    print(f"  Total EvidenceUnits: {total_units}")
    if all_unit_counts:
        print(f"  Per page: min={min(all_unit_counts)}  max={max(all_unit_counts)}  "
              f"mean={statistics.mean(all_unit_counts):.1f}  "
              f"median={statistics.median(all_unit_counts):.1f}")

    print()
    print("  Unit type distribution:")
    for ut, count in sorted(total_type_counts.items(), key=lambda x: -x[1]):
        pct = count / total_units * 100 if total_units else 0
        print(f"    {ut:12s}: {count:5d} ({pct:5.1f}%)")

    if total_anomalies:
        print()
        print("  Anomaly flag distribution:")
        for flag, count in sorted(total_anomalies.items(), key=lambda x: -x[1]):
            print(f"    {flag:20s}: {count:5d}")

    # ── Salvage Score ──────────────────────────────────────────────
    print()
    print("-" * 70)
    print("SALVAGE SCORE")
    print("-" * 70)
    salvage_scores = [r["stage_b"]["salvage_score"] for r in valid]
    if salvage_scores:
        print(f"  min={min(salvage_scores):.4f}  max={max(salvage_scores):.4f}  "
              f"mean={statistics.mean(salvage_scores):.4f}  "
              f"median={statistics.median(salvage_scores):.4f}")
        perfect = sum(1 for s in salvage_scores if s == 1.0)
        print(f"  Perfect (1.0): {perfect}/{len(salvage_scores)}")

    # ── Per-Page Detail Table ──────────────────────────────────────
    print()
    print("-" * 90)
    print(f"{'Stem':<35} {'Nodes':>5} {'Tbls':>4} {'Units':>5} "
          f"{'Cov':>5} {'Ord':>3} {'TblP':>4} "
          f"{'Orph':>4} {'Bld':>3} {'TblI':>4} {'Size':>4} {'Salv':>6}")
    print("-" * 90)
    for r in sorted(valid, key=lambda x: x["stem"]):
        ag = r["stage_a"]["gates"]
        bg = r["stage_b"]["gates"]
        cov_ratio = r["stage_a"]["gate_details"]["coverage"]["ratio"]
        print(
            f"{r['stem']:<35} "
            f"{r['stage_a']['node_count']:5d} "
            f"{r['stage_a']['table_count']:4d} "
            f"{r['stage_b']['unit_count']:5d} "
            f"{cov_ratio:5.2f} "
            f"{'P' if ag.get('ordering') else 'F':>3} "
            f"{'P' if ag.get('table_parse') else 'F':>4} "
            f"{'P' if bg.get('orphan') else 'F':>4} "
            f"{'P' if bg.get('bleed') else 'F':>3} "
            f"{'P' if bg.get('table_integrity') else 'F':>4} "
            f"{'P' if bg.get('unit_size') else 'F':>4} "
            f"{r['stage_b']['salvage_score']:6.2f}"
        )

    # ── Error / Empty Pages ────────────────────────────────────────
    if errors:
        print()
        print("-" * 70)
        print("ERRORS")
        print("-" * 70)
        for r in errors:
            print(f"  {r['stem']}: {r['error']}")

    # ── All-gates-pass summary ─────────────────────────────────────
    print()
    print("=" * 90)
    all_a_pass = sum(
        1 for r in valid
        if all(r["stage_a"]["gates"].values())
    )
    all_b_pass = sum(
        1 for r in valid
        if all(r["stage_b"]["gates"].values())
    )
    all_ab_pass = sum(
        1 for r in valid
        if all(r["stage_a"]["gates"].values()) and all(r["stage_b"]["gates"].values())
    )

    print(f"ALL STAGE A GATES PASS: {all_a_pass}/{len(valid)} ({all_a_pass/len(valid)*100:.0f}%)")
    print(f"ALL STAGE B GATES PASS: {all_b_pass}/{len(valid)} ({all_b_pass/len(valid)*100:.0f}%)")
    print(f"ALL A+B GATES PASS:     {all_ab_pass}/{len(valid)} ({all_ab_pass/len(valid)*100:.0f}%)")
    print("=" * 90)

    # Write full JSON report
    report_path = OUT_DIR / "evaluation_report.json"
    report_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nFull JSON report: {report_path}")


if __name__ == "__main__":
    main()
