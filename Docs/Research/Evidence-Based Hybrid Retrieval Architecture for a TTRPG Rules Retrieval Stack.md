# Evidence-Based Hybrid Retrieval Architecture for a TTRPG Rules Retrieval Stack

## Executive summary

Hybrid retrieval (dense + lexical) is not guaranteed to raise MRR/Hit@10 in every benchmark, even when it is “working,” because adding a second candidate source often increases recall at the expense of rank purity at small cutoffs. The right expectation is: **hybrid should increase (or at least not materially decrease) candidate coverage** (“gold-in-candidates,” recall@K at a sufficiently large K), and it should be **stable and diagnosable** under wiring audits. Large drops in gold-in-candidates when moving from dense-only to hybrid are more consistent with **budgeting, truncation timing, canonical-ID mismatches, or dedupe bugs** than with an inherent “hybrid is worse” truth.

A high-quality hybrid system for rulebooks should treat hybrid as a **candidate-generation union problem first**, and as a **fusion/scoring problem second**. Concretely: retrieve a healthy number of candidates from each retriever (dense Ku, lexical Ks), take a union **before** dedupe and truncation, map everything to canonical IDs, dedupe deterministically with clear precedence rules, then fuse/rerank. This mirrors standard IR fusion framing (metasearch/data fusion) where the key challenge is combining heterogeneous evidence in a stable way. citeturn8view6turn10view4turn6search6

For fusion, **rank-based methods** like Reciprocal Rank Fusion (RRF) are robust defaults when score scales differ, but RRF is parameter-sensitive in practice and doesn’t uniformly dominate across domains. citeturn8view6turn9view0turn10view3 Evidence suggests that **a convex combination of scores** (with appropriate normalization/calibration) can outperform RRF in-domain and out-of-domain, and can be tuned with relatively few labels. citeturn9view0turn10view1turn10view4

Recommended starting defaults (production-oriented, easy to debug):

- **Candidate budgets**: `Kfinal=20` (evaluation) / `Kfinal=50` (RAG candidate handoff), `Ku=100`, `Ks=100`, `headroom_factor≈4–5×` (i.e., union size typically 150–200 after dedupe). Rationale: headroom reduces “gold_not_in_candidates” failures and makes fusion non-fragile to list noise; multi-stage ranking is a standard pattern. citeturn10view2turn10view1  
- **Fusion**: Default to **RRF** for immediate robustness; add an optional **convex-combination scorer** that can be tuned per corpus. citeturn8view6turn9view0turn10view1  
- **Embedding inference**: Run **two tracks** per model: (1) your standardized recipe, (2) the model’s recommended recipe; log all provenance (pooling, normalization, prefixes, max length, revision pins). Vendor docs show that inference “recipes” are part of the product surface (pooling + normalization + prefixes can be decisive). citeturn12view0turn13view2turn11view0turn16view2

The rest of this report gives a rigorous reference design, invariants to assert, failure-mode tests, and a concrete experiment rollout tuned for your environment (RTX 4080).

## Hybrid design goals and decision criteria

A TTRPG retrieval stack is “document-structured, clause-dense, and ambiguity-prone.” Hybrid retrieval should be judged on **evidence-oriented** criteria, not just a single leaderboard metric. The decision goal is to maximize *useful* evidence surfaced to downstream reasoning (reranker, answer synthesis), under latency/cost constraints, and without destabilizing ranking.

### Quality criteria

**Candidate coverage (recall-first)**  
For RAG, the dominant failure to eliminate is “the right rule text never makes it into candidates.” This is best tracked by:

- **Gold-in-candidates** at a sufficiently large K (e.g., 50–200).
- **Recall@K** at K that matches your downstream rerank/LLM context window, not only @10.  

This aligns with the general role of candidate retrieval in retrieval systems: dense embeddings map text to a shared space for ANN search, while lexical models ensure exact/rare-term coverage. citeturn14view0turn8view7

**Rank quality at shipping cutoffs (precision-first)**  
Once gold is in candidates, rank quality matters:

- MRR / nDCG@10 and a “first-gold-rank” distribution.
- Rank stability: how often gold swings wildly when you change model or fusion.

**Hybrid does not always improve @10**  
Hybrid can improve recall while slightly hurting MRR@10 if lexical injects distractors near the top. This is a known practical point in hybrid ranking: effectiveness depends on dataset, strategies, and fusion type; there is no universal “silver bullet.” citeturn10view1turn9view0

### Operational criteria

**Latency and cost**  
- Dense retrieval latency: embedding query + ANN search.
- Lexical latency: BM25 scoring (often fast) but can expand candidate set.
- Fusion/rerank latency: global normalization or cross-corpus feature computation can be expensive, especially if you need global score distributions. citeturn10view1turn10view2

**Simplicity and auditability**  
Given your current “hybrid feels flat or worse” observations, auditability is a first-class requirement. Hybrid must support per-query tracing and invariant checks.

## Detailed wiring patterns for high-quality hybrid

The central architectural rule for high-quality hybrid is:

> **Union before dedupe, dedupe before truncation, canonicalize IDs before evaluation.**

This is both an engineering best practice and the cleanest way to prevent “gold disappears” bugs.

### Reference flow with explicit stages

```mermaid
flowchart TD
  Q[Query text] --> QT[Query transform & tokenize<br/>(lowercase? punctuation?)]
  QT --> DENSE[Dense retriever<br/>embed(query)->ANN top Ku]
  QT --> LEX[Lexical retriever<br/>BM25 top Ks]

  DENSE --> U[Union candidates<br/>(before dedupe)]
  LEX --> U

  U --> CANON[Canonical ID mapping<br/>raw_id -> canonical_evidence_unit_id]
  CANON --> DEDUPE[Dedupe + precedence rules<br/>deterministic tie-breaks]
  DEDUPE --> PROV[Attach provenance<br/>sources + ranks + scores + reasons]

  PROV --> FUSE[Fusion / scoring<br/>RRF or score fusion]
  FUSE --> TOPK[Truncate to Kfinal]
  TOPK --> OUT[Candidates + features to reranker/LLM]
```

### Candidate provenance tracking is not optional

Every candidate should carry:

- `candidate_id` (raw retriever ID)
- `canonical_id` (your evaluation/serving identity)
- `source`: `{dense, bm25}` (possibly both)
- `dense_rank`, `dense_score` (if present)
- `bm25_rank`, `bm25_score` (if present)
- `dedupe_reason` (kept/dropped; replaced-by; merged-into)
- `final_rank`, `final_score`, `fusion_reason`

This mirrors classic IR fusion thinking: you are combining “evidence” from multiple systems; you must keep the evidence lineage to debug why a document rose or fell. citeturn10view4turn8view6

### Canonical ID mapping and dedupe strategies

Hybrid systems fail in practice when two retrievers disagree about “what the unit is.” In your setting, this is especially plausible if:

- dense indexes EvidenceUnits (fine-grained),
- BM25 indexes larger merged windows or clause families,
- or you have aliasing due to merges/rechunking.

Recommended approach:

1. **Choose a single canonical unit for evaluation and serving** (typically your EvidenceUnit ID).
2. Require both retrievers to emit either:
   - canonical IDs directly, or  
   - retriever-native IDs that can be deterministically mapped to canonical IDs.

3. Dedupe operates only after canonicalization.

Dedupe precedence rules (deterministic defaults):

- If two candidates map to the same canonical ID, prefer the one with **more provenance** (present in both lists) over single-source.
- If tie, prefer the one with better “best rank” (min(dense_rank, bm25_rank)).
- If tie, prefer dense over BM25 for semantic stability at top positions (optional; depends on benchmarks); document and test.

## Budget strategies with recommended defaults

Budgeting is often the hidden reason hybrid “does nothing” or regresses: if you retrieve too few candidates from one side, hybrid cannot help (or can actively harm) because it becomes “BM25 with a tiny dense garnish.”

### Why headroom matters

Multi-stage ranking patterns commonly retrieve more than the final cutoff and then rerank/truncate. This is necessary when downstream scoring (fusion, rerank) needs a richer candidate set. Systems like Vespa explicitly treat rerank as a later phase with a rerank-count (headroom). citeturn10view1turn10view2

### Recommended starting defaults

I recommend you standardize on two Kfinal values:

- **Kfinal_eval = 20** (if your benchmark emphasizes @10/@20).
- **Kfinal_ship = 50** (typical RAG candidate handoff; adjust based on context window and reranker capacity).

Then choose budgets with a headroom factor of 4–5×:

- `Ku = 100` (dense)
- `Ks = 100` (BM25)
- Expect `|union_after_dedupe| ≈ 150–200` (varies with overlap)

If you later add a cross-encoder reranker, you can cap rerank-count to 50–100 to control cost.

### Adaptive budgets and dynamic allocation

Static Ku/Ks is fine to start, but rulebooks are heterogeneous: some queries are rare-term (“grenade”, “encumbrance”) and benefit from lexical; others are conceptual (“what happens when surprised”) and benefit from dense. Hybrid can become more robust by allocating budgets per query:

**Heuristic signals (cheap, effective):**
- OOV/rare-token ratio (based on corpus DF): high → increase Ks.
- Query length and structure:
  - very short queries (1–3 tokens) → boost lexical + expand Ku (short queries are ambiguous).
  - long natural language questions → boost dense and allow more Ku.
- Presence of “rules jargon tokens” (domain dictionary): boost lexical because exact matches often matter.

**Policy sketch:**
- Start with Ku=80, Ks=80.
- If rare-token ratio > threshold → Ks=150, Ku=80.
- If query length <= 3 → Ku=150, Ks=150.
- If query contains numbers/tables references (“Table”, “DC 15”, “p. 123”) → Ks=200.

This is consistent with the general idea in fusion work that improvement depends on query/system characteristics and that no single fusion mode dominates in all cases. citeturn6search18turn10view1turn9view0

### Budget settings comparison table

| Budget mode | Expected retrieval impact | Cost + risk profile |
|---|---|---|
| Minimal union (`Ku=Kfinal`, `Ks=Kfinal`) | Often **no recall gain**, fragile; can lose gold if truncation/dedupe misfires | Cheapest; highest risk of “hybrid regresses” |
| Headroom default (`Ku=100`, `Ks=100`, `Kfinal=20/50`) | Best baseline; improves gold-in-candidates; enables fusion to matter | Moderate compute; stable; easiest to debug |
| Recall-first (`Ku=200`, `Ks=200`, `Kfinal=50`) | Max coverage; good for diagnosing whether hybrid can help at all | Higher cost; may lower MRR@10 without reranker |
| Adaptive budgets (rule-based) | Better tail recall and less noise; more stable across corpora | More complexity; requires good logging/tests |

## Fusion algorithms and score calibration

You should treat fusion as its own model selection problem. Dense and BM25 produce scores with different distributions; naïve score addition can be dominated by BM25 because BM25 scores are not naturally bounded like cosine. citeturn10view1turn8view7

### Rank-based fusion: Reciprocal Rank Fusion

RRF combines ranked lists by summing reciprocal ranks with a constant *k*:

- RRF was shown (in TREC-style experiments) to outperform the constituent systems and Condorcet-Fuse in the original SIGIR work. citeturn8view6  
- Implementations commonly use `1/(k+rank)` and sum across sources. citeturn10view2turn8view6

Pros:
- robust to score scale mismatch and outliers (only uses ranks). citeturn10view3
- no calibration data required.

Cons:
- can be parameter sensitive; evidence suggests RRF is not universally dominant. citeturn9view0  
- ignores “score margin” (rank 1 barely beating rank 2 is treated like a large win).

Recommended default:
- RRF with `k ≈ 60` (common default; note how it compresses rank contributions). citeturn10view2turn8view6  
- Use RRF primarily when you don’t trust score distributions or you need stable behavior across corpora.

### Score-based fusion: convex combination (CC) with normalization

A convex combination fuses normalized scores:

\[
S(d) = \lambda \cdot \hat{s}_{dense}(d) + (1-\lambda)\cdot \hat{s}_{bm25}(d)
\]

What the literature says:
- Bruch et al. analyze CC vs RRF and report CC can outperform RRF in-domain and out-of-domain, and that tuning CC can be sample efficient. citeturn9view0  
- Classic metasearch/data fusion literature emphasizes score normalization as a prerequisite for score-based combination rules like CombSUM/CombMNZ. citeturn10view4turn6search6

Normalization options (practical):
- **Min-max / zero-one**: maps min→0, max→1 (sensitive to outliers).
- **Sum normalization**: maps sum(scores)→1 (more outlier-insensitive under truncation). citeturn10view4
- **ZMUV**: shift/scale to zero mean, unit variance; requires careful handling for unretrieved docs. citeturn10view4
- **Atan / sigmoid squashing**: common for BM25-like unbounded scores; used in practical hybrid tutorials to prevent BM25 dominance. citeturn10view1

Recommended approach:
- Start with **atan normalization for BM25** + cosine for dense (bounded), then tune λ on a small labeled set. This matches practical guidance that raw BM25 can dominate without normalization. citeturn10view1turn10view4

### Learned fusion / learned ranker

If you have labeled data (your benchmark gold), you can learn fusion as:
- a simple logistic/linear model over features (dense score, BM25 score, overlap flags, length signals), or
- a learning-to-rank model like LambdaMART. citeturn17view4

LambdaMART is a standard boosted-tree LTR method used for ranking problems and can optimize IR metrics like NDCG directly via lambda gradients. citeturn17view4

Recommended progression:
1. Ship RRF (robust + no training).
2. Add CC with normalization and tune λ per corpus (fast).
3. If stable and worth it, add learned ranker.

### Fusion methods comparison table

| Fusion method | Expected quality behavior | Complexity + cost profile |
|---|---|---|
| RRF | Stable, robust to scale mismatch; may not maximize in-domain ranking | Low complexity; minimal tuning; parameter *k* still matters citeturn8view6turn9view0 |
| CC (normalized score sum) | Often stronger in-domain; tunable; can generalize | Medium complexity; requires normalization + λ tuning citeturn9view0turn10view4 |
| Learned ranker (LambdaMART / logistic) | Best ceiling if features + labels are good; can enforce domain preferences | Higher complexity + maintenance; needs training hygiene citeturn17view4 |

## Embedding model inference recipes and integration patterns

You asked for both (a) standardized recipe and (b) recommended per model. That’s the right way to do this, because vendor docs explicitly encode assumptions about pooling, normalization, and task prefixes.

### Unified integration principle

For every model in your bakeoff matrix, your embedding runner should emit:

- `embedding_vector` (+ dtype/quantization)
- `pooling` and whether mask-aware
- `normalize` step (on/off, L2)
- `similarity_metric` intended (cosine/dot/L2)
- `max_seq_len` and truncation policy
- `prefix/prompt` policy (query vs document)
- `model revision` pin for reproducibility

This is essential because the same base weights can behave very differently under different pooling/prompts. citeturn12view0turn13view2turn12view3

### all-mpnet-base-v2

**Recommended inference (per model card / config):**
- Mean pooling over token embeddings (mask-aware) + L2 normalize; then cosine similarity. citeturn12view0  
- Max sequence length is effectively 384 (recommended; model includes a Normalize layer in common packaging). citeturn8view0turn12view2

**Standardized recipe compatibility:**
- If your standard is “mean pool + L2 norm,” mpnet is a natural fit.

### nomic-embed-text-v2

You benchmarked `nomic-embed-text-v2`—the most explicit vendor guidance you can rely on is from the v2 family model cards and docs.

**Recommended inference highlights:**
- **Task prefixes are required** when not using the Nomic API task fields:  
  - queries: `search_query: `  
  - docs: `search_document: ` citeturn8view2turn13view2turn13view0
- Mean pooling + L2 normalization is shown in the model card example. citeturn13view2
- Max input length: 512 tokens (per model card best practices + architecture section). citeturn8view2turn13view2
- Matryoshka/truncation: the v2 family supports truncating embedding dims (e.g., 256) as a storage/throughput trade. citeturn13view2

**Standardized recipe compatibility:**
- Works well if your standard supports query/doc prefixes and normalization. Without prefixes, you may be benchmarking the wrong behavior. citeturn13view0turn13view2

### bge-m3

BGE-M3 is unusual because it’s explicitly “multi-function” (dense + sparse + multi-vector). citeturn11view0turn15view1 If you’re benchmarking it purely as a dense embedder, you should use the dense mode as documented.

**Recommended dense inference:**
- Dense embedding uses the **normalized [CLS] hidden state** (`norm(H[0])`). citeturn11view0
- Max position / long input: extended to **8192 tokens**; documentation mentions MCLS to improve long-text ability. citeturn11view0turn17view7
- “No instruction prefix needed” for queries in BGE-M3 vs earlier BGE models. citeturn11view1
- The FlagEmbedding example notes `use_fp16=True` speeds up with slight degradation—so for “highest quality,” prefer fp32; for throughput, fp16. citeturn11view1

**Hybrid-native possibility:**
- The BGE-M3 paper describes a hybrid process where candidates can be retrieved by each method and then re-ranked based on an integrated score, while noting multi-vector is expensive. This is directly aligned with your “dual list” architecture idea. citeturn15view1

**Standardized recipe caution:**
- If your standard recipe forces mean pooling, you may undercut BGE-M3 dense mode (because its recommended dense representation is normalized CLS). citeturn11view0turn12view0

### pplx-embed-v1-0.6B

pplx-embed is explicitly designed around mean pooling and quantization-aware output.

**Recommended inference:**
- Mean pooling is core to the design; the paper proposes mean pooling combined with INT8 quantization (tanh then rounding). citeturn16view2turn14view0
- Quantized embeddings are compared using **cosine similarity**. citeturn16view2turn8view4
- The model family is **not instruction-tuned**, so no instruction prefix is required. citeturn14view0turn8view4
- Hugging Face TEI path: only INT8 embeddings available via TEI at present; use cosine with unnormalized INT8. citeturn8view3turn17view6
- Perplexity docs reiterate embeddings are unnormalized; compare INT8 via cosine, binary via Hamming. citeturn11view4turn11view5

**Contextual variant integration (conditional):**
- Contextual embeddings require nested chunk arrays per document and **chunk order must match source order** for best results. citeturn11view5turn8view4  
This maps cleanly onto your `structural_path` grouping if you treat each structural group as a “document.”

## Diagnostics, invariants, failure-mode tests, and an experiment rollout

### Wiring invariants your agent should assert

These invariants are designed to catch the exact class of “hybrid is flat or worse” bugs that come from wiring, not from retrieval theory.

**Corpus identity invariants**
- Dense index and BM25 index must be built over the **same canonical corpus units** (same canonical IDs, same text field, same chunking profile).
- Assert: the set of canonical IDs in both indices is identical (or explicitly explain deltas).

**Candidate monotonicity invariants**
- For each query:
  - `dense_top_Ku ⊆ union_before_dedupe`
  - `bm25_top_Ks ⊆ union_before_dedupe`
  - `union_after_dedupe ⊆ union_before_dedupe`

If any fail: bug in union/dedupe/canonicalization.

**Union coverage invariant (most important)**
- If dense-only retrieves gold within its top Ku, then gold must appear in `union_before_dedupe` in hybrid (unless canonicalization differs). If it doesn’t: you have an ID mapping or truncation bug.

### Embedding health checks (fast, high signal)

For each model run:
- No NaNs / infs.
- Norm statistics: mean/median norms stable across batches.
- Dimensionality matches expectation (mpnet 768, nomic 768, bge-m3 dense 1024, pplx 1024). citeturn8view0turn13view2turn11view0turn8view1
- Prefix enforcement tests for Nomic (query/document encode differences should be detectable). citeturn13view0turn13view2

### Per-query tracing schema

Make tracing a first-class artifact (`per_query_trace.jsonl`). Minimum record:

```json
{
  "query_id": "...",
  "query_text": "...",
  "gold_canonical_ids": ["..."],
  "dense": {"Ku": 100, "results": [{"id": "...", "canonical_id": "...", "rank": 1, "score": 0.42}]},
  "bm25": {"Ks": 100, "results": [{"id": "...", "canonical_id": "...", "rank": 1, "score": 17.3}]},
  "union_before_dedupe": ["..."],
  "union_after_dedupe": ["..."],
  "fusion": {"method": "rrf", "params": {"k": 60}},
  "final_topK": [{"canonical_id": "...", "final_rank": 1, "provenance": ["dense","bm25"]}],
  "gold_presence": {
    "dense": true,
    "bm25": false,
    "union_before_dedupe": true,
    "final_topK": false
  }
}
```

### Failure-mode analysis with targeted tests

**Oracle union test (truth serum)**
- Retrieve `dense_top_200` and `bm25_top_200`.
- Compute oracle union coverage: is gold present anywhere in union?
- If yes but hybrid@K misses: fusion/truncation/dedupe bug.
- If no: neither retriever is finding it; embedding/chunking/benchmark issue.

**Headroom experiment**
- Fix wiring; vary budgets:
  - (Ku,Ks) = (Kfinal,Kfinal), (50,50), (100,100), (200,200)
- Plot gold-in-candidates@K and MRR@10.
- Expectation: coverage should be non-decreasing with headroom if wiring is correct.

**ID-canonicalization check**
- For a failing query, find whether the gold **text span** appears under a different ID in hybrid output.
- If yes: canonicalization mismatch, not retrieval failure.

### Fusion-specific tests

Because BM25 scores are unbounded, naïve score addition can cause BM25 to dominate dense similarity. citeturn10view1turn8view7 Run:

1. **RRF (k=60)** baseline. citeturn10view2turn8view6
2. **CC with BM25 normalization**:
   - atan(BM25) or ZMUV/Sum normalization inspired by metasearch literature. citeturn10view1turn10view4
3. Small λ sweep (e.g., 0.1–0.9), pick λ per corpus.

This follows evidence that CC can outperform RRF and is tunable with few labels. citeturn9view0

### Experiment rollout timeline

```mermaid
flowchart TD
  A[Smoke tests<br/>(5 queries per corpus)] --> B[Instrumentation on<br/>per-query tracing + invariants]
  B --> C[Headroom sweep<br/>Ku/Ks grid]
  C --> D[Fusion bakeoff<br/>RRF vs CC(normalized)]
  D --> E[Model recipe bakeoff<br/>standardized vs recommended]
  E --> F[Optional learned fusion<br/>if CC wins and labels sufficient]
  F --> G[Contextual embeddings trial<br/>pplx-context or BGE multi-function<br/>(only if signal)]
```

### Decision thresholds aligned to acceptance rules

Tie your “adopt/reject” to a small set of thresholds (you can tighten later):

- **No-go**: any statistically meaningful drop in gold-in-candidates at K that matches your rerank stage (e.g., @50) without a compensating gain elsewhere.
- **Adopt** hybrid wiring change if:
  - gold-in-candidates@50 improves (or returns to dense-only baseline) **and**
  - MRR/nDCG@10 does not regress beyond an agreed margin (e.g., ≤1–2 points absolute), unless your product prioritizes recall.  
- **Adopt** CC fusion if it beats RRF on both corpora or if it materially improves the harder corpus without introducing Tier-1 regressions.

## Implementation checklist for RTX 4080 and reproducibility

### Reproducibility and security pinning

Because some models require `trust_remote_code`, you should pin revisions to a commit hash or tag and log them:

- Hugging Face Hub supports downloading/pinning by `revision` (branch/tag/commit). citeturn17view0
- Hugging Face warns that `trust_remote_code=True` executes third-party code and recommends pinning to a specific commit for reproducibility and security. citeturn17view1turn12view3

Minimum provenance fields:
- model_id, revision/commit, tokenizer revision
- library versions (`transformers`, `sentence-transformers`, `torch`, `FlagEmbedding`)
- pooling, normalization, prefixes, max_seq_len, truncation policy
- dtype (fp16/fp32) and device

### GPU embedding environment notes

If you want to serve embeddings via TEI:
- TEI supports an explicit `--revision` flag and can run on GPU; GPU support requires compatible NVIDIA drivers (CUDA 12.2+ in their docs) and NVIDIA Container Toolkit. citeturn17view2turn17view3  
- For mpnet, TEI example uses mean pooling and float16. citeturn12view0  
- For pplx, TEI notes only INT8 embeddings are available and should be compared with cosine similarity. citeturn8view3turn17view6

### Prioritized follow-up experiments

1. **Hybrid wiring audit + invariant enforcement** (highest priority): before you debate model quality, prove hybrid is not dropping gold via ID/dedupe/budget issues.
2. **Headroom sweep** on both corpora: verify hybrid recall monotonicity with Ku/Ks.
3. **Fusion bakeoff**: RRF vs CC(normalized) + λ tuning.
4. **Recipe bakeoff per model**: standardized vs recommended, because vendor-required prefixes/pooling can be decisive (especially Nomic prefixes and BGE CLS pooling). citeturn13view2turn11view0turn12view0
5. **Context-aware chunk embeddings**:
   - pplx contextual embeddings with structural grouping and ordered chunks (only after wiring is validated). citeturn11view5turn14view0
6. If still flat: examine **chunking policy and unit granularity**, because hybrid cannot recover gold that is split away from identifying context.

