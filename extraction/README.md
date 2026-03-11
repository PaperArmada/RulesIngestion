# Extraction — Mark III Stage A & B

This package implements **Stage A (Prose Reconstruction)** and **Stage B (Evidence Binding)** for RulesIngestion Mark III. It is the only normative extraction code for the prose-first pipeline.

---

## 1. What this package does

- **Stage A:** PDF page → rendered image → DeepSeek OCR → raw markdown → **SurfaceAST** (deterministic structural tree) → Stage A gates.
- **Stage B:** SurfaceAST → segmentation → **EvidenceUnits** (prose-bound units with provenance) → Stage B gates.

**Invariant:** Authored prose is the canonical substrate. No semantic claim exists without a pointer back to verbatim text. Safety comes from **contracts and provenance**, not from lossy extraction.

Downstream (Stage C: graph, indices, retrieval) consumes **EvidenceUnits only**. No chunks, blocks, or marker streams.

---

## 2. Canonical design docs (read these first)

| Doc | Purpose |
| --- | --- |
| **`Docs/Design/v1/architecture_overview.md`** | Canonical Mark III architecture, pipeline spine, and artifact boundaries. |
| **`Docs/Design/v1/stage_a_contract.md`** | Normative Stage A contract: inputs, outputs, ordering, and replay guarantees. |
| **`Docs/Design/v1/stage_b_contract.md`** | Normative Stage B contract: EvidenceUnit schema, segmentation, and provenance invariants. |
| **`Docs/Design/v1/gates_stage_c_d.md`** | Current gate framing for what is stabilized now versus deferred to later stages. |
| **`Docs/Design/ARCHITECTURE-TOC-Structural-Enrichment.md`** | Current TOC enrichment architecture that feeds Stage B structural context. |
| **`Docs/Design/gold_resolution_design.md`** | Current benchmark projection and corpus-contract lifecycle used by Retrieval Lab. |

Design is authoritative. Code that diverges from these contracts is wrong.

---

## 3. Module map

| Module               | Responsibility                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **`pipeline.py`**    | Top-level API: `run_a_only()`, `run_a_b()`, `run_stage_b_on_result()`. Use these from scripts or tests.             |
| **`stage_a.py`**     | Stage A orchestration: page source → OCR → raw markdown → AST → gates. Returns `StageAResult`.                      |
| **`stage_b.py`**     | Stage B: SurfaceAST → segmenter/chunker → EvidenceUnits → gates. Returns `StageBResult`.                            |
| **`ocr_worker.py`**  | DeepSeek OCR 2 invocation; returns raw markdown per page.                                                           |
| **`page_source.py`** | Renders PDF pages to images; fingerprints and provenance.                                                           |
| **`ast_parser.py`**  | Parses raw markdown into SurfaceAST (structural tree, no semantics).                                                 |
| **`chunker.py`**     | Splits AST into contiguous regions for EvidenceUnit boundaries.                                                     |
| **`normalize.py`**   | Text/HTML normalization and helpers.                                                                                |
| **`gates_a.py`**     | Stage A gate checks (coverage, ordering, table parse, stability).                                                   |
| **`gates_b.py`**     | Stage B gate checks (orphan rate, bleed, table integrity, unit size).                                               |
| **`schemas.py`**     | Data contracts: `StageARecord`, `SurfaceAST`/`SurfaceASTNode`, `EvidenceUnit`, `PageFingerprint`, `GateDiagnostic`. |

Add new behavior in the stage that owns the contract; extend schemas only when the design doc is updated.

---

## 4. How to run

**From Python (recommended):**

```python
from pathlib import Path
from extraction.pipeline import run_a_only, run_a_b

# Stage A only (one page)
result_a = run_a_only(Path("path/to.pdf"), page_index=0, out_dir=Path("out/page0"))

# Stage A + Stage B
result = run_a_b(Path("path/to.pdf"), page_index=0, out_dir=Path("out/page0"))
# result["units"] = list of EvidenceUnit dicts; result["gates_passed"] = bool
```

**From the repo:**

- **Batch / stability runs:** `scripts/run_mark3_stability.py` (uses `run_a_b` over PDFs and pages, writes to `out/mark3_evaluation/` or similar).
- **Single-page debugging:** Call `run_a_only` or `run_a_b` from a small script or notebook.

**Outputs (under `out_dir`):**

- Stage A: `stageA.page.json`, `stageA.surface.md`, `stageA.surface.ast.json`, gate diagnostics.
- Stage B: EvidenceUnit list (and any Stage B artifacts); gate diagnostics.

---

## 5. Evaluation and regression

- **Brutal Pages** is the primary regression harness. Page sets and success criteria are defined in the design docs; evaluation reports live under `out/mark3_evaluation/` (or as configured in the stability script).
- **Metrics and gate intent** are now documented through the canonical `v1/` contract set, especially `Docs/Design/v1/stage_a_contract.md`, `Docs/Design/v1/stage_b_contract.md`, and `Docs/Design/v1/gates_stage_c_d.md`.
- `Docs/Design/archive/BRUTAL_PAGES_METRICS.md` remains useful historical context, but it is no longer the primary normative reference.

Any change to Stage A or B behavior should be checked against Brutal Pages and the metrics doc.

---

## 6. Archived Marker-era code (do not use for new work)

The previous pipeline (PDF → **Marker** → blocks → **chunks** → broadening → EvidenceChunks) is archived. It is **not** normative for Mark III.

- **Location:** `Archive/marker-era/extraction/` (and `broadening/`, `cds/`, `blind_eval/`, scripts there).
- **When to use:** Only for reproducing old results, comparing against Mark III, or mining logic that might be re-anchored to prose/AST.
- **How to run:** From repo root:  
  `PYTHONPATH=Archive/marker-era uv run python -m extraction.run <pdf_path> --output-dir <dir> --doc-id <id>`

Do **not** import Marker-era modules into this package. Do not add new features to the archived pipeline.

---

## 7. For the next developer or agent

- **Adding a gate:** Implement the check in `gates_a.py` or `gates_b.py`; update the relevant `Docs/Design/v1/` contract doc and `Docs/Design/v1/gates_stage_c_d.md` if the contract surface changes.
- **Changing Stage A output:** Update `schemas.py` and the Stage A contract doc; ensure `stage_a.py` and `gates_a.py` stay in sync.
- **Changing Stage B output:** Update `EvidenceUnit` in `schemas.py` and the Stage B contract; update `stage_b.py` and `gates_b.py`.
- **New extractor or OCR path:** Stage A is DeepSeek-centric by design. If you introduce another producer, it must emit the same Stage A surface (raw markdown → AST) and satisfy the same gates; add it behind the same `StageARecord` / SurfaceAST contract.
- **Tests:** Add unit tests for new gates or segmenter logic; keep integration tests aligned with the pipeline entry points (`run_a_only`, `run_a_b`).

When in doubt, resolve against the design docs and Brutal Pages metrics; do not assume behavior from the archived Marker-era code.
