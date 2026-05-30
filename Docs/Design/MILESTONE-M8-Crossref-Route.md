# Milestone M8 — Cross-Reference Traversal Route (2nd cross-paradigm route)

**Status:** Done. Confirms a *second* non-similarity paradigm beats similarity,
so M7's enumeration win wasn't enumeration-specific.
**Companion:** [MILESTONE-M7](MILESTONE-M7-Enumeration-Route.md),
[ANALYSIS](ANALYSIS-Routing-and-HyDE-Bitter-Lesson.md).

## Thesis

Cross-reference is a **graph** relation, not a similarity one. Two query types,
both anchored on a resolved graph node (a glossary term):
- **references** (1-hop reverse): units that mention X.
- **depends_on** (k-hop forward closure, k=2): the transitive dependency closure
  reachable from X's defining unit — the genuinely-graph capability neither
  dense nor BM25 can compute.

Graph re-seeded on the M9 LLM glossary (811 terms → 5898 edges, vs the M1
130-term/1949-edge graph), so M8 doesn't inherit the weak-glossary confound.

## Result (24 auto-gen queries, paraphrased, Gemini)

Three-way set-F1: crossref traversal vs dense @top-|gold| vs BM25 @top-|gold|.

| segment | crossref | dense | bm25 | resolution |
|---|---|---|---|---|
| **depends_on** (transitive) | 1.000 | **0.088** | **0.053** | 12/12 |
| references (1-hop mention) | 1.000 | 0.389 | 0.076 | 12/12 |

- **Transitive closure is the decisive, clean win.** Dense and BM25 both score
  ~0.05–0.09 — neither can compute a 2-hop dependency closure; only a graph
  traversal can. crossref reproduces it exactly.
- **A prediction was refuted:** "1-hop references ≈ BM25 (just lexical)" was
  wrong. BM25 on the verbose NL query (0.076) cannot isolate the entity, so dense
  (0.389) beats it; the crossref route wins by *resolving to the node first*. The
  advantage on references is entity-resolution + exact membership, not deep
  paradigm — but it is still real against naive dense/BM25 on the query.
- **Resolution held 24/24 on paraphrased queries** (NL → correct graph node +
  relation direction).

## Honest caveats

- **Circularity (stronger than M7's).** The route and the gold read the *same*
  graph, so crossref = 1.000 by construction. The independently-measured skills
  are (a) node+mode resolution on paraphrases (24/24) and (b) the *structural
  inability* of dense/BM25 to reproduce graph sets — especially the transitive
  closure, which is the generalizable finding.
- **Gold is operationalized from mention edges.** "references" gold = units
  containing the term; "depends_on" gold = the BFS closure over mention edges.
  These are reasonable operationalizations, not a human-curated dependency truth.
- **Node quality varies.** Auto-selected content nodes still include a few
  marginal ones (monster names like Hydrae/Shadows, OCR-cased "tREASuRE"); a
  facet/node-quality filter (the same gap noted in M7) would tighten this.
- **Single corpus / n=24.** Directional, not definitive.

## Verdict

Cross-reference graph traversal is a second non-similarity paradigm where routing
wins on quality, decisively for the transitive case. Combined with M7
(enumeration), **"route the queries where similarity is the wrong primitive"
holds across two distinct paradigms** — the surviving form of the original
routing thesis (M6) is now validated twice. Similarity-based retrieval (dense or
lexical) structurally cannot serve set-completion or graph-reachability queries;
a cheap LLM resolves the NL to the right discovered structure and the traversal
does the rest.
