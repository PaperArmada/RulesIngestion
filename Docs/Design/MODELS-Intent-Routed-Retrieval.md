# Model Lineup: Intent-Routed Retrieval

**Status:** Companion to [VISION-Intent-Routed-Retrieval.md](VISION-Intent-Routed-Retrieval.md). Reflects the local-model lineup as of 2026-05-28.
**Host machine:** WSL2 Ubuntu 24.04, i9-13950HX, 31 GB RAM, RTX 4080 Laptop (12 GB VRAM, compute 8.9).
**Runtime:** Ollama 0.13.0.

---

## 1. Role → Model Map

| Role | Model | Quant | Disk | Approx VRAM | Thinking default |
|---|---|---|---|---|---|
| Embedder (dense retrieval + HyDE hypothesis embedding) | `qwen3-embedding` | default | 4.7 GB | ~5-6 GB | n/a |
| Query classifier (online, per query) | `qwen3:4b` | Q4_K_M | ~2.5 GB | ~2.5-3 GB | **off** |
| Intent extractor & shape inference (online) | `qwen3:14b` | Q4_K_M | ~9 GB | ~9-10 GB | off (configurable on) |
| HyDE hypothesizer (online) | `qwen3:14b` | Q4_K_M | ~9 GB | ~9-10 GB | off |
| Synthesizer (online) | `qwen3:14b` | Q4_K_M | ~9 GB | ~9-10 GB | off (configurable on) |
| Glossary / acronym extractor (offline) | `qwen3:14b` | Q4_K_M | ~9 GB | ~9-10 GB | **on** |
| Structural cluster labeler (offline) | `qwen3:14b` | Q4_K_M | ~9 GB | ~9-10 GB | on |
| Cross-encoder reranker (online) | `bge-reranker-v2-m3` | full | ~2 GB on disk | ~2 GB | n/a |

Cross-encoder reranker is **not** an Ollama model. It runs via `sentence-transformers` / `FlagEmbedding` in-process.

---

## 2. Rationale

### Embedder: `qwen3-embedding:8b`

Qwen3-Embedding-8B is the leading open-weight MTEB English embedder as of early 2026. Gemini-Embedding-001 leads English MTEB but is API-only. Open alternatives (`nomic-embed-text` ~62.4 MTEB, `mxbai-embed-large` ~64.7 MTEB) trail by enough that a single-corpus advantage is unlikely but worth A/B-ing if Qwen3 underperforms on rulebook text specifically.

### Classifier: `qwen3:4b`

The classifier runs on every query, so latency matters. Qwen3-4B (Q4) is small enough to stay co-resident with the embedder and reportedly competitive with much larger models on simple structured-output tasks. Llama-3.2-3B was considered but is reported as unreliable for valid JSON without grammar constraints (~50% parse success without `format=json`). Qwen3-4B with `format=json` is a safer floor.

### Workhorse: `qwen3:14b`

Sweet spot for 12 GB VRAM at Q4_K_M. Used for all online generation roles (intent extraction, hypothesis generation, synthesis) and offline extraction. Reusing the same model across roles avoids model-swap latency on the hot path. Phi-4 (14B, 8.3 GB Q4_K_M) is the alternative, with reportedly better MMLU/GPQA but weaker IFEval (instruction adherence), which directly affects shape-constrained generation. Default to Qwen3-14B; revisit phi-4 if instruction-following turns out to be sufficient and reasoning advantage matters.

### Reranker: `bge-reranker-v2-m3`

Open standard cross-encoder reranker for 2026. Not packaged on Ollama. Run via `FlagEmbedding` or `sentence-transformers`. Upgrade path is `bge-reranker-v2-gemma` (9B) if latency budget allows.

---

## 3. VRAM Math

Concurrent residency budget on 12 GB VRAM:

| Combination | Approx VRAM | Headroom |
|---|---|---|
| `qwen3-embedding:8b` only | ~6 GB | 6 GB |
| `qwen3-embedding:8b` + `qwen3:4b` | ~9 GB | 3 GB |
| `qwen3-embedding:8b` + `qwen3:14b` | ~15-16 GB | **overflows** |
| `qwen3:4b` + `qwen3:14b` | ~12-13 GB | borderline |
| `qwen3:14b` only | ~10 GB | 2 GB |

Practical approach: Ollama swaps on demand. The hot path is:

```
[embedder loaded]
  -> embed query
  -> [classifier 4b kept co-resident, used to route]
  -> if intent-bearing bucket:
       [swap embedder out, load 14b]
       -> hypothesize
       -> [swap 14b out, load embedder]
       -> embed hypothesis & retrieve
       -> [swap embedder out, load 14b]
       -> synthesize
```

Each swap is ~1-2 s. For an intent-bearing query that pays for both hypothesis generation and synthesis, expect ~3-4 s of swap overhead added to model-inference time. Worth measuring before optimizing.

If swap overhead dominates, two mitigations:

1. Drop embedder to `qwen3-embedding:4b` (~2.5 GB) so it can stay co-resident with `qwen3:14b`.
2. Drop the workhorse to `qwen3:8b` (~5 GB) so both fit. Accept lower generation quality.

We'll measure first.

---

## 4. The Qwen3 Thinking-Mode Caveat

Qwen3 has a built-in "thinking" mode that emits a long chain-of-thought before its answer. This is on by default for the model family. For low-latency roles (classifier, hypothesizer, synthesizer) it destroys the latency budget without meaningful quality gain on routine tasks. For offline reasoning-heavy roles (glossary extraction, cluster labeling), it can help.

**Toggle:** set `think=False` in the Ollama Python client, or append `/no_think` to the prompt. The default in `tinker/llm.py` reflects the per-role thinking policy in the table above; callers can override.

---

## 5. Disk Footprint

After cleanup of `qwen2.5:7b` and `llama3.1:8b-instruct-q4_K_M`:

```
qwen3-embedding:8b   ~4.7 GB
qwen3:4b             ~2.5 GB
qwen3:14b            ~9 GB
bge-reranker-v2-m3   ~2 GB  (HF cache, not Ollama)
                     ------
                     ~18 GB total
```

---

## 6. Alternatives To Try Later

- `phi-4` (14B): possible upgrade for offline extraction if MMLU advantage materializes on our corpus.
- `qwen3-embedding:4b`: smaller embedder if VRAM contention becomes a problem.
- `bge-m3`: multilingual + long-context embedder, if Qwen3-Embedding has trouble with table-heavy or list-heavy chunks.
- `nomic-embed-text-v1.5`: tiny embedder (~0.3 GB) for a quick baseline.

---

## 7. Open Questions

- Real swap latency between `qwen3-embedding:8b` and `qwen3:14b` on this machine (measure once `tinker/llm.py` exists).
- Whether `qwen3:4b` is reliable enough for 8-way classification with structured JSON output, or whether we need to step up to 7B/8B.
- Whether phi-4's reasoning advantage on benchmarks translates to better glossary / cluster-label quality on rulebook text.
- KV-cache footprint at the context lengths we actually need (32K is plausible for synthesis with 5-20 retrieved chunks).

---

## 8. Update Log

- 2026-05-28: Initial lineup. Removed `qwen2.5:7b` and `llama3.1:8b-instruct-q4_K_M`. Pulled `qwen3:4b` and `qwen3:14b`.
