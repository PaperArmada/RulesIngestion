#!/usr/bin/env python3
"""
Map archived (marker-era) StarFinder gold chunks to Mark III EvidenceUnit IDs
and update evals/retrieval/StarFinderPlayerCore batch JSONs with gold_unit_ids.

Uses: Archive/marker-era/blind_eval/gold_audit/gold_reference.json (target_text per gold item)
      out/mark3_evaluation/StarFinderPlayerCore (stageB.evidence_units.json per page)
"""
from __future__ import annotations

import json
import re
from pathlib import Path


RULES_ROOT = Path(__file__).resolve().parent.parent
GOLD_REFERENCE = RULES_ROOT / "Archive/marker-era/blind_eval/gold_audit/gold_reference.json"
SUBSTRATE = RULES_ROOT / "out/mark3_evaluation/StarFinderPlayerCore"
BATCH_DIR = RULES_ROOT / "evals/retrieval/StarFinderPlayerCore"
BATCH_FILES = [
    "batch_001.json",
    "batch_002_state.json",
    "batch_003_grounding.json",
    "batch_004_temporal.json",
    "batch_005_constraints.json",
    "batch_006_conceptual.json",
]


def doc_id_to_chapter_stem(doc_id: str) -> str:
    """sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057 -> PZO22001 Starfinder Player Core 040-057"""
    if doc_id.startswith("sf2e-playercore-"):
        doc_id = doc_id[len("sf2e-playercore-"):]
    parts = doc_id.split("-")
    # Keep page range as 040-057 (hyphen), not 040 057
    if len(parts) >= 2 and parts[-2].isdigit() and parts[-1].isdigit():
        range_part = f"{parts[-2]}-{parts[-1]}"
        rest = "-".join(parts[:-2])
        return rest.replace("-", " ") + " " + range_part
    return doc_id.replace("-", " ")


def load_units_by_chapter_page(substrate_path: Path) -> dict[tuple[str, int], list[dict]]:
    """(chapter_stem, page) -> list of {unit_id, text}."""
    out: dict[tuple[str, int], list[dict]] = {}
    for f in sorted(substrate_path.rglob("stageB.evidence_units.json")):
        if not f.is_file():
            continue
        page_dir = f.parent
        # page_dir.name like "PZO22001 Starfinder Player Core 040-057_p9"
        m = re.match(r"^(.+)_p(\d+)$", page_dir.name)
        if not m:
            continue
        chapter_stem = m.group(1)
        page = int(m.group(2))
        data = json.loads(f.read_text(encoding="utf-8"))
        units = [
            {"unit_id": u.get("unit_id", ""), "text": (u.get("text") or "").strip()}
            for u in data.get("units", [])
        ]
        out[(chapter_stem, page)] = units
    return out


def normalize_for_match(s: str) -> str:
    """Collapse whitespace for matching."""
    return " ".join(s.split())


def match_target_to_units(target_text: str, units: list[dict]) -> str | None:
    """
    Find the best EvidenceUnit for this gold target_text.
    Prefer: target contained in unit text, then unit text contained in target, then best Jaccard.
    """
    if not target_text.strip() or not units:
        return None
    target_norm = normalize_for_match(target_text)
    target_lower = target_norm.lower()
    target_tokens = set(target_lower.split())

    best_id: str | None = None
    best_score = -1.0

    for u in units:
        text = u.get("text", "")
        unit_norm = normalize_for_match(text)
        unit_lower = unit_norm.lower()
        unit_tokens = set(unit_lower.split())

        # Containment: gold often is a substring of Mark III unit (unit may have heading prefix)
        if target_norm in unit_norm or unit_norm in target_norm:
            score = 1.0
        elif target_lower in unit_lower:
            score = 0.95
        elif unit_lower in target_lower:
            score = 0.9
        else:
            # Jaccard
            if not target_tokens or not unit_tokens:
                continue
            inter = len(target_tokens & unit_tokens)
            union = len(target_tokens | unit_tokens)
            score = inter / union if union else 0

        if score > best_score:
            best_score = score
            best_id = u.get("unit_id")

    # Require at least 0.4 Jaccard or containment
    if best_id is not None and best_score >= 0.4:
        return best_id
    return None


def main() -> None:
    if not GOLD_REFERENCE.exists():
        raise SystemExit(f"Gold reference not found: {GOLD_REFERENCE}")
    if not SUBSTRATE.is_dir():
        raise SystemExit(f"Substrate not found: {SUBSTRATE}")

    ref = json.loads(GOLD_REFERENCE.read_text(encoding="utf-8"))
    units_by_key = load_units_by_chapter_page(SUBSTRATE)
    print(f"Loaded {len(units_by_key)} (chapter, page) -> units from substrate")

    # query_id -> list of EvidenceUnit ids (deduplicated, order preserved)
    query_to_gold_unit_ids: dict[str, list[str]] = {}
    match_stats = {"matched": 0, "missed": 0, "no_candidates": 0}

    for q in ref["queries"]:
        query_id = q.get("query_id", "")
        gold_ids: list[str] = []
        seen: set[str] = set()
        for g in q.get("gold_items", []):
            doc_id = g.get("document_id", "")
            page = g.get("page", 0)
            target_text = (g.get("target_text") or "").strip()
            chapter_stem = doc_id_to_chapter_stem(doc_id)
            key = (chapter_stem, page)
            candidates = units_by_key.get(key, [])
            if not candidates:
                match_stats["no_candidates"] += 1
                continue
            unit_id = match_target_to_units(target_text, candidates)
            if unit_id and unit_id not in seen:
                gold_ids.append(unit_id)
                seen.add(unit_id)
                match_stats["matched"] += 1
            else:
                if not unit_id:
                    match_stats["missed"] += 1
        if gold_ids:
            query_to_gold_unit_ids[query_id] = gold_ids

    print(f"Match stats: matched={match_stats['matched']}, missed={match_stats['missed']}, no_candidates={match_stats['no_candidates']}")
    print(f"Queries with at least one gold_unit_id: {len(query_to_gold_unit_ids)}")

    # Update batch files
    for name in BATCH_FILES:
        path = BATCH_DIR / name
        if not path.exists():
            print(f"Skip (not found): {path}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        updated = 0
        for q in data.get("queries", []):
            qid = q.get("id", "")
            if qid in query_to_gold_unit_ids:
                q["gold_unit_ids"] = query_to_gold_unit_ids[qid]
                updated += 1
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Updated {path.name}: {updated} queries with gold_unit_ids")

    # Write mapping audit for reference
    audit_path = BATCH_DIR / "gold_unit_ids_audit.json"
    audit = {
        "source": str(GOLD_REFERENCE),
        "substrate": str(SUBSTRATE),
        "query_to_gold_unit_ids": query_to_gold_unit_ids,
        "match_stats": match_stats,
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote audit: {audit_path}")


if __name__ == "__main__":
    main()
