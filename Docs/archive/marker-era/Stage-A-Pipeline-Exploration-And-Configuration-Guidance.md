> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Stage A Pipeline Exploration and Configuration Guidance

## Goals and Context

The goal of Stage A is to produce a **deterministic, replayable and high‑quality extraction** of complex multi‑column rulebooks (e.g. TTRPG manuals) so that Stage B and later stages can focus on grouping and admissibility rather than fixing extraction errors. The extraction layer should

* preserve **reading order** and **region separation** so that text from adjacent columns or sidebars does not interleave;

* capture **semantic unit boundaries** (e.g. spell/stat block/feat headers and bodies) using visual cues (font, underline, spacing);

* include **bounding boxes, block types and region labels** so that downstream modules can deterministically assign structural addresses and authority tiers;

* remain **deterministic** across runs and versions and avoid stochastic OCR outputs;

* provide options for raising or lowering thresholds (e.g. MAX\_CHARS) without hidden learned weights.

This section explores each pipeline/profile defined in §6.1 and recommends how to configure it to best meet these goals. Where available, lines from documentation or research are cited to justify claims.

---

## P0 — Baseline: Current Marker pipeline

**Summary**

Marker is a CLI tool built on the **Surya** OCR/layout engine. It extracts PDFs into Markdown/JSON by performing OCR, layout detection (including reading order) and table recognition. Marker is used as the current Stage A baseline in the mark II spec.

**Capabilities**

* Surya’s layout analysis task yields bounding boxes for text, captions, figures and headings and returns their reading-order positions[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR). This enables a deterministic total order over the page.

* Surya can recognise tables and break them into cells[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR).

**Known weaknesses**

* An academic critique notes that mistakes in Marker’s layout analysis propagate: reading-order errors cause content from different regions to be merged or separated incorrectly[\[2\]](https://arxiv.org/html/2512.18122v1#:~:text=A%20widely%20used%20method%20for,modules%20are%20called%20to%20convert). This leads to column interleaving and orphaned headers in Stage B.

* Marker uses heuristics for region merging that may not distinguish between main text and sidebars, causing two‑column pages to interleave.

**Configuration recommendations**

1. **Pin versions for determinism.** Use a containerised version of Marker with pinned Surya weights and dependencies so that repeated runs yield identical MarkerStream and chunk IDs.

2. **Disable high‑aggressive grouping.** Marker has rules for merging adjacent text blocks. Adjust configuration to **avoid merging across columns**; if necessary, treat each column as a separate region and linearise left→right after top→bottom ordering.

3. **Enable table extraction.** Surya’s table recognition should be enabled by passing \--tasks layout ocr table to preserve tables as separate blocks and avoid mixing them into prose[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR).

4. **Capture font/underline metadata.** Marker can output style attributes (e.g. bold, italic, font size) from Surya. Include these in the MarkerStream to help Stage B identify templates (spell/monster/feat headers).

5. **Log reading‑order issues early.** Add instrumentation to detect when bounding boxes from distinct columns overlap in the reading order. Use the StageA‑Pathology metrics to flag interleaving before Stage B.

---

## P1 — Marker “strict layout” variants

If Marker exposes configuration options to change layout heuristics, this profile explores them.

**Potential options**

* **Column detection mode.** Some Surya settings allow switching between full‑page reading order and per‑column segmentation. Enabling strict column isolation prevents mixing of left and right columns. Surya’s layout task returns region labels such as caption, footnote, figure and **section‑header**[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR); these labels could be used to separate sidebars from body text.

* **Reading‑order heuristics.** Marker might provide flags controlling how reading order is computed (e.g. top‑to‑bottom vs left‑to‑right). Setting a stricter heuristic (e.g. “sort by column index then y‑coordinate”) can reduce interleaving.

* **Minimum block size thresholds.** Lowering thresholds for merging may reduce the number of micro‑chunks but risks merging across column boundaries. Conversely, raising thresholds may increase fragmentation but preserve separation.

**Recommendation**

* **Test multiple heuristics on the StageA‑Pathology suite**. For each pathologic page, run Marker with default and strict layout flags and compute interleaving/record‑integrity metrics. Promote only the configuration that meets Stage A gates.

* **If strict options are unavailable**, treat P1 as identical to P0 and rely on external segmentation (see P2–P7).

---

## P2 — Surya‑based extraction

Instead of using Marker’s high‑level pipeline, one can directly invoke **Surya** to produce raw OCR and layout data. Surya supports multiple tasks:

* ocr\_with\_boxes performs multilingual OCR and returns bounding boxes for each line and token.

* layout performs **layout detection and reading order detection**[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR). It labels regions (caption, footnote, figure, section‑header, page header/footer) and outputs their reading‑order positions so that a page can be linearised correctly.

* table performs **table recognition** and can break tables into cells[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR).

**Strengths**

* Surya’s reading order detection yields a deterministic ordering of blocks and supports multilingual PDFs, which is essential for rulebooks with names and spells in various languages[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR).

**Limitations**

* Surya does not attempt to enforce semantics (it cannot recognise that a bold line is a monster name). It may still mis‑order columns if pages have complex sidebars.

**Configuration guidelines**

1. **Perform all Surya tasks:** layout, ocr\_with\_boxes and table concurrently. This ensures bounding boxes, reading order and table structure are all available for Stage B.

2. **Calibrate reading order.** Surya’s layout output includes a reading\_order attribute. Use this to reconstruct the reading sequence for each region. When multi‑column is detected, sort by column index and vertical position to produce a stable ordering.

3. **Flag region labels.** Use Surya’s region labels (e.g. section‑header, caption, footnote) to filter out non‑text regions such as page numbers and footnotes.

4. **Persist style attributes.** If Surya returns font size or bold attributes, preserve them so Stage B can recognise templates.

5. **Integrate with custom grouping.** Because Surya alone does not merge paragraphs, Stage B will need to group line‑level tokens into logical paragraphs. Use heuristics based on bounding box gaps and indentation.

---

## P3 — Docling conversion pipeline

Docling is a structured conversion pipeline that emphasises layout analysis and reading‑order tracking. Recent improvements include the **Heron** layout model, which maps entire pages to boxes and uses a separate module to predict reading order. According to the Docling report, Heron “splits the page into multiple boxes in a 2D plane” and a reading‑order module **predicts the order to reconstruct paragraphs**[\[3\]](https://alain-airom.medium.com/behind-the-scenes-of-docling-pdf-parsing-20f557b289da#:~:text=Share). This results in near‑human reading‑order accuracy.

**Strengths**

* Built‑in reading‑order predictor yields structured paragraphs rather than a “word salad”[\[3\]](https://alain-airom.medium.com/behind-the-scenes-of-docling-pdf-parsing-20f557b289da#:~:text=Share). This is valuable for multi‑column documents.

* Docling’s layout models (Heron, Egret) are modular; they can be swapped for faster or more accurate models.

* It provides cell assignment and table extraction options for forms.

**Limitations**

* Docling is more complex and may rely on learned models (LayoutLMv3/Heron). Determinism must be ensured by pinning model versions and disabling random augmentations.

**Configuration guidelines**

1. **Select the Heron layout model** for highest reading‑order accuracy[\[3\]](https://alain-airom.medium.com/behind-the-scenes-of-docling-pdf-parsing-20f557b289da#:~:text=Share). Use Egret only if performance becomes a bottleneck.

2. **Enable reading‑order reconstruction**. Docling’s pipeline has flags to output reading order. Use these to linearise multi‑column pages before grouping.

3. **Use table model if rulebook tables are important.** Docling includes a table model to extract table structure as JSON.

4. **Disable randomness.** Pin model weights and disable dropout to maintain deterministic outputs. Use Docker containers to freeze dependencies.

5. **Configure cluster rules.** Docling’s keep\_empty\_clusters and skip\_cell\_assignment settings can be tuned to prevent merging lines across sections. On pathologic pages, test which settings best preserve record boundaries.

---

## P4 — PDF‑Extract‑Kit

PDF‑Extract‑Kit is an open‑source toolkit for high‑quality extraction from complex PDFs. It emphasises modular layout detection and recognition tasks. The documentation notes that the kit provides **layout detection** using models such as DocLayout‑YOLO, YOLOv10 and LayoutLMv3, plus table recognition and formula recognition[\[4\]](https://github.com/opendatalab/PDF-Extract-Kit#:~:text=Task%20Type%20Description%20Models%20Layout,UniMERNet). A **reading‑order sorting model** is planned but not yet available[\[4\]](https://github.com/opendatalab/PDF-Extract-Kit#:~:text=Task%20Type%20Description%20Models%20Layout,UniMERNet).

**Strengths**

* Excellent region segmentation: the object‑detection models can identify figures, tables, formulas and text blocks; this prevents mixing sidebars with main text.

* Table recognition (TableMaster) can extract table content into structured form[\[4\]](https://github.com/opendatalab/PDF-Extract-Kit#:~:text=Task%20Type%20Description%20Models%20Layout,UniMERNet).

**Limitations**

* Lacks a mature reading‑order module at present[\[4\]](https://github.com/opendatalab/PDF-Extract-Kit#:~:text=Task%20Type%20Description%20Models%20Layout,UniMERNet); thus cannot on its own linearise multi‑column pages.

* May depend on learned detectors that need deterministic seeding.

**Configuration guidelines**

1. **Use PDF‑Extract‑Kit for segmentation only.** Run its layout model to produce bounding boxes and region labels; treat the output as a segmentation map.

2. **Pair with a reading‑order engine.** Because reading order is absent, feed the segmented regions into a reading‑order algorithm (e.g. Surya’s or Docling’s reading‑order module). Sort regions by x‑coordinate and y‑coordinate to approximate reading order.

3. **Activate TableMaster and formula detection** for rulebooks that contain tables and formulas; this will keep tables separate from text[\[4\]](https://github.com/opendatalab/PDF-Extract-Kit#:~:text=Task%20Type%20Description%20Models%20Layout,UniMERNet).

4. **Pin the detection model**. Choose a single model (e.g. LayoutLMv3 or YOLOv10) and freeze its weights for determinism.

5. **Tune detection thresholds**. Lower thresholds may detect small sidebars; test on the pathology suite to avoid missing small spell headers.

---

## P5 — TrOCR “strategy ladder” pipeline

A recent technical article proposes a robust multi‑stage OCR pipeline built around **TrOCR**. It runs a **“strategy ladder”** of OCR engines with preprocessing and heuristics[\[5\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Ordered%20escalation%3A%201.%20Full,text%20layer%20for%20digital%20PDFs):

1. Rasterise each page and apply preprocessing (grayscale, denoise, gamma correction, binarisation).

2. Run full‑page TrOCR; if the result has enough characters (min\_chars\_accept) and the non‑white pixel ratio is high, accept it.

3. Otherwise, run **PaddleOCR** for text detection and recognition to handle pages where layout segmentation is needed[\[5\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Ordered%20escalation%3A%201.%20Full,text%20layer%20for%20digital%20PDFs).

4. If detection fails, run **line‑level TrOCR** on small detected lines or cropping windows.

5. As a final fallback, run **Tesseract** or vector text extraction to catch any remaining text[\[5\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Ordered%20escalation%3A%201.%20Full,text%20layer%20for%20digital%20PDFs).

6. Post‑process and evaluate accuracy metrics (character/word error rate); adjust pipeline accordingly[\[5\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Ordered%20escalation%3A%201.%20Full,text%20layer%20for%20digital%20PDFs).

**Strengths**

* Robustness: by cascading multiple OCR engines and fallbacks, the pipeline recovers text from degraded scans and small fonts[\[5\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Ordered%20escalation%3A%201.%20Full,text%20layer%20for%20digital%20PDFs).

* Preprocessing heuristics improve OCR results under poor contrast or skew[\[6\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Per).

* Logging of metrics (word error rate, acceptance heuristics) provides observability.

**Limitations**

* It focuses on OCR accuracy rather than layout; thus reading order and table segmentation must be handled separately.

* A multi‑stage pipeline may be slower and uses multiple learned components; determinism requires careful pinning.

**Configuration guidelines**

1. **Adopt the strategy ladder as a fallback for OCR within a segmented region.** Use a layout engine (e.g. Surya or PDF‑Extract‑Kit) to produce regions and apply the multi‑stage OCR only within each region. This prevents interleaving and provides better recognition of small fonts.

2. **Set acceptance heuristics.** Tune min\_chars\_accept and non\_white\_ratio thresholds to avoid prematurely accepting poor full‑page OCR[\[5\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Ordered%20escalation%3A%201.%20Full,text%20layer%20for%20digital%20PDFs). Use StageA metrics to calibrate these values.

3. **Preprocess only when needed.** Use grayscale, contrast, denoise and gamma correction for scanned images but skip for vector PDFs where vector text extraction may suffice.

4. **Pin all models** (TrOCR, PaddleOCR, Tesseract) to specific versions. Use deterministic seeds for model execution.

5. **Measure at each stage.** Log acceptance reasons and number of fallbacks. This will help triage where errors occur.

---

## P6 — DeepSeek‑OCR‑2 document mode

DeepSeek‑OCR‑2 is a vision‑language model designed to read documents “like humans.” The research emphasises that flattening a 2D layout into a 1D line loses the original reading order and leads to hallucinations. DeepSeek‑OCR‑2 therefore uses **causal flow queries** and a graph‑based encoder to learn the reading path: the model reads the document step‑by‑step, combining global and causal attention[\[7\]](https://webkul.com/blog/deepseek-ocr-2/#:~:text=Turning%20a%202D%20layout%20into,loses%20the%20original%20reading%20order). This approach claims to improve reading‑order accuracy and reduce repetition/hallucinations[\[7\]](https://webkul.com/blog/deepseek-ocr-2/#:~:text=Turning%20a%202D%20layout%20into,loses%20the%20original%20reading%20order).

**Strengths**

* The model is trained to follow a **natural reading order**, using both layout and semantics[\[7\]](https://webkul.com/blog/deepseek-ocr-2/#:~:text=Turning%20a%202D%20layout%20into,loses%20the%20original%20reading%20order). This can directly solve column interleaving issues.

* Dual attention (global and causal) gives tokens context about the entire page and the next word to read[\[7\]](https://webkul.com/blog/deepseek-ocr-2/#:~:text=Turning%20a%202D%20layout%20into,loses%20the%20original%20reading%20order).

**Limitations**

* DeepSeek‑OCR‑2 is a large VLM requiring GPU acceleration; determinism must be enforced by fixing the checkpoint and disabling randomness.

* The open‑source release may not provide full control over reading‑order outputs; it returns markdown or JSON using its own heuristics.

**Configuration guidelines**

1. **Use document mode with grounding tags**. The DeepSeek team suggests using \<|grounding|\> tags to enable structured document extraction. This ensures the model outputs text with layout markers rather than free‑form summarisation.

2. **Pin the model version and checkpoint** to ensure deterministic outputs. Avoid using online endpoints that might change weights.

3. **Provide page images, not PDF text**, because the model processes images. For vector PDFs, first rasterise pages at high resolution.

4. **Combine with template heuristics.** Even with accurate reading order, treat outputs carefully: verify that the model separated spells, monsters and sidebars, using StageA metrics. If necessary, post‑process the markdown into EvidenceChunks.

5. **Validate performance on pathology suite.** Because VLMs may guess content, test on pathologic pages and ensure near‑perfect recall and ordering.

---

## P7 — LlamaParse / document‑parsing APIs

LlamaParse is a commercial/open source API for parsing PDFs into structured Markdown or JSON. It emphasises preserving document structure, especially **tables**, and offers a fast boolean that toggles heuristics for speed versus accuracy. The documentation notes that LlamaParse can unroll table columns correctly in Markdown and has options to **flatten multi‑row headers**[\[8\]](https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama_parse/#:~:text=LlamaParse%20is%20an%20API%20created,converting%20PDF%20tables%20into%20markdown).

**Strengths**

* Converts complex PDFs into Markdown while preserving headers, paragraphs and tables. It is particularly good at converting tables[\[8\]](https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama_parse/#:~:text=LlamaParse%20is%20an%20API%20created,converting%20PDF%20tables%20into%20markdown).

* Offers a fast mode for quicker parsing but notes that it may be less accurate[\[8\]](https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama_parse/#:~:text=LlamaParse%20is%20an%20API%20created,converting%20PDF%20tables%20into%20markdown).

* Suitable as a high‑level baseline for comparison against open‑source pipelines.

**Limitations**

* Being an external service, determinism may be limited; API updates could change outputs.

* May not expose bounding boxes or reading order indices; it returns Markdown which may embed structure implicitly.

* Terms of service may restrict use or reproduction; thus treat P7 as a “reference competitor” rather than a production option.

**Configuration guidelines**

1. **Set fast=False for maximum accuracy**[\[8\]](https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama_parse/#:~:text=LlamaParse%20is%20an%20API%20created,converting%20PDF%20tables%20into%20markdown). Use the slow/accurate mode when generating the pathology suite outputs.

2. **Extract table settings.** If available, set flags to flatten multi‑row headers and preserve merged cells so that rulebook tables remain intact[\[8\]](https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama_parse/#:~:text=LlamaParse%20is%20an%20API%20created,converting%20PDF%20tables%20into%20markdown).

3. **Interpret Markdown into blocks.** Because LlamaParse returns Markdown, Stage A must parse the Markdown into blocks (e.g. headings, paragraphs, lists). Use heuristics to derive bounding boxes or approximate spans.

4. **Validate determinism.** Keep a copy of the API response for each page. If results change over time, use local caching or consider another pipeline.

5. **Use for evaluation only.** Because of ToS and reproducibility constraints, treat LlamaParse as a benchmark for what a high‑quality extraction might look like rather than the final extractor.

---

## Comparing Pipelines and Selecting Configurations

The StageA‑Pathology suite defines metrics such as column interleaving rate, record integrity, heading attachment and sidebar bleed. Each pipeline should be run on the same set of pathologic pages, and metrics should be computed. A recommended approach:

1. **Segmentation vs OCR**

2. **Surya/Docling** excel at reading order and region segmentation, making them strong candidates for Stage A when configured properly.

3. **PDF‑Extract‑Kit** provides better segmentation but needs an external reading‑order module.

4. **TrOCR ladder** improves OCR quality but must be paired with segmentation.

5. **DeepSeek‑OCR‑2** may solve segmentation and OCR simultaneously but needs GPU resources and determinism checks.

6. **LlamaParse** is mostly useful as a reference for structure quality.

7. **Determinism**

8. Use containerised versions and fix seeds for all learned models.

9. Document model versions and hashing in StageA reports.

10. **Best‑effort configuration recommendations**

| Profile | Recommended configuration | Rationale |
| :---- | :---- | :---- |
| **P0: Marker** | Pin Marker version; enable Surya tasks layout, ocr\_with\_boxes, table; disable cross‑column merging; output style attributes; log reading‑order issues. | Baseline must ensure determinism and preserve as much structure as possible. |
| **P1: Marker strict** | If available, enable strict column detection and reading‑order heuristics; reduce merging across columns. | Minimises interleaving; may slightly increase fragmentation. |
| **P2: Surya** | Call Surya directly with layout+ocr+table; reconstruct reading order from reading\_order fields; treat region labels to separate sidebars; preserve style attributes. | Provides fine‑grained control over layout and reading order[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR). |
| **P3: Docling** | Use Heron layout model and enable reading‑order reconstruction[\[3\]](https://alain-airom.medium.com/behind-the-scenes-of-docling-pdf-parsing-20f557b289da#:~:text=Share); enable table model; pin weights; tune cluster rules; ensure determinism. | Offers near‑human reading order and structured output. |
| **P4: PDF‑Extract‑Kit** | Run only for segmentation; choose a layout model; tune thresholds; output region labels; pair with a reading‑order engine (e.g. Surya). | Excellent at detecting regions/tables but lacks reading order[\[4\]](https://github.com/opendatalab/PDF-Extract-Kit#:~:text=Task%20Type%20Description%20Models%20Layout,UniMERNet). |
| **P5: TrOCR ladder** | Use as OCR fallback within segmented regions; tune acceptance heuristics (min\_chars\_accept, non\_white\_ratio)[\[5\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Ordered%20escalation%3A%201.%20Full,text%20layer%20for%20digital%20PDFs); measure accuracy; pin models. | Provides robust OCR for difficult scans, but not layout. |
| **P6: DeepSeek‑OCR‑2** | Use document mode with \<|grounding|\> tags; pin model; rasterise pages; validate reading order; treat as potential high‑accuracy extractor. | Designed to follow natural reading order[\[7\]](https://webkul.com/blog/deepseek-ocr-2/#:~:text=Turning%20a%202D%20layout%20into,loses%20the%20original%20reading%20order); may replace separate segmentation and OCR. |
| **P7: LlamaParse** | Use fast=False to maximise accuracy[\[8\]](https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama_parse/#:~:text=LlamaParse%20is%20an%20API%20created,converting%20PDF%20tables%20into%20markdown); flatten multi‑row table headers; parse Markdown into blocks; use as evaluation baseline. | Preserves structure and tables; determinism uncertain; treat as reference. |

1. **Experimental ladder**

2. Start with **P2 (Surya)** and **P3 (Docling)** because they offer strong reading‑order capabilities. Evaluate them on the pathology suite using StageA metrics.

3. If they pass gates, proceed to Stage B with minimal grouping changes. If not, test P4 \+ reading‑order algorithm or P6.

4. Use **P5** as an OCR fallback within whichever segmentation pipeline is chosen.

5. Use **P7** to validate that final extraction quality approaches the high‑quality reference.

6. **Next steps**

7. Implement instrumentation in Stage A to compute interleaving, heading attachment and sidebar bleed on the fly.

8. Build small adaptation layers: e.g. a **Surya→Marker** adapter that takes raw Surya outputs and constructs MarkerStream; a **PDF‑Extract‑Kit→Surya** pipeline.

9. Use the StageA‑Pathology suite to test variations and choose the pipeline that meets quality and determinism gates.

By systematically evaluating these pipelines and following the configuration recommendations, Stage A can be transformed from a brittle OCR process into a deterministic extraction layer that preserves the rich structure of complex rulebooks and sets the foundation for high‑recall retrieval and authoritative grounding.

---

[\[1\]](https://github.com/datalab-to/surya#:~:text=,LaTeX%20OCR) GitHub \- datalab-to/surya: OCR, layout analysis, reading order, table recognition in 90+ languages

[https://github.com/datalab-to/surya](https://github.com/datalab-to/surya)

[\[2\]](https://arxiv.org/html/2512.18122v1#:~:text=A%20widely%20used%20method%20for,modules%20are%20called%20to%20convert) Accelerating End-to-End PDF to Markdown Conversion through Assisted Generation

[https://arxiv.org/html/2512.18122v1](https://arxiv.org/html/2512.18122v1)

[\[3\]](https://alain-airom.medium.com/behind-the-scenes-of-docling-pdf-parsing-20f557b289da#:~:text=Share) Behind the scenes of Docling PDF Parsing | by Alain Airom (Ayrom) | Jan, 2026 | Medium

[https://alain-airom.medium.com/behind-the-scenes-of-docling-pdf-parsing-20f557b289da](https://alain-airom.medium.com/behind-the-scenes-of-docling-pdf-parsing-20f557b289da)

[\[4\]](https://github.com/opendatalab/PDF-Extract-Kit#:~:text=Task%20Type%20Description%20Models%20Layout,UniMERNet) GitHub \- opendatalab/PDF-Extract-Kit: A Comprehensive Toolkit for High-Quality PDF Content Extraction

[https://github.com/opendatalab/PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit)

[\[5\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Ordered%20escalation%3A%201.%20Full,text%20layer%20for%20digital%20PDFs) [\[6\]](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede#:~:text=Per) TrOCR : A Robust Multi‑Stage PDF OCR & Accuracy Pipeline with Streamlit | by Sobhan Hota | Medium

[https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede)

[\[7\]](https://webkul.com/blog/deepseek-ocr-2/#:~:text=Turning%20a%202D%20layout%20into,loses%20the%20original%20reading%20order) DeepSeek-OCR 2 : Changed How Machines Read Documents \- Webkul Blog

[https://webkul.com/blog/deepseek-ocr-2/](https://webkul.com/blog/deepseek-ocr-2/)

[\[8\]](https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama_parse/#:~:text=LlamaParse%20is%20an%20API%20created,converting%20PDF%20tables%20into%20markdown) LlamaParse | LlamaIndex Documentation

[https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama\_parse/](https://developers.llamaindex.ai/typescript/framework/modules/data/readers/llama_parse/)

---

**Execution:** For how to run, configure, and evaluate each pipeline (P0–P7) in this repo, see [StageA-Pipeline-Execution-And-Examination.md](StageA-Pipeline-Execution-And-Examination.md).
