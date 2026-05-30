# Report: Intent-Routed Retrieval v0 — Decision

**Status:** M6 decision report. No new code.
**Date:** 2026-05-29.
**Decides:** deepen / expand / back out, per the milestone roadmap and
[VISION §9 success signals](../Design/VISION-Intent-Routed-Retrieval.md).
**Companion:** [ANALYSIS-Routing-and-HyDE-Bitter-Lesson.md](../Design/ANALYSIS-Routing-and-HyDE-Bitter-Lesson.md)
holds the mechanistic analysis and the empirical diagnosis behind this verdict.

---

## 1. What was built (M0–M5)

- **M0** SWCR substrate (Stage A/B EvidenceUnits) via local pymupdf4llm ingest.
- **M1** Automated corpus self-portrait: glossary, acronyms, KMeans structural
  clusters with model-written labels, typed metadata index, cross-ref edges.
- **M2** q-ROFS classifier (Pythagorean, q=2) emitting per-bucket (μ, ν, π).
- **M3** Cross-encoder reranker (`bge-reranker-v2-m3`), GPU-resident.
- **M4** Router v0: two live routes (`entity_anchored` = hybrid+rerank,
  `intent_bearing` = HyDE-with-shape-prior + dense + rerank). The other six
  buckets fall back to `entity_anchored`.
- **M5** End-to-end eval on a 19-query SWCR atomic-rules benchmark with
  LLM-as-judge gold, vs a raw_dense baseline. Plus a backend abstraction
  (`tinker/backends/`) added afterward so the pipeline runs on local Ollama or
  hosted Gemini 2.5 Flash, and a 2×2 ablation (hypothesis cap × classifier
  thinking) on the hosted backend.

The build is complete and the harness is sound: the no-LLM `raw_dense` baseline
is byte-identical across the Ollama and Gemini runs (R@10 0.589, R@20 0.827),
which is what let us trust the comparison and catch a reporting error (below).

---

## 2. Results

19-query SWCR atomic-rules benchmark. raw_dense = dense top-50 + cross-encoder
rerank, no classifier, no HyDE.

| Config (backend) | R@5 | R@10 | R@20 | MRR | strictR@10 |
|---|---:|---:|---:|---:|---:|
| **raw_dense** (both) | **0.418** | **0.589** | **0.827** | 0.607 | **0.474** |
| router, local Ollama | 0.362 | 0.505 | 0.705 | 0.606 | — |
| router, Gemini capped/no-think | 0.390 | 0.541 | 0.719 | 0.603 | 0.474 |
| router, Gemini uncapped/no-think | 0.323 | 0.512 | 0.679 | 0.591 | 0.421 |
| router, Gemini capped/think | 0.338 | 0.515 | 0.651 | 0.596 | 0.368 |
| router, Gemini uncapped/think | 0.345 | 0.521 | 0.647 | 0.596 | 0.368 |

**raw_dense beats the router on every recall metric, on both backends. MRR is a
tie.** Neither lifting the hypothesis token cap nor enabling classifier thinking
closed the gap; both slightly worsened it. Multi-path never triggered (0/19).

**Reporting correction (recorded for honesty):** an earlier reading of the local
run had the `router` and `raw_dense` columns swapped, making it look like routing
won by +0.084. It did not; raw_dense won by +0.084. The error propagated across
the backend-swap effort until a cross-run diff of the deterministic baseline
surfaced it. See the `feedback-verify-with-data` memory.

### Why HyDE underperforms (diagnosed, not asserted)

`diagnose_hyde.py` over all 19 queries:

- **Candidate-pool recall@50:** query embedding **0.993** vs HyDE hypothesis
  **0.873**. HyDE's pool is never better (0/19). The strong instruction-tuned
  embedder (`qwen3-embedding` 7.6B) already retrieves ~99% of gold into the
  top-50, so there is no query→document asymmetry left for HyDE to bridge —
  only gold to lose by swapping the query out. The reranker scores the original
  query but cannot surface a passage the pool omitted.
- **Hypothesis drift:** the generated hypotheses are generic-D&D-flavored and
  confabulate structure from the injected glossary, embedding *away* from SWCR's
  idiosyncratic OSR passages (e.g. inventing a generic healing block while the
  gold is SWCR's Subdual Damage rule). Bias, not variance — which is why a
  longer/better hypothesis did not help.

> **Confound (added 2026-05-30):** the shape-prior bridge HyDE was given was
> weak. The M1 glossary feeding it is a 130-term regex grab-bag missing the rule
> concepts the failing queries needed (subdual/morale/reaction/negotiation/rest).
> So this is "HyDE with a *weak* shape prior," not a clean test of HyDE-as-
> designed. The embedder-ceiling argument (0.993 pool recall) is the part that
> stands independently; the prior-drift cause is refined to "weak bridge +
> fallback to prior." M9 re-runs HyDE with a proper LLM-built glossary to put the
> as-designed performance on the record.

### Side-finding worth carrying forward

raw_dense pool recall@50 is 0.993 but its final recall@10 is 0.589: the gold is
in the pool; the **reranker** (or `top_k`) is the binding constraint on this
corpus, not retrieval. Any future quality work should target ranking, not recall.

### Cost / latency context

Moving the LLM to Gemini cut router latency from ~57 s/query mean (local, swap-
bound) to ~14 s (capped/no-think). raw_dense is ~6 s. Local VRAM is now bound by
the embedder (6.24 GB, a 7.6B model that must stay local) + reranker (3.15 GB),
not the generation LLM.

---

## 3. Verdict against the success signals

| VISION §9 signal | Outcome |
|---|---|
| Intent-bearing (HyDE) beats raw dense by a measurable MRR delta | **Failed.** No delta; recall worse. |
| Entity-anchored matches/beats baseline (no regression on simple cases) | Inconclusive (entity_anchored rarely chosen; concept→entity fallback under thinking hurt strictR@10). |
| Classifier accuracy ≥ 85% | Not the binding question; routing didn't help even when it fired as designed. |
| Fast-path latency / single-round HyDE | Met on Gemini, irrelevant given the quality result. |

The roadmap's **back-out condition is met**: "HyDE-with-shape-prior shows no MRR
delta over raw dense."

### Decision: BACK OUT of taxonomy-routing-for-quality; REDIRECT

We back out of the thesis *as implemented* — a hand-designed query-type taxonomy
that dispatches between flavors of similarity retrieval to improve quality. The
analysis doc lays out why this is a bitter-lesson outcome: a strong embedder
subsumes the intra-similarity distinctions the taxonomy encodes, and HyDE in
particular is a 2022-era patch for weak embedders that is now a liability on a
niche corpus.

This is **not** a blanket rejection of routing. Two forms were never actually
tested and are where the concept's value plausibly remains:

1. **Cross-paradigm routing.** Route only the queries where similarity is the
   *wrong primitive* — enumeration (set-completeness), structural (positional),
   cross-reference (graph) — to non-similarity mechanisms; let everything else
   hit the embedder directly. Every route we built was still similarity search,
   so the strongest case for routing-as-quality was never on trial.
2. **Cost / effort routing.** Decide *how much* compute a query needs (cheap
   path vs escalate), not *what human category* it is. Orthogonal to the bitter
   lesson; compatible with model cascades.

---

## 4. Recommended next experiment

Build **one** genuinely non-similarity route — enumeration is easiest: a typed-
metadata predicate filter + scan, not a ranker — and test it against raw_dense on
enumeration-style queries. A similarity baseline structurally cannot return a
complete set; a filter can. If it wins there, routing earns its keep on quality
for the first time, on a within-paradigm-vs-cross-paradigm basis rather than a
human-ontology one.

Prerequisite, and an honest scope note: the current SWCR atomic benchmark has
**no enumeration queries** (all 19 are broad "how does X work" questions), so
this experiment requires authoring enumeration queries + gold first. That is a
new milestone, not a continuation of M5.

Secondary, cheaper lever suggested by the side-finding: the reranker, not
retrieval, caps recall here. Trying a stronger reranker or a larger rerank `top_k`
would likely move raw_dense more than any routing change would.

---

## 5. What to keep

- The **backend abstraction** (`tinker/backends/`) — clean, useful regardless.
- The **eval harness + LLM-as-judge gold** — reusable for the enumeration test.
- The **corpus self-portrait** — still the right substrate for a cross-paradigm
  router (metadata index feeds enumeration; cross-ref edges feed traversal).
- The **q-ROFS classifier** — but repurposed: its natural next job is the
  "is this a similarity problem at all / how much compute" decision, not the
  8-way ontology.

What to retire: the expectation that HyDE-with-shape-prior improves retrieval
against a strong modern embedder. It doesn't, here.
