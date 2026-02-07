> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Gold Chunk Evaluation and Retrieval-Reboot Plan

**Purpose:** (1) Evaluate current benchmark gold chunks for quality; (2) Store gold as **text + position** so we can re-find them after a graph/retrieval reboot.

**Status:** Plan. Implement export script and workflow, then human review.

---

## 1. Current State

- **Benchmark queries:** 6 batch files under `blind_eval/batches/` (batch_001 … batch_006_conceptual). Each query has:
  - `id`, `question`, `source_page`, `gold_chunk_ids[]`, `expected_answer_summary`, `notes`
- **Gold chunk IDs:** Point into `merged.enriched.json` (e.g. `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/9/Text/12`). After a **reboot**, chunk IDs may change or disappear; retrieval will be different.
- **Enriched chunk fields we care about:** `id`, `text`, `document_id`, `page` (often 0 in merged), `section_path`, `block_type`. The **chunk id path** (`/page/N/BlockType/M`) is the stable position within that document.

---

## 2. Goals

1. **Evaluate** – For each (query, gold_chunk_id), confirm the chunk is a **good** gold: i.e. it contains text that directly supports answering the question (or is necessary context). Flag or drop bad/irrelevant chunks.
2. **Capture for reboot** – For each accepted gold, store:
   - **Document position:** `document_id` + logical page/path (from chunk id, e.g. page 9, block Text/12) so we can locate the span in the source PDF or re-chunked output.
   - **Target text:** The substring (or full chunk text) that is most relevant to the query and answers it well. This allows:
     - Re-finding by **text search** or **similarity** in the new retrieval system.
     - Optional: re-anchoring by position if the new pipeline exposes document_id + page/block.

---

## 3. Workflow (Efficient)

### Phase A: Export gold audit (automated)

1. **Script:** `blind_eval/scripts/export_gold_audit.py` (or equivalent).
2. **Inputs:** All `blind_eval/batches/batch_*.json`; one enriched file (e.g. `merged.enriched.json`).
3. **Actions:**
   - Load all batches; collect every (query_id, question, expected_answer_summary, gold_chunk_id).
   - Resolve each `gold_chunk_id` in the enriched corpus → get `text`, `document_id`, `section_path`; parse chunk id for **page** and **block path** (`/page/N/BlockType/M`).
   - If a chunk id is **missing** from enriched, record that (gap) and still emit a row with empty text.
4. **Outputs:**
   - **`gold_audit.json`** – One array of “gold items”:
     - `query_id`, `question`, `expected_answer_summary`, `batch_id`, `source_page`
     - `chunk_id`, `document_id`, `page` (from id), `block_path`, `section_path`, `chunk_text`
     - `evaluation_status`: `"pending"` | `"keep"` | `"drop"` | `"trim"`
     - `target_text`: optional string (filled during review: the best substring for retrieval).
     - `reviewer_notes`: optional.
   - **`gold_audit_review.md`** (optional) – Human-friendly: one section per query, each gold chunk with question + expected answer + full chunk text, so reviewers can mark keep/drop/trim and paste target_text.

### Phase B: Human evaluation

1. **Review** each (query, chunk) in `gold_audit_review.md` or a spreadsheet/UI built from `gold_audit.json`.
2. **Criteria:**
   - **keep** – Chunk clearly supports the answer; use full chunk text as `target_text` (or a tight substring if chunk is long and only part answers).
   - **trim** – Chunk is relevant but only a portion is the “gold”; set `target_text` to that portion.
   - **drop** – Chunk is irrelevant, redundant, or wrong; will not appear in final gold reference.
3. **Update** `gold_audit.json` with `evaluation_status` and `target_text` (and optional `reviewer_notes`). Alternatively, keep review in a separate file and merge in a second script run.

### Phase C: Produce retrieval-reboot–safe gold reference

1. **Script:** Same or second script reads `gold_audit.json`, filters to `evaluation_status in ("keep", "trim")`, and emits the **gold reference**.
2. **Schema – `gold_reference.json` (or per-batch):**
   - **Retrieval-reboot–safe:** No dependency on current chunk IDs. Only:
     - `document_id` – source document (e.g. PDF range id).
     - `page` – logical page within that document (from chunk id).
     - `block_path` – e.g. `/page/9/Text/12` for precise location.
     - `target_text` – the text to match (full chunk or trimmed). New retrieval can find by text search/similarity or by re-mapping document_id + page if the new pipeline preserves that.
   - **Query side:** `query_id`, `question`, `expected_answer_summary`, `batch_id`, `source_page` (for audit), and list of **gold items** as above.
3. **Use after reboot:**
   - **By text:** Index or search over `target_text`; for each query, success = any retrieved chunk overlaps or matches the target text (or the document position if you re-expose it).
   - **By position:** If the new ingestion keeps `document_id` + page/block, you can check whether the chunk at that position is in the retrieved set.

---

## 4. Output Schemas (Summary)

### 4.1 Gold audit (export + review)

```json
{
  "metadata": { "enriched_path": "...", "batches": ["batch_001.json", ...], "exported_at": "ISO8601" },
  "gold_items": [
    {
      "query_id": "blind_001_01",
      "batch_id": "001",
      "question": "What abilities can cancel out Vent Gas when a Barathu uses it?",
      "expected_answer_summary": "Gust of Wind can blow away...",
      "source_page": 49,
      "chunk_id": "sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/9/Text/12",
      "document_id": "sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057",
      "page": 9,
      "block_path": "/page/9/Text/12",
      "section_path": [],
      "chunk_text": "Full text of the chunk...",
      "evaluation_status": "pending",
      "target_text": null,
      "reviewer_notes": null
    }
  ],
  "gaps": ["chunk_id not found in enriched", ...]
}
```

### 4.2 Gold reference (retrieval-reboot–safe)

```json
{
  "metadata": {
    "pdf_source": "PZO22003_PlayerCore.pdf",
    "created_at": "ISO8601"
  },
  "queries": [
    {
      "query_id": "blind_001_01",
      "batch_id": "001",
      "question": "What abilities can cancel out Vent Gas when a Barathu uses it?",
      "expected_answer_summary": "Gust of Wind can blow away...",
      "source_page": 49,
      "gold_items": [
        {
          "document_id": "sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057",
          "page": 9,
          "block_path": "/page/9/Text/12",
          "target_text": "The exact text that answers the query or the full chunk."
        }
      ]
    }
  ]
}
```

---

## 5. Implementation Checklist

- [x] **export_gold_audit.py** – `blind_eval/scripts/export_gold_audit.py`. Load batches + enriched; resolve chunk ids; output `gold_audit.json` (+ optional `gold_audit_review.md`).
- [x] **Parse chunk id** – Extract `document_id` and `page` / `block_path` from `chunk_id` (format: `{document_id}::/page/N/BlockType/M`).
- [x] **Handle missing chunks** – Log and list in `gaps`; still emit audit row with empty text and status `pending` (or `missing`).
- [ ] **Review workflow** – Edit `gold_audit.json` (or use `gold_audit_review.md` as guide) to set `evaluation_status` (keep/trim/drop) and `target_text` where needed.
- [x] **Build gold_reference from audit** – Run `uv run python blind_eval/scripts/export_gold_audit.py --build-reference --audit blind_eval/gold_audit/gold_audit.json`; outputs `gold_reference.json` with schema above.
- [x] **Docs** – See §6 below; `blind_eval/README.md` links to this plan.

---

## 6. Script Usage

**Export audit (run from RulesIngestion root):**

```bash
uv run python blind_eval/scripts/export_gold_audit.py
# Optional: human-friendly review file
uv run python blind_eval/scripts/export_gold_audit.py --review-md
```

Output: `blind_eval/gold_audit/gold_audit.json` and optionally `gold_audit_review.md`.

**After review** – Set `evaluation_status` and `target_text` in `gold_audit.json`, then:

```bash
uv run python blind_eval/scripts/export_gold_audit.py --build-reference --audit blind_eval/gold_audit/gold_audit.json
```

Output: `blind_eval/gold_audit/gold_reference.json` (retrieval-reboot–safe; only keep/trim items).

---

## 7. Efficiency Notes

- **Single pass:** One script can do: load enriched once, build id→chunk map; iterate all batches and all gold_chunk_ids; emit audit. No need for multiple tools.
- **Review in bulk:** Markdown or CSV with question + expected answer + chunk text lets reviewers go query-by-query and mark keep/drop/trim + paste target_text.
- **Reboot use:** New retrieval only needs `gold_reference.json`: for each query, success = any retrieved chunk matches (by text or by document_id + page if your new system preserves it).
