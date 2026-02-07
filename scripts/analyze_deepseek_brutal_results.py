#!/usr/bin/env python3
"""
Analyze the DeepSeek OCR 2 brutal-suite results.

Reads all *_ocr.json files from the suite output directory, computes structural
metrics, and prints a summary report.

Usage:
  python3 scripts/analyze_deepseek_brutal_results.py [--results-dir out/deepseek_ocr2_brutal]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def extract_metrics(md_text: str) -> dict:
    """Extract structural metrics from the markdown output."""
    lines = md_text.split("\n")
    non_empty = [l for l in lines if l.strip()]

    # Headings
    headings = [l for l in lines if re.match(r"^#{1,6}\s", l)]
    h2_count = sum(1 for l in headings if l.startswith("## ") and not l.startswith("### "))
    h3_count = sum(1 for l in headings if l.startswith("### "))

    # Tables (HTML-style <table> blocks)
    tables = re.findall(r"<table>.*?</table>", md_text, re.DOTALL)
    table_rows_total = sum(len(re.findall(r"<tr>", t)) for t in tables)

    # Image references
    image_refs = re.findall(r"!\[.*?\]\(.*?\)", md_text)

    # Bullet lists
    bullets = [l for l in lines if re.match(r"^\s*[•\-\*]\s", l)]

    # Bold/italic markers
    bold_count = len(re.findall(r"\*\*[^*]+\*\*", md_text))

    # LaTeX math fragments (model sometimes emits these)
    latex_frags = re.findall(r"\\\(.*?\\\)", md_text)

    # Stat block signals (D&D/PF2e/SF2e patterns)
    stat_signals = []
    if re.search(r"\bAC\s+\d+", md_text):
        stat_signals.append("AC")
    if re.search(r"\bHP\s+\d+", md_text):
        stat_signals.append("HP")
    if re.search(r"\bSpeed\s+\d+\s*f", md_text, re.IGNORECASE):
        stat_signals.append("Speed")
    if re.search(r"\b(Melee|Ranged)\s+[♦▶✿]", md_text):
        stat_signals.append("Attack")
    if re.search(r"\bCR\s+\d", md_text):
        stat_signals.append("CR")
    if re.search(r"\bPerception\s+\+?\d", md_text):
        stat_signals.append("Perception")
    if re.search(r"\b(Fort|Ref|Will)\s+\+\d", md_text):
        stat_signals.append("Saves-PF2e")
    if re.search(r"(STR|DEX|CON|INT|WIS|CHA)\s+\d+\s+[+\-]?\d", md_text, re.IGNORECASE):
        stat_signals.append("Abilities")

    # Spell block signals
    spell_signals = []
    if re.search(r"Casting Time:", md_text):
        spell_signals.append("CastingTime")
    if re.search(r"Components:\s*V", md_text):
        spell_signals.append("Components")
    if re.search(r"Duration:", md_text):
        spell_signals.append("Duration")
    if re.search(r"Range:\s*\d+", md_text):
        spell_signals.append("Range")

    # Reading-order: check for sidebar/nav detritus at end
    nav_detritus = bool(re.search(
        r"(INTRODUCTION|GLOSSARY\s*&\s*INDEX|CHARACTER\s+SHEET|APPENDIX)\s*$",
        md_text.strip(),
        re.IGNORECASE,
    ))

    # "Image-only" pages — model returns only image refs, no text
    image_only = len(non_empty) <= 2 and all(
        re.match(r"!\[.*?\]\(.*?\)", l.strip()) for l in non_empty if l.strip()
    )

    return {
        "total_lines": len(lines),
        "non_empty_lines": len(non_empty),
        "char_count": len(md_text),
        "heading_count": len(headings),
        "h2_count": h2_count,
        "h3_count": h3_count,
        "table_count": len(tables),
        "table_rows_total": table_rows_total,
        "image_ref_count": len(image_refs),
        "bullet_count": len(bullets),
        "bold_count": bold_count,
        "latex_frag_count": len(latex_frags),
        "stat_signals": stat_signals,
        "spell_signals": spell_signals,
        "nav_detritus": nav_detritus,
        "image_only": image_only,
    }


def classify_content(metrics: dict) -> str:
    """Rough content-type classification based on metrics."""
    if metrics["image_only"]:
        return "IMAGE-ONLY (form/sheet)"
    if len(metrics["spell_signals"]) >= 2:
        return "SPELL-BLOCK"
    if len(metrics["stat_signals"]) >= 3:
        return "STAT-BLOCK"
    if metrics["table_count"] >= 2:
        return "TABLE-HEAVY"
    if metrics["table_count"] == 1 and metrics["heading_count"] >= 3:
        return "MIXED (table+prose)"
    if metrics["heading_count"] >= 4 and metrics["bullet_count"] >= 3:
        return "RULES-PROSE (structured)"
    if metrics["heading_count"] >= 2:
        return "PROSE (headings)"
    return "PROSE (minimal structure)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze DeepSeek OCR 2 brutal-suite results.")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=REPO_ROOT / "out" / "deepseek_ocr2_brutal",
        help="Suite output directory",
    )
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()

    # Load suite timings
    timings_path = results_dir / "suite_timings.json"
    if timings_path.exists():
        timings = json.loads(timings_path.read_text())
    else:
        timings = None

    # Find all per-page JSON files
    json_files = sorted(results_dir.rglob("*_ocr.json"))
    if not json_files:
        print(f"No *_ocr.json files found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    records: list[dict] = []
    for jf in json_files:
        data = json.loads(jf.read_text())
        md_text = data.get("markdown", "")
        metrics = extract_metrics(md_text)
        content_type = classify_content(metrics)
        stem = jf.parent.name  # directory name = PDF stem
        records.append({
            "stem": stem,
            "json_path": str(jf),
            "elapsed_sec": data.get("elapsed_sec", 0),
            "result_type": data.get("result_type", "unknown"),
            "content_type": content_type,
            **metrics,
        })

    # ── REPORT ──────────────────────────────────────────────────────────
    print("=" * 80)
    print("DeepSeek OCR 2 — Brutal Suite Analysis")
    print("=" * 80)

    # Timings summary
    if timings:
        print(f"\nSuite total: {timings['suite_elapsed_min']:.1f} min ({timings['suite_elapsed_sec']:.0f}s)")
        print(f"PDFs processed: {timings['total_pdfs']}  OK: {timings['ok_count']}  FAIL: {timings['fail_count']}")
        print(f"Avg per page: {timings['avg_sec_per_page']:.1f}s")
        print("\nBook estimates:")
        for label, est in timings.get("book_estimates", {}).items():
            print(f"  {label}: {est['estimated_min']:.0f} min ({est['estimated_hr']:.2f} hr)")

    # Per-page inference times (from the JSON elapsed_sec, not the subprocess wallclock)
    inference_times = [r["elapsed_sec"] for r in records if r["elapsed_sec"] > 0]
    if inference_times:
        print(f"\nInference time (model only, from JSON):")
        print(f"  min: {min(inference_times):.1f}s  max: {max(inference_times):.1f}s  "
              f"mean: {statistics.mean(inference_times):.1f}s  median: {statistics.median(inference_times):.1f}s")
        if len(inference_times) >= 2:
            print(f"  stdev: {statistics.stdev(inference_times):.1f}s")

    # Content type distribution
    print("\n" + "-" * 60)
    print("Content Type Distribution")
    print("-" * 60)
    type_counts: dict[str, list[str]] = {}
    for r in records:
        ct = r["content_type"]
        type_counts.setdefault(ct, []).append(r["stem"])
    for ct, stems in sorted(type_counts.items(), key=lambda x: -len(x[1])):
        print(f"  {ct}: {len(stems)}")
        for s in stems:
            print(f"    - {s}")

    # Image-only pages (forms/sheets that returned no text)
    image_only = [r for r in records if r["image_only"]]
    if image_only:
        print(f"\n⚠ IMAGE-ONLY pages ({len(image_only)}) — model returned only image refs, no text:")
        for r in image_only:
            print(f"  - {r['stem']} ({r['elapsed_sec']:.1f}s)")

    # Nav detritus (sidebar TOC leaked into output)
    nav_pages = [r for r in records if r["nav_detritus"]]
    if nav_pages:
        print(f"\n⚠ Nav/sidebar detritus detected ({len(nav_pages)} pages):")
        for r in nav_pages:
            print(f"  - {r['stem']}")

    # Table analysis
    print("\n" + "-" * 60)
    print("Table Extraction")
    print("-" * 60)
    pages_with_tables = [r for r in records if r["table_count"] > 0]
    print(f"Pages with tables: {len(pages_with_tables)}/{len(records)}")
    for r in sorted(pages_with_tables, key=lambda x: -x["table_count"]):
        print(f"  {r['stem']}: {r['table_count']} table(s), {r['table_rows_total']} total rows")

    # result_type analysis — DeepSeek returns None (falls back to result.mmd)
    result_types = {}
    for r in records:
        rt = r["result_type"]
        result_types[rt] = result_types.get(rt, 0) + 1
    print(f"\nResult types: {result_types}")

    # Per-page detail table
    print("\n" + "-" * 60)
    print(f"{'Stem':<40} {'Time':>6} {'Lines':>6} {'Chars':>7} {'Hdgs':>5} {'Tbls':>5} {'Imgs':>5} {'Type'}")
    print("-" * 60)
    for r in sorted(records, key=lambda x: x["stem"]):
        print(
            f"{r['stem']:<40} {r['elapsed_sec']:6.1f} {r['non_empty_lines']:6} "
            f"{r['char_count']:7} {r['heading_count']:5} {r['table_count']:5} "
            f"{r['image_ref_count']:5} {r['content_type']}"
        )

    # Stat-signal coverage
    print("\n" + "-" * 60)
    print("Stat-block signal coverage")
    print("-" * 60)
    stat_pages = [r for r in records if r["stat_signals"]]
    for r in stat_pages:
        print(f"  {r['stem']}: {', '.join(r['stat_signals'])}")

    # LaTeX fragments
    latex_pages = [r for r in records if r["latex_frag_count"] > 0]
    if latex_pages:
        print(f"\nPages with LaTeX fragments ({len(latex_pages)}):")
        for r in latex_pages:
            print(f"  {r['stem']}: {r['latex_frag_count']} fragments")

    print("\n" + "=" * 80)
    print("Analysis complete.")


if __name__ == "__main__":
    main()
