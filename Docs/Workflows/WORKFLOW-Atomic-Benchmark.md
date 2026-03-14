# Workflow: Atomic Benchmark

This workflow defines the canonical atomic benchmark path for any rules corpus.

Goal: create and maintain a same-language atomic benchmark that can be reused across rulesets without rewriting the question text, so the resulting metrics expose baseline retrieval behavior and vocabulary drift rather than benchmark phrasing drift.

---

## 1) Why this benchmark exists

Use the atomic benchmark when you want fast, comparable signal on narrow retrieval primitives before or alongside a broader corpus benchmark.

The atomic benchmark is intentionally different from a broader corpus benchmark:

- a broader benchmark measures corpus retrieval quality for real user-facing questions,
- an atomic benchmark measures whether the retriever can land the same small set of universal rules concepts using the exact same question language used in other rulesets.

This is the key contract:

- Do not rewrite atomic question text per ruleset.
- Reuse the shared template wording verbatim.
- Only the answers, summaries, notes, and gold annotations should change per corpus.

If the wording changes, the benchmark stops measuring vocabulary drift and starts measuring prompt-author drift.

---

## 2) Corpus inputs and atomic files

Run all commands from `RulesIngestion` root.

Resolve this corpus contract before running anything:

- Corpus slug: `<CORPUS_SLUG>`
- Atomic benchmark definition: `<ATOMIC_BENCHMARK_PATH>`
- Shared template source: `evals/retrieval/benchmark_template_atomic_rules.json`
- Dense config: `<ATOMIC_EXPERIMENT_CONFIG>`
- Substrate: `<SUBSTRATE_DIR>`
- Document ID: `<DOCUMENT_ID>`
- Substrate version: `<SUBSTRATE_VERSION>`
- Broader benchmark path: `<BROADER_BENCHMARK_PATH>`
- Model baseline: `<MODEL_ID>`
- Chunk recipe: `min_chars=<MIN_CHARS>`, `merge_chunks=<BOOL>`, `merge_max_chars=<MERGE_MAX_CHARS>`

Reference workflow:

- `Docs/Workflows/WORKFLOW-PF2E-Agentic-AutoGold-Runbook.md`

---

## 3) Atomic benchmark contract

The atomic benchmark uses the shared atomic query IDs and shared wording on purpose.

Agent rules:

1. Keep every atomic question string identical to the shared template.
2. Do not rewrite the wording to make retrieval easier for a specific ruleset.
3. Use corpus-specific answers and gold only after retrieval/citation work.
4. If a concept is not present as a codified rule in the corpus, leave the question text unchanged and use benchmark annotation to capture refusal or not-applicable behavior.
5. Treat the checked-in versioned benchmark JSON plus its metadata plus the matching config `substrate_version` as the corpus contract.
6. If chunk topology changes, create a new benchmark version or explicitly re-anchor the existing surface rather than hand-editing stale chunk IDs under an old contract.

What this benchmark is good for:

- fast baseline measurement,
- cross-ruleset apples-to-apples comparison,
- early warning that a corpus uses different terminology than the shared query language,
- separating vocabulary mismatch from general retrieval quality problems.

What this benchmark is not for:

- replacing a broader corpus benchmark for promotion decisions,
- corpus-specific phrasing optimization,
- measuring broad user-facing query coverage.

---

## 4) Phase 0: Preflight

Before running retrieval:

1. Confirm the substrate exists.
2. Confirm the atomic benchmark JSON is valid.
3. Confirm the benchmark still matches the shared template wording.
4. Confirm the benchmark metadata and config still agree on substrate path, document id, substrate version, and chunk recipe.

Recommended checks:

```bash
ls <SUBSTRATE_DIR>
uv run python -m retrieval_lab.benchmark_lint \
  <ATOMIC_BENCHMARK_PATH>
```

Manual language-lock check:

- compare the `question` strings in `<ATOMIC_BENCHMARK_PATH>` against `benchmark_template_atomic_rules.json`,
- if a question was rewritten for corpus-specific convenience, revert it before running experiments.

Contract check:

- verify the benchmark filename, benchmark `metadata.substrate_version`, and config `substrate_version` all describe the same target corpus,
- if `min_chars`, `merge_chunks`, or `merge_max_chars` change, create a new benchmark version or explicitly re-anchor before running comparisons.

---

## 5) Phase 1: Establish atomic baseline

Run the atomic benchmark first when you want fast signal before spending time on the broader benchmark.

### 5.1 Embed-only

This embed step intentionally runs against the merged retrieval corpus defined in the config, not the raw page-level Stage B units.

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <ATOMIC_EXPERIMENT_CONFIG> \
  --experiment-name <CORPUS_SLUG>_atomic_rules_embed \
  --embed-only
```

Capture the emitted `run_id`. If `min_chars`, `merge_chunks`, or `merge_max_chars` change, treat that as a new corpus contract and re-embed before eval.

### 5.2 Eval-only

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <ATOMIC_EXPERIMENT_CONFIG> \
  --experiment-name <CORPUS_SLUG>_atomic_rules_eval \
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

Note:

- emitted `.contract.json` files are validation artifacts, not the source-of-truth readiness contract for the benchmark surface.

---

## 6) Phase 2: Interpret atomic results

Read the atomic benchmark as a diagnostic surface, not as a replacement for the broader benchmark.

Questions to ask:

1. Which universal concepts retrieve cleanly in the corpus with shared wording?
2. Which misses look like vocabulary drift rather than corpus absence?
3. Which misses come from chunking or ranking issues rather than wording mismatch?

Signals that suggest vocabulary drift:

- the correct rule exists, but candidates are dominated by adjacent terminology rather than the exact mechanic,
- head-ranking is weak on atomic questions even when the broader benchmark is healthy,
- misses cluster around template words that the corpus expresses differently.

Signals that suggest a broader retrieval problem:

- the correct area of the book rarely enters candidates at all,
- misses are spread across most atomic concepts rather than a few vocabulary-sensitive ones,
- the same failure pattern also appears on the broader benchmark.

---

## 7) Phase 3: Annotate and ground gold

The checked-in atomic benchmark is the language-locked definition surface. It can start life with empty answers and gold, but it is more valuable once grounded.

Recommended annotation order:

1. Fill `expected_answer_summary`.
2. Fill `answer` with a concise corpus-specific grounded answer.
3. Add `source_page`.
4. Add `required_gold`, `supporting_gold`, and `required_gold_rationale`.
5. Re-run benchmark lint.

Gold discipline:

- Prefer 1 required chunk when possible.
- Use 2 required chunks only when the rule is genuinely split.
- Demote near-duplicate or adjacency spillover chunks to `supporting_gold`.
- Preserve the question wording even when the answer is "this corpus handles this differently" or "this is not a codified rule."

If you want the LLM-assisted grounding path, use the auto-gold workflow after the atomic benchmark exists as a stable definition surface.

---

## 8) Relationship to the auto-gold runbook

Use both workflows, but for different jobs:

1. Run this atomic workflow when you want same-language baseline signal and vocabulary-drift diagnostics.
2. Run `WORKFLOW-PF2E-Agentic-AutoGold-Runbook.md` when you want broader corpus-level gold creation and validation on a full benchmark.

Suggested progression:

1. Atomic benchmark for fast structural and vocabulary-drift signal.
2. Broader benchmark baseline for primary quality measurement.
3. Auto-gold runbook for scalable gold creation and review.

---

## 9) Decision rules

An agent should follow these rules:

1. Never rewrite atomic question text to match corpus terminology.
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
