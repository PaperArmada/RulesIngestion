"""Verify a Stage A+B substrate by loading EvidenceUnits and reporting shape.

Use after ingestion to confirm the output is usable for downstream work.

Usage:
  uv run python -m tinker.scripts.check_substrate --substrate-dir out/swcr --document-id Swords_Wizardry
"""

from __future__ import annotations

import argparse
import collections
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from retrieval_lab.substrate_loader import load_evidence_units  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanity-check a Stage B substrate.")
    parser.add_argument(
        "--substrate-dir",
        type=Path,
        required=True,
        help="Path containing <stem>_p*/ page dirs with stageB.evidence_units.json.",
    )
    parser.add_argument(
        "--document-id",
        type=str,
        default="unknown",
        help="Document ID tag (used by the loader).",
    )
    parser.add_argument(
        "--min-units",
        type=int,
        default=200,
        help="Fail if fewer than this many units are found.",
    )
    args = parser.parse_args()

    substrate_dir = args.substrate_dir.resolve()
    if not substrate_dir.is_dir():
        print(f"ERROR: not a directory: {substrate_dir}", file=sys.stderr)
        return 2

    try:
        units = load_evidence_units(substrate_dir, args.document_id)
    except Exception as exc:
        print(f"ERROR: load_evidence_units raised {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2

    if not units:
        print("ERROR: zero units loaded", file=sys.stderr)
        return 1

    type_counts: collections.Counter[str] = collections.Counter()
    depth_counts: collections.Counter[int] = collections.Counter()
    text_lens: list[int] = []
    empty_text = 0
    pages = set()

    for u in units:
        type_counts[u.get("unit_type", "?")] += 1
        sp = u.get("structural_path") or []
        depth_counts[len(sp)] += 1
        text = (u.get("text") or "").strip()
        text_lens.append(len(text))
        if not text:
            empty_text += 1
        if "page" in u:
            pages.add(u["page"])

    print(f"Substrate: {substrate_dir}")
    print(f"Document:  {args.document_id}")
    print(f"Units:     {len(units)}")
    if pages:
        print(f"Pages:     {len(pages)} unique")
    print()

    print("unit_type distribution:")
    for t, n in sorted(type_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t:<10s} {n:5d}  ({n / len(units):5.1%})")
    print()

    print("structural_path depth distribution:")
    for d in sorted(depth_counts):
        n = depth_counts[d]
        print(f"  depth={d}: {n:5d}  ({n / len(units):5.1%})")
    print()

    print("text length stats (chars):")
    if text_lens:
        text_lens_sorted = sorted(text_lens)
        p = lambda q: text_lens_sorted[max(0, int(q * len(text_lens_sorted)) - 1)]
        print(
            f"  min={min(text_lens)} p25={p(0.25)} median={statistics.median(text_lens)} "
            f"p75={p(0.75)} p95={p(0.95)} max={max(text_lens)}"
        )
    print(f"  empty_text_units: {empty_text}")
    print()

    print("Sample units:")
    for u in units[:3]:
        text = (u.get("text") or "")
        text_preview = text[:120].replace("\n", " ")
        print(f"  [{u.get('id', '?')[:12]}] type={u.get('unit_type')} "
              f"path={u.get('structural_path')[:3]}")
        print(f"    text: {text_preview}...")
    print()

    if len(units) < args.min_units:
        print(f"FAIL: only {len(units)} units (min={args.min_units})", file=sys.stderr)
        return 1
    if empty_text > len(units) * 0.05:
        print(f"WARN: {empty_text} units have empty text (>{5}% threshold)")

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
