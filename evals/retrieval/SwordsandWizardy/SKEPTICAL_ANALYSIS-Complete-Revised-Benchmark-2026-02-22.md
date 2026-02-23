2# Skeptical Analysis: Swords & Wizardry Complete Revised Benchmark

**Date:** 2026-02-22
**Benchmark:** `swords_wizardry_complete_revised_benchmark.json` (21 queries)
**Compared Against:** `swords_wizardry_benchmark.json` (27 queries, original)
**Baseline Run:** `baseline_20260222` (Modes A/B/C, all-mpnet-base-v2, hybrid retrieval)

---

## 1. Headline Numbers

| Mode                       | MRR  | Hit@10 | Recall@10 | ReqFSH@10 | Gold-in-Cand |
| -------------------------- | ---- | ------ | --------- | --------- | ------------ |
| A (raw-only)               | 0.49 | 0.81   | 0.40      | 0.14      | 0.90         |
| B (merged-only)            | 0.20 | 0.33   | 0.19      | 0.10      | 0.38         |
| C (raw-first merge-rerank) | 0.60 | 0.81   | 0.60      | 0.33      | 0.86         |

Mode C at 0.60 MRR and 0.81 Hit@10 looks like solid progress. The rest of this document stress-tests what these numbers actually mean.

---

## 2. The Old Benchmark Was Broken by Design

The old benchmark had 27 questions. The breakdown:

- **17 of 27 questions (63%) had NO `gold_locations`.** They had `gold_unit_ids` that were never grounded to the corpus. Any evaluation system grounding gold by page+structural_path would score them as total failures regardless of retrieval quality.
- **7 questions referenced S&W Light** — a separate 4-page product, not the S&W Complete Revised PDF being evaluated.
- **8 questions were comparative** ("How does S&W differ from Labyrinth Lord?") — requiring knowledge from a different game system entirely.
- **1 question referenced a blog post** (Tenkar's Tavern) as its authoritative source, not the PDF.

~63% of the old benchmark asked the retriever to find answers that _do not exist in the corpus_. The old benchmark's low scores were not evidence of bad retrieval — they were evidence of a bad benchmark. Any new benchmark that removes these impossible questions will show "improvement" by tautology.

**Verdict:** The comparison between old and new benchmark scores is meaningless. They measure different things on incompatible question sets. The new benchmark's better scores don't demonstrate retrieval system improvement; they demonstrate benchmark construction improvement.

---

## 3. The Atomic Questions Are Problematic for Retrieval Evaluation

The new benchmark contains 12 `atomic_rules` questions (u01–u05, s05, s06, s09, s12, s13, s14, s16). These are the reusable cross-ruleset questions designed for consistent evaluation across different rulesets. Here's the problem:

### They demand absurdly large gold sets.

| Question                       | Required Gold | Total Gold |
| ------------------------------ | :-----------: | :--------: |
| u01 (roles at table)           |       7       |     7      |
| u02 (uncertainty resolution)   |      10       |     10     |
| u03 (time progression)         |      11       |     12     |
| u04 (player actions in combat) |       8       |     13     |
| u05 (what must be tracked)     |      14       |     15     |
| s05 (combat sequence)          |       8       |     18     |

**A question with 14 required gold units can never achieve Full-Set Hit@10.** It's mathematically impossible — you'd need all 14 in the top 10 slots when you only have 10 slots. Even getting all 14 in top 20 is near-impossible for a general-purpose retriever against 1618 corpus units. This isn't measuring retrieval quality; it's measuring how many pages a question sprawls across.

The consequence: these questions **systematically suppress** Full-Set Hit and Recall metrics. The benchmark's low Recall@10 of 0.40/0.60 and ReqFSH@10 of 0.14/0.33 sound alarming, but they're an artifact of gold set construction, not retrieval failure.

### They don't represent real user queries.

If a user asks "What are the roles at the table?", does a retrieval system actually need to find 7 scattered evidence units spanning pages 33, 73, and 95 to give a correct answer? Probably not. One or two well-chosen chunks would suffice for a useful RAG response. The atomic questions conflate "comprehensive textbook answer" with "useful retrieval."

Questions like "What information must be tracked to play correctly?" are how a textbook index talks. Real users ask "how does encumbrance work?" or "what are the time units?" The atomic questions test comprehensiveness, not findability.

### Cross-ruleset comparability may be illusory.

If these same questions are used cross-ruleset, they'll produce metrics that reflect gold-set-size differences between books (a verbose 150-page book vs a terse 30-page book), not retrieval quality differences. A question needing 15 evidence units from one book and 3 from another tells you which book is more verbose about that topic, not which retriever works better.

---

## 4. Massive Gold Unit Overlap Inflates Hit Rates

Of the 73 unique gold units across all 21 queries, **37 (51%) are shared across 2+ queries**. Twelve units each appear in 4 different queries.

### Distribution of gold unit reuse:

| Used in N queries | Number of units |
| :---------------: | :-------------: |
|         1         |       36        |
|         2         |       17        |
|         3         |        8        |
|         4         |       12        |

The initiative/combat units from page 35 appear in u02, u03, u04, and s05 simultaneously. The page 95 "Reading the Monster Descriptions" units appear in u01, u05, s02, and s13.

This means:

- If the retriever happens to rank the page-35 initiative units highly, it gets credit for 4 different queries at once.
- If it misses them, 4 queries fail at once.

The hit rates are heavily correlated, not independent. The effective sample size is much smaller than 21 queries suggest. A few "hot pages" dominate the benchmark, and performance hinges more on whether those specific pages embed well than on general retrieval quality.

---

## 5. The Sourced Questions Are Better — But Explicitly Built for This PDF

The 8 `lookup` questions (s01–s04, s07–s08, s10–s11, s15) and 1 `reasoning` question are genuinely better benchmark material. They ask about specific rules that exist in the PDF, have reasonable gold set sizes (1–7 units), and represent real user queries. Questions like "What does a 'T' result mean on the Turn Undead table?" or "Can a first-level cleric cast spells?" are the kind of thing a player would actually ask.

But these questions were written _by looking at the PDF_ and then manually identifying exactly which evidence units answer them. The question-writer had the answer key in hand while writing the question. This biases the benchmark toward questions whose answers happen to be well-contained in single evidence units that the extractor produced cleanly.

Real user questions don't come with that guarantee. They might span structural boundaries the extractor didn't preserve, reference content in tables that got mangled, or use vocabulary the book doesn't use.

**The questions from the old internet-sourced benchmark, for all their flaws, at least represented genuine user confusion.** The phrasing "If the rules don't cover something, are we supposed to find the closest matching rule, or just let the referee make a call?" is how a real person talks. The atomic questions like "What information must be tracked to play correctly?" are how a textbook index talks.

---

## 6. Mode B (Merged) Is Catastrophically Broken

Mode B shows gold-in-candidates at **0.38** — meaning 62% of queries have gold that doesn't even appear _anywhere_ in the ranked list. This isn't a ranking problem; it's a grounding/identity problem. The gold unit IDs in the benchmark don't survive the merge process, so the scoring system can't find them in merged units even though the _content_ is there.

This makes Mode B numbers useless for comparison. You're not measuring "is merged retrieval worse?" — you're measuring "do gold IDs survive merging?" The answer is: usually not.

Mode C inherits the merge-rerank stage from B, so its numbers are partially compromised as well.

---

## 7. Corpus Quality Concerns

The integrity check shows a **0.696 dangling-reference ratio** in the corpus. Nearly 70% of evidence units have dangling references. This suggests systematic extraction quality issues that the benchmark may be papering over by only asking questions about well-extracted content.

Additionally, `sw_rev_s02_treasure_division_procedure` has **0 required gold** and 7 supporting gold. A query with no required gold can never fail the RequiredFSH metric — it's a free pass that inflates the score.

---

## 8. What the Numbers Actually Tell You (Honest Assessment)

Stripping away the confounds:

**Mode A (raw) at 0.49 MRR and 0.90 gold-in-candidates:** This is the cleanest signal. For a corpus of 1618 raw evidence units, the retriever finds _some_ relevant unit in the top 10 for 81% of queries, and the first relevant unit appears around rank 2–3 on average. For a general-purpose mpnet embedding model, this is decent but not great. The 10% of queries with gold not in candidates at all suggests either grounding issues or that some gold annotations point to units the retriever fundamentally can't distinguish semantically.

**Mode C at 0.60 MRR, 0.60 Recall@10:** The merge-rerank step adds roughly +0.11 MRR and +0.20 Recall@10 over raw-only, which is a legitimate retrieval pipeline improvement. But 0.60 MRR means the first relevant result is, on average, appearing around rank 2. That's acceptable but leaves room for improvement.

**The 0.33 ReqFSH@10 in Mode C:** Only a third of queries get all their required gold in the top 10. But given that 5 queries demand 8–14 required units each, this metric is structurally suppressed by benchmark design. If you isolated just the sourced questions (s01–s16), the number would likely be substantially higher.

---

## 9. What's Real Progress and What Isn't

### Real progress:

- Building a benchmark where all 21 queries have verified `gold_locations` and `required_gold` annotations. The old benchmark was broken. This one functions.
- Establishing `required_gold` vs `supporting_gold` separation. This is genuine methodological improvement.
- Providing `required_gold_rationale` for each annotation. Good practice for reproducibility.
- The cross-ruleset atomic question concept is a legitimate innovation for future comparability, even if the current implementation has issues.

### Not evidence of retrieval improvement:

- Comparing scores from the new benchmark to the old benchmark's scores. Different question sets, different gold standards, different grounding quality.
- Mode C's high Hit@10 of 0.81. This is partly an artifact of gold overlap — finding the page-35 combat units counts as a "hit" for 4 queries simultaneously.
- Any metric from Mode B. The merged grounding is broken enough (0.38 ceiling) that the numbers are meaningless.

### Genuinely concerning:

- The 0.696 dangling-reference ratio in the corpus.
- The atomic questions with 10–15 required gold units are not tractable retrieval targets. If these same questions are used cross-ruleset, they'll produce metrics that reflect gold-set-size differences between books, not retrieval quality differences.
- `sw_rev_s02_treasure_division_procedure` with 0 required gold is a free pass.

---

## 10. Recommendations for Honest Evaluation

1. **Run the old benchmark on this same corpus and pipeline** for an apples-to-apples comparison. Even if many old questions are unanswerable, the 10 questions that _do_ have `gold_locations` would give a comparable signal.

2. **Report metrics separately for atomic vs sourced questions.** The atomic questions have fundamentally different gold set structures and shouldn't be averaged together with the narrower lookup questions.

3. **Cap required gold at a tractable number** (e.g., 3–5). If a question genuinely needs 14 evidence units, it should be decomposed into sub-questions. A single question demanding 14 chunks is not a retrieval task — it's a literature review.

4. **Fix the Mode B grounding.** If merged units can't resolve gold IDs, Mode B and Mode C metrics are both compromised. Mode C inherits the merge-rerank stage from B.

5. **De-duplicate gold units across queries** when computing aggregate metrics, or at least report the effective independence (e.g., "21 queries, but only 73 unique gold units, 37 of which overlap"). This puts confidence intervals in context.

---

## 11. Bottom Line

This benchmark is a significant improvement over the old one — but mostly because the old one was fundamentally broken (63% ungroundable questions about external content). The "improved scores" primarily reflect that the new benchmark asks questions that are actually answerable from the corpus. That's necessary hygiene, not retrieval progress.

The atomic questions are an interesting concept for cross-ruleset standardization, but in their current form they create gold sets so large (10–15 units per question) that they structurally suppress recall and full-set-hit metrics, making the benchmark look harder than the retrieval task actually is for a downstream RAG application.

The honest signal in these results: **Mode C gets at least one relevant chunk into the top 3 for about 76% of queries (Hit@3), and the first relevant chunk averages around rank 2 (MRR 0.60).** For a RAG system that needs to provide a useful answer, that's workable. For a system that needs to provide a _complete, citable_ answer pulling from 5–15 scattered sources per query — no retrieval system at this embedding tier is going to do that.

The progress is real in benchmark construction methodology. The progress in retrieval quality is undemonstrated because there's no valid baseline to compare against.
