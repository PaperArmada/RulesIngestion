# Analysis: Why HyDE Underperforms, and What Survives of Routing

**Status:** Analysis companion to the M5/M6 evaluation. Written 2026-05-29 after
the hosted-backend (Gemini 2.5 Flash) ablation grid.
**Audience:** future-us deciding whether and how to keep exploring intent-routed
retrieval.

---

## 0. The result that prompted this

On the 19-query SWCR atomic-rules benchmark, **plain dense + cross-encoder
rerank (`raw_dense`) beats the router on every recall metric, on both the local
Ollama backend and hosted Gemini 2.5 Flash.** MRR is a tie.

| Config | R@5 | R@10 | R@20 | MRR | strictR@10 |
|---|---:|---:|---:|---:|---:|
| **raw_dense** | **0.418** | **0.589** | **0.827** | 0.607 | **0.474** |
| router: capped, no-think | 0.390 | 0.541 | 0.719 | 0.603 | 0.474 |
| router: uncapped, no-think | 0.323 | 0.512 | 0.679 | 0.591 | 0.421 |
| router: capped, think | 0.338 | 0.515 | 0.651 | 0.596 | 0.368 |
| router: uncapped, think | 0.345 | 0.521 | 0.647 | 0.596 | 0.368 |

Two mechanism interventions we expected to help did not:
- **Uncapping the hypothesis** (200→512 tok, 120→250 words) slightly *hurt*.
- **Thinking on the classifier** shifted routing toward `concept_anchored`
  (which falls back to the hybrid runner) and *hurt* strict-required@10.

Correction recorded for honesty: an earlier reading of the local run had the
`router` and `raw_dense` columns swapped, which made it look like routing won
by +0.084. It did not. `raw_dense` won by +0.084, locally and hosted. See
the `feedback-verify-with-data` memory.

---

## 1. Why HyDE underperforms here — the causal chain

**Core claim: HyDE's value is inversely proportional to the embedder's quality,
and it was designed in 2022 for embedders that no longer represent the frontier.**

Original HyDE (Gao et al., 2022) solved query→document asymmetry: a short query
embeds far from the prose passage that answers it, and a weak unsupervised
embedder (Contriever-class) could not bridge the gap. HyDE outsourced the
bridging to an LLM — generate a fake answer, embed *that*, land near real
answers. It worked precisely because the embedder could not do the job itself.

`qwen3-embedding` (7.6B, instruction-tuned retrieval embedder) is trained on the
query→document asymmetry problem directly, with query/document prompt templates
and a retrieval objective. **The function HyDE performs has been absorbed into
the embedder's weights.** So HyDE is at best redundant. It is actively harmful
for the following reasons:

1. **The route replaces the true query with a single generated hypothesis** and
   retrieves on the hypothesis embedding. The actual information need — with its
   exact constraints — is discarded for the retrieval step.
2. **The hypothesis is a sample from the LLM's parametric prior, and for tabletop
   RPGs that prior is dominated by D&D 5e / Pathfinder, not Swords & Wizardry.**
   SWCR is idiosyncratic OSR (descending AC, different saving-throw categories,
   different turn structure). A hypothesized answer is 5e-flavored, embeds near
   generic/5e content, and therefore lands *away* from SWCR's actual passages.
   This is the drift, concretely: **prior-contamination from the dominant system
   in the training data.** The literal query carries no such contamination.
3. **The hypothesis determines the candidate pool; the reranker cannot recover
   what the pool never surfaced.** Verified structurally in
   `tinker/routing/intent_bearing.py`: step 5 retrieves on the hypothesis vector
   (dense-only), step 6 reranks on the *original query*. So `intent_bearing` vs
   `raw_dense` is a clean A/B whose only difference is which 50 candidates reach
   the reranker. A drifted hypothesis yields a pool with a lower recall ceiling,
   and no reranker fixes an absent passage.
4. The failure is therefore **bias, not variance.**

**Evidence already in hand for the bias (not variance) reading:** uncapping the
hypothesis and enabling thinking both failed to help. If the problem were a noisy
single sample, a longer / better-reasoned hypothesis would help. It did not — a
better-written wrong answer still embeds near the wrong (5e) centroid.

**Decisive test (run separately; results appended in §4):** measure pool
recall@50 of the HyDE pool vs the query pool against gold, across the
population, and read the actual hypothesis text next to the gold passage to see
whether the 5e-drift is visible.

---

## 2. The bitter-lesson question

Sutton's bitter lesson: general methods that scale with computation beat methods
that bake in human knowledge about problem structure; hand-built structure gives
a short-term gain and a long-term ceiling.

"Routing" is three different things wearing one coat. The bitter lesson applies
to exactly one of them.

### 2a. The 8-bucket taxonomy as a *quality* mechanism — this is the bitter pill

We invented `entity_anchored / concept_anchored / intent_bearing / …` from human
intuition about how questions relate to evidence. A strong embedder does not need
to be *told* a query is intent-bearing; it just embeds it well. The categories
are interpretable to *us* and invisible to the model's actual needs. Imposing a
query-type ontology to improve *similarity retrieval* is the kind of
human-structure that scale subsumes. The data agrees.

### 2b. But we only tested routing *within* the similarity paradigm

Both live routes are still similarity search: `entity_anchored` = hybrid
(dense+BM25) + rerank; `intent_bearing` = HyDE-dense + rerank. We pitted two
flavors of similarity search against a third (`raw_dense`). The bitter lesson
flatly predicts the simplest member of a family wins within that family — and
"just embed the query" did.

**The routes where similarity is the wrong primitive were never built:**
- **enumeration** ("list every 3rd-level spell") — set-completeness, not
  nearest-neighbor.
- **structural** ("what's in the combat chapter") — positional / metadata.
- **cross-reference** ("what does this rule depend on") — graph traversal.

For those, a pure embedder doesn't have a quality *ceiling*; it has a *category
error*: similarity ≠ set membership ≠ reachability. **The strongest case for
routing-as-quality was never on trial.** Our negative result is scoped to
"routing between kinds of similarity search," which is the part most thoroughly
eaten by a strong embedder.

### 2c. Routing as cost / effort allocation — orthogonal to the bitter lesson

The bitter lesson is a statement about the capability *frontier*: what wins when
you are willing to spend the compute. It says nothing against spending *less*
compute when you can get away with it. Model cascades (cheap path first, escalate
on low confidence) are a validated pattern precisely because running the strong
path on every query is wasteful. This routing decides *how much* scale to deploy
per query; it does not impose structure to beat scale. Fully compatible.

---

## 3. Synthesis and reorientation

The taxonomy dies as a retrieval-quality device against a strong embedder. Two
forms of routing the experiment never tested are where the value, if any, lives:

1. **Cross-paradigm routing:** route only the queries where similarity is the
   *wrong primitive* (enumeration, structural, cross-reference) to a
   non-similarity mechanism; let everything else hit the strong embedder
   directly. The decision is "is this a similarity problem at all," not "what
   flavor of similarity."
2. **Effort routing:** the classifier's job becomes "how much compute does this
   query need," not "what human category is it." Success metric flips from
   per-bucket retrieval lift to a cost–quality Pareto curve: same quality at
   lower average cost.

On interpretability: the taxonomy was partly an *explainability* scaffold. That
has real debugging value, but an interpretability artifact is not a performance
mechanism. If we want interpretability, derive it post-hoc (cluster the queries
the system actually treats alike) rather than impose it a priori and pay for it
in quality.

**Cleanest forward experiment:** build one genuinely non-similarity route
(enumeration is easiest — a metadata filter + scan, not a ranker) and test it
against `raw_dense` on enumeration-style queries. If a similarity baseline
structurally cannot enumerate and a cheap filter can, that is routing earning
its keep on quality for the first time in this project — a
within-paradigm-vs-cross-paradigm distinction, not a human-ontology one.

---

## 4. Empirical confirmation of the HyDE causal chain

Run: `tinker/scripts/diagnose_hyde.py` over all 19 queries, Gemini backend,
capped/no-think (the canonical HyDE config). Output:
`out/tinker/swcr/runs/hyde_diagnosis/hyde_diagnosis.json`.

### H1 (pool recall ceiling) — CONFIRMED

The candidate pool is the recall ceiling the reranker works within (rerank
scores the original query but cannot surface a passage the pool omitted).

| Pool source | mean recall@50 |
|---|---:|
| query embedding (raw_dense) | **0.993** |
| hypothesis embedding (HyDE) | **0.873** |

HyDE pool was **better on 0/19**, worse on 9/19, tied on 10/19. The query
embedding alone retrieves ~99% of all gold into the top-50 — **the embedder
has essentially already solved the retrieval step on this corpus.** There is no
query→document asymmetry gap left for HyDE to bridge; swapping the query out for
a hypothesis can only lose gold, and it does (−0.12 mean ceiling).

Side-finding: raw_dense final recall@10 is 0.589 while its pool recall@50 is
0.993 — so the gold is in the pool but the **reranker** only lifts ~59% of it
into the top-10. On this corpus the reranker (or top_k), not retrieval, is the
binding constraint. Orthogonal to HyDE, but relevant to any future quality work.

### H2 (prior-contamination + confabulation drift) — CONFIRMED, worse than predicted

The hypotheses are generic-D&D-flavored *and* actively confabulate structure
from the glossary vocabulary we inject (the M1 shape-prior mechanism is part of
the damage). Three worst losers:

- **s18 recovery/rest (delta −0.45):** hypothesis writes a generic D&D healing
  block ("1 hp/day rest, long-term care 2 hp/day, *Goodberry*, Resurrection with
  XP penalties"). The actual gold is SWCR's idiosyncratic **Subdual Damage** rule
  (recovers 1 hp *per hour*) — never imagined by the hypothesis.
- **s12 morale/reaction (delta −0.29):** hypothesis fabricates a tidy
  "1-3 Hostile / 4-6 Unfriendly / …" reaction table with invented entries
  ("offer Invulnerability", "Initial Equipment"). The gold passage is SWCR's
  prose **Negotiation and Diplomacy** rule, which explicitly says *"Do not
  replace them with die rolls!"* — nearly the opposite of the hypothesis.
- **m01 social resolution (delta −0.33):** hypothesis stitches glossary terms
  ("Declare Spells: Command … Banishing Undead", "Druidic Hierarchy",
  "Fighter-Thief") into a plausible-looking but fabricated procedure.

The failure is bias, not variance (confirmed independently by uncapping /
thinking not helping in the grid): a longer, better-written hypothesis still
embeds near the wrong (generic-D&D) neighborhood. Feeding the model the corpus
glossary did not anchor it to SWCR; it gave it tokens to confabulate with.

### Verdict

Both links of the §1 causal chain hold at the population level. HyDE is the wrong
tool against a strong instruction-tuned embedder on a niche corpus: the embedder
removes HyDE's reason to exist, and the LLM prior makes the hypothesis an active
liability. This is the empirical spine of the §2 bitter-lesson reading.

### Confound found later (2026-05-30): the shape-prior bridge was weak

A follow-up review (prompted by the question "but we gave HyDE the glossary as a
bridge — why did it still drift?") found the bridge was nearly empty of the right
content. The intent-bearing route does inject a shape prior (cluster shapes +
glossary terms), but the M1 glossary is a 130-term **regex grab-bag** with low
recall and noise — it contains a credits line ("Additional proofreading and
suggestions") and is MISSING the rule concepts the failing queries needed
(subdual / morale / reaction / negotiation / rest all absent). So the
hypothesizer was handed noisy, often-irrelevant terms, used what it was given
(visible confabulation from injected class-feature terms in §4's m01 example),
and filled the rest from its prior.

Consequence for the verdict: the fair claim is **"HyDE with this (weak) shape
prior failed,"** not "HyDE-with-shape-prior is obsolete." The drift mechanism (§1)
is real but its *cause* is refined: weak bridge + fallback to prior, not an
inherent inability to know the domain. What survives independently is the
embedder-ceiling argument — the raw query already pulls 0.993 of gold into the
top-50, so even a perfect bridge has almost no headroom to beat it. M9 re-tests
HyDE with a proper LLM-built glossary to put the system's described performance on
the record and separate "weak bridge" from "no headroom."
