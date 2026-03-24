# Reference: Retrieval Benchmark Results Timeline

**Purpose:** Working reference for current retrieval benchmark results, organized as a timeline of decision-driving reports.
**Scope:** Retrieval and benchmarking outcomes (not full ingestion archaeology).
**Updated at:** 2026-03-24
**Status:** Canonical reference for README linking.

---

## How to use this doc

- Start with the timeline to understand what changed and why.
- Use the report index and metrics snapshot tables to jump into detail.
- Use the "Decision impact" and "What we learned" columns to trace how results informed policy and architecture.
- Use the metric and acronym glossaries to keep naming consistent across docs.

---

## Quick reference table (current benchmark results)

Primary source for this table:
`Docs/Reports/REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md`
(hardened rerun refresh, clean subset + full working set split).

| Corpus | Atomic benchmark (queries) | Main benchmark (queries) | Atomic clean subset (2026-03-13) | Benchmark clean subset (2026-03-13) | Current read |
|---|---|---|---|---|---|
| PHB5e | `evals/retrieval/PHB5e/dnd_5e_2024_atomic_rules_benchmark.v2_merged2000_min200.json` (19) | `evals/retrieval/PHB5e/dnd_5e_2024_rules_50q_benchmark.json` (50) | `19/19` clean, `MRR=0.4867` | `37/50` clean, `MRR=0.5875` (full `MRR=0.4447`) | Atomic is ratified; broad benchmark still has notable working-set debt. |
| PF2e | `evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_atomic_rules_benchmark.json` (19) | `evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_50q_benchmark.json` (50) | `17/19` clean, `MRR=0.5647` | `50/50` clean, `MRR=0.8254` | Broad benchmark is fully clean and strong; atomic is near-clean. |
| SR4 | `evals/retrieval/ShadowRun4e/shadowrun4e_anniversary_atomic_rules_benchmark.json` (19) | `evals/retrieval/ShadowRun4e/benchmark_shadowrun_sr4_retrieval.json` (50) | `18/19` clean, `MRR=0.6184` | `50/50` clean, `MRR=0.5597` | Broad benchmark is fully clean; atomic has small remaining debt. |
| Starfinder | `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_atomic_rules_benchmark.json` (19) | `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json` (50) | `10/19` clean, `MRR=0.6333` (full `MRR=0.3333`) | `50/50` clean, `MRR=0.6162` | Biggest atomic debt tail; broad benchmark is fully clean. |
| SWCR | `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_atomic_rules_benchmark.v3_swcr_merged2000_min100.json` (19) | `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json` (21) | `18/19` clean, `MRR=0.5565` | `21/21` clean, `MRR=0.2868` | Broad benchmark is clean but weak, indicating true retrieval difficulty. |

Use `clean_subset` as the default headline for recommendation decisions; treat
`full_working_set` primarily as debt diagnostics where clean/full diverge.

---

## Metric glossary (canonical naming)

Use these names consistently in summaries and tables. If a source report uses a
different token, map it using the aliases below.

| Canonical name | Meaning | Typical range | Common aliases in older docs |
|---|---|---|---|
| `MRR` | Mean Reciprocal Rank of first relevant gold item (higher is better, rank-sensitive). | `0..1` | `mean_reciprocal_rank` |
| `nDCG@10` | Normalized Discounted Cumulative Gain at 10 (ranking quality over multiple relevant items). | `0..1` | `NDCG@10` |
| `Recall@10` | Fraction of gold evidence retrieved in top 10 (coverage metric). | `0..1` | `R@10`, `required_recall@10` (context-dependent) |
| `Hit@10` | Query-level success: at least one relevant gold item appears in top 10. | `0..1` | `H@10` |
| `ReqFSH@10` | Required Full-Set Hit at 10: all required gold obligations satisfied in top 10. | `0..1` | `required_full_set_hit@10` |
| `Gold-in-Candidates` | Ceiling metric: gold appears somewhere in candidate set before final truncation/rerank. | `0..1` | `gold_in_candidates`, `Gold-in-candidates` |
| `clean_subset` | Ratified-core evaluation surface used for recommendation-grade comparisons. | surface label | `clean` |
| `full_working_set` | Full active benchmark surface; includes unresolved/working-set debt and is diagnostic-first. | surface label | `full`, `working_set` |
| `contract_valid` | Run contract checks passed for corpus/benchmark projection compatibility. | `true/false` | benchmark contract valid |
| `promotion_ready` | Run emitted promotion-grade artifacts and passed promotion gating checks. | `true/false` | prod ready |

---

## Retrieval acronym glossary

| Acronym | Expanded form | Meaning in this repo |
|---|---|---|
| `CC` | Convex Combination | Score-level hybrid fusion where dense and BM25 scores are blended by a lambda weight. |
| `RRF` | Reciprocal Rank Fusion | Rank-based hybrid fusion that combines rank positions rather than raw scores. |
| `BM25` | Best Matching 25 | Sparse lexical retrieval function used as the lexical branch in hybrid retrieval. |

---

## Timeline (high signal, non-comprehensive)

### 2026-03-04: Embedding baseline decision-grade bakeoff

- **Primary report:** `Docs/Reports/REPORT-Embedding-Bakeoff-Comprehensive-2026-03-04.md`
- **Decision impact:** Established the embedding baseline used by retrieval defaults and downstream comparisons.
- **What we learned:** Model behavior differs by corpus; default must optimize for robust cross-corpus operation, not only per-corpus peak score.
- **Design references informed:** `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md`, `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`

### 2026-03-05: Hybrid CC parity and lambda sweep (clean run)

- **Primary report:** `Docs/Reports/REPORT-Hybrid-Bakeoff-2026-03-05-Full.md`
- **Decision impact:** Locked hybrid default posture around CC fusion, minmax normalization, and lambda defaults with corpus-aware nuance.
- **What we learned:** Hybrid uplift is corpus/model dependent; one global knob is not enough for every edge case, but stable defaults are still possible.
- **Design references informed:** `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md`, `Docs/Design/ARCHITECTURE-RERANKING-TOOLING.md`, `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`

### 2026-03-13: Hardened full benchmark sweep refresh

- **Primary report:** `Docs/Reports/REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md`
- **Decision impact:** Promoted clean-subset-first interpretation and hardened contract-valid scoreboard usage.
- **What we learned:** Dual-scoreboard (`clean_subset` vs `full_working_set`) is essential to separate retrieval quality from benchmark debt.
- **Design references informed:** `Docs/Design/RETRIEVAL_LAB.md`, `Docs/Design/gold_resolution_design.md`, `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`

### 2026-03-17: SWCR and decomposition deep dives

- **Primary reports:** `Docs/Reports/REPORT-SWCR-Retrieval-Deep-Dive-2026-03-17.md`, `Docs/Reports/REPORT-Decomposition-System-Comprehensive-Review.md`, `Docs/Reports/REPORT-Query-Decomposition-Per-Query-Investigation-2026-03-17.md`
- **Decision impact:** Clarified where retrieval weaknesses are true model/retrieval issues vs benchmark/data-process issues, and where decomposition should remain controlled.
- **What we learned:** Per-query diagnostics change conclusions; aggregate metrics alone can hide failure modes and policy risk.
- **Design references informed:** `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md`, `Docs/Design/SPEC-Controller-V0-Operators.md`, `Docs/Design/RETRIEVAL_LAB.md`

---

## Report index and learning map

| Report | Primary use | Key learning | Informed decisions/docs | When |
|---|---|---|---|---|
| `Docs/Reports/REPORT-Embedding-Bakeoff-Comprehensive-2026-03-04.md` | Embedding model baseline selection | Cross-corpus stability matters as much as peak per-track score. | `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md`, `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md` | 2026-03-04 |
| `Docs/Reports/REPORT-Hybrid-Wiring-Audit-2026-03-04.md` | Validate hybrid plumbing and scoring assumptions | Metric conclusions are only trustworthy after wiring correctness is verified. | `Docs/Design/ARCHITECTURE-RERANKING-TOOLING.md`, `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md` | 2026-03-04 |
| `Docs/Reports/REPORT-Hybrid-Bakeoff-Results-2026-03-04.md` | Early hybrid decision snapshot | Early signal aligned with later full sweep direction. | `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md` | 2026-03-05 |
| `Docs/Reports/REPORT-Hybrid-Bakeoff-2026-03-05-Full.md` | Full hybrid parameter/model/corpus sweep | CC + minmax is a durable default; lambda should be tuned with corpus/model context. | `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md`, `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md` | 2026-03-05 |
| `Docs/Reports/REPORT-2026-03-12-Atomic-Benchmark-Question-Surface-Review.md` | Question-surface quality diagnostics | Benchmark quality strongly affects metric interpretability. | `Docs/Design/gold_resolution_design.md`, `Docs/Design/RETRIEVAL_LAB.md` | 2026-03-12 |
| `Docs/Reports/REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md` | Hardened rerun baseline refresh | `clean_subset` is the trustworthy headline; `full_working_set` remains diagnostic. | `Docs/Design/RETRIEVAL_LAB.md`, `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md` | 2026-03-13 |
| `Docs/Reports/REPORT-SWCR-Retrieval-Deep-Dive-2026-03-17.md` | SWCR corpus-level retrieval diagnosis | Some low scores are true retriever challenges, not benchmark debt artifacts. | `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md` | 2026-03-17 |
| `Docs/Reports/REPORT-Decomposition-System-Comprehensive-Review.md` | Decomposition strategy evaluation | Decomposition should be bounded and policy-driven, not always-on. | `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md`, `Docs/Design/SPEC-Controller-V0-Operators.md` | 2026-03-16 |
| `Docs/Reports/REPORT-Query-Decomposition-Per-Query-Investigation-2026-03-17.md` | Per-query decomposition failures/wins | Per-query audits are required before promoting decomposition defaults. | `Docs/Design/SPEC-Controller-V0-Operators.md`, `Docs/Design/RETRIEVAL_LAB.md` | 2026-03-17 |

---

## Metrics snapshot for the report index

Use this as the quantitative quick read behind the learning map above.

| Report | Benchmark use | Retrieval metric signals | Decision implication | When |
|---|---|---|---|---|
| `Docs/Reports/REPORT-Embedding-Bakeoff-Comprehensive-2026-03-04.md` | Embedding baseline selection on Starfinder 50q and SWCR broad benchmark | `MRR`: best Starfinder dense `pplx=0.6921`; `Recall@10`: best `all-mpnet=0.8467`; `Gold-in-Candidates`: `1.0000` (all-mpnet) | Keep a robust baseline default posture, not a single-metric winner policy. | 2026-03-04 |
| `Docs/Reports/REPORT-Hybrid-Wiring-Audit-2026-03-04.md` | Hybrid sanity check on Starfinder 50q (all-mpnet standardized pair) | `MRR`: `0.6660 -> 0.6142` (`-0.0518`); `Hit@10`: `0.92 -> 0.86`; `Gold-in-Candidates`: `1.000 -> 0.960` | Fix wiring/budget before trusting hybrid comparisons. | 2026-03-04 |
| `Docs/Reports/REPORT-Hybrid-Bakeoff-Results-2026-03-04.md` | Early patched hybrid comparison matrix before full sweep lock-in | Confirms Convex Combination (CC) viability over Reciprocal Rank Fusion (RRF) on patched pipeline; directional signal later validated by full sweep | Promote Convex Combination (CC) path; treat Reciprocal Rank Fusion (RRF) as comparison/legacy only. | 2026-03-05 |
| `Docs/Reports/REPORT-Hybrid-Bakeoff-2026-03-05-Full.md` | Full hybrid bakeoff across corpora/models for fusion-default selection | Run health: `300/300` succeeded; avg `MRR` delta vs dense: RRF `Starfinder -0.018`, `SWCR -0.095`; CC `Starfinder +0.016`, `SWCR -0.006` | Canonical default: Convex Combination (CC) fusion + calibrated lambda/normalization; retire Reciprocal Rank Fusion (RRF) default. | 2026-03-05 |
| `Docs/Reports/REPORT-2026-03-12-Atomic-Benchmark-Question-Surface-Review.md` | PF2E parity/backstop experiment and benchmark-question hygiene | `ReqFSH@10`: `0.90 -> 0.90`; `Recall@10`: `0.92 -> 0.93`; target misses unchanged | Do not assume hybrid backstop fixes parity misses; prioritize query/annotation quality and targeted rerank paths. | 2026-03-12 |
| `Docs/Reports/REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md` | Hardened dense sweep across active atomic and broad benchmark families | Clean-family `MRR`: Atomic `0.5719` vs Benchmark `0.5751`; reliability: all `10` successful reruns are `contract_valid=true` and `promotion_ready=true` | Use `clean_subset` as default headline metric; keep `full_working_set` as debt diagnostic. | 2026-03-13 |
| `Docs/Reports/REPORT-SWCR-Retrieval-Deep-Dive-2026-03-17.md` | SWCR broad benchmark diagnostic (clean-subset behavior) | SWCR clean subset: `MRR=0.2868`, `ReqFSH@10=0.1905`, `Gold-in-Candidates=0.8571`; hard misses `3/21` | Frame SWCR as true retrieval-quality work, not benchmark-debt cleanup. | 2026-03-17 |
| `Docs/Reports/REPORT-Decomposition-System-Comprehensive-Review.md` | Decomposition architecture and policy-evaluation readiness | Metric direction: no recovery in E7 vs E6; decomposition remains non-promoted for default policy | Keep decomposition policy-gated and evidence-driven before default promotion. | 2026-03-16 |
| `Docs/Reports/REPORT-Query-Decomposition-Per-Query-Investigation-2026-03-17.md` | PHB/PF2E multihop decomposition per-query benchmark audit | PHB: worsen/improve/unchanged `11/7/49`, `hit->miss=4`; PF2E: `4/3/63`, `hit->miss=0`, `hit@10` worsened `1` | Do not promote decomposition; first resolve baseline-parity and low-yield expansion behavior. | 2026-03-17 |

---

## Canonical policy surfaces tied to these results

- `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md` (operator runbook)
- `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md` (runtime defaults and retired knobs)
- `Docs/Design/RETRIEVAL_LAB.md` (artifact contracts, surfaces, promotion semantics)
- `Docs/Design/gold_resolution_design.md` (benchmark definition/projection contract)

---

## Notes and boundaries

- This doc is intentionally concise and does not replace the underlying reports.
- If a future report supersedes a decision-grade report, append it to the timeline and update this file's `Updated at` date.
- For broad report discovery beyond this curated map, see `Docs/Reports/INDEX-Bakeoff-and-Sweep-Reports.md`.
