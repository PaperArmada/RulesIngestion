"""Enumeration route eval: set-F1 vs raw_dense, on paraphrased queries.

Tests the M7 thesis: does routing set-completion queries to a facet-scan beat
top-K similarity? Reports:
  - set precision/recall/F1 + exact-set-match for the enumeration route vs
    raw_dense at top-K=20 and at top-|gold| (a generous similarity ceiling);
  - facet-resolution accuracy (did the resolver pick the gold channel+value);
  - form-detection on enumeration queries (should fire) vs non-enumeration
    negatives from the atomic benchmark (should not).

Queries are the PARAPHRASES (run paraphrase_enumeration_gold first), so facet
resolution is tested on phrasing it didn't generate from.

Usage:
  TINKER_LLM_BACKEND=gemini uv run python -m tinker.scripts.run_enumeration_eval \
      --gold out/tinker/swcr/enumeration_autogen_gold.json \
      --facets out/tinker/swcr/facets.json \
      --negatives evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_atomic_rules_benchmark.v3_swcr_merged2000_min100.json \
      --corpus-dir out/tinker/swcr --substrate-dir out/swcr --document-id Swords_Wizardry \
      --out out/tinker/swcr/runs/m7_enumeration
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.eval.enumeration_metrics import set_scores  # noqa: E402
from tinker.eval.harness import run_raw_dense_baseline  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.routing.enumeration import is_enumeration_form, run_enumeration  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def _mean(xs):
    return statistics.mean(xs) if xs else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--facets", type=Path, required=True)
    ap.add_argument("--negatives", type=Path, required=True)
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--use-paraphrase", action="store_true", default=True)
    args = ap.parse_args()

    gold = json.loads(args.gold.read_text())
    facets = json.loads(args.facets.read_text())["channels"]
    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    dense = DenseIndex.load(args.corpus_dir / "embeddings")

    rows = []
    for qid, e in gold.items():
        q = e.get("question_paraphrase") or e["question"]
        gold_set = set(e["gold_unit_ids"])

        r = run_enumeration(q, facets=facets, unit_text_by_id=unit_text_by_id)
        enum_set = {c["id"] for c in r.top_k}
        enum_scores = set_scores(enum_set, gold_set)

        # raw_dense at top-20 and at top-|gold| (generous ceiling).
        ids20, _, _ = run_raw_dense_baseline(
            q, dense_index=dense, unit_text_by_id=unit_text_by_id,
            top_k=20, candidate_pool=max(50, len(gold_set)), rerank=True,
        )
        rd20 = set_scores(set(ids20), gold_set)
        idsN, _, _ = run_raw_dense_baseline(
            q, dense_index=dense, unit_text_by_id=unit_text_by_id,
            top_k=len(gold_set), candidate_pool=max(50, len(gold_set)), rerank=True,
        )
        rdN = set_scores(set(idsN), gold_set)

        resolution_correct = (
            r.debug.get("resolved_channel") == e["channel"]
            and str(r.debug.get("resolved_value")) == str(e["value"])
        )
        rows.append({
            "qid": qid, "query": q, "channel": e["channel"], "value": e["value"],
            "gold_size": len(gold_set),
            "enum": enum_scores, "rd20": rd20, "rdN": rdN,
            "resolution_correct": resolution_correct,
            "form_detected": is_enumeration_form(q),
            "status": r.debug.get("status"),
        })
        print(f"  {qid:<34s} F1 enum={enum_scores['f1']:.2f} "
              f"rd@20={rd20['f1']:.2f} rd@N={rdN['f1']:.2f}  "
              f"resolve={'ok' if resolution_correct else 'MISS'} "
              f"({r.debug.get('status')})", flush=True)

    # Negatives: atomic benchmark queries should NOT be enumeration-form.
    neg_raw = json.loads(args.negatives.read_text())
    neg_qs = neg_raw if isinstance(neg_raw, list) else neg_raw.get("queries", [])
    neg_form_fired = sum(1 for q in neg_qs if is_enumeration_form(q.get("question", "")))

    enum_f1 = [r["enum"]["f1"] for r in rows]
    rd20_f1 = [r["rd20"]["f1"] for r in rows]
    rdN_f1 = [r["rdN"]["f1"] for r in rows]
    resolved = sum(1 for r in rows if r["resolution_correct"])
    exact = sum(1 for r in rows if r["enum"]["exact"] == 1.0)

    print("\n" + "=" * 78)
    print(f"ENUMERATION EVAL  (n={len(rows)} queries, paraphrased)")
    print("-" * 78)
    print(f"  mean set-F1   enumeration route : {_mean(enum_f1):.3f}")
    print(f"  mean set-F1   raw_dense @ top-20 : {_mean(rd20_f1):.3f}")
    print(f"  mean set-F1   raw_dense @ top-|gold| (ceiling): {_mean(rdN_f1):.3f}")
    print(f"  exact-set-match (enumeration)    : {exact}/{len(rows)}")
    print(f"  facet-resolution accuracy        : {resolved}/{len(rows)}")
    print("-" * 78)
    print(f"  form-detection on {len(rows)} enum queries  : "
          f"{sum(1 for r in rows if r['form_detected'])}/{len(rows)} fired (want all)")
    print(f"  form-detection on {len(neg_qs)} non-enum negs: "
          f"{neg_form_fired}/{len(neg_qs)} fired (want ~0)")
    print("=" * 78)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "enumeration_results.json").write_text(json.dumps({
        "summary": {
            "n": len(rows),
            "enum_f1": _mean(enum_f1),
            "rd20_f1": _mean(rd20_f1),
            "rdN_f1": _mean(rdN_f1),
            "exact_set_match": exact,
            "resolution_correct": resolved,
            "form_fired_on_enum": sum(1 for r in rows if r["form_detected"]),
            "form_fired_on_negatives": neg_form_fired,
            "n_negatives": len(neg_qs),
        },
        "per_query": rows,
    }, indent=2))
    print(f"Wrote {args.out}/enumeration_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
