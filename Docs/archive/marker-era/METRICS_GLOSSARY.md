> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Metrics Glossary

**Purpose:** Single source of truth for benchmark metrics used in `rule_fact_benchmark_eval.py`. Defines what each metric computes, its intent, and caveats.

**See also:** [rule_ingestion_evaluation_criteria.md](rule_ingestion_evaluation_criteria.md) for stage-by-stage success criteria.

---

## Per-query metrics (QueryMetrics)

These are recorded per query and optionally saved via `--save-query-metrics`.

| Metric                     | Formula / Definition                                                                                                      | Intent                                        | Caveat                                                                         |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------ |
| **gold_hit**               | 1 if any gold chunk in `reachable_chunks`, else 0.                                                                        | Binary “did we reach any gold?”               | Does not account for ranking or number of golds; one gold = same as all golds. |
| **gold_found**             | Count of gold chunks in reachable set.                                                                                    | Raw recall numerator.                         | Set overlap only; not @k.                                                      |
| **gold_total**             | Total gold chunks for the query (from batch JSON).                                                                        | Raw recall denominator.                       |                                                                                |
| **total_entity_count**     | `len(entity_path)` in explanation.                                                                                        | Entity-only path size.                        | 0 in full traversal mode.                                                      |
| **total_fact_count**       | `len(attached_facts)`.                                                                                                    | Facts attached to entity path.                |                                                                                |
| **entity_traversal_depth** | Number of entity–entity edges in entity-only traversal.                                                                   | Path length in entity-only mode.              |                                                                                |
| **entity_semantic_purity** | Among entity–entity edges in path: (edges in `ENTITY_SEMANTIC_RELATIONS`) / (total entity–entity edges). Facts excluded.  | “Reasoning” edges vs structural.              | Relation sets must match intent; verify ENTITY_SEMANTIC_RELATIONS.             |
| **entity_semantic_edges**  | Count of semantic entity–entity edges.                                                                                    | Numerator for purity.                         |                                                                                |
| **entity_total_edges**     | Count of all entity–entity edges in path.                                                                                 | Denominator for purity.                       |                                                                                |
| **entity_count**           | Number of entity nodes in explanation path.                                                                               | Entity compactness (lower = tighter).         |                                                                                |
| **frame_count**            | Number of mechanic-frame entities in path (Feat, Spell, Rule, etc.).                                                      | Frame-level compactness.                      |                                                                                |
| **facts_per_entity**       | `len(attached_facts) / len(entity_path)`.                                                                                 | Assertion load: facts per entity.             |                                                                                |
| **chunks_per_entity**      | Unique chunks cited across entities / `len(entity_path)`.                                                                 | Chunks per entity.                            |                                                                                |
| **causal_coverage**        | Fraction of explanation facts that are “supported”: connected via `SEMANTIC_FACT_RELATIONS` to another fact or procedure. | Structural sanity: facts are graph-connected. | Unvalidated against rule correctness; threshold 0.9 is arbitrary.              |
| **traversal_mode**         | "full" or "entity".                                                                                                       | Which traversal was used.                     |                                                                                |

---

## Batch-aggregate metrics (printed in Summary)

Computed per batch and printed in the `=== Summary ===` block.

| Metric                             | Formula / Definition                                                                                                                                             | Intent                                                                        | Caveat                                                                                                      |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Gold chunks found**              | Sum over _scored_ queries of `len(found)`; denominator = sum of `len(gold_set)`. Recall = total_found / total_gold.                                              | Retrieval recall (set overlap).                                               | Only queries with `scoring_enabled` (behavioral + resolved mechanic targets) are included.                  |
| **Recall@5**                       | Gold chunks appearing in top-5 of ranked chunks (`_rank_chunks_from_reachable`, or after CDS rerank if `--cds-gate`).                                            | Ranking quality at k=5.                                                       | Depends on traversal order and optional CDS.                                                                |
| **Recall@10**                      | Gold chunks in top-10 of ranked chunks.                                                                                                                          | Ranking quality at k=10.                                                      | Same as above.                                                                                              |
| **Avg traversal purity**           | Mean over queries of (semantic edges in explanation / total edges). Semantic = `RELATION_WHITELIST`; structural = `STRUCTURAL_RELATIONS`.                        | Full-graph “reasoning” vs structural edges.                                   | Entity-only mode has separate entity_semantic_purity.                                                       |
| **Avg effective semantic purity**  | Same as traversal purity but excludes `belongs_to` and collapses has_fact/describes.                                                                             | Purity without ownership edges.                                               |                                                                                                             |
| **Causal coverage (CCR)**          | Mean of per-query causal_coverage. **Failures:** count of queries with CCR < 0.9.                                                                                | Structural sanity of selected facts.                                          | Threshold 0.9 is arbitrary; “supported” is graph-theoretic only, not rule-correctness.                      |
| **Hubbed causal coverage (CCR')**  | Like CCR but facts anchored to seeded/active frames count as supported.                                                                                          | CCR with frame-aware support.                                                 |                                                                                                             |
| **Minimality pass rate**           | Fraction of queries where `len(explanation_facts) ≤ bound` (5 single-mechanic, 8 multi-mechanic) and `len(explanation_frames) ≤ 3`.                              | Explanation size discipline.                                                  | Bounds are heuristic; not validated against answer quality.                                                 |
| **Justified negation rate**        | Among queries with “negative” expected answer (via `_is_negative_expected(expected_summary)`), fraction whose explanation contains `NEGATION_FACT_TYPES`.        | Negation handling.                                                            | Heuristic; negative detection is text-based.                                                                |
| **Behavioral activation rate**     | Among queries in `PHASE1_BEHAVIORAL_QUERIES`, fraction with `reachable_facts` non-empty.                                                                         | Behavioral queries that activate.                                             | Batch_001 specific.                                                                                         |
| **Structural silence correctness** | Among `PHASE1_STRUCTURAL_QUERIES`, fraction with `reachable_facts` empty.                                                                                        | Structural queries correctly silent.                                          | Batch_001 specific.                                                                                         |
| **Name resolvability**             | (Mechanic mentions that resolve to entities) / (total mechanic mentions).                                                                                        | Mention → entity resolution.                                                  |                                                                                                             |
| **Invariant violations**           | Count of queries where `explanation_facts` is not a subset of `scoring_reachable_facts` (i.e. explanation included facts not reachable under scoring adjacency). | Pipeline consistency: explanation must be contained in scoring reachable set. | Incremented in rule_fact_benchmark_eval.py when `explanation_facts - scoring_reachable_facts` is non-empty. |
| **CDS filtered**                   | When `--cds-gate`: total chunks removed by CDS admissibility.                                                                                                    | Filtering impact.                                                             |                                                                                                             |
| **CDS refusals**                   | When `--cds-gate`: count of queries where candidate set became empty.                                                                                            | Safety.                                                                       |                                                                                                             |

---

## Relation sets (reference)

- **RELATION_WHITELIST:** semantic + structural relations used in full traversal adjacency.
- **STRUCTURAL_RELATIONS:** next, contains, has_fact, in_same_chunk, mentions_same_entity, describes, etc.
- **ENTITY_SEMANTIC_RELATIONS:** requires, modifies, triggers, contrasts_with, overridden_by, etc. (entity–entity “reasoning” edges).
- **SEMANTIC_FACT_RELATIONS:** applies_to_role, requires_level, same_subject, triggers, unless, modifies_parameter, etc. (fact–fact or fact–procedure).
- **NEGATION_FACT_TYPES:** prevents, requires, triggers, unless (used for justified negation).

---

## Recommended use for the user story

**User story:** Pipeline that ingests TTRPG rulebook text → traceable, replayable graph → RAG hybrid search → generic TTRPG questions → true rule algorithms.

- **Primary (retrieval):** Gold chunks found, Recall, Recall@5, Recall@10, gold_hit rate. These directly measure “did we retrieve the right evidence?”
- **Secondary (structural sanity):** CCR (and CCR'). Use as a sanity check; do not treat as ground truth for rule correctness.
- **Monitor:** Minimality rate, entity_semantic_purity (when using entity-only). Report but do not optimize solely on these until correlated with answer quality.
- **Not yet measured:** Rule-correctness or downstream “true rule algorithms”; add when rule-engine or QA benchmarks exist.

---

## Verification and validation

**Gold set:** Gold chunks are human-curated; they may be incomplete or batch-specific. Before trusting recall as the primary signal, spot-check 2–3 queries per batch: confirm that `gold_chunk_ids` in the batch JSON are indeed the correct evidence chunks for the question (e.g. by opening the source PDF at the chunk’s page/section).

**CCR (causal coverage):** Measures graph connectivity of selected facts (“supported” via SEMANTIC_FACT_RELATIONS), not correctness of rule logic. The 0.9 failure threshold is arbitrary and unvalidated against ground-truth rule correctness. Treat CCR as a structural sanity check and tuning knob, not as a rule-correctness metric.

**Minimality:** Bounds (5/8 facts, 3 frames) are heuristic and not derived from user study or answer quality. Report minimality rate but do not treat as a primary target until we have evidence that these bounds correlate with answer quality.

**Correlation analysis:** The script (when `--save-query-metrics` is used and multiple queries run) prints Pearson correlations: entity_semantic_purity vs causal_coverage, entity_compactness vs gold_hit, assertion_load vs entity_semantic_purity. Expected patterns (entity-only mode): purity vs coverage positive; compactness vs gold_hit negative. Record these in the benchmark report and flag if expected correlations do not hold.
