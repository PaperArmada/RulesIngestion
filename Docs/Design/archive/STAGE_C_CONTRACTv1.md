> **Archived.** Superseded by [Docs/Design/v1/](v1/). Kept for reference.
---

# Stage C Contract — Semantic Lifting

## Purpose

Derive semantic graph structures from EvidenceUnits only.

## Outputs

- GraphDelta
- entity_index
- fact_index

## Invariants

- Every entity/fact must cite EvidenceUnit
- Facts are not entities
- No silent inference

## Gates

- Evidence-pointer gate
- Canonical stability gate
- Partition invariants

---

## Retrieval Benchmarks (Stage C Guidance)

**Goal:** Stage C consumes EvidenceUnits (Stage B output) and must be robust across retrieval modes. The benchmarks below are the current baselines for **dense**, **BM25**, and **hybrid (dense+BM25 via RRF)** on three books.

### Swords & Wizardry (25 queries, 307 units, grounded=25, method=page_anchored)

**Dense (no expand context)** — `swords_wizardry_baseline_merged_min200_20260209_041000`

- MRR: **0.398**
- Gold-in-Candidates: **0.68**
- R@5 / H@5: **0.173 / 0.52**
- R@10 / H@10: **0.227 / 0.64**
- Failure counts: hit=17, retrieval_miss=8

**Dense + expand_context (n=1)** — `swords_wizardry_dense_baseline_20260209_044608`

- MRR: **0.150**
- Gold-in-Candidates: **0.64**
- R@5 / H@5: **0.053 / 0.16**
- R@10 / H@10: **0.107 / 0.28**
- R@20 / H@20: **0.227 / 0.64**
- Failure counts: hit=16, retrieval_miss=9
- Scoring time: **112.96s**

**BM25** — `swords_wizardry_bm25_baseline_20260209_042609`

- MRR: **0.258**
- Gold-in-Candidates: **0.56**
- R@5 / H@5: **0.120 / 0.36**
- R@10 / H@10: **0.187 / 0.56**
- Failure counts: hit=14, retrieval_miss=11

**Hybrid (RRF k=60)** — `swords_wizardry_hybrid_20260209_043008`

- MRR: **0.419**
- Gold-in-Candidates: **0.64**
- R@5 / H@5: **0.200 / 0.60**
- R@10 / H@10: **0.227 / 0.64**
- Failure counts: hit=16, retrieval_miss=9

**Takeaway:** Hybrid is best; dense+expand regressed significantly relative to dense (no expand). BM25 alone is weakest.

---

### Starfinder Player Core (50 queries, 13,162 units, grounded=47, method=page_anchored)

**Dense (no expand context)** — `starfinder_baseline_20260208_200648`

- MRR: **0.436**
- Gold-in-Candidates: **0.74**
- R@5 / H@5: **0.507 / 0.62**
- R@10 / H@10: **0.554 / 0.68**
- R@20 / H@20: **0.621 / 0.74**
- Failure counts: hit=37, retrieval_miss=10, grounding_failure=3

**Dense + expand_context (n=1)** — `starfinder_dense_baseline_20260209_044336`

- MRR: **0.336**
- Gold-in-Candidates: **0.74**
- R@5 / H@5: **0.355 / 0.48**
- R@10 / H@10: **0.450 / 0.58**
- R@20 / H@20: **0.621 / 0.74**
- Failure counts: hit=37, retrieval_miss=10, grounding_failure=3
- Scoring time: **142.17s**

**BM25** — `starfinder_bm25_baseline_20260209_042711`

- MRR: **0.280**
- Gold-in-Candidates: **0.58**
- R@5 / H@5: **0.277 / 0.38**
- R@10 / H@10: **0.353 / 0.50**
- R@20 / H@20: **0.432 / 0.58**
- Failure counts: hit=29, retrieval_miss=18, grounding_failure=3

**Hybrid (RRF k=60)** — `starfinder_hybrid_20260209_043633`

- MRR: **0.461**
- Gold-in-Candidates: **0.72**
- R@5 / H@5: **0.462 / 0.66**
- R@10 / H@10: **0.562 / 0.72**
- R@20 / H@20: **0.597 / 0.72**
- Failure counts: hit=36, retrieval_miss=11, grounding_failure=3

**Takeaway:** Hybrid is best. Dense+expand regressed vs dense (no expand) while costing more compute.

---

### PHB 5e (28 queries, 6,999 units, grounded=26, method=page_anchored)

**Dense + expand_context (n=1)** — `phb_baseline_3model_comparison_20260208_053446`

- MRR: **0.758**
- Gold-in-Candidates: **0.929**
- R@5 / H@5: **0.565 / 0.857**
- R@10 / H@10: **0.701 / 0.893**
- R@20 / H@20: **0.801 / 0.929**
- Failure counts: hit=26, grounding_failure=2
- Scoring time: **43.68s**

**BM25** — `phb_bm25_baseline_20260209_042731`

- MRR: **0.249**
- Gold-in-Candidates: **0.536**
- R@5 / H@5: **0.184 / 0.357**
- R@10 / H@10: **0.245 / 0.429**
- R@20 / H@20: **0.323 / 0.536**
- Failure counts: hit=15, retrieval_miss=11, grounding_failure=2

**Hybrid (RRF k=60)** — `phb_hybrid_20260209_043301`

- MRR: **0.490**
- Gold-in-Candidates: **0.857**
- R@5 / H@5: **0.368 / 0.714**
- R@10 / H@10: **0.436 / 0.750**
- R@20 / H@20: **0.671 / 0.857**
- Failure counts: hit=24, retrieval_miss=2, grounding_failure=2

**Takeaway:** Dense is the clear winner on PHB; hybrid reduces precision and overall MRR.

---

## Stage C Design Implications

### 1) Retrieval Strategy Defaults

- **Default to dense** for clean, well-grounded corpora (PHB-like).
- **Prefer hybrid** for noisier or smaller corpora (S&W, Starfinder), where BM25 adds useful lexical signal.
- **Do not default to BM25-only**; it underperforms across all books.

### 2) Expand-Context Caution

- **S&W and Starfinder show a clear regression** with expand_context (lower MRR, lower Hit@k) despite heavy compute cost.
- **PHB benefits from expand_context**, but this does not generalize.
- Stage C should **treat expand_context as optional** and **record it in metadata** for auditability.

### 3) Fusion Weighting (Hybrid)

- RRF (k=60) improves hybrid for S&W/Starfinder but harms PHB (where dense is strong).
- Consider **weighted fusion**: e.g., double-count dense rankings or set a larger k for BM25 to reduce its influence.
- For Stage C, allow **per-corpus fusion weights** or an **auto-tune step** (optimize MRR/Hit@k).

### 4) Evidence Quality Gates

- Maintain **min_chars** and **merge_chunks** controls upstream (Stage B) to avoid low-signal units.
- Use **Gold-in-Candidates** as the first-stage health metric: if low, Stage C will have limited lift regardless of graph logic.

### 5) Metrics to Track in Stage C

- **MRR, Hit@k, Recall@k**, **Gold-in-Candidates**, **Grounding coverage**.
- **Retrieval misses** and **grounding failures** separately (mis-grounding ≠ retrieval failure).
- **Per-suite breakdowns** (blind/state/grounding/temporal) to see if Stage C rules bias against certain query types.

### 6) Practical Guidance for Stage C Outputs

- Stage C should **preserve the originating EvidenceUnit IDs** in all entities/facts.
- **Surface retrieval mode + config** in GraphDelta metadata (dense vs hybrid vs bm25, expand_context on/off, merge_max_chars, min_chars).
- Enable **post-hoc auditing** (given a fact → evidence unit → retrieval run).
