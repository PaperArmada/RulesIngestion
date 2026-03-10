# Retrieval Benchmark Construction Guide

This guide produces a retrieval benchmark for evaluating how well the system surfaces relevant EvidenceUnits from a TTRPG rulebook corpus. It incorporates lessons from the S&W Complete Revised benchmark cycle (Feb 2026), including the skeptical analysis, min-anchor rewrite experiment, and miss diagnostics.

---

## Design Principles

### 1. A benchmark measures the retriever, not the topic

If a question requires 14 evidence units to "fully answer," the retriever will always fail full-set metrics — not because retrieval is bad, but because the question is a literature review, not a retrieval target. Every query must be a plausible retrieval task: something a user or downstream system would ask and expect 1–5 chunks to answer.

### 2. Separate suites, separate reporting

The benchmark contains three suites with fundamentally different purposes. They must never be averaged together into a single score.

| Suite | Purpose | Gold structure | Scored how |
|---|---|---|---|
| **Atomic** | Cross-ruleset comparability; compiler-oriented primitives | Narrow: 1–2 required anchors per micro-query | Standard retrieval metrics (MRR, Hit@k, ReqFSH@k) |
| **Sourced** | Corpus-specific user-facing retrieval quality | Moderate: 1–5 required, broader supporting | Standard retrieval metrics |
| **Negative** | Out-of-corpus rejection quality | No gold (answer not in corpus) | Abstention rate, false-positive penalty |

### 3. Easy questions are not useful

A benchmark that the retriever already aces provides no diagnostic signal. Questions should target areas where retrieval is non-trivial:

- Content spread across non-adjacent pages.
- Answers buried under generic headings (e.g., "How to Play").
- Terminology in the query differing from terminology in the book.
- Procedural rules interleaved with flavor text.
- Table-derived facts that require interpreting structure, not just matching keywords.

If you find yourself writing a question where the answer is the entire content of a clearly-labeled section heading, it's too easy. Push toward questions that require distinguishing between related-but-different rules, or that ask about a specific step within a longer procedure.

### 4. Gold overlap must be managed

When the same EvidenceUnit appears as required gold for multiple queries, hit rates become correlated and the effective sample size shrinks. Design constraint: a single EvidenceUnit should appear as `required_gold` in at most 2 queries. Report overlap statistics in every benchmark evaluation.

### 5. No corpus-name bias in query text

Questions must not include the system name. The benchmark file already selects the corpus. Answers become system-specific once cited, but the question text stays generic.

---

## Benchmark Schema (per query)

```
id                       stable string ID
suite                    "atomic" | "sourced" | "negative"
tier                     "T1" (core) | "T2" (detail) | "T3" (edge)
question_type            "atomic_rules" | "lookup" | "reasoning" | "negative"
question                 natural-language question text
answer                   referee-style answer grounded in cited text
expected_answer_summary  one crisp line
source_page              comma-separated printed page numbers (string)
gold_unit_ids            list of all gold EvidenceUnit IDs
gold_locations           map: unit_id → { page, structural_path, source_unit_ids }
required_gold            list of unit IDs that MUST be retrieved
supporting_gold          list of unit IDs that provide helpful context
required_gold_rationale  map: unit_id → why it's required
_parent_atomic           (atomic micro-queries only) parent concept ID
_status                  "draft_needs_citations" | "cited" | "draft_micro"
```

For **negative** queries, `gold_unit_ids`, `gold_locations`, `required_gold`, and `supporting_gold` are all empty. The `answer` field should state what the user is looking for and that it is not present in this ruleset, plus optionally where such a rule might exist in other systems.

---

## Benchmark lifecycle contract

This workflow now assumes a two-layer benchmark model:

- **Benchmark definition:** the stable, human-maintained artifact that captures query text and anchor intent.
- **Benchmark projection:** the generated artifact actually scored for one exact corpus contract.

Use these rules:

- `gold_locations` and related intent fields are the durable curation surface.
- `gold_unit_ids`, `required_gold`, and `supporting_gold` should be treated as projection outputs tied to a specific corpus shape.
- If chunk topology changes, regenerate the projection instead of hand-editing stale chunk IDs against the new corpus.
- Production decisions should reference the run's `prod_readiness.json`, not just the source benchmark filename.

### Required evaluation artifacts

For a scored run, expect:

- `benchmark.<surface>.json`
- `benchmark.<surface>.contract.json`
- `benchmark_contract_validation.json`
- `embeddings/corpus_index.json`

If these artifacts are missing or mismatched, the run is not a trustworthy recommendation surface.

---

## Suite 1: Atomic Questions

### Purpose

Atomic questions target universal TTRPG engine primitives that exist in most core rulebooks. They enable cross-ruleset comparison of retrieval quality on the same conceptual targets.

### The five universal concepts

These map to a deterministic engine loop (evaluate rules → request choice/RNG → commit transition → next frame):

1. **Roles & authority** — who decides what during play
2. **Uncertainty resolution** — dice procedures, saves, initiative
3. **Time progression model** — turns, rounds, what advances time
4. **Player actions in combat** — action economy, sequencing, casting constraints
5. **What must be tracked** — character state, consumables, XP accounting

### Min-anchor decomposition (mandatory)

Each universal concept must be decomposed into micro-queries. A single concept like "time progression" becomes 3–4 separate benchmark entries, each with its own narrow retrieval target.

Rules for decomposition:

- **Max `required_gold` per micro-query: 2.** If you need 3+, the query is bundling two distinct lookup targets — split it.
- **1 is preferred.** Use 2 only when the minimal operationalization genuinely requires two adjacent units (e.g., initiative procedure split across two consecutive evidence units).
- **Duplicate/slice units go to `supporting_gold`.** If two evidence units contain overlapping content due to extraction boundaries, pick the better one as required and demote the other.
- **Optional/variant content gets its own micro-query.** Don't lump "default initiative" and "optional Dex-based initiative" into one question.
- **Every micro-query carries `_parent_atomic`** pointing to the parent concept.

### Writing atomic questions that aren't trivially easy

Bad (too easy, too broad):

> "What are the time units used in the game?"

Better (targets a specific operational fact):

> "What is the step-by-step combat round sequence, and what causes play to advance to the next round?"

Better still (requires distinguishing between related rules):

> "In mass combat, does the game redefine the round length? If so, how does it differ from the standard combat round?"

The question should require the retriever to find a *specific* procedural or definitional anchor, not just anything on the topic.

### Cross-ruleset comparability contract

The same micro-query IDs (e.g., `u03a_time_units_turn_vs_round`) are reused across rulesets. The question text stays identical. Only the gold annotations change per corpus. This makes metric deltas across rulesets interpretable as "retrieval quality on the same conceptual target in different books" rather than "how verbose is this book."

If a concept doesn't exist in a particular ruleset (e.g., no mass combat rules), mark the query as `not_applicable` for that corpus rather than forcing a gold annotation.

---

## Suite 2: Sourced Questions

### Purpose

Sourced questions test retrieval on real user-facing lookup and reasoning tasks specific to this rulebook. They represent what a player, GM, or rules-compiler would actually ask.

### Gold sizing

Sourced questions may have wider required gold than atomic questions:

- **Recommended `required_gold` range: 1–5.** This reflects that real user questions sometimes need multiple pieces of evidence to answer correctly (e.g., "how does the saving throw work?" might need the procedure definition + the class-specific target table).
- **Max `required_gold`: 5.** If you need more, the question should be split or the extra units should be demoted to supporting.
- **`supporting_gold` is unlimited** but should be annotated honestly.

### Question sourcing strategies

To avoid the "answer key in hand" bias (writing questions while staring at the PDF, which produces artificially clean retrieval targets), use multiple sourcing methods:

**Method A: PDF-derived (traditional)**

Read the book, identify rules that would generate questions, write the question. This is the simplest method but biases toward well-extracted content. Use for at most 50% of sourced questions.

**Method B: External-phrasing (real confusion)**

Find questions from forums, Reddit, Discord, or blog posts where real users asked about the rules. Rephrase them into benchmark entries. These questions use vocabulary the book doesn't use, mix concepts the book separates, and reflect genuine user confusion. They are harder retrieval targets and more representative of production use.

Examples of external-phrasing patterns:
- "If the rules don't cover something, are we supposed to find the closest matching rule, or just let the referee make a call?"
- "Do first-level clerics get any spells at all, or do they have to wait until second level?"
- "When someone says 'check for wandering monsters every turn,' how long is a turn exactly?"

**Method C: Adversarial (distractor-aware)**

Deliberately construct questions where the answer is near but not identical to content that scores highly by keyword overlap. These test whether the retriever can distinguish between related-but-wrong and actually-correct evidence.

Examples:
- A question about treasure *division* procedure in a book with extensive treasure *generation* tables.
- A question about *morale* rules near a section about *reaction rolls*.
- A question about a specific class ability at level 1 when the book has extensive multi-level progression tables.

### Multi-part sourced questions

Sourced questions may be multi-part when the user's real information need is inherently compound:

> "When a character reaches 0 HP, do they die immediately, and if not, what options exist for healing or stabilization?"

For multi-part questions:
- `required_gold` should cover the minimum anchors for *each* part.
- The `required_gold_rationale` should explain which part each anchor serves.
- If the parts are truly independent lookups, split them into separate entries.
- If they form a natural follow-on ("what happens, and then what can you do about it?"), keep them together.

---

## Suite 3: Negative Questions (Out-of-Corpus)

### Purpose

Negative questions test whether the system correctly identifies when the corpus does *not* contain an answer. A retrieval system that always returns confident results — even for questions the book can't answer — is dangerous for a rules engine.

### Design

Negative questions ask about concepts that:

1. **Exist in other TTRPG systems but not this one.** Example for S&W: "How do opportunity attacks work when a character moves out of melee range?" (S&W doesn't have opportunity attacks.)
2. **Sound plausible but are not addressed.** Example: "What is the crafting system for creating magic items?" (if the book has no crafting rules).
3. **Use terminology from a different edition/system.** Example: "How do bonus actions work during combat?" (5e terminology not present in OSR systems).

### Schema for negatives

```json
{
  "id": "sw_rev_neg01_opportunity_attacks",
  "suite": "negative",
  "tier": "T1",
  "question_type": "negative",
  "question": "How do opportunity attacks work when a character moves out of melee range?",
  "answer": "This ruleset does not include opportunity attacks. Movement in and out of melee is handled by the Referee's rulings and the combat sequence phases.",
  "expected_answer_summary": "No opportunity attack mechanic exists in this ruleset.",
  "source_page": "",
  "gold_unit_ids": [],
  "gold_locations": {},
  "required_gold": [],
  "supporting_gold": [],
  "required_gold_rationale": {}
}
```

### Evaluation of negatives

Negative queries are scored differently from positive queries. They do not contribute to MRR, Hit@k, or Recall@k. Instead, report:

- **Abstention rate**: fraction of negative queries where the system correctly declines to answer or flags low confidence.
- **False-positive rate**: fraction of negative queries where the system returns a confident (but wrong) answer citing retrieved chunks.
- **Nearest-miss rank**: for each negative query, the rank of the highest-scoring chunk — useful for understanding how close the system came to surfacing misleading content.

### Recommended count

Include 3–5 negative queries per benchmark. More is better for statistical power but harder to construct well.

---

## Construction Workflow

### Phase A: Draft the outline (no citations)

#### Step 1: Atomic set

For each of the 5 universal concepts, draft 2–4 micro-queries following the decomposition rules above. Target 12–20 atomic micro-queries total per ruleset.

Write question text system-agnostic. Mark `_status: draft_needs_citations`.

#### Step 2: Sourced set

Draft 8–15 sourced questions using a mix of methods A, B, and C (see above). Aim for at least 30% from method B (external phrasing) to counter answer-key bias.

For each question, note which sourcing method was used (as a `_source_method` field: `pdf_derived`, `external_phrasing`, or `adversarial`).

#### Step 3: Negative set

Draft 3–5 negative questions. Verify that the concept genuinely does not appear in the book before including it.

#### Step 4: Difficulty calibration check

Before proceeding to citation, review the draft set and flag any question where:
- The answer is the *entire* content of a single clearly-labeled section (too easy).
- The gold set would obviously require 6+ units (too broad — split it).
- The question is essentially a chapter title rephrased as a question (too easy).
- Two questions target the exact same evidence units (overlap problem).

Remove or revise flagged items.

### Phase B: Manual citation loop (one question at a time)

For each draft entry:

#### Step 1: Present the entry

Show: `id`, `suite`, `tier`, `question`, draft `answer`, and any existing citations.

#### Step 2: Gather evidence

Request from the curator:
- Exact quoted text from the PDF (copy/paste).
- Printed page number(s).
- Exact section heading(s) visible on those pages.

#### Step 3: Claim-check the answer

For each sentence in the draft `answer`:
- If **explicitly supported** by cited text: keep, using the book's own wording.
- If **inferred but reasonable**: rewrite as "table practice" or "Referee judgment" (not "the rules say").
- If **unsupported**: delete.

#### Step 4: Split if needed

If the question mixes two independent lookups, split into separate entries. If it mixes lookup + reasoning, make them separate entries with different `question_type`.

#### Step 5: Fill citations and gold

Update all citation fields. Apply these rules:

- Fill `gold_locations` completely. This is the anchor-intent layer that must survive future projection changes.
- `required_gold`: the minimum set of EvidenceUnits needed to *operationalize* the answer (what a compiler needs to implement the procedure/state). Not "everything that mentions the topic."
- `supporting_gold`: expansions, examples, extra context, edge cases.
- Check overlap: if this query's `required_gold` shares units with another query's `required_gold`, and total shared count > 2 across the benchmark, consider whether one query should use a different anchor.
- Set `_status: cited`.

When editing a benchmark after a corpus change:

- update the intent fields first (`gold_locations`, rationale, source-page evidence),
- regenerate the projection for the active corpus,
- validate the new projection contract instead of trusting old IDs.

### Phase C: Post-citation validation

After all entries are cited, run these checks:

#### Check 1: Required gold size distribution

```
atomic queries:  max required_gold = 2, mean < 1.5
sourced queries: max required_gold = 5, mean < 3
negative queries: required_gold = 0 (all)
```

If any entry violates these caps, it must be split or its gold demoted.

#### Check 2: Gold overlap matrix

Compute how many queries share each required gold unit. Flag any unit appearing as required in > 2 queries. Either reassign one query's anchor to a different unit covering the same fact, or accept and document the overlap with rationale.

#### Check 3: Zero-required-gold queries

No positive query (atomic or sourced) should have empty `required_gold`. This creates a "free pass" that inflates ReqFSH. Every positive query must have at least 1 required anchor.

#### Check 3b: Projection validity

After curation, confirm that the benchmark projection for the active corpus:

- has zero dead gold IDs,
- validates against the active `corpus_fingerprint`,
- validates against the active `corpus_content_fingerprint`,
- validates against the active `corpus_index_sha256`.

#### Check 4: Suite balance

Verify the benchmark has adequate representation:

```
atomic:  12–20 micro-queries
sourced: 8–15 questions (≥30% external-phrasing)
negative: 3–5 questions
total:   25–40 queries
```

#### Check 5: Difficulty spread

Review the `tier` distribution. Aim for roughly:
- T1 (core, should-always-retrieve): 50–60%
- T2 (detail, moderate difficulty): 25–35%
- T3 (edge, hard/obscure): 10–20%

If the benchmark is all T1, it won't discriminate between a good and great retriever.

---

## Anchor Guidance

### What counts as "required"

`required_gold` = the minimal EvidenceUnits that enable correct operationalization. Think: "what does a compiler need to implement this procedure or state field?"

Not required: examples, flavor text, cross-references to related topics, duplicate units covering the same fact due to extraction slicing.

### Handling extraction artifacts

When the extraction pipeline splits one logical rule across two adjacent EvidenceUnits (common at heading boundaries or page breaks):
- Pick the unit that contains the operative statement as required.
- Demote the continuation/context unit to supporting.
- Note this in `required_gold_rationale`.

### Heading-specific guidance

Some headings are generic containers (e.g., "How to Play," "Referee Guide," "Equipment"). Units under these headings are valid gold only when the answer depends on content unique to that heading — not when the heading merely happens to contain tangentially related text.

---

## Running and Interpreting Baseline Results

### Required runs

For each benchmark, run at minimum:
- Mode A (raw-only): establishes embedding quality baseline.
- Mode C (raw-first merge-rerank): tests pipeline improvement over raw.

Mode B (merged-only) is optional and currently has known gold-grounding issues where unit IDs don't survive the merge process.

### Surface discipline

If auto-gold review is enabled, treat pre-review and post-review as separate benchmark surfaces.

- `benchmark.pre_review_manual.json` / `.contract.json` represent the manual surface.
- `benchmark.post_review_applied.json` / `.contract.json` represent the auto-applied surface.
- Do not mix metrics from those surfaces when making a recommendation.

### Metrics to report per suite

| Metric | What it tells you |
|---|---|
| MRR | How high the first relevant result ranks (1.0 = always rank 1) |
| Hit@k | Whether *any* gold appears in top-k |
| Recall@k | Fraction of gold units found in top-k |
| ReqFSH@k | Whether *all* required gold appears in top-k |
| Gold-in-candidates | Ceiling check: can the retriever even see the gold? |
| Retrieval misses | Count of queries where no gold appears at any k |

### Known metric distortions to watch for

- **ReqFSH suppression**: if any query has `required_gold` > k, ReqFSH@k is mathematically impossible for that query. This is why the cap matters.
- **Gold overlap inflation**: correlated hit rates from shared gold units. Report overlap statistics alongside metrics.
- **Free-pass inflation**: queries with 0 required gold always "pass" ReqFSH. The construction guide eliminates this, but verify after edits.

### Interpreting miss diagnostics

When queries miss, classify the failure:

| Tag | Meaning | Fix category |
|---|---|---|
| `query-phrase mismatch` | Query uses different vocabulary than the gold unit | Query rewrite or alias expansion |
| `gold anchor too narrow` | The selected anchor unit doesn't contain the operative fact well | Annotation correction |
| `heading dilution` | Gold is buried under a generic heading; distractors from same heading dominate top-k | Heading-aware rerank or better anchor selection |
| `semantic confound` | Retriever returns topically related but wrong content with high confidence | Adversarial training signal or discriminative rerank |
| `evaluator anomaly` | Gold ID appears in top-k but evaluator reports miss (grounding/merge ID issue) | Evaluator fix, not retrieval fix |

---

## Revision History

- **2026-02-22 v2**: Complete rewrite incorporating min-anchor experiment results, three-suite design (atomic/sourced/negative), gold sizing caps, overlap management, difficulty calibration, and failure classification taxonomy. Supersedes original PDF-only curation workflow.
- **2026-02-XX v1**: Original manual curation workflow (PDF-driven, single suite).
