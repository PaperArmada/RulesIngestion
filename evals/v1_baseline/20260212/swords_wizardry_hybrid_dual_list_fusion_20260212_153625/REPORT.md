# Retrieval Lab Report: swords_wizardry_hybrid_dual_list_fusion

**Experiment ID:** `swords_wizardry_hybrid_dual_list_fusion_20260212_153625`
**Created:** 2026-02-12T15:38:43.253174+00:00

---

## 1. Experiment Summary

- **Substrate:** /media/drakosfire/Projects/DungeonOverMind/RulesIngestion/out/Swords&Wizardry
- **Document ID:** Swords&Wizardry
- **Substrate version:** v1
- **Embedding run_id:** retrieval_lab_Swords&Wizardry_v1
- **Models:** all-mpnet-base-v2
- **Top-k values:** [1, 3, 5, 10, 20]
- **Retrieval mode:** hybrid
- **Corpus unit count:** 307
- **Corpus page count:** 141

### Grounding Summary

- **Total queries:** 25
- **Grounded:** 25
- **Ungrounded:** 0
- **Method:** page_anchored

---

## 2. Model Comparison

| Model | MRR | Gold-in-Cand | Gold-in-Cand(True) | FSH@10 | R@1 | H@1 | R@3 | H@3 | R@5 | H@5 | R@10 | H@10 | R@20 | H@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all-mpnet-base-v2 | 0.3633 | 0.5200 | 0.5200 | 0.0000 | 0.0800 | 0.2400 | 0.1600 | 0.4800 | 0.1733 | 0.5200 | 0.1733 | 0.5200 | 0.1733 | 0.5200 |

---

## 3. Per-Model Detail

### all-mpnet-base-v2

- **MRR:** 0.3633
- **Gold-in-candidates:** 0.5200
- **Gold-in-candidates (true ceiling):** 0.5200
- **Grounding coverage:** 1.0000
- **Recall@k:** {"1": 0.08, "3": 0.16, "5": 0.1733333333333333, "10": 0.1733333333333333, "20": 0.1733333333333333}
- **Hit@k:** {"1": 0.24, "3": 0.48, "5": 0.52, "10": 0.52, "20": 0.52}
- **Full-set hit@k:** {"1": 0.0, "3": 0.0, "5": 0.0, "10": 0.0, "20": 0.0}
- **Answer similarity@k:** {"1": 0.4451, "3": 0.3957, "5": 0.3735, "10": 0.3259, "20": 0.2661}
- **Failure counts:** {"retrieval_miss": 12, "hit": 13}
- **Failure buckets:** {"gold_not_in_candidates": 12, "success": 13}
- **Embedding time (s):** 65.84
- **Scoring time (s):** 0.01

---

## 4. Per-Suite Breakdown

| Suite | MRR | R@5 | H@5 | R@10 | H@10 | FSH@10 | N |
|-------|-----|-----|-----|------|------|--------|---|
| default | 0.3633 | 0.1733 | 0.5200 | 0.1733 | 0.5200 | 0.0000 | 25 |

---

## 5. Per-Tier Breakdown (R8 Gold Taxonomy)

| Tier | MRR | R@5 | H@5 | R@10 | H@10 | FSH@10 | N |
|------|-----|-----|-----|------|------|--------|---|
| T1 | 0.1759 | 0.1481 | 0.4444 | 0.1481 | 0.4444 | 0.0000 | 9 |
| T2 | 0.3750 | 0.1667 | 0.5000 | 0.1667 | 0.5000 | 0.0000 | 8 |
| T3 | 0.5625 | 0.2083 | 0.6250 | 0.2083 | 0.6250 | 0.0000 | 8 |

---

## 6. Failure Analysis

| Model | hit | retrieval_miss | rank_miss | grounding_failure |
|-------|-----|----------------|-----------|-------------------|
| all-mpnet-base-v2 | 13 | 12 | 0 | 0 |

### Failure Buckets

| Model | no_gold_defined | gold_not_in_candidates | gold_in_candidates_but_low_rank | grounding_or_answer_failure_after_retrieval |
|-------|------------------|------------------------|----------------------------------|----------------------------------------------|
| all-mpnet-base-v2 | 0 | 12 | 0 | 0 |

---

## 7. Gold Grounding Audit

Sample (first 10): query_id, method, count.
- `sw_q01`: prefilled, count=3
- `sw_q02`: prefilled, count=3
- `sw_q03`: prefilled, count=3
- `sw_q04`: prefilled, count=3
- `sw_q05`: prefilled, count=3
- `sw_q06`: prefilled, count=3
- `sw_q07`: prefilled, count=3
- `sw_q08`: prefilled, count=3
- `sw_q09`: prefilled, count=3
- `sw_q10`: prefilled, count=3
- ... and 15 more (see grounding_audit.json).

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
