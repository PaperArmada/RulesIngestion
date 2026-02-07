#!/usr/bin/env python3
"""
Re-run chunking on existing marker_stream.json without re-running Marker.

Loads marker_stream.json and logical_document.json from output_dir, runs
stream_to_chunks with current chunker logic, and overwrites chunks.json,
drop_records.json, structural_blocks.json (empty_content), and metrics.json.

Usage:
    uv run python scripts/rechunk.py out/StarFinder2e-PlayerCore-v2 [--check-gates]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extraction.schemas import MarkerBlock
from extraction.chunker import stream_to_chunks, _default_should_drop
from extraction.serialize import markerstream_hash, chunkset_hash
from extraction.gates import run_gates, gates_report_to_dict


def _block_from_dict(d: dict) -> MarkerBlock:
    bbox = d.get("bbox", [])
    if isinstance(bbox, list) and len(bbox) >= 4:
        bbox = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    else:
        bbox = (0.0, 0.0, 0.0, 0.0)
    sh = d.get("section_hierarchy", [])
    if not isinstance(sh, (list, dict)):
        sh = []
    return MarkerBlock(
        doc_id=d.get("doc_id", ""),
        page_index=int(d.get("page_index", d.get("logical_page_index", 0))),
        text=(d.get("text") or ""),
        bbox=bbox,
        raw_block_type=d.get("raw_block_type", "Text"),
        block_ordinal=int(d.get("block_ordinal", 0)),
        section_hierarchy=sh if isinstance(sh, dict) else {},
        logical_doc_id=d.get("logical_doc_id", ""),
        document_part_id=d.get("document_part_id", ""),
        source_pdf_id=d.get("source_pdf_id", ""),
        source_pdf_page_index=int(d.get("source_pdf_page_index", -1)),
        logical_page_index=int(d.get("logical_page_index", -1)),
    )


def main() -> None:
    check_gates = "--check-gates" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--check-gates"]
    if len(args) < 1:
        print("Usage: uv run python scripts/rechunk.py <output_dir> [--check-gates]")
        sys.exit(1)
    out_dir = Path(args[0]).resolve()

    marker_path = out_dir / "marker_stream.json"
    logic_path = out_dir / "logical_document.json"
    if not marker_path.exists():
        print(f"Missing {marker_path}")
        sys.exit(1)
    if not logic_path.exists():
        print(f"Missing {logic_path}")
        sys.exit(1)

    print("[rechunk] Loading marker_stream.json ...")
    ms = json.loads(marker_path.read_text())
    stream_data = ms if isinstance(ms, list) else ms.get("marker_stream", ms)

    print("[rechunk] Loading logical_document.json ...")
    ld = json.loads(logic_path.read_text())
    logical_doc_id = ld.get("logical_doc_id", "")

    blocks = [_block_from_dict(b) for b in stream_data]
    print(f"[rechunk] Chunking {len(blocks)} blocks ...")
    result = stream_to_chunks(blocks, logical_doc_id, _default_should_drop)

    def write_json(name: str, data: list | dict) -> None:
        (out_dir / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    write_json("chunks.json", [c.to_dict() for c in result.chunks])
    print(f"[rechunk] Wrote chunks.json ({len(result.chunks)} chunks)")

    write_json("drop_records.json", [d.to_dict() for d in result.drop_records])
    print(f"[rechunk] Wrote drop_records.json ({len(result.drop_records)} records)")

    struct_path = out_dir / "structural_blocks.json"
    if struct_path.exists():
        struct = json.loads(struct_path.read_text())
        empty = getattr(result, "empty_structural_blocks", None) or []
        struct["empty_content"] = [b.to_dict() for b in empty]
        write_json("structural_blocks.json", struct)
        print(f"[rechunk] Updated structural_blocks.json (empty_content: {len(empty)})")

    metrics = {
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
            print("[rechunk] Gates failed")
            sys.exit(1)
    write_json("metrics.json", metrics)
    print("[rechunk] Wrote metrics.json")
    print("[rechunk] Done.")


if __name__ == "__main__":
    main()
