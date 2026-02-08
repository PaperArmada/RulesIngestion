"""
Stage A Orchestrator — Prose Reconstruction.

Chains: PageSourceManager → OCR Worker → AST Parser → Gates → Artifact Writing.

Produces per-page:
  - stageA.page.json     (raw model envelope)
  - stageA.surface.md    (verbatim markdown copy)
  - stageA.surface.ast.json  (deterministic structural AST)
  - stageA.gate_diagnostics.json  (gate results)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extraction.ast_parser import parse_markdown_to_ast
from extraction.gates_a import run_stage_a_gates
from extraction.ocr_worker import run_ocr
from extraction.page_source import render_page
from extraction.schemas import (
    GateDiagnostic,
    PageFingerprint,
    StageARecord,
    SurfaceAST,
)

logger = logging.getLogger(__name__)


@dataclass
class StageAResult:
    """Complete output of a Stage A run for one page."""

    fingerprint: PageFingerprint
    record: StageARecord
    ast: SurfaceAST
    gate_diagnostics: list[GateDiagnostic] = field(default_factory=list)

    @property
    def gates_passed(self) -> bool:
        return all(g.passed for g in self.gate_diagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint.to_dict(),
            "record": self.record.to_dict(),
            "ast": self.ast.to_dict(),
            "gate_diagnostics": [g.to_dict() for g in self.gate_diagnostics],
            "gates_passed": self.gates_passed,
        }


def run_stage_a(
    pdf_path: Path,
    page_index: int,
    out_dir: Path,
    *,
    dpi: int = 200,
    skip_ocr: bool = False,
    raw_markdown_override: str | None = None,
) -> StageAResult:
    """Execute the full Stage A pipeline for a single page.

    Args:
        pdf_path: Path to the source PDF.
        page_index: 0-based page index.
        out_dir: Output directory for all artifacts.
        dpi: Render resolution for the page image.
        skip_ocr: If True, skip OCR and use *raw_markdown_override* instead.
            Useful for testing the AST parser on pre-existing OCR output.
        raw_markdown_override: Pre-existing raw markdown (requires skip_ocr=True).

    Returns:
        StageAResult with all artifacts and gate diagnostics.
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Render page image and compute fingerprint
    logger.info("Stage A: rendering %s page %d", pdf_path.name, page_index)
    fingerprint = render_page(pdf_path, page_index, out_dir, dpi=dpi)

    # 2. Run DeepSeek OCR (or use override)
    if skip_ocr and raw_markdown_override is not None:
        import blake3

        content_hash = blake3.blake3(
            raw_markdown_override.encode("utf-8")
        ).hexdigest()
        record = StageARecord(
            page_fingerprint=fingerprint.fingerprint,
            source_pdf=str(pdf_path.resolve()),
            page_index=page_index,
            model_id="override",
            prompt="",
            raw_markdown=raw_markdown_override,
            inference_elapsed_sec=0.0,
            content_hash=content_hash,
        )
    else:
        ocr_out_dir = out_dir / "ocr_raw"
        record = run_ocr(
            pdf_path,
            page_index,
            fingerprint.fingerprint,
            ocr_out_dir,
        )

    # 3. Parse raw markdown into SurfaceAST
    ast = parse_markdown_to_ast(record.raw_markdown, fingerprint.fingerprint)

    # 4. Run gates
    diagnostics = run_stage_a_gates(record.raw_markdown, ast)

    result = StageAResult(
        fingerprint=fingerprint,
        record=record,
        ast=ast,
        gate_diagnostics=diagnostics,
    )

    # 5. Write artifacts
    _write_artifacts(out_dir, result)

    logger.info(
        "Stage A complete: %s page %d  gates=%s  nodes=%d  tables=%d",
        pdf_path.name,
        page_index,
        "PASS" if result.gates_passed else "FAIL",
        ast.node_count,
        ast.table_count,
    )

    return result


def _write_artifacts(out_dir: Path, result: StageAResult) -> None:
    """Write Stage A output artifacts to disk."""
    # stageA.page.json — raw model envelope
    page_json = out_dir / "stageA.page.json"
    page_json.write_text(
        json.dumps(result.record.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # stageA.surface.md — verbatim markdown copy
    surface_md = out_dir / "stageA.surface.md"
    surface_md.write_text(result.record.raw_markdown, encoding="utf-8")

    # stageA.surface.ast.json — deterministic structural AST
    ast_json = out_dir / "stageA.surface.ast.json"
    ast_json.write_text(
        json.dumps(result.ast.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # stageA.gate_diagnostics.json — gate results
    diag_json = out_dir / "stageA.gate_diagnostics.json"
    diag_json.write_text(
        json.dumps(
            [g.to_dict() for g in result.gate_diagnostics],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    logger.info("Artifacts written to %s", out_dir)
