# Retrieval Lab Report: starfinder_hybrid_dual_list_fusion

**Experiment ID:** `starfinder_hybrid_dual_list_fusion_20260212_151943`
**Created:** 2026-02-12T15:34:16.029379+00:00

---

## 1. Experiment Summary

- **Substrate:** /media/drakosfire/Projects/DungeonOverMind/RulesIngestion/out/StarFinderPlayerCore
- **Document ID:** StarFinderPlayerCore
- **Substrate version:** v1
- **Embedding run_id:** retrieval_lab_StarFinderPlayerCore_v1
- **Models:** all-mpnet-base-v2
- **Top-k values:** [1, 3, 5, 10, 20]
- **Retrieval mode:** hybrid
- **Corpus unit count:** 13162
- **Corpus page count:** 36

### Grounding Summary

- **Total queries:** 50
- **Grounded:** 47
- **Ungrounded:** 3
- **Method:** page_anchored

---

## 2. Model Comparison

| Model | MRR | Gold-in-Cand | Gold-in-Cand(True) | FSH@10 | R@1 | H@1 | R@3 | H@3 | R@5 | H@5 | R@10 | H@10 | R@20 | H@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all-mpnet-base-v2 | 0.4539 | 0.7400 | 0.7872 | 0.4468 | 0.2200 | 0.3400 | 0.3490 | 0.5400 | 0.4773 | 0.6600 | 0.5473 | 0.7000 | 0.6080 | 0.7400 |

---

## 3. Per-Model Detail

### all-mpnet-base-v2

- **MRR:** 0.4539
- **Gold-in-candidates:** 0.7400
- **Gold-in-candidates (true ceiling):** 0.7872
- **Grounding coverage:** 0.9400
- **Recall@k:** {"1": 0.22, "3": 0.349, "5": 0.47733333333333333, "10": 0.5473333333333333, "20": 0.608}
- **Hit@k:** {"1": 0.34, "3": 0.54, "5": 0.66, "10": 0.7, "20": 0.74}
- **Full-set hit@k:** {"1": 0.1276595744680851, "3": 0.23404255319148937, "5": 0.3617021276595745, "10": 0.44680851063829785, "20": 0.48936170212765956}
- **Answer similarity@k:** {"1": 0.61, "3": 0.5361, "5": 0.5057, "10": 0.4479, "20": 0.3742}
- **Failure counts:** {"hit": 37, "retrieval_miss": 10, "grounding_failure": 3}
- **Failure buckets:** {"success": 37, "gold_not_in_candidates": 10, "no_gold_defined": 3}
- **Embedding time (s):** 214.81
- **Scoring time (s):** 0.06

---

## 4. Per-Suite Breakdown

| Suite | MRR | R@5 | H@5 | R@10 | H@10 | FSH@10 | N |
|-------|-----|-----|-----|------|------|--------|---|
| default | 0.4539 | 0.4773 | 0.6600 | 0.5473 | 0.7000 | 0.4468 | 50 |

---

## 5. Per-Tier Breakdown (R8 Gold Taxonomy)

| Tier | MRR | R@5 | H@5 | R@10 | H@10 | FSH@10 | N |
|------|-----|-----|-----|------|------|--------|---|
| T1 | 0.4067 | 0.2200 | 0.6000 | 0.2533 | 0.6000 | 0.0000 | 10 |
| T2 | 0.4803 | 0.5303 | 0.7273 | 0.6136 | 0.7273 | 0.5000 | 22 |
| T3 | 0.4480 | 0.5556 | 0.6111 | 0.6296 | 0.7222 | 0.6667 | 18 |

---

## 6. Failure Analysis

| Model | hit | retrieval_miss | rank_miss | grounding_failure |
|-------|-----|----------------|-----------|-------------------|
| all-mpnet-base-v2 | 37 | 10 | 0 | 3 |

### Failure Buckets

| Model | no_gold_defined | gold_not_in_candidates | gold_in_candidates_but_low_rank | grounding_or_answer_failure_after_retrieval |
|-------|------------------|------------------------|----------------------------------|----------------------------------------------|
| all-mpnet-base-v2 | 3 | 10 | 0 | 0 |

---

## 7. Gold Grounding Audit

Sample (first 10): query_id, method, count.
- `blind_001_01`: prefilled, count=3
- `blind_001_02`: prefilled, count=2
- `blind_001_03`: prefilled, count=3
- `blind_001_04`: prefilled, count=2
- `blind_001_05`: prefilled, count=5
- `blind_001_06`: prefilled, count=3
- `blind_001_07`: prefilled, count=3
- `blind_001_08`: prefilled, count=3
- `blind_001_09`: prefilled, count=2
- `blind_001_10`: prefilled, count=4
- ... and 40 more (see grounding_audit.json).

### Query rubric notes

- **blind_001_03** refusal_acceptable — Refusal acceptable if no rule exists for powering devices.
- **batch_006_03** accept_qualified_answer — Accept qualified answers; rule is default expectation, not absolute.


## Glossary of Metrics

| Metric | Formula / Definition | Interpretation |
|--------|----------------------|----------------|
| **Recall@k** | (Number of gold units found in top-k) / (Total gold units per query), averaged over queries | Fraction of relevant evidence discoverable in the first k results. Higher is better. |
| **Hit@k** | Fraction of queries where at least one gold unit appears in top-k | Whether *any* relevant evidence surfaces per question. Simpler than recall. |
| **MRR** | Mean over queries of 1/rank of first gold hit; 0 if no gold in list | How high the first relevant result ranks. 1.0 = gold always at rank 1. |
| **Gold-in-Candidates** | Fraction of queries where any gold unit appears anywhere in the full ranked list | Ceiling check: if gold never appears, retrieval cannot succeed regardless of k. |
| **Gold-in-Candidates (True Ceiling)** | Same as Gold-in-Candidates, but excludes `no_gold_defined` queries from denominator | Better estimate of retriever ceiling after benchmark hygiene separation. |
| **Grounding Coverage** | Fraction of queries where gold grounding found at least one EvidenceUnit | Measures eval set quality (and extraction coverage), not retrieval quality. |
| **Full-Set Hit@k** | Fraction of grounded queries where *all* gold units appear within top-k | Compositional retrieval metric; critical for multi-unit T2/T3 questions. |
| **Answer Similarity@k** | Mean cosine similarity between the query (expected_answer_summary) embedding and the embeddings of the top-k retrieved units | Model-agnostic relevance signal when gold IDs are uncertain (e.g. corpus-wide semantic grounding). |
| **Candidate Set Size** | Total number of EvidenceUnits in the corpus | Context for interpreting recall: larger corpus = harder retrieval problem. |

### Failure Types

| Type | Meaning |
|------|--------|
| **hit** | At least one gold unit appeared within the largest k evaluated. |
| **retrieval_miss** | Gold EvidenceUnit(s) exist but none appear in top-k for any k tested. |
| **rank_miss** | Gold was retrieved but ranked below the maximum k (e.g. beyond top-20). |
| **grounding_failure** | No EvidenceUnit could be mapped as gold for this query (eval set or extraction issue). |

### Failure Buckets (Phase-0 Contract)

| Bucket | Meaning |
|--------|---------|
| **no_gold_defined** | Query has no gold units (`gold_unit_ids` empty): benchmark hygiene/annotation issue. |
| **gold_not_in_candidates** | Gold exists but never appears in ranked list: candidate ceiling failure. |
| **gold_in_candidates_but_low_rank** | Gold appears only below max-k: ranking depth issue. |
| **grounding_or_answer_failure_after_retrieval** | Gold was retrievable but downstream grounding/answer stage failed. |

### When to Worry

- **Low gold-in-candidates**: Either grounding is failing or the corpus does not contain the answer text; fix grounding or add evidence.
- **Low recall@k with high gold-in-candidates**: Retrieval or ranking is the bottleneck; consider better embeddings or hybrid retrieval.
- **Low grounding coverage**: Queries or expected_answer_summary do not align with EvidenceUnit text; review eval set or use semantic grounding.
