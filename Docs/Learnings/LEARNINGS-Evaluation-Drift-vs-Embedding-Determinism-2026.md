# Evaluation drift vs embedding determinism (baseline selection risk)

**Date:** 2026-03  
**Context:** Bakeoff runs looked inconsistent with prior "retrieval_best/current" results. We needed to determine whether this was random embedding behavior or evaluation/setup drift.

## 1. Key finding

The retrieval stack behaves deterministically for fixed inputs.  
The observed mismatch is primarily from **evaluation drift** (benchmark/corpus contract changed), not embedding randomness.

## 2. Evidence for determinism

A Starfinder hybrid standardized run was repeated with the same configuration, same model, same benchmark path, same run-id family, and fixed seed:

- config: `retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml`
- model: `all-mpnet-base-v2`
- recipe: `standardized`
- benchmark: `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json`
- seed: `42`

The repeated run reproduced the same headline metrics as the earlier bakeoff run:

- MRR: `0.2047`
- R@10: `0.4000`
- H@10: `0.4000`
- Gold-in-candidates: `0.4600`

Conclusion: with fixed inputs, the pipeline is near-deterministic in practice.

## 3. Where drift occurred (root causes)

### 3.1 Starfinder benchmark contract drift

Between the prior strong run and bakeoff run, the benchmark artifact changed materially:

- prior run (`starfinder_player_core_50q_post_full_gold_curation_20260228_184410`):
  - query batch size/hash from manifest: larger file, different hash
  - benchmark lint: `required_gold_empty = 1`
- bakeoff run (`bakeoff_sf_hybrid_std_20260301_031213`):
  - query batch hash changed
  - benchmark lint: `required_gold_empty = 38`

This is not a small perturbation. It changes the effective evaluability of the suite.

### 3.2 S&W corpus/query-set drift

Two different S&W evaluation tracks were compared as if they were equivalent:

- Historical strong run (`SW Complete Revised PDF` track):
  - corpus units: `734`
  - queries: `38`
  - grounded: `34`
  - MRR: `0.6104`
- Bakeoff run (`Swords&Wizardry` track):
  - corpus units: `482` (and `1341` in enrichment-full run)
  - queries: `21`
  - grounded: `2` or `3`
  - MRR: `0.0000` to `0.0034`

These are different corpora and benchmark contracts. Model comparisons across them are invalid for baseline selection.

### 3.3 Annotation-hygiene dominates retrieval signal

When `required_gold_empty` is high, metrics become dominated by annotation coverage rather than ranking quality:

- low grounding coverage inflates `no_gold_defined`
- `gold_not_in_candidates` and MRR become less diagnostic of model quality
- model-vs-model differences are swamped by benchmark hygiene noise

## 4. What this means for baseline selection

At present, **model-vs-model conclusions are not trustworthy** until the evaluation contract is locked.  
Otherwise, we are measuring benchmark/annotation drift more than embedding quality.

Baseline decision risk under drift:

1. False rejection of good models (because gold is missing or ungrounded).
2. False confidence in weak models (if denominator shifts favorably).
3. Non-transferable conclusions between corpora/runs.

## 5. Contract to lock before any baseline decision

For each corpus, freeze and record:

1. **Corpus contract**
   - `substrate_path`
   - `document_id`
   - `substrate_version`
   - `corpus_fingerprint`
2. **Benchmark contract**
   - benchmark path
   - benchmark sha256
   - query count
   - lint summary (`required_gold_empty` threshold)
3. **Retrieval contract**
   - retrieval mode (dense/hybrid)
   - fusion and rerank policy knobs
   - top-k list
4. **Embedding contract**
   - model id + revision
   - recipe mode
   - pooling/normalize/max_seq_len/prefixes
5. **Run key contract**
   - `(corpus, run_id family, model, recipe, enrichment profile)`

## 6. Operational guardrails (recommended)

1. Hard fail on corpus/run mismatch (already added):  
   `run_id incompatible with current corpus shape; re-embed with same config.`
2. Hard fail if benchmark hash differs from expected for a named baseline track.
3. Hard fail (or explicit opt-in override) when `required_gold_empty` exceeds a small threshold.
4. Publish run manifest + embedding provenance for every baseline candidate run.

## 7. Practical interpretation

- Embeddings are mostly deterministic in this setup.
- The recent mismatch is explained by **evaluation drift**.
- The next correct step is not "pick the best model now"; it is "freeze eval contracts, then compare models."

Only after that lock should we answer baseline model selection (sentence-transformer vs nomic vs bge-m3 vs pplx-embed variants).

## 8. Related artifacts

- `out/StarFinderPlayerCore/retrieval_best/current/REPORT.md`
- `out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF/retrieval_best/current/REPORT.md`
- `out/retrieval_lab/bakeoff/bakeoff_sf_hybrid_std_20260301_031213/REPORT.md`
- `out/retrieval_lab/bakeoff/bakeoff_sw_hybrid_std_20260301_031442/REPORT.md`
- `out/retrieval_lab/bakeoff/bakeoff_sw_hybrid_std_enrich_full_20260301_174755/REPORT.md`
- `out/retrieval_lab/experiments/determinism_check_sf_hybrid_std_20260301_212033/REPORT.md`
