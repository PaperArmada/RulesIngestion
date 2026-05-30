"""M9: re-run the HyDE pool-recall diagnostic with a PROPER bridge.

The original diagnose_hyde fed HyDE a weak shape prior (regex glossary, term
names only). This feeds it the LLM glossary (811 terms, with definitions),
selects the entries most relevant to each query by embedding similarity (query
+ glossary only, no gold), and injects `term: definition`. Strongest faithful
bridge short of leaking gold.

Reports, per query and in aggregate, the pre-rerank pool recall@50 of:
  - query pool (raw_dense)        — the embedder-alone ceiling
  - bridged-HyDE pool             — hypothesis built with the good bridge
and references the original weak-bridge HyDE number (0.873) for contrast.

Usage:
  TINKER_LLM_BACKEND=gemini uv run python -m tinker.scripts.diagnose_hyde_bridged \
      --benchmark <atomic_benchmark.json> --gold out/tinker/swcr/gold_labels.json \
      --glossary out/tinker/swcr/glossary_llm.json \
      --corpus-dir out/tinker/swcr --substrate-dir out/swcr --document-id Swords_Wizardry \
      --out out/tinker/swcr/runs/m9_hyde_bridged --top-vocab 15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker import llm as tinker_llm  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402

POOL = 50


def _load_queries(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    return raw if isinstance(raw, list) else list(raw.get("queries") or raw.get("benchmark") or [])


def _gold_union(gold: dict, qid: str) -> set[str]:
    e = gold.get(qid) or {}
    return set(e.get("required") or []) | set(e.get("supporting") or [])


def _recall(pool_ids: list[str], gold: set[str]) -> float:
    return len(set(pool_ids[:POOL]) & gold) / len(gold) if gold else 0.0


def _norm(m: np.ndarray) -> np.ndarray:
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--glossary", type=Path, required=True)
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--top-vocab", type=int, default=15)
    ap.add_argument("--max-tokens", type=int, default=400)
    args = ap.parse_args()

    queries = _load_queries(args.benchmark)
    gold = json.loads(args.gold.read_text())
    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    dense = DenseIndex.load(args.corpus_dir / "embeddings")
    glossary = json.loads(args.glossary.read_text())["terms"]

    # Embed glossary entries (term: definition) once for relevance selection.
    gloss_texts = [f"{t['term']}: {t['definition']}" for t in glossary]
    print(f"Embedding {len(gloss_texts)} glossary entries for relevance selection...", flush=True)
    gloss_vecs = _norm(np.asarray(tinker_llm.embed(gloss_texts), dtype=np.float32))

    rows = []
    for i, q in enumerate(queries):
        qid = q.get("id") or f"q{i}"
        question = q.get("question", "")
        g = _gold_union(gold, qid)
        if not g:
            continue

        qvec = np.asarray(tinker_llm.embed([question])[0], dtype=np.float32)
        qn = qvec / (np.linalg.norm(qvec) + 1e-9)

        # query pool (raw_dense, pre-rerank)
        q_ids, _ = dense.search(qvec, top_k=POOL)
        q_rec = _recall(list(q_ids), g)

        # relevance-select glossary entries, build definition-bearing vocab
        sims = gloss_vecs @ qn
        top_idx = np.argsort(-sims)[: args.top_vocab]
        vocab = [gloss_texts[j] for j in top_idx]

        shape = ("A Swords & Wizardry rulebook passage that states the relevant "
                 "rule, in the book's own terse style.")
        hyp = tinker_llm.hypothesize(question, shape, vocab, max_tokens=args.max_tokens)
        hvec = np.asarray(tinker_llm.embed([hyp])[0], dtype=np.float32)
        h_ids, _ = dense.search(hvec, top_k=POOL)
        h_rec = _recall(list(h_ids), g)

        rows.append({"qid": qid, "query_pool_recall50": q_rec,
                     "bridged_hyde_pool_recall50": h_rec, "delta": h_rec - q_rec,
                     "vocab_sample": vocab[:5], "hypothesis": hyp})
        print(f"  {qid:<40s} query={q_rec:.2f} bridged_hyde={h_rec:.2f} delta={h_rec-q_rec:+.2f}", flush=True)

    n = len(rows)
    q_mean = sum(r["query_pool_recall50"] for r in rows) / n
    h_mean = sum(r["bridged_hyde_pool_recall50"] for r in rows) / n
    better = sum(1 for r in rows if r["delta"] > 0)
    worse = sum(1 for r in rows if r["delta"] < 0)

    print("\n" + "=" * 74)
    print(f"M9 HyDE with PROPER bridge (LLM glossary + definitions + relevance), n={n}")
    print("-" * 74)
    print(f"  query pool (raw_dense)        mean recall@50: {q_mean:.3f}")
    print(f"  bridged-HyDE pool             mean recall@50: {h_mean:.3f}")
    print(f"  (reference) weak-bridge HyDE  mean recall@50: 0.873")
    print(f"  bridged-HyDE better than query pool on {better}/{n}, worse on {worse}/{n}")
    print("=" * 74)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "hyde_bridged.json").write_text(json.dumps(
        {"summary": {"n": n, "query_pool": q_mean, "bridged_hyde_pool": h_mean,
                     "weak_bridge_hyde_pool": 0.873, "better": better, "worse": worse},
         "per_query": rows}, indent=2))
    print(f"Wrote {args.out}/hyde_bridged.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
