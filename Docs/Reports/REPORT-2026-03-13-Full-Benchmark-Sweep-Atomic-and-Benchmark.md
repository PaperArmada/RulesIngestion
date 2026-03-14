# Full Benchmark Sweep: Hardened Rerun Refresh

**Date:** 2026-03-13  
**Scope:** Dense retrieval (`all-mpnet-base-v2`) across all active atomic and benchmark families under the ratified hardening regime  
**Repo:** `RulesIngestion`

## Executive Summary

This refresh supersedes the earlier permissive sweep as the primary readout.

- All 10 successful reruns finished with `contract_valid=true` and `promotion_ready=true`.
- Every successful rerun emitted both `metrics.clean_subset.json` and `metrics.full_working_set.json`.
- The clean subset now gives a believable scoreboard; the full working set still usefully exposes benchmark debt.

Top-line family means:

| Family | Surface | Mean MRR | Mean Hit@10 | Mean required Hit@10 | Mean gold ceiling | Mean grounding |
|---|---|---:|---:|---:|---:|---:|
| Atomic | Clean subset | 0.5719 | 0.8776 | 0.7151 | 0.9110 | 1.0000 |
| Atomic | Full working set | 0.4877 | 0.7474 | 0.7151 | 0.9110 | 0.8632 |
| Benchmark | Clean subset | 0.5751 | 0.8513 | 0.7203 | 0.9606 | 1.0000 |
| Benchmark | Full working set | 0.5466 | 0.8143 | 0.7119 | 0.9612 | 0.9560 |

Interpretation:

- On the ratified clean subset, atomic and benchmark are now much closer than the earlier report suggested.
- On the full working set, benchmark still remains healthier than atomic.
- The main remaining contamination is concentrated in Starfinder atomic and PHB5e benchmark.

## Run Matrix

All runs were executed with:

- `uv run python -m retrieval_lab.run_experiment` or equivalent in-process invocation of `retrieval_lab.run_experiment._run_experiment`
- Dense retrieval mode
- Model: `all-mpnet-base-v2`
- Hardened ratification gates active
- Successful runs: no contract override

Successful experiment outputs:

### Atomic

- `rerun_hardened_phb5e_atomic_20260313_140530`
- `rerun_hardened_pf2e_atomic_20260313_140542`
- `rerun_hardened_sr4_atomic_20260313_140555`
- `rerun_hardened_starfinder_atomic_20260313_140608`
- `rerun_hardened_swcr_atomic_20260313_140616`

### Benchmark

- `phb_autogold_pilot_20260306`
- `rerun_hardened_pf2e_benchmark_20260313_140636`
- `sr4_autogold_pilot`
- `rerun_hardened_starfinder_benchmark_20260313_140744`
- `rerun_hardened_swcr_benchmark_20260313_140754`

## Hardened Regime Notes

- The first attempt to rerun SR4 broad failed immediately because `sr4_autogold_pilot.yaml` still carried `allow_benchmark_contract_mismatch: true`.
- That failure was correct behavior under the new ratified policy.
- The blocked tail of the matrix was rerun with that override forced off at runtime, after which SR4 broad, Starfinder broad, and SWCR broad all completed successfully.
- `PHB5e` broad and `SR4` broad still write into legacy output directories because of current experiment/config naming behavior; the artifacts are valid, but the output naming should be cleaned up.

## Atomic Results

| Corpus | Clean / Total | Working-set queries | Clean MRR | Full MRR | Clean Hit@10 | Full Hit@10 | Clean grounding | Full grounding | Clean failures | Full failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| PHB5e | 19 / 19 | 0 | 0.4867 | 0.4867 | 0.8421 | 0.8421 | 1.0000 | 1.0000 | hit=17, retrieval_miss=2 | hit=17, retrieval_miss=2 |
| PF2e | 17 / 19 | 2 | 0.5647 | 0.5052 | 0.8235 | 0.7368 | 1.0000 | 0.8947 | hit=15, retrieval_miss=2 | hit=15, grounding_failure=2, retrieval_miss=2 |
| SR4 | 18 / 19 | 1 | 0.6184 | 0.5858 | 0.8889 | 0.8421 | 1.0000 | 0.9474 | hit=17, retrieval_miss=1 | hit=17, grounding_failure=1, retrieval_miss=1 |
| Starfinder | 10 / 19 | 9 | 0.6333 | 0.3333 | 1.0000 | 0.5263 | 1.0000 | 0.5263 | hit=10 | hit=10, grounding_failure=9 |
| SWCR | 18 / 19 | 1 | 0.5565 | 0.5273 | 0.8333 | 0.7895 | 1.0000 | 0.9474 | hit=15, retrieval_miss=3 | hit=15, grounding_failure=1, retrieval_miss=3 |

### Atomic Takeaways

- `PHB5e` atomic is now fully ratified and stable: clean and full are identical.
- `PF2e`, `SR4`, and `SWCR` atomic are close to stable; each has only 1-2 working-set queries left.
- `Starfinder` atomic is the clearest proof that the dual-scoreboard model is necessary: the clean subset is perfect on `Hit@10`, while the full surface is dragged down by 9 working-set queries that all currently land as `grounding_failure`.
- Atomic clean-subset performance is now strong enough to be taken seriously as a comparative signal, but not yet as a single headline gate because the working-set debt is still extremely uneven by corpus.

## Benchmark Results

| Corpus | Clean / Total | Working-set queries | Clean MRR | Full MRR | Clean Hit@10 | Full Hit@10 | Clean grounding | Full grounding | Clean failures | Full failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| PHB5e | 37 / 50 | 13 | 0.5875 | 0.4447 | 0.8649 | 0.6800 | 1.0000 | 0.7800 | hit=35, retrieval_miss=2 | hit=37, grounding_failure=11, retrieval_miss=2 |
| PF2e | 50 / 50 | 0 | 0.8254 | 0.8254 | 0.9400 | 0.9400 | 1.0000 | 1.0000 | hit=50 | hit=50 |
| SR4 | 50 / 50 | 0 | 0.5597 | 0.5597 | 0.9600 | 0.9600 | 1.0000 | 1.0000 | hit=50 | hit=50 |
| Starfinder | 50 / 50 | 0 | 0.6162 | 0.6162 | 0.9200 | 0.9200 | 1.0000 | 1.0000 | hit=50 | hit=50 |
| SWCR | 21 / 21 | 0 | 0.2868 | 0.2868 | 0.5714 | 0.5714 | 1.0000 | 1.0000 | hit=18, retrieval_miss=3 | hit=18, retrieval_miss=3 |

### Benchmark Takeaways

- `PF2e`, `SR4`, and `Starfinder` broad benchmarks are fully ratified and clean.
- `PHB5e` broad remains the main benchmark curation debt surface: 13 working-set queries and an 0.1428 absolute MRR drop from clean to full.
- `SWCR` broad is now clean but weak. This is important: its current low score is no longer benchmark-debt noise, it looks like a real retrieval problem on a ratified surface.

## Cross-Family Interpretation

What is trustworthy now:

- `clean_subset` comparisons across corpora and across atomic vs benchmark.
- Any run with `promotion_ready=true` and `contract_valid=true`, which is now all 10 successful reruns.
- The conclusion that ratification debt, not just retriever quality, was previously contaminating the matrix.

What remains diagnostic rather than release-gating:

- `full_working_set` on corpora with large working-set tails, especially `Starfinder` atomic and `PHB5e` benchmark.
- Any absolute story about atomic as a whole without explicitly reporting how many ratified queries are actually in play for each corpus.

Important comparative read:

- Earlier reports made atomic look categorically weaker than broad.
- Under the hardened clean subset, the family means are nearly tied on MRR: `Atomic=0.5719`, `Benchmark=0.5751`.
- The meaningful current gap is not atomic vs broad in the abstract; it is ratified clean vs debt-contaminated full.

## Key Findings

1. **The hardening work succeeded operationally.**  
   All final reruns are contract-valid, promotion-ready, and emit the intended dual-scoreboard artifacts.

2. **The dual-scoreboard model is justified.**  
   `Starfinder` atomic moves from `MRR=0.3333` on the full working set to `MRR=0.6333` on the clean subset, entirely due to working-set debt.

3. **PHB5e broad still needs editorial cleanup.**  
   `PHB5e` benchmark drops from `MRR=0.5875` clean to `0.4447` full, with `grounding_failure=11` on the full surface.

4. **SWCR broad is now a true retriever-quality concern.**  
   It has no working-set debt, full grounding coverage, and still scores only `MRR=0.2868`, `Hit@10=0.5714`.

5. **Most corpora are close to ratified on atomic.**  
   `PHB5e` is fully clean; `PF2e`, `SR4`, and `SWCR` are each one small cleanup pass away; `Starfinder` atomic is the only major remaining outlier.

## Recommendations

1. **Remove the stale `allow_benchmark_contract_mismatch` flag from `sr4_autogold_pilot.yaml`.**  
   The run now works only because the rerun forced that override off at runtime.

2. **Finish atomic cleanup on `Starfinder`.**  
   That one file still contains 9 working-set queries and is the largest remaining source of benchmark contamination.

3. **Clean up `PHB5e` broad working-set debt.**  
   It is the only broad benchmark where clean vs full materially diverges.

4. **Investigate `SWCR` broad as a retrieval problem, not a benchmark problem.**  
   The benchmark is clean; the model still misses too often.

5. **Refresh any downstream summary or dashboard to use `clean_subset` as the default headline metric.**  
   `full_working_set` should remain visible, but as a secondary diagnostic scoreboard.

## Notes

- Artifacts live under `out/retrieval_lab/experiments/<experiment_id>/`.
- Successful runs all emitted `prod_readiness.json`, `evaluation_surfaces.json`, `metrics.clean_subset.json`, and `metrics.full_working_set.json`.
- This refresh intentionally centers the hardened rerun rather than the older permissive sweeps.
