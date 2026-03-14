# REPORT-2026-03-06-SWCR Auto-Gold Full Benchmark Audit

Scope: all 21 Swords & Wizardry queries in `swords_wizardry_autogold_manual_compare_20260306`, expanding the original flagged-case-only audit.

Working note: many manual gold IDs no longer surface cleanly in the current top-20 retrieval for this run, so adjudication is based on question alignment, benchmark answer intent, reviewer rationale, and the answer-bearing quality of the visible auto-selected chunks rather than raw overlap alone.

| query_id | classification | rationale | key disagreement |
|---|---|---|---|
| `sw_rev_u01_roles_and_authority` | `auto arguably better` | The auto set uses two direct anchors that cleanly split player authority from Referee authority and explicitly includes the Referee’s rulings/interpreting-the-rules role. That is more minimal and more answer-bearing than the current manual bundle, whose units are not visible in the current candidate set. | Auto picks the operative role-definition prose directly; manual appears broader and older-ID bound. |
| `sw_rev_u02_uncertainty_core_mechanic` | `auto arguably better` | The core of the question is the game’s default uncertainty mechanism, and the auto set makes the dice-conventions chunk the only required anchor while demoting example procedures to supporting evidence. That is more consistent with minimal-anchor hygiene than requiring multiple example procedures as mandatory gold. | Manual appears to require examples as required gold; auto treats them as supporting context around the true core anchor. |
| `sw_rev_u03_time_progression_model` | `manual better` | Auto correctly anchors turns, combat rounds, and the mass-combat exception, but it does not directly capture the standard round-to-round cadence that answers what moves play from one step to the next. The benchmark answer explicitly includes the repeating ordered combat sequence, so the fuller manual bundle is the better fit. | Auto covers time units but undercovers the ordinary progression logic of combat rounds. |
| `sw_rev_u04_player_actions_in_combat` | `needs adjudication` | Auto usefully captures movement/missiles plus alternate combat methods 2 and 3, but it seems to miss some standard-method constraints that the benchmark answer cares about, especially spell declaration timing, spell disruption, no casting in melee, and Method 1’s hold-initiative rule. The manual set likely overweights the standard sequence while auto overweights alternate methods, so both are defensible but partial. | Manual likely favors standard-phase rules; auto favors a broader but still incomplete alternate-method bundle. |
| `sw_rev_u05_what_must_be_tracked` | `needs adjudication` | This question is extremely broad and mixes tracked values, resources, positional state, clocks, and where information is recorded. Auto only anchors “record stats/equipment on a character sheet,” which is too narrow for the benchmark answer, but the manual set is not transparent enough from current evidence to prove it is the uniquely correct minimal bundle. | The disagreement is really about question scope: neither set cleanly resolves what counts as the minimal required anchor set. |
| `sw_rev_s01_rules_silent_referee_ruling` | `auto arguably better` | The auto required chunk states the entire rule almost verbatim: the rules are guidelines, there is not a rule for everything, and when in doubt the Referee should make a ruling. That is effectively the benchmark answer in one place. | Auto isolates the decisive paragraph; manual appears to distribute the same idea across less direct units. |
| `sw_rev_s02_treasure_division_procedure` | `needs adjudication` | Auto grounds the “no explicit rule, Referee adjudicates gaps” conclusion with the generic “rules are guidelines / make a ruling” text, which is plausible but indirect. Because the answer is fundamentally inferential rather than anchored in one explicit treasure-division rule, this looks like a human judgment case more than a clean win for either set. | Auto relies on a generic referee-ruling philosophy chunk; manual likely assembles a broader inferential case rather than a direct rule. |
| `sw_rev_s03_treasure_to_xp_rule` | `auto arguably better` | The auto required chunk directly states both halves of the answer in one place: XP comes from monsters and treasure, and each gold piece is worth one XP. That is a cleaner minimal anchor than any larger bundle would be. | Auto finds a single fully answer-bearing rule paragraph. |
| `sw_rev_s04_advancement_tables_where` | `auto arguably better` | The cleric advancement table is a direct, answer-bearing anchor for the claim that XP thresholds live on class-specific advancement tables rather than in a unified global table. The visible manual evidence includes at least one multi-class XP prose chunk that is less directly responsive to “where do you find the thresholds,” so the auto set is more minimal and better scoped. | Manual appears to include broader XP prose; auto picks the table itself as the operative anchor. |
| `sw_rev_s05_combat_sequence_group_initiative` | `manual better` | The auto set does a decent job anchoring initiative itself plus steps 3-6 of the round sequence, but it appears to miss the surprise check and spell-declaration steps that are part of the benchmark’s own six-step answer. Because the question explicitly asks for the basic combat sequence, the more complete manual bundle is better aligned even if the current chunk IDs have drifted. | Auto is cleaner and current-chunk aligned, but undercovers the full round sequence. |
| `sw_rev_s06_spell_preparation_reprepare_and_interruption` | `auto arguably better` | Auto selects the direct Magic-User preparation rule plus the direct interruption/lost-spell rule, which together cover the benchmark answer well. The supporting declare-spells chunk is helpful but not necessary as required gold once the interruption rule is already anchored explicitly. | Auto captures the two operative rules directly; manual seems to require a more fragmented bundle. |
| `sw_rev_s07_turn_undead_table_symbols` | `auto arguably better` | The auto required pair cleanly contrasts “T” with a numeric table result, and the supporting chunks add the 2d10 roll context plus the nearby “D” interpretation. That is well scoped to the actual question, which asks specifically about “T” versus a number. | Auto makes the T-vs-number distinction primary and leaves adjacent table semantics as support. |
| `sw_rev_s08_first_level_cleric_spells` | `needs adjudication` | Auto is very close, but it makes the class-abilities prose the required anchor and leaves the actual advancement table as supporting evidence, even though the table is the decisive evidence for “no spells at level 1; first spell at level 2.” That is plausible, but because the table seems like the stronger minimal anchor, this remains a close human-judgment case rather than a clear auto win. | The main dispute is whether the required anchor should be the prose spellcasting description or the advancement table itself. |
| `sw_rev_s09_zero_hp_death_and_healing` | `auto arguably better` | Auto uses the two exact operational chunks the benchmark answer needs: one for 0 HP / death threshold and one for natural healing. That is more complete and more direct than the current manual set visible through this run. | Auto cleanly separates death threshold from healing recovery with two direct anchors. |
| `sw_rev_s10_firing_missiles_into_melee` | `auto arguably better` | Manual and auto are an exact match here, and the selected chunk fully states the rule. Since the question is answered by one self-contained paragraph, the auto choice is plainly acceptable. | No substantive disagreement; this is effectively parity. |
| `sw_rev_s11_saving_throw_procedure` | `auto arguably better` | Auto is more complete than the visible manual set: it anchors the default d20 procedure, the multiclass rule, the monster-save rule, and the alternative category-based variant. That aligns tightly with the benchmark answer’s four-part structure. | Manual appears to miss some default and monster-side operational pieces that auto includes. |
| `sw_rev_s12_morale_and_reaction_rolls` | `manual better` | Auto strongly grounds optional morale, but its reaction-roll anchor is weaker: it points to negotiation/diplomacy context without clearly carrying the full 2d6 interpretation bands that the benchmark answer expects. For a multi-part question asking when to roll, what dice to use, and how to read results, the manual set is the better-scoped target. | Auto captures morale well but only indirectly anchors reaction procedure and result interpretation. |
| `sw_rev_s13_encumbrance_and_movement` | `auto arguably better` | Auto selects exactly the three chunks the answer needs: movement brackets, Strength carry modifier, and the weight rules for gear/treasure/coins. That is a strong minimal bundle for both the “how movement changes” and “what must be tracked” halves. | Auto directly mirrors the benchmark answer’s structure. |
| `sw_rev_s14_exploration_time_and_encounter_checks` | `auto arguably better` | Auto captures the three core facts directly: turns are 10 minutes, wandering monsters are commonly checked 1-in-6 per turn or less often, and time-consuming actions like searching consume turns and trigger checks. This is a very good minimal grounding set. | Auto covers the time unit, check cadence, and example trigger explicitly. |
| `sw_rev_s15_light_sources_duration` | `auto arguably better` | Auto picks the exact two item-duration rules the answer needs, including the hour-based time unit. There is no sign the manual bundle improves on that directness. | Auto is the clean two-chunk answer. |
| `sw_rev_s16_surprise_procedure` | `auto arguably better` | The required auto chunk already includes the full surprise procedure and the tactical advantage of pre-initiative actions, and the supporting chunks reinforce initiative and Ranger alertness. This is an efficient, answer-bearing selection. | Auto compresses the whole rule into one operative required anchor plus two small supports. |

## Bucket Summary

### `manual better`

- `sw_rev_u03_time_progression_model`
- `sw_rev_s05_combat_sequence_group_initiative`
- `sw_rev_s12_morale_and_reaction_rolls`

### `auto arguably better`

- `sw_rev_u01_roles_and_authority`
- `sw_rev_u02_uncertainty_core_mechanic`
- `sw_rev_s01_rules_silent_referee_ruling`
- `sw_rev_s03_treasure_to_xp_rule`
- `sw_rev_s04_advancement_tables_where`
- `sw_rev_s06_spell_preparation_reprepare_and_interruption`
- `sw_rev_s07_turn_undead_table_symbols`
- `sw_rev_s09_zero_hp_death_and_healing`
- `sw_rev_s10_firing_missiles_into_melee`
- `sw_rev_s11_saving_throw_procedure`
- `sw_rev_s13_encumbrance_and_movement`
- `sw_rev_s14_exploration_time_and_encounter_checks`
- `sw_rev_s15_light_sources_duration`
- `sw_rev_s16_surprise_procedure`

### `needs adjudication`

- `sw_rev_u04_player_actions_in_combat`
- `sw_rev_u05_what_must_be_tracked`
- `sw_rev_s02_treasure_division_procedure`
- `sw_rev_s08_first_level_cleric_spells`

## Net Takeaway

The poor manual-vs-auto overlap in this run looks much more like anchor drift and minimality disagreement than a blanket auto-gold failure. Across the full 21-query set, the expanded audit lands at 14 `auto arguably better`, 3 `manual better`, and 4 `needs adjudication`.
