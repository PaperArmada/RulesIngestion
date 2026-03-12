# Workflow: PF2E Atomic Benchmark

This workflow defines the canonical Pathfinder 2e atomic benchmark path.

Goal: create and maintain a same-language atomic benchmark that can be reused across rulesets without rewriting the question text, so the resulting metrics expose baseline retrieval behavior and vocabulary drift rather than benchmark phrasing drift.

---

## 1) Why this benchmark exists

Use the PF2E atomic benchmark when you want fast, comparable signal on narrow retrieval primitives before or alongside the broader `50q` benchmark.

The atomic benchmark is intentionally different from the corpus-level PF2E benchmark:

- `pathfinder2e_player_core_50q_benchmark.json` measures broad corpus retrieval quality for real user-facing questions.
- `pathfinder2e_player_core_atomic_rules_benchmark.json` measures whether the retriever can land the same small set of universal rules concepts using the exact same question language used in other rulesets.

This is the key contract:

- Do not rewrite atomic question text per ruleset.
- Reuse the shared template wording verbatim.
- Only the answers, summaries, notes, and gold annotations should change per corpus.

If the wording changes, the benchmark stops measuring vocabulary drift and starts measuring prompt-author drift.

---

## 2) Canonical PF2E atomic files

Run all commands from `RulesIngestion` root.

Current PF2E atomic contract:

- Benchmark definition: `evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_atomic_rules_benchmark.json`
- Shared template source: `evals/retrieval/benchmark_template_atomic_rules.json`
- Dense config: `retrieval_lab/experiments/dense/pf2e_atomic_rules.yaml`
- Substrate: `out/Pathfinder2ePlayerCore`
- Document ID: `PathCore`
- Model baseline: `all-mpnet-base-v2`
- Chunk recipe: `min_chars=200`, `merge_chunks=true`, `merge_max_chars=2000`

Reference workflow:

- `Docs/Workflows/WORKFLOW-PF2E-Agentic-AutoGold-Runbook.md`

---

## 3) Atomic benchmark contract

The PF2E atomic benchmark uses the shared atomic query IDs and shared wording on purpose.

Agent rules:

1. Keep every atomic question string identical to the shared template.
2. Do not "PF2E-ify" the wording to make retrieval easier.
3. Use PF2E-specific answers and gold only after retrieval/citation work.
4. If a concept is not present as a codified rule in PF2E, leave the question text unchanged and use benchmark annotation to capture refusal/not-applicable behavior.
5. Treat the checked-in JSON as the benchmark definition. If chunk topology changes, regenerate the projection rather than hand-editing stale chunk IDs.

What this benchmark is good for:

- fast baseline measurement,
- cross-ruleset apples-to-apples comparison,
- early warning that a corpus uses different terminology than the shared query language,
- separating vocabulary mismatch from general retrieval quality problems.

What this benchmark is not for:

- replacing the PF2E `50q` benchmark for promotion decisions,
- corpus-specific phrasing optimization,
- measuring broad user-facing query coverage.

---

## 4) Phase 0: Preflight

Before running retrieval:

1. Confirm the PF2E substrate exists.
2. Confirm the atomic benchmark JSON is valid.
3. Confirm the benchmark still matches the shared template wording.
4. Confirm you are keeping the corpus contract fixed for comparison.

Recommended checks:

```bash
ls out/Pathfinder2ePlayerCore
uv run python -m retrieval_lab.benchmark_lint \
  evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_atomic_rules_benchmark.json
```

Manual language-lock check:

- compare the `question` strings in `pathfinder2e_player_core_atomic_rules_benchmark.json` against `benchmark_template_atomic_rules.json`,
- if a question was rewritten for PF2E convenience, revert it before running experiments.

---

## 5) Phase 1: Establish atomic baseline

Run the atomic benchmark first when you want fast signal before spending time on the broader `50q` benchmark.

### 5.1 Embed-only

This embed step intentionally runs against the merged retrieval corpus defined in the config, not the raw page-level Stage B units.

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/pf2e_atomic_rules.yaml \
  --experiment-name pf2e_atomic_rules_embed \
  --embed-only
```

Capture the emitted `run_id`. If `min_chars`, `merge_chunks`, or `merge_max_chars` change, treat that as a new corpus contract and re-embed before eval.

### 5.2 Eval-only

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/pf2e_atomic_rules.yaml \
  --experiment-name pf2e_atomic_rules_eval \
  --run-id <RUN_ID_FROM_EMBED_STEP>
```

Expected outputs:

- `REPORT.md`
- `metrics.json`
- `per_query.json`
- `retrieved_chunks.json`
- `benchmark.<surface>.json`
- `benchmark.<surface>.contract.json`
- `benchmark_contract_validation.json`
- `embeddings/corpus_index.json`

---

## 6) Phase 2: Interpret atomic results

Read the atomic benchmark as a diagnostic surface, not as a replacement for the broader benchmark.

Questions to ask:

1. Which universal concepts retrieve cleanly in PF2E with shared wording?
2. Which misses look like vocabulary drift rather than corpus absence?
3. Which misses come from chunking or ranking issues rather than wording mismatch?

Signals that suggest vocabulary drift:

- the correct rule exists, but candidates are dominated by adjacent terminology rather than the exact mechanic,
- head-ranking is weak on atomic questions even when PF2E `50q` is healthy,
- misses cluster around template words that PF2E expresses differently.

Signals that suggest a broader retrieval problem:

- the correct area of the book rarely enters candidates at all,
- misses are spread across most atomic concepts rather than a few vocabulary-sensitive ones,
- the same failure pattern also appears on the PF2E `50q` benchmark.

---

## 7) Phase 3: Annotate and ground gold

The checked-in PF2E atomic benchmark is the language-locked definition surface. It can start life with empty answers and gold, but it is more valuable once grounded.

Recommended annotation order:

1. Fill `expected_answer_summary`.
2. Fill `answer` with a concise PF2E-specific grounded answer.
3. Add `source_page`.
4. Add `required_gold`, `supporting_gold`, and `required_gold_rationale`.
5. Re-run benchmark lint.

Gold discipline:

- Prefer 1 required chunk when possible.
- Use 2 required chunks only when the rule is genuinely split.
- Demote near-duplicate or adjacency spillover chunks to `supporting_gold`.
- Preserve the question wording even when the answer is "PF2E handles this differently" or "this is not a codified rule."

If you want the LLM-assisted grounding path, use the PF2E auto-gold workflow after the atomic benchmark exists as a stable definition surface.

---

## 8) Relationship to the PF2E auto-gold runbook

Use both workflows, but for different jobs:

1. Run this atomic workflow when you want same-language baseline signal and vocabulary-drift diagnostics.
2. Run `WORKFLOW-PF2E-Agentic-AutoGold-Runbook.md` when you want broader corpus-level gold creation and validation on the PF2E `50q` benchmark.

Suggested progression:

1. Atomic benchmark for fast structural and vocabulary-drift signal.
2. PF2E `50q` baseline for primary quality measurement.
3. PF2E auto-gold runbook for scalable gold creation and review.

---

## 9) Decision rules

An agent should follow these rules:

1. Never rewrite PF2E atomic question text to match PF2E terminology.
2. Never use atomic results alone for production promotion decisions.
3. Always compare atomic runs on a fixed substrate and fixed benchmark definition.
4. Always keep the atomic benchmark language-locked to the shared template.
5. Always pair atomic findings with per-query inspection before claiming vocabulary drift.

---

## 10) Minimum evidence bundle to return

When the agent finishes an atomic benchmark run, it should return:

1. exact artifact directory path,
2. benchmark file path used,
3. model and chunk recipe used,
4. top-line metric table,
5. per-query misses that look like vocabulary drift,
6. per-query misses that look like true retrieval failures,
7. any benchmark lint findings.
