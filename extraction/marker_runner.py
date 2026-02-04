"""
Run Marker and produce MarkerStream (A1).

Invokes Marker CLI, flattens tree or blocks, assigns doc_id/page_index/block_ordinal,
sorts by page_index, y_min, x_min, block_ordinal. Deterministic.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from extraction.normalize import extract_text_from_html
from extraction.schemas import DocumentPart, MarkerBlock


def run_marker(pdf_path: Path, output_dir: Path, output_format: str = "json") -> Path:
    """Run Marker CLI on PDF. Returns path to Marker output directory."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "marker_single",
        str(Path(pdf_path).resolve()),
        "--output_dir",
        str(output_dir),
        "--output_format",
        output_format,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Marker failed: {result.stderr or result.stdout}")
    pdf_name = Path(pdf_path).stem
    marker_out = output_dir / pdf_name
    if not marker_out.exists():
        for sub in output_dir.iterdir():
            if sub.is_dir() and pdf_name in sub.name:
                return sub
    return marker_out if marker_out.exists() else output_dir


def load_marker_json(marker_dir: Path) -> Any:
    """Load first non-meta JSON file from Marker output directory."""
    marker_dir = Path(marker_dir)
    for f in sorted(marker_dir.iterdir()):
        if f.suffix == ".json" and "_meta" not in f.name:
            with open(f, "r", encoding="utf-8") as fp:
                return json.load(fp)
    raise FileNotFoundError(f"No JSON output in {marker_dir}")


def flatten_marker_tree(node: dict[str, Any], blocks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Flatten Marker nested tree (children) into ordered list of blocks. Depth-first."""
    if blocks is None:
        blocks = []
    if node.get("block_type") and (node.get("html") or node.get("text")):
        blocks.append(node)
    for child in node.get("children") or []:
        flatten_marker_tree(child, blocks)
    return blocks


def raw_to_blocks(raw: Any) -> list[dict[str, Any]]:
    """Convert Marker raw output (list, or dict with blocks/children) to flat list of block dicts."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "blocks" in raw:
        return raw["blocks"]
    if isinstance(raw, dict) and "children" in raw:
        return flatten_marker_tree(raw)
    return []


def _bbox_from_block(block: dict[str, Any]) -> tuple[float, float, float, float]:
    bbox = block.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    return (0.0, 0.0, 0.0, 0.0)


def _page_from_block(block: dict[str, Any], fallback: int = 0) -> int:
    p = block.get("page")
    if p is not None:
        try:
            return int(p)
        except (TypeError, ValueError):
            pass
    return fallback


def blocks_to_marker_stream(
    blocks: list[dict[str, Any]],
    doc_id: str,
    document_part: DocumentPart | None = None,
) -> list[MarkerBlock]:
    """
    Convert raw block dicts to MarkerStream (A1). Sort by page_index, y_min, x_min, block_ordinal.
    Assign block_ordinal per page. If document_part is provided, set A-DOC-INV-4 provenance.
    """
    if not blocks:
        return []
    enriched: list[tuple[int, int, float, float, int, dict]] = []
    page_ordinal: dict[int, int] = {}
    for i, b in enumerate(blocks):
        page = _page_from_block(b, fallback=0)
        bbox = _bbox_from_block(b)
        y_min = bbox[1] if bbox else 0.0
        x_min = bbox[0] if bbox else 0.0
        block_ordinal = page_ordinal.get(page, 0)
        page_ordinal[page] = block_ordinal + 1
        text_raw = b.get("text")
        if text_raw is None or not str(text_raw).strip():
            text = extract_text_from_html(b.get("html") or "")
        else:
            text = text_raw
        section_hierarchy = b.get("section_hierarchy") or {}
        raw_type = b.get("block_type") or "Text"
        logical_page = (document_part.page_offset + page) if document_part else page
        d: dict[str, Any] = {
            "doc_id": document_part.logical_doc_id if document_part else doc_id,
            "page_index": logical_page,
            "text": text,
            "bbox": bbox,
            "raw_block_type": raw_type,
            "section_hierarchy": section_hierarchy,
        }
        if document_part:
            d["logical_doc_id"] = document_part.logical_doc_id
            d["document_part_id"] = document_part.document_part_id
            d["source_pdf_id"] = document_part.source_pdf_id
            d["source_pdf_page_index"] = page
            d["logical_page_index"] = logical_page
        enriched.append((page, y_min, x_min, block_ordinal, i, d))
    enriched.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    out: list[MarkerBlock] = []
    page_ordinal = {}
    for page, _y, _x, _old_ord, _idx, d in enriched:
        ord_in_page = page_ordinal.get(page, 0)
        page_ordinal[page] = ord_in_page + 1
        out.append(MarkerBlock(
            doc_id=d["doc_id"],
            page_index=d["page_index"],
            text=d["text"],
            bbox=d["bbox"],
            raw_block_type=d["raw_block_type"],
            block_ordinal=ord_in_page,
            section_hierarchy=d["section_hierarchy"],
            logical_doc_id=d.get("logical_doc_id", ""),
            document_part_id=d.get("document_part_id", ""),
            source_pdf_id=d.get("source_pdf_id", ""),
            source_pdf_page_index=d.get("source_pdf_page_index", -1),
            logical_page_index=d.get("logical_page_index", -1),
        ))
    return out


def run_marker_and_stream(
    pdf_path: Path,
    output_dir: Path,
    doc_id: str,
    document_part: DocumentPart | None = None,
) -> list[MarkerBlock]:
    """
    Run Marker on PDF, load JSON, flatten, sort, produce MarkerStream.
    If document_part is provided, blocks get A-DOC-INV-4 provenance (logical_doc_id, logical_page_index, etc.).
    """
    marker_dir = run_marker(pdf_path, output_dir)
    raw = load_marker_json(marker_dir)
    blocks = raw_to_blocks(raw)
    return blocks_to_marker_stream(blocks, doc_id, document_part)
