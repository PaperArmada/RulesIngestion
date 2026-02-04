 # Manual End-to-End Exercise: StarFinder2e GalaxyGuide

## Purpose
Validate the full ingestion + edge discovery + merge + evaluation loop using the
StarFinder2e GalaxyGuide ruleset as the target.

## Preconditions
- PDFs exist at `Rules/StarFinder2e/GalaxyGuide/source/*.pdf`.
- `OPENAI_API_KEY` set if using `--auto-config`, `--llm-pre-enrich`, or `--llm-review`.
- Optional: MongoDB configured if you want run records stored.

## Current ideal path (single command)
From `RulesIngestion/` run the full end-to-end pipeline via the dedicated script:
```
./run_full_galaxyguide.sh
```

This script runs ingestion + traversal eval + embedding harness in one flow.

## Canonical ingestion-only path
If you want to stop after traversal eval (no embedding harness), use the CLI:
```
uv run python ingest.py \
  --ruleset StarFinder2e \
  --ruleset-id sf2e-galaxyguide \
  --book GalaxyGuide \
  --profile full \
  --auto-config \
  --llm-pre-enrich \
  --llm-review \
  --llm-review-limit 10
```

This command is the authoritative path for "full" ingestion: marker → profile/config →
enrich → deterministic edges → merge → traversal evaluation.

## Canonical evaluation-only path
If you already have an existing run folder and only want traversal + retrieval eval:
```
uv run python merge_enriched_outputs.py \
  --enriched-dir Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched \
  --output-prefix merged \
  --edge-candidates-dir Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched \
  --edge-eval
```
Then run the retrieval evaluation (see step 6).

## 1) Ingestion (full profile)
This is the same canonical command as above. Use it unless you are debugging a sub-step:
```
uv run python ingest.py \
  --ruleset StarFinder2e \
  --ruleset-id sf2e-galaxyguide \
  --book GalaxyGuide \
  --profile full \
  --auto-config \
  --llm-pre-enrich \
  --llm-review \
  --llm-review-limit 10
```

Expected outputs under:
`Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched/`
- `*.enriched.json`
- `*.coalesced.json`
- `*.graph.json`
- `*.evaluation_queries.json`
- optional `*.llm_review.json`

## 2) OCR/Spelling gates (automatic during edge discovery)
The ingest flow runs `scripts/discover_deterministic_edges.py` during the eval phase.
Watch for gate summaries like:
```
gates: {
  "unresolved_rate": ...,
  "suspect_token_rate": ...,
  "near_duplicate_count": ...,
  "gate_failures": []
}
```
If a gate fails and you need to continue anyway, rerun the step manually with:
```
uv run python scripts/discover_deterministic_edges.py <run_dir>/enriched --write --allow-gate-fail
```

## 3) Merge enriched outputs (with deterministic edges)
```
uv run python merge_enriched_outputs.py \
  --enriched-dir Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched \
  --output-prefix merged \
  --edge-candidates-dir Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched
```

Expected:
- `merged.enriched.json`
- `merged.graph.json`
- `merged.evaluation_queries.json`

## 4) Edge-restricted evaluation (required)
This is required for the traversal metrics (DEP/TCG). The `ingest.py --profile full`
path runs this automatically, but you can re-run manually:
```
uv run python merge_enriched_outputs.py \
  --enriched-dir Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched \
  --output-prefix merged \
  --edge-candidates-dir Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched \
  --edge-eval
```

## 5) Chapter summary embeddings (optional, uses DungeonMindServer)
From `DungeonMindServer/`, generate LLM summaries + summary embeddings:
```
uv run python -m ruleslawyer.evaluation_harness \
  --queries-dir ../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched \
  --model-id nomic-embed-text-v2 \
  --embedding-run-id <timestamp> \
  --chapter-summary-only \
  --chapter-summary-llm \
  --chapter-summary-output ../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/reports/chapters-llm/chapter_summaries_llm.json \
  --chapter-summary-embed \
  --chapter-summary-embedding-output ../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/reports/chapters-llm/chapter_summary_embeddings_llm_nomic-embed-text-v2.json \
  --trust-remote-code
```

## 6) Retrieval evaluation (optional, uses DungeonMindServer)
From `DungeonMindServer/`, run retrieval evaluation using the summary embeddings:
If you need traversal metrics for this run, run step 4 (edge-eval) first.
```
uv run python -m ruleslawyer.evaluation_harness \
  --queries-dir ../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/enriched \
  --best-practice-boost \
  --model-id nomic-embed-text-v2 \
  --embedding-run-id <timestamp> \
  --trust-remote-code \
  --report-dir ../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/reports/chapters-llm \
  --chapter-routing-top-n 5 \
  --chapter-embedding-source summary \
  --chapter-summary-embedding-path ../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/reports/chapters-llm/chapter_summary_embeddings_llm_nomic-embed-text-v2.json \
  --chapter-routing-rerank \
  --traversal-eval
```

Expected report files in:
`Rules/StarFinder2e/GalaxyGuide/outputs/runs/<timestamp>/reports/chapters-llm/`

## 7) Manual spot checks
- Open a `*.enriched.json` file and confirm `content_kind`, `section_path`, and `text` look sane.
- Open `*.graph.json` and confirm `stats` and `edges` are non-empty.
- Open `*.evaluation_queries.json` and confirm queries reference real chunk IDs.
- Check `.edge_candidates.json` for reasonable `resolution_count` and `gate_failures`.

## Success criteria
- Ingestion completes without errors (no failed config diagnostics or pipeline exceptions).
- Ruleset config is generated and saved (snapshot exists under `outputs/runs/<timestamp>/configs/`).
- Gates pass or are explicitly allowed (no unresolved/ocr gate failures blocking merge).
- Merged outputs exist and include deterministic edges:
  `merged.enriched.json`, `merged.graph.json`, `merged.evaluation_queries.json`.
- Traversal evaluation files exist for the run (DEP/TCG metrics present in outputs).
- If running the optional embedding harness, reports are written under
  `outputs/runs/<timestamp>/reports/chapters-llm/` without errors.
