# SWCR Retrieval Deep Dive (2026-03-17)

## Scope

Investigate why SWCR broad clean-subset retrieval is low (`MRR=0.2868`) and determine whether this is benchmark debt or a real retrieval problem.

Primary artifact analyzed:
- `out/retrieval_lab/experiments/rerun_hardened_swcr_benchmark_20260313_140754`

## Baseline Snapshot (clean_subset)

From `REPORT.clean_subset.md`:
- Queries: 21 (grounded 21/21)
- `MRR`: 0.2868
- `ReqFSH@10`: 0.1905
- `Gold-in-candidates`: 0.8571
- Failure buckets: `gold_not_in_candidates=3`, `success=18`

Interpretation:
- This is **not** primarily benchmark debt (grounding coverage is complete on this surface).
- The dominant failure mode is retrieval quality: missing gold candidates (ceiling failures) and deep-ranking hits.

## Failure Analysis

From `per_query.clean_subset.json` and `retrieved_chunks.clean_subset.json`:
- Hard misses (`retrieval_miss`): 3/21
  - `sw_rev_u01_roles_and_authority`
  - `sw_rev_u04_player_actions_in_combat`
  - `sw_rev_s02_treasure_division_procedure`
- Additional weak ranking among hits (`first_gold_rank > 10`): 6/21
  - worst examples include `sw_rev_s15_light_sources_duration` (rank 48), `sw_rev_s13_encumbrance_and_movement` (rank 42), `sw_rev_u05_what_must_be_tracked` (rank 33)

Qualitative pattern:
- Queries ask for procedural and role-allocation semantics that spread across multiple sections.
- Retrieved top results are often topically adjacent but not the exact contract gold, indicating ranking/representation drift rather than missing benchmark annotations.

## Configuration and Contract Drift Notes

- The hardened run that produced `MRR=0.2868` used `dense` mode and a contract-valid benchmark snapshot at execution time.
- Current attempt to rerun SWCR hybrid canonical config hits benchmark contract mismatches (run_id/substrate_version/fingerprints), showing the SWCR benchmark contract has drifted relative to present substrate outputs.
- This contract drift is operational debt, but it does **not** explain the low score in the hardened run itself.

## Conclusions

1. SWCR broad low MRR is a **real retrieval problem** on this benchmark surface.
2. The main bottleneck is candidate quality and rank depth (3 hard misses + multiple very deep first-gold ranks).
3. Contract drift now blocks straightforward apples-to-apples reruns and should be fixed before promotion decisions that depend on fresh SWCR runs.

## Recommended Remediation

1. **Re-lock SWCR contract to current substrate**
   - Recompute benchmark contract and projection for the intended SWCR substrate version.
   - Ensure run_id/substrate_version/fingerprints align before comparative sweeps.
2. **Run canonical hybrid (CC/minmax/lambda=0.7) on the re-locked contract**
   - Compare against dense baseline on the same contract; prioritize `gold_in_candidates`, `MRR`, and `ReqFSH@10`.
3. **Miss-focused diagnostics**
   - For the 3 hard misses, inspect section-path mismatch and lexical aliasing between query phrasing and gold passages.
   - Add targeted retrieval diagnostics (query rewrite probes, alternate lexical formulations) as analysis-only artifacts.
4. **Do not treat this as benchmark-cleanup-only**
   - Keep remediation framed as retrieval improvement work; benchmark contract maintenance is prerequisite plumbing.
