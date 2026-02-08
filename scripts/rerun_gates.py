#!/usr/bin/env python3
"""
Rerun Stage B gates on existing extraction output.

No OCR or parsing — loads stageA.surface.ast.json and stageB.evidence_units.json,
reruns gates (including image+caption orphan exemption), and updates artifacts.

For orphans that are not image+caption pages: calls LLM to assign a heading,
updates units with structural_path=[heading], then reruns gates (which pass).

Usage (from RulesIngestion root):
  uv run python scripts/rerun_gates.py [EVAL_DIR]

  EVAL_DIR defaults to: out/mark3_evaluation/DnD5eBrutalChapters

  Requires OPENAI_API_KEY for LLM orphan header assignment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import blake3

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.gates_b import run_stage_b_gates
from extraction.orphan_header import (
    discover_orphans,
    is_image_and_caption_only_ast,
    run_orphan_header_pass,
)
from extraction.schemas import EvidenceUnit

DEFAULT_EVAL_DIR = REPO_ROOT / "out" / "mark3_evaluation" / "DnD5eBrutalChapters"


def _load_env_development() -> None:
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


def _parse_page_number(dir_name: str) -> int | None:
    m = re.search(r"_p(\d+)$", dir_name)
    return int(m.group(1)) if m else None


def _recompute_unit_id(text: str, structural_path: list[str]) -> str:
    path_str = " > ".join(structural_path)
    return blake3.blake3(f"{text}|{path_str}".encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rerun Stage B gates on existing extraction")
    parser.add_argument(
        "eval_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_EVAL_DIR,
        help=f"Evaluation dir (default: {DEFAULT_EVAL_DIR})",
    )
    args = parser.parse_args()
    eval_dir = args.eval_dir if args.eval_dir.is_absolute() else REPO_ROOT / args.eval_dir

    if not eval_dir.exists():
        print(f"Eval dir not found: {eval_dir}", file=sys.stderr)
        sys.exit(1)

    _load_env_development()

    page_dirs = sorted(
        (d for d in eval_dir.iterdir() if d.is_dir() and _parse_page_number(d.name) is not None),
        key=lambda d: _parse_page_number(d.name) or 0,
    )

    # Orphan header pass: call LLM for orphans that are not image+caption
    orphans = discover_orphans(eval_dir)
    assigned_by_label: dict[str, str] = {}
    if orphans and os.environ.get("OPENAI_API_KEY"):
        try:
            results = run_orphan_header_pass(eval_dir)
            for r in results:
                if r.get("status") == "assigned" and r.get("heading"):
                    assigned_by_label[r["label"]] = r["heading"]
                    print(f"[LLM] {r['label']} → {r['heading']!r}")
        except Exception as e:
            print(f"Orphan header pass failed: {e}", file=sys.stderr)

    # Update units with assigned headings, then run gates
    for page_dir in page_dirs:
        units_path = page_dir / "stageB.evidence_units.json"
        if page_dir.name in assigned_by_label and units_path.exists():
            heading = assigned_by_label[page_dir.name]
            stage_b_data = json.loads(units_path.read_text(encoding="utf-8"))
            units_raw = stage_b_data.get("units", [])
            path = [heading]
            updated_units = []
            for u in units_raw:
                unit = EvidenceUnit.from_dict(u)
                new_unit = EvidenceUnit(
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
                )
                updated_units.append(new_unit.to_dict())
            stage_b_data["units"] = updated_units
            units_path.write_text(
                json.dumps(stage_b_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    updated = 0
    for page_dir in page_dirs:
        ast_path = page_dir / "stageA.surface.ast.json"
        units_path = page_dir / "stageB.evidence_units.json"
        summary_path = page_dir / "pipeline_summary.json"

        if not ast_path.exists() or not units_path.exists():
            continue

        ast_data = json.loads(ast_path.read_text(encoding="utf-8"))
        stage_b_data = json.loads(units_path.read_text(encoding="utf-8"))
        units = [EvidenceUnit.from_dict(u) for u in stage_b_data.get("units", [])]

        page_num = _parse_page_number(page_dir.name) or 0
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
            summary["all_gates_passed"] = (summary.get("stage_a", {}).get("gates_passed", False) and gates_passed)
            summary_path.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        updated += 1
        status = "PASS" if gates_passed else "FAIL"
        orphan_gate = next((g for g in diagnostics if g.gate_name == "orphan"), None)
        orphan_note = f" orphan={orphan_gate.detail.get('note', '')}" if orphan_gate and orphan_gate.passed and orphan_gate.detail.get("note") else ""
        print(f"{page_dir.name}: {status}{orphan_note}")

    print(f"\nUpdated {updated} page(s)")


if __name__ == "__main__":
    main()
