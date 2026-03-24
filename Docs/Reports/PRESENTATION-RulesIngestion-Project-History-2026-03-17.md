# Presentation: Rules Ingestion Project History

**Date:** 2026-03-17  
**Purpose:** Speaker-ready presentation document for a project history talk on `RulesIngestion`  
**Audience:** Internal team / stakeholders / collaborators

---

## Presentation Goal

Tell the story of `RulesIngestion` as a project that started broad and ambitious, learned hard lessons through dead ends and benchmark pain, and gradually matured into a deterministic, provenance-first evidence system for a future rules engine.

The central message should be:

> The substrate is the product.

---

## Opening Framing

Use this at the start of the talk:

`RulesIngestion` is not just a PDF parsing project and not just a RAG project. Its real job is to transform visually complex TTRPG rulebooks into trustworthy, citable, deterministic units of evidence that can support retrieval today and executable rule systems later.

If you want a shorter opener:

> This project began as a retrieval experiment and matured into the front half of a compiler-adjacent rules system.

---

## Slide 1

### Title

`Rules Ingestion: From Rulebooks to Trustworthy Rule Evidence`

### Core Point

The project exists to turn messy authored rulebooks into a deterministic, provenance-rich substrate for retrieval and future rules execution.

### Speaker Notes

Start by correcting the framing. This is not "chat with PDFs." The project goal is stricter: preserve rule text faithfully enough that downstream retrieval, citation, and future engine compilation are all grounded in evidence instead of approximation.

Stress that this changes what "good" means:

- not just answer quality
- not just embedding performance
- but evidence fidelity, determinism, and auditability

### Suggested Quote

> Rules Ingestion is not just "PDF parsing for RAG." Its job is to turn authored rulebooks into a deterministic, provenance-rich, retrieval-ready substrate...

### Source

`Docs/Design/Rules_Ingestion_Project_Capture.md`

---

## Slide 2

### Title

`The Early Vision: Graphs, Chunks, Retrieval, Ambition`

### Core Point

Early `RulesIngestion` was intentionally broad: enriched chunks, deterministic graphs, traversal, rule facts, hybrid retrieval, and evaluation assets all at once.

### Speaker Notes

Present this phase honestly but respectfully. The early version reached for a lot of power very quickly. That created architectural sprawl, but it also exposed the real problem space:

- chunks are not automatically trustworthy evidence
- graph structure is not a substitute for source fidelity
- retrieval quality is bottlenecked by ingestion quality
- evaluation can lie if benchmark grounding is weak

Frame this as exploratory work that surfaced the questions the later system had to answer.

### Suggested Quote

> Transform TTRPG rulebooks into structured, graph-connected, retrieval-ready artifacts.

### Source

`Archive/Mark I/README.md`

---

## Slide 3

### Title

`Mark III: The Architectural Reset`

### Core Point

Mark III was the turning point. The project explicitly rejected chunk-first authority and made authored prose the canonical substrate.

### Speaker Notes

This is the most important before-and-after slide.

The team learned that if the source reconstruction is wrong, everything built on top of it becomes fragile or misleading. Mark III changed the mental model:

- authored prose first
- evidence binding second
- semantics and graphs later

This reset turned the project from "interesting retrieval machinery" into a serious ingestion architecture.

### Suggested Quote

> RulesIngestion Mark III treats authored prose as the canonical substrate.

### Source

`Docs/Design/archive/RULES_INGESTION_MARK_III.md`

---

## Slide 4

### Title

`The Key Insight: The Unit Of Retrieval Must Also Be The Unit Of Evidence`

### Core Point

`EvidenceUnit` became the single most important abstraction in the project.

### Speaker Notes

Explain why this mattered.

The project stopped treating retrieval chunks, semantic projections, and future graph artifacts as interchangeable. Instead it separated:

- canonical admissible evidence
- retrieval-only projections
- future enrichment and graph layers

That separation is why the architecture became stable. It protected the system from retrieval hacks becoming fake source truth.

### Suggested Quote

> The unit of retrieval must also be a trustworthy unit of evidence.

### Source

`Docs/Design/Rules_Ingestion_Project_Capture.md`

---

## Slide 5

### Title

`What Actually Worked`

### Core Point

The biggest wins were architectural discipline, benchmark hardening, and a few validated retrieval improvements.

### Speaker Notes

Highlight the concrete wins:

- `EvidenceUnit` as canonical evidence
- strict Stage A / Stage B boundaries
- deterministic artifact and baseline discipline
- benchmark projection contracts
- hybrid retrieval gains on the right corpora
- stronger evaluation surfaces and promotion rules

A strong point here is that the project got better not just by improving scores, but by improving how it decided whether a score should be trusted.

### Suggested Quote

> All 10 successful reruns finished with `contract_valid=true` and `promotion_ready=true`.

### Source

`Docs/Reports/REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md`

### Optional Supporting Points

- `PF2e`, `SR4`, and `Starfinder` broad benchmarks became fully ratified and clean.
- Hybrid retrieval produced clear gains on `Starfinder`.
- Cross-corpus model selection became evidence-based instead of taste-based.

---

## Slide 6

### Title

`The Dead Ends Were Real, And They Taught Us A Lot`

### Core Point

Several expensive paths turned out to be wrong, premature, or only partly useful.

### Speaker Notes

Be candid here. This increases credibility.

Main dead ends or painful lessons:

- naive extraction was not enough
- fixed-size chunking was destructive
- dense-only optimism did not hold for rules text
- benchmark quality was a hidden source of confusion
- graph temptation arrived before substrate stability
- always-on decomposition failed on PHB5e

Explain that these were not just abstract lessons. They cost time, but they also forced the team to define the system more clearly.

### Suggested Quote

> If the ingestion is wrong, everything after it is fake progress.

### Source

`Docs/Design/Rules_Ingestion_Project_Capture.md`

### Optional Supporting Example

The chunking regression is a clean case study: raw corpus shaping created micro-chunk and duplicate pollution, and the fix was to add enforced defaults plus a pre-run chunk-quality gate.

Source: `Docs/Design/ARCHITECTURE-Chunking-System-Deep-Dive-2026-02-28.md`

---

## Slide 7

### Title

`One Of The Best Signs Of Maturity: The Project Learned To Say No`

### Core Point

The decomposition work is valuable because it shows the team tested a serious idea, measured it carefully, and refused to promote it when it regressed the benchmark.

### Speaker Notes

This is one of the strongest credibility slides in the deck.

Use it to show that the current architecture is not a pile of accumulated cleverness. Instead:

- ideas are tested against contract-valid surfaces
- regressions are investigated per-query
- features that do not clear the bar remain off

This is the opposite of feature hoarding.

### Suggested Quote

> Verdict: not promoted.

### Source

`Docs/Experiments/EXPERIMENT-Query-Decomposition.md`

### Optional Supporting Note

The failure mode was especially telling: the prompt often behaved more like a research planner than a bounded retrieval controller.

Source: `Docs/Reports/REPORT-Decomposition-System-Comprehensive-Review.md`

---

## Slide 8

### Title

`Where The Project Is Now`

### Core Point

The project is now converging on a simpler and stronger architecture:

- a deterministic substrate plane
- a bounded retrieval runtime plane
- a contract-aware evaluation plane

### Speaker Notes

End on confidence and direction.

The current architecture is smaller than some earlier versions, but much more durable. The system now knows:

- what counts as truth
- what is retrieval-only
- what has been validated
- what is still experimental

The current runtime path is intentionally tight: classify, retrieve, maybe decompose if proven, assemble a fixed pool, rerank, and return cited `EvidenceUnit`s.

### Suggested Quote

> Rules Ingestion has matured from a retrieval experiment into the beginnings of a real compiler-adjacent subsystem.

### Source

`Docs/Design/Rules_Ingestion_Project_Capture.md`

---

## Suggested Closing Slide Or Closing Line

If you want a formal closing slide, use:

### Title

`The Deepest Lesson`

### Closing Line

> The substrate is the product: if the evidence is faithful, bounded, citable, and deterministic, everything downstream becomes possible.

### Speaker Notes

Close by tying the whole project together.

This project did find retrieval wins. It did produce architectural advances. But the deepest success was more foundational: it learned that rule retrieval, rule citation, and future rules execution all stand or fall on the quality of the evidence substrate.

That is the hard-earned lesson underneath every success and every dead end.

---

## Optional Appendix: Fast Talking Points

Use these if you need short answers during Q&A.

### What was the biggest success?

Turning `EvidenceUnit` into the canonical admissible layer and hardening evaluation enough that the team could trust its own comparisons.

### What was the biggest failure?

Treating retrieval cleverness as if it could compensate for an unstable or poorly shaped substrate.

### What changed the trajectory most?

Mark III, followed by benchmark hardening and projection-contract discipline.

### What is still unresolved?

- SWCR remains a real retrieval-quality problem on a clean surface.
- Answer-eval for reranking still needs parse-path repair before answer-level fidelity claims are trustworthy.
- Stage C should only be promoted where it produces typed artifacts useful beyond retrieval rescue.

---

## Recommended Source Documents

These are the most useful documents to keep open while presenting:

- `Docs/Design/Rules_Ingestion_Project_Capture.md`
- `Docs/Design/archive/RULES_INGESTION_MARK_III.md`
- `Docs/Design/archive/v1/architecture_overview.md`
- `Docs/Reports/REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md`
- `Docs/Reports/REPORT-Embedding-Bakeoff-Comprehensive-2026-03-04.md`
- `Docs/Reports/REPORT-Hybrid-Bakeoff-2026-03-05-Full.md`
- `Docs/Reports/REPORT-Decomposition-System-Comprehensive-Review.md`
- `Docs/Experiments/EXPERIMENT-Query-Decomposition.md`

---

## One-Paragraph Version

If someone asks for the summary in one paragraph:

`RulesIngestion` started as a broad graph-and-retrieval effort, but the team learned that none of that mattered if the underlying evidence was unstable. Mark III reset the architecture around authored prose and `EvidenceUnit`s as canonical evidence. From there, the project hardened benchmark contracts, projection logic, and promotion discipline, found real wins in hybrid retrieval and evaluation rigor, and also discovered meaningful dead ends like always-on decomposition. The project is now much more focused: build a deterministic, provenance-safe evidence substrate first, then layer bounded retrieval and future typed rule extraction on top of it.
