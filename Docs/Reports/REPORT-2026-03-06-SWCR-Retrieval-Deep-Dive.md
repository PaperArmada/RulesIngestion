# REPORT-2026-03-06-SWCR Retrieval Deep Dive

Scope: explain why chunks the manual SWCR benchmark treats as important are not consistently entering retrieved context in the current `swords_wizardry_autogold_manual_compare_20260306` pipeline, and rank the remaining levers that actually address that failure.

## Top-Line Conclusion

The main reason manual-important chunks are missing from retrieved context is not one thing.

The deepest problem is **benchmark/corpus drift**:

- The run was executed against a specific embedded corpus (`run_id = retrieval_lab_Swords&Wizardry_v3_swcr_merged2000_min100_recipe_standardized`).
- The current manual benchmark file now contains `gold_locations` that only partially overlap that run corpus.
- When I checked the run's own `corpus_index.json`, only `12 / 55` manual `gold_locations` IDs still existed in the run corpus, and `12 / 21` queries had **zero** surviving manual gold IDs.

That means many "manual better" disagreements are not pure retrieval misses. In a large share of cases, the manual benchmark is pointing at anchors that are no longer present as the same chunk IDs in the evaluated corpus.

After that drift problem, there is a smaller but real second problem: **the hybrid head is suppressing some lexically relevant anchors that BM25 can see but dense retrieval does not value highly enough**. The clearest surviving examples are:

- `sw_rev_s05_combat_sequence_group_initiative`
- `sw_rev_u03_time_progression_model`
- `sw_rev_u04_player_actions_in_combat`

There is also a third class: **broad or inferential questions that do not have stable minimal anchors**, especially:

- `sw_rev_u05_what_must_be_tracked`
- `sw_rev_s02_treasure_division_procedure`

So the answer to "why aren't we putting the manual-important chunks into retrieved context?" is:

1. In many cases, the benchmark's chunk IDs do not line up with the run corpus anymore.
2. In a smaller set of real misses, dense-led hybrid ranking is favoring semantically nearby prose over the exact procedural/table anchor.
3. In a few cases, the question itself is too broad or inferential for a stable minimal-anchor benchmark.

## A Critical Diagnostic Caveat

The run's top-level `REPORT.md` is not a reliable source for this exact question, because the experiment applied auto-gold review and then rescored against the rewritten benchmark.

That is why the run report says:

- `Failure counts: {"hit": 21}`
- `Failure buckets: {"success": 21}`

Those numbers are true for the **post-auto-review benchmark**, but they do not tell us whether the original manual benchmark's important chunks were surfaced. For this deep dive, the useful artifacts are:

- `retrieved_chunks.json`
- `manual_vs_auto_comparison.json`
- the manual benchmark itself
- the run's `corpus_index.json`

## 1. What The Current Architecture Actually Does

### 1.1 Chunk boundaries are created in Stage B

The real boundaries come from `extraction/stage_b.py`:

- each leaf AST node becomes one EvidenceUnit,
- headings are absorbed into child text,
- tables are never split,
- consecutive paragraphs remain separate units.

This means the corpus starts life as fairly atomic page-local units, not semantic answer bundles.

### 1.2 Several later steps can rewrite IDs

There are three different ID-changing mechanisms in the current stack:

1. **TOC binding** rewrites `structural_path` and recomputes `unit_id`.
2. **Fold-under-threshold** creates synthetic combined IDs from merged source IDs.
3. **Heading merge** creates new synthetic merged IDs from grouped source IDs.

So even before retrieval quality is discussed, chunk identity can drift as corpus shaping changes.

### 1.3 Cross-page join exists, but the current loader does not build the experiment corpus from a joined artifact

`cross_page_join.py` can merge split paragraphs, tables, and lists across page boundaries. But `retrieval_lab/substrate_loader.py` loads `stageB.evidence_units.json`, then applies fold/merge at retrieval time. The evaluated experiment corpus is therefore shaped from the Stage B page artifacts plus retrieval-time fold/merge, not from a separately materialized joined-corpus artifact.

### 1.4 The evaluated SWCR run used a merged retrieval corpus

From the run report:

- substrate version: `v3_swcr_merged2000_min100`
- corpus units: `2994`
- retrieval mode: `hybrid`

So this is not a raw atomic-only run. The evaluated corpus already includes:

- `min_chars = 100`
- heading merge with `merge_max_chars = 2000`

But that still leaves a noisy shaped corpus:

- `short_le_40_rate = 0.307`
- `short_le_80_rate = 0.402`
- `duplicate_text_entry_rate = 0.131`

That background noise does not explain every miss, but it does mean the head still spends budget on small or repetitive units.

## 2. Where Retrieval Can Lose Important Chunks

### 2.1 Candidate admission is deeper than the visible head

The run is not searching only top-20 internally:

- `dense_budget = 100`
- `bm25_budget = 100`
- final evaluation/report head = top 20
- auto-gold review candidate window = top 20

So a chunk can be:

- in the broader dense or BM25 candidate pool,
- but still absent from the visible top-20 head,
- and therefore invisible to auto-gold review as a candidate explanation.

### 2.2 `expand_context` is not a recall rescue

`expand_context` only re-embeds and reranks already admitted center chunks. It does not fetch new chunks from elsewhere in the corpus.

So if the right chunk never enters the top head in the first place, `expand_context` cannot save it.

### 2.3 Structural expansions happen too late to fix head recall

The code supports:

- crossref sidecar expansion,
- co-retrieval expansion,
- dependency pairing expansion,
- parent fetch.

But these are post-retrieval append/enrichment behaviors. They help context assembly or add low-scored neighbors after the main ranking decision. They are not a substitute for admitting the correct anchor high enough.

### 2.4 This run was effectively dense-led

The run report's hybrid contribution snapshot shows:

- dense-only gold hits: `2`
- BM25-only gold hits: `0`

That means BM25 was not improving the official post-review gold metrics for this run. In practice, the hybrid behaves like dense-led ranking with BM25 assistance that is usually too weak to change the head.

## 3. Failure Taxonomy

### 3.1 Primary taxonomy for the problematic queries

These are the queries that remained `manual better` or `needs adjudication` in the full-benchmark audit.

| query_id | primary failure mode | why |
|---|---|---|
| `sw_rev_u03_time_progression_model` | `partial drift + real head miss` | Some manual anchors survive into the run corpus, but the retrieved head prefers time-unit prose and a mass-combat round rule over the fuller standard combat-sequence anchor the benchmark answer expects. |
| `sw_rev_u04_player_actions_in_combat` | `partial drift + selector incompleteness` | One manual gold anchor survives into the run corpus, but none of the surviving manual anchors enter top-20. The retrieved head favors alternate-method combat text rather than the benchmark's fuller standard-method constraints. |
| `sw_rev_u05_what_must_be_tracked` | `benchmark question too broad` | Zero manual gold IDs survive into the run corpus, and the question spans sheet data, resources, clocks, position, and play procedure. There is no stable minimal anchor set. |
| `sw_rev_s02_treasure_division_procedure` | `benchmark question too inferential` | Zero manual gold IDs survive into the run corpus, and the answer itself is an inference from the absence of an explicit rule plus referee adjudication philosophy. |
| `sw_rev_s05_combat_sequence_group_initiative` | `mixed drift + real head miss` | Only `1 / 6` manual gold IDs survives into the run corpus, and that surviving `DECLARE SPELLS` anchor still does not enter top-20. The head over-focuses initiative and alternate combat methods. |
| `sw_rev_s08_first_level_cleric_spells` | `table-shape / corpus-drift mix` | `0 / 2` manual gold IDs survive into the run corpus. The retrieved head gets nearby cleric prose, but not the decisive advancement-table anchor the benchmark answer really wants. |
| `sw_rev_s12_morale_and_reaction_rolls` | `drift + selector incompleteness` | `0 / 3` manual gold IDs survive into the run corpus. The head retrieves morale text and nearby diplomacy prose, but not a stable answer-bearing reaction-roll anchor. |

### 3.2 What is not a primary failure mode here

The evidence does **not** support the claim that the whole SWCR stack is broadly failing to retrieve manual-important evidence.

Instead:

- many allegedly "missing" manual chunks are not in the run corpus anymore as the same IDs,
- many auto-better cases are really benchmark minimality disagreements,
- only a narrow subset look like true head-recall failures.

## 4. Exemplar Traces

### 4.1 `sw_rev_s05_combat_sequence_group_initiative`

**What the benchmark answer needs**

- surprise check,
- spell declaration,
- initiative,
- movement/missiles,
- melee/spells,
- repeat sequence.

**What the run retrieved at the head**

The head is initiative-heavy:

- `3. ROLL INITIATIVE`
- alternate combat sequence methods
- mass-combat order-of-battle
- movement/missiles phase
- initiative/order-of-battle prose

**What is missing**

The surviving manual `2. DECLARE SPELLS` gold anchor is not in top-20, and the full `INITIATIVE AND ORDER OF BATTLE` / `SURPRISE` manual anchors do not even exist as matching IDs in the run corpus.

**Diagnosis**

This is the clearest mixed case:

- benchmark/corpus drift is real (`1 / 6` manual gold IDs survive),
- but there is also a real head miss, because the one surviving procedural anchor still does not surface.

This is the best evidence that multi-part procedure questions are under-served by the current dense-led hybrid head.

### 4.2 `sw_rev_u03_time_progression_model`

**What the benchmark answer needs**

- 10-minute turns,
- ordinary combat rounds,
- the repeating combat sequence that advances one round to the next,
- the mass-combat exception.

**What the run retrieved at the head**

The head mostly contains:

- `TIME`
- general play/how-to-play prose
- mass-combat round rules
- movement timing text
- alternate combat timing text

**What is missing**

Only `2 / 5` manual gold IDs survive into the run corpus. One surviving anchor hits at rank 4 (`INITIATIVE AND COMBAT ROUNDS` on the Referee Guide mass-combat page), but the standard sequence anchor the benchmark wants is not in the head.

**Diagnosis**

This is not a total retrieval failure. It is a **focus failure**:

- the query wording pulls the model toward abstract time-unit definitions,
- the benchmark answer expects a fuller procedural model,
- the head therefore under-surfaces the ordinary round sequence.

### 4.3 `sw_rev_s12_morale_and_reaction_rolls`

**What the benchmark answer needs**

- morale trigger timing,
- morale die/result handling,
- reaction-roll die and interpretation bands.

**What the run retrieved at the head**

The head captures morale reasonably well:

- `Optional Morale Rules`
- `How it works` morale text

But for the reaction side it retrieves:

- `NEGOTIATION AND DIPLOMACY`
- other semantically nearby combat material

**What is missing**

None of the manual gold IDs survive into the run corpus index (`0 / 3`), so this cannot be called a clean rank miss by ID evidence alone.

**Diagnosis**

This is primarily a drift problem, with a secondary selector problem:

- the benchmark's exact reaction anchor is not stable against the evaluated corpus,
- the retriever gets nearby negotiation context rather than a decisive reaction-roll procedure chunk.

If this query is kept, it needs fresh re-anchoring against the exact run corpus.

### 4.4 `sw_rev_s08_first_level_cleric_spells`

**What the benchmark answer needs**

The real answer is: clerics do not get 1st-level spells at level 1; the advancement table is the decisive evidence.

**What the run retrieved at the head**

The head contains:

- `CLERIC CLASS ABILITIES`
- unrelated spell mentions,
- general divine-magic prose,
- a page-11 cleric chunk,

but not a clearly decisive advancement-table anchor.

**What is missing**

None of the manual gold IDs survive into the run corpus (`0 / 2`).

**Diagnosis**

This is a combined table-shape and drift case:

- the benchmark's table anchors are not stable against the run corpus,
- the retriever falls back to nearby cleric prose,
- the question's decisive evidence lives in a table-like unit that is not becoming the head anchor.

This is one of the best arguments for table-specific retrieval handling.

### 4.5 `sw_rev_s02_treasure_division_procedure`

**What the benchmark answer needs**

The benchmark answer is effectively: there is no explicit formal treasure-division procedure; this is left to adjudication.

**What the run retrieved at the head**

The head contains treasure-generation rules, class charity obligations, and castle toll demands.

**What is missing**

There is no clean, explicit "treasure division procedure" rule chunk, and none of the manual gold IDs survive into the run corpus (`0 / 3`).

**Diagnosis**

This is not a good stable retrieval benchmark question in its current form. It is inferential and absence-based. The current retriever is not wrong to retrieve nearby treasure rules, because there may be no single answer-bearing anchor to retrieve.

### 4.6 `sw_rev_u05_what_must_be_tracked`

**What the benchmark answer needs**

A very broad bundle:

- sheet statistics,
- equipment,
- hit points,
- spells/resources,
- time,
- position / exploration state,
- other play-state bookkeeping.

**What the run retrieved at the head**

The head strongly favors:

- character sheet setup,
- getting started,
- generic play procedure,
- some mechanical reference text.

**What is missing**

None of the manual gold IDs survive into the run corpus (`0 / 2`), and the question itself asks for a cross-document bookkeeping ontology rather than a single rule.

**Diagnosis**

This is benchmark design, not primarily retrieval. The retriever is doing the natural thing: finding character-sheet and bookkeeping-adjacent text. The benchmark is asking a broad synthesis question that does not map cleanly onto stable chunk anchors.

## 5. What The Evidence Says Overall

### 5.1 Manual-important chunks are often missing because the benchmark no longer matches the run corpus

This is the strongest quantified finding:

- manual gold IDs present in run corpus: `12 / 55`
- queries with zero surviving manual gold IDs: `12 / 21`

That means many disagreements are upstream of retrieval.

### 5.2 Among the surviving anchors, only a few look like true head misses

When restricted to queries where at least one manual gold ID still exists in the run corpus:

- `sw_rev_u04_player_actions_in_combat`: surviving anchors exist, but none hit top-20
- `sw_rev_s05_combat_sequence_group_initiative`: surviving anchor exists, but none hit top-20
- `sw_rev_u03_time_progression_model`: partial hit, but incomplete head coverage

That is a much narrower problem than "the system usually fails to surface manual-important chunks."

### 5.3 The current run configuration makes this worse for procedural anchors

The current setup is:

- hybrid retrieval,
- dense-led CC fusion,
- no two-stage retrieval,
- no raw-first merge-rerank,
- no clause-family projection,
- no crossref/co-retrieval/pairing rescue for head recall,
- auto-gold review limited to top-20.

That combination is particularly bad for:

- multi-step procedure chunks,
- table-driven answers,
- semantically specific but lexically obvious anchors,
- benchmark questions whose answer is spread across two or three nearby chunks.

## 6. Ranked Remaining Levers

These are ordered by expected value for the specific question: "why didn't the relevant chunk enter retrieved context?"

### 1. Lock the evaluation contract and stop using a post-review-rescored report as the diagnostic surface

**Why this is first**

Right now the experiment rewrites benchmark gold via auto-gold review and then rescoring makes the run look like `21/21` hits. That hides the very failure you are trying to diagnose.

**What to do**

- freeze benchmark path + hash,
- freeze corpus fingerprint + run_id,
- persist a run-local resolved-gold artifact,
- compare manual benchmark against that exact run corpus before any auto-review rewrite.

**What it fixes**

- separates real retrieval misses from benchmark/corpus drift,
- makes future SWCR debugging trustworthy,
- prevents "all success" report artifacts from masking manual disagreements.

### 2. Re-anchor SWCR manual gold to the exact evaluated run corpus

**Why this is second**

With only `12 / 55` manual gold IDs surviving into the run corpus, retrieval tuning alone cannot answer the question cleanly.

**What to do**

- rebuild `gold_locations` against the exact run corpus index,
- store the corpus fingerprint alongside the benchmark,
- fail loudly when a benchmark is used against a non-matching corpus.

**What it fixes**

- benchmark/corpus drift,
- false misses caused by dead IDs,
- ambiguity about whether the "important chunk" even exists as a candidate.

### 3. Add a retrieval mode that protects BM25-visible procedural anchors from dense suppression

**Why this is third**

The surviving head misses are mostly procedural or exact-anchor cases. The current dense-led CC hybrid is too willing to demote them.

**What to try**

- a BM25-preserving hybrid mode for multi-part procedure questions,
- query-class-conditioned fusion,
- or a constrained union policy where strong BM25 procedural anchors cannot be entirely erased from the visible head.

**What it fixes**

- `s05`-style initiative/sequence misses,
- `u03`-style time-progression procedure misses,
- likely some reaction-roll style lexical anchors when dense goes semantic and broad.

### 4. Use two-stage retrieval or raw-first merge-rerank for sequence/table questions

**Why this is fourth**

Some answers live in a larger local bundle, but the head retrieves only one sub-piece or nearby prose.

**What to try**

- stage 1: broader admission using question-plus-summary or lexical-heavy retrieval,
- stage 2: rerank merged candidates or raw-to-merged promoted candidates,
- especially for combat sequence and class table questions.

**What it fixes**

- partial-head misses where the right family enters the pool but not the right consolidated chunk,
- procedure bundles that need both a local anchor and its adjoining context.

### 5. Improve table retrieval and table text shaping

**Why this is fifth**

`sw_rev_s08_first_level_cleric_spells` is the clearest example where the decisive evidence is table-shaped.

**What to try**

- stronger table-title propagation,
- row/column verbalization for embeddings,
- table-aware BM25 text,
- table-specific rerank features.

**What it fixes**

- advancement-table questions,
- turn-undead/table-symbol questions,
- other answers whose real anchor is not ordinary prose.

### 6. Decompose overly broad questions before retrieval

**Why this is sixth**

Some questions are not stable as one-shot retrieval prompts.

**What to try**

- split multi-part questions into subqueries,
- retrieve per subquery,
- union and rerank,
- then evaluate against a benchmark that recognizes multi-anchor answers.

**What it fixes**

- `u05` broad bookkeeping questions,
- `s12` multi-part morale + reaction questions,
- `u04` bundled combat-action questions.

### 7. Treat `expand_context`, parent-fetch, and sidecar expansion as precision tools, not recall tools

**Why this is last**

These are still useful, but they do not solve the main failure here.

**What they fix**

- answerability once the correct center chunk is already in the head,
- local context completeness,
- presentation quality.

**What they do not fix**

- missing anchor admission,
- benchmark/corpus drift,
- table/procedure anchor suppression at ranking time.

## Final Answer To The Core Question

If the question is strictly:

> Why aren't we putting the chunks that manual thinks are important into the retrieved context?

The answer is:

1. **Often because the manual benchmark is pointing at chunk IDs that are not in the evaluated run corpus anymore.**
2. **Sometimes because the current hybrid head suppresses procedure-heavy lexical anchors that dense retrieval does not strongly favor.**
3. **Sometimes because the benchmark question is too broad, inferential, or table-shaped for a stable minimal anchor set.**

So the next best move is not "blindly tune retrieval harder." It is:

1. lock the corpus/benchmark contract,
2. re-anchor manual gold to the exact run corpus,
3. then target the much smaller set of true head-miss queries with hybrid/admission changes.
