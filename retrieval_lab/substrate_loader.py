"""Load EvidenceUnits from Mark III stageB output into a flat corpus."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _parse_page_from_dir_name(dir_name: str, document_id: str) -> int | None:
    """
    Extract 0-based page index from directory name like DnD_PHB_5.5_p45 -> 45.
    Directory name is expected to be {document_id}_p{N}.
    """
    suffix = f"_p"
    if not dir_name.startswith(document_id) or suffix not in dir_name:
        return None
    match = re.search(r"_p(\d+)$", dir_name)
    if match:
        return int(match.group(1))
    return None


def load_evidence_units(
    phb_dir: str | Path,
    document_id: str,
    min_chars: int | None = None,
) -> List[Dict[str, Any]]:
    """
    Load all EvidenceUnits from page directories under phb_dir.
    Each page dir is expected to contain stageB.evidence_units.json.
    Supports both flat layout (phb_dir / {doc_id}_p0 / stageB...) and nested
    multi-PDF layout (phb_dir / PDF_stem / PDF_stem_p0 / stageB...).
    Returns a flat list of chunk-like dicts: id, text, page, structural_path, unit_type, document_id.

    If min_chars is set, units with len(text) < min_chars are excluded (reduces noise from
    spell header lines and key-value metadata; see Docs/Learnings/LEARNINGS-SnW-Tiny-Chunks-Root-Cause-2026.md).
    When using min_chars the corpus changes, so re-embed is required (new run_id).
    """
    phb_path = Path(phb_dir)
    if not phb_path.is_dir():
        raise FileNotFoundError(f"Substrate directory not found: {phb_path}")
    corpus: List[Dict[str, Any]] = []
    skipped = 0
    # Find all dirs that contain stageB.evidence_units.json (one or two levels deep)
    units_file_name = "stageB.evidence_units.json"
    page_dirs = sorted(
        [f.parent for f in phb_path.rglob(units_file_name) if f.name == units_file_name and f.parent.is_dir()],
        key=lambda d: (d.parent.name, d.name),
    )
    for page_dir in page_dirs:
        units_file = page_dir / units_file_name
        if not units_file.exists():
            continue
        page_num = _parse_page_from_dir_name(page_dir.name, document_id)
        if page_num is None:
            # Fallback: try any _pN pattern
            match = re.search(r"_p(\d+)$", page_dir.name)
            page_num = int(match.group(1)) if match else -1
        data = json.loads(units_file.read_text(encoding="utf-8"))
        units = data.get("units", [])
        for u in units:
            unit_id = u.get("unit_id", "")
            text = u.get("text", "")
            if min_chars is not None and len(text) < min_chars:
                skipped += 1
                continue
            structural_path = u.get("structural_path", [])
            unit_type = u.get("unit_type", "unknown")
            corpus.append({
                "id": unit_id,
                "text": text,
                "page": page_num,
                "structural_path": structural_path,
                "unit_type": unit_type,
                "document_id": document_id,
            })
    if min_chars is not None and skipped:
        logger.info("Substrate filter min_chars=%d: excluded %d units, kept %d", min_chars, skipped, len(corpus))
    return corpus


def _structural_path_key(unit: Dict[str, Any]) -> Tuple[int, str]:
    """Return (page, joined structural_path) as a merge-group key.

    Units with an empty structural_path get a unique key per unit so they
    are never merged (orphan paragraphs, tables, images).
    """
    page = unit.get("page", -1)
    sp = unit.get("structural_path", [])
    if not sp:
        # Use the unit id to make the key unique → never merges
        return (page, f"__orphan__{unit.get('id', '')}")
    return (page, " > ".join(sp))


def merge_units_by_heading(
    corpus: List[Dict[str, Any]],
    max_chars: int = 2000,
    separator: str = " — ",
) -> List[Dict[str, Any]]:
    """Merge consecutive units that share the same structural_path (heading parent).

    Walk units in corpus order (already sorted by page then ordering_key from
    ``load_evidence_units``).  When consecutive units have the same
    (page, structural_path), concatenate their ``text`` with *separator*.
    If appending the next unit would push the merged text past *max_chars*,
    flush the current chunk and start a new one (still under the same heading).

    Units with an empty ``structural_path`` (orphans, tables, images) pass
    through unmerged.

    The merged chunk gets:
    - ``id``: deterministic SHA-256 of the sorted constituent unit ids.
    - ``text``: concatenated text.
    - ``page``, ``structural_path``, ``document_id``: inherited from the group.
    - ``unit_type``: "merged" (or original type if only one unit in the group).
    - ``source_unit_ids``: list of original unit ids that were merged.

    Returns a new corpus list (does not mutate the input).
    """
    if not corpus:
        return []

    merged: List[Dict[str, Any]] = []

    def _flush(buf: List[Dict[str, Any]]) -> None:
        """Flush a buffer of units sharing the same heading into one or more merged chunks."""
        if not buf:
            return
        # Single unit → pass through (keep original id and type)
        if len(buf) == 1:
            out = dict(buf[0])
            out["source_unit_ids"] = [buf[0]["id"]]
            merged.append(out)
            return

        # Multiple units → merge with size cap
        parts: List[str] = []
        current_ids: List[str] = []
        current_len = 0

        for u in buf:
            text = u.get("text", "")
            addition_len = len(text) + (len(separator) if parts else 0)
            if parts and (current_len + addition_len) > max_chars:
                # Flush current accumulator as a merged chunk
                _emit(parts, current_ids, buf[0])
                parts = []
                current_ids = []
                current_len = 0
            parts.append(text)
            current_ids.append(u["id"])
            current_len += addition_len

        if parts:
            _emit(parts, current_ids, buf[0])

    def _emit(parts: List[str], unit_ids: List[str], template: Dict[str, Any]) -> None:
        """Create a single merged chunk from accumulated parts."""
        merged_text = separator.join(parts)
        # Deterministic id: SHA-256 of sorted constituent ids
        id_material = "|".join(sorted(unit_ids))
        merged_id = hashlib.sha256(id_material.encode("utf-8")).hexdigest()
        merged.append({
            "id": merged_id,
            "text": merged_text,
            "page": template.get("page", -1),
            "structural_path": template.get("structural_path", []),
            "unit_type": "merged" if len(unit_ids) > 1 else template.get("unit_type", "unknown"),
            "document_id": template.get("document_id", ""),
            "source_unit_ids": list(unit_ids),
        })

    # Walk corpus in order, grouping consecutive same-heading units
    prev_key: Tuple[int, str] | None = None
    buf: List[Dict[str, Any]] = []

    for unit in corpus:
        key = _structural_path_key(unit)
        if key != prev_key:
            _flush(buf)
            buf = [unit]
            prev_key = key
        else:
            buf.append(unit)

    _flush(buf)

    original_count = len(corpus)
    merged_count = len(merged)
    multi_source = sum(1 for m in merged if len(m.get("source_unit_ids", [])) > 1)
    logger.info(
        "Heading merge: %d units → %d chunks (%d merged from multiple units, max_chars=%d)",
        original_count, merged_count, multi_source, max_chars,
    )
    return merged


def merge_enrichments_into_corpus(
    corpus: List[Dict[str, Any]],
    phb_dir: str | Path,
) -> List[Dict[str, Any]]:
    """R6: Merge topic_tags and co_retrieval_hints from stageAPrime.enrichments.json into corpus.

    Enrichments are keyed by unit_id. Mutates corpus items in place and returns corpus.
    """
    phb_path = Path(phb_dir)
    enrichments_file = "stageAPrime.enrichments.json"
    id_to_enr: Dict[str, Dict[str, Any]] = {}
    for f in phb_path.rglob(enrichments_file):
        if f.name != enrichments_file:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for uid, enr in (data if isinstance(data, dict) else {}).items():
                if isinstance(enr, dict) and uid not in id_to_enr:
                    id_to_enr[uid] = enr
        except Exception as e:
            logger.warning("Could not load enrichments from %s: %s", f, e)
    for u in corpus:
        uid = u.get("id", "")
        enr = id_to_enr.get(uid)
        if enr:
            u["topic_tags"] = enr.get("topic_tags", [])
            u["co_retrieval_hints"] = enr.get("co_retrieval_hints", [])
    return corpus


def units_by_page(corpus: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """Group corpus items by page number for page-anchored gold grounding."""
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for item in corpus:
        p = item.get("page", -1)
        if p not in by_page:
            by_page[p] = []
        by_page[p].append(item)
    return by_page
