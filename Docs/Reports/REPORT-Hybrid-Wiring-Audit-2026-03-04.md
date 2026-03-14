# Hybrid Retrieval Wiring Audit — Findings & Recommendations
**Date:** 2026-03-04  
**Corpus:** StarFinderPlayerCore (`v2_merged2000_min200`, 2386 units)  
**Model pair audited:** `all-mpnet-base-v2` standardized  
**Runs compared:**
- Dense: `bakeoff_starfinder_dense_all_mpnet_base_v2_standardized_baseline_20260303_021102`
- Hybrid: `bakeoff_starfinder_hybrid_all_mpnet_base_v2_standardized_baseline_20260303_021107`

---

## 1. What We Set Out to Answer

Hybrid retrieval on Starfinder is consistently underperforming dense-only across all four bakeoff models (lower MRR, lower Gold-in-Candidates). The playbook asked us to determine: **is this a wiring/config defect, or is it legitimate hybrid behavior?**

The answer is: **both**, but the dominant cause is a wiring defect — specifically a BM25 budget starvation issue that causes gold items to be dropped from the fused candidate list entirely. One true vocabulary mismatch miss also exists, which is not fixable by budget alone.

---

## 2. Baseline Metrics (the problem)

| Metric | Dense | Hybrid | Delta |
|---|---|---|---|
| MRR | 0.6660 | 0.6142 | **−0.0518** |
| nDCG@10 | 0.6631 | 0.6378 | −0.0253 |
| Hit@10 | 0.92 | 0.86 | **−0.06** |
| Recall@10 | 0.8467 | 0.8100 | −0.0367 |
| FSH@10 | 0.760 | 0.720 | −0.040 |
| **Gold-in-Candidates** | **1.000** | **0.960** | **−0.040** |

Gold-in-Candidates dropping from 1.00 → 0.96 is the smoking gun. Hybrid *should never* lose items that dense-only retrieves, unless there is a truncation/budget/ID bug.

---

## 3. Step 0 — Regression Queries

Six query_ids regress in hybrid vs dense. Two are GIC_LOSS (gold vanishes from candidates entirely); four are rank push-outs (gold present but demoted past @10):

| query_id | Type | Dense rank | Hybrid rank | Question (truncated) |
|---|---|---|---|---|
| `batch_003_14` | **GIC_LOSS** | 12 | missing | "If the text is ambiguous, where does the book say to look?" |
| `batch_005_07` | **GIC_LOSS** | 18 | missing | "Does Sure Footing let me ignore the movement restriction from being grabbed?" |
| `batch_004_05` (gold 3) | **GIC_LOSS** | 16 | missing | "When a reaction says you Grapple the triggering creature…" |
| `blind_001_09` | rank push | 7 | 14 | "Can a Shirren use Undying more than once per day?" |
| `batch_003_02` | rank push | 8 | 14 | "Is the 'until end of next turn' effect applied before or after…" |
| `batch_004_05` (gold 1,2) | rank push | 7/8 | 13/15 | same as above |
| `batch_006_03` | rank push | 7 | 12 | "Do spells always have visible or sensory effects when cast?" |

---

## 4. Step 1 — Invariant Checks

### Invariant A: Corpus Identity — **PASS**

Both runs use the same substrate, same transforms:

```
substrate: out/StarFinderPlayerCore
substrate_version: v2_merged2000_min200
transforms: fold_under_threshold_into_adjacent(min_chars=200) → merge_units_by_heading(max_chars=2000)
corpus size: 2386 units
```

All IDs in hybrid results exist in the corpus. No phantom IDs.

**Code paths:**
- `retrieval_lab/substrate_loader.py:fold_under_threshold_into_adjacent()` (line 87)
- `retrieval_lab/substrate_loader.py:merge_units_by_heading()` (line 225)
- `retrieval_lab/run_experiment.py:_prepare_experiment_corpus_context()` (line 329)

### Invariant B: Candidate Monotonicity — **VACUOUSLY PASSES, FUNCTIONALLY FAILS**

Gold IS in `union(dense@20, bm25@20)` for all regression queries, because gold is always in `dense@20`. But gold's RRF score falls below the 20th-place cutoff, so it's truncated out of the final list.

For `batch_003_14`: gold at dense rank 12 → RRF score = `1/(60+12) = 0.01389`. Minimum hybrid@20 score = **0.01410**. Gold is below the cutoff by 0.00021.

The union *contains* the gold, but the truncation step evicts it. This is the key diagnostic.

### Invariant C: Gold ID Compatibility — **PASS**

`chunk_id` in retrieved chunks is the same field as `gold_unit_ids` in benchmark. No ID aliasing, no family-anchor translation issues. The scoring is correctly aligned.

---

## 5. Step 3 — Root Cause: Failure Mode 1 (Budget Starvation)

### What the code does

In `retrieval_lab/orchestration/dense_mode.py`, the BM25 budget was computed as:

```python
# dense_mode.py lines 1280–1285 (BEFORE patch)
max_k_hybrid = max(
    max(config.top_k),          # = 20
    int(getattr(config, "stage1_admission_k", 100))
    if bool(getattr(config, "two_stage_retrieval", False))
    else max(config.top_k),     # = 20 (two_stage=False)
)
bm25_ranked_lists, _ = bm25_rank(..., max_k_hybrid, ...)  # Ks = 20
```

With `two_stage_retrieval=False` and `top_k=[1,3,5,10,20]`, this collapses to `Ks = max(top_k) = 20`.

The dense list is also capped at `retrieval_cutoff = max_k = 20` (line 618 before patch). RRF then fuses two lists of depth 20 into a final list of depth 20 (`max_k=retrieval_cutoff`):

```python
# dense_mode.py lines 675–677 (BEFORE patch)
ranked_lists, score_lists = reciprocal_rank_fusion(
    rankings_per_query, k=rrf_k, max_k=retrieval_cutoff  # = 20
)
```

**The problem:** With `Ku=Ks=Kfinal=20`, the hybrid system has *zero headroom*. BM25 fills its 20 slots with high-TF documents that may be semantically irrelevant. Each of those items receives RRF score `1/(60+rank)`. An item at BM25 rank 1 scores `1/61 = 0.01639`. An item at BM25 rank 11 scores `1/71 = 0.01408`. All 20 BM25 items sit above gold's dense-only score of `1/(60+12) = 0.01389`. Gold is pushed out.

### BM25 rank analysis for regression queries

| query_id | Gold dense rank | BM25@20 | BM25@50 | BM25@100 | BM25@200 |
|---|---|---|---|---|---|
| `batch_003_14` | 12 | None | None | **90** | 90 |
| `batch_005_07` | 18 | None | None | None | **None** |
| `batch_004_05` gold-3 | 16 | None | None | None | 136 |
| `blind_001_09` | 7 | None | None | None | 33 |
| `batch_003_02` | 8 | None | None | None | None |
| `batch_004_05` gold-1,2 | 7, 8 | None | None | None | None |
| `batch_006_03` | 7 | None | None | None | 48 |

For `batch_003_14`: BM25 rank is 90. With `Ks=100`, gold gets a BM25 contribution of `1/(60+90) = 0.00667`. Combined RRF score = `0.01389 + 0.00667 = 0.02056`. That beats the hybrid@20 minimum (0.01410) → gold enters at rank 6.

For `batch_005_07`: BM25 never retrieves the gold (not in top 200). "Sure Footing" is a named ability with no lexical overlap with "movement restriction" or "grabbed." This is a pure vocabulary mismatch miss. No budget increase helps.

---

## 6. Step 4 — Oracle Check

Dense@20 union BM25@200 = `oracle_union`. Gold presence in oracle:

| query_id | In dense@20 | In BM25@200 | In oracle_union |
|---|---|---|---|
| `batch_003_14` | Yes | Yes (rank 90) | Yes |
| `batch_005_07` | Yes | **No** | Yes (via dense only) |
| `blind_001_09` | Yes | Yes (rank 33) | Yes |
| `batch_003_02` | Yes | No | Yes (via dense only) |
| `batch_004_05` | Yes | No / Yes@136 | Yes |
| `batch_006_03` | Yes | Yes (rank 48) | Yes |

**Interpretation (per Step 4 of the playbook):** Oracle union improves over hybrid for all cases → **wiring/config issue** confirmed. The only case where BM25 adds zero value even at budget 200 is `batch_005_07` (vocabulary mismatch).

---

## 7. Step 5 — RRF Budget Simulation

Simulating `Ks = {20, 50, 100, 200}` with `Ku=20` (dense@20 from experiment), `Kfinal=20`:

| query_id | Ks=20 | Ks=50 | Ks=100 | Ks=200 |
|---|---|---|---|---|
| `batch_003_14` (dense=12) | missing | missing | **rank 6** | rank 6 |
| `batch_005_07` (dense=18) | missing | missing | missing | missing |
| `blind_001_09` (dense=7) | rank 14 | **rank 6** | rank 6 | rank 6 |
| `batch_003_02` (dense=8) | rank 14 | rank 16 | rank 17 | rank 19 |
| `batch_004_05` gold-3 (dense=16) | missing | missing | missing | **rank 10** |
| `batch_006_03` (dense=7) | rank 12 | **rank 4** | rank 4 | rank 4 |

Note the counter-intuitive result for `batch_003_02` and `batch_004_05` gold-1,2: increasing `Ks` makes gold's rank *worse*, not better. This is because BM25 at budget 50–200 finds more semantically-irrelevant but lexically-overlapping items that each receive a BM25 contribution to their RRF score, pushing gold down in the final ranking. This is the known hybrid precision-recall tradeoff: more candidates, lower rank purity when gold is low-lexical-overlap.

---

## 8. The Patch

### Files modified

**`retrieval_lab/config.py`** — added `bm25_budget` and `dense_budget` knobs:

```python
# retrieval_lab/config.py (new, after line 166)
# Hybrid retrieval candidate budgets (Ku/Ks).
# bm25_budget: BM25 candidate list depth (Ks). Defaults to None → falls back to max(top_k).
# Setting Ks > Kfinal (max(top_k)) gives BM25 a deeper candidate pool before RRF, which
# prevents BM25 from displacing dense-only gold that ranks beyond Kfinal in BM25 alone.
# dense_budget: dense candidate list depth (Ku). Defaults to None → falls back to max(top_k).
# Setting Ku > Kfinal gives dense a deeper pool; has no effect when dense is already
# monotonically better than hybrid (Invariant B already holds with Ku=Kfinal).
bm25_budget: Optional[int] = None   # Ks — None means use max(top_k)
dense_budget: Optional[int] = None  # Ku — None means use max(top_k)
```

**`retrieval_lab/orchestration/dense_mode.py`** — three changes:

**Change 1** (BM25 budget, lines ~1280–1320): BM25 candidate list is built to `bm25_ks` instead of `max_k_hybrid`, and budgets are logged at INFO level:

```python
# dense_mode.py — BM25 build block (AFTER patch)
_kfinal = max(config.top_k)
_bm25_budget_cfg = getattr(config, "bm25_budget", None)
_dense_budget_cfg = getattr(config, "dense_budget", None)
max_k_hybrid = max(_kfinal, _stage1_k if _two_stage else _kfinal)
bm25_ks = int(_bm25_budget_cfg) if _bm25_budget_cfg is not None else max_k_hybrid
dense_ku = int(_dense_budget_cfg) if _dense_budget_cfg is not None else max_k_hybrid
logger.info(
    "Hybrid budgets: Ku(dense)=%d Ks(bm25)=%d Kfinal=%d rrf_k=%s",
    dense_ku, bm25_ks, _kfinal, getattr(config, "rrf_k", 60),
)
bm25_ranked_lists, _ = bm25_rank(..., bm25_ks, ...)
```

**Change 2** (dense budget, lines ~418–430): Dense candidate list uses `dense_ku_cutoff` when in hybrid mode:

```python
# dense_mode.py — retrieval_cutoff block (AFTER patch)
max_k = max(config.top_k)
retrieval_cutoff = max(max_k, stage1_admission_k if use_two_stage else max_k)
# Hybrid dense budget: extend dense depth to dense_ku when bm25_ranked_lists is present.
_dense_budget_cfg = getattr(config, "dense_budget", None)
dense_ku_cutoff = retrieval_cutoff
if bm25_ranked_lists is not None and _dense_budget_cfg is not None:
    dense_ku_cutoff = max(retrieval_cutoff, int(_dense_budget_cfg))
```

Then the scoring loop (line ~618) uses `dense_ku_cutoff`:
```python
top_indices = order[:dense_ku_cutoff]  # was: order[:retrieval_cutoff]
```

**Change 3** (diagnostics, after RRF fusion): Per-query diagnostic log at DEBUG level:

```python
# dense_mode.py — after RRF fusion block
for i, q in enumerate(grounded_queries):
    dense_set = set(rankings_per_query[i][0])
    bm25_set = set(rankings_per_query[i][1])
    fused_set = set(ranked_lists[i])
    union_not_in_fused = (dense_set | bm25_set) - fused_set
    if union_not_in_fused:
        logger.debug(
            "RRF[q=%s]: union=%d, fused=%d, dropped_from_union=%d "
            "(expected: union may exceed Kfinal=%d, extra items truncated by max_k)",
            q.get("id", q.get("query_id", i)),
            len(dense_set | bm25_set), len(fused_set),
            len(union_not_in_fused), retrieval_cutoff,
        )
```

---

## 9. Confirmed Working Proof

Global GiC@20 simulation (all 50 queries) using the dense@20 lists from the experiment and re-running BM25 at two budgets:

| Configuration | GiC@20 | Improvement |
|---|---|---|
| Original (Ks=20) | 48/50 = **0.960** | baseline |
| Fixed (Ks=100) | 49/50 = **0.980** | +0.020 |
| Dense-only ceiling | 50/50 = 1.000 | — |

Regression query detail:

| query_id | Dense rank | Orig hybrid | Fixed(Ks=100) | Verdict |
|---|---|---|---|---|
| `batch_003_14` | 12 | missing | **rank 6** | GIC restored ✓ |
| `batch_005_07` | 18 | missing | still missing | Vocabulary mismatch — unfixable by budget |
| `blind_001_09` | 7 | rank 14 | **rank 6** | rank improved ✓ |
| `batch_006_03` | 7 | rank 12 | **rank 4** | rank improved ✓ |
| `batch_003_02` | 8 | rank 14 | rank 17 | slightly worse (BM25 noise) |
| `batch_004_05` (gold 1,2) | 7/8 | rank 13/15 | rank 16/18 | slightly worse (BM25 noise) |
| `batch_004_05` (gold 3) | 16 | missing | still missing (Ks=200 fixes it) | needs Ks=200 |

---

## 10. Why Hybrid Underperforms for the Remaining Rank Push-Outs

For `batch_003_02`, `batch_004_05`, and their gold items that get demoted: BM25 at `Ks=100` retrieves additional lexically-matching but semantically-wrong items. Because RRF is rank-based, each BM25 item at rank ≤ 60 contributes `≥ 1/120 = 0.00833` to its RRF score. The gold (dense rank 7–8, no BM25 match) gets only `≈ 0.015`. BM25 items ranked 1–10 can each score `0.016–0.026`, outcompeting the gold.

This is expected hybrid behavior: BM25 is surfacing documents that contain the exact query tokens but not the relevant rule clause. The fix here is a downstream reranker (cross-encoder), not a budget change. This is well-documented in the research baseline (`Docs/Research/Evidence-Based Hybrid Retrieval Architecture.md`, §Fusion algorithms):

> "Hybrid can improve recall while slightly hurting MRR@10 if lexical injects distractors near the top. This is a known practical point in hybrid ranking."

---

## 11. Recommended Next Steps

### Immediate (this sprint)

**1. Set `bm25_budget: 100` in the Starfinder hybrid YAML** (and create one for SwordsAndWizardry hybrid too):

```yaml
# retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml
# Add to hybrid variant:
bm25_budget: 100
dense_budget: 100   # optional; set if you want deeper dense candidates too
```

This single change restores GiC@20 from 0.960 → 0.980 and improves rank for 2 of the 4 push-out queries. Expected run time: same as current hybrid (BM25 is fast at any budget).

**2. Re-run the bakeoff with `bm25_budget=100` for all four models** to get updated comparative metrics. The current bakeoff results are contaminated by the Ks=Kfinal starvation bug. The real question — does hybrid add value over dense — cannot be answered until budgets are correct.

**3. Add `bm25_budget` and `dense_budget` to `retrieval_lab/orchestration/config_access.py:RunFlags`** so it propagates cleanly through the flags system (currently the patch reads from `config` directly via `getattr`, which works but bypasses the typed interface):

```python
# retrieval_lab/orchestration/config_access.py:RunFlags (add to dataclass)
bm25_budget: Optional[int]
dense_budget: Optional[int]

# retrieval_lab/orchestration/config_access.py:read_run_flags()
bm25_budget=getattr(config, "bm25_budget", None),
dense_budget=getattr(config, "dense_budget", None),
```

### Short-term (next 1–2 sprints)

**4. Run the oracle check as a CI assertion.** The oracle pattern (`dense@200 ∪ bm25@200`) is a cheap correctness bound. Add it to the experiment report output (or as a separate check script). Any experiment where `oracle_union_gic < dense_gic` should trigger a warning — it means the BM25 index or ID mapping has diverged from the dense corpus.

Relevant code: `retrieval_lab/orchestration/dense_mode.py` lines 668–700 (the RRF fusion block now has the per-query diagnostics at DEBUG; promote to a proper report artifact).

**5. Address `batch_005_07`-type vocabulary misses.** This query ("Sure Footing" / "movement restriction" / "grabbed") has zero lexical overlap between query and gold text — confirmed BM25 rank is not-in-200 at any budget. The gold text uses the term "grabbed" while the rule uses implementation language. Solutions:

- Query enhancement: expand with synonym/paraphrase (existing `query_enhancement` infrastructure in `dense_mode.py`)
- Embedding enrichment: the `embedding_enrichment_profile` field in config can inject `structural_path` or `topic_tags` into the passage text to improve topical anchoring
- Accept as a hard miss category and track separately in `miss_classification.json` (already done — classified as `vocabulary_mismatch`)

**6. Run a headroom sweep** to empirically establish the Pareto frontier for this corpus:

```yaml
# Three configs to run:
bm25_budget: 20    # current (broken baseline)
bm25_budget: 100   # recommended fix
bm25_budget: 200   # max recall test
```

Plot GiC@20, MRR, and nDCG@10 for each. Expectation (from the research baseline §Budget strategies): GiC should be non-decreasing with budget; MRR may dip at very large budgets due to noise.

### Medium-term (future sprints)

**7. Consider a cross-encoder reranker as Stage 2** for queries where BM25 introduces noise. The existing infrastructure supports this:

```python
# config.py line 195
reranker: Optional[str] = None  # e.g., "cross-encoder/ms-marco-MiniLM-L6-v2"
```

And in `dense_mode.py` lines 680–760, `hybrid+rerank` mode is already wired. Setting `retrieval_mode: hybrid+rerank` with a cross-encoder would rerank the top-50 hybrid candidates, potentially recovering the rank quality losses seen in `batch_003_02` and `batch_004_05`.

**8. Explore convex-combination (CC) fusion as an alternative to RRF.** The research baseline (`§Fusion algorithms`) documents that CC with BM25 normalization can outperform RRF in-domain. The current `HybridRetriever` in `DungeonMindServer/ruleslawyer/hybrid_retriever.py` already uses weighted linear combination (CC with min-max normalization, `lexical_weight=0.4, semantic_weight=0.6`). The lab (`sparse_retrieval.py`) only implements RRF. A CC variant in the lab would allow direct comparison.

**9. Log `Ku`, `Ks`, `Kfinal`, and `rrf_k` in `run_manifest.json` and `metrics.json`** so future run comparisons can detect budget mismatches at a glance. Currently these are buried in `config` inside the manifest but not surfaced as top-level fields in `metrics.json`.

---

## 12. What This Audit Does NOT Explain

The audit establishes that hybrid underperformance is **partly** due to budget starvation. However, the following questions remain open:

1. **MRR gap after budget fix**: Even with `Ks=100`, MRR will likely still be below dense-only for some queries (the `batch_003_02` / `batch_004_05` rank push-outs). This is not a wiring bug — it is BM25 introducing lexical distractors. Resolving it requires a reranker.

2. **Swords & Wizardry hybrid results**: The audit was scoped to Starfinder. The SWCR bakeoff shows hybrid occasionally better (bge-m3, nomic), which is consistent with Ks=20 starvation *plus* those models having more lexical overlap in their gold sets. The same Ks fix should be applied to SWCR runs and re-evaluated.

3. **Dense budget (`Ku`) effect**: We only had `dense@20` from the experiment to work with. The simulation assumed `Ku=20` (unchanged). Setting `dense_budget=100` would let dense provide 100 candidates to RRF, which could further improve GiC for items at dense rank 21–100. A proper re-run with `dense_budget=100` is needed to measure this.

4. **Whether `bge-m3` should use CLS pooling instead of mean pooling**: The research baseline (`§bge-m3`) notes its dense representation is the normalized CLS token, not mean pool. The current standardized recipe uses mean pooling across all models. This is a separate accuracy concern, not a hybrid wiring concern.

---

## 13. Summary Table of Findings

| Check | Result | Severity |
|---|---|---|
| Corpus identity (Invariant A) | PASS | — |
| BM25 and dense over same corpus | PASS | — |
| ID compatibility (gold vs candidates) | PASS | — |
| Candidate monotonicity (Invariant B) | VACUOUS PASS / FUNCTIONAL FAIL | **High** |
| Ku/Ks = Kfinal = 20 (budget starvation) | **CONFIRMED BUG** | **High** |
| RRF truncation evicts dense gold at rank 12–18 | **CONFIRMED** | **High** |
| BM25 vocabulary mismatch for `batch_005_07` | TRUE MISS (not a bug) | Low |
| BM25 adds rank noise for `batch_003_02` / `batch_004_05` | Expected hybrid behavior | Low |
| No per-query BM25 rank logged in outputs | **Missing instrumentation** | Medium |
| `bm25_budget` / `dense_budget` not configurable | **Patched** | — |

---

## 14. Files Changed by This Audit

| File | Change | Lines |
|---|---|---|
| `retrieval_lab/config.py` | Added `bm25_budget: Optional[int]` and `dense_budget: Optional[int]` fields | ~158–174 |
| `retrieval_lab/orchestration/dense_mode.py` | BM25 uses `bm25_ks` instead of `max_k_hybrid`; logs Ku/Ks/Kfinal at INFO | ~1280–1320 |
| `retrieval_lab/orchestration/dense_mode.py` | Dense loop uses `dense_ku_cutoff` (extends when `dense_budget` set) | ~418–430, ~618 |
| `retrieval_lab/orchestration/dense_mode.py` | Per-query DEBUG log after RRF: union size vs fused size vs Kfinal | ~677–700 |

**Files that should be updated next** (not yet changed):

| File | Needed change |
|---|---|
| `retrieval_lab/orchestration/config_access.py:RunFlags` | Add `bm25_budget`, `dense_budget` typed fields |
| `retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml` | Add `bm25_budget: 100` for hybrid variant |
| SWCR hybrid YAML (when one exists) | Same |
