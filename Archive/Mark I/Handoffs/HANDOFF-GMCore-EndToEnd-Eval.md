# Handoff: GMCore End-to-End Evaluation (Merged vs Chapter-Ranked)
**Date:** 2026-01-24  
**Type:** Evaluation  
**Last Updated:** 2026-01-24 09:40  

---

## 🚨 CURRENT STATE

### What's Working ✅
- GMCore run completed end-to-end ingestion, config generation, enrichment, and evaluation.
- Expanded-only evaluation completed for **merged** and **chapter-ranked** runs across:
  - `bge-m3`, `nomic-embed-text-v2`, `all-mpnet-base-v2`
- LLM chapter summaries used for routing (map-reduce).

### What's NOT Working ❌
- Chapter routing requires **matching model embeddings** for chapter summaries.
  - Using nomic embeddings with bge-m3 caused a dimension mismatch.

### Suspected Causes
1. Chapter summary embeddings are model-specific (768 vs 1024 dims).
2. Reusing summaries is correct, but embeddings must be regenerated per model.

### Debug Steps for Next Session
1. Use **existing summaries** and regenerate **only embeddings** per model.
2. Confirm report comparisons: merged vs chapter-ranked per model.

---

## Quick Pickup

### Run Directory
```
/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32
```

### Key Reports (Expanded-Only)
```
reports/merged/bge-m3/evaluation_expanded_queries_20260124-082646.md
reports/chapters-llm/bge-m3/evaluation_expanded_queries_20260124-091741.md
reports/merged/nomic-embed-text-v2/evaluation_expanded_queries_20260124-092342.md
reports/chapters-llm/nomic-embed-text-v2/evaluation_expanded_queries_20260124-092711.md
reports/merged/all-mpnet-base-v2/evaluation_expanded_queries_20260124-092945.md
reports/chapters-llm/all-mpnet-base-v2/evaluation_expanded_queries_20260124-093213.md
```

---

## Results Summary (Expanded Gold)

### Merged (no chapter routing)
| Model | Coverage | MRR | hit@1 | hit@3 | hit@5 | hit@10 | Total ms |
|---|---|---|---|---|---|---|---|
| bge-m3 | 1.0000 | 0.9119 | 0.8879 | 0.9273 | 0.9364 | 0.9485 | 424,434 |
| nomic-embed-text-v2 | 1.0000 | 0.9093 | 0.8848 | 0.9273 | 0.9333 | 0.9424 | 221,354 |
| all-mpnet-base-v2 | 1.0000 | 0.8934 | 0.8576 | 0.9303 | 0.9424 | 0.9455 | 149,697 |

### Chapter-Ranked (LLM summaries, top_n=8)
| Model | Coverage | MRR | hit@1 | hit@3 | hit@5 | hit@10 | Total ms |
|---|---|---|---|---|---|---|---|
| bge-m3 | 0.8727 | 0.9359 | 0.9201 | 0.9479 | 0.9479 | 0.9583 | 426,319 |
| nomic-embed-text-v2 | 0.9061 | 0.9254 | 0.9030 | 0.9398 | 0.9498 | 0.9565 | 204,250 |
| all-mpnet-base-v2 | 0.6606 | 0.9093 | 0.8761 | 0.9358 | 0.9450 | 0.9541 | 143,210 |

**Note:** Chapter routing improves MRR but lowers coverage (expected).

---

## Commands (Reference)

### Embed existing summaries (per-model)
```bash
cd /media/drakosfire/Projects/DungeonOverMind/DungeonMindServer
uv run python -m ruleslawyer.evaluation_harness \
  --run-outputs-dir "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/enriched" \
  --model-id bge-m3 \
  --chapter-summary-only \
  --chapter-summary-output "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/reports/chapters-llm/chapter_summaries_llm.json" \
  --chapter-summary-embed \
  --chapter-summary-embedding-output "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/reports/chapters-llm/chapter_summary_embeddings_llm_bge.json"
```

### Chapter-ranked eval (example)
```bash
uv run python -m ruleslawyer.evaluation_harness \
  --run-outputs-dir "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/enriched" \
  --chunk-source enriched \
  --expand-gold \
  --best-practice-boost \
  --model-id nomic-embed-text-v2 \
  --trust-remote-code \
  --report-dir "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/reports/chapters-llm" \
  --chapter-routing-top-n 8 \
  --chapter-embedding-source summary \
  --chapter-summary-embedding-path "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/reports/chapters-llm/chapter_summary_embeddings_llm.json"
```

---

## Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | End-to-end GMCore ingestion + config |
| Phase 2 | ✅ Complete | Expanded-only eval for merged + chapter-ranked |
| Phase 3 | 🔄 In Progress | Decide default embedding model for RulesLawyer rebuild |

---

## Files Modified This Session

### Created
- `handoffs/HANDOFF-GMCore-EndToEnd-Eval.md` — this summary

### Modified
- `DungeonMindServer/ruleslawyer/evaluation_harness.py` — reuse existing summaries, add `--force-chapter-summary-regen`

---

## Decision Focus (Next Session)
- Choose **embedding model** for the RulesLawyer backend:
  - **bge-m3**: best MRR, slowest chunk embedding.
  - **nomic-embed-text-v2**: near-best MRR, ~2x faster than bge on GMCore.
  - **all-mpnet-base-v2**: lowest MRR, fastest; weaker coverage when chapter-ranked.

---

## References
- Run directory: `/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32`
- Automation script: `RulesIngestion/run_gmcore_ingest_and_eval.sh`
