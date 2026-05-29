# tinker

Exploratory work on intent-routed retrieval. Lives on branch
`tinker/intent-routed-retrieval` in the fork `PaperArmada/RulesIngestion`.
Designed to import from `retrieval_lab/` and `extraction/` but never modify
them. Outputs land under `out/tinker/` (gitignored).

See:
- [Docs/Design/VISION-Intent-Routed-Retrieval.md](../Docs/Design/VISION-Intent-Routed-Retrieval.md)
- [Docs/Design/MODELS-Intent-Routed-Retrieval.md](../Docs/Design/MODELS-Intent-Routed-Retrieval.md)
- The milestone plan at `/home/matt/.claude/plans/well-of-course-the-optimized-pumpkin.md`

## Setup

```bash
uv sync --extra tinker
```

Adds: `ollama`, `pymupdf4llm`, `numpy`, `rank-bm25`, `sentence-transformers`,
`scikit-learn`, `FlagEmbedding`.

Ollama models required:
```
ollama pull qwen3:4b           # classifier (fast path)
ollama pull qwen3:14b          # workhorse (intent, HyDE, synthesis, offline)
ollama pull qwen3-embedding    # dense retrieval embedder
```

## Corpus situation (SWCR)

Drakosfire's upstream benchmarks were anchored against the **Revised** edition
of Swords & Wizardry Complete (Mythmere Games, ~2018, paid PDF `$4.99` and
currently sold out).

We are working against the **2012 Complete edition** (freely redistributed
under the OGL via Iron Tavern). Source:

- URL: `http://irontavern.com/wp-content/uploads/2013/11/Swords-Wizardry-Complete-revised.pdf`
- SHA-256: `7fe633bdac5191b256e53eb0940fcea193f118cf103c018f6c4227da91dd2472`
- Local path (gitignored): `input_pdfs/swords_wizardry/SW_Complete_Revised.pdf`
- Pages: 144, PDF 1.6, embedded text (no OCR required)
- Metadata: created 2012-12-05 via Adobe InDesign CS6

**Consequence:** Drakosfire's existing gold `unit_id`s in
`evals/retrieval/SwordsandWizardry/*.json` will not align with our substrate.
We will generate fresh gold for the atomic-rules benchmark (universal questions
that apply to any OSR rulebook) as part of M5. We do not attempt to match the
historical hybrid baseline numbers in MRR — direct comparison is to our own
raw-dense run, not Drakosfire's archived metrics.

## Ingestion (no OCR)

The standard `scripts/run_mark3_full_pdf.py` runs DeepSeek-OCR-2 even for
PDFs with embedded text. For SWCR (text-extractable) we use a tinker-side
shim that pulls markdown via `pymupdf4llm` and passes it to Stage A via
`raw_markdown_override=...` + `skip_ocr=True`:

```bash
uv run python -m tinker.scripts.ingest_no_ocr \
    --pdf input_pdfs/swords_wizardry/SW_Complete_Revised.pdf \
    --out-dir out/swcr
```

About 1.8s per page on this machine. Full 144-page run completes in ~4 min.
Re-run with `--skip-existing` to resume after a crash.

## Substrate verification

```bash
uv run python -m tinker.scripts.check_substrate \
    --substrate-dir out/swcr \
    --document-id Swords_Wizardry
```

Prints unit count, unit_type distribution, structural_path depth histogram,
text length percentiles, and a sample. Fails (exit 1) if fewer than 200 units.

## Smoke test the LLM wrapper

```bash
uv run python -m tinker.llm
```

Hits the embedder, classifier (qwen3:4b), and hypothesizer (qwen3:14b)
end-to-end with trivial inputs and prints results.
