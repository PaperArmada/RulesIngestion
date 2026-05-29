"""Interactive CLI for hand-labeling benchmark queries with intended buckets.

Loads a retrieval benchmark JSON (list of {id, question, ...}) and walks the
operator through assigning a bucket to each. Saves to a side JSON keyed by
query id so subsequent eval can compare classifier output to gold.

Usage:
  uv run python -m tinker.scripts.label_classifier_sample \\
      --benchmark evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_atomic_rules_benchmark.v3_swcr_merged2000_min100.json \\
      --out out/tinker/swcr/classifier_gold.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.routing.buckets import BUCKETS  # noqa: E402


def _print_bucket_menu() -> None:
    print()
    print("Buckets:")
    for i, b in enumerate(BUCKETS, start=1):
        print(f"  {i}. {b.id}  -- {b.name}")
        print(f"     {b.definition[:120]}{'...' if len(b.definition) > 120 else ''}")
    print()
    print(
        "Enter a number (1-{}), 'd' for definitions, 's' to skip, "
        "'q' to save and quit, '!' to redo last".format(len(BUCKETS))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Hand-label benchmark queries with buckets.")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start", type=int, default=0, help="Skip first N queries.")
    parser.add_argument("--limit", type=int, default=None, help="Label at most N queries.")
    args = parser.parse_args()

    raw = json.loads(args.benchmark.read_text())
    queries = raw if isinstance(raw, list) else raw.get("queries") or raw.get("benchmark") or []
    if not isinstance(queries, list) or not queries:
        print("ERROR: benchmark queries not found (expected list at top level "
              "or under key 'queries'/'benchmark')", file=sys.stderr)
        return 2

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if out_path.is_file():
        existing = json.loads(out_path.read_text())
        print(f"Resuming: {len(existing)} queries already labeled in {out_path}")

    _print_bucket_menu()
    end_idx = len(queries) if args.limit is None else min(
        len(queries), args.start + args.limit
    )
    history: list[str] = []
    try:
        for i in range(args.start, end_idx):
            q = queries[i]
            qid = q.get("id") or f"q{i}"
            if qid in existing:
                continue
            print(f"\n[{i + 1}/{end_idx}]  id={qid}")
            qtype = q.get("question_type", "?")
            tier = q.get("tier", "?")
            print(f"  type={qtype} tier={tier}")
            print(f"  Q: {q.get('question', '')}")
            while True:
                raw = input("bucket? ").strip()
                if not raw:
                    continue
                if raw == "q":
                    raise KeyboardInterrupt
                if raw == "s":
                    print("  (skipped)")
                    break
                if raw == "d":
                    _print_bucket_menu()
                    continue
                if raw == "!":
                    if not history:
                        print("  no previous label to undo")
                        continue
                    last_id = history.pop()
                    existing.pop(last_id, None)
                    print(f"  removed label for {last_id}; re-enter at next save")
                    continue
                try:
                    n = int(raw)
                    if not 1 <= n <= len(BUCKETS):
                        raise ValueError
                except ValueError:
                    print(f"  ?? expected 1..{len(BUCKETS)} or d/s/q/!")
                    continue
                chosen = BUCKETS[n - 1].id
                existing[qid] = chosen
                history.append(qid)
                print(f"  -> {chosen}")
                break
    except (KeyboardInterrupt, EOFError):
        print("\nSaving and exiting...")

    out_path.write_text(json.dumps(existing, indent=2, sort_keys=True))
    print(f"Wrote {len(existing)} labels to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
