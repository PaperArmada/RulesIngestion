"""
Mark III Pipeline — top-level orchestrator for Stage A and Stage B.

Provides:
  - run_a_only()       — Stage A only (prose reconstruction + gates)
  - run_a_b()          — Stage A + Stage B (segmentation + evidence binding)
  - run_stage_b_on_result() — Stage B from a pre-existing StageAResult

Each function writes all artifacts to the output directory and returns
structured results for programmatic inspection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from extraction.gates_b import run_stage_b_gates
from extraction.stage_a import StageAResult, run_stage_a
from extraction.stage_b import StageBResult, run_stage_b

logger = logging.getLogger(__name__)


def run_a_only(
    pdf_path: Path,
    page_index: int,
    out_dir: Path,
    *,
    dpi: int = 200,
    skip_ocr: bool = False,
    raw_markdown_override: str | None = None,
) -> StageAResult:
    """Run Stage A only on a single page.

    This is a thin wrapper around stage_a.run_stage_a() for API consistency.
    """
    return run_stage_a(
        pdf_path,
        page_index,
        out_dir,
        dpi=dpi,
        skip_ocr=skip_ocr,
        raw_markdown_override=raw_markdown_override,
    )


def run_stage_b_on_result(
    stage_a_result: StageAResult,
    out_dir: Path,
    *,
    page_index: int = 0,
) -> dict[str, Any]:
    """Run Stage B on a pre-existing StageAResult.

    Called by the sample runner when --stage ab is used.

    Returns a dict with:
      - units: list of EvidenceUnit dicts
      - gates_passed: bool
      - gate_details: list of GateDiagnostic dicts
      - salvage_score: float
    """
    out_dir = Path(out_dir).resolve()

    # Run segmenter
    stage_b_result = run_stage_b(stage_a_result.ast, out_dir=None)

    # Run Stage B gates (pass AST for image+caption exemption, standalone for page 0)
    ast_dict = stage_a_result.ast.to_dict()
    diagnostics = run_stage_b_gates(
        stage_b_result.units,
        ast_dict=ast_dict,
        is_standalone=(page_index == 0),
    )
    stage_b_result.gate_diagnostics = stage_b_result.gate_diagnostics + diagnostics

    # Write artifacts (including gate diagnostics)
    _write_stage_b_artifacts(out_dir, stage_b_result)

    return {
        "units": [u.to_dict() for u in stage_b_result.units],
        "gates_passed": stage_b_result.gates_passed,
        "gate_details": [g.to_dict() for g in stage_b_result.gate_diagnostics],
        "salvage_score": round(stage_b_result.salvage_score, 4),
    }


def run_a_b(
    pdf_path: Path,
    page_index: int,
    out_dir: Path,
    *,
    dpi: int = 200,
    skip_ocr: bool = False,
    raw_markdown_override: str | None = None,
) -> dict[str, Any]:
    """Run Stage A + Stage B on a single page.

    Returns a combined result dict with both stage outputs.
    """
    out_dir = Path(out_dir).resolve()

    # Stage A
    stage_a_result = run_stage_a(
        pdf_path,
        page_index,
        out_dir,
        dpi=dpi,
        skip_ocr=skip_ocr,
        raw_markdown_override=raw_markdown_override,
    )

    # Stage B
    stage_b_dict = run_stage_b_on_result(stage_a_result, out_dir, page_index=page_index)

    combined = {
        "stage_a": {
            "gates_passed": stage_a_result.gates_passed,
            "node_count": stage_a_result.ast.node_count,
            "table_count": stage_a_result.ast.table_count,
            "content_hash": stage_a_result.ast.content_hash,
            "gate_details": [g.to_dict() for g in stage_a_result.gate_diagnostics],
        },
        "stage_b": stage_b_dict,
        "all_gates_passed": (
            stage_a_result.gates_passed and stage_b_dict["gates_passed"]
        ),
    }

    # Write combined summary
    summary_path = out_dir / "pipeline_summary.json"
    summary_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "Pipeline A+B complete: %s page %d  A=%s B=%s salvage=%.2f",
        pdf_path.name,
        page_index,
        "PASS" if stage_a_result.gates_passed else "FAIL",
        "PASS" if stage_b_dict["gates_passed"] else "FAIL",
        stage_b_dict["salvage_score"],
    )

    return combined


def _write_stage_b_artifacts(out_dir: Path, result: StageBResult) -> None:
    """Write Stage B output artifacts including gate diagnostics."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # stageB.evidence_units.json
    units_path = out_dir / "stageB.evidence_units.json"
    units_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # stageB.gate_diagnostics.json
    diag_path = out_dir / "stageB.gate_diagnostics.json"
    diag_path.write_text(
        json.dumps(
            [g.to_dict() for g in result.gate_diagnostics],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    logger.info("Stage B artifacts written to %s", out_dir)
