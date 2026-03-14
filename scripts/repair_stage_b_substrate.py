#!/usr/bin/env python3
from __future__ import annotations

import argparse
import blake3
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from extraction.gates_b import run_stage_b_gates
from extraction.schemas import EvidenceUnit
from extraction.unit_identity import compute_evidence_unit_id


def _page_sort_key(page_dir: Path) -> tuple[str, int, str]:
    match = re.search(r"_p(\d+)$", page_dir.name)
    page_num = int(match.group(1)) if match else -1
    return (page_dir.parent.name, page_num, page_dir.name)


def _load_page_dirs(substrate_root: Path) -> list[Path]:
    return sorted(
        {
            units_file.parent
            for units_file in substrate_root.rglob("stageB.evidence_units.json")
            if units_file.parent.is_dir()
        },
        key=_page_sort_key,
    )


def _recompute_unit(unit: EvidenceUnit) -> EvidenceUnit:
    return EvidenceUnit(
        unit_id=compute_evidence_unit_id(
            text=unit.text,
            structural_path=list(unit.structural_path),
            page_fingerprint=unit.page_fingerprint,
            source_line_start=unit.source_line_start,
            source_line_end=unit.source_line_end,
            unit_type=unit.unit_type,
        ),
        unit_type=unit.unit_type,
        text=unit.text,
        structural_path=list(unit.structural_path),
        ordering_key=unit.ordering_key,
        page_fingerprint=unit.page_fingerprint,
        content_hash=unit.content_hash,
        source_line_start=unit.source_line_start,
        source_line_end=unit.source_line_end,
        anomaly_flags=list(unit.anomaly_flags),
        content_version=unit.content_version,
        page_fingerprints=list(unit.page_fingerprints),
        table_group_id=unit.table_group_id,
        join_metadata=dict(unit.join_metadata) if unit.join_metadata else None,
        source_unit_ids=list(unit.source_unit_ids),
    )


def _normalize_unit_text(unit: EvidenceUnit) -> EvidenceUnit | None:
    text = unit.text
    if unit.unit_type == "table":
        open_count = len(re.findall(r"<table\b", text, flags=re.IGNORECASE))
        close_count = len(re.findall(r"</table>", text, flags=re.IGNORECASE))
        row_count = len(re.findall(r"<tr\b", text, flags=re.IGNORECASE))
        if open_count == close_count + 1 and row_count > 0:
            unit.text = text + "</table>"
            unit.content_hash = blake3.blake3(unit.text.encode("utf-8")).hexdigest()
        return unit

    text_len = len(text)
    if text_len > 5000 and "<|ref|>" in text:
        return None
    return unit


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair persisted Stage B units and gate artifacts in-place.")
    parser.add_argument("substrate_path", type=Path, help="Root substrate directory (for example out/DnD_PHB_5.5)")
    args = parser.parse_args()

    substrate_root = args.substrate_path.resolve()
    page_dirs = _load_page_dirs(substrate_root)
    if not page_dirs:
        raise SystemExit(f"No Stage B page directories found under {substrate_root}")

    pages_processed = 0
    units_rewritten = 0
    ids_changed = 0
    units_dropped = 0

    for page_dir in page_dirs:
        units_path = page_dir / "stageB.evidence_units.json"
        ast_path = page_dir / "stageA.surface.ast.json"
        if not units_path.exists() or not ast_path.exists():
            continue

        stage_b_payload = json.loads(units_path.read_text(encoding="utf-8"))
        units = [EvidenceUnit.from_dict(item) for item in stage_b_payload.get("units", [])]
        if not units:
            continue

        normalized_units: list[EvidenceUnit] = []
        for unit in units:
            normalized = _normalize_unit_text(unit)
            if normalized is None:
                units_dropped += 1
                continue
            normalized_units.append(normalized)

        rewritten_units = [_recompute_unit(unit) for unit in normalized_units]
        old_to_new = {old.unit_id: new.unit_id for old, new in zip(units, rewritten_units, strict=False)}
        for rewritten in rewritten_units:
            if rewritten.source_unit_ids:
                rewritten.source_unit_ids = [old_to_new.get(uid, uid) for uid in rewritten.source_unit_ids]

        ids_changed += sum(
            1 for old, new in zip(normalized_units, rewritten_units, strict=False) if old.unit_id != new.unit_id
        )
        units_rewritten += len(rewritten_units)

        ast_payload = json.loads(ast_path.read_text(encoding="utf-8"))
        page_match = re.search(r"_p(\d+)$", page_dir.name)
        page_index = int(page_match.group(1)) if page_match else -1
        diagnostics = run_stage_b_gates(
            rewritten_units,
            ast_dict=ast_payload,
            is_standalone=(page_index == 0),
        )
        gates_passed = all(diag.passed for diag in diagnostics)

        stage_b_payload["units"] = [unit.to_dict() for unit in rewritten_units]
        units_path.write_text(json.dumps(stage_b_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        diag_path = page_dir / "stageB.gate_diagnostics.json"
        diag_path.write_text(
            json.dumps([diag.to_dict() for diag in diagnostics], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        summary_path = page_dir / "pipeline_summary.json"
        if summary_path.exists():
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            summary_payload.setdefault("stage_b", {})
            summary_payload["stage_b"]["units"] = [unit.to_dict() for unit in rewritten_units]
            summary_payload["stage_b"]["gates_passed"] = gates_passed
            summary_payload["stage_b"]["gate_details"] = [diag.to_dict() for diag in diagnostics]
            summary_payload["all_gates_passed"] = (
                bool(summary_payload.get("stage_a", {}).get("gates_passed", False)) and gates_passed
            )
            summary_path.write_text(
                json.dumps(summary_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        pages_processed += 1

    print(
        json.dumps(
            {
                "substrate_path": str(substrate_root),
                "pages_processed": pages_processed,
                "units_rewritten": units_rewritten,
                "unit_ids_changed": ids_changed,
                "units_dropped": units_dropped,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
