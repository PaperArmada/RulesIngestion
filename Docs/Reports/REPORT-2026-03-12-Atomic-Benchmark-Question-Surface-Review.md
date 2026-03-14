# REPORT-2026-03-12 Atomic Benchmark Question Surface Review

## Atomic Benchmark Question Surface Review: Revisions, Hygiene, and Expansion

## 2026-03-13 Addendum: Hybrid Backstop Parity Experiment Outcome

### Why this addendum exists

After resolver hardening, remaining PF2E parity misses at `min_chars=225` were concentrated in:
- `pf2e_001_21`
- `pf2e_001_48`

Working hypothesis was that these were now ranking-depth misses (not anchor-mapping misses), and that hybrid CC fusion might recover them.

### Experiment executed

- **Control run:** `pf2e_mpnet_dense_baseline_20260313_164521`
- **Treatment run:** `pf2e_mpnet_hybrid_baseline_20260313_215228`
- **Command (treatment):**
  - `uv run python -m retrieval_lab.run_experiment --config "retrieval_lab/experiments/hybrid/pf2e_mpnet_hybrid_baseline.yaml" --batches "out/retrieval_lab/phase3_temp_benchmarks/pathfinder2e_player_core_50q_benchmark.min225.json" --min-chars 225 --merge-chunks --merge-max-chars 2000`
- **Hybrid config intent:** CC fusion (`minmax`, `lambda=0.7`, `bm25_budget=100`, `dense_budget=100`) as previously validated in parity work.

### Results (control vs treatment)

| Metric | Control | Treatment | Delta |
|---|---:|---:|---:|
| required_full_set_hit@10 | 0.90 | 0.90 | +0.00 |
| required_recall@10 | 0.92 | 0.93 | +0.01 |

### Target query outcomes

| Query | Full-set@10 (C→T) | Recall@10 (C→T) | Outcome |
|---|---|---|---|
| `pf2e_001_02` | False → False | 0.0 → 0.0 | unchanged |
| `pf2e_001_21` | False → False | 0.5 → 0.5 | unchanged |
| `pf2e_001_23` | True → True | 1.0 → 1.0 | unchanged |
| `pf2e_001_48` | False → False | 0.5 → 0.5 | unchanged |

### Failure-set delta (required_full_set@10)

- **Control fails (5):** `pf2e_001_02`, `pf2e_001_21`, `pf2e_001_27`, `pf2e_001_40`, `pf2e_001_48`
- **Treatment fails (5):** `pf2e_001_02`, `pf2e_001_21`, `pf2e_001_27`, `pf2e_001_42`, `pf2e_001_48`
- **Recovered in treatment:** `pf2e_001_40`
- **New regression in treatment:** `pf2e_001_42`

### Pre-registered criteria verdict

- Primary #1 (global required full-set@10 improves): **Fail** (flat)
- Primary #2 (`pf2e_001_21` or `pf2e_001_48` flips): **Fail**
- Safety/honesty constraints: **Pass** (command-exact run, no contract bypass flag, resolver unchanged, anchor resolution all-resolved)

### Decision-grade conclusion

For this specific parity gap, **reject hybrid backstop as the next step**.  
The treatment improved required recall slightly but did not improve composition-complete success at `k=10`, and did not recover the two target misses.

### Implication for next design agent

Treat remaining parity failures as **retrieval ranking quality under fixed required sets**, but not obviously solvable by generic hybrid fusion in current configuration.

Prioritized next-step options:
1. **Query-shape interventions** for failing items (`pf2e_001_21`, `pf2e_001_48`) via controlled wording variants and lexical trigger audits.
2. **Targeted rerank stage** (cross-encoder or calibrated stage-2) on dense candidates for definition-like and condition-like queries.
3. **Per-query failure bucket deep dive** for new tradeoff (`pf2e_001_40` recovered vs `pf2e_001_42` regressed) to identify ranking instability patterns.

## Framing of what this benchmark is actually measuring

The current atomic template is attempting a hard but valuable objective: use one shared question surface to retrieve the right rule anchor across four corpora with different terminology, editorial patterns, and procedural assumptions.

The evaluated books are:
- Player's Handbook (D&D 5e 2024)
- Swords and Wizardry Complete Revised
- Shadowrun 4th Edition 20th Anniversary Core Rulebook
- Starfinder Player Core

Because the evidence source is dense retrieval over embeddings (`all-mpnet-base-v2`), each question string does more than ask a natural-language question. It shapes the retrieval distribution. Parentheticals, appositions, and loaded system nouns can reweight similarity neighborhoods in ways that materially change top-k behavior.

Metric interpretation also determines what should be revised versus annotated:
- **MRR** emphasizes whether a relevant anchor appears early.
- **nDCG** is better when multiple relevant chunks exist and ranking quality across those chunks matters.

That distinction explains many observed misses: some failures are not question-surface defects, but completeness demands caused by large `required_gold` sets that exceed realistic dense retrieval behavior at practical k values.

## Separating wording defects from benchmark defects

The strongest conclusion is that failure modes split into three distinct categories, each with a different fix:

1. **Index/candidate-set defects** (`gold_not_in_candidates`)
   - Evaluation-invalidating for wording decisions.
   - If gold is absent from candidates, retrieval quality is not being measured.

2. **Annotation scope defects** (`required_gold_large`, `rank_of_last_required=null`)
   - Inflate scatter by requiring dispersed anchors.
   - Often tests citation-gathering completeness, not atomic rule findability.

3. **Wording defects**
   - Show up as systematic rank depression and cross-corpus concept drift.
   - Most visible where OSR-specific nouns are used as if they were universal primitives.

## What to revise and what to remove or reclassify

### Items to revise now due to structural non-universality as written

#### `s12_morale_and_reaction_rolls`

The concept (NPC disposition and willingness to continue fighting) is broadly meaningful, but explicit procedural names ("reaction rolls", "morale checks") are not universal in player-facing corpora.

Recommendation:
- Keep as universal concept.
- Remove subsystem-loaded nouns.
- Mark `refusal_acceptable` where the corpus delegates this to GM judgment.

Stronger atomic handling options:
- Keep one revised question, or
- Split into two questions:
  - NPC first-contact attitude
  - NPC break-point under adversity

#### `s14_exploration_time_and_encounter_checks`

"Dungeon exploration" and "wandering monsters" are not stable cross-system anchors.

Recommendation:
- Rewrite to target noncombat time progression and time-based interruptions in system-neutral language.
- Consider separating timekeeping from encounter cadence if you want stricter atomicity.

### Items to revise now because they are compound and induce unavoidable scatter

#### `u03_time_progression_model`

The current wording bundles:
- time units, and
- transition causality.

These often live in separate sections, producing multi-chunk required sets.

Recommendation:
- Revise to "named units of time" plus "how each begins/ends."

#### `s06_spell_preparation_reprepare_and_interruption`

The current wording bundles:
- resource refresh cadence, and
- interruption while casting.

These are separate mechanics in many systems.

Recommendation:
- Use a universal resource-recovery framing.
- If interruption matters, split it into its own question (likely module-level, not core).

### Items that should move from universal core to module

Evidence supports moving the following into optional modules rather than endlessly rewriting:
- Procedural exploration cadence (for example, explicit wandering checks/dungeon turns)
- Explicit morale/reaction subsystems

This preserves core universality while still supporting system-family depth.

## Hygiene and annotation fixes that improve signal more than wording tweaks

### 1) Keep `required_gold` minimal for definition-like queries

Adopt a two-tier grounding policy:
- **required_gold**: smallest anchor set that answers the question (usually 1, occasionally 2).
- **supporting_gold**: adjacent citations that improve completeness but are not required for core answerability.

Apply to known scatter-heavy items:
- `u04_player_actions_in_combat` (PHB5e, SWCR)
- `s05_combat_sequence_group_initiative` (SWCR)
- `s13_encumbrance_and_movement` (PHB5e, SWCR)
- `u02_uncertainty_core_mechanic` (SR4, "BUYING HITS" likely supporting)

### 2) Add a hard preflight gate for required-gold indexability

Before evaluation:
1. Confirm each required gold chunk exists after extraction/chunking.
2. Confirm each required gold chunk has embeddings and is in ANN index.
3. Confirm candidate generation can retrieve each required chunk in principle (self-retrieval sanity query).

This prevents treating data plumbing failures as wording failures.

## Expanding the question surface without destabilizing the template

The three proposed additions are directionally strong because they map to broad, low-ambiguity, chapter-level anchors:
- `atomic_u06_advancement_and_growth`
- `atomic_s17_damage_and_wound_application`
- `atomic_u07_character_creation_basics`

Expansion rubric (recommended):
- Single neighborhood likely to answer question
- System-neutral trigger phrase
- Low dependency on GM-only material
- Annotatable with 1-2 required anchors

Two additional candidate questions that fit this rubric:

### Candidate: Recovery and rest

- **ID:** `atomic_s18_recovery_and_rest`
- **Wording:** "How do characters regain lost health or remove injuries outside of the dying/death state (rest, medicine, magic, repair), and what limits apply?"
- **Why:** Captures the between-fights recovery loop, a major cross-system differentiator.

### Candidate: Difficulty and modifiers

- **ID:** `atomic_u08_difficulty_and_modifiers`
- **Wording:** "How does the game set task difficulty and apply situational modifiers (bonuses/penalties, advantage/disadvantage, edge, dice added/removed)?"
- **Why:** Complements `u02` by probing practical resolution complexity.

## Validation protocol to confirm revisions worked

1. **Repair Starfinder substrate first**
   - Rebuild full corpus index.
   - Fix missing annotations.
   - Treat current substrate failures as non-blocking for wording conclusions.

2. **Run wording-only A/B**
   - Hold embedder, chunking, and candidate parameters constant.
   - Change only revised prompts (`s12`, `s14`, `u03`, `s06`, optionally `u05`).

3. **Use two success criteria**
   - **Anchor success:** at least one required gold in top-k.
   - **Completeness success:** if needed, evaluate via nDCG/recall against supporting gold rather than required-gold explosion.

4. **Carry a sparse baseline alongside dense**
   - Use BM25 (or equivalent) to detect wording shifts that become overly keyword-driven or overly semantic.

## Strategic decision to lock before next template version

Settle one policy question explicitly:

**Does "universal" mean:**
- every system has a mechanized procedure for the concept, or
- the concept exists even when resolution is partly discretionary?

If using the second interpretation, apply `refusal_acceptable` consistently. That keeps the benchmark focused on what matters:
- retrieve the rule when codified,
- and correctly surface absence-of-explicit-rule when not codified.
