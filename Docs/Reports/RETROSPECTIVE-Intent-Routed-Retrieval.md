# Retrospective: Intent-Routed Retrieval

**Status:** Project retrospective / journey log. No code.
**Date:** 2026-05-30.
**Hub for:** [VISION](../Design/VISION-Intent-Routed-Retrieval.md),
[MODELS](../Design/MODELS-Intent-Routed-Retrieval.md),
[ANALYSIS (HyDE & bitter lesson)](../Design/ANALYSIS-Routing-and-HyDE-Bitter-Lesson.md),
[M6 decision report](REPORT-Intent-Routed-Retrieval-v0.md),
[M7 enumeration milestone](../Design/MILESTONE-M7-Enumeration-Route.md).

This is a stock-taking of the whole arc: what we set out to do, what we found,
what we learned about the work itself, and what's ahead. It is deliberately
honest about where the original idea was wrong, because that is where the value
turned out to be.

---

## 1. What we set out to do

A deliberately contrarian thesis: **retrieval is a routing problem.** Instead of
treating HyDE as a universal hammer, the bet was that queries have different
*relationships* to their evidence (lexical, conceptual, intent-to-evidence,
set-membership, structural, link-traversal), that a cheap per-query classifier
could dispatch to the right specialized mode, and that an *automated* corpus
self-portrait could ground the whole system without hand-curation. Product frame:
tabletop RPG rulebooks. Intellectual frame: HyDE bridges *encoded intent*, not a
terminology shortage.

We built the full stack to test it rather than to ship it: substrate (M0),
automated self-portrait (M1), q-ROFS Pythagorean classifier (M2), cross-encoder
reranker (M3), a two-path router — entity-anchored hybrid and intent-bearing
HyDE (M4), and an end-to-end eval with LLM-as-judge gold (M5). The goal was a
verdict, not a product.

---

## 2. What we discovered

**The original thesis, as built, was wrong — and the shape of the wrongness was
the payoff.**

- **M5: routing between flavors of similarity search lost to a plain baseline.**
  On the 19-query SWCR atomic benchmark, dense + rerank (`raw_dense`) beat the
  router on every recall metric, on both local Ollama and hosted Gemini. MRR
  was a tie. Lifting the HyDE token cap and turning on classifier "thinking"
  both made it slightly worse.

- **We diagnosed why HyDE hurt, rather than asserting it.** Query-pool
  recall@50 was 0.993 vs HyDE's 0.873; the hypothesis pool never beat the query
  pool. A strong 2025 instruction-tuned embedder has already absorbed the job
  HyDE was invented for in 2022, and on a niche corpus the generated hypothesis
  drifts toward the LLM's training prior (generic D&D, not the idiosyncratic OSR
  rules of SWCR), poisoning the candidate pool. HyDE was not neutral; it was a
  liability. Failure was bias, not variance — which is why a longer or
  better-reasoned hypothesis did not help.

- **M6: the bitter-lesson reframe.** The hand-built query-type *taxonomy as a
  quality mechanism* is exactly the human structure that scale subsumes. But two
  things survive it: routing *across paradigms* (where similarity is the wrong
  primitive entirely) and routing for *cost*. Crucially, we had only ever tested
  the part the embedder eats — every live route was still a flavor of similarity
  search.

- **M7: we built the part we had never tested, and it won.** Enumeration is the
  cleanest case where similarity is structurally the wrong tool: "give me the
  complete set sharing an attribute value" is bounded by K/|set| for any top-K
  retriever, regardless of embedder quality. A discovered-facet scan is not.
  Validated on two different rulebooks:

  | metric | SWCR | D&D 5e SRD |
  |---|---|---|
  | enumeration route set-F1 | 1.000 (37/37 exact) | 1.000 (20/20 exact) |
  | raw_dense set-F1 @ top-20 | 0.128 | 0.107 |
  | facet resolution (paraphrased) | 37/37 | 20/20 |

  The win is real but bounded, and the doc says so: the 1.000 is partly circular
  (route and gold read the same discovered facet index), so the independently
  measured skills are facet-resolution accuracy on paraphrased queries and
  raw_dense's structural failure (~0.11). Two corpora, same domain.

---

## 3. What we learned about how we work

Three process lessons, earned rather than assumed (each saved to memory):

- **Verify with data, at the right moment.** We were bitten repeatedly: a
  single-probe latency projection 3x off; a VRAM story built on one snapshot;
  and, worst, the foundational M5 result reported with the two compared columns
  *swapped*, an inversion carried across an entire follow-on effort. The
  discipline that finally caught it — diffing a deterministic baseline across
  runs — is now the reflex. Report a winner by pasting both numbers from the
  source in the same breath, never from memory.

- **Discover, don't hardcode.** The push toward "general concepts, not the
  unique properties of the distribution in question" reshaped M7 from a brittle
  hand-authored test into a schema-free, self-generating, size-adaptive pipeline.
  The 5e spike was the proof: brittleness surfaced (the SRD's typography broke
  bold-label extraction), and the fix made the code *more* general (bold-or-plain
  label detection, phrase-mode values, corpus-size-relative thresholds), not more
  special-cased. Validate generality on a *second* instance before claiming it.

- **A perfect score demands more skepticism, not less.** The 1.000 set-F1 is
  partly circular, and stating that plainly is worth more than the number.

---

## 4. What we're excited about ahead

- **Cost / effort routing — the real open frontier.** The second
  bitter-lesson-compatible form of routing we named but never built. The decision
  is not "what kind of question is this" but "how much compute does this one
  need." This is where the economic value lives, because running strong models on
  every query is the actual waste. Success is a cost–quality Pareto curve, not a
  per-bucket lift.

- **A facet-quality filter.** Auto-discovery currently emits noise facets (gp
  costs, page-header barewords). A statistical/LLM quality gate would let the
  self-generating eval and the route trust their own facets.

- **The next non-similarity route.** Cross-reference traversal is the most
  interesting: a graph-hop problem similarity cannot touch, and the self-portrait
  already builds the link edges.

- **A synthesis layer.** Use the clean retrieved sets to actually answer, where
  enumeration's completeness should pay off in grounded, citeable responses.

- **Pull the reranker lever.** A quiet side-finding: on these corpora the gold is
  in the pool (recall@50 ~0.99) but the *reranker*, not retrieval, caps recall@10
  (~0.59). That is a lever we noticed and have not pulled.

---

## 5. The throughline

We set out to prove a clever idea, found it was mostly wrong, diagnosed exactly
why, and ended up somewhere more defensible and more general than the original
pitch: route across paradigms (and eventually across compute tiers), not between
flavors of the same similarity search. The negative result was not a detour; it
was the project working as intended.
