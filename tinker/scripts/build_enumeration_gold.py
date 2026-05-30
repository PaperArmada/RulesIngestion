"""Build + human-verify the enumeration gold from the corpus metadata index.

Computes each query's complete gold set by applying its canonical predicate to
`corpus_self_portrait.json` metadata_index.by_unit, writes
`enumeration_gold.json`, and prints per-query counts plus sample matched-unit
text so a human (or LLM-as-judge) can spot-check that the metadata-derived set
actually corresponds to the intended content.

Usage:
  uv run python -m tinker.scripts.build_enumeration_gold \
      --corpus-dir out/tinker/swcr \
      --substrate-dir out/swcr \
      --document-id Swords_Wizardry \
      --out out/tinker/swcr/enumeration_gold.json \
      --sample 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.eval.enumeration_gold import QUERIES, build_gold  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sample", type=int, default=3,
                    help="matched units to print per query for verification")
    args = ap.parse_args()

    sp = json.loads((args.corpus_dir / "corpus_self_portrait.json").read_text())
    by_unit = sp["metadata_index"]["by_unit"]
    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}

    gold = build_gold(by_unit)

    print(f"Built enumeration gold for {len(QUERIES)} queries "
          f"over {len(by_unit)} metadata-bearing units.\n")
    print(f"{'query_id':<26s} {'size':>5s}  dimensions")
    print("-" * 70)
    for q in QUERIES:
        g = gold[q.id]
        print(f"{q.id:<26s} {g['set_size']:>5d}  {','.join(g['dimensions'])}")

    print("\n" + "=" * 70)
    print("SPOT-CHECK: sample matched units per query (verify they truly match)")
    print("=" * 70)
    for q in QUERIES:
        g = gold[q.id]
        print(f"\n### {q.id}  ({g['set_size']} units)  — {q.question}")
        print(f"    predicate: {g['predicate']['clauses']}")
        if g["set_size"] == 0:
            print("    !! EMPTY SET — predicate likely wrong; investigate")
            continue
        for uid in g["gold_unit_ids"][: args.sample]:
            txt = " ".join(unit_text_by_id.get(uid, "(no text)").split())
            print(f"    - [{uid[:10]}] {txt[:160]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(gold, indent=2))
    sizes = [g["set_size"] for g in gold.values()]
    print("\n" + "=" * 70)
    print(f"Wrote {args.out}")
    print(f"set sizes: min={min(sizes)} max={max(sizes)} "
          f"mean={sum(sizes)/len(sizes):.1f}  "
          f"(all should exceed a top-K of 20 to make the paradigm contrast real)")
    empties = [qid for qid, g in gold.items() if g["set_size"] == 0]
    if empties:
        print(f"WARNING: empty gold sets: {empties}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
