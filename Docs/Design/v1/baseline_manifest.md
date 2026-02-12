# Stage A/B v1 Baseline Manifest

**Purpose:** Single source of truth for reproducing the Stage A/B v1 baseline and comparison runs.

---

## 1. Commit / Tag

- **Baseline commit SHA:** `3dca57d0b1799abc31661451a68a10278d657e8f`
- **Optional tag:** `stage-ab-v1-baseline` (may be applied when baseline is ratified)
- **Branch:** `stage-ab-v1-stabilization`

---

## 2. Corpus Manifest

| Book / Corpus     | Document ID   | Substrate path (relative to repo root)     | Version | Extraction inputs |
|------------------|---------------|--------------------------------------------|---------|--------------------|
| D&D 5e PHB       | DnD_PHB_5.5   | `out/mark3_evaluation/DnD_PHB_5.5`         | v2      | Mark III pipeline: Stage A (extraction + prose reconstruction), Stage B (evidence binding). |
| Starfinder 2e PC | (see evals)   | (see retrieval_lab experiments)            | —       | Same pipeline where available. |
| Swords & Wizardry| (see evals)   | (see retrieval_lab experiments)            | —       | Same pipeline where available. |

For v1 baseline comparison, the canonical corpus used is **DnD_PHB_5.5** (6999 units, 379 pages per baseline run).

---

## 3. Retrieval Configs (v1 Baseline)

| Config role           | Config file (relative to repo root)                                      | Run ID (example) |
|-----------------------|---------------------------------------------------------------------------|------------------|
| **Canonical hybrid (baseline)** | `retrieval_lab/experiments/hybrid/phb_hybrid.yaml`                  | `phb_hybrid_20260211_212748` |
| **Dual-list fusion (production default)** | `retrieval_lab/experiments/hybrid/phb_hybrid_dual_list_fusion.yaml` | `phb_hybrid_dual_list_fusion_20260212_032935` |
| **Dual-list + pairing (experimental)**     | `retrieval_lab/experiments/hybrid/phb_hybrid_dual_list_fusion_plus_pairing.yaml` | `phb_hybrid_dual_list_fusion_plus_pairing_20260212_034258` |

- **Comparison report path:** `out/retrieval_lab/stage_a_and_b/COMPARISON_BASELINE_DUAL_LIST_PAIRING.md`
- To regenerate comparison:
  ```bash
  uv run python -m retrieval_lab.compare_baseline_dual_list_pairing \
    --baseline out/retrieval_lab/stage_a_and_b/phb_hybrid_20260211_212748 \
    --dual-list out/retrieval_lab/stage_a_and_b/phb_hybrid_dual_list_fusion_20260212_032935 \
    --pairing out/retrieval_lab/stage_a_and_b/phb_hybrid_dual_list_fusion_plus_pairing_20260212_034258 \
    --output out/retrieval_lab/stage_a_and_b/COMPARISON_BASELINE_DUAL_LIST_PAIRING.md
  ```

---

## 4. Environment Fingerprint

- **Python:** 3.12+ (project `pyproject.toml` specifies `requires-python = ">=3.13"`; CI and local may use 3.12 or 3.13).
- **OS:** Linux (recommended for reproducibility; macOS/Windows may differ for path handling).
- **Dependency lock:** `uv.lock` at repo root. Use `uv sync` to install exact versions.
- **Random seed policy:** No global RNG seed is set for Stage A/B or Retrieval Lab; determinism is achieved via sorted iteration and stable ordering keys (document_id, page, structural_path, unit_id). Embedding models are deterministic for same inputs.

---

## 5. Determinism Statements

- **Stage A:** Given the same input (PDF page, OCR/model output), Stage A produces byte-identical structural outputs (SurfaceAST, prose blocks) when iteration order over structures is fixed. Deterministic replay requires same Python version and dependency versions.
- **Stage B:** Given the same Stage A artifacts (and same config), Stage B produces byte-identical EvidenceUnit outputs when all dict/set iteration uses stable sort keys (document_id, page, structural_path, ordering_key, unit_id).
- **Retrieval Lab:** Given the same corpus (substrate), config, and embedding cache, Retrieval Lab produces identical rankings and metrics. Stable ordering and dedupe rules (EvidenceUnit preferred over family anchor when both exist) ensure reproducible results.
