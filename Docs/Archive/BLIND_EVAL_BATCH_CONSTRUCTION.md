# Blind Eval: Batch Construction and Agent Workflow

**Purpose:** (1) Capture the pattern that works for building blind evaluation batches—including agent-as-evaluator using workflow tools to find gold chunks. (2) Preserve a repeatable methodology for constructing eval batches by humans or agents.

**Status:** Living document. Update when the workflow or batch format changes.

---

## 1. What Is Working

### 1.1 The Core Idea

Blind evaluation only stays blind if **gold chunk IDs are discovered from the corpus**, not chosen in advance. The same tools used to run the eval can be used to _build_ the eval: search the enriched chunks for terms that should appear in the answer, collect chunk IDs, and treat those as the gold set. No embedding, no prior knowledge of system behavior—just search and select.

### 1.2 Agent-as-Evaluator Pattern

An agent (or human) can construct batches by:

1. **Taking a query** (e.g. from a random page, or from a target reasoning mode).
2. **Using `find_chunks.py`** with one or more **search terms** derived from the question and expected answer.
3. **Combining results** from multiple searches into a single set of gold chunk IDs.
4. **Writing the batch entry**: `question`, `gold_chunk_ids`, `expected_answer_summary`, `notes`.

The agent does not guess chunk IDs. It uses the same deterministic search tool a human would use. The workflow is **traversal-like**: multiple hops (searches) from different entry points (terms), then union of results to form the candidate gold set. That keeps batch construction reproducible and uncheatable.

### 1.3 Why This Works

| Aspect                            | Benefit                                                                                                                                                      |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Single search tool**            | `find_chunks.py --search "term"` is the only way to find chunks by content; no hidden shortcuts.                                                             |
| **Multiple gold chunks**          | Queries can list several `gold_chunk_ids` for full context; eval passes if _any_ gold chunk is in the retrieval candidate set (or all, depending on metric). |
| **Term-driven discovery**         | Agent/human infers terms from the question (e.g. "Redirect Current", "console", "power") and runs separate searches, then merges.                            |
| **No embeddings in construction** | Gold set is defined by text match and human/agent judgment on which chunks are needed—not by similarity to the query.                                        |

### 1.4 Tools Involved

| Tool                    | Role in batch construction                                                                                                                               |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`generate_pages.py`** | Optional. Produces random page numbers; human opens PDF and writes a question per page.                                                                  |
| **`find_chunks.py`**    | Core. `--search "term"` returns chunks containing that term; output includes chunk IDs for copy-paste into batch JSON. Use `--limit` and `-v` as needed. |
| **`run_eval.py`**       | Not used for construction. Used later to run the batch and compute recall.                                                                               |

**Important:** `find_chunks.py` accepts **one** `--search` argument per run. To use multiple terms, run the script once per term and merge the chunk IDs (by hand or in the agent’s workflow).

---

## 2. Batch File Format

### 2.1 File Location and Naming

- **Path:** `RulesIngestion/blind_eval/batches/`
- **Naming:** `batch_001.json`, `batch_002_state.json`, etc. Use a suffix (e.g. `_state`) when a batch targets a specific reasoning mode.

### 2.2 Batch-Level Metadata

```json
{
  "metadata": {
    "batch_id": "001",
    "created_by": "human",
    "pdf_source": "PZO22003_PlayerCore.pdf",
    "creation_method": "random_page_selection",
    "created_at": "2026-01-27",
    "notes": "First blind eval batch - 10 random pages"
  },
  "queries": [ ... ]
}
```

For **reasoning-mode–specific batches**, add:

- **`reasoning_mode`** (string): e.g. `"state_and_condition_reasoning"`.
- **`graph_capabilities_tested`** (array of strings): e.g. `["state_node_lookup", "condition_modifier_links", ...]`.

### 2.3 Query Entry Schema

**Required for every query:**

| Field                         | Type             | Description                                                                             |
| ----------------------------- | ---------------- | --------------------------------------------------------------------------------------- |
| **`id`**                      | string           | Unique per query, e.g. `blind_001_01`, `batch_002_03`.                                  |
| **`source_page`**             | number           | PDF page number the question was derived from (for audit).                              |
| **`question`**                | string           | Natural-language question as a user would ask.                                          |
| **`gold_chunk_ids`**          | array of strings | Chunk IDs that together provide the answer. Order does not matter for recall.           |
| **`expected_answer_summary`** | string           | Short summary of the correct answer (for human review and future answer-quality evals). |
| **`notes`**                   | string           | Optional. e.g. "Tests: Vent Gas + wind spells"; "AMBIGUOUS: creature vs object".        |

**Optional (recommended for targeted batches):**

| Field                           | Type             | Description                                                   |
| ------------------------------- | ---------------- | ------------------------------------------------------------- |
| **`reasoning_modes`**           | array of strings | e.g. `["state_reasoning", "condition_modifiers"]`.            |
| **`graph_capabilities_tested`** | array of strings | e.g. `["state_node_lookup", "condition_to_modifiers_edges"]`. |

**Chunk ID format:** Same as in enriched JSON, e.g.  
`sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/9/Text/12`.  
Copy-paste from `find_chunks.py` output.

### 2.4 Example: Single Gold Chunk

```json
{
  "id": "blind_001_03",
  "source_page": 90,
  "question": "Can I use Redirect Current to power up a console?",
  "gold_chunk_ids": [
    "sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/16/Text/17",
    "sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/16/Text/20"
  ],
  "expected_answer_summary": "Redirect Current is triggered by taking electricity damage and redirects it. To power devices you'd need a different ability.",
  "notes": "Tests: Ability lookup + what Redirect Current actually does vs powering devices"
}
```

### 2.5 Example: Multiple Gold Chunks (Full Context)

```json
{
  "id": "blind_001_01",
  "source_page": 49,
  "question": "What abilities can cancel out Vent Gas when a Barathu uses it?",
  "gold_chunk_ids": [
    "sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/9/Text/12",
    "sf2e-playercore-PZO22001-Starfinder-Player-Core-330-363::/page/6/Text/2",
    "sf2e-playercore-PZO22001-Starfinder-Player-Core-294-329::/page/7/Text/7"
  ],
  "expected_answer_summary": "Gust of Wind can blow away the gas cloud. Dispel Magic could counter it if magical. Alternative senses can detect through concealment.",
  "notes": "Tests: Vent Gas definition + wind spells + dispel mechanics + sense abilities"
}
```

Multiple gold chunks are the norm when the answer spans definitions, exceptions, or related mechanics.

---

## 3. How to Construct Batches (Methodology)

### 3.1 Option A: Random-Page–Driven (Classic Blind)

1. **Generate pages:**  
   `uv run python blind_eval/generate_pages.py --count 10`  
   Optionally `--exclude 1,2,3,60,90` to skip front matter or already-used pages.

2. **For each page:**

   - Open the PDF, go to the page.
   - Write a natural question about that page’s content.
   - Identify 1–5 key terms (ability names, conditions, rule names) that must appear in the answer.

3. **Find gold chunks:**  
   For each term, run:  
   `uv run python blind_eval/find_chunks.py --search "Term" --enriched path/to/merged.enriched.json`  
   Use `--limit` and `-v` if needed. From the output, copy the chunk IDs that actually contain the answer content.

4. **Merge and trim:**  
   Combine IDs from all term searches. Remove duplicates and chunks that are only tangentially related. What remains is `gold_chunk_ids`.

5. **Fill the entry:**  
   Add `id`, `source_page`, `question`, `gold_chunk_ids`, `expected_answer_summary`, and `notes` to the batch JSON.

### 3.2 Option B: Grounding-Stressor (Parameterized from Generic Forms)

1. **Start from generic question forms** that stress scope, authority, conditions/triggers, definitions, procedure, or examples (e.g. “Does this rule apply only to the immediate action, or persist?”).
2. **Parameterize with concrete SF2e (or other ruleset) content**: pick a specific rule, ability, or term (e.g. flanking, Nanite Surge, Aid, reaction, dying recovery).
3. **For each concrete question:** derive search terms, run `find_chunks.py` per term, merge chunk IDs, set `gold_chunk_ids`, `expected_answer_summary`, and `notes`.
4. **Add metadata:** batch-level `reasoning_mode` (e.g. `grounding_stressors`) and `graph_capabilities_tested`; per-query `reasoning_modes` and `graph_capabilities_tested` where useful.
5. **Example batch:** `batch_003_grounding.json` — 14 questions across A (scope), B (authority), C (conditions/triggers), D (definitions), E (procedure), F (examples/silence).

### 3.3 Option C: Reasoning-Mode–Driven (Targeted Batch)

1. **Choose a capability** to stress (e.g. state/condition reasoning, temporal ordering, constraint/prevention).

2. **Design questions** that require that capability (e.g. “What penalties apply while blinded?”, “Does this trigger before the recovery check?”).

3. **For each question:**

   - Derive search terms (condition names, rule names, key phrases).
   - Run `find_chunks.py` once per term.
   - Collect chunk IDs that together give the full answer; set `gold_chunk_ids`.
   - Set `expected_answer_summary` and `notes`.
   - Optionally set `reasoning_modes` and `graph_capabilities_tested` per query and in batch metadata.

4. **Save as a dedicated batch** (e.g. `batch_002_state.json`) with batch-level `reasoning_mode` and `graph_capabilities_tested`.

### 3.4 Agent Workflow (Concise)

1. Receive query (and optionally source page or reasoning mode).
2. Infer 2–5 search terms from the question and expected answer.
3. For each term: run `find_chunks.py --search "term"` (and `--enriched` if needed); parse output for chunk IDs.
4. Union chunk IDs; drop irrelevant ones by text preview.
5. Write one query entry: `id`, `source_page`, `question`, `gold_chunk_ids`, `expected_answer_summary`, `notes`; add optional metadata if batch is targeted.
6. Append to the appropriate batch JSON.

No embedding calls, no access to retrieval internals—only the public search tool and the batch schema.

---

## 4. Finding Gold Chunks: Practical Notes

### 4.1 Page vs Text Search

- **`--page N`** restricts to chunks that have `page == N`. In some pipelines the `page` field is not populated; chunk location then appears only in the **chunk ID** (e.g. `::/page/9/Text/12`). Prefer **`--search "term"`** when in doubt.
- Use **`--search`** with the most specific terms first (e.g. feat name, condition name, spell name), then broaden if needed.

### 4.2 One Term Per Invocation

`find_chunks.py` takes a single `--search` value. To use multiple terms:

- Run the script once per term.
- Merge the printed chunk IDs (and optionally deduplicate) to form `gold_chunk_ids`.

### 4.3 Enriched File Path

Default enriched path is set inside `find_chunks.py` (and in `run_eval.py` / tests). If your run lives elsewhere, pass it explicitly:

`--enriched Rules/StarFinder2e/PlayerCore/outputs/runs/YYYY-MM-DD_HH-MM-SS/enriched/merged.enriched.json`

### 4.4 Copy-Paste from Output

The script prints a block of chunk IDs at the end, e.g.:

```
Chunk IDs (copy-paste for blind_eval JSON):
  "sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/9/Text/12",
  ...
```

Use those strings verbatim in `gold_chunk_ids` (including the `::/page/...` suffix).

---

## 5. Quality and Consistency

### 5.1 When to Add a Chunk to Gold Set

- Chunk text is needed to answer the question (definition, rule, exception, or example).
- Chunk is from the same ruleset/source as the query (e.g. Player Core).
- Prefer the minimal set that gives full context; avoid redundant or off-topic chunks.

### 5.2 Notes and Expected Summary

- **`notes`:** Use for construction/audit: e.g. “Tests: X + Y”, “EDGE CASE”, “AMBIGUOUS”, “HARD: cross-chapter”.
- **`expected_answer_summary`:** One or two sentences that a correct answer should align with. Keeps batch self-documenting and supports future answer-quality metrics.

### 5.3 Targeted Batches and Regression

For batches with `reasoning_modes` and `graph_capabilities_tested`:

- A change that improves overall recall but does **not** improve the intended capability may indicate a metric exploit or regression.
- Track recall per batch (and per capability) in addition to global recall.

---

## 6. Running the Eval After Construction

- **All batches:**  
  `uv run pytest tests/test_blind_eval.py -v`

- **Single batch:**  
  `uv run pytest tests/test_blind_eval.py -v -k "batch_001"`

- **Report:**  
  `uv run python blind_eval/run_eval.py --batch 001 --verbose`  
  (or `--all`)

Recall is computed per batch: for each query, at least one (or all, depending on metric) of `gold_chunk_ids` must appear in the retrieval candidate set.

---

## 7. Summary

| Goal                            | How                                                                                                                                                      |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Keep eval blind**             | Gold chunks come from corpus search (`find_chunks.py`), not from prior knowledge of system behavior.                                                     |
| **Support multi-chunk answers** | `gold_chunk_ids` is an array; build it by running multiple searches and merging.                                                                         |
| **Replicate construction**      | Use the same tools (generate_pages, find_chunks) and the same batch schema every time.                                                                   |
| **Agent-as-evaluator**          | Agent uses only `find_chunks.py` and the batch format; no embeddings or internal retrieval; workflow is traversal-like (multiple term hops, then union). |

This document captures what works today and how to build batches consistently; update it when the workflow or schema changes.
