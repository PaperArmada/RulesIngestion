# Manual review: nominate gold chunks for Swords & Wizardry retrieval eval

Workflow to enrich the S&W benchmark with **gold EvidenceUnit IDs** by running retrieval with top-50, then marking which retrieved chunks are true gold per query.

## 1. Run retrieval (50 chunks per query)

From `RulesIngestion`:

```bash
# Embed substrate once (if not already done)
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/swords_wizardry_baseline.yaml \
  --embed-only

# Run retrieval (use run_id printed by embed; quote run_id if it contains &)
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/swords_wizardry_baseline.yaml \
  --run-id 'retrieval_lab_Swords&Wizardry_v3_merged2000_min200' \
  --top-k 1,3,5,10,20,50
```

Output: `out/retrieval_lab/experiments/swords_wizardry_dense_baseline_<timestamp>/` with `retrieved_chunks.json` (up to 50 chunks per query). The config already sets `top_k: [1,3,5,10,20,50]`; if you see only 20 chunks, pass `--top-k 1,3,5,10,20,50` explicitly.

## 2. Generate nominated-gold file

```bash
uv run python scripts/build_nominated_gold_sw.py out/retrieval_lab/experiments/swords_wizardry_dense_baseline_<timestamp>
```

This writes **`evals/retrieval/SwordsandWizardy/nominated_gold_per_query.json`** with one entry per query: `query_id`, `question`, `expected_answer_summary`, `nominated` (list of `rank`, `chunk_id`, `score`, `text_snippet`), and empty `gold_unit_ids`.

## 3. Manual review

1. Open **`nominated_gold_per_query.json`**.
2. For each query, read the expected answer and the nominated chunks (snippets).
3. For each query, set **`gold_unit_ids`** to the list of `chunk_id` values that are true supporting evidence (copy from the `nominated` list for that query). You may include chunk_ids that were not in the top-50 if you know them (e.g. from the answer’s source refs).
4. Save the file.

## 4. Apply gold to benchmark

```bash
uv run python scripts/apply_nominated_gold_sw.py
```

This copies `gold_unit_ids` from `nominated_gold_per_query.json` into **`swords_wizardry_benchmark.json`** so the benchmark has the reviewed gold.

## 5. Run retrieval benchmarks

Re-run the retrieval lab with the same config (and same `--run-id`). The lab will use the updated benchmark’s `gold_unit_ids` for recall@k, MRR, etc.

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/swords_wizardry_baseline.yaml \
  --run-id retrieval_lab_Swords&Wizardry_v3_merged2000_min200
```

New report: `out/retrieval_lab/experiments/swords_wizardry_baseline_<new_timestamp>/REPORT.md`.
