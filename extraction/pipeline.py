"""
Mark III Pipeline — top-level orchestrator for Stage A, Stage B, and Stage A'.

Provides:
  - run_a_only()       — Stage A only (prose reconstruction + gates)
  - run_a_b()          — Stage A + Stage B (segmentation + evidence binding)
  - run_a_b_aprime()   — Stage A + Stage B + Stage A' (enrichment for retrieval)
  - run_stage_b_on_result() — Stage B from a pre-existing StageAResult

Each function writes all artifacts to the output directory and returns
structured results for programmatic inspection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from extraction.cross_page_join import run_join_pass
from extraction.gates_b import (
    gate_cross_page_join_rate,
    run_join_conservation_gates,
    run_stage_b_gates,
)
from extraction.schemas import EvidenceUnit
from extraction.stage_a import StageAResult, run_stage_a
from extraction.stage_a_prime import StageAPrimeResult, run_stage_a_prime
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


def run_join_pass_and_gate(
    units_by_page: list[list[EvidenceUnit]],
) -> tuple[list[EvidenceUnit], list[Any]]:
    """R3: Run cross-page join pass on units by page, then run cross_page_join gate.

    Returns joined units and join diagnostics (rate + conservation gates).
    """
    joined = run_join_pass(units_by_page)
    diag = [gate_cross_page_join_rate(joined)] + run_join_conservation_gates(units_by_page, joined)
    return joined, diag


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
    content_version = stage_a_result.record.content_version
    stage_b_result = run_stage_b(stage_a_result.ast, out_dir=None, content_version=content_version)

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


def run_a_b_aprime(
    pdf_path: Path,
    page_index: int,
    out_dir: Path,
    *,
    book_id: str | None = None,
    dpi: int = 200,
    skip_ocr: bool = False,
    raw_markdown_override: str | None = None,
    model: str = "gpt-5-mini",
    openai_client: Any | None = None,
    concurrency: int = 10,
) -> dict[str, Any]:
    """Run Stage A + Stage B + Stage A' on a single page.

    Stage A' enriches EvidenceUnits with retrieval-only annotations (non-evidence).
    """
    out_dir = Path(out_dir).resolve()
    bid = book_id or pdf_path.stem

    combined = run_a_b(
        pdf_path,
        page_index,
        out_dir,
        dpi=dpi,
        skip_ocr=skip_ocr,
        raw_markdown_override=raw_markdown_override,
    )

    units_raw = combined.get("stage_b", {}).get("units", [])
    if not units_raw:
        logger.info("Stage A': no units to enrich (page %d)", page_index)
        combined["stage_a_prime"] = {
            "enrichments": {},
            "gates_passed": True,
            "gate_details": [],
            "run_manifest": {},
        }
        return combined

    units = [EvidenceUnit.from_dict(u) for u in units_raw]
    a_prime_result = run_stage_a_prime(
        units,
        out_dir,
        book_id=bid,
        model=model,
        openai_client=openai_client,
        concurrency=concurrency,
    )

    enrichments_dict = {
        uid: enr.model_dump()
        for uid, enr in a_prime_result.enrichments
    }
    write_stage_a_prime_artifacts(out_dir, a_prime_result)

    combined["stage_a_prime"] = {
        "enrichments": enrichments_dict,
        "gates_passed": a_prime_result.gates_passed,
        "gate_details": [g.to_dict() for g in a_prime_result.gate_diagnostics],
        "run_manifest": a_prime_result.run_manifest,
    }
    combined["all_gates_passed"] = (
        combined["all_gates_passed"] and a_prime_result.gates_passed
    )

    logger.info(
        "Pipeline A+B+A' complete: %s page %d  A'=%s",
        pdf_path.name,
        page_index,
        "PASS" if a_prime_result.gates_passed else "FAIL",
    )
    return combined


def write_stage_a_prime_artifacts(out_dir: Path, result: StageAPrimeResult) -> None:
    """Write Stage A' output artifacts (enrichments, run manifest, gate diagnostics)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    enrichments_dict = {
        uid: enr.model_dump()
        for uid, enr in result.enrichments
    }

    enrich_path = out_dir / "stageAPrime.enrichments.json"
    enrich_path.write_text(
        json.dumps(enrichments_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest_path = out_dir / "stageAPrime.run_manifest.json"
    manifest_path.write_text(
        json.dumps(result.run_manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    diag_path = out_dir / "stageAPrime.gate_diagnostics.json"
    diag_path.write_text(
        json.dumps(
            [g.to_dict() for g in result.gate_diagnostics],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    logger.info("Stage A' artifacts written to %s", out_dir)


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
