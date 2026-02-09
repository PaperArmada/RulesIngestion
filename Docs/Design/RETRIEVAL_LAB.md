# HANDOFF — Retrieval Lab (Baseline & Experimental Retrieval over EvidenceUnits)

## Status

Normative handoff document.

This document revises and supersedes earlier “baseline retrieval” or “chunk evaluation” handoffs.
It defines a **permanent Retrieval Lab** used across RulesIngestion Mark III and beyond.

---

## 1. Purpose

The Retrieval Lab exists to answer one class of questions only:

> How discoverable is a given representation of evidence under a given retrieval regime?

It is:

- authority-free
- semantics-free
- ingestion-agnostic
- comparative by design

It is **not** a correctness evaluator and must never be treated as one.

---

## 2. Why This Exists (Non‑Negotiable)

As the system evolves, multiple dimensions will change independently:

- OCR / ingestion tooling
- Evidence representations (EvidenceUnits, projections, graph-derived views)
- Embedding models
- Retrieval strategies
- Graph augmentations

Without a fixed retrieval laboratory, it becomes impossible to answer:

- whether recall improved or authority simply hid failures
- whether a new embedding model is better or just noisier
- whether graph augmentation actually recovers missed evidence
- whether traceability improvements reduce discoverability

The Retrieval Lab is the **control instrument** for these questions.

---

## 3. Scope Boundaries

### In Scope

- Sparse retrieval (BM25 or equivalent)
- Dense retrieval (pluggable embedding backends)
- Hybrid retrieval
- Retrieval-time graph expansion (experimental)
- Retrieval metrics and diagnostics

### Explicitly Out of Scope

- Authority modeling
- Pedagogical signals
- Override logic
- Rule precedence
- Answer synthesis
- “Correctness” judgments

If authority or semantics are required, the experiment does not belong here.

---

## 4. Canonical Input: Retrieval Substrate

The Retrieval Lab operates over a **Retrieval Substrate**.

A Retrieval Substrate is:

> A set of searchable units representing the same underlying evidence, exposed to retrieval as text + identity.

Examples:

- Raw EvidenceUnits
- EvidenceUnits with fixed context windows
- EvidenceUnits augmented with entity names
- Graph-expanded synthetic units
- Clause-level projections (future)

The Lab does not care how substrates are produced.
It only requires:

- stable unit identity
- stable text content
- explicit provenance

---

## 5. Retrieval Modes (First‑Class Knobs)

Each experiment explicitly selects one retrieval mode:

- sparse
- dense
- hybrid
- hybrid + graph expansion
- hybrid + reranker (future)

Retrieval tooling must be hot‑swappable.
Embedding models must be pluggable without code changes to evaluation logic.

---

## 6. Experiment Definition

Each experiment is defined as:

(Substrate, RetrievalMode, QuerySet) → Metrics

No experiment is valid unless all three are explicitly named and logged.

---

## 7. Metrics (What Is Measured)

### Primary Metrics

- Gold‑in‑candidates rate
- Recall@k
- Mean Reciprocal Rank (MRR)
- Candidate set size
- Rank distribution of gold evidence

### Failure Classification

Each miss must be classified as:

1. No admissible evidence exists
2. Evidence exists but was not retrieved
3. Evidence retrieved but ranked too low

These categories must remain distinct.

---

## 8. Metrics That Are Forbidden Here

The Retrieval Lab must never report:

- correctness
- rule resolution success
- authority compliance
- explanation quality
- user satisfaction

Those belong to downstream systems.

---

## 9. Relationship to RulesIngestion Mark III

- The Retrieval Lab consumes **outputs of Stage B** (EvidenceUnits or projections).
- It never feeds results back into ingestion or semantics.
- It provides empirical baselines used to interpret later gains from Stage C.

The Retrieval Lab defines:

> the worst discoverability the system should ever have.

Anything better must be justified by added structure or authority.

---

## 10. Baseline Substrates: Baseline-A vs Baseline-B

Two baselines must be kept distinct. Mixing them conflates Stage B quality with retrieval quality and hides ingestion failures.

**Baseline-A (pure Stage B, ingestion discoverability)**

- **Substrate:** Raw EvidenceUnits only. No synthetic expansion, no context windows, no heading attachment.
- **Gold:** **Manually grounded.** Gold evidence IDs are chosen by human or rule-based judgment against the corpus, not by embedding similarity in the same space used for retrieval.
- **Measures:** Whether the smallest admissible authored-prose units are discoverable.
- **If gold is chosen by embedding similarity in the same space as retrieval:** the experiment measures embedding self-consistency, not discoverability of evidence. That systematically hides Stage A/B failures (tiny units, heading dominance, structural bleed, OCR fragmentation).

**Baseline-B (synthetic retrieval substrate)**

- **Substrate:** EvidenceUnits plus expansions (e.g. context windows, merged blocks, heading attachment, graph-expanded units).
- **Gold:** May use synthetic or embedding-assisted gold, with explicit documentation.
- **Measures:** Usable retrieval system performance over a richer representation.

Compare Baseline-A and Baseline-B in the Lab to separate **Stage B tuning** (fewer undersized units, better structure) from **retrieval improvement** (better ranking, hybrid, graph). The baseline substrate for ingestion must remain “smallest admissible units that are still semantically complete” (see Stage B contract); otherwise there is no control.

---

## 11. Graph Experimentation Role

When graph construction is introduced:

- graph‑augmented retrieval is tested here first
- improvements must be measurable against non‑graph baselines
- recall gains and noise costs are made explicit

This prevents graph value from being assumed rather than demonstrated.

---

## 12. Operational Rules

- Results are comparative, not absolute
- Baselines are frozen once established
- No tuning loops inside the Lab
- No heuristics added to “help” retrieval

If tuning is required, it happens elsewhere.

---

## 13. How to Run Retrieval Benchmarks

**Entry point:** From `RulesIngestion` root, run:

```bash
uv run python -m retrieval_lab.run_experiment [OPTIONS]
```

**Prerequisites:**

- A **substrate**: directory of Stage B output (page dirs containing `stageB.evidence_units.json`). Single-doc (e.g. `out/mark3_evaluation/DnD_PHB_5.5`) or multi-PDF (e.g. `out/mark3_evaluation/StarFinderPlayerCore` with one subdir per chapter).
- **Query batches**: JSON file(s) with queries. Format: `{"batches": [{"queries": [{"id": "...", "question": "...", "expected_answer_summary": "..."}]}]}` or a flat list of query objects. The canonical gold field is **`gold_unit_ids`** (list of EvidenceUnit IDs from the substrate). See `evals/retrieval/PHB5e/` and `evals/retrieval/StarFinderPlayerCore/` for examples.

**Two-step workflow (recommended):**

1. **Embed once** (when substrate or substrate version changes):

   ```bash
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/dense/phb_baseline.yaml \
     --embed-only
   ```

   Prints `run_id=` (e.g. `retrieval_lab_DnD_PHB_5.5_v1`). Embeddings are written to MongoDB (if available) and to `out/retrieval_lab/experiments/embed_<run_id>/embeddings/`.

2. **Eval only** (reuse embeddings; no re-embed):
   ```bash
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/dense/phb_baseline.yaml \
     --run-id <RUN_ID from step 1>
   ```
   If MongoDB is down, embeddings are loaded from the embed output dir on disk when possible.

**Full run** (embed if missing, then eval):

```bash
uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/dense/phb_baseline.yaml
```

**Without a config file:**

```bash
uv run python -m retrieval_lab.run_experiment \
  --substrate out/mark3_evaluation/StarFinderPlayerCore \
  --document-id StarFinderPlayerCore \
  --models all-mpnet-base-v2 \
  --batches evals/retrieval/StarFinderPlayerCore/batch_001.json evals/retrieval/StarFinderPlayerCore/batch_002_state.json \
  --substrate-version v2
```

**Important options:**

| Option                    | Meaning                                                                               |
| ------------------------- | ------------------------------------------------------------------------------------- |
| `--embed-only`            | Only embed the substrate; do not run queries or report.                               |
| `--run-id <id>`           | Eval-only: use this embedding run (no embedding step).                                |
| `--substrate-version <v>` | Sets run*id to `retrieval_lab*{document*id}*{version}`. Bump when extraction changes. |
| `--trust-remote-code`     | Required for nomic-embed-text-v2, bge-m3, gte-multilingual-base.                      |
| `--no-reuse-embeddings`   | Force recompute of embeddings (ignore MongoDB/disk cache).                            |

**Outputs** (per experiment, under `output_dir` / `<experiment_id>`):

- `REPORT.md` — Summary, model comparison table, failure analysis, glossary.
- `metrics.json` — Aggregate metrics per model.
- `per_query.json` — Per-query results per model.
- `retrieved_chunks.json` — Retrieved chunk text per query per model (for manual review).
- `grounding_audit.json` — Gold grounding audit.
- `experiment.json` — Experiment config and metadata.

**Gold grounding:** If query batches do not contain `gold_unit_ids`, the lab uses **corpus-wide semantic** grounding (embedding similarity of `expected_answer_summary` to corpus) to assign gold. For Baseline-A (ingestion discoverability), prefer manually grounded gold; see §10.

---

## 14. Summary

The Retrieval Lab is a permanent experimental layer.

It measures **discoverability**, not truth.
It provides baselines, not answers.
It enables honest comparison across time, tools, and representations.

If a question involves authority or correctness, this is not the system to ask.
