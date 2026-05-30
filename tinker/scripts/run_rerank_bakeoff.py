"""M10: rerank bake-off — dense-only vs cross-encoder vs LLM-listwise.

The cross-encoder was found net-negative (dense-only recall@10 0.768 vs
dense+rerank 0.589), fooled by keyword-dense index/TOC pages. This tests whether
(a) filtering navigational units helps, and (b) a lightweight-LLM listwise
reranker beats both. Six conditions on the 19-query gold:

  {dense_only, cross_encoder, llm_listwise} x {index-filter off, on}

The LLM prompt deliberately does NOT mention index/navigation pages — a fair
test of whether it avoids the cross-encoder's trap on its own.

Usage:
  TINKER_LLM_BACKEND=gemini uv run python -m tinker.scripts.run_rerank_bakeoff \
      --benchmark <atomic_benchmark.json> --gold out/tinker/swcr/gold_labels.json \
      --corpus-dir out/tinker/swcr --substrate-dir out/swcr --document-id Swords_Wizardry \
      --out out/tinker/swcr/runs/m10_rerank_bakeoff
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker import llm as tinker_llm  # noqa: E402
from tinker import rerank as tinker_rerank  # noqa: E402
from tinker.backends import current_backend  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402

POOL = 50
KS = (1, 5, 10)


def _load_queries(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    return raw if isinstance(raw, list) else list(raw.get("queries") or raw.get("benchmark") or [])


def _gold_union(gold: dict, qid: str) -> set[str]:
    e = gold.get(qid) or {}
    return set(e.get("required") or []) | set(e.get("supporting") or [])


def _recall(ranked: list[str], g: set[str], k: int) -> float:
    return len(set(ranked[:k]) & g) / len(g) if g else 0.0


_NAV_RE = re.compile(r"\b(index|table of contents|list of tables)\b", re.IGNORECASE)


def is_navigational(text: str) -> bool:
    """Heuristic nav-page detector: index/TOC markers in the head, or a high
    density of 'see _' cross-refs / bare page numbers (navigational layout)."""
    head = " ".join((text or "").split())[:160]
    if _NAV_RE.search(head):
        return True
    body = (text or "")[:1200]
    sees = body.lower().count("see ")
    nums = len(re.findall(r"\b\d{1,3}\b", body))
    return sees >= 4 and nums >= 15


def _llm_listwise(query: str, cands: list[dict], top_k: int = 10) -> list[str]:
    """Ask the LLM to return indices of the top_k most relevant candidates."""
    listing = "\n".join(
        f"[{i}] {' '.join((c['text'] or '').split())[:280]}" for i, c in enumerate(cands)
    )
    system = (
        "You are a retrieval reranker. Given a user query and numbered candidate "
        "passages, return the indices of the passages most relevant to ANSWERING "
        "the query, most relevant first. Relevance means the passage contains the "
        "rule/content that answers the query. Respond ONLY with JSON: "
        f'{{"ranking": [<indices, best first, up to {top_k}>]}}.'
    )
    user = f"Query: {query}\n\nCandidates:\n{listing}\n\nReturn the JSON ranking."
    try:
        res = current_backend().chat(role="rerank_listwise", system=system,
                                     user=user, think=False, json_format=True)
        order = json.loads(res.text).get("ranking", [])
    except Exception:
        order = []
    seen, out = set(), []
    for idx in order:
        if isinstance(idx, int) and 0 <= idx < len(cands) and idx not in seen:
            seen.add(idx)
            out.append(cands[idx]["id"])
    # backfill with pool order for anything the LLM omitted (so @10 is defined)
    for c in cands:
        if c["id"] not in out:
            out.append(c["id"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    queries = _load_queries(args.benchmark)
    gold = json.loads(args.gold.read_text())
    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    nav_ids = {u.id for u in units if is_navigational(u.text)}
    dense = DenseIndex.load(args.corpus_dir / "embeddings")
    print(f"flagged {len(nav_ids)} navigational units out of {len(units)}", flush=True)

    conditions = ["dense_only", "cross_encoder", "llm_listwise"]
    variants = ["filter_off", "filter_on"]
    acc = {f"{c}|{v}": {k: 0.0 for k in KS} for c in conditions for v in variants}
    n = 0

    for i, q in enumerate(queries):
        qid = q.get("id") or f"q{i}"
        question = q.get("question", "")
        g = _gold_union(gold, qid)
        if not g:
            continue
        n += 1
        qvec = tinker_llm.embed([question])[0]
        ids, _ = dense.search(qvec, top_k=POOL)
        ids = list(ids)
        tinker_llm.unload_ollama_model(tinker_llm.MODEL_EMBEDDER)

        for v in variants:
            pool_ids = [u for u in ids if not (v == "filter_on" and u in nav_ids)]
            cands = [{"id": u, "text": unit_text_by_id.get(u, "")} for u in pool_ids]
            # dense_only: pool order is dense order
            dense_order = pool_ids
            ce = [c["id"] for c in tinker_rerank.rerank(question, cands, top_k=len(cands))]
            llm = _llm_listwise(question, cands, top_k=10)
            for cname, ranked in (("dense_only", dense_order),
                                  ("cross_encoder", ce), ("llm_listwise", llm)):
                for k in KS:
                    acc[f"{cname}|{v}"][k] += _recall(ranked, g, k)
        print(f"  [{i+1}] {qid}", flush=True)

    print("\n" + "=" * 72)
    print(f"RERANK BAKE-OFF (n={n} queries, dense pool={POOL})")
    print(f"{'condition':<26s} {'R@1':>7s} {'R@5':>7s} {'R@10':>7s}")
    print("-" * 72)
    for v in variants:
        for c in conditions:
            row = acc[f"{c}|{v}"]
            tag = f"{c} [{v.replace('filter_','idx-filter ')}]"
            print(f"{tag:<26s} {row[1]/n:>7.3f} {row[5]/n:>7.3f} {row[10]/n:>7.3f}")
        print("-" * 72)
    print("reference: dense+cross-encoder, no filter == the pipeline default all "
          "project numbers used")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "bakeoff.json").write_text(json.dumps(
        {"n": n, "nav_units": len(nav_ids),
         "results": {k: {kk: vv / n for kk, vv in row.items()} for k, row in acc.items()}},
        indent=2))
    print(f"Wrote {args.out}/bakeoff.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
