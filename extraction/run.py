"""
Stage A CLI: PDF → MarkerStream → Chunk[] → output JSON.

Document identity (A-DOC): one Logical Document per (ruleset_id, book_id); provenance on every Chunk.
Usage: uv run python -m extraction.run <pdf_path> --doc-id <id> --output-dir <dir> [--check-gates]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from extraction.chunker import ExtractionResult, stream_to_chunks
from extraction.document_identity import (
    build_logical_document_multi_pdf,
    build_logical_document_single_pdf,
    pdf_content_hash,
)
from extraction.gates import gates_report_to_dict, run_gates
from extraction.marker_runner import (
    load_marker_json,
    raw_to_blocks,
    run_marker,
    blocks_to_marker_stream,
)
from extraction.normalize import is_structural_container
from extraction.serialize import chunkset_hash, markerstream_hash
from extraction.schemas import MarkerBlock


def _pdfs_in_folder(folder: Path) -> list[Path]:
    """Return all PDFs in folder (direct children only), sorted by name for deterministic order."""
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")
    pdfs = sorted(folder.glob("*.pdf"), key=lambda p: p.name)
    return pdfs


def _pdf_page_count_from_metadata(pdf_path: Path) -> int | None:
    """Return page count from PDF metadata if pypdf is available; else None. No required dependency."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(pdf_path)
        return len(reader.pages)
    except Exception:
        return None


def _log(msg: str) -> None:
    """Progress message to terminal (flush so output appears immediately)."""
    print(msg, flush=True)


def _infer_num_pages(blocks: list[dict]) -> int:
    """Infer page count from block 'page' fields. Fallback when PDF metadata unavailable. Returns at least 1 if blocks non-empty."""
    num_pages = 0
    for b in blocks:
        p = b.get("page")
        if p is not None:
            try:
                num_pages = max(num_pages, int(p) + 1)
            except (TypeError, ValueError):
                pass
    return num_pages if num_pages > 0 else (1 if blocks else 0)


def _split_structural_blocks(
    marker_stream: list[MarkerBlock],
) -> tuple[list[MarkerBlock], list[MarkerBlock]]:
    """Return (content_blocks, structural_blocks) based on raw block type."""
    structural = [b for b in marker_stream if is_structural_container(b.raw_block_type)]
    content = [b for b in marker_stream if not is_structural_container(b.raw_block_type)]
    return content, structural


def run_extraction(
    pdf_path: Path | None = None,
    output_dir: Path | None = None,
    doc_id: str | None = None,
    ruleset_id: str | None = None,
    book_id: str | None = None,
    check_gates: bool = False,
    pdf_paths: list[Path] | None = None,
) -> ExtractionResult:
    """
    Run Stage A: Marker → Logical Document + DocumentPart(s) → MarkerStream → Chunk[] + DropRecords.
    Writes logical_document.json, marker_stream.json, chunks.json, drop_records.json, optional metrics.json.
    A-DOC-INV-1: one Logical Document per (ruleset_id, book_id). A-DOC-INV-4: provenance on every Chunk.

    Single-PDF: pass pdf_path (and optionally output_dir, doc_id). Multi-PDF: pass pdf_paths (list)
    and output_dir, doc_id. When pdf_paths has more than one path, builds one logical document from
    multiple parts and wires provenance for each part.
    """
    paths: list[Path] = list(pdf_paths) if pdf_paths else ([Path(pdf_path)] if pdf_path else [])
    if not paths:
        raise ValueError("Provide pdf_path or pdf_paths")
    if output_dir is None:
        raise ValueError("output_dir is required")
    if doc_id is None:
        doc_id = paths[0].stem
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        p_resolved = Path(p).resolve()
        if not p_resolved.exists():
            raise FileNotFoundError(f"PDF not found: {p_resolved}")

    ruleset_id = ruleset_id or doc_id
    book_id = book_id or doc_id

    _log(f"[extraction] Starting: {len(paths)} PDF(s) → {output_dir}")
    if len(paths) == 1:
        return _run_single(paths[0], output_dir, doc_id, ruleset_id, book_id, check_gates)
    return _run_multi(paths, output_dir, doc_id, ruleset_id, book_id, check_gates)


def _run_single(
    pdf_path: Path,
    output_dir: Path,
    doc_id: str,
    ruleset_id: str,
    book_id: str,
    check_gates: bool,
) -> ExtractionResult:
    """Single-PDF path: one LogicalDocument, one DocumentPart."""
    source_pdf_id = Path(pdf_path).stem
    _log(f"[extraction] Running Marker on {pdf_path.name} ...")
    marker_dir = run_marker(pdf_path, output_dir)
    raw = load_marker_json(marker_dir)
    blocks = raw_to_blocks(raw)
    num_pages = _pdf_page_count_from_metadata(pdf_path) or _infer_num_pages(blocks)
    pdf_hash = pdf_content_hash(pdf_path)
    logical_doc, document_part = build_logical_document_single_pdf(
        ruleset_id=ruleset_id,
        book_id=book_id,
        source_pdf_id=source_pdf_id,
        pdf_hash=pdf_hash,
        num_pages=num_pages,
    )
    _log("[extraction] Building marker stream and chunks ...")
    marker_stream = blocks_to_marker_stream(blocks, doc_id, document_part)
    content_stream, structural_blocks = _split_structural_blocks(marker_stream)
    result = stream_to_chunks(content_stream, logical_doc.logical_doc_id)
    _log("[extraction] Writing outputs ...")
    _write_outputs(output_dir, logical_doc, result, check_gates, structural_blocks)
    _log("[extraction] Done.")
    return result


def _run_multi(
    pdf_paths: list[Path],
    output_dir: Path,
    doc_id: str,
    ruleset_id: str,
    book_id: str,
    check_gates: bool,
) -> ExtractionResult:
    """Multi-PDF path: one LogicalDocument, one DocumentPart per PDF; combined MarkerStream."""
    total = len(pdf_paths)
    _log(f"[extraction] Multi-PDF: {total} file(s).")
    parts_spec: list[tuple[str, str, int]] = []
    all_blocks: list[list[dict]] = []

    for i, p in enumerate(pdf_paths):
        _log(f"[extraction] Processing PDF {i + 1}/{total}: {p.name} ...")
        part_out = output_dir / f"part_{i}_{p.stem}"
        marker_dir = run_marker(p, part_out)
        raw = load_marker_json(marker_dir)
        blocks = raw_to_blocks(raw)
        num_pages = _pdf_page_count_from_metadata(p) or _infer_num_pages(blocks)
        pdf_hash = pdf_content_hash(p)
        source_pdf_id = p.stem
        parts_spec.append((source_pdf_id, pdf_hash, num_pages))
        all_blocks.append(blocks)

    _log("[extraction] Building logical document and merging streams ...")
    # Preserve input order so document_parts[i] matches all_blocks[i] (avoids provenance mismatch).
    logical_doc, document_parts = build_logical_document_multi_pdf(
        ruleset_id=ruleset_id,
        book_id=book_id,
        parts_spec=parts_spec,
        part_order=list(range(len(parts_spec))),
    )

    stream_parts: list[list] = []
    for blocks_i, part in zip(all_blocks, document_parts):
        stream_parts.append(blocks_to_marker_stream(blocks_i, logical_doc.logical_doc_id, part))

    marker_stream = _merge_marker_streams(stream_parts)
    _log("[extraction] Chunking ...")
    content_stream, structural_blocks = _split_structural_blocks(marker_stream)
    result = stream_to_chunks(content_stream, logical_doc.logical_doc_id)
    _log("[extraction] Writing outputs ...")
    _write_outputs(output_dir, logical_doc, result, check_gates, structural_blocks)
    _log("[extraction] Done.")
    return result


def _merge_marker_streams(streams: list[list]) -> list:
    """Merge per-part MarkerStreams into one, sorted by logical_page_index, then bbox, block_ordinal."""
    from extraction.schemas import MarkerBlock

    combined: list[MarkerBlock] = []
    for s in streams:
        combined.extend(s)
    combined.sort(
        key=lambda b: (
            b.logical_page_index if b.logical_page_index >= 0 else b.page_index,
            b.bbox[1] if b.bbox else 0.0,
            b.bbox[0] if b.bbox else 0.0,
            b.block_ordinal,
        )
    )
    return combined


def _write_outputs(
    output_dir: Path,
    logical_doc,
    result: ExtractionResult,
    check_gates: bool,
    structural_blocks: list[MarkerBlock] | None = None,
) -> None:
    """Write logical_document.json, marker_stream, chunks, drop_records, metrics, optional structural_blocks."""
    def write_json(name: str, data: list[dict] | dict) -> None:
        path = output_dir / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    write_json("logical_document.json", logical_doc.to_dict())
    write_json(
        "marker_stream.json",
        [b.to_dict() for b in result.marker_stream],
    )
    write_json(
        "chunks.json",
        [c.to_dict() for c in result.chunks],
    )
    write_json(
        "drop_records.json",
        [d.to_dict() for d in result.drop_records],
    )
    # Structural side-channel: containers (Page, etc.) + empty content (TableCell/Text with no text) for markdown reconstruction.
    containers = (structural_blocks or []) if structural_blocks is not None else []
    empty_content = getattr(result, "empty_structural_blocks", None) or []
    if containers or empty_content:
        write_json(
            "structural_blocks.json",
            {
                "containers": [b.to_dict() for b in containers],
                "empty_content": [b.to_dict() for b in empty_content],
            },
        )
    metrics: dict = {
        "markerstream_hash": markerstream_hash(result.marker_stream),
        "chunkset_hash": chunkset_hash(result.chunks),
    }
    if check_gates:
        empty_count = len(getattr(result, "empty_structural_blocks", None) or [])
        report = run_gates(
            result.marker_stream,
            result.chunks,
            result.drop_records,
            empty_structural_count=empty_count,
        )
        metrics["gates"] = gates_report_to_dict(report)
        if not report.passed:
            sys.exit(1)
    write_json("metrics.json", metrics)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage A: PDF → MarkerStream → Chunk[]. Single PDF or multi-PDF (one logical doc)."
    )
    parser.add_argument(
        "pdf_path",
        type=Path,
        nargs="?",
        default=None,
        help="Path to single PDF (omit if using --pdfs or --folder)",
    )
    parser.add_argument(
        "--pdfs",
        type=Path,
        nargs="+",
        default=None,
        help="Multiple PDFs to build one logical document (ruleset_id + book_id)",
    )
    parser.add_argument(
        "--folder",
        type=Path,
        default=None,
        metavar="DIR",
        help="Directory containing PDFs; all *.pdf (direct children) become one logical document",
    )
    parser.add_argument("--doc-id", default=None, help="Stable document identifier (default: from path or folder name)")
    parser.add_argument("--output-dir", required=True, type=Path, help="Output directory")
    parser.add_argument("--ruleset-id", default=None, help="Optional ruleset namespace")
    parser.add_argument("--book-id", default=None, help="Optional book namespace")
    parser.add_argument("--check-gates", action="store_true", help="Run gates and exit non-zero if any fail")
    args = parser.parse_args()

    if args.folder is not None:
        paths = _pdfs_in_folder(args.folder)
        if not paths:
            parser.error(f"No PDFs found in folder: {args.folder}")
        doc_id = args.doc_id or args.folder.name
    elif args.pdfs:
        paths = list(args.pdfs)
        doc_id = args.doc_id or (paths[0].stem if paths else None)
    elif args.pdf_path is not None:
        paths = [args.pdf_path]
        doc_id = args.doc_id or paths[0].stem
    else:
        parser.error("Provide pdf_path, --pdfs, or --folder")
    if not doc_id:
        parser.error("--doc-id is required when using --pdfs with multiple paths")
    run_extraction(
        pdf_path=paths[0] if len(paths) == 1 else None,
        output_dir=args.output_dir,
        doc_id=doc_id,
        ruleset_id=args.ruleset_id,
        book_id=args.book_id,
        check_gates=args.check_gates,
        pdf_paths=paths if len(paths) != 1 else None,
    )


if __name__ == "__main__":
    main()
