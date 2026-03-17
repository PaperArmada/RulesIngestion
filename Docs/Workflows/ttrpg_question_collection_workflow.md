# TTRPG Rule-Question Collection Workflow

## Purpose

This document defines a repeatable workflow for finding, drafting, curating, and maintaining a high-quality, diverse question set for TTRPG rule systems. It is designed for retrieval evaluation work rather than general QA generation.

The workflow assumes the current Stage A → Stage B → Retrieval Lab architecture: Stage A reconstructs authored prose, Stage B emits EvidenceUnits as the admissible evidence layer, and Retrieval Lab evaluates discoverability of that evidence under different retrieval regimes. Retrieval Lab is comparative and retrieval-focused; it is not itself a correctness evaluator. fileciteturn2file1 fileciteturn2file2

## Core principles

1. **Questions are built for evidence retrieval, not vibes.**
   Every benchmark question should be answerable from authored rule text and grounded to one or more EvidenceUnits, because EvidenceUnits are the canonical admissible layer and gold sets are sets of EvidenceUnit IDs. fileciteturn2file0

2. **The benchmark must be diverse on purpose.**
   Diversity does not happen automatically. The collector must deliberately sample across rule types, wording styles, answer shapes, and reasoning depth.

3. **The benchmark should stress retrieval, not hidden world knowledge.**
   Questions should be answerable from the rules corpus itself, not from community convention, designer intent, forum rulings, or prior edition memory.

4. **The benchmark should separate retrieval difficulty from answer difficulty.**
   Retrieval Lab measures discoverability of evidence, so the benchmark should clearly encode whether a failure is due to missing gold, low ranking, or downstream grounding/answer issues. fileciteturn2file2

5. **Admissible evidence and retrieval aids must stay distinct.**
   Clause families, context windows, graph expansions, and similar aids may help retrieval, but the gold and citations must resolve back to EvidenceUnits. fileciteturn2file0 fileciteturn2file1

---

## What counts as a good benchmark question

A good question:

- corresponds to a real user information need,
- has a reasonably bounded answer,
- is answerable from the corpus,
- can be grounded to one or more specific EvidenceUnits,
- exposes something meaningful about retrieval quality,
- is not trivial duplication of many nearby questions.

A bad question usually has one of these smells:

- depends on table culture or GM preference rather than text,
- is so broad that half the book is relevant,
- is really a character-building advice question with no stable gold,
- encodes edition knowledge not stated in the book,
- is paraphrased so loosely that it becomes ambiguous,
- differs from another question only by a noun swap.

---

## Target coverage model

Every question set should be intentionally balanced across several axes.

### 1. Rule object type

Sample across:

- conditions,
- actions,
- reactions,
- movement,
- combat procedures,
- spell rules,
- class features,
- feats,
- equipment,
- weapon properties,
- status effects,
- hazards,
- rests/recovery,
- vision/light/stealth,
- tables and list-driven content,
- exceptions and overrides,
- glossary entries.

### 2. Retrieval shape

Sample across:

- **single-anchor lookup**: one primary unit answers the question,
- **local multi-unit**: answer needs adjacent or same-section units,
- **cross-section compositional**: answer requires rules from different parts of the book,
- **exception/base pairing**: base rule plus exception or modifier,
- **table lookup**: answer depends on a table row + header context,
- **definition-to-procedure**: glossary entry plus procedure section,
- **alias/synonym phrasing**: user wording differs from book wording.

### 3. User phrasing style

Sample across:

- exact rulebook language,
- plain-English paraphrase,
- player table language,
- mistaken-but-plausible wording,
- compressed search-query style,
- long natural question.

### 4. Answer shape

Sample across:

- boolean,
- numeric,
- enumerated list,
- conditional rule,
- ordered procedure,
- compare/contrast,
- “what happens if…” consequence chain.

### 5. Difficulty tier

Use and maintain explicit tiers. The project glossary already treats T1/T2/T3 as a real distinction, with T1 usually being a single primary unit and T2/T3 being more compositional. fileciteturn1file0

Recommended operationalization:

- **T1**: one gold unit is primary; at most one optional support unit.
- **T2**: two or more units are genuinely needed, but within a coherent local region or obvious pairing.
- **T3**: multi-hop, cross-section, or exception-heavy composition.

Do not inflate the benchmark by labeling soft T1s as T2s just because supporting context exists.

---

## The workflow

## Phase 0 — Prepare the corpus

Before collecting questions, confirm the corpus is stable enough to benchmark:

1. Stage A output is structurally deterministic.
2. Stage B output is byte-stable under fixed sort keys.
3. EvidenceUnits are the canonical admissible substrate.
4. The current retrieval config and output paths are known.

This matters because question quality cannot be separated from corpus stability. Stage B defines admissible units with stable identity and provenance, and Retrieval Lab expects to evaluate discoverability over that substrate. fileciteturn2file1 fileciteturn1file14 fileciteturn2file2

### Phase 0 checklist

- corpus version pinned,
- document_id recorded,
- substrate path recorded,
- config family known,
- current baseline run identified,
- question file versioned separately from corpus version.

---

## Phase 1 — Map the search space before drafting questions

Do not begin by free-associating cool questions. First map where questions can come from.

Build a **coverage map** of the rulebook with at least these buckets:

- chapter/section,
- rule object type,
- procedural vs declarative text,
- tables/lists,
- glossary-heavy zones,
- exception-rich zones,
- player-facing high-frequency lookups,
- obscure but mechanically important zones.

### Recommended extraction passes

1. **Table of contents pass**
   Build a simple inventory of chapters and subheads.

2. **Glossary pass**
   Mark entries that likely support short exact-match lookups.

3. **Procedure pass**
   Mark stepwise procedures like combat flow, action resolution, spellcasting rules, stealth, and movement.

4. **Exception pass**
   Mark places with words like “unless,” “instead,” “except,” “can’t,” “only if,” “when,” “while,” and “if… then…”.

5. **Table/list pass**
   Mark tables, bullet lists, and compact enumerations, since these often fail under weak chunking and are useful retrieval stressors. Keeping complete tables and lists intact is already part of the Stage A/Stage B design logic. fileciteturn1file3 fileciteturn1file14

6. **Player-frequency pass**
   Mark content players actually ask about at the table.

Output of Phase 1: a coverage sheet that tells you where questions should come from before you write any.

---

## Phase 2 — Mine candidate questions from multiple lenses

Use multiple collection lenses, because each one produces different failure modes and different value.

### Lens A — Direct player lookup questions

These are the most natural benchmark items.

Prompts for mining:

- “What would a player ask at the table?”
- “What would a DM need in under ten seconds?”
- “What would someone search for after only half-remembering the rule?”

Examples of shapes:

- “Can I do X while Y?”
- “What happens when Z?”
- “How much movement does this cost?”
- “Does this provoke an opportunity attack?”

### Lens B — Book-structured extraction

Walk each section and ask:

- what is the section’s main retrieval target,
- what is the likely confusion point,
- what nearby text would be easy to miss,
- what exact term would a lexical search catch,
- what paraphrase would require semantic retrieval.

This systematically prevents over-sampling flashy rules and under-sampling boring but critical procedures.

### Lens C — Exception and modifier mining

These are especially valuable because they stress compositional retrieval.

Mine questions from:

- base rule + exception,
- default rule + special case,
- condition + override,
- action + reaction interaction,
- movement + terrain + condition interactions,
- spell + target/state constraints.

These questions are also where pairing-style retrieval logic may help, so they should be tagged explicitly for later analysis rather than mixed invisibly into the set. Pairing is still experimental and must be judged with instrumentation, not just headline metrics. fileciteturn1file4

### Lens D — Terminology and synonym mining

Good user questions often do not use book language.

For each important concept, collect:

- exact canonical term,
- common paraphrases,
- mistaken near-synonyms,
- slang/table phrasing,
- abbreviation or shorthand.

The design critique already notes that TTRPG retrieval is unusually sensitive to the split between natural-language meaning and mechanical meaning, and that lexical precision matters for terms, acronyms, and exact strings. fileciteturn1file3 fileciteturn1file10

### Lens E — Table and list mining

For every important table or list, draft:

- direct lookup questions,
- compare-two-entry questions,
- threshold questions,
- row + note interaction questions,
- “which of these…” style questions.

### Lens F — Failure-driven mining

Use retrieval reports and manual play experience to mine questions from observed misses:

- gold not in candidates,
- gold in candidates but low rank,
- answer failures after apparently decent retrieval,
- rules users repeatedly ask you or each other.

Retrieval Lab already distinguishes these failure buckets, so the benchmark workflow should lean on that taxonomy instead of inventing new ones ad hoc. fileciteturn2file2

Output of Phase 2: a large, messy candidate pool.

---

## Phase 3 — Normalize each candidate into a benchmark-ready record

Each candidate question should be normalized into a structured record before golding.

### Required fields

```yaml
query_id: <stable_id>
question: <user-facing wording>
book: <document_id>
section_hint: <human note>
question_type: <lookup|procedure|exception|table|compositional|etc>
tier: <T1|T2|T3>
expected_answer_shape: <boolean|numeric|list|conditional|procedure|compare>
source_strategy: <player_lookup|section_walk|exception_mining|failure_mining|etc>
notes: <optional human comments>
status: <draft|reviewed|grounded|rejected>
```

### Recommended optional fields

```yaml
aliases:
  - <alternate phrasing>
likely_terms:
  - <exact lexical hooks>
likely_sections:
  - <chapter or heading guesses>
interaction_tags:
  - <movement>
  - <condition>
  - <spellcasting>
answerability_risk: <low|medium|high>
```

Do not gold yet. Normalize first.

---

## Phase 4 — Apply the first curation filter

Before grounding, reject low-value candidates aggressively.

### Reject if the question is:

- too broad to have bounded evidence,
- better framed as strategy/opinion than rules lookup,
- answerable only through lore outside the chosen corpus,
- duplicative of an existing item without meaningful retrieval difference,
- reliant on unclear pronouns or hidden assumptions,
- dependent on edition bleed,
- basically the same as the section heading.

### Merge if the difference is only:

- surface wording with no retrieval consequence,
- singular/plural swap,
- exact synonym swap,
- cosmetic actor swap.

### Preserve separately if the difference affects retrieval:

- exact term vs paraphrase,
- player slang vs book language,
- direct rule vs exception framing,
- same concept but different reasoning depth,
- same answer but table vs prose access path.

Output of Phase 4: a smaller curated draft pool.

---

## Phase 5 — Ground to EvidenceUnits

This is the most important discipline.

Stage B EvidenceUnits are the only canonical admissible evidence layer, and gold sets in Retrieval Lab are sets of EvidenceUnit IDs. The question workflow must therefore ground every retained question to one or more EvidenceUnits rather than to vibes, headings, or freeform summaries. fileciteturn2file0

### Golding process

For each candidate:

1. Read the question carefully.
2. Find the minimally sufficient EvidenceUnit set.
3. Separate **required gold** from **supportive but optional** context.
4. Record the gold unit IDs.
5. Write a short expected answer summary.
6. Record why each gold unit is needed.

### Golding rules

- Prefer the **smallest sufficient** gold set.
- Do not include adjacent units just because they are nearby.
- Include multiple gold units only if the answer genuinely requires them.
- If one unit states the rule and another only restates it, gold the authoritative one.
- If a table row is needed, ensure the gold covers both row content and header context as represented in the actual EvidenceUnit.
- If an exception modifies a base rule, gold both only when both are actually needed to answer correctly.

### Record format

```yaml
gold_unit_ids:
  - <unit_id_1>
  - <unit_id_2>
required_gold_count: 2
expected_answer_summary: <short grounded summary>
golding_notes:
  - unit <id_1> gives the base rule
  - unit <id_2> gives the exception that changes the outcome
```

If gold cannot be stated cleanly, the question is not ready.

---

## Phase 6 — Tier and classify after golding

Do not assign final tier blindly before grounding. The gold often reveals the real difficulty.

### Practical tiering rubric

**T1**
- one primary EvidenceUnit,
- maybe one optional support unit,
- answer is mostly local and direct.

**T2**
- two or more required EvidenceUnits,
- usually same chapter, same topic zone, or obvious paired rule,
- answer needs composition but not major search breadth.

**T3**
- cross-chapter or cross-subsystem,
- exception-heavy,
- relies on joining distant concepts,
- likely to expose structural retrieval weaknesses.

This matters because Retrieval Lab explicitly tracks T1 and T2 metrics, including a no-regressions policy for T1 in key configs. fileciteturn2file2

---

## Phase 7 — Diversity audit before admission

Once a batch is drafted and grounded, run a diversity audit. The goal is not just “some variety”; it is deliberate spread.

### Audit dimensions

Count questions by:

- chapter/section,
- rule object type,
- answer shape,
- tier,
- direct vs compositional,
- exact term vs paraphrase,
- prose vs table/list dependence,
- exception/modifier dependence,
- player-frequency importance.

### Warning signs

- too many condition questions,
- too many glossary lookups,
- too many combat-only items,
- almost no table-driven items,
- almost no T3s,
- almost all questions using book wording,
- almost no negative/exception forms,
- lots of questions from the same few pages.

### Batch targets

For a general-purpose benchmark batch, aim for something like:

- 40–50% T1,
- 35–45% T2,
- 10–20% T3,
- at least 15–20% table/list or tightly structured content,
- at least 20–30% paraphrase-heavy wording,
- at least 15–20% exception/override questions.

These are heuristics, not laws, but the point is to stop the benchmark from collapsing into one style.

---

## Phase 8 — Red-team the question wording

Before finalizing, test each question for ambiguity and retrieval realism.

### Red-team prompts

Ask:

- Would a human table user plausibly ask this?
- Is the wording too polished compared with real user phrasing?
- Does the question accidentally reveal the answer term?
- Does it smuggle in the exact heading name?
- Is there a more natural phrasing that would still target the same gold?
- Could two different readers reasonably ground it differently?

### Recommended practice

For high-value questions, keep two versions:

- a natural user wording,
- a stricter internal paraphrase note for curators.

Only the user-facing wording should be used in evaluation unless you are explicitly running paraphrase studies.

---

## Phase 9 — Validate the batch against retrieval goals

Because Retrieval Lab is comparative and discoverability-focused, a question batch should be validated for the kinds of retrieval signal it can produce. fileciteturn2file2

### A good batch supports analysis of:

- lexical retrieval strengths,
- semantic retrieval strengths,
- chunk boundary failures,
- table/list handling,
- exception/base recall,
- local context expansion usefulness,
- dual-list projection effects,
- experimental pairing effects,
- tier-specific regressions.

The design critique argues that strong TTRPG retrieval needs more than plain vector search: lexical matching, structure-aware chunking, and in some cases richer graph or projection approaches matter because exact mechanical wording and cross-rule relationships matter. That is precisely why the benchmark should include questions that stress those dimensions instead of only easy semantic paraphrases. fileciteturn1file3 fileciteturn1file10

---

## Phase 10 — Maintain the benchmark as a living asset

A benchmark is not a one-time dump.

### On every major revision

- remove or rewrite ambiguous questions,
- re-ground any item whose gold changed due to corpus updates,
- add questions from newly discovered failure buckets,
- preserve IDs when meaning is unchanged,
- version the benchmark explicitly.

### Trigger events for review

- corpus re-extraction,
- changed Stage B segmentation,
- new retrieval projection type,
- new rulebook edition,
- new observed user confusion clusters,
- high disagreement among curators,
- repeated failure bucket concentration in a single category.

Because determinism and stable substrates matter across Stage A, Stage B, and Retrieval Lab, benchmark maintenance should always track the corpus version and retrieval config context it was designed against. fileciteturn2file1 fileciteturn2file2

---

## Recommended curator rubric

Score each candidate 1–5 on these axes:

### 1. Answerability
Can this be answered from the chosen corpus alone?

### 2. Groundability
Can I point to a minimal EvidenceUnit set without hand-waving?

### 3. Retrieval value
Will this tell us something real if retrieval succeeds or fails?

### 4. User realism
Does this sound like an actual table/user question?

### 5. Diversity contribution
Does this add a needed shape to the set, or is it redundant?

### 6. Stability
Is it unlikely to become invalid due to minor segmentation or wording shifts?

### Suggested acceptance rule

Keep candidates with:

- no score below 3,
- average of 4 or higher,
- or lower average only if they fill an intentional diversity gap.

---

## Question archetypes worth preserving

Keep explicit slots for each of these archetypes.

### Exact-term lookup
Tests lexical hooks and glossary discoverability.

### Paraphrase lookup
Tests semantic retrieval without exact text overlap.

### Procedure question
Tests retrieval of ordered steps and complete local context.

### Table-row question
Tests structured data retrieval and header-row preservation.

### Exception question
Tests base rule plus override.

### Negative constraint question
“Can’t,” “cannot,” “only if,” “unless,” “while.”

### Interaction question
Condition + action, spell + movement, terrain + speed, etc.

### Boundary question
A question likely to fail if chunking splits the relevant text badly.

### Misremembered-user question
Plausible but imperfect language from an actual player perspective.

### Deep composition question
A small number of carefully chosen T3s that expose retrieval architecture limits.

---

## Anti-patterns to avoid

### 1. Advice disguised as rule lookup
“Best feat for X” is usually not a retrieval benchmark question.

### 2. Entire-chapter questions
“What should I know about stealth?” is too broad.

### 3. Over-literal synthetic phrasing
If the question sounds like it was generated by a benchmark bot, it often is less useful.

### 4. Hidden answer leakage
If the query includes the exact rare heading and key exception phrase, retrieval may look better than it is.

### 5. Gold inflation
Adding too many “just in case” gold units makes evaluation muddy.

### 6. Near-duplicate inflation
Ten small variants of the same opportunity attack question are not ten useful questions.

### 7. Unsupported compositional fantasy
Do not invent multi-hop questions that the corpus does not really support.

---

## Minimal operating procedure for a new book

When starting a new TTRPG corpus, follow this sequence.

1. Build the section coverage map.
2. Mine 3–5x more candidates than you expect to keep.
3. Normalize every candidate into a structured record.
4. Reject weak or redundant items.
5. Ground survivors to minimal EvidenceUnit sets.
6. Assign final tier after grounding.
7. Run diversity audit and rebalance.
8. Red-team wording.
9. Freeze a versioned batch.
10. Run Retrieval Lab and inspect failure buckets.
11. Add a small follow-up batch from observed blind spots.

---

## Suggested file format for stored questions

```yaml
benchmark_id: <name>
corpus:
  document_id: <document_id>
  substrate_version: <version>
  benchmark_version: <version>
questions:
  - query_id: <id>
    question: <text>
    tier: <T1|T2|T3>
    question_type: <type>
    expected_answer_shape: <shape>
    gold_unit_ids: [<id1>, <id2>]
    expected_answer_summary: <summary>
    aliases: []
    interaction_tags: []
    source_strategy: <strategy>
    notes: <notes>
```

This keeps the benchmark explicit, inspectable, and compatible with future tooling.

---

## Short checklist for future use

### Before drafting

- corpus pinned
- coverage map built
- diversity targets chosen

### Before grounding

- candidates normalized
- duplicates merged
- low-value items removed

### Before freezing

- every kept question has gold
- tier assigned after golding
- diversity audit passed
- wording red-teamed

### After running retrieval

- inspect failure buckets
- inspect tier-specific regressions
- inspect table/list failures
- inspect exception/base misses
- feed misses back into next candidate batch

---

## Final stance

The benchmark should behave like a careful instrument, not a pile of prompts.

The real object being curated is not “questions” in the abstract. It is a disciplined interface between:

- authored rule text,
- admissible evidence units,
- retrieval architectures,
- and the concrete failure modes you want to expose.

If a question cannot be grounded cleanly, does not broaden coverage, or does not teach you something when retrieval fails, it probably does not belong in the set.
