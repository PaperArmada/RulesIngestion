# Handoff: Rules Ingestion → RulesLawyer RAG Eval
**Date:** 2026-01-22  
**Type:** Feature / Evaluation  
**Last Updated:** 2026-01-26 00:30  

---

## 🚨 CURRENT STATE

### What's Working ✅
- Marker → enrichment → graph → coalesced chunks run end-to-end.
- LLM config generation + reuse works; config snapshots written to disk.
- LLM paragraph enrichment works (`--llm-pre-enrich`) and writes annotations.
- LLM review pass works (`--llm-review`) with progress logging.
- Outputs now include:
  - `*.enriched.json` (original enriched chunks)
  - `*.coalesced.json` (review-friendly chunks)
  - `*.llm_paragraphs.json` (paragraph annotations)
  - `*.llm_review.json` (review annotations)

### What's NOT Working ❌
- **RAG evaluation harness** not built yet (queries + embeddings comparison).
- **RulesLawyer integration** needs tuning to use enriched + coalesced chunks.
- **Table/layout debate** unresolved (how much to invest vs benefits).

### Decisions/Notes
- LLM model in use: `gpt-5-chat-latest`.
- Enrichment flags:
  - `--llm-pre-enrich` uses config `nondeterministic_flags`
  - `--llm-review` runs on coalesced chunks
  - `--llm-review-limit` caps review calls
- LLM review runtime observed: ~2.48s/call (119 calls, 295.38s).

---

## Quick Pickup

### Commands
```bash
cd /media/drakosfire/Projects/DungeonOverMind/RulesIngestion

# Full PDF run + auto-config + LLM enrich + review (limit for speed)
uv run python rules_ingestion_pipeline.py "Rules/StarFinder2e/PlayerCore/source/PZO22001 Starfinder Player Core 001-013.pdf" \
  --output-dir "Rules/StarFinder2e/PlayerCore/outputs" \
  --auto-config \
  --ruleset-id "sf2e-playercore" \
  --llm-model "gpt-5-chat-latest" \
  --llm-pre-enrich \
  --llm-review \
  --llm-review-limit 10
```

### Key Files
```
RulesIngestion/rules_ingestion_pipeline.py
  - Auto-config + LLM enrich/review + coalesced output

RulesIngestion/llm_enrichment.py
  - Paragraph targets + review pass prompts

RulesIngestion/llm_config_generator.py
  - LLM-backed ruleset config generation

RulesIngestion/ingestion_service.py
  - Async /ingest API with ThreadPoolExecutor(max_workers=10)

RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/enriched/
  - `.enriched.json`, `.coalesced.json`, `.llm_paragraphs.json`, `.llm_review.json`

DungeonMindServer/ruleslawyer/ruleslawyer_helper.py
  - Uses Responses API model constant OPENAI_RESPONSE_MODEL

Docs/architecture/RulesLawyer_Architecture.md
  - Blueprint for RAG evaluation tool integration
```

---

## Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Marker extraction + enrichment + graph |
| Phase 2 | ✅ Complete | Coalesced chunks + LLM enrich/review outputs |
| Phase 3 | 🔄 In Progress | RAG evaluation harness planning |
| Phase 4 | ⬜ Not Started | RulesLawyer integration + embedding evaluation |

---

## Files Modified This Session

### Created
- `RulesIngestion/llm_config_generator.py` - LLM config generator
- `RulesIngestion/llm_enrichment.py` - LLM paragraph + review annotation
- `RulesIngestion/tests/test_llm_enrichment.py` - LLM enrichment tests

### Modified
- `RulesIngestion/enrichment.py` - Coalescing helper for larger chunks
- `RulesIngestion/rules_ingestion_pipeline.py` - Auto-config + LLM enrich/review + coalesced output
- `RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/` - New outputs from runs

---

## Next Steps (Focused)

1. **Build RAG evaluation harness (RulesLawyer-aligned)**
   - Use `Docs/architecture/RulesLawyer_Architecture.md` as blueprint.
   - Generate evaluation queries alongside pipeline outputs (target chunk IDs).
   - Add simple evaluation runner: embed → retrieve → measure hit@k / MRR.
   - Iterate embedding models and record speed + accuracy.

2. **RulesLawyer tweaks**
   - Decide which source: `.coalesced.json` or `.enriched.json`.
   - Add a minimal evaluation-only retriever path (no SSE needed).

3. **Table/Layout debate**
   - Assess whether table extraction adds RAG value for rules vs cost/complexity.

---

## Context
- LLM is used for config generation + optional enrichment/review passes.
- Coalesced chunks are review-friendly and likely better for RAG.
- Next focus: evaluation tooling for embeddings + retrieval quality.

---

## Embedding Model Recommendations (Jan 2026)

GTE Multilingual Base (Alibaba) - Top choice for this scenario. It offers an outstanding balance of accuracy, long input support (8192 tokens), efficiency (300M params), and fully open licensing. GTE will handle English rulebooks very well, capturing domain-specific terms (it was trained on diverse text) and even outputting token-level signals for structured data. Its deterministic and fast, fitting well into an extensible pipeline. Since multilingual support isnt a strict need, youre essentially using its English prowess, which is state-of-the-art or close to it. Importantly, you wont have to worry about license or deployment issues - Apache 2.0 gives you freedom to integrate it commercially. GTEs design explicitly targets RAG use-cases and long documents, which aligns perfectly with rulebook ingestion and QA. Overall, GTE checks every box: high semantic fidelity, table-friendly hybrid features, CPU-friendly, and permissive.

EmbeddingGemma-300M (Google) - Close second. Gemma is extremely high-performing and likewise very efficient. If not for the slightly restrictive license click-through, it would be an easy #1 alongside GTE. In practice, if your organization is comfortable with Googles terms, Gemma will serve you exceptionally well. It excels in semantic search and even general classification tasks out-of-the-box. Its 2048-token limit is smaller than GTEs, but still sufficient for most rulebook sections (and you can always chunk if needed). Gemmas strength is that its tuned to be state-of-the-art for its size - youre getting almost Qwen-level performance at half the size. Its been validated on many benchmarks (MTEB English and multilingual) and found to be at the top. It doesnt explicitly handle tables beyond treating them as text, but if you format inputs clearly, Gemma will embed them meaningfully. Also, Gemmas small size and on-device optimization mean you can embed content on commodity hardware quickly. If you choose Gemma, just ensure the licensing is cleared with your legal team (its expected to be fine, but its not as clean as Apache). Many developers are adopting Gemma for mobile and PC apps - a testament to its practical usability.

BGE-M3 (BAAI) - Highly recommended especially if hybrid search or long-document handling is a priority. BGEs 8192-token context and multi-vector + sparse capabilities make it ideal for rulebooks with lots of factual data (like tables). You can rely on its dense embeddings for semantic similarity, and optionally leverage its token-weight output to implement deterministic filters or boosts for certain keywords (in a very extensible way - you can tweak your retrieval pipeline without changing models). BGEs performance is top-tier; it may be a hair behind Gemma/GTE in pure semantic similarity for English, but not by much (and it actually outperforms many models in multi-lingual and long-doc scenarios). The model is MIT licensed, so no worries there. The main cost is the ~0.5B size - slightly slower than 300M models, but still feasible on CPU, especially if quantized. If your use-case might benefit from combining semantic search with classic keyword search (which often improves reliability in QA systems), BGE is a fantastic one-stop solution because it was literally built for that hybrid approach. It also aligns with the World Engine concept of projections - e.g., you could use BGE to generate both a semantic projection (dense vector) and a lexically grounded projection (sparse vector) of the rules, enabling different reasoning or audit views without changing the underlying data.

Nomic Embed Text V2 - Another strong candidate, particularly if you want cutting-edge research features and are okay with 512-token chunks. Nomics model is open, very high quality, and innovative (being the first MoE embedding model). It performs extremely well on retrieval (especially multilingual) and should do fine on RPG text. Its efficient like a 300M model at runtime. The downsides are manageable: you have to consistently use the prefix format (which you can build into your pipeline deterministically), and you have to chunk text beyond 512 tokens (which youd need to plan for with overlap or careful splitting). If your rulebook content naturally breaks into paragraphs or if you dont mind smaller chunks, this is less of an issue. Nomic v2 also gives you flexibility to reduce vector dimensions easily. Given Nomic (the company) specializes in embedding analysis tools, using their model might integrate nicely if you plan to visualize or map the embeddings (e.g., using Atlas to create a semantic map of your rulebook). The open Apache license is a plus. We rank it slightly below GTE/Gemma/BGE mainly because of the 512-token limit - otherwise, its on par with them in many respects. If future versions extend the context or if your documents are mostly short paragraphs, Nomic v2 could be nearly equal to the top picks.

Qwen3-Embedding-0.6B - We recommend Qwen if maximum quality is the top priority and you can accommodate its heavier footprint. Qwens advantages are its unmatched multilingual and reasoning capabilities, and the 32k context. It will handle any size chunk you throw at it and still generate a meaningful embedding. For very complex queries or if you anticipate needing embeddings that capture subtle logical relations (e.g., "if X then Y" kind of rule logic), Qwen might encode that nuance slightly better due to its LLM origins. It also has an ecosystem of rerankers (0.6B, 4B, 8B models) - while those are too large for CPU, it indicates Qwens embeddings were designed to work with downstream re-ranking for even higher precision. Even without rerankers, Qwens standalone performance is stellar. The only reason its not our top pick is the efficiency aspect: its ~2x slower and memory-hungry than a 300M model. If your use-case is an internal tool that can take a bit more time to index or if you have a powerful machine, Qwen is absolutely a valid choice. Its license is Apache 2.0, so no restrictions. Many in the community were excited about Qwen3-0.6B because it brought very high accuracy in an open model. There were some reports early on that it was slower than expected on CPU until quantized, but those can be addressed. So consider Qwen if you value the 32k context (maybe you want to embed entire chapters or multi-section context for RAG) or if you trust Alibabas model quality to be superior (their MTEB English score for Qwen-0.6B isnt explicitly stated, but likely in the 61-62 range vs Gemma ~58-59 on MTEB English v2 judging by Qwens multilingual being 61.8 and Gemmas claim). Its a minor boost for a doubling of size.

all-mpnet-base-v2 - We generally do not recommend MPNet-base for this specific use, given the availability of far stronger models. Its only advantages are speed and the fact its a proven stable model. If you had a scenario where you needed to embed content on a very low-power device or in huge volume very fast and you couldnt quantize larger models, MPNet could be a fallback. But for ingesting a handful of rulebooks and performing queries, the newer models superior semantic understanding of complex RPG text is well worth the slight extra cost in runtime. MPNet might miss finer distinctions (e.g., it might not clearly separate the concept of "cover" in combat vs "cover" as in book cover, whereas larger models would from context, or it might not link an abbreviation to its full term as robustly). Given the rulebooks may have intricate terminology, a stronger model will reduce incorrect matches. Thus, MPNet would only be a choice if system resources are extremely constrained or as a baseline to compare against.

Jina Embeddings V4 - We do not recommend Jina-v4 for your scenario due to its non-commercial license and enormous resource requirements. While its an impressive model (multimodal embeddings could be useful if you wanted to incorporate images/maps from the rulebooks), it simply doesnt align with "CPU inference" and "permissive licensing." Its better suited for specialized cases with GPU inference and where mixing image/text retrieval is needed. If in the future a smaller distilled version or a commercial license becomes available, one might revisit it, but currently its not a fit.

To conclude, EmbeddingGemma and GTE emerge as the top picks for a balanced solution - they are purpose-built for exactly this kind of task. They give you near state-of-the-art semantic search power with minimal infrastructure burden, and they integrate cleanly into a deterministic pipeline. BGE-M3 is a strong contender if you value its hybrid retrieval strengths and dont mind the larger model size. Nomic Embed v2 is excellent if you handle the 512-token limitation, offering innovative tech with full openness. And Qwen-0.6B, while heavier, provides maximum performance and might be worth it if you need that extra edge and context window. All of these recommended models support pure text (and structured text) ingestion in a stable, extensible way, which aligns with the World Engine principles of determinism and extensibility. Each can be the "embedding backbone" of your semantic index for RPG rulebooks, enabling powerful search, question-answering, and analytical reasoning on your content.

---

## References
- `RulesIngestion/Handoffs/HANDOFF-Pipeline-Enrichment-Evaluation.md`
- `RulesIngestion/Docs/ingestion_polishing_guidebook.md`

---

## Research: Best Practices for Post-Processing OCR (TTRPG Rulebooks)

### Post-Processing Strategies
- **Schema-first structuring:** Define strict schemas for spells/items/monsters and validate OCR/LLM output against them.
- **Rule-based parsing:** Use headings/bold labels/DOM layout to map fields where layout is consistent.
- **LLM-assisted structuring:** Constrain JSON via schema/Pydantic; retry until valid; treat LLM as a structuring layer on top of OCR, not a replacement.
- **Domain term integration:** Cross-reference known terms (conditions, damage types, items) to correct OCR drift (e.g., “Pierciug” → “Piercing”).

### Layout Fixes & Paragraph Reconstruction
- **Reading order:** Use layout geometry (pdfplumber/PyMuPDF/layoutparser/Docling) for column order and sidebars.
- **Line joining:** Merge lines when punctuation is missing and next line begins lowercase.
- **Hyphenation repair:** Remove line-break hyphens to reconstruct words (e.g., “incr-” + “eases” → “increases”).
- **Hybrid approach:** OCR + heuristic post-correction yields the best text flow.

### Semantic Segmentation & Labeling
- **Heuristic labels:** Use italics, bold, font size, and layout cues to tag flavor vs rules.
- **Structured patterns:** Detect stat blocks via regex/sequence patterns (e.g., Armor Class, HP).
- **LLM/ML tagging:** Classify blocks as lore/rules/table/example; validate for consistency.
- **Context propagation:** Chapter-level cues can label subsections (lore chapter → lore default).

### Table Extraction & Normalization
- **Table detection:** Use Camelot/PDFMiner/table-transformer/layoutparser to detect cells/grids.
- **Multi-line cells:** Group rows by a stable column (quantity/index) to merge wrapped lines.
- **Header continuation:** Merge multi-page tables by repeated headers; strip footers/headers.
- **Normalization:** Align column counts and standardize labels/units.

### Typography & Styling Cues
- **Preserve styles:** Keep bold/italic/size metadata from OCR/PDF output.
- **Interpretation:** Bold → labels/field names; italics → special terms or flavor; all-caps → headings.
- **Semantic tagging:** Prefer semantic tags in JSON over literal styling where possible.

### Cross-References & Entity Linking
- **Page/chapter refs:** Convert “see page X” to structured links if page index exists.
- **Entity links:** Match extracted entities in text; restrict by capitalization/format to avoid false positives.
- **Integrity checks:** Flag broken references or missing targets.

### QA & Validation
- **Schema validation:** JSON Schema/Pydantic checks for required fields and type correctness.
- **Cross-field validation:** Range/format checks (spell level 0–9, durations, dice notation).
- **Structural alignment:** Compare to TOC/bookmarks; verify expected headings exist.
- **Automated flags:** Treat validation failures as pipeline errors for review/retry.

### OCR Error Detection & Correction
- **Common OCR errors:** 1/l, 0/O, rn/m, misread “d6” or numeric values.
- **Spellcheck + custom lexicon:** Use TTRPG vocabulary to reduce false positives.
- **Contextual fixes:** Levenshtein or constrained LLM correction for near-miss words.
- **Numeric checks:** Validate dice patterns and numeric fields (e.g., “1O0” → “100”).
- **Multi-engine cross-check:** Compare outputs from different OCR engines on low-confidence text.

### Visual QA & Human-in-the-Loop
- **Side-by-side viewer:** Show original PDF next to extracted text; highlight low-confidence zones.
- **Overlay QA:** Render OCR text boxes on page image to spot omissions/misorder.
- **Sampling:** Review dense tables and layout-heavy pages first; sample per chapter.
- **Human corrections:** Feed fixes back via overrides to prevent regression on reruns.

### Metrics & Success Criteria
- **CER/WER:** Quantify OCR accuracy against ground truth when possible.
- **Field accuracy:** Validate entity-level extraction for names/stats.
- **Structural fidelity:** Track heading/table detection success and section counts.
- **Error density:** Log errors per page or per 1K words.
