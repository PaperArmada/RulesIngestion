# PF2E Multihop Benchmark Design

## Goal

Design a Pathfinder 2e Player Core multihop benchmark as a diagnostic `working_set` suite first, using the 30 seed prompts as the source bank and normalizing them into benchmark-ready retrieval questions.

This benchmark is intended to stress:

- candidate generation failures
- bounded multihop expansion
- reranking depth failures
- answer assembly failures after retrieval

It should fit the current Retrieval Lab definition/projection workflow and later support derivation of a smaller promotion-grade subset.

## Recommended Artifact Layout

Primary benchmark definition target:

- `RulesIngestion/evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_multihop_working_set_benchmark.json`

Possible later derivative:

- `RulesIngestion/evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_multihop_ratified_subset.json`

Recommended ID namespace:

- `pf2e_mh_ws_001` through `pf2e_mh_ws_020` for the initial retained working-set catalog
- reserve `pf2e_mh_rs_001+` for any later ratified subset if you want a visibly separate recommendation-grade lineage

Recommended metadata stance:

- `benchmark_track`: `working_set`
- default `_status`: `uncited` until grounded
- default `_mode`: `multi_cite` for the multihop set unless grounding proves a query is operationally answerable from a single anchor
- keep `gold_locations` as the durable curation layer; treat `required_gold`, `supporting_gold`, and `gold_unit_ids` as projection-sensitive outputs

## Dual-Surface Evaluation Structure

The PF2E multihop benchmark should be treated as two related `working_set` surfaces rather than one blended score.

### Surface 1: `pf2e_multihop_e2e_working_set`

Purpose:

- preserve the original user-shaped multihop questions
- measure whether retrieval can assemble the full evidence chain inside a realistic top-k budget
- remain the primary production-facing retrieval benchmark for this family

What belongs here:

- the original normalized multihop questions such as `pf2e_mh_ws_001`
- larger multi-anchor questions are allowed when they reflect the real user task
- `required_gold` may exceed ratified-core norms when the full task genuinely requires it

Primary scoring for this surface:

- `ReqFSH@10` is the primary success metric
- `rank_of_last_required_mean` is the primary depth diagnostic
- `MRR`, `Hit@k`, and `Recall@k` remain secondary supporting metrics

How to interpret it:

- strong `gold_in_candidates` with weak `ReqFSH@10` means the system can find relevant neighborhoods but cannot yet assemble the full chain in the top 10
- improving `MRR` without improving `ReqFSH@10` means first-hit quality is getting better but full evidence assembly is still incomplete
- this surface should answer: "Can the retriever solve the whole question under realistic constraints?"

### Surface 2: `pf2e_multihop_microbundle_working_set`

Purpose:

- decompose the largest multihop questions into smaller evidence obligations
- provide sharper retrieval-only signal for Stage C, query expansion, structural expansion, and reranking changes
- identify which hop is still failing before end-to-end success arrives

What belongs here:

- micro-questions derived from an end-to-end parent query
- each micro-bundle should target one narrow evidence obligation such as:
- feat discovery
- baseline rule linkage
- exception or stacking rule retrieval
- environment-rule mitigation lookup
- table-to-text bridge retrieval

Recommended micro-bundle discipline:

- target `required_gold` size of `1-2`, with `3` as an upper bound except in unusual cases
- each micro-bundle should keep one clearly named parent query reference
- micro-bundles should remain diagnostically narrow rather than becoming alternate paraphrases of the entire macro question

Primary scoring for this surface:

- `ReqFSH@10` is still the primary metric, but here it becomes a much sharper signal because the required set is intentionally small
- `Recall@10` and `Hit@10` are useful secondary diagnostics
- per-hop pass rate across all micro-bundles from the same parent query should be tracked as an explicit decomposition summary

How to interpret it:

- this surface should answer: "Which evidence obligation is broken?"
- if micro-bundles improve while the parent end-to-end query stays red, the retriever is making real progress but still lacks full-chain assembly
- if micro-bundles remain weak, the problem is earlier in the pipeline and Stage C or expansion changes are not yet solving the missing hop

### Comparison Rules

The two surfaces should be compared together, but they should not be collapsed into one unlabeled aggregate score.

Do:

- report `pf2e_multihop_e2e_working_set` and `pf2e_multihop_microbundle_working_set` separately
- compare dense baseline, hybrid baseline, Stage C enrichment, and later systems on both surfaces
- use the e2e surface to assess realistic task completion
- use the micro-bundle surface to assess where partial progress is happening

Do not:

- average the macro and micro surfaces into one headline number
- treat micro-bundle gains alone as proof of production readiness
- remove the original question just because its diagnostic children exist

Recommended readout pattern:

- first ask whether `pf2e_multihop_e2e_working_set` improved on `ReqFSH@10` and last-required-rank
- then inspect whether `pf2e_multihop_microbundle_working_set` improved on the same parent queries
- if micro-bundles improve but e2e does not, the remaining problem is full-chain assembly or ranking depth
- if neither improves, the retrieval change likely did not fix the intended hop

### Retrieval Lab Mapping

Within Retrieval Lab, both surfaces should be emitted and compared as independent benchmark definitions or independent query batches, each with its own scored artifacts.

Recommended naming:

- end-to-end surface label: `pf2e_multihop_e2e_working_set`
- diagnostic decomposition label: `pf2e_multihop_microbundle_working_set`

Recommended promotion stance:

- keep both surfaces in `working_set` during iteration
- promote only carefully selected end-to-end or micro-bundle entries into a later clean ratified subset
- do not assume a micro-bundle should be ratified just because it is easy; it still has to represent a meaningful retrieval obligation

This gives us both:

- a realistic macro benchmark for "can we solve the whole PF2E task?"
- a fine-grained diagnostic benchmark for "did we fix the missing hop?"

## Worked Example: E2E Plus Micro-Bundles

The dual-surface structure is easiest to evaluate if we show one concrete retained query in both forms.

### Example parent query in `pf2e_multihop_e2e_working_set`

Use `pf2e_mh_ws_010` as the reference case:

- End-to-end question:
- `What limits does Player Core place on casting spells underwater, especially spells with verbal components, and what feats, spells, or abilities mitigate those limits?`

Operational evidence shape:

- one anchor for the underwater environment or breathing/speaking restriction
- one anchor for spell component or verbal-casting requirements
- one or more mitigation anchors such as a feat, spell, or class ability that changes the constraint

Why this is a good e2e query:

- it is user-shaped rather than artificially decomposed
- it crosses rule families instead of staying inside one feat table
- it needs complete evidence assembly, not just one relevant hit

Primary success readout for the e2e version:

- `ReqFSH@10`: did all required anchors land in the top 10?
- `rank_of_last_required`: how deep did the retriever have to go before the full chain was assembled?
- `MRR` and `Hit@k`: did the system at least get onto the right evidence neighborhood quickly?

### Derived diagnostic units in `pf2e_multihop_microbundle_working_set`

The same parent query can be decomposed into narrower micro-bundles.

Recommended example decomposition:

- `pf2e_mh_mb_010a`
- question: `What underwater rule or condition limits speaking or breathing in a way that matters for spellcasting?`
- expected evidence obligation: environment-rule anchor only

- `pf2e_mh_mb_010b`
- question: `What rule makes verbal spell components sensitive to whether the caster can speak?`
- expected evidence obligation: spell-component anchor only

- `pf2e_mh_mb_010c`
- question: `Which PF2e option mitigates underwater casting limits for spells that would otherwise be blocked by speaking or breathing constraints?`
- expected evidence obligation: one mitigation anchor, or one mitigation family if the question is still narrow enough for `required_gold <= 2`

- `pf2e_mh_mb_010d`
- question: `Which mitigation specifically addresses underwater casting rather than general aquatic survival?`
- expected evidence obligation: exception or applicability anchor that distinguishes relevant mitigation from merely adjacent water-related options

Recommended micro-bundle metadata discipline:

- `parent_query_id: pf2e_mh_ws_010`
- keep `required_gold` at `1-2` where possible
- use one micro-bundle per distinct retrieval obligation, not one per sentence of the answer

### Example scoring readout

Suppose a retrieval change improves rule linkage but not full-chain assembly yet.

Possible e2e surface result:

- `pf2e_mh_ws_010`
- `MRR = 1.0`
- `Hit@10 = 1.0`
- `ReqFSH@10 = 0`
- `rank_of_last_required = null`

Interpretation:

- the retriever is getting onto the right neighborhood immediately
- at least one gold anchor is present early
- but the full evidence chain is still incomplete by top 10

Possible micro-bundle surface result:

- `pf2e_mh_mb_010a`: `ReqFSH@10 = 1`
- `pf2e_mh_mb_010b`: `ReqFSH@10 = 1`
- `pf2e_mh_mb_010c`: `ReqFSH@10 = 0`
- `pf2e_mh_mb_010d`: `ReqFSH@10 = 0`

Interpretation:

- the system can retrieve the baseline underwater rule
- the system can retrieve the verbal-component rule
- the remaining weakness is mitigation retrieval or applicability filtering
- Stage C or structural enrichment should now be judged on whether it flips `010c` and `010d`, not only on whether the whole parent query turns green immediately

### Why this dual readout is better

If we only scored the e2e query:

- we would see a failure on `ReqFSH@10`
- but we would not know whether the missing evidence was:
- the environment rule
- the component rule
- the mitigation option
- the applicability or exception bridge

If we only scored the micro-bundles:

- we could miss the fact that the retriever still fails to assemble all obligations under one realistic top-10 cap

Using both surfaces together gives the correct read:

- the e2e query tells us whether the real user task is solved
- the micro-bundles tell us which hop still blocks the real user task

### Recommended reporting pattern for parent-child groups

For any parent query with diagnostic children, report both:

- parent query outcome:
- `MRR`, `ReqFSH@10`, `rank_of_last_required`

- child bundle outcome:
- pass rate across the micro-bundles for that parent
- list of which child obligations are still failing

Suggested decomposition summary:

- `parent_query_id: pf2e_mh_ws_010`
- `microbundle_pass_rate_at_10: 2/4`
- `still_failing_obligations: ["mitigation retrieval", "applicability filtering"]`

This summary makes Stage C comparisons much easier to reason about than a single parent-level `0`.

## Seed Prompt Classification

| Seed | Working title | Retrieval pattern | Decision | Direction |
|---|---|---|---|---|
| 1 | Reactions by ancestry | cross-table enumeration | split | Break into smaller ancestry-feat slices or a reactions-only ancestry pilot set later. |
| 2 | Hit-point and healing feats | broad feat inventory | defer | Too diffuse across feat families, ancestries, and scaling rules for the first multihop suite. |
| 3 | Arcane attack spells | spell-list plus spell-text lookup | keep | Retain as a bounded spell-inventory query with explicit rank and trait filters. |
| 4 | Enhancing Hunt Prey | class feat chain | keep | Strong class-local multihop query with manageable scope and good rerank signal. |
| 5 | Twin Takedown vs Double Slice | cross-class feat comparison | keep | Strong two-anchor comparison with MAP handling and damage-combination detail. |
| 6 | Darkvision upgrades | broad inventory across many subsystems | split | Split later by source family such as ancestry-only or feat-source comparisons. |
| 7 | Bardic compositions inventory | spell inventory plus stacking | split | Split into inventory and stacking/interplay queries; keep the stacking query now. |
| 8 | Level-10 action modifiers | wide cross-class inventory | split | Better as smaller class-family slices rather than one all-class benchmark entry. |
| 9 | Stances across classes | wide feat inventory | split | Too broad as written; keep targeted stance-interaction questions instead. |
| 10 | Champion causes and reactions | class doctrine plus reaction bundle | keep | Good multi-anchor class-structure query. |
| 11 | Disruptive Stance vs Reactive Strike | feat plus reaction interaction | keep | High-value interaction query for multihop expansion and answer assembly. |
| 12 | Shield Block interactions | reaction stacking and timing | keep | Retain as a shield-reaction interaction query, but normalize around concrete action-economy limits. |
| 13 | Bardic composition interplay | spell stacking / overlap | keep | Good focused descendant of the broader bard composition inventory prompt. |
| 14 | Skirmish Strike vs Opportune Backstab | feat comparison plus MAP | keep | Strong cross-class tactical comparison query. |
| 15 | Witch familiars and hexes | class feature plus familiar ability interaction | keep | Good multihop class query if normalized and grounded conservatively. |
| 16 | Casting underwater | environment rule plus spellcasting mitigation | keep | Strong rules-interaction query spanning environment, components, and mitigation options. |
| 17 | Multiclass two-weapon synergy | build legality plus action sequencing | keep | Distinct from the pure feat comparison query and worth retaining separately. |
| 18 | Sneak Attack and fear effects | condition plus class-feature interaction | keep | Strong cross-anchor rules interaction; update wording to remaster terms. |
| 19 | Disrupting concentrate spells | feat plus trait plus disruption timing | keep | Similar cluster to seed 11, but specific enough to retain as a separate spell-facing query. |
| 20 | Quick Alchemy outside your turn | likely corpus-mismatch subsystem | defer | Verify corpus coverage before reviving; likely belongs in a different book or later PF2e corpus. |
| 21 | Level-1 reaction feats by class | wide class inventory | split | Better as narrower class-family or reaction-category slices. |
| 22 | Removing poison | spell family comparison | keep | Strong bounded spell-comparison query across traditions and secondary effects. |
| 23 | Aggressive Block vs Shield Warden | shield feat comparison | keep | Strong interaction query and cleaner than the broader shield-block cluster. |
| 24 | Backgrounds with Warfare Lore | background plus class training interaction | keep | Good low-noise query with clear multihop structure. |
| 25 | Ranger vs Druid spell progression | cross-class progression comparison | keep | Strong progression query with clear evidence neighborhoods. |
| 26 | Increasing initiative | broad inventory of modifiers | split | Split later by feat-based bonuses, rerolls, and status/item/circumstance sources. |
| 27 | Hexes affecting defenses | focused spell-family comparison | keep | Good witch-specific debuff query with stacking analysis. |
| 28 | Champion and fighter weapon proficiencies | proficiency progression and multiclass interaction | keep | Strong rules-progression query. |
| 29 | Mid-level mobility feats | broad class-feat inventory | split | Better as movement-mode-specific slices later. |
| 30 | Rogue spellcasting options | class path plus archetype/racket access | keep | Strong class-option comparison with level gating and spell access. |

## Retained Working-Set Catalog

The initial retained catalog contains 20 benchmark-ready working-set queries.

### Query Catalog

| ID | Derived from | Tier | Type | Normalized question | Expected answer summary | Evidence plan | Expected multihop type |
|---|---|---|---|---|---|---|---|
| `pf2e_mh_ws_001` | 3 | T3 | `reasoning` | Which arcane spells of rank 3 or lower in Player Core use spell attack rolls and increase their damage when heightened, and how do their targets and heightening entries differ? | Enumerate low-rank arcane spell-attack spells with damage-scaling heightening clauses. | Likely `multi_anchor`; spell-list anchor plus several spell-text anchors. | `rewrite`, `rerank_sensitive` |
| `pf2e_mh_ws_002` | 4 | T2 | `lookup` | Which ranger feats in Player Core modify Hunt Prey or add benefits that apply specifically to your hunted prey, and what new benefit does each feat grant? | Inventory of Hunt Prey modifier feats with level, benefit, and key trait or stance distinctions. | Likely `multi_anchor`; feat-table plus feat-text anchors. | `structural_expansion` |
| `pf2e_mh_ws_003` | 5 | T2 | `reasoning` | How do Twin Takedown and Double Slice differ in action cost, requirements, combined-damage handling, and multiple attack penalty treatment? | Compare the two feats on actions, prerequisites, damage-combination rules, and MAP handling. | Likely `multi_anchor`; one anchor per feat plus supporting MAP rule if needed. | `rerank_sensitive` |
| `pf2e_mh_ws_004` | 10 | T2 | `lookup` | What champion causes are available in Player Core, and what reaction, tenets, and deity or cause restrictions does each one grant? | Enumerate the causes and connect each one to its reaction and restrictions. | Likely `multi_anchor`; cause overview plus per-cause reaction anchors. | `structural_expansion` |
| `pf2e_mh_ws_005` | 11 | T3 | `reasoning` | How does Disruptive Stance modify Reactive Strike against actions with the concentrate trait, and what changes from the baseline Reactive Strike disruption rule? | Explain the baseline Reactive Strike disruption behavior and the extra concentrate-action coverage from the stance. | Likely `multi_anchor`; stance text plus Reactive Strike text plus trait support. | `typed_closure_later`, `rerank_sensitive` |
| `pf2e_mh_ws_006` | 12 | T3 | `reasoning` | How do Shield Block and shield-related reaction abilities interact in the same round, and what timing limits apply when a character has more than one shield-based defensive option available? | Explain same-round reaction limits and whether shield defenses stack, replace, or compete. | Likely `multi_anchor`; Shield Block plus one or more shield-reaction feature anchors. | `reasoning_chain`, `rerank_sensitive` |
| `pf2e_mh_ws_007` | 13 | T2 | `reasoning` | How do Courageous Anthem and Dirge of Doom affect the same encounter, and which parts of their effects stack, overlap, or conflict? | Compare areas, effects, durations, and overlap or stacking behavior. | Likely `multi_anchor`; one spell anchor per composition plus condition or bonus context. | `rerank_sensitive` |
| `pf2e_mh_ws_008` | 14 | T2 | `reasoning` | How do Skirmish Strike and Opportune Backstab differ in trigger, action cost, and multiple attack penalty handling, and can a character use both in the same round? | Compare trigger timing, action or reaction cost, MAP handling, and same-round compatibility. | Likely `multi_anchor`; one anchor per feat plus supporting timing/MAP rule if needed. | `rerank_sensitive` |
| `pf2e_mh_ws_009` | 15 | T3 | `reasoning` | How do witch familiar abilities that add focus utility or spell delivery change the way a witch can cast hexes or spells, and what class features or feats limit or expand that usage? | Explain how familiar-based support changes hex or spell delivery and focus management. | Likely `multi_anchor`; witch core familiar anchor plus feat or familiar-ability anchors. | `structural_expansion`, `typed_closure_later` |
| `pf2e_mh_ws_010` | 16 | T3 | `reasoning` | What limits does Player Core place on casting spells underwater, especially spells with verbal components, and what feats, spells, or abilities mitigate those limits? | Connect underwater breathing or speaking limits to spell component requirements and mitigation options. | Likely `multi_anchor`; environment rule anchor plus component rule anchor plus mitigation anchors. | `rewrite`, `reasoning_chain` |
| `pf2e_mh_ws_011` | 17 | T3 | `reasoning` | If a ranger gains Double Slice through multiclassing, how do Twin Takedown and Double Slice interact in the same turn, and how does hunted prey affect the damage calculation? | Explain same-turn compatibility, action sequencing, and whether hunted-prey benefits apply across both feats. | Likely `multi_anchor`; multiclass access plus both feat texts plus hunted-prey language. | `reasoning_chain`, `rerank_sensitive` |
| `pf2e_mh_ws_012` | 18 | T2 | `reasoning` | How do Sneak Attack, Dread Striker, frightened, and off-guard interact when a rogue attacks a frightened enemy? | Explain how frightened can create off-guard access through Dread Striker and how Sneak Attack then applies. | Likely `multi_anchor`; Sneak Attack, Dread Striker, frightened, and off-guard anchors. | `typed_closure_later` |
| `pf2e_mh_ws_013` | 19 | T3 | `reasoning` | While in Disruptive Stance, which concentrate actions or spells can a fighter interfere with using Reactive Strike, and what determines whether the action is actually disrupted? | Explain triggering actions, attack resolution, and disruption outcome in the spell-facing case. | Likely `multi_anchor`; stance text plus Reactive Strike plus spell/concentrate context. | `typed_closure_later`, `rerank_sensitive` |
| `pf2e_mh_ws_014` | 22 | T2 | `lookup` | Which divine or primal spells in Player Core can remove poison or the poisoned condition, and how do their rank, casting time, and secondary effects differ? | Enumerate poison-removal spells and compare rank, cast time, and bonus effects. | Likely `multi_anchor`; spell-list anchors plus spell-text anchors. | `rewrite`, `structural_expansion` |
| `pf2e_mh_ws_015` | 23 | T2 | `reasoning` | How do Aggressive Block and Shield Warden change the use of Shield Block, and what differs about their tactical outcome when a shield is raised? | Compare the two feats in terms of trigger relationship to Shield Block and resulting ally or enemy outcome. | Likely `multi_anchor`; feat texts plus Shield Block anchor. | `rerank_sensitive` |
| `pf2e_mh_ws_016` | 24 | T2 | `lookup` | Which backgrounds in Player Core grant Warfare Lore, and how does starting with Warfare Lore interact with the fighter's level-1 skill training choices? | Enumerate Warfare Lore backgrounds and explain how that changes the fighter's initial training flexibility. | Likely `multi_anchor`; background anchors plus fighter skill-training anchor. | `structural_expansion` |
| `pf2e_mh_ws_017` | 25 | T3 | `reasoning` | How do the ranger's Warden Spells progression and the druid's primal spellcasting progression differ between levels 1 and 5, including spell access, focus or spell-slot progression, and multiclass implications? | Compare early progression shape, spell access model, and multiclass consequences. | Likely `multi_anchor`; ranger progression anchors plus druid spellcasting anchors. | `reasoning_chain`, `structural_expansion` |
| `pf2e_mh_ws_018` | 27 | T2 | `reasoning` | Which witch hexes or focus spells in Player Core penalize Armor Class or saving throws, how do they scale, and how do they combine with conditions such as frightened or slowed? | Enumerate defense-affecting witch options and explain scaling plus interaction with common conditions. | Likely `multi_anchor`; several spell anchors plus condition anchors. | `rewrite`, `rerank_sensitive` |
| `pf2e_mh_ws_019` | 28 | T3 | `reasoning` | How does a champion's proficiency with a deity's favored weapon interact with the fighter's weapon proficiency progression for a multiclass character? | Explain which class sets the operative proficiency rank over time and whether favored-weapon benefits change the schedule. | Likely `multi_anchor`; champion proficiency anchor plus fighter progression anchor plus multiclass context. | `reasoning_chain` |
| `pf2e_mh_ws_020` | 30 | T2 | `reasoning` | What paths in Player Core let a rogue gain arcane spellcasting, what are the prerequisites for each path, and when does the rogue first gain access to spells? | Compare the rogue's arcane-access paths by prerequisite, level gate, and initial spell access. | Likely `multi_anchor`; rogue class-option anchor plus spellcasting-access anchors. | `structural_expansion`, `reasoning_chain` |

## Queries Deferred To Later Split Passes

These prompts are useful, but they should not go directly into the first working-set artifact without refactoring.

| Seed | Why not now | Better future shape |
|---|---|---|
| 1 | Eight-ancestry inventory is broad and table-heavy. | Split into ancestry-reaction slices or a curated 4-ancestry pilot. |
| 6 | Cross-source darkvision inventory is broad and prone to weak gold sizing. | Split by source family such as ancestry options vs feat upgrades. |
| 7 | Inventory and stacking behavior are two different retrieval tasks. | Keep only stacking now; later add a bard composition inventory benchmark. |
| 8 | Eight-class inventory produces large answer sets and diffuse gold. | Split by action family or by class family. |
| 9 | All stances across classes is too wide for interpretable misses. | Split by class group or retain only high-signal stance interactions. |
| 21 | Level-1 reaction feat inventory across all classes is broad and repetitive. | Split by martial vs caster classes or by trigger family. |
| 26 | Initiative modifiers are spread across many sources and bonus types. | Split bonuses, rerolls, and preparation effects into separate entries. |
| 29 | Level-6 mobility feats span many movement modes and class tables. | Split by movement mode such as flight, climb, swim, or burrow. |

## Deferred Prompts

| Seed | Reason for defer |
|---|---|
| 2 | The feat inventory plus ancestry and class comparison request is too broad for the first multihop working set and is not the best early diagnostic slice. |
| 20 | Quick Alchemy is likely a corpus mismatch for Player Core and should be revived only after verifying corpus coverage. |

## Pilot Slice Recommendation

Use a 10-query pilot before grounding the full retained set.

| Pilot ID | Why it belongs in the pilot |
|---|---|
| `pf2e_mh_ws_001` | Spell-list filtering plus spell-text comparison; good rewrite and rerank stress test. |
| `pf2e_mh_ws_002` | Class-local structural expansion over a feat chain. |
| `pf2e_mh_ws_003` | Clean two-anchor cross-class comparison with MAP semantics. |
| `pf2e_mh_ws_005` | High-signal feat plus reaction interaction. |
| `pf2e_mh_ws_007` | Focused answer-assembly and stacking judgment query. |
| `pf2e_mh_ws_009` | Class feature plus familiar-ability interaction with likely dispersed evidence. |
| `pf2e_mh_ws_010` | Environment rule plus spellcasting component interaction. |
| `pf2e_mh_ws_011` | Multiclass compatibility and same-turn sequencing. |
| `pf2e_mh_ws_016` | Low-noise background plus class-training interaction; useful control case. |
| `pf2e_mh_ws_019` | Cross-class proficiency progression and multiclass override reasoning. |

This pilot intentionally spans:

- spell-list plus spell-text retrieval
- class feat neighborhoods
- cross-class feat comparison
- reaction and stance interaction
- environment plus core-rules interaction
- multiclass legality
- progression comparison
- a lower-noise control query that is still multihop

## Evidence Strategy Before Grounding

Use the following evidence discipline while grounding the retained set:

1. Prefer the smallest operational `required_gold` set that makes the question answerable.
2. Use `supporting_gold` for glossary support, trait definitions, and nearby clarifying text that improves completeness but is not strictly answer-critical.
3. For the multihop working set, allow `required_gold` to rise above the ratified-core limit when the question genuinely needs it, but treat `1-3` as the target band and `4-5` as exceptional.
4. Mark `evidence_scope` as `multi_anchor` unless grounding proves the answer is operationally recoverable from one anchor plus optional support.
5. If a query explodes beyond interpretable gold during grounding, split it instead of normalizing an oversized required set.

Expected gold patterns by family:

- Spell inventory queries: spell-list anchor plus 2-5 spell description anchors.
- Feat comparison queries: one anchor per feat plus one supporting glossary or MAP anchor if needed.
- Rules-interaction queries: one subsystem anchor per rule family, such as stance plus reaction plus condition.
- Progression queries: one anchor per class progression table or class feature progression block.

## Grounding Plan

Ground the pilot first, then expand.

### Stage 1

Ground the 10 pilot queries against the active PF2E corpus contract.

### Stage 2

For each pilot query:

- resolve durable `gold_locations`
- keep `required_gold` minimal
- capture `required_gold_rationale`
- note whether the query stayed interpretable at its original scope

### Stage 3

Run the pilot across the normal evaluation surfaces:

- `full_working_set`
- `clean_subset`

Use the pilot results to identify which retained queries are:

- worth promoting into the full multihop working set
- worth splitting before grounding
- good candidates for a later ratified subset

### Stage 4

Only after the pilot stabilizes:

- ground the rest of the retained working-set catalog
- generate the benchmark projection for the active corpus contract
- consider mining a smaller ratified subset from the cleanest, lowest-scatter entries

## Relationship To The Bounded Multihop Memo

This benchmark is designed to support the architecture in `RulesIngestion/Docs/Design/bounded_multihop_retrieval_design_memo.md`.

It should help distinguish:

- questions where gold never enters the candidate pool
- questions where gold is present but ranked too low
- questions where retrieval is adequate but answer synthesis or citation assembly is incomplete

That is why the retained query set emphasizes focused rules interactions and bounded comparisons instead of very large inventories.
