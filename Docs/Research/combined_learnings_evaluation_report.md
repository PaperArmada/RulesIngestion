# Combined Learnings and Evaluation Report  
*(Stages A/B focus: Extraction + Prose Reconstruction, Evidence Binding)*

## 0) Executive summary

Your current interpretation is correct: the architecture is stable and you are now in “crack‑finding” mode. The benchmark behavior (parity holding, post‑retrieval knobs mostly flat, T2 weakest, and a non‑trivial gold‑in‑candidates ceiling) strongly indicates the next gains will come from **Stage B segmentation / binding policies and deterministic co‑retrieval affordances**, not from fusion/reranking tweaks, and not from fine‑tuning.

Stage A extraction is already high‑fidelity (minimal prose/structure loss). The research focus should therefore shift from “layout recovery” toward **deterministic structural modelling, clause boundary discipline, multi‑unit coherence, and provenance‑rich linking**.

This report consolidates (a) your benchmark interpretation, (b) the design critique themes, and (c) web‑sourced patterns (especially from legal/regulatory parsing) into a small set of **discrete hypotheses** with **bounded experiments**. The goal is to reduce noise by turning “many ideas” into a compact experiment slate with clear acceptance criteria.

---

## 1) Current state and what the results mean

### 1.1 Parity and stability
- Refactor parity (H1) is a clean win: refactor did not break retrieval outcomes across corpora. This establishes a stable baseline for experimentation.

### 1.2 Dead knobs are information, not failure
When multiple retrieval‑layer knobs are flat, it usually means:
- the candidate pool is already shaped such that those knobs have little room to act, **or**
- the candidate pool is missing what matters (ceiling), so downstream knobs cannot help.

Your observations align with the second: **gold‑in‑candidates ceiling** + **T2 weakness** point upstream.

### 1.3 T2 is the real use‑case bottleneck
T2 (“what applies when…”) is inherently **compositional**: it often requires retrieving multiple units (base rule + modifier + exception + definition) and composing them against state. Single‑hit retrieval improvements (fusion smoothing, reranking) won’t reliably fix a multi‑unit problem unless the pipeline explicitly supports co‑retrieval or deterministic linking.

---

## 2) Consolidated themes from critique + external patterns

Across the critique and external (legal/regulatory) techniques, the recurring high‑value ideas are:

1) **Grammar / pattern driven extraction**
   - Use explicit grammars (BNF/PEG), finite state recognizers, and rule templates for clause boundaries and reference expressions.

2) **Deterministic cross‑reference and dependency modelling**
   - Legal texts treat cross‑references as first‑class; many systems detect cross‑refs via curated pattern grammars and then resolve them structurally.

3) **“Binding” more than “chunking”**
   - The binding step is where atomicity and sufficiency trade off; “too small” creates delta fragments that don’t retrieve well; “too big” blurs semantics.

4) **Projections over the substrate**
   - Keep EvidenceUnits pristine; build **parallel retrieval substrates** (families, row‑docs, reference‑expanded candidates) to test hypotheses without corrupting admissible evidence.

5) **Candidate shaping beats smarter reranking**
   - If reranking increases Recall@10 but drops MRR, the candidate set likely contains many plausible near‑misses. The remedy is deterministic pairing (delta→parent, exception→base), not more model complexity.

---

## 3) Discrete hypotheses and experiments

Each hypothesis is framed so multiple tactics collapse into one controlled experiment family.

### H‑A: EvidenceUnit boundaries are admissible but not retrieval‑coherent for compositional queries (T2)

**Claim:** Stage B splitting policies produce units that are technically admissible but often insufficient for retrieval to assemble the needed set for T2.

#### Experiment A1 — Clause‑Family projection substrate (retrieval‑only)
Build a Retrieval Lab substrate where a “document” is a deterministic **family** of 2–6 adjacent EvidenceUnits, formed by:
- same heading path segment + adjacency window
- list membership / table membership boundaries
- paragraph continuation markers

Do **not** change EvidenceUnits; this is a parallel index.

**Measure:**
- gold‑in‑candidates (overall and T2)
- Recall@10 and Hit@10 (T2)
- MRR change (ensure first‑hit doesn’t collapse)

**Accept if:**
- gold‑in‑candidates increases materially for T2, and Hit@10 rises without major MRR loss.

#### Experiment A2 — “Must‑not‑split” boundary constraints (Stage B)
Introduce deterministic constraints for patterns that should remain inseparable:
- “If/When/Unless/Except/However” chains
- list introducer + list items (when introducer is needed to interpret items)
- delta clauses (“increase by… at 5th…”) that depend on a base rule

**Measure:**
- distribution of unit sizes
- rate of delta‑only fragments
- gold‑in‑candidates for previously missed queries

**Accept if:**
- delta‑only/orphan fragments drop and candidate ceiling improves.

---

### H‑B: Missing navigational affordances (cross‑refs / exception pointers) prevent deterministic co‑retrieval

**Claim:** The engine lacks deterministic edges that reflect “read these together,” forcing retrieval to guess via semantics.

#### Experiment B1 — Cross‑reference detection grammar + resolution (retrieval‑time only)
Implement a rule/grammar recognizer for cross‑reference expressions and implicit references, producing a “ReferenceEdge” sidecar index.
Then at retrieval time, do bounded expansion:
- for top‑K hits, union in referenced section’s first N units (or resolved target)

**Measure:**
- T2 Hit@10 and Recall@10
- expansion rate and noise (candidate count delta)
- MRR stability

**Accept if:**
- T2 Hit@10 improves and candidate ceiling improves with bounded expansion.

#### Experiment B2 — Exception/base pairing edge (structure + lexical markers)
Create deterministic edges for exception relationships:
- detect exception markers (“except”, “unless”, “despite”, “however”)
- bind exception to nearest compatible base unit under same heading path

At retrieval time, always include the paired unit when one is retrieved.

**Measure:**
- MRR recovery (first gold comes earlier)
- reranker‑style near‑miss issues reduce even without reranker

**Accept if:**
- MRR improves and the “near‑miss outranks gold” pattern diminishes.

---

### H‑C: Representation gap (question phrasing ≠ book phrasing) needs controlled, non‑authoritative enrichment

**Claim:** A portion of misses are vocabulary mismatch or paraphrase mismatch; solve this with bounded A′ enrichment, not fine‑tuning.

#### Experiment C1 — Minimal A′ (questions_answered + anchors only)
Generate retrieval‑only metadata for each EvidenceUnit:
- lexical anchors (canonical terms)
- “questions answered” (short, literal, non‑interpretive)
- risk flags: requires_parent, delta_only, orphan_step

Index these fields alongside verbatim text.

**Measure:**
- gold‑in‑candidates for paraphrased queries
- differential improvement on corpora with different style (e.g., S&W)
- T2 improvements if questions_answered includes prerequisite hints

**Accept if:**
- candidate ceiling rises without creating broad semantic drift.

#### Experiment C2 — A′ gated expansion (risk‑flag only)
Allow A′ to influence retrieval **only** when risk flags are present, and only to select deterministic parent/context expansions.

**Measure:**
- Recall@10 improves without MRR regression typical of generic semantic expansions.

---

### H‑D: Tables and lists are not broken, but they are not query‑addressable

**Claim:** Even with high‑fidelity extraction, table content can be retrieved without enough schema context (headers/row semantics), harming relevance.

#### Experiment D1 — Table row projection docs (retrieval‑only)
For each table:
- create deterministic “row docs” whose text is: (header cells + row cells)
- stable IDs with provenance back to the table EvidenceUnit

**Measure:**
- subset benchmark focusing on table‑addressed queries
- overall noise impact (candidate distribution change)

**Accept if:**
- table‑related queries improve with minimal collateral impact.

---

### H‑E: Benchmark misses mix failure modes; experiments must target the correct bucket

**Claim:** Without strict failure classification, improvements can be misattributed.

#### Experiment E1 — Failure bucket dashboard
For each query, classify:
1) no gold exists in corpus / annotation error  
2) gold exists but not in candidates (ceiling)  
3) gold retrieved but ranked too low  
4) grounding/explanation failure despite retrieval  

**Measure:**
- Each experiment must shift at least one bucket significantly, otherwise it’s noise.

---

## 4) Prioritization: the smallest high‑signal experiment slate

If you want the “next push” to be maximally informative with minimal disruption:

1) **A1 Clause‑Family substrate (retrieval‑only projection)**
2) **B1 Cross‑ref grammar + bounded expansion**
3) **E1 Failure bucket dashboard** (run alongside everything)

These three tell you quickly whether “multi‑unit coherence” is truly the bottleneck and whether deterministic linking can lift T2 without model changes.

If A1 succeeds but B1 doesn’t: segmentation/granularity is the lever.  
If B1 succeeds but A1 doesn’t: missing cross‑refs/dependency edges are the lever.  
If neither succeeds and ceiling persists: investigate annotation or deeper representation mismatch (then C1).

---

## 5) Scoring rubric (for new ideas discovered later)

Use the 0–5 scoring dimensions you defined:
- Determinism
- Semantic independence
- Stage alignment
- Atomicity impact
- Provenance preservation
- Compositional support
- Implementation feasibility
- LLM avoidance

**Meta‑filter:** discard anything requiring fine‑tuning, heavy ontologies, rewriting/summarization, or nondeterministic replay.

---

## 6) Implementation notes (how to keep the design clean)

1) **EvidenceUnits remain canonical and admissible.**  
Do not mutate them to chase metrics. Use projections.

2) **All expansions are tagged.**  
Every candidate added via pairing or cross‑ref expansion should carry a provenance label:
- expanded_by = crossref | exception_pair | delta_parent | family_projection | table_row_projection

3) **Bound candidate growth.**  
Expansion must be capped by count and by structural scope.

4) **Keep A′ non‑authoritative.**  
A′ may help retrieval, but it must never become the evidence itself.

---

## 7) What “success” looks like, concretely

For this phase, success is not “SOTA MRR.” It is:
- gold‑in‑candidates ceiling drops materially (PHB ceiling improves)
- T2 Hit@10 improves without collapsing T1 MRR
- failure bucket shifts from “not in candidates” → “retrieved but ranked” (a healthier problem)
- changes are attributable to deterministic mechanisms (auditable deltas)

---

## 8) Appendix: Why legal cross‑reference work is especially relevant

Legal/regulatory systems often:
- formalize cross‑reference expressions with explicit grammars (BNF‑like)
- use deterministic dictionaries for markers (section, article, subsection)
- resolve references to fine‑grained provisions
- treat exceptions and amendments as explicit navigational edges

Those are direct analogs to:
- “see also” / “as described in”
- exception clauses
- rule dependencies
- compositional retrieval requirements

The key is to adopt the *structural* techniques (pattern grammars + resolution) without importing semantic inference.

