# v1 Baseline Suite

**Purpose:** Reproducible baseline runs across all books for Stage A/B v1. Substrate is Stage A + B output only. "Baseline" refers to the outputs under this directory (or a dated subdirectory), not ad-hoc older runs.

## Substrate (Stage A + B output)

All baselines use extracted corpora under **`out/`** (relative to repo root):

| Book | Document ID | Substrate path |
|------|-------------|----------------|
| D&D 5e PHB | DnD_PHB_5.5 | `out/DnD_PHB_5.5` |
| Starfinder 2e Player Core | StarFinderPlayerCore | `out/StarFinderPlayerCore` |
| Swords & Wizardry | Swords&Wizardry | `out/Swords&Wizardry` |

Ensure these directories exist and contain Stage A + B output (e.g. per-page `stageB.evidence_units.json` or merged EvidenceUnit corpus). See [Docs/Design/v1/baseline_manifest.md](../../Docs/Design/v1/baseline_manifest.md).

## Suite definition

- **PHB:** `phb_hybrid.yaml` (baseline) and `phb_hybrid_dual_list_fusion.yaml` (production). Optional: `phb_hybrid_dual_list_fusion_plus_pairing.yaml` for comparison.
- **Starfinder:** `starfinder_hybrid.yaml` (baseline) and `starfinder_hybrid_dual_list_fusion.yaml` (production).
- **S&W:** `swords_wizardry_hybrid.yaml` (baseline) and `swords_wizardry_hybrid_dual_list_fusion.yaml` (production).

Dual-list fusion uses **Index_U** (unit embeddings) and **Index_F** (clause-family windowed text). Unit embeddings are produced by the baseline hybrid run; family embeddings are computed and cached (MongoDB or run output) the first time you run the dual-list config for that corpus.

## Fresh baselines (all books, end-to-end)

From **RulesIngestion** repo root, with `uv` and dependencies installed (`uv sync`):

### One-shot: run the script

```bash
./evals/v1_baseline/run_baseline_suite.sh
```

This runs hybrid retrieval (embed + eval) for all three books into `evals/v1_baseline/<YYYYMMDD>/`, using `--substrate-version v1` so run IDs are stable. For each book it runs baseline hybrid then dual-list fusion; the first dual-list run for a book generates and caches family (Index_F) embeddings.

### Manual: step by step

1. **Output directory** (optional; configs default to `out/retrieval_lab/stage_a_and_b` or `experiments`). For a dated baseline:
   ```bash
   export BASELINE_DATE=$(date +%Y%m%d)
   mkdir -p evals/v1_baseline/$BASELINE_DATE
   ```

2. **PHB — baseline (hybrid, no dual-list)**
   ```bash
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/hybrid/phb_hybrid.yaml \
     --output evals/v1_baseline/$BASELINE_DATE \
     --substrate-version v1
   ```

3. **PHB — dual-list fusion (production default)**
   ```bash
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/hybrid/phb_hybrid_dual_list_fusion.yaml \
     --output evals/v1_baseline/$BASELINE_DATE \
     --substrate-version v1
   ```
   Embeddings are reused from step 2 (same substrate + version).

4. **Starfinder — baseline then dual-list**
   ```bash
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml \
     --output evals/v1_baseline/$BASELINE_DATE \
     --substrate-version v1
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/hybrid/starfinder_hybrid_dual_list_fusion.yaml \
     --output evals/v1_baseline/$BASELINE_DATE \
     --substrate-version v1
   ```
   Dual-list run reuses unit embeddings and computes/caches family embeddings on first run.

5. **Swords & Wizardry — baseline then dual-list**
   ```bash
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml \
     --output evals/v1_baseline/$BASELINE_DATE \
     --substrate-version v1
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/hybrid/swords_wizardry_hybrid_dual_list_fusion.yaml \
     --output evals/v1_baseline/$BASELINE_DATE \
     --substrate-version v1
   ```
   Same as Starfinder: dual-list computes family embeddings on first run.

6. **Comparison report (PHB baseline vs dual-list vs pairing)**  
   After runs, if you have baseline, dual-list, and pairing experiment dirs:
   ```bash
   uv run python -m retrieval_lab.compare_baseline_dual_list_pairing \
     --baseline evals/v1_baseline/$BASELINE_DATE/phb_hybrid_<timestamp> \
     --dual-list evals/v1_baseline/$BASELINE_DATE/phb_hybrid_dual_list_fusion_<timestamp> \
     --pairing evals/v1_baseline/$BASELINE_DATE/phb_hybrid_dual_list_fusion_plus_pairing_<timestamp> \
     --output evals/v1_baseline/$BASELINE_DATE/COMPARISON_BASELINE_DUAL_LIST_PAIRING.md
   ```

## Default config per corpus

| Corpus | Default config (production) | Baseline for comparison |
|--------|-----------------------------|--------------------------|
| PHB | phb_hybrid_dual_list_fusion.yaml | phb_hybrid.yaml |
| Starfinder | starfinder_hybrid_dual_list_fusion.yaml | starfinder_hybrid.yaml |
| S&W | swords_wizardry_hybrid_dual_list_fusion.yaml | swords_wizardry_hybrid.yaml |

See [Docs/Design/v1/retrieval_lab_v1.md](../../Docs/Design/v1/retrieval_lab_v1.md) for full run options, two-step (embed-only then eval), and regression policy.
