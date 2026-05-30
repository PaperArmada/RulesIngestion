"""Build the auto-generated enumeration eval from discovered facets.

Pipeline: load corpus -> discover_facets (schema-free) -> generate_queries
(templated NL + facet-membership gold) -> write JSON. Corpus-agnostic: the same
command run against a different substrate emits that corpus's enumeration eval.

Usage:
  uv run python -m tinker.scripts.build_autogen_enumeration_gold \
      --substrate-dir out/swcr --document-id Swords_Wizardry \
      --out out/tinker/swcr/enumeration_autogen_gold.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.eval.enumeration_autogen import generate_queries, to_gold_dict  # noqa: E402
from tinker.introspect.facets import discover_facets  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-coverage-floor", type=int, default=6)
    ap.add_argument("--min-coverage-frac", type=float, default=0.015)
    ap.add_argument("--max-cardinality", type=int, default=30)
    ap.add_argument("--min-set-size", type=int, default=8)
    ap.add_argument("--values-per-channel", type=int, default=3)
    ap.add_argument("--max-queries", type=int, default=40)
    args = ap.parse_args()

    units = load_corpus(args.substrate_dir, args.document_id)
    facets = discover_facets(
        units, min_coverage_floor=args.min_coverage_floor,
        min_coverage_frac=args.min_coverage_frac, max_cardinality=args.max_cardinality
    )
    queries = generate_queries(
        facets,
        min_set_size=args.min_set_size,
        values_per_channel=args.values_per_channel,
        max_queries=args.max_queries,
    )

    print(f"Loaded {len(units)} units -> {len(facets)} facet channels "
          f"-> {len(queries)} auto-generated enumeration queries.\n")
    print(f"{'query_id':<40s} {'size':>4s}  channel")
    print("-" * 80)
    for q in queries:
        print(f"{q.id:<40s} {q.set_size:>4d}  {q.channel}")
        print(f"    \"{q.question}\"")

    gold = to_gold_dict(queries)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(gold, indent=2))

    sizes = [q.set_size for q in queries]
    channels = sorted({q.channel for q in queries})
    print("\n" + "=" * 80)
    print(f"Wrote {len(queries)} queries across {len(channels)} channels to {args.out}")
    print(f"set sizes: min={min(sizes)} max={max(sizes)} mean={sum(sizes)/len(sizes):.1f}")
    above_20 = sum(1 for s in sizes if s > 20)
    print(f"{above_20}/{len(sizes)} queries have |set| > 20 "
          f"(where top-K=20 similarity is structurally capped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
