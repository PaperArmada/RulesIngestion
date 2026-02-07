> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Phase 3 Rewrite: Authority-at-Selection v1 (Not Seeding)
**Status:** Spec v0.1  
**Date:** 2026-02-02  
**Purpose:** Replace authority-for-seeding (regressive) with **authority-at-selection**, where authority naturally belongs: choosing among already-recalled candidates.

---

## 1) Why Phase 3 should move

You observed that applying authority during seeding can drop recall. That is expected because:

- Seeds are an approximation of “where to start.”
- Authority is about “which of multiple plausible answers wins.”

Therefore, Phase 3 should be:

> **Use authority to constrain and resolve grounding among candidates, not to decide which candidates exist.**

---

## 2) Locked controls (must not change)

- Traversal: ENTITY_ONLY, Variant A
- Retrieval: your current candidate retrieval baseline (e.g., R2 IDF)
- Scope: V1
- Ownership: baseline
- Edge semantics: unchanged

Only change: **selection/reranking** after candidates are retrieved.

---

## 3) New contract: Authority Eligibility + Precedence

### 3.1 Eligibility gate (hard filter, conservative)

Given:
- Candidate chunks `C` from retrieval (top K candidates)
- Query intent `I` (optional, deterministic heuristic)
- CDS/authority projection metadata per chunk

Compute `eligible(C, I)`:

Default v1 (no intent classifier required):
- Drop chunks where `layout_tier ∈ {example_box, caption, footnote}` **unless**
  - no remaining candidates OR
  - query explicitly asks for “example” / “variant” (simple keyword gate)

- Drop chunks where `section_role == variants` unless query includes keywords:
  - “variant”, “optional”, “alternate”, “GM option”, “subsystem” (book-specific list)

This is not a “score.” It is an admissibility rule.

### 3.2 Precedence order (tie-break among remaining)

Define `authority_key(chunk)` as tuple ordered lexicographically:

1. `section_role_rank` (core_rules highest)
2. `layout_tier_rank` (main highest)
3. `content_kind_rank` (procedure/rule/definition above example)
4. Optional: `voice_rank`
5. `-structural_specificity` (deeper section depth = more specific)
6. `ordinal_in_doc` (stable fallback) or `chunk_id`

Then selection chooses:
- Among candidates linked to reachable entities/facts, prefer higher `authority_key`.

---

## 4) Dependent metrics (what should move)

Primary:
- **Gold recall@K** should increase, especially on:
  - authority inversion cases (examples/variants beating rules)
  - hub-dominance cases where low-authority hubs drown out good chunks

Guardrails:
- Candidate recall (gold in candidates) should not change (filter happens after candidates).
- Refusal rate must not rise materially (eligibility gate must be conservative with fallback).

---

## 5) Diagnostics (required)

For every query where gold is reachable but not selected:
- Log top N candidates with their authority metadata:
  - section_role, layout_tier, content_kind, ordinal, section_path
- Log whether gold was filtered out by eligibility (should be rare)
- Log “authority inversion detected”:
  - gold exists in candidates AND
  - selected candidate has lower authority_key than gold

This directly measures whether authority is doing its job.

---

## 6) Experiment design (A/B)

### A: Baseline selection (current)
### B: Authority-at-selection v1
Same candidates, same traversal, different selection.

Success criteria:
- Increase in recall@5 or recall@10 by ≥ 5% absolute on full blind-eval
- Authority inversion rate decreases
- No >2% regression in batches where authority is irrelevant (purely mechanical tables, etc.)

Kill criteria:
- Eligibility filter removes gold > 2% of the time
- Refusal rate increases without accuracy gain

---

## 7) Implementation notes (where to wire)

Likely wiring points (names may differ in your repo):
- `traversal/retriever.py` (candidate selection / reranking)
- `experiments/rule_fact_benchmark_eval.py` (scoring + logging)
- new module: `grounding/authority.py`:
  - `authority_key(chunk_id, cds)`
  - `is_eligible(chunk_id, query_text, cds)`
  - `rerank_candidates(candidates, cds, query_text)`

Importantly: **no changes to seeds.py**.

---

## One-line takeaway

> Authority should decide *which recalled answer wins*, not *which answers exist*.
