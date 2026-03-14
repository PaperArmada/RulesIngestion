"""
TOC Binder — bind EvidenceUnits to their deepest covering TOC section,
enriching structural_path with book-level ancestry.

Also performs table caption binding: if a table unit is immediately preceded
by a short prose unit on the same page, that prose is treated as the table's
caption and stored in join_metadata.table_title.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from extraction.schemas import EvidenceUnit
from extraction.toc_parser import TocNode
from extraction.unit_identity import compute_evidence_unit_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fingerprint → page index mapping
# ---------------------------------------------------------------------------

def build_fingerprint_to_page_index(
    eval_dir: Path,
    stem: str,
) -> dict[str, int]:
    """Scan page artifacts to build page_fingerprint → page_index mapping."""
    fp_map: dict[str, int] = {}
    for page_dir in sorted(eval_dir.iterdir()):
        if not page_dir.is_dir():
            continue
        if not page_dir.name.startswith(f"{stem}_p"):
            continue
        page_json = page_dir / "stageA.page.json"
        if not page_json.exists():
            continue
        data = json.loads(page_json.read_text(encoding="utf-8"))
        fp = data.get("page_fingerprint", "")
        page_idx = data.get("page_index")
        if fp and page_idx is not None:
            fp_map[fp] = page_idx
    return fp_map


# ---------------------------------------------------------------------------
# Deepest-match binding
# ---------------------------------------------------------------------------

def _find_deepest_covering_node(
    page_index: int,
    nodes: list[TocNode],
    ancestry: list[str] | None = None,
) -> list[str] | None:
    """Find the deepest TOC node whose [page_num, page_end] range covers page_index.

    Returns the full ancestry path (list of titles from root to deepest match),
    or None if no node covers this page.
    """
    if ancestry is None:
        ancestry = []

    for node in nodes:
        if node.page_num <= page_index <= node.page_end:
            current_path = ancestry + [node.title]
            deeper = _find_deepest_covering_node(page_index, node.children, current_path)
            if deeper is not None:
                return deeper
            return current_path

    return None


def _recompute_unit_id(unit: EvidenceUnit, structural_path: list[str]) -> str:
    return compute_evidence_unit_id(
        text=unit.text,
        structural_path=structural_path,
        page_fingerprint=unit.page_fingerprint,
        source_line_start=unit.source_line_start,
        source_line_end=unit.source_line_end,
        unit_type=unit.unit_type,
    )


# ---------------------------------------------------------------------------
# Table caption binding
# ---------------------------------------------------------------------------

_TABLE_CAPTION_MAX_CHARS = 80


def _bind_table_captions(units: list[EvidenceUnit]) -> list[dict[str, Any]]:
    """Identify table captions: short prose immediately before a table on same page.

    Returns list of binding records for auditability.
    """
    bindings: list[dict[str, Any]] = []
    for i, unit in enumerate(units):
        if unit.unit_type != "table" or i == 0:
            continue
        prev = units[i - 1]
        if prev.unit_type not in ("prose", "heading"):
            continue
        if prev.page_fingerprint != unit.page_fingerprint:
            continue
        caption_text = prev.text.strip()
        if len(caption_text) > _TABLE_CAPTION_MAX_CHARS:
            continue
        if not caption_text:
            continue

        if unit.join_metadata is None:
            unit.join_metadata = {}
        unit.join_metadata["table_title"] = caption_text
        bindings.append({
            "table_unit_id": unit.unit_id[:16],
            "caption_unit_id": prev.unit_id[:16],
            "table_title": caption_text,
        })
    return bindings


# ---------------------------------------------------------------------------
# Core binding pass
# ---------------------------------------------------------------------------

def bind_units_to_toc(
    units: list[EvidenceUnit],
    toc_tree: list[TocNode],
    fp_to_page: dict[str, int],
) -> tuple[list[EvidenceUnit], list[dict[str, Any]]]:
    """Enrich each unit's structural_path from the TOC tree.

    For each unit:
      1. Look up its page_fingerprint → page_index
      2. Find deepest TOC node covering that page
      3. Replace structural_path with TOC ancestry
      4. Preserve original path in join_metadata.original_structural_path
      5. Recompute unit_id to reflect new path

    Also runs table caption binding.

    Returns (enriched_units, binding_records).
    """
    binding_records: list[dict[str, Any]] = []
    enriched: list[EvidenceUnit] = []
    bound_count = 0
    unbound_count = 0

    for unit in units:
        page_idx = fp_to_page.get(unit.page_fingerprint)
        if page_idx is None:
            enriched.append(unit)
            unbound_count += 1
            binding_records.append({
                "unit_id": unit.unit_id[:16],
                "status": "no_page_mapping",
                "page_fingerprint": unit.page_fingerprint[:16],
            })
            continue

        toc_path = _find_deepest_covering_node(page_idx, toc_tree)
        if toc_path is None:
            enriched.append(unit)
            unbound_count += 1
            binding_records.append({
                "unit_id": unit.unit_id[:16],
                "status": "no_toc_coverage",
                "page_index": page_idx,
            })
            continue

        original_path = list(unit.structural_path)

        new_path = list(toc_path)
        if unit.structural_path:
            last_existing = unit.structural_path[-1]
            if last_existing not in toc_path:
                new_path = toc_path + [last_existing]

        new_unit_id = _recompute_unit_id(unit, new_path)

        meta = dict(unit.join_metadata) if unit.join_metadata else {}
        meta["original_structural_path"] = original_path
        meta["toc_bound"] = True

        anomaly = list(unit.anomaly_flags)
        if "no_heading_parent" in anomaly:
            anomaly.remove("no_heading_parent")
        if "toc_structural_path" not in anomaly:
            anomaly.append("toc_structural_path")

        new_unit = EvidenceUnit(
            unit_id=new_unit_id,
            unit_type=unit.unit_type,
            text=unit.text,
            structural_path=new_path,
            ordering_key=unit.ordering_key,
            page_fingerprint=unit.page_fingerprint,
            content_hash=unit.content_hash,
            source_line_start=unit.source_line_start,
            source_line_end=unit.source_line_end,
            anomaly_flags=anomaly,
            content_version=unit.content_version,
            page_fingerprints=unit.page_fingerprints,
            table_group_id=unit.table_group_id,
            join_metadata=meta,
            source_unit_ids=unit.source_unit_ids,
        )
        enriched.append(new_unit)
        bound_count += 1
        binding_records.append({
            "unit_id": new_unit.unit_id[:16],
            "original_unit_id": unit.unit_id[:16],
            "status": "bound",
            "page_index": page_idx,
            "original_path": original_path,
            "toc_path": new_path,
        })

    caption_bindings = _bind_table_captions(enriched)

    logger.info(
        "TOC binding: %d bound, %d unbound, %d table captions",
        bound_count, unbound_count, len(caption_bindings),
    )

    all_bindings = binding_records + [
        {**cb, "status": "table_caption"} for cb in caption_bindings
    ]
    return enriched, all_bindings


# ---------------------------------------------------------------------------
# Page-level binding (operates on per-page stageB files in-place)
# ---------------------------------------------------------------------------

def run_toc_binding_pass(
    eval_dir: Path,
    stem: str,
    toc_tree: list[TocNode],
    total_pages: int,
) -> dict[str, Any]:
    """Run TOC binding on all per-page stageB.evidence_units.json files.

    Updates files in-place (same pattern as orphan header pass).

    Returns a summary dict with counts and per-page details.
    """
    from extraction.toc_parser import compute_page_ranges
    compute_page_ranges(toc_tree, total_pages)

    fp_to_page = build_fingerprint_to_page_index(eval_dir, stem)

    all_bindings: list[dict[str, Any]] = []
    total_bound = 0
    total_unbound = 0
    total_captions = 0
    pages_processed = 0

    for page_dir in sorted(eval_dir.iterdir()):
        if not page_dir.is_dir():
            continue
        if not page_dir.name.startswith(f"{stem}_p"):
            continue
        units_path = page_dir / "stageB.evidence_units.json"
        if not units_path.exists():
            continue

        stage_b_data = json.loads(units_path.read_text(encoding="utf-8"))
        units = [EvidenceUnit.from_dict(u) for u in stage_b_data.get("units", [])]
        if not units:
            continue

        enriched, bindings = bind_units_to_toc(units, toc_tree, fp_to_page)

        stage_b_data["units"] = [u.to_dict() for u in enriched]
        units_path.write_text(
            json.dumps(stage_b_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        page_bound = sum(1 for b in bindings if b.get("status") == "bound")
        page_captions = sum(1 for b in bindings if b.get("status") == "table_caption")
        total_bound += page_bound
        total_unbound += len(units) - page_bound
        total_captions += page_captions
        pages_processed += 1
        all_bindings.extend(bindings)

    summary = {
        "pages_processed": pages_processed,
        "total_units_bound": total_bound,
        "total_units_unbound": total_unbound,
        "total_table_captions": total_captions,
        "binding_records": all_bindings,
    }

    bindings_path = eval_dir / "toc_bindings.json"
    bindings_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "TOC binding pass complete: %d pages, %d bound, %d unbound, %d captions",
        pages_processed, total_bound, total_unbound, total_captions,
    )

    return summary
