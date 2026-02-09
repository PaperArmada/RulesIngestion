# Manual review: match old gold chunks to Mark III EvidenceUnits

One-off workflow to map **archived (marker-era) gold chunks** to **new EvidenceUnit IDs** by running retrieval and manually matching retrieved text to old gold text.

## 1. Old gold (text + context)

**File:** `evals/retrieval/StarFinderPlayerCore/OLD_GOLD_REFERENCE.md`

- Source: `Archive/marker-era/blind_eval/gold_audit/gold_reference.json`
- For each of the 48 queries it lists:
  - **query_id**, question, expected answer summary, source page
  - For each **old gold item**: document_id, page (in chapter), block_path, and **target_text**
- Use the **target_text** to identify which retrieved chunk is the same content in the new extraction.

## 2. Retrieved chunks (Mark III)

**File:** `out/retrieval_lab/experiments/starfinder_baseline_<timestamp>/retrieved_chunks.json`

- One run: `starfinder_baseline_20260208_164348` (or the latest `starfinder_baseline_*` dir).
- Structure: by model (e.g. `all-mpnet-base-v2`), then a list of query reviews. Each has:
  - `query_id`, `question`, `expected_answer_summary`
  - `gold_unit_ids` (currently from page-anchored/semantic grounding; not the old gold)
  - `retrieved`: list of `{ rank, chunk_id, score, text }` — **top 20** retrieved EvidenceUnits per query.

## 3. Manual matching steps

1. Open **OLD_GOLD_REFERENCE.md** and **retrieved_chunks.json** (e.g. side by side or in two windows).
2. For each **query_id** in the reference:
   - Find the same `query_id` in `retrieved_chunks.json` → `all-mpnet-base-v2` → query list.
   - For each **old gold item** for that query, look at its **target_text**.
   - In that query’s `retrieved` list (up to 20 chunks), find the chunk whose **text** best matches that target (exact substring, or strong overlap; Mark III may add heading prefixes like `VENT GAS — BARATHU TRAVERSAL — …`).
   - Note the **chunk_id** (that is the EvidenceUnit `unit_id` in Mark III).
3. Build the new gold set per query: list of those **chunk_id**s as `gold_unit_ids`.
4. (Optional) Update the batch JSONs in `evals/retrieval/StarFinderPlayerCore/` by adding or replacing `gold_unit_ids` with the matched EvidenceUnit IDs so future retrieval lab runs use manually grounded gold (Baseline-A).

**See also:** `PER_QUERY_GOLD_DIFF.md` — per-query guidance on what to KEEP/ADD/REMOVE in gold sets and which queries need rubric nuance (e.g. refusal-acceptable, qualified answers).

## 4. Automated mapping (done)

Gold has been mapped to Mark III EvidenceUnit IDs and batch JSONs updated:

- **Script:** `scripts/map_starfinder_gold_to_mark3_units.py`
- **Audit:** `evals/retrieval/StarFinderPlayerCore/gold_unit_ids_audit.json` (query → gold_unit_ids, match_stats)
- **Result:** 90/109 gold items matched; 47/48 queries have at least one gold_unit_id. The 16 unmatched are mostly short headers or table cells that did not meet the text-similarity threshold.

To re-run the mapping (e.g. after substrate or gold_reference changes):

```bash
cd /path/to/RulesIngestion
uv run python scripts/map_starfinder_gold_to_mark3_units.py
```

## 5. Regenerating the old-gold reference

If you need to regenerate `OLD_GOLD_REFERENCE.md` from the archive:

```bash
cd /path/to/RulesIngestion
uv run python evals/retrieval/StarFinderPlayerCore/_oneoff_export_old_gold.py
```

## 6. Re-running retrieval only

Embeddings are already computed (`retrieval_lab_StarFinderPlayerCore_v2`). To re-run eval only:

```bash
cd /path/to/RulesIngestion
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/starfinder_baseline.yaml \
  --run-id retrieval_lab_StarFinderPlayerCore_v2
```

New output goes to `out/retrieval_lab/experiments/starfinder_dense_baseline_<new_timestamp>/`.
