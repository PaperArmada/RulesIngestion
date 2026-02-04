# Handoff: Graph-Aware Retrieval Enhancement (Why Graph Isn’t Meaningful)
**Date:** 2026-01-23  
**Type:** Technical Debt  
**Last Updated:** 2026-01-24 05:40  

---

## 🚨 CURRENT STATE

### What’s Working ✅
- Graph rebuild in `RulesIngestion` is done; merged outputs regenerated for run `2026-01-22_21-59-56`.
- **Graph expansion logging** added to evaluation reports (adds + reasons per query).
- Chapter‑slice + query‑sampling evaluation works (document prefix + query limit).
- **Graph boost (non‑oracle, top‑seeded)** is implemented and improves strict MRR across slices.
- **LLM chapter summaries** are generated + embedded and used for chapter routing.

### What’s NOT Working ❌
- **Expanded gold deltas are small** (non-zero in full runs, but still minimal lift).
- **Section expansion contributes nothing** in sampled runs (all adds are `graph_depth_1`).

### Suspected Causes
1. Graph neighbors are **not relevant enough** to affect rank (adds are graph‑adjacent but not retrieved higher).
2. Graph edges may be **too local / weak** (single‑depth adjacency mirrors near‑duplicate chunks).
3. Evaluation expansion is happening, but retrieval **doesn’t benefit** without true graph‑aware rerank/boost.

### Debug Steps for Next Session
1. **Inspect added chunks** in the sample report to verify if graph adds are meaningful or noise.
2. **Increase graph depth** (`--gold-next-depth 2`, `--gold-max-total 20`) and re‑sample.
3. Run **same‑kind restriction** (`--gold-same-kind-only`) to see if noise drops.
4. Try a **Conditions/Class chapter slice** instead of spell sections.

---

## Quick Pickup

### Commands
```bash
cd /media/drakosfire/Projects/DungeonOverMind/DungeonMindServer
# Sample run with logging + chapter slice
uv run python -m ruleslawyer.evaluation_harness \
  --queries-dir "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-22_21-59-56/enriched" \
  --chunk-source enriched \
  --model-id bge-m3 \
  --both --expand-gold \
  --document-prefix "PZO22001 Starfinder Player Core 294-329" \
  --document-prefix "PZO22001 Starfinder Player Core 330-363" \
  --query-limit 200 --query-seed 42 \
  --report-dir "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-22_21-59-56/enriched/reports/sample"
```

### Key Files
```
DungeonMindServer/ruleslawyer/evaluation_harness.py
  - _expand_expected_ids with reasons (lines ~407-466)
  - document filtering + sampling (lines ~538-553)
  - expansion logging in report (lines ~240-287)
  - graph boost + non‑oracle seeding (top‑seeded, decay, same‑kind)
RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-22_21-59-56/enriched/merged.graph.json
RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-22_21-59-56/enriched/merged.enriched.json
```

---

## Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Graph rebuild + canonical IDs + semantic edges |
| Phase 2 | ✅ Complete | Expansion logging + chapter-slice sampling |
| Phase 3 | 🔄 In Progress | Diagnose why expansion doesn’t move metrics |
| Phase 4 | ✅ Complete | Graph-aware rerank experiments (non‑oracle boost) |

---

## Files Modified This Session

### Modified
- `DungeonMindServer/ruleslawyer/evaluation_harness.py`
  - Added document filters + query sampling (`--document-id`, `--document-prefix`, `--query-limit`, `--query-seed`).
  - Added expansion reason logging and per‑query added chunk list.
  - Added graph boost parameters and non‑oracle seeding:
    - `--graph-boost-source` (`expected` | `top`)
    - `--graph-boost-seed-top-n`
    - `--graph-boost-decay`
    - `--graph-boost-same-kind-only`

---

## Evidence

Sample report with expansion logging:
```
/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-22_21-59-56/enriched/reports/sample/bge-m3/evaluation_expanded_queries_20260123-110628.md
```
- Expansion stats show **queries with additions: 200**, avg added **1.99**, **reasons: graph_depth_1 only**.
- **Delta** remains `0.0000`.

---

## Context
Core hypothesis: **graph expansion is happening, but it does not change ranks**, implying the graph is not contributing meaningful alternative answers. This was validated; the lift came from **graph-aware reranking** instead.

---

## Next Agent Role (Metrics + Research Review)
**Objective:** Extract and study the metrics + review code, then read `RulesIngestion/Docs/Research` and related design docs to recommend retrieval-quality improvements.

**Focus Areas:**
- Evaluate metrics/review logic in `RulesIngestion/rules_ingestion_pipeline.py` (see **METRICS & REVIEW** section).
- Cross-reference research notes in `RulesIngestion/Docs/Research/` for graph/retrieval levers.
- Produce concrete, prioritized recommendations tied to design goals.

---

## Metadata Management in Open-Source RAG Frameworks (Research Summary)
**Purpose:** Influence metadata strategy for ingestion + retrieval to improve relevance and filtering.

**Common philosophy:**
- Metadata anchors chunks to sources (citations, navigation).
- Metadata enables filtering/disambiguation (edition, chapter, system, domain).
- Metadata can improve retrieval (restrict search space, re-rank).

**Framework notes:**
- **LlamaIndex:** LLM-generated chunk summaries stored as metadata to disambiguate similar passages; metadata returned with results; can apply filters.
- **LangChain:** Declarative metadata filters (e.g., `$and`, `$gt`) applied before similarity search; metadata stored alongside vectors.
- **RAGFlow:** Emphasizes ingestion normalization + hybrid (dense + sparse) retrieval; metadata contributes to sparse signal.
- **Dify:** Low-code ingestion workflows; metadata transformation steps integrated into pipeline design.

**Actionable recommendations (apply to TTRPG rulebooks):**
1. Attach **granular metadata** (book, edition, chapter, page, entity names, unique IDs).
2. Add **LLM-generated chunk summaries** as metadata to disambiguate similar sections.
3. Support **metadata filtering** in retrieval (edition/system/level/ruleset).
4. Consider **hybrid retrieval** (dense + sparse lexical on metadata fields).
5. Explore a **simple UI/workflow** to manage metadata extraction rules.

---

## Alias Normalization Experiment (2026-01-23)
**Status:** Completed (no lift on baseline; graph boost still helps)

**Setup:**
- Regenerated enriched + graph for slices `294-329` and `330-363` using alias normalization.
- Evaluated with `bge-m3`, `--query-limit 200`, `--query-seed 42`.

**Results:**
- Baseline (alias-only, no boost): **no change** vs prior run.
- Graph boost still improves strict MRR when enabled (top-seeded, depth=2, top-k=50).
- Expanded gold delta remains `0` (expanded == strict).

**Implication:** Alias normalization alone does not move ranks; graph topology must become more semantic.

---

## Graph Upgrade Implementation (2026-01-23)
**Status:** Implemented (see `RulesIngestion/enrichment.py`)

**Changes shipped:**
1) **Graph-to-chunk projection**
   - Added `mentioned_in` edges so entity nodes connect to all chunks that mention them.
2) **Relation extraction edges**
   - Deterministic edges for `requires`, `grants`, `affects`, `has_effect` using pattern rules.
3) **Chunk-semantic adjacency**
   - Added `mentions_same_entity` chunk↔chunk edges for shared canonical entities.
4) **Boost out of top-k window**
   - Supported by leaving `--graph-boost-top-k` unset (no limit); bounded top-k still recommended.

**Graph stats output:**
- `*.graph.json` now includes `stats` (node counts, edge relation counts, alias collapse metrics).

---

## New Graph Results (Spells Slice, 294-329 + 330-363)
**Run:** `2026-01-23-alias-v2` (new graph edges + alias normalization)

- **Boosted (top-seed, depth=2, top-k=50):** MRR `0.8576`  
  - Report: `RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-23-alias-v2/enriched/reports/sample-boost-topn-3/bge-m3/evaluation_strict_queries_20260123-165104.md`
- **Previous alias boosted baseline:** MRR `0.8085`  
  - Report: `RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-23-alias/enriched/reports/sample-boost-topn-3-v2/bge-m3/evaluation_strict_queries_20260123-160945.md`
- **Delta:** +0.0491 MRR (expanded still matches strict)

---

## Model Decision (2026-01-23)
We will continue iterating with **`nomic-embed-text-v2`** because it matches MRR vs `bge-m3` while running faster in practice. All new evaluations should use `nomic-embed-text-v2` unless otherwise stated.

**Best-practice eval shortcut:**
```
uv run python -m ruleslawyer.evaluation_harness \
  --queries-dir "<run>/enriched" \
  --model-id nomic-embed-text-v2 \
  --document-prefix "<doc-prefix-1>" \
  --document-prefix "<doc-prefix-2>" \
  --query-limit 200 --query-seed 42 \
  --best-practice-eval \
  --best-practice-boost \
  --report-dir "<run>/enriched/reports/sample-boost-topn-3-nomic"
```

---

## LLM Chapter Summary Routing (Full-Query Sweep, 2026-01-24)
**Setup:**
- Run: `2026-01-23-full-source`
- Model: `nomic-embed-text-v2` (MOE)
- Flags: `--best-practice-eval --best-practice-boost --reuse-embeddings`
- Summary source: **LLM summaries**, embed key `medium`
- Embedding path: `.../reports/chapters-nomic/chapter_summary_embeddings_llm.json`

**Results (Expanded Gold):**
| top_n | Coverage | MRR | hit@1 | hit@3 | hit@5 | hit@10 | Report |
|---|---|---|---|---|---|---|---|
| 3 | 0.3891 | 0.8522 | 0.8004 | 0.8795 | 0.9202 | 0.9615 | `evaluation_expanded_queries_20260123-222656.md` |
| 5 | 0.4795 | 0.8301 | 0.7785 | 0.8531 | 0.8878 | 0.9370 | `evaluation_expanded_queries_20260123-222916.md` |
| 8 | 0.5937 | 0.8112 | 0.7548 | 0.8417 | 0.8744 | 0.9173 | `evaluation_expanded_queries_20260123-223148.md` |
| 12 | 0.7044 | 0.7931 | 0.7339 | 0.8272 | 0.8559 | 0.9020 | `evaluation_expanded_queries_20260123-223434.md` |

**Takeaway:** Higher `top_n` increases coverage and lowers MRR; expanded-gold deltas are small but positive (~0.004–0.007).

**Full-run sweep command:**
```bash
cd /media/drakosfire/Projects/DungeonOverMind/DungeonMindServer
for top_n in 3 5 8 12; do
  uv run python -m ruleslawyer.evaluation_harness \
    --run-outputs-dir "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-23-full-source/enriched" \
    --model-id nomic-embed-text-v2 \
    --best-practice-eval \
    --best-practice-boost \
    --reuse-embeddings \
    --embedding-run-id "2026-01-23-full-source" \
    --chapter-embedding-source summary \
    --chapter-summary-embedding-path "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-23-full-source/enriched/reports/chapters-nomic/chapter_summary_embeddings_llm.json" \
    --chapter-routing-report \
    --chapter-routing-top-n "$top_n" \
    --report-dir "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-23-full-source/enriched/reports/chapters-nomic" \
    --trust-remote-code
done
```

---

## New Lever: Embedding Fine-Tuning (2026-01-23)
We will add **fine-tuning `nomic-embed-text-v2`** as a retrieval lever. We already generate evaluation queries and have a 4080 (16GB VRAM), so this is feasible to prototype. Use repo instructions for embedding fine-tuning when we decide to run it.

---

## Canonical Findings (Graph Boost Experiments)
**Non‑oracle, top‑seeded graph boost consistently improved strict MRR across three slices** (Conditions/Class, Spells, Intro).

**Recommended defaults (locked):**
- `--graph-boost-source top`
- `--graph-boost-seed-top-n 3`
- `--graph-boost-depth 2`
- `--graph-boost-top-k 50`
- `--graph-boost-decay 0.4`

**Seed top‑N decision:**
- `seed_top_n=3` outperformed or tied `seed_top_n=5` on MRR with lower complexity (intro slice tie‑breaker).

---

## Concrete Next Experiments (from research)
1. **Alias normalization / entity linking pass** → re‑run seed_top_n grid on a slice to measure lift.
2. **Graph‑first filter** (entity‑linked nodes → vector search on subset) vs **vector‑first → graph expansion** A/B.
3. **Graph embeddings** (Node2Vec/GraphSAGE) as rerank signal vs current boost.
4. **Relation extraction expansion** (add explicit `has_effect`, `requires_level`, `grants_ability`) → measure MRR shift.
5. **Baseline answer generation** (acceptable informed answer per query) → add semantic similarity scoring as a secondary retrieval metric.

---

## Optional Before Locking In
- Run a **full-query sweep** using **non‑LLM summaries (first‑10‑chunks)** at the same `top_n` values for a direct A/B baseline.
- Decide **routing default** (`top_n=8` vs `12`) based on desired coverage vs MRR tradeoff.

---

## References
- Related handoff: `handoffs/HANDOFF-Graph-Retrieval-Enhancement.md` (this file)
