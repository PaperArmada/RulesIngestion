# Milestone M7 — Enumeration Route (first cross-paradigm route)

**Status:** Planned. Follows the M6 decision
([REPORT-Intent-Routed-Retrieval-v0.md](../Reports/REPORT-Intent-Routed-Retrieval-v0.md)).
**Thesis under test:** routing earns its keep on *quality* only when it routes to
a mechanism that is a different *primitive* from similarity search. Enumeration
is the cleanest such case: "give me every X matching Y" is set-completion, not
nearest-neighbor. A top-K similarity baseline structurally cannot return a
complete set; a predicate filter can.

This is the experiment M6 named. It is a **new milestone**, not a continuation of
M5, because it requires its own queries and gold — the current 19-query atomic
benchmark contains no enumeration queries.

---

## 1. Why this is a fair test (and M5 wasn't)

M5 pitted flavors of similarity search against each other (HyDE-dense, hybrid,
dense), and the strong embedder won the simplest one. Enumeration is off that
axis entirely:

- The answer is a **set defined by a predicate**, not the top-K most similar
  passages. Correctness is "did you return exactly the matching units," not
  "is the best one ranked first."
- Sets are often large. On SWCR: 183 Magic-User units, 41 spell-level-5 units,
  170 `1d6` damage_dice units. Any top-20 retriever caps out far below the true
  set size, so its recall is bounded by K/|set| regardless of embedder quality.
- The mechanism has **no embedding step**: NL query → predicate → scan typed
  metadata → return all matches. One cheap structured LLM call (predicate
  extraction), then deterministic filtering.

If enumeration beats raw_dense on enumeration queries, that is routing winning on
quality for the first time in this project — on a cross-paradigm basis, not a
human-ontology one.

---

## 2. What we have to build on

`out/tinker/swcr/corpus_self_portrait.json` `metadata_index` already provides
per-unit typed metadata (`by_unit`) and a `summary` of enumerable dimensions:

| Dimension | distinct values | example counts |
|---|---:|---|
| `classes` | 10 | Magic-User 183, Cleric 108, Druid 87, Fighter 49 |
| `spell_levels` | 9 | L5 41, L6 41, L4 41, L3 31 |
| `damage_dice` | 20 | 1d6 170, 1d4 88, 2d6 56, 1d8 55 |
| `hit_dice` | 18 | 1 → 11, 9 → 3, 12 → 3 |
| `armor_class` | 15 | mixed asc/desc notation (see caveats) |
| `alignment` | 4 | Evil 14, Chaotic 11, Lawful 11, Neutral 10 |

568/793 units carry metadata. The filter substrate exists; M7 adds the NL→predicate
front end, the scan, set-aware metrics, and the gold.

---

## 3. Deliverables

- `tinker/routing/enumeration.py` — `run_enumeration(query, metadata_index, …) -> RouteResult`.
  - `llm.extract_predicate(query, enumerable_schema) -> {field, op, value(s)}` (new
    role; structured JSON; one call). `enumerable_schema` is the `summary` field
    list + value vocabularies so the model maps NL terms to canonical values
    (e.g. "wizard" → `Magic-User`, "third level" → `spell_levels=3`).
  - Deterministic scan over `by_unit`; return **all** matching unit_ids (ordered
    by page/structural_path for stability). No ranking, no top-K truncation.
  - Debug payload: parsed predicate, matched count, units lacking the field.
- Wire `enumeration` bucket in `dispatch._bucket_to_runner` to the new runner
  (currently falls back to `entity_anchored`). Add to `_IMPLEMENTED_BUCKETS`.
- `tinker/eval/enumeration_gold.py` + `tinker/scripts/build_enumeration_gold.py`
  — author 10–15 NL enumeration queries; derive each query's gold set as the
  result of the *intended* predicate applied to `by_unit` (the metadata is the
  ground truth for "all level-3 spells"), human-verified. Write
  `out/tinker/swcr/enumeration_gold.json`.
- Set-aware metrics in the harness (or a sibling): **set precision / recall / F1**
  and **exact-set-match**, replacing MRR/recall@K for these queries. Report
  raw_dense (top-K, and top-|set| as a generous ceiling) vs enumeration route.
- `tinker/scripts/run_enumeration_eval.py` — CLI.
- Tests: `tests/tinker/test_enumeration.py` — predicate parsing on monkeypatched
  LLM; scan correctness on a synthetic metadata index; dispatch wires the bucket
  to the new runner.

---

## 4. Test gate

- Predicate-parse test passes on a fixture (synonyms map to canonical values).
- Scan returns the exact set on a synthetic index (no truncation, no metadata-less
  units leaking in).
- On the authored gold: report set-F1 for enumeration route vs raw_dense.
  **Success signal:** enumeration route set-F1 materially exceeds raw_dense on
  enumeration queries (expected by construction when |set| > K; the real question
  is whether NL→predicate parsing is reliable enough to realize it).

## 5. Verification

`uv run python -m tinker.scripts.run_enumeration_eval --gold out/tinker/swcr/enumeration_gold.json …`
prints per-query parsed predicate, |returned| vs |gold|, set-P/R/F1, and the
raw_dense comparison. Inspect 3 queries by hand: predicate correct? set complete?

## 6. Risks / honest caveats

- **NL→predicate parsing is the new failure surface.** The route's quality now
  depends on mapping "wizard"→Magic-User, "third-level"→spell_levels=3, etc. If
  parsing is unreliable, enumeration loses its structural advantage. This is the
  thing actually being tested; report parse accuracy separately from set-F1.
- **Metadata coverage is partial** (568/793). Units without the queried field are
  invisible to enumeration; gold must be defined over the metadata-bearing subset
  or the route is unfairly penalized for missing data, not bad logic.
- **Messy dimensions.** `armor_class` mixes ascending/descending notation
  (`7[12]`, `6 [13]`); `hit_dice` has `1+4`. Start with clean dimensions
  (`classes`, `spell_levels`, `damage_dice`, `alignment`); defer AC/HD.
- **Gold circularity.** Gold is metadata-derived, so it tests NL→predicate +
  execution, not the metadata extraction itself (that was M1's job). State this
  plainly; it's a test of the *route*, given the substrate.
- **Small N.** 10–15 queries, one corpus. A positive result is directional
  evidence for cross-paradigm routing, not proof.

## 7. Decision this milestone informs

If enumeration beats raw_dense on set-F1 with acceptable parse accuracy:
**cross-paradigm routing is validated** — proceed to the next non-similarity
route (structural or cross-reference) and reframe the router around
"is this a similarity problem at all," per M6.

If NL→predicate parsing is too unreliable to realize the structural advantage:
the bottleneck is query understanding, not routing — document and reconsider.
