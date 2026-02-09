# Retrieval Lab experiments

- **dense/** — Dense retrieval only (sentence-transformers embeddings, cosine similarity). `retrieval_mode: dense`; run `--embed-only` once per substrate then eval with `--run-id`.
- **sparse/** — Sparse retrieval only (BM25). `retrieval_mode: bm25`; no embedding step.
- **hybrid/** — Dense + BM25 fused with Reciprocal Rank Fusion (RRF, k=60). `retrieval_mode: hybrid`; reuse the same embeddings as dense (same `--run-id`), BM25 built at eval time.

Run from **RulesIngestion** root, e.g.:
`uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/dense/swords_wizardry_baseline.yaml`
`uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml --run-id 'retrieval_lab_Swords&Wizardry_v3_merged2000_min200'`
