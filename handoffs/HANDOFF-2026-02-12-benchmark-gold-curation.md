# Handoff: Benchmark Gold Curation (Manual Review Loop)

**Date:** 2026-02-12 (updated 2026-02-15)  
**Repo:** `RulesIngestion`  
**Intent for next agent:** (1) **S&W path-based curation** — Add or fix gold for S&W queries using the pattern in §8 so gold survives corpus/config changes. (2) **Manual review loop** — Sample queries, show gold by page, apply keep/expand/delete per user.

---

## 0) Start here (fresh agent)

- **S&W benchmark file:** `evals/retrieval/SwordsandWizardy/swords_wizardry_benchmark.json`
- **Curated queries (path-based gold_locations):** sw_q01, sw_q02a, sw_q02b, sw_q02c, sw_q04, sw_q05, sw_q06, sw_q07, sw_q08, sw_q09 (10 of 27). The rest are **legacy** (gold_unit_ids only; no gold_locations).
- **Pattern to add or fix gold:** §8 — use **path-based gold_locations** (page + structural_path) with placeholder keys; resolution runs at experiment time and persists resolved IDs back to the file.
- **How to discover structural_path for a page:** Same pipeline as experiment: `load_evidence_units` → `fold_under_threshold_into_adjacent(min_chars)` → `merge_units_by_heading(max_chars)`. List chunks on the target page(s); use their `structural_path` exactly (e.g. `["CHAPTER 5: PLAYING THE GAME"]`). Config: `retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml` (min_chars=100, merge_max_chars=2000).
- **Run baseline after edits:** `uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml` (resolves gold and overwrites benchmark with resolved IDs).
- **Legacy queries (sw_q03, sw_q10–sw_q25):** Have only `gold_unit_ids`; no `gold_locations`. To make them robust, add path-based gold_locations using §8.

---

## 1) Goal

The user will:

1. Work through benchmark questions and check each **gold chunk** against the **source book (PDF)**.
2. For each query/gold set: decide whether to **keep**, **expand** (add more unit IDs as gold), or **delete** (remove one or more gold unit IDs).
3. Receive from the agent: **randomly sampled queries**, with each gold chunk labeled by **page number** so they can open the book to that page and verify.

The agent must:

- Sample queries at random from the chosen corpus.
- For each sampled query, list every **gold_unit_id** (and optional **required_gold** / **supporting_gold** if present).
- For each gold unit ID, **resolve to the EvidenceUnit** in the substrate and report:
  - **Page number** (1-based for human reference: *"Page 17"* = substrate page index 16).
  - Optional: short **text snippet** (e.g. first 120 chars) so the user can confirm it’s the right chunk without opening the file first.
- After the user responds with keep/expand/delete per query (and any new unit IDs for expand), the agent should apply edits to the benchmark JSON (or produce a patch/nomination file) as specified in §5.

---

## 2) Relevant Code Paths and Data Locations

### 2.1 Loading queries (gold list per query)

- **Entry:** [retrieval_lab/gold_grounding.py](retrieval_lab/gold_grounding.py) — `flatten_query_batches(batch_paths: List[str])`.
- **Behavior:** Reads one or more JSON batch paths; returns a flat list of query dicts. Each query has at least: `id`, `question`, `expected_answer_summary` (or `answer`), `gold_unit_ids`, optionally `source_page`, `required_gold`, `supporting_gold`, `mode`.
- **Batch formats supported:**
  - Root key `"batches"`: list of `{ "batch_id", "suite", "queries": [ ... ] }`.
  - Root key `"queries"`: list of query objects (e.g. Starfinder batch files, S&W benchmark).
  - Root is an array of query objects (e.g. S&W `swords_wizardry_benchmark.json`).

### 2.2 Loading the corpus (unit_id → page and text)

- **Entry:** [retrieval_lab/substrate_loader.py](retrieval_lab/substrate_loader.py) — `load_evidence_units(phb_dir, document_id)` (no min_chars; fold/merge applied separately per config).
- **Returns:** List of dicts: `id`, `text`, `page`, `structural_path`, `unit_type`, `document_id`.
- **Page semantics:** `page` is the **0-based** page index derived from the directory name (e.g. `DnD_PHB_5.5_p16` → `page = 16`). For **user-facing output** use **1-based** "Page N" = `page + 1` when `page >= 0`, else "unknown page".

### 2.3 Corpus ↔ benchmark mapping (which substrate for which queries)

| Corpus | Document ID | Substrate path (repo root) | Query batch path(s) |
|--------|-------------|----------------------------|----------------------|
| **PHB (D&D 5e)** | `DnD_PHB_5.5` | `out/DnD_PHB_5.5` | `evals/retrieval/PHB5e/dnd_5_e_equivalent_rag_eval_queries.json` |
| **Starfinder** | `StarFinderPlayerCore` | `out/StarFinderPlayerCore` | `evals/retrieval/StarFinderPlayerCore/batch_001.json` … `batch_006_conceptual.json` |
| **S&W** | `Swords&Wizardry` | `out/Swords&Wizardry` | `evals/retrieval/SwordsandWizardy/swords_wizardry_benchmark.json` |

- Configs that define these: [retrieval_lab/experiments/hybrid/phb_hybrid.yaml](retrieval_lab/experiments/hybrid/phb_hybrid.yaml), [starfinder_hybrid.yaml](retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml), [swords_wizardry_hybrid.yaml](retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml).

### 2.4 Applying user edits (nomination pattern)

- **S&W:** [scripts/apply_nominated_gold_sw.py](scripts/apply_nominated_gold_sw.py) reads `evals/retrieval/SwordsandWizardy/nominated_gold_per_query.json` and writes `gold_unit_ids` into `evals/retrieval/SwordsandWizardy/swords_wizardry_benchmark.json`. Use the same JSON shape for nominations: `{ "queries": [ { "query_id": "<id>", "gold_unit_ids": [ ... ] } ] }`.
- **PHB / Starfinder:** There is no apply script yet. Edits are direct to the benchmark JSON:
  - PHB: single file `evals/retrieval/PHB5e/dnd_5_e_equivalent_rag_eval_queries.json` — structure is `{ "batches": [ { "queries": [ ... ] } ] }`. Find query by `id` in the right batch and set `gold_unit_ids` (and optionally `required_gold` / `supporting_gold`).
  - Starfinder: one file per batch under `evals/retrieval/StarFinderPlayerCore/`; each has `"queries": [ ... ]`. Find query by `id` and set `gold_unit_ids`.

---

## 3) Instructions for the Next Agent

### 3.1 First response: random sample and page resolution

1. **Ask the user** (or use defaults):
   - **Corpus:** one of `PHB` | `Starfinder` | `S&W`.
   - **Sample size:** e.g. 5 or 10 queries per round.
2. **Load queries** for that corpus using `flatten_query_batches` with the paths from the table in §2.3. Filter to queries that have at least one gold unit ID (or explicitly include queries with empty gold for “expand” workflow).
3. **Randomly sample** the chosen number of queries (e.g. `random.sample(queries, min(n, len(queries)))`). Use a fixed seed if the user wants reproducibility (e.g. `random.seed(42)`).
4. **Load the substrate** for that corpus: `load_evidence_units(substrate_path, document_id)` with no `min_chars` so every unit is present. Build `unit_id_to_unit: Dict[str, Dict]` keyed by `id`.
5. **For each sampled query**, output a clear section:
   - **Query id:** `<id>`
   - **Question:** `<question>`
   - **Expected answer summary:** `<expected_answer_summary>` (or `answer` if present)
   - **Source page (query-level):** if `source_page` is set, report it (1-based for display).
   - **Gold chunks:**
     - For each `gold_unit_id` in `gold_unit_ids` (and, if present, list which are in `required_gold` vs `supporting_gold`):
       - **Unit ID:** `<id>`
       - **Page:** "Page N" (1-based) or "unknown page" if not found / page &lt; 0.
       - **Snippet:** first ~120 characters of `unit["text"]` (or "(unit not in corpus)" if missing).

Present the list in a consistent, copy-paste-friendly form so the user can reference the PDF by page and then reply with decisions.

**Optional: run the curation sampler script** (from repo root):

```bash
uv run python scripts/sample_gold_for_curation.py --corpus phb --sample 5
uv run python scripts/sample_gold_for_curation.py --corpus starfinder --sample 10 --seed 42
uv run python scripts/sample_gold_for_curation.py --corpus sw --sample 5
```

This prints the same structure: query id, question, expected answer, then each gold chunk with 1-based page and snippet. The user can paste the output into the chat and then reply with keep/expand/delete.

If many gold chunks show "(unit not in corpus)", the substrate may have changed (e.g. re-extraction or min_chars filter); consider re-running gold grounding or deleting those IDs.

### 3.2 Second response: interpret user decisions and apply

After the user replies with keep/expand/delete per query (and any new unit IDs for expand):

1. **Keep:** no change to gold for that query.
2. **Expand:** add the user-provided unit IDs to `gold_unit_ids` (and optionally to `required_gold` or `supporting_gold` if the user specifies). Ensure each new ID exists in the substrate; if not, report which IDs were missing.
3. **Delete:** remove the user-specified unit IDs from `gold_unit_ids` (and from `required_gold` / `supporting_gold` if present).

Then:

- **S&W:** Update `evals/retrieval/SwordsandWizardy/nominated_gold_per_query.json` (or the benchmark directly if that’s the chosen workflow) and run `uv run python scripts/apply_nominated_gold_sw.py` if using the nomination file.
- **PHB / Starfinder:** Edit the corresponding benchmark JSON file(s) in place: update the `gold_unit_ids` (and optional fields) for each modified query.

Confirm what was changed (query id, before/after gold list) and remind the user to re-run the baseline if they want updated metrics.

---

## 4) Page Number Convention (Critical)

- **In code / substrate:** `unit["page"]` is **0-based** (e.g. first page = 0).
- **In output to the user:** Always report **"Page N"** with **1-based** N: `display_page = (unit["page"] + 1) if isinstance(unit.get("page"), int) and unit["page"] >= 0 else "unknown"`.
- So when the user opens the PDF to "Page 17", they are looking at the same content as the chunk with `page == 16` in the substrate.

---

## 5) File Paths Summary (from repo root)

- **PHB queries:** `evals/retrieval/PHB5e/dnd_5_e_equivalent_rag_eval_queries.json`
- **Starfinder queries:** `evals/retrieval/StarFinderPlayerCore/batch_001.json` … `batch_006_conceptual.json`
- **S&W benchmark:** `evals/retrieval/SwordsandWizardy/swords_wizardry_benchmark.json`
- **S&W nomination (optional):** `evals/retrieval/SwordsandWizardy/nominated_gold_per_query.json`
- **Substrates:** `out/DnD_PHB_5.5`, `out/StarFinderPlayerCore`, `out/Swords&Wizardry` (EvidenceUnits live under `.../..._pN/stageB.evidence_units.json`).

---

## 6) Suggested User Reply Format

To keep parsing simple, the user can reply in free form; the agent should accept e.g.:

- *"Query dnd5e_blind_001_02: keep."*
- *"Query sw_q01: expand — add unit IDs abc123, def456."*
- *"Query blind_001_03: delete unit 26ec4889... and f0b6cee2...; keep the rest."*

The agent should normalize to: per-query action (keep | expand | delete) and, for expand, the list of new unit IDs; for delete, the list of unit IDs to remove.

---

## 8) S&W path-based curation pattern (canonical)

Use this pattern whenever you **add** or **replace** gold for a Swords & Wizardry query. It keeps benchmarks valid across substrate/merge/min_chars changes.

### 8.1 Why path-based

- `gold_unit_ids` are **derived** from the corpus pipeline (fold + merge). Changing min_chars or merge logic changes chunk IDs; hardcoded IDs become invalid.
- **gold_locations** keyed by (page, structural_path) are **stable**. At run time, `resolve_gold_locations_to_current_corpus` in `retrieval_lab/gold_grounding.py` matches (page, structural_path) to the current merged corpus and fills in real chunk IDs. Optionally, the run **persists** those resolved IDs back to the benchmark file so the file stays up to date.

### 8.2 Schema per query (curated shape)

- **gold_unit_ids:** Either **placeholder keys** (e.g. `sw_q01_p39`, `sw_q04_p19`) or, after a run, **resolved chunk IDs**. Placeholder keys must match keys in `gold_locations`.
- **gold_locations:** Map from each key (placeholder or id) to `{ "page": <int>, "structural_path": [ "Heading Name" ] }`. Page is **0-based** in JSON (same as substrate). `structural_path` is the exact list from a merged chunk on that page (e.g. `["CHAPTER 5: PLAYING THE GAME"]`).
- **required_gold** / **supporting_gold:** List of the same keys as in gold_locations. Required = must-have for the answer; supporting = context.
- **required_gold_rationale:** Optional map from key to short reason (for audit).
- **source_page:** Comma-separated **1-based** page list for display (e.g. `"8, 28, 39, 64"`).
- **answer:** Expert Referee–style; detailed, S&W-only; cite slots/rounds/caveats where relevant.
- **expected_answer_summary:** One-line summary for embedding/display.
- **_gold_note:** Optional (e.g. "Good candidate for HYDE vocabulary").

### 8.3 Steps to add or fix gold for one query

1. **Identify target pages** (from PDF or user: "Page 8, 28, 39, 64 are good gold").
2. **Discover structural_path for those pages:** Run the same pipeline as the experiment:
   - Config: `retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml` (min_chars=100, merge_max_chunks=2000).
   - Load: `load_evidence_units(substrate_path, document_id)` → `fold_under_threshold_into_adjacent(raw, 100)` → `merge_units_by_heading(folded, max_chars=2000)`.
   - For each page P, list chunks with `page == P` and their `structural_path` (use exact string list, e.g. `["REMEMBER"]`).
3. **Choose placeholder keys** (e.g. `sw_q01_p8_ch1`, `sw_q01_p39`) and build:
   - `gold_locations`: each key → `{ "page": <0-based>, "structural_path": [...] }`.
   - `gold_unit_ids`: list of those keys.
   - `required_gold` / `supporting_gold`: subset of those keys.
   - `required_gold_rationale` if desired.
4. **Set source_page** (1-based, comma-separated), **answer**, **expected_answer_summary**.
5. **Run the experiment** so resolution runs and (if persist is enabled) the benchmark file is updated with resolved chunk IDs. After that, the same file will show real IDs in `gold_unit_ids` and `gold_locations`; optional `_required_gold` / `_supporting_gold` may still show placeholder keys for reference.

### 8.4 Resolution and persist (code)

- **Resolve:** `retrieval_lab/gold_grounding.py` — `resolve_gold_locations_to_current_corpus(queries, folded_corpus, merged_corpus)`. Matching uses `_path_key(unit) == (page, " > ".join(structural_path))`.
- **Persist:** `run_experiment.py` calls `persist_resolved_gold_to_batch_files` after resolution when `queries_with_gold_locations > 0`, writing resolved gold back to the batch JSON.
- **Design:** `Docs/Design/gold_resolution_design.md` (Option A: resolve at run time; persist is optional).

### 8.5 Example (sw_q01)

- Question: "If the rules don't cover something in Swords & Wizardry, are we supposed to find the closest matching rule, or just let the referee make a call?"
- Gold pages: 8, 28, 39, 64. Placeholder keys: `sw_q01_p8_ch1`, `sw_q01_p8_alt`, `sw_q01_p28`, `sw_q01_p39`, `sw_q01_p64`.
- gold_locations: `sw_q01_p39` → `{ "page": 39, "structural_path": ["REMEMBER"] }`, `sw_q01_p64` → `{ "page": 64, "structural_path": ["CHAPTER 7: RUNNING THE GAME"] }`, etc. (page 8 has two headings: CHAPTER 1: GETTING STARTED, About the Alternate Rules.)
- required_gold: `["sw_q01_p39", "sw_q01_p64"]`; supporting_gold: the rest.
- After a run, the file contains resolved chunk IDs in `gold_unit_ids` and `gold_locations` (with `source_unit_ids` where applicable).

---

## 9) Success Criteria for the Agent

- Random sample of queries is produced with **every gold chunk labeled by 1-based page** and an optional snippet.
- User can open the source PDF to the given page and verify the chunk.
- After user decisions, the agent applies only the requested keep/expand/delete and reports what changed.
- Benchmark JSON (or S&W nomination file) is written correctly so that a subsequent run of the retrieval lab uses the updated gold sets.
