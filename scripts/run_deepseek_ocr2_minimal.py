#!/usr/bin/env python3
"""
Minimal DeepSeek OCR 2 runner: one image in, markdown out.

Uses Hugging Face Transformers with eager attention (no flash-attn).

Recommended (avoids transformers version conflict with marker-pdf):
  bash scripts/run_deepseek_ocr2_venv.sh --create-test-image
  bash scripts/run_deepseek_ocr2_venv.sh --image /path/to/page.png
  That script uses a dedicated venv with transformers==4.46.x.

Or in this repo's main env (transformers 4.57; may hit API mismatches):
  uv run python scripts/run_deepseek_ocr2_minimal.py --image /path/to/page.png
  uv run python scripts/run_deepseek_ocr2_minimal.py --create-test-image

Requires: NVIDIA GPU (the model's infer() uses CUDA).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Eager attention only (no flash_attn)
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

# Shims for transformers>=4.47+ compatibility with DeepSeek OCR 2 Hub code.
def _patch_llama_flash_attention() -> None:
    import transformers.models.llama.modeling_llama as llama_mod
    if not hasattr(llama_mod, "LlamaFlashAttention2"):
        llama_mod.LlamaFlashAttention2 = llama_mod.LlamaAttention  # type: ignore[attr-defined]


def _patch_cache_seen_tokens() -> None:
    """DynamicCache in 4.47+ has get_seq_length() but model expects .seen_tokens and .get_max_length()."""
    from transformers.cache_utils import DynamicCache
    if not hasattr(DynamicCache, "seen_tokens"):
        seen_tokens = property(lambda self: self.get_seq_length(0))
        DynamicCache.seen_tokens = seen_tokens  # type: ignore[attr-defined]
    if not hasattr(DynamicCache, "get_max_length"):

        def get_max_length(self: DynamicCache) -> int | None:
            n = self.get_max_cache_shape(0)
            return n if n >= 0 else None

        DynamicCache.get_max_length = get_max_length  # type: ignore[attr-defined]
    if not hasattr(DynamicCache, "get_usable_length"):

        def get_usable_length(self: DynamicCache, seq_length: int) -> int:
            return self.get_seq_length(0)

        DynamicCache.get_usable_length = get_usable_length  # type: ignore[attr-defined]


def create_test_image(out_path: Path) -> Path:
    """Create a small PNG with text for smoke testing (no external image needed)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise SystemExit("Pillow required for --create-test-image. Install with: uv add pillow") from None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Simple 400x150 image with text
    img = Image.new("RGB", (400, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 50), "Hello DeepSeek OCR 2", fill=(0, 0, 0), font=font)
    draw.text((20, 90), "Minimal smoke test.", fill=(0, 0, 0), font=font)
    img.save(out_path)
    return out_path


def _render_pdf_page(pdf_path: Path, page_index: int, out_path: Path, dpi: int) -> Path:
    """Render a single PDF page to PNG using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise SystemExit(
            "PyMuPDF required for --pdf. Install in the DeepSeek venv with: uv pip install pymupdf"
        ) from None
    if page_index < 0:
        raise SystemExit("--page must be >= 0")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    if page_index >= len(doc):
        raise SystemExit(f"--page {page_index} out of range (max {len(doc) - 1})")
    page = doc.load_page(page_index)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(out_path.as_posix())
    return out_path


def _json_safe(obj: object) -> object:
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return repr(obj)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeepSeek OCR 2 on a single image (minimal, no PDF)."
    )
    parser.add_argument("--image", type=Path, help="Path to image (e.g. .png, .jpg)")
    parser.add_argument("--pdf", type=Path, help="Path to PDF (renders one page to image)")
    parser.add_argument(
        "--page",
        type=int,
        default=0,
        help="PDF page index (0-based; default: 0)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Render DPI when using --pdf (default: 200)",
    )
    parser.add_argument(
        "--create-test-image",
        action="store_true",
        help="Create a small test image and run OCR on it (no --image needed)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out/deepseek_ocr2_minimal"),
        help="Output directory (default: out/deepseek_ocr2_minimal)",
    )
    parser.add_argument(
        "--device",
        choices=("cuda", "cpu"),
        default="cuda",
        help="Device (default: cuda)",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="<image>\n<|grounding|>Convert the document to markdown.",
        help="Prompt (default: grounding markdown)",
    )
    args = parser.parse_args()

    if args.create_test_image:
        out_base = args.out_dir.resolve()
        test_img = out_base / "test_input.png"
        print(f"Creating test image: {test_img}")
        image_path = create_test_image(test_img)
        source_pdf = None
        source_page = None
    elif args.pdf:
        pdf_path = args.pdf.resolve()
        if not pdf_path.exists():
            print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
            sys.exit(1)
        out_base = args.out_dir.resolve()
        rendered = out_base / f"{pdf_path.stem}_p{args.page}.png"
        print(f"Rendering PDF page {args.page} to image: {rendered}")
        image_path = _render_pdf_page(pdf_path, args.page, rendered, args.dpi)
        source_pdf = pdf_path
        source_page = args.page
    elif args.image:
        image_path = args.image.resolve()
        if not image_path.exists():
            print(f"Error: image not found: {image_path}", file=sys.stderr)
            sys.exit(1)
        source_pdf = None
        source_page = None
    else:
        print("Error: provide --image PATH, --pdf PATH, or --create-test-image", file=sys.stderr)
        sys.exit(1)

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.device == "cpu":
        print(
            "Error: CPU mode is not supported. DeepSeek OCR 2 infer() uses CUDA; use --device cuda.",
            file=sys.stderr,
        )
        sys.exit(1)

    _patch_llama_flash_attention()
    _patch_cache_seen_tokens()

    import torch
    from transformers import AutoModel, AutoTokenizer

    model_name = "deepseek-ai/DeepSeek-OCR-2"
    use_cuda = args.device == "cuda" and torch.cuda.is_available()
    if args.device == "cuda" and not use_cuda:
        print(
            "Error: CUDA requested but not available. The model's infer() hardcodes .cuda(); use an NVIDIA GPU.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Loading tokenizer and model: {model_name} (eager attention)...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_name,
        _attn_implementation="eager",
        trust_remote_code=True,
        use_safetensors=True,
        torch_dtype=torch.bfloat16 if use_cuda else torch.float32,
    )
    model = model.eval()
    if use_cuda:
        model = model.cuda()

    print(f"Inference on: {image_path}")
    t0 = time.time()
    res = model.infer(
        tokenizer,
        prompt=args.prompt,
        image_file=str(image_path),
        output_path=str(out_dir),
        base_size=1024,
        image_size=768,
        crop_mode=True,
        save_results=True,
    )
    elapsed = time.time() - t0
    print(f"Done in {elapsed:.2f}s")

    # Extract text from result (model may return str, dict, list, or None when save_results=True)
    text: str | None = None
    if isinstance(res, str):
        text = res
    elif isinstance(res, dict):
        for key in ("markdown", "text", "output", "pred", "result"):
            if key in res and isinstance(res[key], str):
                text = res[key]
                break
    elif isinstance(res, list) and res and isinstance(res[0], str):
        text = res[0]
    if text is None and (out_dir / "result.mmd").exists():
        text = (out_dir / "result.mmd").read_text(encoding="utf-8")
    if text is None:
        text = f"[Could not get text from result: {type(res).__name__}]"

    out_md = out_dir / f"{image_path.stem}_ocr.md"
    out_md.write_text(text, encoding="utf-8")
    out_json = out_dir / f"{image_path.stem}_ocr.json"
    out_json.write_text(
        json.dumps(
            {
                "model": model_name,
                "prompt": args.prompt,
                "device": args.device,
                "image_path": str(image_path),
                "source_pdf": str(source_pdf) if source_pdf else None,
                "source_page_index": source_page,
                "elapsed_sec": round(elapsed, 3),
                "output_md": str(out_md),
                "output_mmd": str(out_dir / "result.mmd") if (out_dir / "result.mmd").exists() else None,
                "result_type": type(res).__name__,
                "result_raw": _json_safe(res),
                "markdown": text,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote: {out_md}")
    print(f"Wrote: {out_json}")
    print("---")
    print(text[:2000] + ("..." if len(text) > 2000 else ""))


if __name__ == "__main__":
    main()
