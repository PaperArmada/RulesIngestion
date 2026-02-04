# Blind Evaluation

This directory contains blind evaluation batches for testing the traversal system on unseen queries.

**Full methodology:** See [Docs/BLIND_EVAL_BATCH_CONSTRUCTION.md](../Docs/BLIND_EVAL_BATCH_CONSTRUCTION.md) for (1) what is working (agent-as-evaluator pattern, tool-driven gold chunk discovery) and (2) step-by-step batch construction for humans and agents.

**Systematic failure analysis:** See [Docs/PLAN-Failure-Taxonomy-And-Constraints.md](../Docs/PLAN-Failure-Taxonomy-And-Constraints.md) for the layered failure taxonomy (A–E), counterfactual validation, contract insertion, and regression harness. Tasks are scoped and checkable there.

**Gold chunk evaluation and retrieval reboot:** See [Docs/GOLD_CHUNK_EVALUATION_AND_REBOOT_PLAN.md](../Docs/GOLD_CHUNK_EVALUATION_AND_REBOOT_PLAN.md) for evaluating benchmark gold chunks (keep/trim/drop) and storing them as **text + document position** so they can be re-found after a graph/retrieval reboot. Use `blind_eval/scripts/export_gold_audit.py` to export `gold_audit.json` and optional `gold_audit_review.md`, then after review run `--build-reference` to produce `gold_reference.json`.

## Protocol

1. **Generate random pages** - Run `generate_pages.py` to get random page numbers
2. **Create questions** - Open PDF, read page, write natural question
3. **Find gold chunk** - Use `find_chunks.py` to identify the gold chunk ID
4. **Add to batch file** - Add entry to `batches/batch_NNN.json`
5. **Commit** - Commit the batch file (no code changes!)
6. **Run eval** - `uv run pytest tests/test_blind_eval.py -v`
7. **Analyze** - Review failures, document root causes

## Directory Structure

```
blind_eval/
├── README.md           # This file
├── generate_pages.py   # Random page generator
├── find_chunks.py      # Helper to find chunks on a page
├── batches/            # Batch JSON files
│   ├── batch_001.json
│   ├── batch_002_state.json
│   ├── batch_003_grounding.json
│   ├── batch_004_temporal.json
│   ├── batch_005_constraints.json
│   ├── batch_006_conceptual.json
│   └── ...
├── scripts/
│   └── export_gold_audit.py   # Export gold chunks to audit + optional review; build gold_reference after review
├── gold_audit/         # Output: gold_audit.json, gold_audit_review.md, gold_reference.json (after review)
└── results/            # Evaluation results
    ├── batch_001_results.json
    └── ...
```

## Batch File Format

```json
{
  "metadata": {
    "batch_id": "001",
    "created_by": "human",
    "pdf_source": "PZO22003_PlayerCore.pdf",
    "created_at": "2026-01-27T10:00:00Z"
  },
  "queries": [
    {
      "id": "blind_001_01",
      "source_page": 142,
      "question": "What happens if I try to cast a spell while grabbed?",
      "gold_chunk_ids": ["sf2e-playercore-chunk-12345"],
      "expected_answer_summary": "Grabbed imposes conditions that affect spellcasting",
      "notes": "Page covers the Grabbed condition"
    }
  ]
}
```

Optional (populated by failure-taxonomy harness; leave absent in hand-authored batches):

- `failure_class`: `"A" | "B" | "C" | "D" | "E" | null` (null = hit)
- `failure_signals`: object with diagnostic fields (see PLAN-Failure-Taxonomy-And-Constraints.md)

## Running Blind Eval

```bash
# Run all blind eval batches
uv run pytest tests/test_blind_eval.py -v

# Run specific batch
uv run pytest tests/test_blind_eval.py -v -k "batch_001"

# Generate detailed report
uv run python blind_eval/run_eval.py --batch 001 --verbose
```

## Running Failure Taxonomy

Labels each gold miss with exactly one failure class (A–E) and prints a distribution report. See [Docs/PLAN-Failure-Taxonomy-And-Constraints.md](../Docs/PLAN-Failure-Taxonomy-And-Constraints.md).

```bash
# From repo root (RulesIngestion)
uv run python blind_eval/run_taxonomy.py

# Custom graph/enriched paths
uv run python blind_eval/run_taxonomy.py --graph path/to/merged.graph.json --enriched path/to/merged.enriched.json

# Write per-query results to results/
uv run python blind_eval/run_taxonomy.py --write-back
```

Results are written to `blind_eval/results/taxonomy_results.json` (distribution + per-query failure_class and failure_signals).

## Running Counterfactuals (Phase 2)

For each failure class A–E, run a minimal counterfactual and report recall delta. Identifies the dominant failure class for Phase 3 contract insertion.

```bash
# From repo root (RulesIngestion)
uv run python blind_eval/run_counterfactuals.py

# Run specific classes only
uv run python blind_eval/run_counterfactuals.py --classes A,C

# Custom graph/enriched/batches
uv run python blind_eval/run_counterfactuals.py --graph path/to/graph.json --enriched path/to/enriched.json --out blind_eval/results/counterfactual_results.json
```

Results are written to `blind_eval/results/counterfactual_results.json` (per-class baseline_recall, counterfactual_recall, delta, queries_affected).

## Contract for seed formation (Phase 3)

When Phase 2 identified **A (seed failure)** as dominant, a deterministic seed contract was added: anchors are reordered by **authority-for-seeding** (definition/canonical first) before capping at `max_anchors`. Only the seed-formation layer is changed.

**Enable (baseline vs contract in Phase 4):**

- Env: `RULES_USE_AUTHORITY_FOR_SEEDING=1`
- Config: `TraversalConfig.use_authority_for_seeding = True` (or in JSON config)

**Disable:** Default is off. Omit the env var or set `use_authority_for_seeding=False`.

**Location:** `traversal/seeds.py` — `_authority_score_for_seeding`, and the reorder step in `find_anchor_nodes`.
