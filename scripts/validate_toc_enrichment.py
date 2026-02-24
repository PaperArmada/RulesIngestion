#!/usr/bin/env python3
"""
Validate TOC structural enrichment on an existing Mark III output directory.

Runs:
  1. TOC detection + flat entry extraction
  2. TOC hierarchy reconstruction (LLM or flat fallback)
  3. TOC binding pass (enrich stageB.evidence_units.json per-page)
  4. Cross-page join pass (rebuild joined.evidence_units.json)
  5. Diagnostic summary: orphan rate, path depth distribution, binding coverage

Usage (from RulesIngestion root):
  uv run python scripts/validate_toc_enrichment.py \
    --eval-dir "out/SwordsAndWizardry/SW_Complete_Revised/SW Complete Revised PDF"
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.gates_b import gate_orphan_after_toc, gate_toc_binding_coverage
from extraction.pipeline import run_join_pass_and_gate
from extraction.schemas import EvidenceUnit
from extraction.toc_binder import run_toc_binding_pass
from extraction.toc_parser import (
    detect_toc_pages,
    reconstruct_hierarchy,
    write_toc_artifacts,
)


def _load_env_development() -> None:
    env_path = REPO_ROOT.parent / ".env.development"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value


def _parse_page_number(dir_name: str) -> int | None:
    import re
    m = re.search(r"_p(\d+)$", dir_name)
    return int(m.group(1)) if m else None


def _load_units_by_page(eval_dir: Path, stem: str) -> list[list[EvidenceUnit]]:
    page_entries: list[tuple[int, list[EvidenceUnit]]] = []
    for page_dir in eval_dir.iterdir():
        if not page_dir.is_dir():
            continue
        if not page_dir.name.startswith(f"{stem}_p"):
            continue
        page_num = _parse_page_number(page_dir.name)
        if page_num is None:
            continue
        units_path = page_dir / "stageB.evidence_units.json"
        if not units_path.exists():
            continue
        data = json.loads(units_path.read_text(encoding="utf-8"))
        units = [EvidenceUnit.from_dict(u) for u in data.get("units", [])]
        page_entries.append((page_num, units))
    page_entries.sort(key=lambda x: x[0])
    return [entry[1] for entry in page_entries]


def main() -> None:
    _load_env_development()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    import argparse
    parser = argparse.ArgumentParser(description="Validate TOC enrichment on existing Mark III output.")
    parser.add_argument("--eval-dir", type=Path, required=True, help="Path to evaluation output directory (e.g. out/.../SW Complete Revised PDF)")
    parser.add_argument("--skip-llm", action="store_true", help="Use flat fallback hierarchy (no LLM call)")
    args = parser.parse_args()

    eval_dir = args.eval_dir.resolve()
    stem = eval_dir.name
    if not eval_dir.exists():
        print(f"Error: eval dir not found: {eval_dir}", file=sys.stderr)
        sys.exit(1)

    total_page_dirs = sum(
        1 for d in eval_dir.iterdir()
        if d.is_dir() and _parse_page_number(d.name) is not None
    )

    print("=" * 70)
    print(f"TOC Structural Enrichment Validation")
    print(f"Eval dir: {eval_dir}")
    print(f"Stem: {stem}")
    print(f"Page dirs: {total_page_dirs}")
    print("=" * 70)

    # --- Pre-enrichment baseline ---
    print("\n--- Pre-enrichment baseline ---")
    pre_units = _load_units_by_page(eval_dir, stem)
    pre_flat = [u for page in pre_units for u in page]
    pre_orphans = sum(1 for u in pre_flat if not u.structural_path)
    pre_depths = [len(u.structural_path) for u in pre_flat]
    pre_unique_paths = len(set(tuple(u.structural_path) for u in pre_flat))
    print(f"  Total units: {len(pre_flat)}")
    print(f"  Orphans (empty path): {pre_orphans} ({pre_orphans / len(pre_flat) * 100:.1f}%)")
    if pre_depths:
        depth_counter = Counter(pre_depths)
        print(f"  Path depth distribution: {dict(sorted(depth_counter.items()))}")
        print(f"  Median depth: {statistics.median(pre_depths):.0f}")
    print(f"  Unique paths: {pre_unique_paths}")

    # --- Step 1: TOC Detection ---
    print("\n--- Step 1: TOC Detection ---")
    detection = detect_toc_pages(eval_dir, stem)
    print(f"  Found: {detection.found}")
    print(f"  Score: {detection.score:.2f}")
    print(f"  Pages: {detection.toc_pages}")
    print(f"  Entries: {len(detection.entries)}")
    if detection.entries:
        for e in detection.entries[:5]:
            print(f"    {e.title} ..... {e.page_num}")
        if len(detection.entries) > 5:
            print(f"    ... ({len(detection.entries) - 5} more)")

    if not detection.found:
        print("\nTOC not found — cannot proceed with enrichment.")
        write_toc_artifacts(eval_dir, detection)
        sys.exit(0)

    # --- Step 2: TOC Hierarchy ---
    print("\n--- Step 2: TOC Hierarchy ---")
    if args.skip_llm:
        from extraction.toc_parser import build_flat_hierarchy
        toc_tree = build_flat_hierarchy(detection.entries)
        hierarchy_method = "flat_fallback"
    else:
        toc_tree, hierarchy_method = reconstruct_hierarchy(detection.entries)
    total_nodes = sum(len(n.all_nodes_flat()) for n in toc_tree)
    print(f"  Method: {hierarchy_method}")
    print(f"  Top-level nodes: {len(toc_tree)}")
    print(f"  Total nodes: {total_nodes}")

    write_toc_artifacts(eval_dir, detection, toc_tree, hierarchy_method)
    print(f"  Artifacts written to: {eval_dir}")

    # --- Step 3: TOC Binding ---
    print("\n--- Step 3: TOC Binding ---")
    summary = run_toc_binding_pass(eval_dir, stem, toc_tree, total_page_dirs)
    print(f"  Pages processed: {summary['pages_processed']}")
    print(f"  Units bound: {summary['total_units_bound']}")
    print(f"  Units unbound: {summary['total_units_unbound']}")
    print(f"  Table captions: {summary['total_table_captions']}")

    # --- Step 4: Rebuild joined corpus ---
    print("\n--- Step 4: Rebuild joined corpus ---")
    post_units = _load_units_by_page(eval_dir, stem)
    if len(post_units) >= 2:
        joined_units, join_diags = run_join_pass_and_gate(post_units)
        join_passed = all(g.passed for g in join_diags)
        input_count = sum(len(p) for p in post_units)
        print(f"  Input units: {input_count}")
        print(f"  Joined units: {len(joined_units)}")
        print(f"  Join gate: {'PASS' if join_passed else 'FAIL'}")

        joined_path = eval_dir / "joined.evidence_units.json"
        joined_path.write_text(
            json.dumps({"units": [u.to_dict() for u in joined_units]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Written: {joined_path}")

        # TOC gates
        toc_cov = gate_toc_binding_coverage(joined_units)
        orph_gate = gate_orphan_after_toc(joined_units)
        print(f"  TOC coverage: {toc_cov.detail.get('coverage', 0):.1%} ({'PASS' if toc_cov.passed else 'FAIL'})")
        print(f"  Orphan after TOC: {orph_gate.detail.get('orphan_rate', 0):.1%} ({'PASS' if orph_gate.passed else 'FAIL'})")
    else:
        joined_units = post_units[0] if post_units else []

    # --- Step 5: Post-enrichment summary ---
    print("\n--- Post-enrichment summary ---")
    post_flat = joined_units if isinstance(joined_units, list) else []
    post_orphans = sum(1 for u in post_flat if not u.structural_path)
    post_depths = [len(u.structural_path) for u in post_flat]
    post_unique_paths = len(set(tuple(u.structural_path) for u in post_flat))
    print(f"  Total units: {len(post_flat)}")
    print(f"  Orphans (empty path): {post_orphans} ({post_orphans / len(post_flat) * 100:.1f}%)" if post_flat else "  No units")
    if post_depths:
        depth_counter = Counter(post_depths)
        print(f"  Path depth distribution: {dict(sorted(depth_counter.items()))}")
        print(f"  Median depth: {statistics.median(post_depths):.0f}")
    print(f"  Unique paths: {post_unique_paths}")

    # Delta
    print("\n--- Delta ---")
    print(f"  Orphan rate: {pre_orphans / len(pre_flat) * 100:.1f}% -> {post_orphans / len(post_flat) * 100:.1f}%" if post_flat else "  N/A")
    if pre_depths and post_depths:
        print(f"  Median depth: {statistics.median(pre_depths):.0f} -> {statistics.median(post_depths):.0f}")
    print(f"  Unique paths: {pre_unique_paths} -> {post_unique_paths}")

    # Check for Cleric table specifically
    cleric_table = [u for u in post_flat if u.unit_type == "table" and "cleric" in u.text.lower()[:200]]
    if cleric_table:
        ct = cleric_table[0]
        print(f"\n  Cleric Advancement Table:")
        print(f"    Path: {ct.structural_path}")
        print(f"    Caption: {(ct.join_metadata or {}).get('table_title', 'none')}")
    else:
        print("\n  Cleric Advancement Table: NOT FOUND")

    print("\n" + "=" * 70)
    print("Validation complete.")


if __name__ == "__main__":
    main()
