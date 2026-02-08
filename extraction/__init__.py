"""
Mark III Extraction Pipeline — Prose Reconstruction and Evidence Binding.

Stage A: PDF page → DeepSeek OCR → raw markdown → SurfaceAST → gates.
Stage B: SurfaceAST → EvidenceUnits → gates.

To run the archived Marker-era pipeline from repo root:
  PYTHONPATH=Archive/marker-era uv run python -m extraction.run <pdf_path> --output-dir <dir> ...
"""

from extraction.schemas import (
    EvidenceUnit,
    GateDiagnostic,
    PageFingerprint,
    StageARecord,
    SurfaceAST,
    SurfaceASTNode,
)

__all__ = [
    "EvidenceUnit",
    "GateDiagnostic",
    "PageFingerprint",
    "StageARecord",
    "SurfaceAST",
    "SurfaceASTNode",
]
