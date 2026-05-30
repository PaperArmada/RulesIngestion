"""Build a high-recall LLM glossary (the proper HyDE bridge, M9).

The M1 glossary was a regex grab-bag (low recall, noise, missing the rule
concepts the failing HyDE queries needed). This re-extracts term->definition
pairs with the LLM over every unit, so the shape prior can carry the corpus's
actual rule vocabulary WITH definitions.

Runs with think=False for speed. Dedupes by lowercased term, keeping the
longest definition. Writes a glossary block compatible with the self-portrait
(terms: [{term, definition, source_unit_id, source:'llm'}]).

Usage:
  TINKER_LLM_BACKEND=gemini uv run python -m tinker.scripts.build_llm_glossary \
      --substrate-dir out/swcr --document-id Swords_Wizardry \
      --out out/tinker/swcr/glossary_llm.json --min-chars 200
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker import llm as tinker_llm  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-chars", type=int, default=200,
                    help="skip units shorter than this (stat-block noise)")
    args = ap.parse_args()

    units = load_corpus(args.substrate_dir, args.document_id)
    candidates = [u for u in units if len(u.text or "") >= args.min_chars]
    print(f"{len(units)} units, {len(candidates)} pass min-chars={args.min_chars}", flush=True)

    by_term: dict[str, dict] = {}
    acronyms: dict[str, dict] = {}
    t0 = time.perf_counter()
    errors = 0
    for i, u in enumerate(candidates, 1):
        try:
            parsed = tinker_llm.extract_glossary(u.text, think=False)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  [{i}] error: {type(e).__name__}: {str(e)[:80]}", flush=True)
            continue
        for t in parsed.get("terms", []):
            term = str(t.get("term", "")).strip()
            defn = str(t.get("definition", "")).strip()
            if not term or not defn:
                continue
            key = term.lower()
            if key not in by_term or len(defn) > len(by_term[key]["definition"]):
                by_term[key] = {"term": term, "definition": defn,
                                "source_unit_id": u.id, "source": "llm"}
        for a in parsed.get("acronyms", []):
            ac = str(a.get("acronym", "")).strip()
            ex = str(a.get("expansion", "")).strip()
            if ac and ex and ac.lower() not in acronyms:
                acronyms[ac.lower()] = {"acronym": ac, "expansion": ex, "source_unit_id": u.id}
        if i % 50 == 0:
            rate = i / (time.perf_counter() - t0)
            print(f"  [{i}/{len(candidates)}] terms={len(by_term)} "
                  f"acronyms={len(acronyms)} ({rate:.1f}/s)", flush=True)

    glossary = {
        "terms": sorted(by_term.values(), key=lambda d: d["term"].lower()),
        "acronyms": sorted(acronyms.values(), key=lambda d: d["acronym"].lower()),
        "stats": {"terms": len(by_term), "acronyms": len(acronyms),
                  "units_scanned": len(candidates), "errors": errors,
                  "source": "llm"},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(glossary, indent=2))
    print(f"\nWrote {len(by_term)} terms + {len(acronyms)} acronyms to {args.out} "
          f"({errors} errors) in {time.perf_counter()-t0:.0f}s", flush=True)
    # Coverage probe vs the rule concepts the failing HyDE queries needed
    allterms = " | ".join(d["term"].lower() for d in by_term.values())
    print("coverage of failing-query concepts:")
    for probe in ["subdual", "morale", "reaction", "negotiation", "recover", "rest", "wound", "surprise"]:
        print(f"  {probe}: {probe in allterms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
