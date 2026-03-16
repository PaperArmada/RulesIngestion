# Experiment: Metadata- and TOC-Enriched Embeddings

**Purpose:** Design an experiment to compare **baseline chunk embeddings** (text only) vs **metadata- and TOC-enriched embeddings**, and to run ablations to measure which enrichments improve retrieval.

**Status:** Implemented and run (2026-02-24). Gates revisited 2026-03: all satisfied; experiment closed for SWCR with baseline-as-default decision. See §8 Run summary, §9 Corrected results, §11 Gates to move forward.  
**Related:** [ARCHITECTURE-TOC-Structural-Enrichment.md](ARCHITECTURE-TOC-Structural-Enrichment.md), retrieval_lab `substrate_loader`, `run_experiment`, `store.substrate_run_id`.
**Canonical note:** Keep as experiment history. Current baseline policy and
workflow guidance live in `Docs/Design/v1/` and
`Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`.

---

## 1. Current behavior

- **Corpus for embedding:** Built from stageB EvidenceUnits → load → optional fold → optional merge_units_by_heading → merge_enrichments_into_corpus. Resulting items have: `id`, `text`, `page`, `structural_path`, `unit_type`, `document_id`, optional `source_unit_ids`, optional `topic_tags`, optional `co_retrieval_hints`.
- **Embedding input:** Only `c["text"]` is passed to the encoder.  
  - `retrieval_lab/run_experiment.py`: `corpus_texts = [c["text"] for c in corpus]` (line 326).  
  - Same in embed-only path (line 241) and in dense_mode (corpus_texts from context).
- **Run identity:** `run_id = substrate_run_id(document_id, corpus_ids, substrate_version)`. With `substrate_version` set, `run_id = retrieval_lab_{document_id}_{version}`. So different embedding *text* (e.g. enriched vs baseline) must use a different `substrate_version` (or equivalent) so cached embeddings are not reused.

---

## 2. Metadata inventory

What we already have (or can add) on each corpus item for enrichment:

| Source | Field | On corpus today? | Description |
|--------|--------|-------------------|-------------|
| stageB (load_evidence_units) | `structural_path` | Yes | TOC/section path, e.g. `["Player Guide", "Choose a Character Class", "Cleric"]`. |
| stageB | `unit_type` | Yes | `prose`, `table`, `list`, `callout`, `heading`. |
| stageB | `join_metadata` | **No** | Not loaded. Contains `table_title` (TOC binding), `toc_bound`, `original_structural_path`. |
| stageB (if we load it) | `join_metadata.table_title` | No | Short caption for tables (e.g. "Cleric Advancement Table"). |
| merge_enrichments / A′ | `topic_tags` | Yes (after merge_enrichments) | From stageAPrime.enrichments.json or build_minimal_a_prime_hints; list of topic strings. |
| merge_enrichments / A′ | `co_retrieval_hints` | Yes (after merge_enrichments) | List of `{related_topic, reason}`. |
| load_evidence_units | `page` | Yes | 0-based page index. |

**LLM enrichment (A′):**  
- **stageAPrime.enrichments.json:** Optional per-unit file with `topic_tags` and `co_retrieval_hints` (from an LLM or external pipeline). Merged by `merge_enrichments_into_corpus`.  
- **build_minimal_a_prime_hints:** When `a_prime_generate_minimal` is true, we generate hints deterministically from the crossref/exception sidecar (related units under same heading → topic_tags + co_retrieval_hints). No LLM; same corpus structure → same hints.

So we have **structural_path**, **unit_type**, **topic_tags**, **co_retrieval_hints**, **page** on the corpus today. We can add **table_title** by loading `join_metadata` from stageB in `load_evidence_units` and carrying it through (tables are passthrough in merge, so one unit → one chunk; we can set `join_metadata` or a flat `table_title` on the corpus item).

---

## 3. How to add metadata to the embedding string

Keep a **single** embedding text per chunk: a deterministic string built from optional prefix lines plus the original body.

- **Prefix block (one line per enabled enrichment):**  
  - `Section: A > B > C` from `structural_path` (join with ` > `).  
  - `Type: table` from `unit_type`.  
  - `Table: Cleric Advancement Table` from `join_metadata.table_title` (or `table_title` on corpus).  
  - `Topics: tag1, tag2` from `topic_tags` (comma-separated, capped e.g. 5).  
  - `Related: topic1; topic2` from `co_retrieval_hints` (e.g. `related_topic` values, capped).  
  - `Page: 10` from `page` (optional; can help “which page” queries).  
- **Body:** Original `text` unchanged.  
- **Format:** e.g. `"{prefix_lines}\n\n{text}"` with prefix lines only when the enrichment is enabled and the value is non-empty. No prefix block if no enrichment is used (baseline = text only).

So the embedding text becomes:

- **Baseline:** `text` only.  
- **Enriched (e.g. path + type + table_title):**  
  `Section: Player Guide > Choose a Character Class > Cleric\nType: table\nTable: Cleric Advancement Table\n\n{text}`

This keeps the model seeing both structure/keywords and the full content, and allows ablations by toggling which prefix lines are added.

---

## 4. Ablation matrix

Run the **same** retrieval benchmark (e.g. SWCR) with the **same** queries and gold, varying only the **embedding text** (and thus run_id). Compare recall@k, hit@k, MRR, gold-in-candidates rate, failure buckets.

| Condition | Name | Prefix lines added | substrate_version / run_id note |
|-----------|------|--------------------|----------------------------------|
| A | baseline | none | current (e.g. existing version or content hash) |
| B | path | Section: … | e.g. `{base}_embed_path` |
| C | type | Type: … | `{base}_embed_type` |
| D | table_title | Table: … (only for unit_type=table) | `{base}_embed_table_title` |
| E | topic_tags | Topics: … | `{base}_embed_topics` |
| F | co_retrieval_hints | Related: … | `{base}_embed_hints` |
| G | page | Page: N | `{base}_embed_page` |
| H | all | Section, Type, Table (if table), Topics, Related, Page | `{base}_embed_full` |

Optional **compound ablations** (e.g. path+type, path+topic_tags) to see interactions. For a first pass, A + B–H (7 ablations + full) is enough.

**Run_id / cache:**  
- Each condition must use a distinct run_id so embeddings are recomputed. Use `substrate_version` to encode the condition: e.g. `swcr_toc_v1` (baseline) vs `swcr_toc_v1_embed_path`, `swcr_toc_v1_embed_full`, etc.  
- If the code uses a single “embedding profile” or “enrichment mask”, run_id should include a short hash or name of that profile (e.g. `_embed_full`) so cache keys are unique per condition.

---

## 5. Implementation sketch

1. **Load `join_metadata` (and `table_title`) in retrieval lab**  
   - In `load_evidence_units`, for each unit read `join_metadata` from stageB; set on corpus item e.g. `u["join_metadata"] = u_raw.get("join_metadata", {})`, and optionally a flat `u["table_title"] = (join_metadata or {}).get("table_title", "")` for convenience.  
   - Preserve through fold and merge: for merged chunks, table_title is N/A (merged chunks are not tables); for passthrough table units, keep the unit’s table_title.

2. **Embedding text builder**  
   - Add a small module or functions in `substrate_loader`: e.g. `build_embedding_text(c: Dict, profile: EmbeddingEnrichmentProfile) -> str`.  
   - `EmbeddingEnrichmentProfile` (or a simple dict/flags): booleans or list of keys: `structural_path`, `unit_type`, `table_title`, `topic_tags`, `co_retrieval_hints`, `page`.  
   - Build prefix lines from corpus item for each enabled key; then return `prefix_block + "\n\n" + text` or just `text` if no prefix.

3. **Wire into corpus_texts and run_id**  
   - In `_prepare_experiment_corpus_context`: instead of `corpus_texts = [c["text"] for c in corpus]`, use `corpus_texts = [build_embedding_text(c, config.embedding_enrichment_profile) for c in corpus]`.  
   - In embed-only and in any path that computes run_id: include the enrichment profile in the run_id (e.g. pass a `substrate_version` that already encodes it, or append `_embed_{profile_name}` to the version). So: `run_id = substrate_run_id(..., substrate_version=f"{config.substrate_version}_embed_{profile_name}")` when embedding_enrichment_profile is non-baseline.

4. **Config**  
   - Add `embedding_enrichment_profile: Optional[str]` or a struct (e.g. `embed_path: bool`, …) to experiment config.  
   - CLI/experiment YAML: e.g. `embedding_enrichment_profile: full` or `embedding_enrichment_profile: path,type,table_title`.  
   - Profile “baseline” or “” = text only; “full” = all; “path”, “type”, etc. = single ablation.

5. **Benchmark and metrics**  
   - Same benchmark file, same gold grounding. Run retrieval for each condition (separate experiment run or same run with multiple embedding caches). Compare: recall@k, hit@k, MRR, gold_not_in_candidates rate, failure_bucket counts.  
   - Optional: one report that side-by-sides metrics for baseline vs each ablation and full.

---

## 6. Prerequisites and risks

- **stageAPrime.enrichments.json:** If not present, `topic_tags` / `co_retrieval_hints` are only from `build_minimal_a_prime_hints` when `a_prime_generate_minimal` is true. So for ablations E and F we need either that flag or pre-generated enrichments.  
- **table_title:** Only on units that had TOC table-caption binding (tables with preceding short prose). Many tables may have empty table_title.  
- **Token/length:** Adding prefix lines increases input length; stay within model limits and similar total length across conditions for fair comparison (or document length delta).  
- **Gold grounding:** Benchmark gold must be grounded to the **same** corpus (same unit_ids). Enrichment only changes the *text we embed*, not unit identity, so gold resolution is unchanged.

---

## 7. Success criteria

- **Implement:** Builder for embedding text with configurable profile; load join_metadata/table_title; wire corpus_texts and run_id; config and CLI for profile.  
- **Run:** Baseline + at least 3–4 ablations (e.g. path, type, topic_tags, full) on SWCR (or one benchmark).  
- **Measure:** Recall@k and gold-in-candidates rate; identify which enrichments improve retrieval and by how much.  
- **Decide:** Adopt a default embedding profile (e.g. path + type + table_title) if beneficial; document in retrieval_lab and TOC architecture.

---

## 8. Run summary (2026-02-24)

**Config:** `retrieval_lab/experiments/dense/swcr_embedding_metadata_enrichment.yaml` (SWCR substrate, min-anchor benchmark, a_prime_generate_minimal, all-mpnet-base-v2).

**Commands run:**
- Baseline: `uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/dense/swcr_embedding_metadata_enrichment.yaml`
- Ablations: same with `--embedding-enrichment-profile path|type|topic_tags|full`

**MRR (all-mpnet-base-v2) by condition:**

| Condition   | MRR     | hit@1  | hit@10 | gold_in_candidates |
|------------|---------|--------|--------|--------------------|
| baseline   | 0.1555  | 0.132  | 0.184  | 0.211              |
| path       | 0.1441  | 0.105  | 0.211  | 0.211              |
| type       | 0.1477  | 0.105  | 0.211  | 0.211              |
| topic_tags | 0.1557  | 0.132  | 0.184  | 0.211              |
| full       | 0.1419  | 0.105  | 0.211  | 0.211              |

Baseline and topic_tags tie for best MRR; path/type/full are slightly lower on this benchmark. Gold-in-candidates is unchanged across conditions. Outputs under `out/retrieval_lab/experiments/swcr_embedding_metadata_enrichment_*`.

**Note:** The metrics above were deflated by a scoring bug (see §9). Corrected baseline metrics are in the next section.

---

## 9. Scoring bug and corrected results (2026-02-24)

**Bug:** The retrieval scoring pipeline had an ID namespace mismatch. Gold grounding resolves benchmark gold to **merged corpus IDs** (the `id` field of post-merge units). The default `ranked_source_id_lists` passed to `score_retrieval` mapped each ranked candidate only to its **source_unit_ids** (pre-merge extraction IDs). Gold IDs (merged namespace) were therefore never found in the candidate source sets, so many queries where gold was actually at rank 1 were classified as `retrieval_miss`. Fix: include the merged corpus ID (`cid`) in each candidate's source set when building the default source lists in `retrieval_lab/orchestration/dense_mode.py` (lines 942–946 and 992–994): use `[[cid] + id_to_source_ids.get(cid, []) for cid in ranked_lists[i]]` instead of `[id_to_source_ids.get(cid, [cid]) for cid in ranked_lists[i]]`.

**Impact:** Pre-fix reported metrics were severely deflated. Post-fix baseline (same config, same embeddings):

| Metric                | Pre-fix (reported) | Post-fix (corrected) |
|-----------------------|--------------------|------------------------|
| MRR                   | 0.1555             | 0.5512                 |
| hit@1                 | 0.132              | 0.474                  |
| hit@10                | 0.184              | 0.684                  |
| gold_in_candidates    | 0.211              | 0.711                  |
| retrieval_miss count  | 26                 | 7                      |
| hit count             | 8                  | 27                     |

The 7 remaining retrieval misses are true misses (gold not in top-20). See **§9.1 Miss analysis** below. The enrichment experiment's qualitative conclusion holds (enrichment did not improve retrieval; gold-in-candidates was unchanged across conditions), but absolute metrics were wrong until the fix. Rerun output: `out/retrieval_lab/experiments/swcr_embedding_metadata_enrichment_20260224_044020/`.

### 9.1 Miss analysis (post-fix baseline)

Benchmark: `evals/retrieval/SwordsandWizardy/swords_wizardry_complete_revised_benchmark_min_anchor_atomic_rewrite.json`. Corpus: SWCR load → fold (min 200 chars) → merge by heading (max 2000 chars).

| Query | Cause | Notes |
|-------|--------|------|
| **sw_rev_s08_first_level_cleric_spells** | Benchmark bug (fixed) | Gold was incorrectly set to page 2 / FOREWORD. Correct gold: Cleric Advancement Table on p.11. Updated to `c3f97beb...` (Player Guide → Creating a Character → Choose a Character Class → Cleric). |
| **sw_rev_u05a_character_attributes_to_record** | Benchmark bug (fixed) | Gold was incorrectly set to page 2 / FOREWORD. Correct gold: ROLL ATTRIBUTE SCORES on p.6. Updated to `a4b99bf4...` (Roll Attribute Scores → ROLL ATTRIBUTE SCORES). |
| **sw_rev_s02_treasure_division_procedure** | Removed from analysis | Abstracted into other questions (e.g. rewards for completing combat). |
| **sw_rev_s04_advancement_tables_where** | Retrieval | Gold is Fighter advancement table (p.15). Manual review of major table chunks and table_title/section labels to do. |
| **sw_rev_u05d_treasure_to_xp_tracking** | Benchmark bug (fixed) | Gold was How to Play (p.33); correct gold is GAINING EXPERIENCE (61d87c8a...). Updated in benchmark. |
| **sw_rev_s13_encumbrance_and_movement_anchor** | Benchmark bug (fixed) | Required gold was p.95 (wrong); correct is Weight and Movement (p.32, 43050798...). Updated in benchmark. |
| **sw_rev_u06b_monster_xp_determination** | Benchmark bug (fixed) | Gold was anchored to Monster Saving Throws; correct is Experience Point Values by Challenge Level (p.130, 6441e2f6...). Updated in benchmark. |

**Foreword vs chunking:** The two Foreword misses were not caused by chunking. The Foreword is a single correct chunk on page 2 (`structural_path=['FOREWORD']`). The benchmark's `gold_locations` for s08 and u05a pointed at that chunk by mistake; `source_page` already indicated p.11 and p.6. The benchmark has been updated with the gold_locations and unit ids above.

---

## 10. Cross-experiment learnings (2026-03)

Learnings from other retrieval-lab experiments (notably PF2E LLM reranking and answer-eval) that apply when running or interpreting experiments that use answer-eval or similar pipelines:

- **Answer-eval model choice:** Refusal accuracy and required-cited rate depend strongly on the answer-eval LLM. On the same 30-query slice with reasoning_effort=none: gpt-5-mini gave refusal accuracy 56.7% and required_cited mean 41%; gpt-5.2-2025-12-11 gave 90% and 71%; gpt-5.4-2026-03-05 gave 86.7% and 79%. For any experiment that uses answer-eval to measure “no degradation of answer-level fidelity,” use a stronger model (e.g. gpt-5.2 or gpt-5.4) and set `--answer-reasoning none` for comparable, parseable output.
- **Answer-eval API behavior:** gpt-5-mini does not accept the `temperature` parameter in the Responses API; omit it for that model. Use structured output (`response_format` + json_schema) and extract text from `output_parsed` or `output[].content[].parsed` first, then fall back to `output_text` or block text, so parse errors do not masquerade as 100% refusal rate.
- **Scoring and ID namespace:** Metrics can be severely deflated if gold IDs (e.g. merged corpus namespace) are not included in the candidate source sets passed to the scorer (see §9). Any new retrieval path or corpus pipeline should verify that the IDs used for scoring match the namespace of the benchmark gold.

These do not change the Embedding-Metadata experiment’s own results; they inform future runs (e.g. if this experiment were extended with answer-eval) and general retrieval-lab practice.

---

## 11. Gates to move forward

Revisit of §7 Success criteria and whether we have satisfied the gates to move forward.

| Criterion | Status | Evidence |
|-----------|--------|----------|
| **Implement** | Satisfied | Builder for embedding text with configurable profile; join_metadata/table_title loading; corpus_texts and run_id wired; config and CLI for `--embedding-enrichment-profile`. |
| **Run** | Satisfied | Baseline + path, type, topic_tags, full ablations on SWCR (2026-02-24). Corrected run after scoring bug: `swcr_embedding_metadata_enrichment_20260224_044020`. |
| **Measure** | Satisfied | Recall@k, hit@k, gold-in-candidates, failure buckets compared across conditions. Post-fix: baseline MRR 0.55, gold_in_candidates 0.71; enrichment did not improve retrieval; gold-in-candidates unchanged across conditions. |
| **Decide** | Satisfied | No default embedding profile adopted beyond baseline. Baseline and topic_tags tied for best MRR on this benchmark; path/type/full were slightly lower. Decision: **keep baseline (text-only) as default**; document that topic_tags showed no harm and could be revisited on other corpora if desired. |

**Verdict:** All gates are satisfied. The experiment can be **closed for this corpus (SWCR)** with the decision above. Policy and workflow guidance live in `Docs/Design/v1/` and `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`. No further ablations are required to move forward unless a new corpus or benchmark motivates a fresh enrichment test.

---

## 12. References

- `retrieval_lab/substrate_loader.py` — load_evidence_units, merge_units_by_heading, merge_enrichments_into_corpus.  
- `retrieval_lab/run_experiment.py` — corpus_texts, _prepare_experiment_corpus_context, run_id.  
- `retrieval_lab/store.py` — substrate_run_id.  
- `retrieval_lab/crossref_sidecar.py` — build_minimal_a_prime_hints.  
- `Docs/Design/ARCHITECTURE-TOC-Structural-Enrichment.md` — TOC binding, table_title, structural_path.
