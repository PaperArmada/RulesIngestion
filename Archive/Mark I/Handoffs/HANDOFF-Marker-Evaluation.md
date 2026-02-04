# Handoff: Datalab Marker Evaluation
**Date:** 2026-01-21  
**Type:** Evaluation / Research  
**Last Updated:** 2026-01-21 16:30  

---

## 🎯 MISSION

Evaluate **Datalab Marker** (VikParuchuri/marker) as a potential replacement or enhancement for the current Docling-based extraction pipeline. Marker offers:
- Direct PDF → Markdown/JSON/Chunks conversion
- Optional LLM enhancement for complex tables
- Built-in "chunks" output mode designed for RAG
- LaTeX math support

---

## 🚨 CURRENT STATE

### Context
- **Docling** evaluation complete - works but struggles with complex TTRPG layouts
- **PaddleOCR-VL** evaluation complete - Docling found to be more accurate for spell blocks
- **Marker** - Not yet evaluated

### Why Marker?
1. **Chunks output mode** - specifically designed for RAG pipelines (matches our use case)
2. **Optional LLM enhancement** (`--use_llm`) - improves table/form accuracy when needed
3. **Benchmarks claim** - outperforms Mathpix, LlamaParse, and similar tools
4. **Simpler pipeline** - direct PDF → structured output with minimal custom code

### License Consideration ⚠️
- **GPL-3.0** license (more restrictive than Apache 2.0)
- Model weights are **cc-by-nc-sa-4.0** (non-commercial restrictions)
- Need to verify compatibility with DungeonMind licensing

---

## Quick Pickup

### Step 1: Install Marker

```bash
cd /media/drakosfire/Projects/DungeonOverMind/RulesIngestion

# Option A: pip install
pip install marker-pdf

# Option B: uv install
uv pip install marker-pdf

# Option C: Clone and poetry install (for latest)
git clone https://github.com/VikParuchuri/marker.git
cd marker
poetry install

# Verify installation
marker --help
```

**Dependencies:** Python 3.10+, PyTorch, Surya OCR (installed automatically)

### Step 2: Run Marker on Test PDF

```bash
# Basic conversion (Markdown output)
marker "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/source/PZO22001 Starfinder Player Core 294-329.pdf" \
  "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/marker_eval"

# With LLM enhancement (better tables)
marker "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/source/PZO22001 Starfinder Player Core 294-329.pdf" \
  "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/marker_eval_llm" \
  --use_llm
```

### Step 3: Get JSON Output (Structured Tree)

```bash
# JSON output with block types and section hierarchies
marker "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/source/PZO22001 Starfinder Player Core 294-329.pdf" \
  "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/marker_eval_json" \
  --output_format json
```

### Step 4: Get Chunks Output (RAG-Optimized)

```bash
# Chunks output - flattened list of blocks for RAG
marker "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/source/PZO22001 Starfinder Player Core 294-329.pdf" \
  "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/outputs/marker_eval_chunks" \
  --output_format chunks
```

### Step 5: Python API (For Integration)

```python
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered

# Initialize models
model_dict = create_model_dict()
converter = PdfConverter(artifact_dict=model_dict)

# Convert PDF
pdf_path = "/media/drakosfire/Projects/DungeonOverMind/RulesIngestion/Rules/StarFinder2e/PlayerCore/source/PZO22001 Starfinder Player Core 294-329.pdf"
rendered = converter(pdf_path)

# Get markdown
markdown = text_from_rendered(rendered)
print(markdown[:2000])

# Save
with open("marker_output.md", "w") as f:
    f.write(markdown)
```

---

## Evaluation Criteria

### 1. Spell Block Coherence

**Test Case: DESICCATE spell**

Expected structure:
```
## DESICCATE [two-actions]

**CONCENTRATE MANIPULATE VOID**

**Traditions** arcane, primal  
**Range** 500 feet; **Targets** any number of living creatures  
**Defense** basic Fortitude

You pull the moisture from the targets' bodies, dealing 10d10 void damage...

**Heightened (+1)** The damage increases by 1d10.
```

**Check:**
- [ ] Title and action icons together
- [ ] Traits formatted consistently
- [ ] Stat block as key-value pairs
- [ ] Description follows stats
- [ ] Heightened at end

### 2. Multi-Column Layout

**Check:**
- [ ] Left column reads before right column
- [ ] Spells don't interleave between columns
- [ ] Reading order preserved

### 3. Table Extraction

**Check:**
- [ ] Markdown table syntax correct
- [ ] Compare with `--use_llm` vs without
- [ ] Column headers preserved

### 4. Chunks Output Quality

**Check:**
- [ ] Chunks are semantically coherent
- [ ] Appropriate chunk boundaries
- [ ] Metadata included (page numbers, section info)
- [ ] Ready for vector embedding

### 5. Comparison with Docling

**Check:**
- [ ] Same DESICCATE spell - which is more accurate?
- [ ] Same spell list page - which handles columns better?
- [ ] Output format - which requires less post-processing?

---

## Key Files

```
RulesIngestion/
├── Handoffs/
│   ├── HANDOFF-Rules-Ingestion-Markdown-Metadata.md  # Main pipeline handoff
│   ├── HANDOFF-PaddleOCR-VL-Evaluation.md            # PaddleOCR evaluation (complete)
│   ├── REPORT-PaddleOCR-VL-Evaluation.md             # PaddleOCR findings
│   └── HANDOFF-Marker-Evaluation.md                  # THIS FILE
└── Rules/StarFinder2e/PlayerCore/
    ├── source/
    │   └── PZO22001 Starfinder Player Core 294-329.pdf  # Test PDF
    └── outputs/
        ├── PZO22001...294-329.annotated.md   # Docling output
        ├── paddle_eval/                       # PaddleOCR output
        ├── marker_eval/                       # Marker markdown (create)
        ├── marker_eval_llm/                   # Marker + LLM (create)
        ├── marker_eval_json/                  # Marker JSON (create)
        └── marker_eval_chunks/                # Marker chunks (create)
```

---

## Status

| Task | Status | Description |
|------|--------|-------------|
| Install Marker | ✅ Complete | `uv add marker-pdf` |
| Run basic conversion | ✅ Complete | Markdown output (~28s for 36 pages) |
| Run with `--use_llm` | ⬜ Not Started | LLM-enhanced tables (requires API key) |
| Run JSON output | ✅ Complete | Structured tree format |
| Run chunks output | ✅ Complete | RAG-optimized format |
| Compare spell blocks | ✅ Complete | DESICCATE - Marker wins significantly |
| Compare with Docling | ✅ Complete | Side-by-side analysis |
| Document findings | ✅ Complete | See REPORT-Marker-Evaluation.md |

---

## Expected Outputs

After evaluation, update `REPORT-Marker-Evaluation.md`:

```markdown
# Marker vs Docling Comparison Report

## Test PDF: PZO22001 Starfinder Player Core 294-329.pdf

### Spell Block Coherence
| Approach | DESICCATE | Multi-Column | Score |
|----------|-----------|--------------|-------|
| Docling  | ...       | ...          | /10   |
| Marker   | ...       | ...          | /10   |
| Marker+LLM | ...     | ...          | /10   |

### Chunks Quality (RAG Readiness)
- Marker chunks output: {assessment}
- Compared to Docling chunks: {assessment}

### Recommendation
- [ ] Stay with Docling
- [ ] Replace with Marker
- [ ] Hybrid approach (specify)
```

---

## Marker vs Other Options

| Feature | Docling (Current) | PaddleOCR-VL | Marker |
|---------|-------------------|--------------|--------|
| **Approach** | Layout + OCR | VLM (0.9B) | Layout + Surya OCR + optional LLM |
| **Output Formats** | JSON, Markdown | Markdown, JSON | Markdown, JSON, HTML, **Chunks** |
| **Table Handling** | TableFormer | Built-in VLM | Table + LLM enhancement |
| **Math/Equations** | Limited | Built-in | **LaTeX** (`$$...$$`) |
| **LLM Enhancement** | No | Built-in (VLM) | Optional `--use_llm` |
| **RAG Optimization** | Custom chunking | Standard | **Built-in chunks mode** |
| **License** | Apache 2.0 | Apache 2.0 | **GPL-3.0** ⚠️ |
| **Multi-format** | PDF only | PDF, images | PDF, images, PPTX, DOCX, etc. |

---

## Context

### Why Consider Marker?

The current Docling pipeline works but requires significant custom code for:
- Metadata enrichment
- Chunk generation
- Graph building

Marker offers an "all-in-one" solution:
- Direct PDF → structured output
- Built-in chunks mode for RAG
- Optional LLM enhancement when accuracy matters
- Less custom code to maintain

### Integration Options (After Evaluation)

1. **Direct Replacement**: Use Marker instead of Docling
   - Simpler pipeline
   - Built-in chunks
   - But: GPL-3.0 license concerns

2. **Hybrid**: Use Marker for extraction, keep our metadata enrichment
   - Best of both worlds
   - Marker handles layout, we handle TTRPG semantics

3. **Chunks Comparison**: Compare Marker's chunks vs our `_chunk_markdown()`
   - If Marker's chunks are better for RAG, consider adopting

4. **Stay with Docling**: If evaluation shows Docling + our enrichment is better
   - More control over output
   - Apache 2.0 license (no restrictions)

---

## References

- **Marker GitHub:** https://github.com/VikParuchuri/marker
- **Datalab API Docs:** https://documentation.datalab.to/docs/recipes/marker/conversion-api-overview
- **Related Handoff:** `HANDOFF-PaddleOCR-VL-Evaluation.md`
- **PaddleOCR Report:** `REPORT-PaddleOCR-VL-Evaluation.md`
- **Main Pipeline Handoff:** `HANDOFF-Rules-Ingestion-Markdown-Metadata.md`
