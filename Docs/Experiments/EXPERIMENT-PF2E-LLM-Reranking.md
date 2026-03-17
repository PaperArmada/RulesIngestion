# Experiment: PF2E LLM Reranking

**Purpose:** Define a discussion-first reranking experiment for Pathfinder 2e multihop retrieval that fits the current Retrieval Lab architecture and can be debated before execution.

**Status:** R0 and R2 (with baseline) executed 2026-03-16; R1 not yet run.  
**Related:** `bounded_multihop_retrieval_design_memo.md`, `pf2e_multihop_benchmark_design.md`, `retrieval_lab/orchestration/dense_mode.py`, `retrieval_lab/experiments/hybrid/pf2e_mpnet_hybrid_baseline.yaml`, `retrieval_lab/experiments/hybrid/pf2e_multihop_r2_llm_listwise.yaml`, `retrieval_lab/experiments/hybrid/pf2e_multihop_r0_baseline.yaml`.

**Canonical tooling reference:** `Docs/Design/ARCHITECTURE-RERANKING-TOOLING.md` (LLM rerank pipeline, CLI/config, baseline delta semantics, sweep findings, and answer-eval model comparison).

---

## Experiment status (as of 2026-03-16)

| Rung | Description | Config | Status |
|------|-------------|--------|--------|
| **R0** | Baseline: hybrid CC, no rerank | `pf2e_multihop_r0_baseline.yaml` (same substrate + both batches, `llm_rerank_enabled: false`, auto_gold off) | **Executed** — `pf2e_multihop_r0_baseline_20260316_131844`; clean_subset MRR=0.854, ReqFSH@10=0.96, 1 retrieval_miss |
| **R1** | Non-LLM rerank control (e.g. cross-encoder) over same hybrid pool | TBD (existing rerank path) | **Not run** — needed to separate "any rerank" from "LLM rerank" |
| **R2** | LLM listwise rerank over fixed hybrid pool, with baseline comparison | `pf2e_multihop_r2_llm_listwise.yaml` + `--baseline-metrics out/retrieval_lab/experiments/pf2e_multihop_r0_baseline_20260316_131844` + `--answer-eval` | **Executed** — `pf2e_multihop_r2_llm_listwise_20260316_131917`; clean_subset MRR=1.0, ReqFSH@10=1.0; outcome_classification=**coverage_gain**; failure-bucket delta vs baseline: gold_not_in_candidates −1 |
| **R3** | Optional LLM pairwise | Deferred | Not started |

**Surfaces:** The plan calls for separate reporting on *Surface A* (`pf2e_multihop_e2e_working_set`) and *Surface B* (`pf2e_multihop_microbundle_working_set`). Currently we have a single benchmark file `pathfinder2e_player_core_multihop_working_set_benchmark.json` (20 queries); reports emit `full_working_set` and `clean_subset` (50q). E2e vs micro-bundle can be interpreted via tiers or a future slice—no separate micro-bundle benchmark file yet.

**Regression guard:** Both R0 and R2 were run on the same two batches (multihop working set + 50q). Clean_subset (50 queries) is the promotion surface; full_working_set (70 queries) also reported. T1 regression check: compare R0 vs R2 on the same surface; R2 improved ReqFSH@10 and rescued the single baseline retrieval_miss.

**Answer-eval:** R2 run included `--answer-eval --answer-model gpt-5-mini --answer-max-queries 30`. Output: `answer_eval.json`; refusal_rate=1.0 (parse_error) so citation/coverage deltas are not yet meaningful — see **Answer-eval parse errors** below.

**Next steps:** (1) Optionally run R1 with cross-encoder/dense rerank for "any rerank" vs "LLM rerank" separation; (2) fix answer-eval parse path so answer-level fidelity can be compared baseline vs R2; (3) document or add micro-bundle slice if needed for Surface B.

---

### Answer-eval parse errors (why “no degradation of answer-level fidelity” is not yet measurable)

The memo says a reranker may only be promoted if it does **not** degrade **answer-level fidelity** on the selected surface. To measure that, we need the **answer-eval** stage: it takes the top-k retrieved chunks, calls an LLM to generate an answer and citations from that evidence, then scores things like “required evidence cited” and “invalid citations.”

We use **gpt-5-mini** for answer-eval (not gpt-4o-mini). The harness expects the model to return **strict JSON**: `{"answer": "...", "citations": ["id1", "id2"], "refusal": false, "uncertainty": ""}`. The parser lives in `retrieval_lab/answer_eval/schema.py`: `parse_answer_response(raw_text)`. If the response is not valid JSON or not a dict with the right shape, it catches the exception and returns a **synthetic** result: `refusal=True`, `uncertainty="parse_error"`, empty answer and citations.

In R2, **every** of the 30 answer-eval queries ended up with that synthetic result: `refusal: true`, `uncertainty: "parse_error"`. So either the model returned non-JSON (e.g. markdown-wrapped or extra prose), or JSON that didn’t match the expected structure. The harness then reports refusal_rate=1.0 and required_cited_rate_mean=0.0 — which reflects **parse failure**, not true refusals or bad citations.

**Implication:** We have no real answer or citation data from that run. We therefore **cannot** yet say “R2 did not degrade answer-level fidelity” in the memo’s sense. To get there we need to **fix the answer-eval path** so that the model output is parseable (e.g. ensure gpt-5-mini is used with a compatible Responses API call and response format, or relax parsing and log raw responses to see what’s coming back). Once parsing succeeds, we can compare baseline vs R2 on required_cited_rate and invalid_citation_rate and apply the memo’s bar.

---

## 1. Why this is the next lever

The current PF2E dual-surface benchmark gives a specific signal:

- the end-to-end parent slice shows `gold_in_candidates = 1.0` under both dense and hybrid baselines, but `ReqFSH@10 = 0.0`
- the micro-bundle slice shows partial success, with several child obligations already retrievable inside top 10
- hybrid improves some rank-sensitive behavior, but it does not yet assemble the full evidence chain in the top-10 budget
- at least one micro-bundle remains a true retrieval miss, so reranking is not expected to solve every failure class

This is the exact profile where reranking should be tested next:

- candidate-generation is not the only problem
- some gold is already in the pool
- the main unresolved question is whether better ordering can move the required set into the top 10 often enough to matter

The reranking experiment should therefore be framed as a **ranking-depth intervention**, not as a retrieval replacement.

---

## 2. Hypothesis

### Primary hypothesis

An LLM reranker operating on a fixed hybrid candidate pool will improve:

- `ReqFSH@10` on `pf2e_multihop_e2e_working_set`
- `rank_of_last_required_mean` on the same surface
- micro-bundle pass rate on `pf2e_multihop_microbundle_working_set`

without materially degrading first-hit precision on precision-sensitive slices.

### Secondary hypothesis

The biggest gains should appear on queries where:

- `gold_in_candidates = true`
- `first_gold_rank` is already reasonably shallow
- the current failure is incomplete assembly rather than complete absence

### Negative expectation

Reranking should **not** materially fix queries where gold never enters the candidate pool. Those cases should remain signals for Stage B expansion or later Stage C enrichment.

---

## 3. Non-goals

- This is not a Stage C implementation.
- This is not bounded multihop controller work beyond fixed-pool reordering.
- This is not open-ended agentic retrieval.
- This is not answer-generation optimization.
- This is not permission to compare across mismatched benchmark contracts or surfaces.

---

## 4. Design principles

The first reranking slice should obey these rules:

1. **Fixed pool only.**
   The reranker may reorder candidates, but it may not retrieve new ones.

2. **Surface-aware evaluation.**
   Results must be reported separately for:
   - `pf2e_multihop_e2e_working_set`
   - `pf2e_multihop_microbundle_working_set`

3. **Deterministic enough to audit.**
   Use a pinned model, temperature `0`, fixed prompt template, strict schema, cached outputs, and deterministic tie-breaks.

4. **No benchmark leakage.**
   The reranker should not see:
   - `expected_answer_summary`
   - `required_gold`
   - gold rationales
   - benchmark labels such as "micro-bundle" or "e2e"

5. **Trace everything.**
   Every reranked run should make it easy to answer:
   - which candidates moved
   - which required units crossed into or out of top 10
   - whether gains came from real evidence assembly or cosmetic reshuffling

---

## 5. Recommended experiment ladder

Do not jump directly from current hybrid baseline to a single LLM reranker run with no controls. Use a small ladder so we can tell whether any gain is truly LLM-specific.

### R0. Existing baseline

Control:

- current PF2E hybrid baseline
- `retrieval_mode: hybrid`
- `hybrid_fusion_method: cc`

Purpose:

- anchor all comparisons to the current live baseline

### R1. Existing non-LLM rerank control

Control:

- current hybrid candidate pool
- current rerank hook using the existing cross-encoder path or dense second-stage rerank

Purpose:

- establish whether simple reranking already captures most of the available lift
- separate "any reranking helps" from "LLM reranking specifically helps"

### R2. Primary proposed experiment: LLM listwise rerank

Treatment:

- retrieve with the same hybrid CC baseline
- freeze a candidate pool
- ask a pinned LLM to return an ordered subset or ordered full list of candidates
- evaluate post-rerank top-k only

Purpose:

- test whether listwise judgment over a bounded pool better prioritizes complementary evidence for multihop questions

### R3. Optional follow-up: LLM pairwise rerank

Treatment:

- same fixed pool
- pairwise comparisons or tournament-style ordering

Purpose:

- compare stability, cost, and quality against listwise reranking

Recommendation:

- debate and design `R2` now
- keep `R1` as the must-have control
- defer `R3` unless listwise output proves unstable or overly expensive

---

## 6. Primary experiment design: LLM listwise rerank

### 6.1 Retrieval input

Use the current PF2E hybrid baseline exactly as the candidate generator:

- `retrieval_mode: hybrid`
- `hybrid_fusion_method: cc`
- same embedding model as baseline
- same substrate and benchmark projections

This keeps the candidate-generation layer fixed so the readout isolates reranking.

### 6.2 Candidate pool size

Primary recommendation:

- admit the top `40` candidates from the hybrid run into the reranker

Why `40`:

- large enough that missing-complement evidence may already be present
- small enough to keep prompt size and cost bounded
- aligned with the design memo's recommended `max_total_candidate_pool_before_rerank: 40`

Debate point:

- if we believe the current hybrid pool often hides required gold below rank 40, then use `50`
- if we want a tighter production-faithful budget, then use `30`

Default position:

- start with `40`

### 6.3 Candidate payload shown to the model

Each candidate should expose only bounded, audit-friendly fields:

- `candidate_id`
- `baseline_rank`
- `structural_path`
- `unit_type`
- short text excerpt or truncated body

Recommended text budget:

- truncate candidate text to a fixed limit, such as `700-900` characters
- keep deterministic truncation rules

The reranker should not see the full benchmark curation metadata.

### 6.4 Query payload shown to the model

The model should see:

- the normalized user question

Optional but debatable:

- deterministic subquery decomposition generated by the controller

Not allowed in the first rerank experiment:

- expected answer summary
- gold annotations
- benchmark notes

### 6.5 Output schema

The model should return a strict JSON object like:

```json
{
  "ordered_candidate_ids": ["c17", "c03", "c08", "c12"],
  "rationale_tags": {
    "c17": ["direct_rule", "high_specificity"],
    "c03": ["complements_other_evidence"],
    "c08": ["exception_rule"],
    "c12": ["background_context"]
  }
}
```

Allowed rationale tags should come from a small fixed vocabulary, for example:

- `direct_rule`
- `high_specificity`
- `required_anchor_likely`
- `complements_other_evidence`
- `exception_rule`
- `definition_link`
- `table_lookup`
- `generic_context`
- `distractor_risk`

These tags are for audit and analysis, not for scoring.

### 6.6 Determinism and audit constraints

- pinned model ID
- temperature `0`
- fixed prompt template ID and prompt hash
- strict JSON schema validation
- caching required
- deterministic fallback on schema failure
- deterministic tie-break by baseline rank, then `candidate_id`

### 6.7 Hard boundaries

The LLM reranker may:

- reorder candidates
- optionally drop low-value candidates if the schema explicitly supports this

The LLM reranker may not:

- retrieve new candidates
- hallucinate candidate IDs
- emit free-text answers
- cite from outside the provided candidate pool

---

## 7. Scoring plan

The reranking experiment should be scored on both PF2E surfaces separately.

### 7.1 Surface A: `pf2e_multihop_e2e_working_set`

Primary metrics:

- `ReqFSH@10`
- `rank_of_last_required_mean`

Secondary metrics:

- `MRR`
- `Hit@10`
- `Recall@10`

Primary question:

- does reranking move enough already-present evidence into the top 10 to solve more whole multihop tasks?

### 7.2 Surface B: `pf2e_multihop_microbundle_working_set`

Primary metrics:

- `ReqFSH@10`
- per-parent micro-bundle pass rate at 10

Secondary metrics:

- `Hit@10`
- `Recall@10`
- `rank_of_last_required_mean`

Primary question:

- which narrow evidence obligations improve under reranking?

### 7.3 Interpretation rules

If e2e improves and micro-bundles improve:

- reranking is helping both local obligation prioritization and whole-task assembly

If micro-bundles improve but e2e does not:

- reranking is helping local evidence ordering, but full-chain assembly still fails under the top-10 cap

If neither improves:

- ranking is probably not the main bottleneck for that slice

If one or more queries remain `gold_not_in_candidates`:

- treat those as out of scope for reranking and feed them into later structural or Stage C work

---

## 8. Regression guardrails

A reranker should not be promoted on PF2E multihop alone.

It should also be checked against at least one precision-sensitive benchmark slice, such as:

- PF2E 50q benchmark
- a selected clean subset if available
- any known T1-sensitive evaluation surface already used in Retrieval Lab recommendations

Minimum promotion rule:

- meaningful improvement on PF2E multihop rank-sensitive metrics
- no material regression on precision-sensitive slices
- no benchmark-contract mismatch
- no unexplained answer-fidelity regression if answer evaluation is run

---

## 9. Required artifacts

Each rerank run should emit enough detail to support argument, not just scoreboard reading.

### 9.1 Per-run artifacts

- standard Retrieval Lab metrics by surface
- per-query rerank diagnostics
- prompt template ID and prompt hash
- reranker model ID
- cache hit rate

### 9.2 Per-query diagnostics

For each query, record:

- baseline candidate pool size
- pre-rerank top 10 IDs
- post-rerank top 10 IDs
- required gold IDs present in pool
- required gold ranks before rerank
- required gold ranks after rerank
- whether each required unit crossed the top-10 boundary

### 9.3 Summary tables worth keeping

- queries helped by reranking
- queries hurt by reranking
- queries unchanged
- queries that remained candidate misses
- parent-child decomposition summaries for micro-bundles

---

## 10. Debate points before execution

These are the main choices worth debating before any code or runs happen.

### A. Should the first LLM reranker be listwise or pairwise?

Argument for listwise:

- better fit for multihop complementarity
- one pass can reason about coverage and redundancy

Argument for pairwise:

- easier to constrain
- sometimes more stable
- potentially clearer failure analysis

Current recommendation:

- start with listwise
- keep pairwise as follow-up only if listwise proves unstable

### B. Should we compare against a cross-encoder first?

Argument for yes:

- the codebase already has a rerank path
- gives a cheap and fair non-LLM control
- avoids attributing generic reranking lift to the LLM

Current recommendation:

- yes, include the existing cross-encoder rerank as `R1`

### C. How large should the candidate pool be?

Argument for `40`:

- balanced between recall opportunity and cost

Argument for `50`:

- closer to the current existing rerank hook in live code

Argument for `30`:

- more production-like and cheaper

Current recommendation:

- start with `40`
- if debate remains unresolved, run `40` and `50` as a tiny ablation

### D. Should the reranker see controller-generated subqueries?

Argument for yes:

- helps the model recognize multi-obligation structure

Argument for no:

- muddies the attribution between reranking and query decomposition

Current recommendation:

- first experiment should use the normalized original query only
- add structured subqueries later as a separate ablation

### E. Should the reranker be allowed to drop candidates rather than only reorder?

Argument for reorder-only:

- simpler attribution
- easier to compare pre/post ranks

Argument for reorder-and-prune:

- better practical top-k focus

Current recommendation:

- reorder only in the first slice

---

## 11. Proposed first decision

If we want the cleanest first debate target, the first reranking experiment should be:

- baseline generator: PF2E hybrid CC
- control 1: no rerank
- control 2: existing cross-encoder rerank over fixed pool
- treatment: LLM listwise rerank over fixed pool of 40
- benchmark surfaces:
  - `pf2e_multihop_e2e_working_set`
  - `pf2e_multihop_microbundle_working_set`
- regression guard:
  - PF2E 50q or another precision-sensitive slice

This design gives us the right question:

- not "can an LLM do something impressive?"
- but "does an LLM reranker produce measurable full-set and rank-depth lift beyond the current hybrid baseline and beyond a simpler reranking control?"

---

## 12. What success would look like

The experiment is worth pursuing further if it shows most of the following:

- e2e `ReqFSH@10` improves on the PF2E multihop parent slice
- e2e `rank_of_last_required_mean` improves meaningfully
- micro-bundle pass rate improves on the same parent families
- gains cluster on current ranking-depth failures rather than on already-easy queries
- there is no meaningful regression on precision-sensitive benchmark slices
- traces clearly show already-present required evidence moving upward rather than noisy churn

If those do not happen, the next lever is probably not more reranking work. It is more likely:

- structural expansion
- better decomposition
- or later Stage C typed enrichment for true candidate misses

---

## Appendix A. D&D 5e 2024 multihop retrieval benchmark questions

This appendix contains thirty multi-hop questions derived from the 2024 edition of the *Dungeons & Dragons Player's Handbook* (PHB). Each question is designed to require information from multiple sections of the PHB, such as class descriptions, subclasses, feats, backgrounds, spell lists, and general rules, so that a retrieval system must assemble evidence from diverse locations. The questions reference new or revised rules from the 2024 PHB and are not intended to be fully answerable from a single page or entry.

### Questions

1. **Acolyte + Magic Initiate (Cleric):** A character chooses the Acolyte background in the 2024 PHB, which grants the Magic Initiate (Cleric) feat. What spells does the character gain from the feat, how do they interact with the character's class spellcasting ability, and what skill and tool proficiencies and ability score increases come from the Acolyte background? Explain any restrictions or options for spell selection and casting.

2. **Artisan + Crafter:** The Artisan background grants the Crafter feat. According to the 2024 PHB, how does the Crafter feat's discount on non-magical items and its ability to craft equipment during a long rest interact with the rules for purchasing or crafting items? What additional tool proficiencies and starting equipment does the Artisan background provide, and how could a martial character combine these benefits with class features like Fighting Style or Martial Arts?

3. **Charlatan + Skilled:** A character with the Charlatan background gains the Skilled feat. How many additional skill proficiencies are granted by the feat and the background combined, and how does this interact with a Rogue's Expertise feature? Include the background's tool proficiency and ability score increases in your discussion.

4. **Criminal + Alert:** The Criminal background in 2024 grants the Alert feat. Summarize the benefits of the Alert feat under the new rules (initiative, reactions, etc.), and explain how these benefits combine with the Dexterity and Constitution ability score increases, skill proficiencies (Sleight of Hand and Stealth), and tool proficiency from the Criminal background.

5. **Entertainer + Musician:** The Entertainer background grants the Musician feat. Describe how the Musician feat allows a character to grant Inspiration during a rest and to play musical instruments, and explain how this interacts with the revised Bardic Inspiration rules for Bards. Mention the Entertainer's ability score options, skill proficiencies, tool proficiencies, and starting equipment.

6. **Farmer + Tough:** In the 2024 PHB, the Farmer background grants the Tough feat. Discuss how the Tough feat's increase to maximum hit points works, how it interacts with the Farmer's Constitution bonus, and what starting equipment and skills the background provides. Explain why this combination may appeal to Barbarians or Druids.

7. **Soldier + Savage Attacker:** The Soldier background grants the Savage Attacker feat, which is no longer limited to melee weapons. Explain how Savage Attacker now works for both melee and ranged weapon attacks and how it synergizes with class features like the Fighter's Extra Attack or the Barbarian's Reckless Attack. Include the Soldier's ability score options, skill proficiencies, tool proficiencies, and starting equipment in your answer.

8. **Wayfarer + Lucky:** A character with the Wayfarer background gains the Lucky feat. Discuss how the Lucky feat now scales with your proficiency bonus and allows you to spend luck points to influence rolls. Explain how the Wayfarer's ability score increases, skill proficiencies (Insight and Stealth), tool proficiency (Thieves' Tools), and starting equipment support classes like Rangers, Rogues, Monks, and Bards.

9. **Noble + Skilled:** The Noble background grants the Skilled feat. Analyze how the three additional skill proficiencies from the feat interact with the Noble's existing skills (History and Persuasion) and ability scores, and discuss how classes like Rogues or Bards can leverage this combination. Include mention of the background's tool proficiency and starting equipment.

10. **Hermit/Moonwell Pilgrim + Magic Initiate (Druid):** Both the Hermit and Moonwell Pilgrim backgrounds grant Magic Initiate (Druid). Choose one of these backgrounds and describe the ability score increases, skill proficiencies, and tool proficiency it provides. Then explain how Magic Initiate (Druid) allows the character to learn specific Druid cantrips and a 1st-level spell, how these spells are cast, and how this interacts with class features like Wild Shape or Circle of the Moon.

11. **Sage + Magic Initiate (Wizard):** The Sage background grants Magic Initiate (Wizard). Describe the Sage's ability score options, skill proficiencies (Arcana and History), tool proficiency, and starting equipment. Then explain how Magic Initiate (Wizard) allows a non-wizard to learn and cast wizard spells, and how this feat interacts with the Wizard's revised spellcasting and Arcane Tradition features in 2024.

12. **Healer feat & spells:** The Healer feat allows you to use a Healer's Kit to let a creature spend a Hit Die and regain extra HP based on your proficiency bonus. Explain how this feat interacts with healing spells such as Healing Word, Prayer of Healing, or Mass Healing Word, and discuss how ability score bonuses or class features (e.g., a Life Domain Cleric's Disciple of Life) influence the healing done.

13. **Crafter feat & crafting rules:** The Crafter feat provides proficiency with three sets of artisan's tools, a discount on non-magical items, and the ability to craft equipment during a long rest. Describe how this discount applies when purchasing mundane equipment, how crafting works under the 2024 rules, and how backgrounds like Artisan or Mythalkeeper (which also grant Crafter) further enhance these abilities.

14. **Musician feat & Bardic Inspiration:** The Musician feat allows a character to grant Inspiration during a short rest. Discuss how this feat complements the 2024 Bardic Inspiration rules, including how Inspiration can be used on ability checks, saving throws, and attack rolls. Provide examples of how a Bard with the Entertainer background might leverage both abilities during play.

15. **Lucky feat & proficiency bonus:** The Lucky feat now grants luck points equal to your proficiency bonus, which you can spend to gain advantage or impose disadvantage on rolls. Explain how this scaling works over a character's career and how the Lucky feat interacts with class features like the Divination Wizard's Portent ability or the Halfling's Lucky racial trait. Include examples using the Wayfarer or Merchant backgrounds.

16. **Alert feat & initiative synergy:** Summarize the new benefits of the Alert feat, such as bonuses to initiative and the inability to be surprised, and discuss how these benefits stack with ability score increases and skills from backgrounds like Criminal, Guard, or Ice Fisher (all of which grant Alert). Consider interactions with class features such as the Rogue's Cunning Action or the Ranger's Favored Foe.

17. **Skilled feat & expertise:** The Skilled feat grants three additional skill proficiencies. Explain how this feat interacts with class features like the Rogue's Expertise or the Bard's Jack of All Trades, and discuss combinations involving backgrounds such as Charlatan, Noble, Scribe, or Chondathan Freebooter. Provide examples of how stacking skill proficiencies can create versatile characters.

18. **Sorcerer: Wild Magic Surge & subclass changes:** The 2024 PHB revises the Wild Magic Sorcerer subclass so that Wild Magic Surge now triggers only when you roll a 20 on a d20 after casting a spell. Describe how this change affects the frequency of Wild Magic events, and explain how the revised Tides of Chaos, Bend Luck, and new Tamed Surge features interact with the base Sorcerer class features (e.g., Font of Magic and Metamagic).

19. **Sorcerer: Innate Sorcery & Sorcery Points:** The Sorcerer now gains Innate Sorcery at level 1 and new features at level 2 that alter Font of Magic, including Sorcery Point creation as a free action. Explain how these new features interact with Metamagic options (which are now gained at level 2) and discuss how Innate Sorcery enhances spellcasting flexibility. Include a comparison between the 2014 and 2024 rules and any interactions with feats like Magic Initiate.

20. **Cleric: Domain & Channel Divinity:** In the 2024 PHB, Clerics receive their subclass (Divine Domain) at level 3. Choose a domain (e.g., Life, War, or a revised domain) and summarize how its level 3 and level 6 features work with the Cleric's revised Channel Divinity and Divine Spark abilities. Discuss how domain spells interact with the Cleric's general spell list and how a background-granted feat like Healer can enhance these features.

21. **Fighter: Subclass & Savage Attacker synergy:** The 2024 PHB standardizes Fighter subclasses so that they all begin at level 3. Pick one subclass (Champion, Battle Master, Eldritch Knight, or a new option) and describe how its level 3 feature interacts with core Fighter abilities such as Fighting Style and Action Surge. Include an example of how the Savage Attacker feat from the Soldier background could further improve the subclass's combat effectiveness.

22. **Paladin: Oaths & Channel Divinity:** Under the 2024 rules, Paladins receive their oath at level 3. Choose an oath (Oath of Devotion, Vengeance, etc.) and describe how the oath's channel divinity options and aura abilities integrate with the revised Paladin class features and spell list. Discuss how the Paladin's features interact with feats like Alert or Lucky from appropriate backgrounds.

23. **Ranger: Favored Foe & subclass synergy:** The 2024 PHB revises the Ranger's early features, including Favored Foe and possibly retiring Favored Terrain. Pick a Ranger subclass (e.g., Hunter or Gloom Stalker) and explain how its features combine with the new Favored Foe rules. Discuss how a background like Wayfarer or Guide (providing the Lucky or Alert feat) can improve the Ranger's effectiveness.

24. **Rogue: Cunning Strike & skills:** The 2024 PHB replaces the Rogue's Blindsense with a new Cunning Strike ability at level 14 (per community reports). Describe how Cunning Strike modifies Sneak Attack and how this interacts with feats like Skilled or Alert from backgrounds such as Charlatan or Criminal. Also discuss how new subclasses might alter this interaction.

25. **Monk: Tavern Brawler & unarmed strikes:** The Tavern Brawler feat has been updated so that it increases unarmed strike damage, allows you to reroll a 1 on the damage die, and can push a target. Explain how this feat interacts with a Monk's Martial Arts feature and subclass abilities (e.g., Open Hand Technique). Discuss whether the feat's benefits stack with a Monk's unarmed strike dice and how it affects grappling or shoving.

26. **Barbarian: Rage & Tough/Savage Attacker synergy:** Discuss how the 2024 Barbarian's Rage features (including any new or revised subclasses) interact with feats like Tough (extra hit points) and Savage Attacker. Explain how combining these feats with backgrounds such as Farmer or Soldier can enhance a Barbarian's durability and damage output.

27. **Wizard: Arcane Tradition & Magic Initiate synergy:** The 2024 PHB reduces the number of wizard subclasses and may modify their features. Choose an Arcane Tradition (e.g., Evocation or a new one introduced in 2024) and discuss its level 3 feature. Then explain how the Magic Initiate (Wizard) feat from the Sage or Genie Touched background lets non-wizards cast wizard spells and how this interacts with the wizard's revised spell preparation and spell list.

28. **Multiclass spell slot calculation:** The 2024 PHB changes the way multiclass spellcasting is handled for certain classes. Using the 2024 rules, calculate the spell slots available to a character who is a Bard 3 / Paladin 2. Explain how the subclass standardization and spell list revisions affect spell preparation and the availability of domain or oath spells compared to the 2014 rules.

29. **Magic action & antimagic fields:** The 2024 PHB introduces a unified Magic action for anything involving spellcasting or activating magic items. Describe what constitutes a Magic action and explain how this classification interacts with antimagic fields or dispel magic. Provide examples of class features (such as the Sorcerer's Metamagic, the Paladin's Lay on Hands, or a Ranger's Hunter's Mark) and whether they require a Magic action or a different type of action under the new rules.

30. **Spell changes & healing synergy:** Choose a spell that has been revised in the 2024 PHB, such as Prayer of Healing, Mass Healing Word, Sleep, or Aid, and summarize the changes. Explain how these changes interact with feats like Healer or class features like the Life Domain's Disciple of Life and the Paladin's Lay on Hands. Discuss how a character might combine these features to maximize healing or control effects under the new rules.
