"""Add a natural-language paraphrase to each auto-generated enumeration query.

Eval prep, run once and persisted: the facet resolver is then tested on phrasing
it did not generate from, so a passing result reflects semantic resolution, not
template reversal. Gold (channel, value, gold_unit_ids) is unchanged.

Usage:
  TINKER_LLM_BACKEND=gemini uv run python -m tinker.scripts.paraphrase_enumeration_gold \
      --gold out/tinker/swcr/enumeration_autogen_gold.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker import llm as tinker_llm  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, required=True)
    args = ap.parse_args()

    gold = json.loads(args.gold.read_text())
    n = len(gold)
    for i, (qid, entry) in enumerate(gold.items(), 1):
        para = tinker_llm.paraphrase_query(entry["question"])
        entry["question_paraphrase"] = para
        print(f"[{i}/{n}] {qid}\n    template:   {entry['question']}\n"
              f"    paraphrase: {para}", flush=True)

    args.gold.write_text(json.dumps(gold, indent=2))
    print(f"\nWrote paraphrases into {args.gold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
