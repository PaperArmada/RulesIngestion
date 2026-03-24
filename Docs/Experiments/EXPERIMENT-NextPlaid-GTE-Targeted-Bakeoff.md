# Experiment: NextPlaid + GTE-ModernColBERT-v1 (Targeted Falsification)

**Purpose:** Run a narrow falsification test for first-hop retrieval using NextPlaid with `lightonai/GTE-ModernColBERT-v1`, focused on known retrieval gaps without re-running broad bakeoffs.

**Status:** Executed (Stage 1 complete, Stage 2 controlled start complete).
**Scope:** Retrieval-only admission test; no decomposition, no rerank, no corpus re-curation.
**Related:** `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`, `Docs/Design/ARCHITECTURE-Chunking-System-Deep-Dive-2026-02-28.md`, `Docs/Reports/REPORT-SWCR-Retrieval-Deep-Dive-2026-03-17.md`, `retrieval_lab/run_experiment.py`.

---

## 0. Execution update (2026-03-24)

### Authoritative artifacts

- Stage 1 authoritative baseline:
  - `out/retrieval_lab/experiments/nextplaid_experiments/nextplaid_stage1_authoritative_baseline.json`
- Stage 1 report source:
  - `out/retrieval_lab/experiments/nextplaid_experiments/nextplaid_stage1_real_rerun_post_canonical_20260324_134912/stage1_report.json`
- Stage 2 controlled start decision:
  - `out/retrieval_lab/experiments/nextplaid_experiments/nextplaid_stage2_controlled_start_decision.json`
- Stage 2 PHB dual-list report:
  - `out/retrieval_lab/experiments/nextplaid_experiments/nextplaid_stage2_phb_duallist_20260324_200353/stage2_report.json`
- Stage 2 repro comparison:
  - `out/retrieval_lab/experiments/nextplaid_experiments/nextplaid_stage2_repro_comparison.json`

### Stage 1 outcome (B1)

- `go_stage2: true`
- Positive signals:
  - `rescued_blind_001_04: true`
  - `phb_t2_completion_improved: true`
- Still flat:
  - `swcr_true_miss_lift: false`
- Guardrails:
  - `guardrail_regression: false`

### Stage 2 controlled start outcome (B2, PHB)

- Integrity preflight clean (`missing_required_gold_total = 0`)
- PHB required-full-set@10:
  - Stage 1 PHB baseline: `20/32`
  - Stage 2 dual-list: `22/32`
  - Delta: `+2`
- Candidate inflation controlled:
  - avg `+0.78125` vs U top10
- Latency stable:
  - p95 around `25.47ms` (repro `25.58ms`)
- Repro status:
  - semantic decision match: `true`
  - query-level full-set and gold-entered-pool sets: matched

### Full-suite zero-result diagnostic (2026-03-24, PHB/Starfinder/SWCR)

- Diagnostic artifact root:
  - `out/retrieval_lab/experiments/nextplaid_experiments/nextplaid_zero_diagnostic_20260324_203131`
- Diagnostic method:
  - Probe 1: real benchmark questions with deeper retrieval window (`top_k=100`)
  - Probe 2: oracle self-retrieval (query is a snippet of required-gold text)
  - Goal: classify `retrieval quality collapse` vs `corpus/query alignment defect`

Observed:

- B0 source for baseline MRR values in this block:
  - `Docs/Reports/REFERENCE-Retrieval-Benchmark-Results-Timeline.md` (Quick reference table, benchmark clean subset column)
- Corrected full-suite fixed-run source for contrast values:
  - `out/retrieval_lab/experiments/nextplaid_experiments/nextplaid_full_suite_fixed_20260324_204736/full_suite_nextplaid_fixed_summary.json`

- PHB5e:
  - required-gold hit rates: `@10=0.897`, `@20=0.974`, `@50=1.000`, `@100=1.000`
  - oracle self-hit: `@1=0.949`, `@10=1.000`
  - contrast baseline/context: B0 benchmark clean-subset MRR `0.5875`; corrected fixed-run clean-subset MRR `0.7437` (`+0.1562`)
- Starfinder:
  - required-gold hit rates: `@10=0.860`, `@20=0.920`, `@50=0.960`, `@100=0.960`
  - oracle self-hit: `@1=0.980`, `@10=1.000`
  - contrast baseline/context: B0 benchmark clean-subset MRR `0.6162`; corrected fixed-run clean-subset MRR `0.6446` (`+0.0284`)
- SWCR:
  - required-gold hit rates: `@10=0.762`, `@20=0.810`, `@50=0.857`, `@100=0.952`
  - oracle self-hit: `@1=1.000`, `@10=1.000`
  - contrast baseline/context: B0 benchmark clean-subset MRR `0.2868`; corrected fixed-run clean-subset MRR `0.6021` (`+0.3153`)

Interpretation:

- This does **not** match a corpus/query alignment defect (oracle retrieval is strong).
- The original `0.0000` full-suite outputs were caused by a **run-path scoring bug** (stale `_required_gold` fields overriding projected `required_gold`), not a retriever failure.
- After patching projection/scoring consistency and rerunning full-suite, PHB/Starfinder/SWCR no longer show collapse and are above B0 baselines.
- Repro pass confirms stability:
  - fixed run: `nextplaid_full_suite_fixed_20260324_204736`
  - fixed repro: `nextplaid_full_suite_fixed_repro_20260324_211148`
  - PHB/Starfinder/SWCR clean-subset MRR deltas remain positive in both runs with only minor variance.
- Updated follow-up focus: targeted optimization for PF2e/SR4 deltas and one additional parity check on per-query rank shifts, rather than depth-sensitivity triage.

### Multihop comparison integration (reported vs NextPlaid)

Integrated artifact:

- `out/retrieval_lab/experiments/nextplaid_experiments/nextplaid_multihop_benchmark_pit_20260324_212049/nextplaid_multihop_reported_integration.json`

This artifact joins:

- fresh NextPlaid multihop slices (PHB/PF2e working-set and microbundle surfaces),
- previously reported multihop references (PHB E0/E6, PF2e reported runs), and
- explicit delta blocks for direct `NextPlaid - reported` comparison.

Integrated comparison highlights:

- PHB combined (`67q`, working_set + microbundle; apples-to-apples):
  - NextPlaid MRR: `0.5614`
  - vs reported PHB E0 baseline MRR `0.6195` -> delta `-0.0581`
  - vs reported PHB E6 qvocab MRR `0.5937` -> delta `-0.0322`
- PF2e working-set-only (`20q`, apples-to-apples with qvocab E6 working-set run):
  - NextPlaid MRR: `0.6725`
  - vs reported PF2e E6 qvocab working-set MRR `0.8542` -> delta `-0.1817`
  - required-full-set@10 delta on this pair: `+0.10` (head-rank metrics remain lower).

Surface compatibility note:

- PHB comparison is directly aligned on benchmark composition (`working_set + microbundle`).
- PF2e historical report runs are mixed-surface (`working_set + 50q`) except the
  qvocab working-set-only run used for strict apples-to-apples comparison.

---

## 1. Core hypothesis

**Hypothesis:** A token-level late-interaction retriever improves candidate admission on known bridge/miss cases.

**Null:** It mostly shifts ordering while true bottlenecks remain multi-evidence closure/completion.

This is a falsification test, not a new retrieval program.

---

## 2. What this experiment is and is not

This experiment **is**:

- A targeted first-hop retriever bakeoff.
- Run on existing canonical Retrieval Lab corpus contracts.
- Judged against existing anchored baselines.
- Focused on known misses and bridge queries.

This experiment **is not**:

- A chunking/shaping experiment.
- A benchmark curation pass.
- A decomposition/multihop/rerank bakeoff.
- A full-suite all-book rerun.

---

## 3. Correct anchors and corpus/benchmark policy

Use these comparison anchors and constraints:

1. **Starfinder anchor**
   - Benchmark: `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json`
   - Primary focus: `blind_001_01..blind_001_04` (headline: `blind_001_04`).
   - Keep canonical shaped-corpus contract behavior; do not introduce alternate chunk recipes.

2. **PHB anchor**
   - Primary benchmark: `evals/retrieval/PHB5e/dnd_5e_2024_rules_50q_benchmark.json`
   - Evaluate on `clean_subset` and `full_working_set` surfaces emitted by Retrieval Lab.
   - Treat legacy Stage A/B dual-list files as historical references only, not the canonical benchmark surface.
   - PHB is an explicit required run in this experiment.

3. **SWCR anchor**
   - Benchmark: `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json`
   - Miss slice must be generated from the latest contract-valid run (`per_query.clean_subset.json` with `failure_type == retrieval_miss`).
   - Exclude benchmark-debt/removed cases from the miss slice.

4. **Contract rule (hard)**
   - All runs must be contract-valid.
   - No `allow_benchmark_contract_mismatch` overrides.
   - Gold IDs must be projected to active shaped corpus before scoring.
   - Integrity preflight for missing required gold IDs is mandatory before stop/go decisions.

5. **Canonical benchmark catalog alignment (README)**
   - Canonical recommendation benchmarks referenced here:
     - Starfinder atomic + Starfinder 50q
     - S&W revised benchmark
   - This experiment intentionally includes PHB as an additional targeted slice.

---

## 4. Target slices to run

Run exactly three narrow slices:

### Slice A: Starfinder bridge-failure slice

- Use `queries[].id` from `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json`:
  - `blind_001_01` ("What abilities can cancel out Vent Gas when a Barathu uses it?")
  - `blind_001_02` ("Suggest some complimentary feats for a Level 9 Lashunta Solarian")
  - `blind_001_03` ("Can I use Redirect Current to power up a console?")
  - `blind_001_04` ("Can I use Side Step to hit something that is inanimate or maybe a robot?")
- Headline success criterion: rescue `blind_001_04` into top-20 candidate pool.

### Slice B: PHB compositional slice

- Source benchmark: `dnd_5e_2024_rules_50q_benchmark.json`
- Scored surface for decisions: `clean_subset`
- Focus metrics: T2 completion metrics (`Full-set@10` / required-full-set variants) and regression checks.

### Slice C: SWCR true-retrieval-miss slice

- Source benchmark: `swords_wizardry_complete_revised_benchmark.json`
- Slice generation: from most recent contract-valid `per_query.clean_subset.json` misses.
- Exclude known benchmark issues and any retired questions.

---

## 5. Two-stage test structure

## Stage 1 (required): U-only canonical EvidenceUnits

Build and test one NextPlaid index per corpus over canonical EvidenceUnits only.

Do not include:

- Clause-family projection
- Sidecar/pairing expansion
- Query rewriting/decomposition
- Rerankers

Goal: isolate retriever engine + encoder effect on admission.

## Stage 2 (conditional): PHB dual-list reproduction

Only if Stage 1 is positive, run PHB dual-list reproduction.
This condition is satisfied in current execution and Stage 2 has started in controlled mode:

- `Index_U`: EvidenceUnits
- `Index_F`: clause-family projection
- Merge/quota policy matching current PHB dual-list policy

If Stage 1 is flat, stop.

---

## 6. Runtime setup (NextPlaid + model)

Use GPU-backed NextPlaid with the target model; do not silently substitute a lightweight model for Stage 1.

```bash
docker pull ghcr.io/lightonai/next-plaid:cuda-1.1.3

docker run --gpus all \
  -p 8080:8080 \
  -v ~/.local/share/next-plaid:/data/indices \
  -v ~/.cache/huggingface/next-plaid:/models \
  ghcr.io/lightonai/next-plaid:cuda-1.1.3 \
  --host 0.0.0.0 \
  --port 8080 \
  --index-dir /data/indices \
  --model lightonai/GTE-ModernColBERT-v1 \
  --cuda \
  --batch-size 128

curl http://localhost:8080/health
```

Install client:

```bash
pip install next-plaid-client
```

---

## 7. Retrieval Lab integration plan

Implemented minimal adapters:

1. **Index builder script**
   - Path: `scripts/bakeoff_nextplaid_build_index.py`
   - Loads already-shaped Retrieval Lab corpus.
   - Pushes text + metadata to NextPlaid.
   - Never mutates corpus contract semantics.

2. **Retriever adapter**
   - Path: `retrieval_lab/retrievers/nextplaid.py`
   - Calls `/indices/{name}/search_with_encoding`
   - Params: `top_k=20`, `n_ivf_probe=8`, `n_full_scores=4096`
   - Records latency
   - Maps returned IDs back to canonical candidate rows

No extra features in adapter path (no rewrites, no rerank, no expansion).

---

## 8. Index identity and metadata contract

When ingesting documents, preserve enough metadata to reconstruct exact EvidenceUnits:

- `unit_id`
- `document_id`
- `page`
- `structural_path`
- `unit_type`
- `source_unit_ids`
- `corpus_manifest_hash`
- `retrieval_lab_corpus_shape` (example: `min200_merge2000`)

Index identity must encode corpus + condition; example names:

- `sfpc_u_nextplaid_gte_v1`
- `phb_u_nextplaid_gte_v1`
- `swcr_u_nextplaid_gte_v1`
- `phb_f_nextplaid_gte_v1` (Stage 2 only)

---

## 9. Minimal script/config skeleton

## 9.1 Index creation skeleton

```python
from next_plaid_client import NextPlaidClient, IndexConfig

client = NextPlaidClient("http://localhost:8080")
client.create_index("sfpc_u_nextplaid_gte_v1", IndexConfig(nbits=4))
```

## 9.2 Ingestion skeleton

```python
client.add(
    "sfpc_u_nextplaid_gte_v1",
    documents=[c["text"] for c in corpus],
    metadata=[
        {
            "unit_id": c["id"],
            "document_id": c.get("document_id", ""),
            "page": c.get("page"),
            "unit_type": c.get("unit_type"),
            "structural_path": " > ".join(c.get("structural_path", [])),
            "source_unit_ids": c.get("source_unit_ids", []),
        }
        for c in corpus
    ],
)
```

## 9.3 Search skeleton

```python
results = client.search(
    "sfpc_u_nextplaid_gte_v1",
    ["your query"],
    params={
        "top_k": 20,
        "n_ivf_probe": 8,
        "n_full_scores": 4096,
    },
)
```

---

## 10. Evaluation protocol

Conditions:

- **B0:** existing anchored baseline artifacts (no rerun).
- **B1:** NextPlaid + GTE over canonical U-only EvidenceUnits.
- **B2 (PHB only, conditional):** NextPlaid-backed dual-list reproduction.

Metric priority:

1. Gold-in-candidates
2. T2 Full-set@10 (or required/full-set equivalent)
3. First-gold rank
4. T1 regressions (or closest guardrail equivalent for the slice)
5. P95 retrieval latency
6. Candidate inflation

---

## 11. Promotion / stop thresholds

Continue only if at least one condition is met:

- `blind_001_04` rescued into top-20 pool
- PHB T2 completion improves over current anchor
- SWCR true-miss slice shows meaningful admission lift
- No meaningful T1/guardrail regressions

Stop early if:

- MRR improves but gold-in-candidates does not
- Full-set@10 is flat
- Gains appear only after adding extra levers
- Operational complexity outweighs benefit

---

## 12. Learnability gates (must pass before expansion)

Stage 2 and broader integration are blocked until all gate groups pass.

### Gate A: Test wall (must be green)

- Unit tests for payload construction, ID mapping, param forwarding, and telemetry.
- Contract tests for run identity and artifact compatibility.
- Controlled integration tests for NextPlaid request/response behavior.
- Slice/evaluation tests for Starfinder/PHB/SWCR selection logic.

### Gate B: Evidence quality (Stage 1 result quality)

- Results emitted for all required Stage 1 slices: Starfinder, PHB, SWCR.
- Gold-in-candidates and first-gold-rank are present for all evaluated queries.
- Required completion metric is present for PHB compositional slice.

### Gate C: Guardrails

- No meaningful guardrail regressions versus B0 anchor on required surfaces.
- Any regression must be explainable and accompanied by per-query diagnostics.

### Gate D: Operational reliability

- Per-query latency and candidate inflation are captured.
- Run bundle is contract-valid (`benchmark_contract_validation.json` passes).
- Run outputs are reproducible from recorded index/run parameters.

If any gate fails, stop at Stage 1 and publish findings; do not run Stage 2.

---

## 13. Required run logging

Per run, emit:

- corpus manifest hash
- NextPlaid server config
- model ID
- index name
- search params
- ingestion time
- per-query retrieval latency
- raw result IDs
- mapped `unit_id`s
- gold-entered-pool boolean
- first-gold rank
- slice membership tags (`starfinder_bridge`, `phb_compositional`, `swcr_true_miss`)

Artifacts should look like standard Retrieval Lab outputs, not an ad-hoc side channel.

---

## 14. Minimal execution order

1. Start NextPlaid with GTE model.
2. Build Starfinder U-only index.
3. Run 4-query Starfinder bridge slice.
4. Build and run PHB U-only slice (clean subset + guardrails).
5. Run SWCR true-miss slice from latest contract-valid misses.
6. Decide stop/go from combined Stage 1 evidence across Starfinder + PHB + SWCR.
7. If Stage 1 is positive, run PHB Stage 2 dual-list reproduction.

Current state:

- Steps 1-7 have been executed for controlled Stage 2 start.
- Stage 2 repro pass has been executed and compared.

---

## 15. Checklist

- [x] NextPlaid server healthy with `lightonai/GTE-ModernColBERT-v1`
- [x] New index builder script created
- [x] New retriever adapter created
- [x] Benchmark slice files/materialization prepared
- [x] Starfinder Stage 1 run completed and logged
- [x] PHB Stage 1 run completed and logged
- [x] SWCR Stage 1 run completed and logged
- [x] Stage 2 decision made from Stage 1 evidence
- [ ] Final recommendation written with stop/go rationale

---

## 16. Notes

- Keep this bakeoff narrow and falsifiable.
- Preserve corpus contract identity across all conditions.
- Compare against real anchors, not stale or legacy convenience baselines.
