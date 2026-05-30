"""M8: cross-reference route eval — crossref vs dense vs BM25, by mode.

Builds the crossref graph (re-seeded on the LLM glossary), auto-generates queries
(references = 1-hop reverse; depends_on = transitive forward closure), then
compares set-F1 of:
  - crossref traversal (resolve node+mode -> traverse)
  - dense @ top-|gold|   (similarity)
  - BM25  @ top-|gold|   (lexical)

The three-way comparison is the honesty point: for "references" (mention-
membership) we expect crossref ~ BM25 >> dense (it's lexical, not novel); for
"depends_on" (transitive) we expect crossref >> both (only a graph can do it).

Queries are PARAPHRASED (run paraphrase_enumeration_gold on the gold first).

Usage:
  TINKER_LLM_BACKEND=gemini uv run python -m tinker.scripts.run_crossref_eval \
      --glossary tinker/data/swcr_glossary_llm.json \
      --corpus-dir out/tinker/swcr --substrate-dir out/swcr --document-id Swords_Wizardry \
      --gold-out out/tinker/swcr/crossref_autogen_gold.json \
      --out out/tinker/swcr/runs/m8_crossref --build-gold
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker import llm as tinker_llm  # noqa: E402
from tinker.eval.crossref_autogen import generate_queries, to_gold_dict  # noqa: E402
from tinker.eval.enumeration_metrics import set_scores  # noqa: E402
from tinker.introspect.crossref import build_crossref_graph  # noqa: E402
from tinker.introspect.crossref_graph import build_graph  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.retrieve.sparse import SparseIndex  # noqa: E402
from tinker.routing.crossref import run_crossref  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def _mean(xs):
    return statistics.mean(xs) if xs else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glossary", type=Path, required=True)
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--gold-out", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--build-gold", action="store_true")
    args = ap.parse_args()

    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    glossary = json.loads(args.glossary.read_text())["terms"]
    cr = build_crossref_graph(units, glossary)
    graph = build_graph({"crossref": cr}, n_units=len(units))
    node_catalog = [t for t in graph.enumerable_terms()][:80]
    print(f"crossref graph: {cr['stats']}; node catalog={len(node_catalog)}", flush=True)

    if args.build_gold or not args.gold_out.exists():
        queries = generate_queries(graph)
        gold = to_gold_dict(queries)
        args.gold_out.parent.mkdir(parents=True, exist_ok=True)
        args.gold_out.write_text(json.dumps(gold, indent=2))
        print(f"generated {len(gold)} crossref queries -> {args.gold_out}", flush=True)
        print("NOTE: run paraphrase_enumeration_gold on it, then re-run with no "
              "--build-gold to eval on paraphrases.", flush=True)
        # still proceed to eval on templated questions if no paraphrase yet
    gold = json.loads(args.gold_out.read_text())

    dense = DenseIndex.load(args.corpus_dir / "embeddings")
    sparse = SparseIndex.load(args.corpus_dir / "bm25_index.pkl")

    rows = []
    for qid, e in gold.items():
        q = e.get("question_paraphrase") or e["question"]
        gset = set(e["gold_unit_ids"])
        if not gset:
            continue
        r = run_crossref(q, graph=graph, node_catalog=node_catalog,
                         unit_text_by_id=unit_text_by_id)
        xref = {c["id"] for c in r.top_k}

        qvec = tinker_llm.embed([q])[0]
        d_ids, _ = dense.search(qvec, top_k=len(gset))
        b_ids, _ = sparse.search(q, top_k=len(gset))

        rows.append({
            "qid": qid, "mode": e["mode"], "node": e["node"], "gold_size": len(gset),
            "crossref_f1": set_scores(xref, gset)["f1"],
            "dense_f1": set_scores(set(d_ids), gset)["f1"],
            "bm25_f1": set_scores(set(b_ids), gset)["f1"],
            "resolution_ok": (r.debug.get("node") == e["node"]
                              and r.debug.get("mode") == e["mode"]),
            "status": r.debug.get("status"),
        })
        print(f"  {qid:<34s} [{e['mode']:<10s}] xref={rows[-1]['crossref_f1']:.2f} "
              f"dense={rows[-1]['dense_f1']:.2f} bm25={rows[-1]['bm25_f1']:.2f} "
              f"resolve={'ok' if rows[-1]['resolution_ok'] else 'MISS'}", flush=True)

    def agg(mode):
        sub = [r for r in rows if mode is None or r["mode"] == mode]
        if not sub:
            return None
        return {"n": len(sub),
                "crossref": _mean([r["crossref_f1"] for r in sub]),
                "dense": _mean([r["dense_f1"] for r in sub]),
                "bm25": _mean([r["bm25_f1"] for r in sub]),
                "resolved": sum(1 for r in sub if r["resolution_ok"])}

    print("\n" + "=" * 76)
    print(f"{'segment':<16s} {'n':>3s} {'crossref':>9s} {'dense':>7s} {'bm25':>7s} {'resolve':>8s}")
    print("-" * 76)
    for label, mode in (("ALL", None), ("references", "references"), ("depends_on", "depends_on")):
        a = agg(mode)
        if a:
            print(f"{label:<16s} {a['n']:>3d} {a['crossref']:>9.3f} {a['dense']:>7.3f} "
                  f"{a['bm25']:>7.3f} {a['resolved']:>4d}/{a['n']}")
    print("=" * 76)
    print("expected: references -> crossref ~ bm25 >> dense (lexical, not novel);")
    print("          depends_on -> crossref >> both (transitive graph; the real test)")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "crossref_results.json").write_text(json.dumps(
        {"graph_stats": cr["stats"], "per_query": rows}, indent=2))
    print(f"Wrote {args.out}/crossref_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
