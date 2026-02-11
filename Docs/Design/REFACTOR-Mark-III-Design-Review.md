# Mark III Design Refactor — Architecture Review Findings

**Status:** Proposed — all items accepted, none yet implemented  
**Date:** 2026-02-09 (updated 2026-02-10 with additional critique integration)  
**Scope:** Design-level changes to RULES_INGESTION_MARK_III_UPDATE.md and downstream contracts  
**Source:** External design review against implementation state, plus follow-up critique analysis

---

## Guiding Principle

Every item here was accepted because it either:

- Closes a gap between the design doc and real TTRPG PDF behavior,
- Resolves a tension between two competing concerns the design doesn't acknowledge, or
- Adds a concrete mechanism where the current design is hand-wavy.

Nothing here contradicts the core thesis (prose-first, evidence-bound, provenance-anchored). Everything strengthens it.

---

## R1 — Stage Naming Alignment

**Problem**

The UPDATE design doc numbers stages: A=Extraction, B=Prose, C=Evidence, D=Enrichment, E=Graph, F=Evaluation. The implementation uses: A=Prose, B=Evidence, A'=Enrichment, retrieval_lab=Evaluation. Graph construction is not yet implemented under either naming.

When someone writes "Stage C" in a handoff or issue, it's ambiguous whether they mean the design doc's "Evidence Binding" or the implementation's "Graph Construction" (per STAGE_C_CONTRACTv2.md, which uses the implementation numbering).

**Safety Argument:** This is not cosmetic. The `stage_a_prime_contract` currently says A' consumes EvidenceUnits "produced by Stage A," but in Mark III's UPDATE numbering EvidenceUnits are Stage C output (A renders, B reconstructs, C binds). If someone wires A' to consume Stage A output instead of Stage B/C output based on the naming, they get raw markdown instead of EvidenceUnits — an evidence leakage bug that silently breaks the admissibility boundary. Unified naming prevents this class of wiring error.

**Decision**

Pick one numbering. Since the implementation is already deployed and STAGE_C_CONTRACTv2.md already exists with graph construction semantics, the design doc should align to implementation naming:

| Implementation Stage | Responsibility                    | Design Doc Equivalent |
| -------------------- | --------------------------------- | --------------------- |
| Stage A              | Extraction + Prose Reconstruction | Stages A + B          |
| Stage B              | Evidence Binding                  | Stage C               |
| Stage A'             | LLM Enrichment (retrieval-only)   | Stage D               |
| Stage C              | Graph Construction                | Stage E               |
| Retrieval Lab        | Evaluation                        | Stage F               |

**Action**

- [ ] Update RULES_INGESTION_MARK_III_UPDATE.md to use implementation stage names
- [ ] Add a "Naming History" appendix noting the renumbering so old handoffs remain interpretable
- [ ] Audit all handoff docs, specs, and SCHEMAS.json for stale stage references
- [ ] Fix stage_a_prime_contract to explicitly state "A' consumes Stage B EvidenceUnits" (not Stage A output)
- [ ] Verify no code paths wire raw Stage A output into A' or Stage C

**Risk:** Low. Pure documentation change, no code impact. But the wiring audit is load-bearing — a naming fix that doesn't verify actual wiring is incomplete.

---

## R2 — Parent-Fetch Primitive (Replace expand_context)

**Problem**

EvidenceUnit serves as both the retrieval unit and the provenance anchor. These two roles have opposing size pressures:

- **Provenance** wants authorial-intent boundaries (a paragraph, a table row, a callout). These range from ~15 tokens ("You gain +2 to Fortitude saves") to ~800 tokens (a full spell description).
- **Retrieval** wants units sized for embedding model context windows (256–512 tokens). Units that are too small embed poorly (insufficient semantic signal); units that are too large dilute the relevant sentence.

The current `expand_context` mechanism (fetching neighbor EvidenceUnits by ordering key) is too blunt: benchmarks show it regresses badly on S&W and Starfinder while helping PHB. The operation is expensive and doesn't respect structural boundaries — it grabs neighbors by sequence position, which may cross section boundaries and dilute relevance.

**Why Not a RetrievalView Merge Layer**

An earlier version of this item proposed a full RetrievalView layer that merges/windows EvidenceUnits for indexing. That adds a new indexing substrate, complicates the provenance chain, and forces a decision about where enrichment attaches (to EvidenceUnits or RetrievalViews?). The critique identifies a cleaner alternative: keep retrieval ranking on EvidenceUnits, but add a deterministic **parent-fetch** at answer-time.

**Proposed Design: Parent-Fetch Primitive**

Retrieval continues to rank and score individual EvidenceUnit IDs. But when candidates are passed to answer synthesis, each candidate carries an optional **parent scope payload** — a deterministic expansion of context defined by structural containment, not sequence proximity.

```
Query → Retrieval (ranks EvidenceUnits) → Top-k candidates
    ↓
Parent-Fetch (deterministic section-scoped expansion)
    ↓
Answer Synthesis receives: [candidate EvidenceUnit + parent context]
```

**Parent scope definition:**

The "parent" of an EvidenceUnit is the deterministic set: `{all EvidenceUnits sharing the same Section node in the Stage C structural graph}`, capped by a character budget. If Stage C is not yet built, fall back to `{all EvidenceUnits sharing the same structural_path prefix up to depth N}`.

**Concretely:**

- Retrieval candidate is still an EvidenceUnit ID (ranking is unit-level)
- "Parent" is a deterministic set defined by structural containment, not neighbor proximity
- Parent context is used for **answer-time reading only** — never for gold scoring, never for Stage C semantics
- Metrics continue to score on the child EvidenceUnit ID only
- Parent policy is reported as metadata: `context_policy=section_parent(depth=k, cap=N_chars)`

**Schema Sketch**

```python
@dataclass
class RetrievalCandidate:
    unit_id: str                    # the ranked EvidenceUnit
    score: float                    # retrieval score
    parent_unit_ids: list[str]      # deterministic section-scoped expansion
    parent_text: str                # concatenated parent context (capped)
    context_policy: str             # e.g., "section_parent(depth=2, cap=4000)"
```

**Why This Is Better Than expand_context:**

| Property                    | expand_context                            | Parent-Fetch                               |
| --------------------------- | ----------------------------------------- | ------------------------------------------ |
| Scope definition            | Sequence neighbors (±N by ordering_key)   | Structural containment (same section)      |
| Respects section boundaries | No                                        | Yes                                        |
| Cost                        | Expensive (doubles candidate set)         | Cheap (fetched post-ranking on top-k only) |
| Gold contamination          | Expanded context counted in gold matching | Parent is answer-context only, never gold  |
| Regression risk             | High (shown in benchmarks)                | Low (structural, not positional)           |

**Action**

- [ ] Define parent-scope resolution rules (structural_path prefix matching, depth parameter)
- [ ] Implement parent-fetch as a post-retrieval step (operates on top-k only, not full corpus)
- [ ] Set character budget cap for parent payloads (start with 4000 chars, tune)
- [ ] Update retrieval_lab to report parent-fetch metadata without contaminating gold metrics
- [ ] Deprecate expand_context once parent-fetch is validated
- [ ] Baseline comparison: expand_context vs. parent-fetch on all corpora (PHB, S&W, Starfinder)

**Risk:** Low-medium. Structurally cleaner than expand_context and cheaper to compute. Main risk is that the Stage C structural graph isn't built yet — but the fallback (structural_path prefix) is available immediately from Stage B output.

**Dependency:** Benefits from R4 (Stage C graph provides the Section nodes for containment). Works without it via structural_path fallback.

---

## R3 — Cross-Page Continuity Pass

**Problem**

TTRPG rulebooks constantly split content across page boundaries:

- A paragraph starts on page 72 and finishes on page 73
- A table header is on page N and rows continue on page N+1
- A bulleted list continues across a page break

Stage B currently produces per-page ASTs. When content splits across pages, the result is two incomplete EvidenceUnits where one complete unit should exist. This is arguably a _worse_ provenance violation than a documented join — the "verbatim text" of each half-unit isn't what the author wrote.

Section 6.3 forbids "cross-page joins without auditable rules," but the key phrase is "without auditable rules." Deterministic, rule-based joins are consistent with the design philosophy.

**Proposed Design**

Add a **cross-page join pass** as the final step of Stage B (after per-page evidence binding, before gates). The pass operates on ordered EvidenceUnits from consecutive pages.

**Join Rules (deterministic, auditable):**

1. **Split paragraph detection:**

   - Last EvidenceUnit on page N is `unit_type=prose`
   - It ends without terminal punctuation (no `.`, `!`, `?`, `:`)
   - First EvidenceUnit on page N+1 is `unit_type=prose`
   - First unit does NOT begin with a heading or a markdown structural marker
   - → Merge into single unit. Record `join_type=split_paragraph` in metadata.

2. **Split table detection:**

   - Last EvidenceUnit on page N is `unit_type=table`
   - First EvidenceUnit on page N+1 is `unit_type=table`
   - Page N+1 table has no header row (or header matches page N table)
   - → Merge into single unit. Record `join_type=split_table`.

   **Table Group ID (first-class continuity artifact):** Beyond binary merge, tables that continue across pages (or that are logically related within a section) should carry a `table_group_id` derived deterministically from: AST adjacency + identical header row hash + page ordering. This is still "structure-only" (not semantics) and gives retrieval-time parent-fetch (R2) a better unit of expansion than "neighbor page."

   ```python
   # Deterministic table group identity
   table_group_id = blake3(header_row_hash + "|" + structural_path_joined)
   ```

   Tables sharing a `table_group_id` are treated as a continuation group. The parent-fetch primitive (R2) can expand to the full group when any member is a retrieval hit, giving answer synthesis the complete table without polluting gold metrics.

3. **Split list detection:**
   - Last EvidenceUnit on page N is `unit_type=list`
   - First EvidenceUnit on page N+1 is `unit_type=list`
   - Page N+1 list items continue the numbering or bullet pattern
   - → Merge into single unit. Record `join_type=split_list`.

**Joined units:**

- `page_fingerprint` becomes a list (both pages)
- `source_line_start/end` annotated with page origin
- `anomaly_flags` includes `cross_page_join`
- `join_metadata` records the join type and the rule that triggered it

**Gate:**

- Cross-page join rate gate: if >30% of units are joined, something is wrong (likely a parsing failure, not real content splits). Flag for manual review.

**Action**

- [ ] Design join rules formally (the three above are a starting point, not exhaustive)
- [ ] Decide: does the join pass live inside Stage B or as a B-postprocess?
- [ ] Implement join pass
- [ ] Update EvidenceUnit schema for multi-page provenance (`page_fingerprints: list[str]`)
- [ ] Add `table_group_id` field to EvidenceUnit (or as Stage B metadata)
- [ ] Implement table group detection (header hash + structural path + page adjacency)
- [ ] Wire table groups into parent-fetch (R2) as an expansion unit
- [ ] Add cross-page join gate
- [ ] Test on known split-content pages from Brutal Pages suite

**Risk:** Medium. The join rules must be conservative — a false join is worse than a missed join, because it corrupts provenance. Err toward false negatives (leave units split) rather than false positives (merge things that shouldn't be merged).

---

## R4 — Graph Construction Contract Expansion (Stage C)

**Problem**

The UPDATE design doc gives graph construction (Stage E in its numbering) exactly 12 lines of specification. STAGE_C_CONTRACTv2.md is much more detailed and is closer to implementation-ready, but several critical questions remain unaddressed.

**Gaps to Close**

### 4a. Entity Disambiguation

TTRPG text is full of polysemy: "Fighter" (class) vs. "fighter" (narrative role), "Channel Energy" (cleric feature) vs. "channel energy" (narrative description). The contract says "canonical label = surface form as printed" but doesn't specify how to distinguish between homographs.

**Proposed Rule:** Entity disambiguation is scoped by `structural_path`. An entity extracted from `["Chapter 3: Classes", "Fighter"]` is a different canonical entity than one from `["Chapter 7: Combat", "Fighting"]`, even if the surface form overlaps. Entity ID should incorporate structural scope:

```
entity_id = hash(book_id + entity_type + canonical_label + section_scope)
```

Where `section_scope` is the top-level section from `structural_path`.

### 4b. Edge Type Enumeration

STAGE_C_CONTRACTv2.md lists: CONTAINS, NEXT_EVIDENCE, MENTIONS, ASSERTS, ABOUT, APPLIES_UNDER, OVERRIDES. This is a good starting set but missing:

- `REQUIRES(entity → entity)` — prerequisite relationships ("Requires: Weapon Focus")
- `MODIFIES(fact → fact)` — one rule modifying another ("This replaces the normal critical hit damage")
- `SUPERSEDES(entity → entity)` — later printing or errata replacing earlier content

**Recommendation:** Enumerate the complete edge vocabulary before implementation. Each edge type needs: definition, extraction rule (how is it detected in text), directionality, and a test case.

### 4c. Graph Query Model

Section 14 says "graphs constrain and explain; they do not retrieve." This should be expanded to specify exactly how the answer synthesis layer (Section 11) interacts with the graph:

- Does the answer layer traverse the graph?
- Does it use the graph for re-ranking retrieved EvidenceUnits?
- Does it use admissibility gates to filter candidates?
- What's the interface? (query → subgraph? query → filtered EvidenceUnit set?)

### 4d. Cross-Document Entity Resolution

When the same entity (e.g., "Magic Missile") appears in multiple books (core rulebook + supplement), how are they related? Options:

- Same entity (merge evidence)
- Different entities (one per book)
- Same entity with SUPERSEDES edge (errata/reprints)

**Action**

- [ ] Resolve entity disambiguation approach (structural scope in ID)
- [ ] Enumerate complete edge vocabulary with definitions and test cases
- [ ] Specify graph query model (how answer synthesis consumes the graph)
- [ ] Define cross-document entity resolution rules
- [ ] Update STAGE_C_CONTRACTv2.md with all of the above
- [ ] Design acceptance tests for graph construction

**Risk:** High if under-specified, low if done thoroughly before implementation. This is the "measure twice, cut once" stage.

---

## R5 — OCR Migration Path and Content Versioning

**Problem**

Section 13 acknowledges model-mediated variability in Stage A but the practical consequence is that the entire downstream pipeline is pinned to a specific OCR run. When OCR improves (model upgrade, parameter tuning, bug fix), every downstream hash changes. Gold sets become invalid. Cached enrichments are stale. There's no way to compare retrieval quality across OCR generations.

**Proposed Design**

Add a `content_version` field to EvidenceUnit (and upstream artifacts) that identifies the OCR generation:

```python
@dataclass
class EvidenceUnit:
    # ... existing fields ...
    content_version: str   # e.g., "deepseek-ocr2-v1.0-dpi200"
```

This enables:

- Maintaining multiple OCR generations side-by-side
- Comparing retrieval quality across OCR versions
- Incremental migration (re-OCR high-value pages first, then the long tail)
- Gold set versioning (gold sets tagged with which content_version they were grounded against)

**Action**

- [ ] Add `content_version` to StageARecord, EvidenceUnit schemas
- [ ] Define version string format (model + version + parameters)
- [ ] Design migration workflow: re-OCR → re-run Stage B → diff → re-ground gold sets
- [ ] Update retrieval_lab to support multi-version comparison
- [ ] Document in design doc Section 13

**Risk:** Low. Additive schema change with no impact on existing pipeline.

---

## R6 — Relational Enrichment in Stage A'

**Problem**

Stage A' enrichment fields are all unit-local: summaries, tags, paraphrases, anchors. But the hardest retrieval failures in TTRPG rules are compositional:

- "Can a 5th-level Mystic cast 3rd-level spells?" requires the Mystic spell progression table AND general spellcasting rules.
- "What happens when Sneak Attack and Critical Hit overlap?" requires both class features plus general critical hit rules.

Unit-local enrichment cannot help here because no single EvidenceUnit contains the full answer.

**Proposed Design**

Add a **relational enrichment** field to the Stage A' schema — safe, non-authoritative annotations that flag retrieval co-dependence:

```python
class APrimeEnrichment(BaseModel):
    # ... existing fields ...

    co_retrieval_hints: list[CoRetrievalHint] = []
    # "To answer questions involving this unit, also retrieve units about..."

class CoRetrievalHint(BaseModel):
    related_topic: str          # controlled vocabulary term or entity mention
    relationship: str           # "prerequisite" | "exception_to" | "modifies" | "requires_context"
    confidence: Literal["explicit", "strong_inference"]
    # Only "explicit" hints are used; "strong_inference" logged but not acted on
```

**Authority Constraints (non-negotiable):**

- These are retrieval hints, NOT authority claims
- Tagged `authority=none`, `citation_policy=never_cite` (same as all Stage A' output)
- Never used for grounding or citation — only for expanding the retrieval candidate set
- The hint says "look for related content," not "this content is related"

**Example:**
An EvidenceUnit containing "At 5th level, a Mystic gains access to 3rd-level spells" would get:

```json
{
  "related_topic": "spellcasting rules",
  "relationship": "requires_context",
  "confidence": "explicit"
}
```

**Action**

- [ ] Design CoRetrievalHint schema
- [ ] Define controlled relationship vocabulary
- [ ] Update Stage A' prompt to extract hints
- [ ] Implement retrieval expansion using hints (expand candidate set, not rewrite query)
- [ ] Measure impact: baseline vs. hint-expanded retrieval on compositional gold queries
- [ ] Verify authority wall: hints never leak into citations or grounding

**Risk:** Medium. The danger is scope creep — hints that slide toward semantic inference. Mitigated by the `confidence` field (only act on "explicit") and the existing authority wall.

---

## R6b — Promote Stage A' to Standard Path

**Problem**

Stage A' is currently positioned as optional experimentation — enrichment that "may help" retrieval. But A' is the designed solution for the most common retrieval failure: admissible EvidenceUnits that are semantically correct but insufficient without parent context. The "Using a Higher-Level Spell Slot" problem (a unit that is admissible but meaningless without its parent rule) is exactly what A' was built to mitigate.

The A' schema already encodes `requires_parent`, `delta_only`, and `questions_answered` — the machinery is there. The problem is positional: A' is treated as experimental rather than as the standard fix.

**Proposed Change**

Promote A' from "optional enrichment experiment" to "standard pipeline stage that runs on every ingestion." The design doc should reflect this:

1. **Stage B stays strict** about admissibility — no semantic interpretation, no enrichment, no inference. This is non-negotiable and the critique confirms it.

2. **Stage A' is the standard path** for making the retrieval surface robust to paraphrase, flagging parent-dependent units, and generating `questions_answered` that improve recall without becoming evidence.

3. **The authority wall remains absolute** — A' output is `admissibility=non_evidence`, `citation_policy=never_cite`, `stage_c_visibility=hidden`. Nothing changes about what A' is allowed to do. What changes is whether it runs.

**Why This Matters**

Without A', the pipeline produces EvidenceUnits that are correct but often insufficient for retrieval. A 15-token unit like "You gain +2 to Fortitude saves" will:

- Embed poorly (no semantic context)
- Miss paraphrased queries ("What bonuses do I get to saving throws?")
- Lack any signal that it needs its parent context

A' fixes all three: it adds a summary (embedding context), question paraphrases (paraphrase robustness), and `requires_parent` / `delta_only` flags (parent-fetch signal for R2).

**Concretely:**

- Mark III design doc: change "Stage D — LLM Enrichment (Retrieval-only annotations)" from "optional" to "standard"
- Pipeline: `run_a_b_aprime()` becomes the default pipeline function, not `run_a_b()`
- Retrieval Lab: baselines should report both pre-A' and post-A' metrics, but post-A' is the production configuration
- A' flags (`requires_parent`, `delta_only`) become inputs to the parent-fetch primitive (R2)

**Action**

- [ ] Update RULES_INGESTION_MARK_III_UPDATE.md to position A'/Stage D as standard, not optional
- [ ] Make `run_a_b_aprime()` the default pipeline entry point
- [ ] Wire A' flags into parent-fetch (R2): units with `requires_parent=true` or `delta_only=true` automatically trigger section-scoped parent expansion at answer time
- [ ] Continue reporting pre-A' baselines for measurement purposes (the "floor" remains valuable)
- [ ] Document the rationale: "Stage B is strict; A' makes it retrievable"

**Risk:** Very low. A' is already implemented and tested. This is a positioning change that makes the pipeline default match the design intent.

---

## R7 — Corpus-Aware Retrieval Policy Layer

**Problem**

Two related issues:

1. TTRPG rulebooks use highly specific, consistent terminology ("Fortitude save," "spell slot," "armor class," "base attack bonus"). Users asking about rules tend to use the exact same vocabulary. This means BM25 may be unexpectedly competitive on "lookup" queries while dense wins on "reasoning" queries. Generic 50/50 RRF fusion weights may not be optimal.

2. Benchmarks show "hybrid is best" for S&W and Starfinder but **harms** PHB. This isn't a bug — it's a signal that different corpora have different optimal retrieval configurations. Debating "dense vs. hybrid" globally is the wrong frame. The right frame is per-corpus retrieval policies.

**Proposed Design: Per-Corpus Retrieval Policy**

Instead of a single global retrieval mode, codify a **retrieval policy** per corpus with auto-tune hooks:

```python
@dataclass
class RetrievalPolicy:
    corpus_id: str
    mode: Literal["dense", "sparse", "hybrid"]
    fusion_alpha: float             # BM25 weight in hybrid (0.0 = pure dense, 1.0 = pure sparse)
    expand_context: bool            # deprecated, replaced by parent-fetch (R2)
    parent_fetch: ParentFetchConfig # R2 config
    reranker: str | None            # R11 reranker model, if any
    tuned_date: str                 # when this policy was last tuned
    baseline_metrics: dict          # metrics snapshot at tune time
```

**Policy lives in Retrieval Lab config**, not in Stage C. Stage C simply records retrieval mode/config in GraphDelta metadata (as the design already calls for).

**Tuning workflow:**

1. Run all retrieval modes on a corpus's gold set
2. Per-query breakdown: which mode wins per query type (lookup/reasoning/compositional/negative-space)
3. Select optimal mode + alpha per corpus
4. Record as RetrievalPolicy with metrics snapshot
5. Re-tune when pipeline changes (new enrichment, new embedding model, new gold queries)

**Simple version:** Per-corpus global alpha (e.g., PHB: 0.4 BM25, Starfinder: 0.7 BM25).

**Advanced version:** Per-corpus + per-query-type alpha, with a lightweight query classifier (regex or keyword-based, not LLM) that adjusts weights at query time.

**Action**

- [ ] Define RetrievalPolicy schema
- [ ] Add per-query dense vs. sparse comparison to retrieval_lab output
- [ ] Classify gold queries by type (manual tagging initially, aligned with R8 tiers)
- [ ] Analyze mode-by-type-by-corpus performance matrix
- [ ] Implement per-corpus policy selection in retrieval_lab
- [ ] Tune initial policies for PHB, S&W, Starfinder
- [ ] Document policies and tuning methodology in RETRIEVAL_LAB.md

**Risk:** Low. Pure measurement and configuration, no architectural change. The only new code is policy selection logic in retrieval_lab.

---

## R8 — Gold Set Taxonomy and Construction Methodology

**Problem**

The design mentions "nominated gold" and "gold audits" but doesn't specify how gold sets are constructed, who writes them, or how they're stratified. If gold sets are biased (over-representing easy lookups), metrics tell a flattering but misleading story.

**Proposed Gold Set Taxonomy**

Stratify gold queries by difficulty tier:

| Tier                         | Description                                         | Example                                                                          | Expected Retrieval Difficulty                  |
| ---------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------- |
| T1 — Direct Lookup           | Single unit, exact terminology match                | "What is the range of Magic Missile?"                                            | Low (BM25 likely sufficient)                   |
| T2 — Section Traversal       | Right section, answer spans a few paragraphs        | "What are the Operative's key ability scores?"                                   | Medium                                         |
| T3 — Compositional           | Multiple units from different sections required     | "Can a Solarian/Mystic multiclass use Stellar Revelations while casting spells?" | High                                           |
| T4 — Negative Space          | Answer is implied by absence, not stated directly   | "Can you use Sneak Attack with a grenade?"                                       | High (system should refuse or qualify)         |
| T5 — Contradictory/Ambiguous | Different source sections give conflicting guidance | Errata conflicts, optional/variant rule overlap                                  | Very High (system should surface the conflict) |

**Construction Rules:**

- Gold queries should be written by someone who hasn't seen the pipeline internals (reduces confirmation bias)
- Each gold query is tagged with its tier
- Each corpus should have gold queries distributed across all tiers (not just T1)
- Gold sets are versioned alongside the pipeline
- T4 and T5 queries should include `refusal_acceptable: true` flags

**Reporting:**

- All metrics (MRR, Hit@k, Recall@k) reported per-tier as well as aggregate
- Regression comparisons are per-tier (a regression on T3 matters more than an improvement on T1)

**Action**

- [ ] Define tier taxonomy formally (the five above, or refine)
- [ ] Tag existing gold queries with tiers
- [ ] Identify tier coverage gaps (likely under-represented: T3, T4, T5)
- [ ] Write additional gold queries to fill gaps
- [ ] Update retrieval_lab to report per-tier metrics
- [ ] Document gold set construction methodology in RETRIEVAL_LAB.md

**Risk:** Low. Purely additive to existing evaluation infrastructure.

---

## R9 — Unit Type as Retrieval Facet

**Problem**

EvidenceUnit has a `unit_type` field (prose, table, list, callout, heading) that is currently metadata only. But unit type is a strong retrieval signal: users asking "What are the requirements for X?" probably want a table or list. Users asking "How does X work?" probably want prose. Users asking about sidebars want callouts.

**Proposed Design**

Expose `unit_type` as a filterable facet in the retrieval index. This is:

- **Free** — no LLM cost, already computed
- **Deterministic** — same input always produces same type
- **Valuable** — can improve precision on type-specific queries

Implementation options:

1. **Soft boost:** Include unit_type as a feature in hybrid scoring (e.g., +0.1 for matching expected type)
2. **Hard filter:** Allow retrieval queries to specify required unit_type (e.g., "find tables about X")
3. **Post-retrieval re-rank:** After candidate retrieval, boost candidates whose type matches query intent

Start with option 1 (soft boost), measure impact, escalate to 2/3 if warranted.

**Action**

- [ ] Add unit_type to retrieval index metadata
- [ ] Implement soft boost in hybrid scoring
- [ ] Add query-type-to-unit-type heuristics (keyword-based)
- [ ] Measure impact on gold set retrieval
- [ ] Document in RETRIEVAL_LAB.md

**Risk:** Very low. Additive, reversible, cheap.

---

## R10 — Exception/Override Annotation

**Problem**

TTRPG rules are heavily exception-based: "Normally X, but if Y then Z." Knowing that an EvidenceUnit contains an exception — and ideally to _what_ general rule — is valuable for:

- **Retrieval:** Boost exception units when queries contain "can you," "what if," "does X override"
- **Answer synthesis:** Ensure exceptions are surfaced alongside general rules, not in isolation

**Proposed Design**

Add to Stage A' enrichment:

```python
class ExceptionAnnotation(BaseModel):
    is_exception: bool
    exception_to: str | None     # general rule or topic being modified
    exception_type: str          # "override" | "special_case" | "conditional" | "optional"
```

This is a retrieval hint (same authority wall as all Stage A' output). It tells the retrieval system "when you retrieve this unit, also consider retrieving the general rule it modifies."

This overlaps with R6 (relational enrichment) and could be implemented as a specific case of `CoRetrievalHint` with `relationship = "exception_to"`.

**Action**

- [ ] Decide: standalone annotation or subcase of CoRetrievalHint (R6)
- [ ] Update Stage A' prompt to detect exception patterns
- [ ] Measure prevalence of exception patterns in existing corpora
- [ ] Implement retrieval boost for exception co-retrieval
- [ ] Evaluate impact on T3/T4 gold queries (most likely to benefit)

**Risk:** Low. Natural extension of existing enrichment.

---

## R11 — Cross-Encoder Re-Ranking (Retrieval Lab Experiment)

**Problem**

Current retrieval modes (dense, sparse, hybrid) are all bi-encoder or lexical. For a rules-lookup system where precision is critical (wrong rule = wrong answer), fine-grained relevance discrimination on the top-k candidates could meaningfully improve quality.

**Proposed Design**

Add a cross-encoder re-ranking stage between hybrid retrieval and answer synthesis:

```
Hybrid Retrieval (top-k=50 candidates)
    ↓
Cross-Encoder Re-Ranker (score each candidate against query)
    ↓
Re-ranked top-k=10 for answer synthesis
```

Cross-encoders (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2` or similar) jointly encode query+document and produce a fine-grained relevance score. They're much more accurate than bi-encoders for relevance discrimination but too slow for full-corpus search — hence applying them only to the top-k candidates from the fast retrieval stage.

**Critical Boundary: Retrieval-Only, Never Semantics**

Reranking is "discoverability tooling," not semantic structure. It must remain a Retrieval Lab mode and, if promoted to production, a retrieval-layer operation in `hybrid_retriever`. It must **never** feed into Stage C.

Stage C continues to consume EvidenceUnits only and remains deterministic/non-LLM. The reranker changes the _order_ in which candidates are presented to answer synthesis, not the _admissibility_ of those candidates. This is the same boundary that separates retrieval (ranking) from grounding (authority).

```
Reranker output → answer synthesis (allowed)
Reranker output → Stage C graph construction (FORBIDDEN)
Reranker scores → gold set evaluation (FORBIDDEN — gold metrics use retrieval scores only)
```

**Action**

- [ ] Select cross-encoder model (balance quality vs. latency)
- [ ] Implement as a new Retrieval Lab mode: `hybrid+rerank`
- [ ] Benchmark: hybrid-only vs. hybrid+rerank on all gold tiers (per R8 taxonomy)
- [ ] Measure latency impact (must stay within acceptable response time)
- [ ] If valuable, integrate into DungeonMindServer's hybrid_retriever as a retrieval-layer option
- [ ] Document Stage C boundary explicitly: reranker output never enters graph construction

**Risk:** Low-medium. Well-understood technique, main concern is latency budget. Since this is a rules-lookup system (not real-time chat), some latency is acceptable. The Stage C boundary rule prevents the most dangerous failure mode (reranker scores leaking into semantic structure).

---

## Explicit Non-Changes

Items considered and deliberately rejected. Recording the reasoning so they don't get re-proposed.

### No Ontology / OWL / RDF Layer

The critique gestures at formal ontology. This is a huge surface area that will tempt inference. Stage C's contract is explicitly "bounded extraction, no synonym inference, no cross-book resolution." Introducing OWL/RDF would:

- Create pressure to infer relationships not explicit in the text (violates "no silent inference")
- Add a complex dependency (OWL reasoner) that doesn't earn its keep at current scale
- Tempt "closed-world assumption" reasoning that TTRPG rules don't support (rules are open-world by design — supplements add new rules constantly)

Richer semantics can be layered later, but only after canonical grounding is boring and stable. The current graph design (typed edges, evidence-bound entities, explicit facts) is sufficient for the retrieval and grounding needs.

### No Vision-Guided Chunking _Replacing_ the Prose Spine

**Clarification:** Mark III already uses vision-guided structural labeling. DeepSeek OCR outputs bounding boxes that explicitly label structure — titles, stat blocks, body text, "higher-level spell slot" callouts, etc. This is visible in the OCR debug output (`result_with_boxes.jpg`). The vision model's structural understanding feeds directly into Stage A's AST construction.

What is rejected is making **visual layout the authoritative substrate** instead of the prose reconstruction. The distinction:

- **What we do:** Vision model (DeepSeek OCR) → structured markdown → AST → EvidenceUnits. The vision model _informs_ structure; the AST _is_ the authority.
- **What we reject:** Bounding boxes directly defining chunk boundaries, authority derived from spatial position rather than prose content, or bypassing the AST to go straight from layout regions to retrieval units.

The spine is: vision model produces prose → prose is parsed into AST → AST is segmented into EvidenceUnits. Vision is an input to this process, not a replacement for it. The critical invariant is that EvidenceUnit boundaries are determined by authorial structure (headings, paragraphs, tables), not by pixel coordinates.

The remaining gaps are handled by:

- **Continuity primitives** (R3: cross-page joins, table groups) — for cases where per-page processing loses authorial structure
- **Parent-fetch** (R2) — for structural context at answer-time

### No Changes to Core Spine (Stages A → B → C)

The critique confirms that ingestion quality is the bottleneck and authority boundaries must be explicit. That is exactly what Stages A/B and the Stage C contract are doing. The deterministic ingestion spine is the strongest part of the architecture and should not be weakened to accommodate retrieval convenience.

---

## Priority Ordering

Roughly ordered by impact-to-effort ratio and dependency chain:

| Priority | Item                                      | Effort   | Impact                                              | Dependencies                                 |
| -------- | ----------------------------------------- | -------- | --------------------------------------------------- | -------------------------------------------- |
| 1        | R1 — Naming Alignment                     | Low      | High (unblocks communication, prevents wiring bugs) | None                                         |
| 2        | R6b — Promote A' to Standard Path         | Very Low | High (makes pipeline default match design intent)   | None                                         |
| 3        | R8 — Gold Set Taxonomy                    | Low      | High (unblocks honest measurement)                  | None                                         |
| 4        | R7 — Corpus-Aware Retrieval Policy        | Low      | Medium-High (per-corpus tuning)                     | R8 (need tiered gold sets)                   |
| 5        | R9 — Unit Type Facet                      | Low      | Medium (precision, free signal)                     | None                                         |
| 6        | R3 — Cross-Page Continuity + Table Groups | Medium   | High (data quality)                                 | None                                         |
| 7        | R5 — Content Versioning                   | Low      | Medium (future-proofing)                            | None                                         |
| 8        | R2 — Parent-Fetch Primitive               | Medium   | High (replaces broken expand_context)               | R3 (need table groups), R6b (need A' flags)  |
| 9        | R6 — Relational Enrichment                | Medium   | High (compositional retrieval)                      | R8 (need T3 gold), R6b (A' must be standard) |
| 10       | R10 — Exception Annotation                | Low      | Medium (compositional retrieval)                    | R6 (subcase of relational enrichment)        |
| 11       | R11 — Cross-Encoder Re-Ranking            | Medium   | Medium (precision)                                  | R7 (tune bi-encoder first)                   |
| 12       | R4 — Graph Construction Contract          | High     | High (long-term architecture)                       | R1, R3, R5 (clean foundation)                |

---

## Open Questions

1. **Cross-encoder model selection (R11):** Start with a general-purpose cross-encoder. Domain fine-tuning is a "later, if the general model isn't good enough" optimization. See explanation below.

### Cross-Encoder Explanation (R11)

Current dense retrieval uses a **bi-encoder**: the query and each EvidenceUnit are embedded independently (query → vector, document → vector), then compared by cosine similarity. This is fast because all document embeddings are pre-computed and stored; retrieval is just a nearest-neighbor search. But query and document never "see" each other — the model can't reason about how a specific question relates to a specific passage.

A **cross-encoder** takes (query, document) as a single concatenated input and processes them jointly. The model's attention layers can look across both the question and the passage simultaneously, so it's much better at fine-grained relevance judgments. For example:

- Bi-encoder: "What's the range of Chain Lightning?" embeds to a vector. Chain Lightning's spell block embeds to a vector. Cosine similarity is high — but so is the similarity to any spell that mentions "chain" or "lightning" or "range."
- Cross-encoder: Sees the full question AND the full spell block together. Can determine that the Chain Lightning block _actually answers_ the range question (it says "Range: 150 feet") while a passage mentioning "a chain of lightning" in flavor text does not.

The tradeoff: cross-encoders are O(N) per query — you must run inference for every (query, candidate) pair. For a corpus of 10,000 EvidenceUnits, that's 10,000 inference calls. Impractical. But on the top-50 candidates from bi-encoder retrieval, it's just 50 calls — fast enough to be useful.

**Domain tuning** means taking a general-purpose cross-encoder (trained on web search data like MS-MARCO) and fine-tuning it on TTRPG (question, relevant EvidenceUnit, irrelevant EvidenceUnit) triples so it learns domain-specific relevance signals. This could help: "What saving throw does Charm Person allow?" is more relevant to the Charm Person block than to a passage about saving throws in general — a domain-tuned model might catch that distinction better.

**Recommendation:** Start general-purpose. Fine-tuning requires training data (your gold sets are a starting point) and adds maintenance burden. Only fine-tune if the general model's reranking delta is disappointing on T2+ gold tiers.

---

## Experiment Queue

These questions were originally "open" but the answer in each case is: **run experiments in Retrieval Lab rather than guess.**

### E1 — Parent-Fetch Depth (from R2)

**Question:** How deep should structural_path matching go?

**Experiment:** Sweep depth values (1, 2, 3, 4) across all corpora. Measure answer-synthesis quality (not retrieval metrics — parent context affects generation, not ranking). Report per-corpus optimal depth. If it varies significantly, make depth part of the per-corpus RetrievalPolicy (R7).

### E2 — Cross-Page Join Detection (from R3)

**Question:** How to detect split content across consecutive pages?

**Approach:** Start with N/N+1 only. Detection heuristics:

- **Punctuation signal:** Last unit on page N ends without terminal punctuation → candidate for join
- **LLM review of candidates:** After heuristic detection produces candidates, have an LLM confirm/reject each candidate join. This is a one-time cost at ingestion, not retrieval.

**Caution:** This will be harder to spot than it seems. False negatives (missed joins) are common when authors use unusual formatting or when OCR introduces spurious punctuation. The LLM review step is the safety net.

### E3 — Table Group Expansion Budget (from R3)

**Question:** What character cap for table group expansion?

**Approach:** Measure, don't guess. We know where every table is in the existing EvidenceUnit corpus. Run a diagnostic:

- Histogram of table lengths (characters) across all corpora
- Identify table groups (by header hash) and measure group total lengths
- Set the cap at P95 of group lengths (covers 95% of tables without outlier blowup)

This is a pure measurement task — the data already exists.

### E4 — A' Flag Accuracy and Parent-Fetch Wiring (from R6b + R2)

**Question:** Should `requires_parent=true` always trigger parent-fetch?

**Experiment:** Measure A' flag accuracy on a sample:

1. Sample N units flagged `requires_parent=true` by A'
2. Human review: is the flag correct? (Does the unit actually need parent context?)
3. If accuracy is >90%, wire it unconditionally — parent-fetch always fires when the flag is set
4. If accuracy is lower, investigate failure modes and tighten the A' prompt before wiring

**Bias toward action:** If it works, yes, always fire. The cost of parent-fetch on a false positive is mild noise; the cost of not fetching on a true positive is a broken answer.

---

## Resolved Questions

- ~~**RetrievalView merge constraints (R2):**~~ Resolved by replacing RetrievalView with parent-fetch primitive. No merge layer needed.
- ~~**Stage A' enrichment target (R2 + R6):**~~ Resolved. A' enriches EvidenceUnits (the authored content). Parent-fetch operates at retrieval time on structural containment. No ambiguity.
- ~~**Gold set authorship (R8):**~~ Resolved. Approach: agent crawls the internet to synthesize rule questions across diverse query types, existing retrieval finds candidate chunks, human + agent review validates gold pairs. This provides both scale (agent generation) and quality (human review) while naturally producing questions from a "doesn't know the pipeline" perspective (the crawled questions come from real users asking about rules).
- ~~**Parent-fetch depth (R2):**~~ Resolved. Run experiments in Retrieval Lab (see E1).
- ~~**Cross-page join detection (R3):**~~ Resolved. Punctuation heuristic + LLM candidate review (see E2).
- ~~**Table group budget (R3):**~~ Resolved. Measure actual table group lengths (see E3).
- ~~**A' flag wiring (R6b + R2):**~~ Resolved. Experiment first, then always fire if it works (see E4).
