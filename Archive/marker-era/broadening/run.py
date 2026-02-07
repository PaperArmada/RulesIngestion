"""
Stage B CLI and orchestration: Chunk[] → EvidenceChunk[].

Usage:
    uv run python -m broadening.run out/StarFinder2e-PlayerCore/chunks.json \
        --output-dir out/StarFinder2e-PlayerCore \
        --check-gates

Contract: Stage B — Chunk Quality & Context Broadening.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .eligibility import filter_eligible
from .gates import run_gates, GatesReport
from .grouper import group_chunks
from .schemas import BroadeningResult, EvidenceChunk, UngroupedRecord
from .serialize import serialize_broadening_output


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------


def _log(msg: str) -> None:
    """Progress message to terminal (flush for immediate output)."""
    print(msg, flush=True)


# -----------------------------------------------------------------------------
# Chunk Loading
# -----------------------------------------------------------------------------


def _load_chunks(chunks_path: Path) -> list[Any]:
    """Load chunks from JSON file."""
    with open(chunks_path) as f:
        data = json.load(f)

    # Handle both raw list and wrapped format
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "chunks" in data:
        return data["chunks"]

    raise ValueError(f"Unexpected chunks format in {chunks_path}")


def _chunk_from_dict(d: dict[str, Any]) -> Any:
    """
    Convert a chunk dict to a Chunk object.

    Imports Chunk lazily to avoid circular imports.
    """
    from extraction.schemas import Chunk

    # Handle bbox
    bbox = d.get("bbox", [])
    if isinstance(bbox, list) and len(bbox) == 4:
        bbox = tuple(bbox)
    else:
        bbox = (0.0, 0.0, 0.0, 0.0)

    return Chunk(
        chunk_id=d["chunk_id"],
        doc_id=d["doc_id"],
        page_index=d["page_index"],
        section_path=d.get("section_path", []),
        block_type=d["block_type"],
        text=d["text"],
        span_start=d["span_start"],
        span_end=d["span_end"],
        span_locality=d.get("span_locality", "page"),
        bbox=bbox,
        block_ordinals=d.get("block_ordinals", []),
        structural_metadata=d.get("structural_metadata", {}),
        logical_doc_id=d.get("logical_doc_id", ""),
        document_part_id=d.get("document_part_id", ""),
        source_pdf_id=d.get("source_pdf_id", ""),
        source_pdf_page_index=d.get("source_pdf_page_index", -1),
        logical_page_index=d.get("logical_page_index", -1),
    )


# -----------------------------------------------------------------------------
# Output Writing
# -----------------------------------------------------------------------------


_SAMPLE_FIRST_N = 15
_SAMPLE_EVERY_NTH = 40


def _build_sample_md(output_dir: Path, result: BroadeningResult) -> str:
    """Build EVIDENCE-CHUNKS-SAMPLE.md content from broadening result."""
    chunks = [c.to_dict() for c in result.evidence_chunks]
    total = len(chunks)
    ungrouped_count = len(result.ungrouped_records)

    kind_counts: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    for c in chunks:
        k = c.get("kind", "?")
        kind_counts[k] = kind_counts.get(k, 0) + 1
        r = c.get("grouping_rule_id", "?")
        rule_counts[r] = rule_counts.get(r, 0) + 1

    indices = set(range(min(_SAMPLE_FIRST_N, total)))
    for i in range(0, total, _SAMPLE_EVERY_NTH):
        indices.add(i)
    sampled = sorted(indices)

    lines = [
        f"# Evidence Chunks Sample: {output_dir.name}",
        "",
        "Stage B output: grouped evidence chunks for retrieval/grounding. Use this doc to manually review grouping quality and content.",
        "",
        "## Counts",
        "",
        f"- **Evidence chunks:** {total}",
        f"- **Ungrouped records:** {ungrouped_count}",
        f"- **Kind:** " + ", ".join(f"{k}={v}" for k, v in sorted(kind_counts.items())),
        f"- **Grouping rule:** " + ", ".join(f"{r}={v}" for r, v in sorted(rule_counts.items())),
        "",
        "## Sampled evidence chunks",
        "",
        f"Showing: first {_SAMPLE_FIRST_N}, then every {_SAMPLE_EVERY_NTH}th. Full text (no truncation).",
        "",
    ]

    for idx in sampled:
        if idx >= total:
            continue
        c = chunks[idx]
        eid = (c.get("evidence_chunk_id") or "")[:14]
        kind = c.get("kind", "?")
        rule = c.get("grouping_rule_id", "?")
        stop = c.get("grouping_stop_reason", "?")
        section_path = c.get("section_path") or []
        sp = " → ".join(str(p) for p in section_path) if section_path else "(none)"
        page_indices = c.get("page_indices") or []
        source_ids = c.get("source_chunk_ids") or []
        text = (c.get("text") or "").strip()
        structural_meta = c.get("structural_metadata") or {}
        meta_flags = ", ".join(f"{k}={v}" for k, v in structural_meta.items()) if structural_meta else ""

        lines.append("---")
        lines.append("")
        lines.append(f"### [{idx + 1}] `{eid}`")
        lines.append("")
        lines.append(f"- **Kind:** {kind}  **Rule:** {rule}  **Stop:** {stop}")
        lines.append(f"- **Section:** `{sp}`")
        lines.append(f"- **Pages:** {page_indices}  **Source chunks:** {len(source_ids)}")
        if meta_flags:
            lines.append(f"- **Structural flags:** {meta_flags}")
        lines.append("")
        lines.append(text)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*End of sample. Full data: evidence_chunks.json, ungrouped_records.json.*")
    lines.append("")
    return "\n".join(lines)


def _write_outputs(
    output_dir: Path,
    result: BroadeningResult,
    gates_report: GatesReport | None,
) -> None:
    """Write Stage B outputs to files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write evidence chunks
    evidence_output = serialize_broadening_output(result.evidence_chunks)
    evidence_path = output_dir / "evidence_chunks.json"
    with open(evidence_path, "w") as f:
        json.dump(evidence_output, f, indent=2)
    _log(f"[broadening] Wrote {len(result.evidence_chunks)} evidence chunks to {evidence_path}")

    # Write ungrouped records (always write so sample script sees current count)
    ungrouped_path = output_dir / "ungrouped_records.json"
    with open(ungrouped_path, "w") as f:
        json.dump([u.to_dict() for u in result.ungrouped_records], f, indent=2)
    _log(f"[broadening] Wrote {len(result.ungrouped_records)} ungrouped records to {ungrouped_path}")

    # Write EVIDENCE-CHUNKS-SAMPLE.md (fresh on every run)
    sample_path = output_dir / "EVIDENCE-CHUNKS-SAMPLE.md"
    sample_path.write_text(_build_sample_md(output_dir, result), encoding="utf-8")
    _log(f"[broadening] Wrote {sample_path}")

    # Write gates report if available
    if gates_report:
        gates_path = output_dir / "broadening_gates.json"
        with open(gates_path, "w") as f:
            json.dump(gates_report.to_dict(), f, indent=2)
        status = "PASSED" if gates_report.passed else "FAILED"
        _log(f"[broadening] Gates {status} — report at {gates_path}")


# -----------------------------------------------------------------------------
# Main Orchestration
# -----------------------------------------------------------------------------


def run_broadening(
    chunks_path: Path,
    output_dir: Path,
    allow_tables: bool = False,
    check_gates: bool = False,
    doc_hash: str = "",
) -> BroadeningResult:
    """
    Stage B: Chunk[] → EvidenceChunk[].

    1. Load chunks from chunks_path
    2. Filter eligible (B-INV-0)
    3. Apply grouping rules
    4. Validate semantic mass (B-INV-2)
    5. Write evidence_chunks.json
    6. Optionally run gates

    Args:
        chunks_path: Path to Stage A chunks.json
        output_dir: Directory for output files
        allow_tables: If True, include Table chunks
        check_gates: If True, run M-B1 through M-B8 gates
        doc_hash: Document hash for ID generation

    Returns:
        BroadeningResult with evidence chunks and ungrouped records
    """
    _log(f"[broadening] Starting: {chunks_path} → {output_dir}")

    # Load chunks
    _log("[broadening] Loading chunks ...")
    raw_chunks = _load_chunks(chunks_path)
    _log(f"[broadening] Loaded {len(raw_chunks)} chunks")

    # Convert to Chunk objects
    chunks = [_chunk_from_dict(d) for d in raw_chunks]

    # Count eligible
    eligible = filter_eligible(chunks, allow_tables)
    _log(f"[broadening] {len(eligible)} eligible chunks (B-INV-0)")

    # Generate doc_hash if not provided
    if not doc_hash:
        # Use chunks_path name as fallback
        doc_hash = chunks_path.stem

    # Apply grouping rules
    _log("[broadening] Applying grouping rules ...")
    evidence_chunks, ungrouped = group_chunks(chunks, doc_hash, allow_tables)
    _log(f"[broadening] Generated {len(evidence_chunks)} evidence chunks")
    _log(f"[broadening] {len(ungrouped)} ungrouped records")

    # Build result
    result = BroadeningResult(
        evidence_chunks=evidence_chunks,
        ungrouped_records=ungrouped,
        input_chunk_count=len(chunks),
        eligible_chunk_count=len(eligible),
    )

    # Run gates if requested
    gates_report: GatesReport | None = None
    if check_gates:
        _log("[broadening] Running gates ...")
        gates_report = run_gates(evidence_chunks)

    # Write outputs
    _log("[broadening] Writing outputs ...")
    _write_outputs(output_dir, result, gates_report)

    _log("[broadening] Done.")
    return result


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Stage B: Chunk[] → EvidenceChunk[]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage
    uv run python -m broadening.run out/StarFinder2e-PlayerCore/chunks.json \\
        --output-dir out/StarFinder2e-PlayerCore

    # With gates check
    uv run python -m broadening.run out/StarFinder2e-PlayerCore/chunks.json \\
        --output-dir out/StarFinder2e-PlayerCore --check-gates

    # Include tables
    uv run python -m broadening.run chunks.json --output-dir out --allow-tables
""",
    )

    parser.add_argument(
        "chunks_path",
        type=Path,
        help="Path to Stage A chunks.json file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for evidence_chunks.json",
    )
    parser.add_argument(
        "--allow-tables",
        action="store_true",
        help="Include Table chunks in eligible set",
    )
    parser.add_argument(
        "--check-gates",
        action="store_true",
        help="Run M-B1 through M-B8 gates after processing",
    )
    parser.add_argument(
        "--doc-hash",
        type=str,
        default="",
        help="Document hash for ID generation (default: derived from chunks_path)",
    )

    args = parser.parse_args()

    # Validate input
    if not args.chunks_path.exists():
        print(f"Error: Chunks file not found: {args.chunks_path}", file=sys.stderr)
        return 1

    try:
        run_broadening(
            chunks_path=args.chunks_path,
            output_dir=args.output_dir,
            allow_tables=args.allow_tables,
            check_gates=args.check_gates,
            doc_hash=args.doc_hash,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
