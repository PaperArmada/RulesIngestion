#!/usr/bin/env python3
"""
Run Mark III Stage A + B on every page of a PDF, then write an evaluation report.

Usage (from RulesIngestion root):
  uv run python scripts/run_mark3_full_pdf.py --pdf brutal_pages/DnD5eBrutalChapters.pdf
  uv run python scripts/run_mark3_full_pdf.py --pdf path/to/book.pdf --out-dir out/my_run

Output:
  - out/<out_dir>/<pdf_stem>_p0/, ... — per-page Stage A + B artifacts
  - out/<out_dir>/run_summary.json — per-page results
  - out/<out_dir>/EVALUATION_REPORT.md — human-readable gate and salvage summary
  - out/<out_dir>/evaluation_report.json — full structured report
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import sys
import time
from pathlib import Path

import blake3
import fitz  # pymupdf

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.gates_b import run_stage_b_gates
from extraction.orphan_header import discover_orphans, run_orphan_header_pass
from extraction.pipeline import run_a_b, run_a_b_aprime, run_join_pass_and_gate
from extraction.schemas import EvidenceUnit

logger = logging.getLogger(__name__)


def _parse_page_number(dir_name: str) -> int | None:
    m = re.search(r"_p(\d+)$", dir_name)
    return int(m.group(1)) if m else None


def _recompute_unit_id(text: str, structural_path: list[str]) -> str:
    path_str = " > ".join(structural_path)
    return blake3.blake3(f"{text}|{path_str}".encode()).hexdigest()


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


def get_page_count(pdf_path: Path) -> int:
    """Return number of pages using PyMuPDF."""
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    doc = fitz.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def load_existing_result(
    out_base: Path, stem: str, page_index: int, pdf_path: Path
) -> dict | None:
    """Load one run result from a page dir's pipeline_summary.json. Returns None if missing."""
    label = f"{stem}_p{page_index}"
    summary_path = out_base / label / "pipeline_summary.json"
    if not summary_path.exists():
        return None
    raw = json.loads(summary_path.read_text(encoding="utf-8"))
    stage_a = raw.get("stage_a")
    stage_b = raw.get("stage_b")
    units = (stage_b or {}).get("units") or []
    return {
        "label": label,
        "pdf": str(pdf_path),
        "page": page_index,
        "elapsed_sec": 0,
        "error": None,
        "stage_a": {
            "gates_passed": stage_a["gates_passed"],
            "node_count": stage_a["node_count"],
            "table_count": stage_a["table_count"],
            "content_hash": stage_a["content_hash"],
            "gate_details": stage_a.get("gate_details", []),
        }
        if stage_a
        else None,
        "stage_b": {
            "unit_count": len(units),
            "gates_passed": stage_b["gates_passed"],
            "salvage_score": stage_b["salvage_score"],
            "gate_details": stage_b.get("gate_details", []),
        }
        if stage_b
        else None,
        "all_gates_passed": raw.get("all_gates_passed", False),
    }


def main() -> None:
    # Load .env.development from DungeonOverMind root before anything uses OPENAI_API_KEY.
    _load_env_development()

    import argparse
    parser = argparse.ArgumentParser(
        description="Run Stage A+B on all pages of a PDF and write evaluation report."
    )
    parser.add_argument("--pdf", type=Path, required=True, help="Path to the PDF.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "out" / "mark3_evaluation",
        help="Base output directory (default: out/mark3_evaluation).",
    )
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI.")
    parser.add_argument(
        "--start-page",
        type=int,
        default=0,
        help="Resume from this page index (0-based). Load results from existing page dirs for pages 0..start_page-1.",
    )
    parser.add_argument(
        "--stage",
        choices=["ab", "ab+aprime"],
        default="ab+aprime",
        help="ab = Stage A+B only; ab+aprime = A+B then Stage A' enrichment (default, standard path). Requires OPENAI_API_KEY for A'.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pdf_path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    num_pages = get_page_count(pdf_path)
    stem = pdf_path.stem
    out_base = args.out_dir.resolve() / stem
    out_base.mkdir(parents=True, exist_ok=True)

    start_page = max(0, args.start_page)
    if start_page >= num_pages:
        print("Error: --start-page >= number of pages", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print(f"Mark III Full PDF: {pdf_path.name}")
    print(f"Pages: {num_pages}")
    print(f"Output: {out_base}")
    if start_page > 0:
        print(f"Resume: loading pages 0..{start_page - 1}, running pages {start_page}..{num_pages - 1}")
    print("=" * 70)
    print()

    # Load existing results for pages 0..start_page-1 (resume)
    results: list[dict] = []
    for page_index in range(start_page):
        existing = load_existing_result(out_base, stem, page_index, pdf_path)
        if existing is not None:
            results.append(existing)
        else:
            results.append({
                "label": f"{stem}_p{page_index}",
                "pdf": str(pdf_path),
                "page": page_index,
                "elapsed_sec": 0,
                "error": "missing pipeline_summary.json (skipped)",
                "stage_a": None,
                "stage_b": None,
                "all_gates_passed": False,
            })
    if start_page > 0:
        print(f"Loaded {len([r for r in results if r.get('error') is None])}/{start_page} existing page results.\n")

    total_t0 = time.perf_counter()

    for page_index in range(start_page, num_pages):
        label = f"{stem}_p{page_index}"
        page_out = out_base / label
        print(f"[{page_index + 1}/{num_pages}] {label} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            if args.stage == "ab+aprime":
                combined = run_a_b_aprime(
                    pdf_path, page_index, page_out,
                    dpi=args.dpi,
                    book_id=stem,
                )
            else:
                combined = run_a_b(pdf_path, page_index, page_out, dpi=args.dpi)
            elapsed = time.perf_counter() - t0
            result_entry = {
                "label": label,
                "pdf": str(pdf_path),
                "page": page_index,
                "elapsed_sec": round(elapsed, 3),
                "error": None,
                "stage_a": {
                    "gates_passed": combined["stage_a"]["gates_passed"],
                    "node_count": combined["stage_a"]["node_count"],
                    "table_count": combined["stage_a"]["table_count"],
                    "content_hash": combined["stage_a"]["content_hash"],
                    "gate_details": combined["stage_a"]["gate_details"],
                },
                "stage_b": {
                    "unit_count": len(combined["stage_b"]["units"]),
                    "gates_passed": combined["stage_b"]["gates_passed"],
                    "salvage_score": combined["stage_b"]["salvage_score"],
                    "gate_details": combined["stage_b"]["gate_details"],
                },
                "all_gates_passed": combined["all_gates_passed"],
            }
            if "stage_a_prime" in combined:
                result_entry["stage_a_prime"] = {
                    "gates_passed": combined["stage_a_prime"]["gates_passed"],
                    "enrichment_count": len(combined["stage_a_prime"].get("enrichments", {})),
                }
            results.append(result_entry)
            a_prime_suffix = ""
            if "stage_a_prime" in combined:
                ap = combined["stage_a_prime"]
                a_prime_suffix = f"  A'={'PASS' if ap['gates_passed'] else 'FAIL'}"
            print(f"{elapsed:.1f}s  A={'PASS' if combined['stage_a']['gates_passed'] else 'FAIL'}  "
                  f"B={'PASS' if combined['stage_b']['gates_passed'] else 'FAIL'}  "
                  f"units={len(combined['stage_b']['units'])}  salvage={combined['stage_b']['salvage_score']:.2f}"
                  f"{a_prime_suffix}")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            results.append({
                "label": label,
                "pdf": str(pdf_path),
                "page": page_index,
                "elapsed_sec": round(elapsed, 3),
                "error": str(e),
                "stage_a": None,
                "stage_b": None,
                "all_gates_passed": False,
            })
            print(f"{elapsed:.1f}s  ERROR: {e}")
            logger.exception("Page %s failed", label)

    total_elapsed = time.perf_counter() - total_t0

    # Write run summary
    summary_path = out_base / "run_summary.json"
    summary_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nRun summary: {summary_path}")

    # ─── Orphan header pass (LLM assignment for orphans) ─────────────────
    _load_env_development()
    orphan_header_results: list[dict] = []
    assigned_by_label: dict[str, str] = {}
    try:
        if os.environ.get("OPENAI_API_KEY"):
            orphan_header_results = run_orphan_header_pass(out_base)
            for r in orphan_header_results:
                if r.get("status") == "assigned" and r.get("heading"):
                    assigned_by_label[r["label"]] = r["heading"]
                    print(f"[LLM] {r['label']} → {r['heading']!r}")
            assigned = len(assigned_by_label)
            print(f"Orphan header pass: {assigned} assigned, {len(orphan_header_results) - assigned} skipped")
        else:
            print("Orphan header pass: skipped (OPENAI_API_KEY not set)")
    except Exception as e:
        logger.warning("Orphan header pass failed: %s", e)
        print(f"Orphan header pass: skipped ({e})")

    # ─── Update units with assigned headings, re-run gates, refresh results ─
    for result in results:
        if result.get("error"):
            continue
        label = result["label"]
        page_dir = out_base / label
        units_path = page_dir / "stageB.evidence_units.json"
        ast_path = page_dir / "stageA.surface.ast.json"
        summary_path = page_dir / "pipeline_summary.json"
        if not units_path.exists() or not ast_path.exists():
            continue

        # Update stageB.evidence_units.json with LLM-assigned headings
        if label in assigned_by_label:
            heading = assigned_by_label[label]
            stage_b_data = json.loads(units_path.read_text(encoding="utf-8"))
            units_raw = stage_b_data.get("units", [])
            path = [heading]
            updated_units = []
            for u in units_raw:
                unit = EvidenceUnit.from_dict(u)
                updated_units.append(EvidenceUnit(
                    unit_id=_recompute_unit_id(unit.text, path),
                    unit_type=unit.unit_type,
                    text=unit.text,
                    structural_path=path,
                    ordering_key=unit.ordering_key,
                    page_fingerprint=unit.page_fingerprint,
                    content_hash=unit.content_hash,
                    source_line_start=unit.source_line_start,
                    source_line_end=unit.source_line_end,
                    anomaly_flags=[f for f in unit.anomaly_flags if f != "no_heading_parent"],
                    content_version=unit.content_version,
                ))
            stage_b_data["units"] = [u.to_dict() for u in updated_units]
            units_path.write_text(
                json.dumps(stage_b_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        # Re-run gates and refresh result
        ast_data = json.loads(ast_path.read_text(encoding="utf-8"))
        stage_b_data = json.loads(units_path.read_text(encoding="utf-8"))
        units = [EvidenceUnit.from_dict(u) for u in stage_b_data.get("units", [])]
        page_num = _parse_page_number(label) or 0
        diagnostics = run_stage_b_gates(
            units, ast_dict=ast_data, is_standalone=(page_num == 0)
        )
        gates_passed = all(g.passed for g in diagnostics)

        # Update stageB.gate_diagnostics.json
        diag_path = page_dir / "stageB.gate_diagnostics.json"
        diag_path.write_text(
            json.dumps([g.to_dict() for g in diagnostics], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Update pipeline_summary.json
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            sb = summary.get("stage_b") or {}
            sb["gates_passed"] = gates_passed
            sb["gate_details"] = [g.to_dict() for g in diagnostics]
            summary["stage_b"] = sb
            summary["all_gates_passed"] = (
                summary.get("stage_a", {}).get("gates_passed", False) and gates_passed
            )
            summary_path.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        # Refresh result for evaluation report
        result["stage_b"]["gates_passed"] = gates_passed
        result["stage_b"]["gate_details"] = [g.to_dict() for g in diagnostics]
        result["all_gates_passed"] = (
            result.get("stage_a") and result["stage_a"]["gates_passed"] and gates_passed
        )

    # ─── R3: Cross-page join pass (multi-page only) ─────────────────────
    units_by_page: list[list] = []
    for r in sorted(results, key=lambda x: x.get("page", 0)):
        if r.get("error"):
            continue
        label = r["label"]
        page_dir = out_base / label
        units_path = page_dir / "stageB.evidence_units.json"
        if not units_path.exists():
            continue
        stage_b_data = json.loads(units_path.read_text(encoding="utf-8"))
        page_units = [EvidenceUnit.from_dict(u) for u in stage_b_data.get("units", [])]
        units_by_page.append(page_units)
    join_diagnostics: list = []
    if len(units_by_page) >= 2:
        joined_units, join_diagnostics = run_join_pass_and_gate(units_by_page)
        join_gate_passed = all(g.passed for g in join_diagnostics)
        print(f"Cross-page join pass: {len(joined_units)} units, gate={'PASS' if join_gate_passed else 'FAIL'}")
        joined_path = out_base / "joined.evidence_units.json"
        joined_path.write_text(
            json.dumps({"units": [u.to_dict() for u in joined_units]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        for gn in ["cross_page_join_rate"]:
            if gn not in b_gate_names:
                b_gate_names.append(gn)
        for r in results:
            if r.get("error"):
                continue
            if r.get("stage_b"):
                for g in join_diagnostics:
                    r["stage_b"].setdefault("gate_details", []).append(g.to_dict())
                if not join_gate_passed:
                    r["stage_b"]["gates_passed"] = False
                    r["all_gates_passed"] = False

    # ─── Evaluation report ─────────────────────────────────────────────
    valid = [r for r in results if r.get("error") is None]
    errors = [r for r in results if r.get("error") is not None]

    # Stage A gate aggregates
    a_gate_names = ["coverage", "ordering", "table_parse"]
    a_rates: dict[str, float] = {}
    for gn in a_gate_names:
        passed = sum(
            1 for r in valid
            if r.get("stage_a") and any(
                g["gate_name"] == gn and g["passed"]
                for g in r["stage_a"].get("gate_details", [])
            )
        )
        a_rates[gn] = passed / len(valid) if valid else 0.0

    # Stage B gate aggregates
    b_gate_names = ["orphan", "bleed", "table_integrity", "unit_size"]
    b_rates: dict[str, float] = {}
    for gn in b_gate_names:
        passed = sum(
            1 for r in valid
            if r.get("stage_b") and any(
                g["gate_name"] == gn and g["passed"]
                for g in r["stage_b"].get("gate_details", [])
            )
        )
        b_rates[gn] = passed / len(valid) if valid else 0.0

    # Per-gate failed page labels (so you can open those page dirs manually)
    def failed_labels(valid_results: list[dict], gate_names: list[str], stage_key: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {gn: [] for gn in gate_names}
        for r in valid_results:
            stage = r.get(stage_key)
            if not stage:
                continue
            for g in stage.get("gate_details", []):
                gn = g.get("gate_name")
                if gn in out and not g.get("passed", True):
                    out[gn].append(r["label"])
        return out

    stage_a_failed = failed_labels(valid, a_gate_names, "stage_a")
    stage_b_failed = failed_labels(valid, b_gate_names, "stage_b")

    salvage_scores = [r["stage_b"]["salvage_score"] for r in valid if r.get("stage_b")]
    unit_counts = [r["stage_b"]["unit_count"] for r in valid if r.get("stage_b")]

    report = {
        "pdf": str(pdf_path),
        "stem": stem,
        "num_pages": num_pages,
        "total_elapsed_sec": round(total_elapsed, 3),
        "valid_pages": len(valid),
        "error_pages": len(errors),
        "stage_a_gate_rates": a_rates,
        "stage_b_gate_rates": b_rates,
        "salvage_score_mean": round(statistics.mean(salvage_scores), 4) if salvage_scores else 0,
        "salvage_score_median": round(statistics.median(salvage_scores), 4) if salvage_scores else 0,
        "salvage_score_min": round(min(salvage_scores), 4) if salvage_scores else 0,
        "salvage_score_max": round(max(salvage_scores), 4) if salvage_scores else 0,
        "unit_count_total": sum(unit_counts) if unit_counts else 0,
        "unit_count_per_page_mean": round(statistics.mean(unit_counts), 1) if unit_counts else 0,
        "all_a_gates_pass_count": sum(1 for r in valid if r.get("stage_a") and r["stage_a"]["gates_passed"]),
        "all_b_gates_pass_count": sum(1 for r in valid if r.get("stage_b") and r["stage_b"]["gates_passed"]),
        "all_ab_gates_pass_count": sum(1 for r in valid if r.get("all_gates_passed")),
        "per_page_results": results,
        "error_labels": [r["label"] for r in errors],
        "stage_a_failed_pages": stage_a_failed,
        "stage_b_failed_pages": stage_b_failed,
        "orphan_header_results": orphan_header_results,
    }

    report_json_path = out_base / "evaluation_report.json"
    report_json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Markdown report
    md_lines = [
        "# Mark III Evaluation Report",
        "",
        f"**PDF:** `{pdf_path.name}`",
        f"**Stem:** {stem}",
        f"**Pages:** {num_pages}",
        f"**Total time:** {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)",
        "",
        "## Summary",
        "",
        f"- Valid pages: {len(valid)}",
        f"- Error pages: {len(errors)}",
        f"- All Stage A gates pass: {report['all_a_gates_pass_count']}/{len(valid)} ({report['all_a_gates_pass_count']/len(valid)*100:.0f}%)" if valid else "-",
        f"- All Stage B gates pass: {report['all_b_gates_pass_count']}/{len(valid)} ({report['all_b_gates_pass_count']/len(valid)*100:.0f}%)" if valid else "-",
        f"- All A+B gates pass: {report['all_ab_gates_pass_count']}/{len(valid)}" if valid else "-",
        "",
        "## Stage A gate pass rates",
        "",
    ]
    for gn in a_gate_names:
        rate = a_rates.get(gn, 0)
        pct = rate * 100
        md_lines.append(f"- **{gn}:** {pct:.1f}%")
    md_lines.extend(["", "## Stage B gate pass rates", ""])
    for gn in b_gate_names:
        rate = b_rates.get(gn, 0)
        pct = rate * 100
        md_lines.append(f"- **{gn}:** {pct:.1f}%")

    # Pages that failed each gate (for manual inspection)
    md_lines.extend(["", "## Pages that failed each gate", ""])
    any_failed = False
    for gate_list, failed_map, stage_label in [
        (a_gate_names, stage_a_failed, "Stage A"),
        (b_gate_names, stage_b_failed, "Stage B"),
    ]:
        for gn in gate_list:
            labels = failed_map.get(gn, [])
            if not labels:
                continue
            any_failed = True
            # Label is like DnD5eBrutalChapters_p13 → page 13
            pages = sorted(set(r["page"] for r in results if r["label"] in labels))
            page_str = ", ".join(str(p) for p in pages)
            md_lines.append(f"- **{stage_label} – {gn}:** pages {page_str} ({', '.join(labels)})")
    if not any_failed:
        md_lines.append("- All gates passed on all pages.")
    md_lines.append("")

    # Orphan header assignment (LLM)
    if orphan_header_results:
        md_lines.extend(["", "## Orphan header assignment", ""])
        for r in orphan_header_results:
            status = r.get("status", "?")
            if status == "assigned":
                md_lines.append(f"- **{r['label']}:** `{r.get('heading', '')}` — {r.get('reason', '')}")
            else:
                md_lines.append(f"- **{r['label']}:** {status}")

    md_lines.extend([
        "",
        "## Salvage score",
        "",
        f"- Mean: {report['salvage_score_mean']:.4f}",
        f"- Median: {report['salvage_score_median']:.4f}",
        f"- Min: {report['salvage_score_min']:.4f}",
        f"- Max: {report['salvage_score_max']:.4f}",
        "",
        "## Evidence units",
        "",
        f"- Total: {report['unit_count_total']}",
        f"- Per page (mean): {report['unit_count_per_page_mean']:.1f}",
        "",
    ])
    if errors:
        md_lines.extend(["## Errors", ""])
        for r in errors:
            md_lines.append(f"- **{r['label']}:** {r['error'][:200]}")
        md_lines.append("")

    report_md_path = out_base / "EVALUATION_REPORT.md"
    report_md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"Evaluation report (JSON): {report_json_path}")
    print(f"Evaluation report (MD):  {report_md_path}")
    print("=" * 70)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
