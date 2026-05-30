"""Run schema-free facet discovery over a corpus and validate it.

Prints the discovered enumerable facet channels ranked by enumerability, then
validates that discovery recovers the facets we found by hand in
`tinker/eval/enumeration_gold.py` (the hand set is now a validation fixture):
for each hand query, check that some discovered channel reproduces its gold set
(Jaccard against the channel's matching value).

Usage:
  uv run python -m tinker.scripts.discover_facets \
      --substrate-dir out/swcr --document-id Swords_Wizardry \
      --out out/tinker/swcr/facets.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.eval.enumeration_gold import QUERIES  # noqa: E402
from tinker.introspect.facets import channel_key, discover_facets  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-coverage-floor", type=int, default=6)
    ap.add_argument("--min-coverage-frac", type=float, default=0.015)
    ap.add_argument("--max-cardinality", type=int, default=30)
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    units = load_corpus(args.substrate_dir, args.document_id)
    print(f"Loaded {len(units)} units. Discovering facets (schema-free)...\n")

    facets = discover_facets(
        units, min_coverage_floor=args.min_coverage_floor,
        min_coverage_frac=args.min_coverage_frac, max_cardinality=args.max_cardinality
    )

    eff = max(args.min_coverage_floor, round(args.min_coverage_frac * len(units)))
    print(f"Discovered {len(facets)} qualified facet channels "
          f"(effective min_coverage={eff} = max({args.min_coverage_floor}, "
          f"{args.min_coverage_frac}*{len(units)}), max_cardinality={args.max_cardinality}):\n")
    print(f"{'channel':<32s} {'card':>4s} {'cover':>5s} {'score':>7s}  top values")
    print("-" * 90)
    for ch in facets[: args.top]:
        top_vals = sorted(ch.values.items(), key=lambda kv: -len(kv[1]))[:6]
        tv = ", ".join(f"{v}({len(ids)})" for v, ids in top_vals)
        print(f"{channel_key(ch):<32s} {ch.cardinality:>4d} {ch.coverage:>5d} "
              f"{ch.enumerability():>7.1f}  {tv[:50]}")

    # --- Validation: does discovery recover the hand-found facets? ---
    # Build a lookup: (label_lower, token) -> unit_id set, across all channels.
    val_index: dict[tuple[str, str, str], set[str]] = {}
    for ch in facets:
        for v, ids in ch.values.items():
            val_index[(ch.label.lower(), ch.token_type, v)] = set(ids)

    print("\n" + "=" * 90)
    print("VALIDATION: can discovered channels reproduce the hand-authored gold sets?")
    print("=" * 90)
    # Map hand metadata fields to expected (token_type) for matching.
    # spell_levels -> ordinal under a 'Spell Level' label; classes -> bareword.
    from tinker.eval.enumeration_gold import apply_query
    sp_units = {u.id: u.text for u in units}
    # Recompute hand gold from metadata for comparison.
    sp_portrait = json.loads(
        (args.substrate_dir.parent / "tinker/swcr/corpus_self_portrait.json").read_text()
    ) if (args.substrate_dir.parent / "tinker/swcr/corpus_self_portrait.json").exists() else None

    best_recoveries = []
    for q in QUERIES:
        # Hand gold from metadata index if available; else skip.
        if sp_portrait is None:
            continue
        gold = set(apply_query(sp_portrait["metadata_index"]["by_unit"], q))
        # Find the discovered channel-value whose set best matches this gold.
        best_j, best_desc = 0.0, "(none)"
        for (label_l, ttype, v), ids in val_index.items():
            j = _jaccard(gold, ids)
            if j > best_j:
                best_j, best_desc = j, f"{label_l}/{ttype}={v}"
        best_recoveries.append((q.id, len(gold), best_j, best_desc))
        print(f"  {q.id:<26s} |gold|={len(gold):>3d}  best_jaccard={best_j:.2f}  via {best_desc}")

    if best_recoveries:
        mean_j = sum(r[2] for r in best_recoveries) / len(best_recoveries)
        print(f"\n  mean best-Jaccard across {len(best_recoveries)} hand facets: {mean_j:.2f}")
        print("  (1.00 = discovery reproduces the hand set exactly; "
              "low values = a facet discovery missed or split)")

    out = {
        "channels": [
            {
                "channel": channel_key(ch),
                "label": ch.label,
                "token_type": ch.token_type,
                "cardinality": ch.cardinality,
                "coverage": ch.coverage,
                "enumerability": ch.enumerability(),
                "values": {v: ids for v, ids in ch.values.items()},
            }
            for ch in facets
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {len(facets)} channels to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
