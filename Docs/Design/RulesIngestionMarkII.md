# **0\) Vocabulary: what “a piece of document” is called**

You currently have (or should have) these “first-class” artifacts:

### **Source artifacts (authoritative, immutable given a PDF \+ extractor version)**

1. **Document**: a rulebook PDF (versioned by hash).

2. **Page**: page image \+ extracted text.

3. **Marker stream**: datalog marker pipeline output (layout \+ reading order \+ spans).

4. **Chunk**: a contiguous unit of extracted content with stable ID and structural address.

   * includes `content_kind` (rule, spell, feat, item, glossary, example, table, etc.)

   * includes `layout_tier` (main text, sidebar, callout, footnote, etc.)

   * includes `section_path` (from CDS; chapter → section → subsection)

5. **Chunk text view(s)**:

   * **EmbedText**: normalized markdown-ish text used for embeddings

   * **LexText**: normalized token stream used for BM25

   * **DisplayText**: human-readable, faithful reconstruction

### **Semantic artifacts (authoritative *claims* extracted deterministically from chunks)**

6. **RuleFact**: an atomic structured statement extracted from chunk text.

   * must preserve provenance: `(doc_id, chunk_id, span)`

   * examples: “increase damage by \+1 at 5th level”, “requires off-guard”, “override target: dying procedure”

7. **Entity**: canonical named thing (spell, feat, condition, trait, procedure, concept).

8. **MechanicFrame (MF)**: the primary “unit of authority” you want to reason about (Spell/Feat/Rule/Procedure/etc.).

   * entities often map into frames; one entity may “be” a frame depending on system.

### **Projection artifacts (NOT authoritative; used only as constraints/scoring)**

9. **CDS (Canonical Document Skeleton)**: frozen structural graph of the book’s organization \+ roles.

10. **PSC (Pedagogical Signal Contract)** projections: authority priors (layout, voice, chapter role, example density, etc.).

11. **Traversal Graph**: entity/entity and chunk/entity edges used to compute reachability/explanations (never the only retrieval engine).

---

# **1\) End-to-end architecture: ingestion → retrieval → grounding → evidence**

## **Stage A — Ingestion: PDF → marker stream → structured JSON**

**Goal:** deterministic, reconstructable parsing of the book.

**Inputs**

* PDF bytes

* extractor version \+ configs

**Outputs**

* `doc_manifest.json` (hashes, version stamps)

* `pages/*.json` (marker stream per page)

* `raw_blocks.jsonl` (optional: flat list of blocks with coordinates)

* invariants report (e.g. missing pages, non-deterministic ordering)

**Key invariants**

* Same input bytes \+ same extractor version ⇒ identical marker stream

* Every extracted block has stable coordinates \+ page provenance

---

## **Stage B — Chunking \+ Structural addressing: marker stream → chunks**

**Goal:** create **stable chunk IDs** that are addressable, replayable, and mappable back into the book’s structure.

**Chunk definition (deterministic)**

* constructed from reading order \+ layout boundaries

* chunk types: Text, Table, TableCell, SectionHeader, Title, ExampleBox, Sidebar, Footnote, etc.

**Outputs**

* `chunks.jsonl` (one record per chunk)

  * `chunk_id`

  * `page_range`

  * `content_kind` (best-effort)

  * `layout_tier`

  * `raw_text` (faithful)

  * `embed_text` (normalized markdown)

  * `lex_text` (BM25-ready)

  * `structure_address` (filled after CDS alignment)

---

## **Stage C — CDS construction: “book structure as a frozen projection”**

**Goal:** build a **parallel structural graph** from titles/headers/index/etc. This graph does *not* reason. It only constrains grounding.

**Inputs**

* chunks (especially Title / SectionHeader)

* optional: ToC pages if detected

* optional: glossary markers, chapter boundaries

**Outputs**

* `cds_nodes.jsonl` (chapter/section/subsection nodes)

* `cds_edges.jsonl` (parent/child, order, page ranges)

* mapping: `chunk_id -> cds_node_id` (structural address)

* derived properties:

  * `section_role` (core rules / options / variants / examples / glossary / narrative)

  * `term_distribution` per node (deterministic)

  * `summary` per node (publisher-provided if available; otherwise deterministic heuristic summary or postponed)

**Important:** CDS is frozen once built for a doc version.

---

## **Stage D — Semantic extraction: chunks → RuleFacts \+ Entities \+ MechanicFrames**

**Goal:** extract structured claims and canonical anchors with provenance.

**Outputs**

* `rule_facts.jsonl`

  * each fact has `fact_id`, `chunk_id`, `span`, `subject`, `predicate`, `object`, qualifiers

  * optional: `override_target`, `condition`, `scope`, `level_scaling`, etc.

* `entities.jsonl`

  * canonicalization rules (names \+ aliases \+ doc scoping discipline)

* `mechanic_frames.jsonl`

  * primary MF for relevant chunks

* mappings:

  * `fact_id -> belongs_to_entity_id` (when confident)

  * `chunk_id -> describes_entity_ids` (when chunk is about an entity/MF)

  * `chunk_id -> is_rule_bearing` (critical feature)

This is where your “authority legibility” lives or dies: if we don’t deterministically tag “this is an example box” / “this is a variant rule” / “this is a definition”, authority cannot be applied later.

---

## **Stage E — Indexing: lexical \+ vector \+ metadata filters**

**Goal:** retrieval should be **high recall**, cheap, and query-driven. The graph is not the primary retriever.

**Vector index**

* embed `embed_text` with **nomic-text-v2** (fine)

* store `(chunk_id, vector)`

**BM25 index**

* index `lex_text`

* store `(chunk_id, token stats)`

**Metadata store**

* `chunk_id -> {content_kind, layout_tier, section_role, cds_node_id, page_range, is_rule_bearing, primary_mf, etc.}`

---

## **Stage F — Query-time pipeline: retrieve → seed → constrain → rank → evidence pack**

This is the runtime architecture you want to become “tight and intentional.”

### **F1) Query normalization \+ intent sketch (lightweight, deterministic-ish)**

* normalize tokens

* identify obvious anchors:

  * explicit ability names / directive names

  * conditions / stats

  * “is this asking for definition vs procedure vs exception vs example?”

**Output:** `query_intent` object (even if crude).

### **F2) Candidate retrieval (hybrid)**

* BM25 top K1

* Vector top K2

* Fuse (RRF or deterministic weighted merge)

* Output candidate set `C` (e.g. 50–150 chunks)

**This is where you should win recall.**

### **F3) Candidate enrichment: map candidates to structures \+ frames**

For each chunk in `C`, attach:

* CDS node path \+ section role

* layout tier

* voice/modality (if extracted)

* primary MF / entity mentions

* rule-bearing flag

### **F4) Admissibility gating (CDS / PSC-lite)**

This is the “oracle chunking but explicit” stage.

Rules like:

* if query has a named directive, prioritize sections whose headers/summaries contain it

* if query is definitional, prioritize glossary/definition nodes

* if query is procedural, prioritize procedure chapters / step sequences

* do not let *examples* outrank *core rules* unless intent is example-seeking

* do not let *variant rules* override *core rules* unless query asks variants explicitly

**Output:** gated candidate set `C'` plus `gate_diagnostics`.

### **F5) Ranking (relevance first, authority as a constraint, not a club)**

The big lesson from CDS v0.2:

Pure authority-key reranking can demote correct gold in lower-authority sections.

So ranking should be:

* relevance score (hybrid retrieval score)

* then authority as tie-break / constraint / penalty, not primary sort

* plus scope alignment features (header scope, MF scope)

**Output:** ranked list `R` of chunks.

### **F6) Evidence pack assembly**

Return:

* top N chunks

* their structural addresses

* their primary entities / frames

* extracted RuleFacts linked to spans

* (optional) graph-based explanation skeleton (but only after candidates are correct)

---

# **2\) Metrics: broad set, definitions, and what each stage uses them for**

The meta-pattern you’re aiming for is: **each stage has its own success metrics \+ invariants** and you don’t advance until they’re stable.

Below is a metric suite organized by layer.

---

## **A) Ingestion \+ chunking metrics (PDF → chunks)**

### **Determinism & integrity**

1. **Extractor determinism rate**

   * % of runs where marker stream hash matches across repeated runs.

2. **Chunk stability**

   * % of chunks whose `(chunk_id, text_hash)` stay identical across rebuilds.

3. **Provenance completeness**

   * % of chunks with valid `(doc_id, page_range, bbox/span pointers)`.

4. **Reconstruction fidelity**

   * edit distance between reconstructed DisplayText and raw extracted text (bounded).

### **Structure coverage**

5. **Header detection recall (structural)**

   * how many Title/SectionHeader chunks exist vs expected (heuristic baseline).

6. **Table capture rate**

   * count tables detected / pages with tables (coarse proxy).

**Usage:** if these are unstable, everything downstream is noise.

---

## **B) CDS / document structure projection metrics**

### **Coverage**

1. **Chunk-to-CDS assignment rate**

   * % of chunks assigned to a CDS node (should be \~100% except truly orphaned junk).

2. **CDS tree validity**

   * acyclic, connected under root, monotonic page ranges, ordinal ordering consistent.

### **Authorial priors legibility**

3. **Section role coverage**

   * % of CDS nodes with `section_role` assigned (core/options/variant/examples/glossary/etc.).

4. **Layout tier coverage**

   * % of chunks with layout\_tier assigned (main/sidebar/callout/footnote).

### **Alignment sanity**

5. **Header-scope span distribution**

   * histogram of “chunks under header before next header” (detect runaway scope).

**Usage:** CDS exists to constrain grounding. If it can’t label the book, it can’t help.

---

## **C) Semantic extraction metrics (chunks → facts/entities/frames)**

### **Entity & frame legibility**

1. **Primary MF coverage**

   * % of rule-bearing chunks with `primary_mf`.

2. **Entity mention recall**

   * average \# of resolved entity mentions per chunk (for relevant content kinds).

3. **Canonicalization precision**

   * rate of ID drift (doc-scoped vs ruleset-scoped collisions).

4. **Belongs-to single-ownership rate**

   * % of facts that map to exactly one entity (high is good for traversal stability).

### **Fact quality proxies (deterministic)**

5. **Fact yield**

   * facts per rule-bearing chunk.

6. **Fact span validity**

   * % of facts whose span points to a real substring in DisplayText.

7. **Override targeting rate**

   * how many facts have structured override fields (if that’s a design pillar).

**Usage:** if authority isn’t legible here, authority cannot be enforced later.

---

## **D) Indexing metrics (vector \+ BM25)**

### **Retrieval health (offline)**

1. **Index completeness**

   * % of chunks present in BM25 and vector index.

2. **Embedding drift**

   * mean cosine distance of embeddings across rebuilds (should be \~0 if deterministic pipeline).

### **Storage/throughput (engineering)**

3. **Index size**

   * bytes per chunk per index type.

4. **Query latency**

   * P50/P95 retrieval time per index.

**Usage:** keep this boring and stable.

---

## **E) Query-time retrieval metrics (hybrid)**

These are the metrics you should treat as “the truth” for retrieval quality.

### **Primary retrieval metrics (your 50Q benchmark)**

1. **Gold found / gold total (Recall)**

   * set overlap, not position.

2. **Recall@k (k=5,10)**

   * gold in top-k ranked candidates.

3. **Hit rate**

   * % queries with ≥1 gold in top-k.

### **Candidate-set diagnostics (what you learned in CRR)**

4. **Gold-in-candidates rate**

   * % of gold chunks that appear anywhere in candidate set `C`.

5. **Candidate set size**

   * |C| and distribution.

### **Failure decomposition (must remain)**

6. **Gold-gap audit breakdown**

   * UNSEEDED / UNREACHABLE / REACHABLE\_UNSELECTED / REACHABLE\_UNEXPLAINABLE

7. **Retrieval failure vs grounding failure**

   * For UNSEEDED, did gold never enter candidates (retrieval\_failure) or entered but failed to seed/attach (grounding\_failure)?

**Usage:** you don’t “improve authority” until gold is reliably in candidates.

---

## **F) Admissibility \+ authority metrics (CDS/PSC stage)**

These are the metrics that tell you if you’re constraining correctly rather than excluding.

### **Gate safety (non-regression)**

1. **T3 preservation (gold not filtered)**

   * count of gold removed by admissibility gate (must be \~0 for conservative gates).

2. **Empty candidate set rate**

   * should be 0 unless you intentionally allow refusals.

### **Gate effectiveness**

3. **Filtered mass**

   * average \# candidates removed by admissibility.

4. **Authority inversion rate**

   * when multiple candidates conflict, how often does a lower-authority one outrank higher-authority *without intent justification*.

5. **Gold rank delta**

   * rank\_before \- rank\_after for gold chunks present in C (distribution, by batch).

**Usage:** your CDS v0.2 result is a classic sign: gate preserved gold but ranking harmed some batches. So the right metric is not “authority increased,” it’s “authority applied without demoting correct evidence.”

---

## **G) Graph / traversal metrics (kept as *supporting*, not primary retrieval)**

Given your goal—eventually constructing algorithmic rules—graphs still matter, but as **explanation scaffolding** and **constraint propagation**, not as your main retriever.

### **Topology**

1. **Degree distribution**

   * hub dominance indicators: Gini coefficient on degree, top-1% degree mass.

2. **Component structure**

   * size of giant component, \# isolated components.

### **Traversal dynamics (diagnostics)**

3. **Frontier growth**

   * nodes visited by depth; explosion indicates permissive edges/hubs.

4. **Entropy of frontier**

   * “does traversal quickly collapse onto hubs?”

5. **Entity semantic purity**

   * semantic edges vs structural edges in traversal explanations (your earlier metric).

### **Explanation support (secondary)**

6. **CCR / causal coverage**

   * fraction of explanation that can be justified via semantic edge paths.

7. **Minimality**

   * facts/frames bounded.

**Usage:** use these to diagnose why selection is drowned out, not as success criteria until retrieval+authority are stable.

---

# **3\) The “intentional design” rebuild: a staged ladder with gates**

This is the disciplined way to stop the Frankenstein effect:

## **Step 1 — Lock the artifact pipeline**

* Deterministic ingestion

* Stable chunk IDs

* Stable EmbedText/LexText

**Gate:** determinism \+ reconstruction fidelity pass.

## **Step 2 — Make authority legible at ingestion**

* layout tiers correct

* section roles correct

* rule-bearing flag reliable

* primary MF coverage high

**Gate:** authority legibility invariant passes (high coverage, low ambiguity).

## **Step 3 — Win recall with hybrid retrieval**

* nomic-text-v2 \+ BM25 \+ fusion

* candidate set big enough for recall

* CRR-style improvements tracked

**Gate:** gold-in-candidates and Recall@10 hit thresholds.

## **Step 4 — Apply CDS/PSC admissibility conservatively**

* never exclude gold

* reduce candidate entropy

* improve Recall@5 without harming Recall@10

**Gate:** T3 gold preservation \+ Recall@5 improvement with bounded regressions.

## **Step 5 — Only then: use the graph as an explainer/constraint engine**

* explain why the retrieved chunk is authoritative

* link RuleFacts with provenance

* detect contradictions, overrides, scope

**Gate:** improved correctness proxies (CCR, fewer authority inversions) without recall harm.

## **Step 6 — Only then: “algorithmic rules from language”**

* rule compilation becomes plausible when evidence selection is stable and authority is enforceable.

---

# **4\) What I think we’re building (in one paragraph, for other experts)**

We are building a **deterministic, auditable retrieval-and-grounding system** for TTRPG rulebooks where **hybrid retrieval (BM25 \+ embeddings)** provides high-recall candidates, and a frozen **Canonical Document Skeleton \+ Pedagogical Signal projections** impose **authorial-intent constraints** (scope, authority, role, layout) so the system grounds answers in the right evidence consistently. The knowledge graph is not the retriever; it is the **explanation and constraint substrate** that links evidence to canonical entities/frames and supports later compilation into algorithmic rule logic with provenance.

