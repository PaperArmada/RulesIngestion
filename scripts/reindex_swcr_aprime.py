"""reindex_swcr_aprime.py — Re-index SWCR enrichments to current unit_ids without LLM calls."""

from __future__ import annotations

import json
from pathlib import Path

import blake3

SWCR_BASE = Path("out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF")


def old_key(text: str) -> str:
    """Reproduces the unit_id used when enrichments were originally generated (empty path)."""
    return blake3.blake3(f"{text}|".encode()).hexdigest()


def main() -> None:
    total_matched = total_units = total_enr = 0
    page_dirs = sorted(d for d in SWCR_BASE.iterdir() if d.is_dir())

    for page_dir in page_dirs:
        stageB_path = page_dir / "stageB.evidence_units.json"
        enr_path = page_dir / "stageAPrime.enrichments.json"
        if not stageB_path.exists() or not enr_path.exists():
            continue

        data = json.loads(stageB_path.read_text(encoding="utf-8"))
        units = data.get("units", [])
        enrichments = json.loads(enr_path.read_text(encoding="utf-8"))
        if not isinstance(enrichments, dict):
            enrichments = {}

        remapped = {}
        matched = 0
        for u in units:
            current_uid = u.get("unit_id", "")
            text = u.get("text", "")
            ok = old_key(text)
            if ok in enrichments:
                remapped[current_uid] = enrichments[ok]
                matched += 1

        backup = page_dir / "stageAPrime.enrichments.pre_reindex.json"
        if not backup.exists():
            backup.write_text(enr_path.read_text(encoding="utf-8"), encoding="utf-8")
        enr_path.write_text(json.dumps(remapped, indent=2), encoding="utf-8")

        print(f"{page_dir.name}: matched {matched}/{len(units)} units")
        total_matched += matched
        total_units += len(units)
        total_enr += len(enrichments)

    pct = 100.0 * total_matched / total_units if total_units else 0.0
    print(f"\nTotal: {total_matched}/{total_units} units re-indexed ({pct:.1f}%)")
    print(f"Old enrichment entries: {total_enr}")


if __name__ == "__main__":
    main()
