"""
DeepSeek OCR Worker — subprocess wrapper around the existing local-GPU script.

Delegates inference to ``scripts/run_deepseek_ocr2_venv.sh`` which manages a
dedicated venv with transformers==4.46.x.  This avoids version conflicts with
the main project environment.

Returns a StageARecord for downstream AST parsing.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

import blake3

from extraction.schemas import StageARecord

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_SCRIPT = REPO_ROOT / "scripts" / "run_deepseek_ocr2_venv.sh"

DEFAULT_MODEL_ID = "deepseek-ai/DeepSeek-OCR-2"
DEFAULT_PROMPT = "<image>\n<|grounding|>Convert the document to markdown."
SUBPROCESS_TIMEOUT_SEC = 600  # 10 minutes


def run_ocr(
    pdf_path: Path,
    page_index: int,
    page_fingerprint: str,
    out_dir: Path,
    *,
    timeout: int = SUBPROCESS_TIMEOUT_SEC,
) -> StageARecord:
    """Run DeepSeek OCR on a single PDF page via the venv subprocess.

    Args:
        pdf_path: Absolute path to the source PDF.
        page_index: 0-based page index.
        page_fingerprint: blake3 hex digest of the rendered page image.
        out_dir: Directory for OCR output files.
        timeout: Subprocess timeout in seconds.

    Returns:
        StageARecord with raw markdown and provenance metadata.

    Raises:
        FileNotFoundError: If the venv script is missing.
        RuntimeError: If the subprocess fails or produces no output.
    """
    if not VENV_SCRIPT.is_file():
        raise FileNotFoundError(
            f"DeepSeek venv script not found: {VENV_SCRIPT}\n"
            "Run from the RulesIngestion root directory."
        )

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "bash",
        str(VENV_SCRIPT),
        "--pdf", str(pdf_path.resolve()),
        "--page", str(page_index),
        "--out-dir", str(out_dir),
    ]

    logger.info("OCR subprocess: %s page %d", pdf_path.name, page_index)
    t0 = time.perf_counter()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-500:]
        raise RuntimeError(
            f"DeepSeek OCR failed (exit {result.returncode}) for "
            f"{pdf_path.name} page {page_index}:\n{stderr_tail}"
        )

    # Find the *_ocr.json output produced by the minimal script
    ocr_jsons = list(out_dir.glob("*_ocr.json"))
    if not ocr_jsons:
        raise RuntimeError(
            f"No *_ocr.json found in {out_dir} after OCR run. "
            f"stdout: {(result.stdout or '')[:300]}"
        )

    ocr_json_path = ocr_jsons[0]
    ocr_data = json.loads(ocr_json_path.read_text(encoding="utf-8"))

    raw_markdown = ocr_data.get("markdown", "")
    if not raw_markdown:
        raise RuntimeError(
            f"Empty markdown in {ocr_json_path}. "
            "Check DeepSeek OCR output manually."
        )

    model_id = ocr_data.get("model", DEFAULT_MODEL_ID)
    prompt = ocr_data.get("prompt", DEFAULT_PROMPT)
    inference_sec = ocr_data.get("elapsed_sec", elapsed)
    content_hash = blake3.blake3(raw_markdown.encode("utf-8")).hexdigest()

    logger.info(
        "OCR complete: %s page %d  %.1fs  hash=%s",
        pdf_path.name,
        page_index,
        inference_sec,
        content_hash[:16],
    )

    return StageARecord(
        page_fingerprint=page_fingerprint,
        source_pdf=str(pdf_path.resolve()),
        page_index=page_index,
        model_id=model_id,
        prompt=prompt,
        raw_markdown=raw_markdown,
        inference_elapsed_sec=round(inference_sec, 3),
        content_hash=content_hash,
    )
