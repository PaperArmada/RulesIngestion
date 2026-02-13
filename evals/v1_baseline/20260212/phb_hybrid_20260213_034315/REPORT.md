# Retrieval Lab Report: phb_hybrid

**Experiment ID:** `phb_hybrid_20260213_034315`
**Created:** 2026-02-13T03:43:51.474197+00:00

---

## 1. Experiment Summary

- **Substrate:** /media/drakosfire/Projects/DungeonOverMind/RulesIngestion/out/DnD_PHB_5.5
- **Document ID:** DnD_PHB_5.5
- **Substrate version:** v1
- **Embedding run_id:** retrieval_lab_DnD_PHB_5.5_v1
- **Models:** all-mpnet-base-v2
- **Top-k values:** [1, 3, 5, 10, 20]
- **Retrieval mode:** hybrid
- **Corpus unit count:** 6999
- **Corpus page count:** 379

### Grounding Summary

- **Total queries:** 28
- **Grounded:** 26
- **Ungrounded:** 2
- **Method:** page_anchored

---

## 2. Model Comparison

| Model | MRR | Gold-in-Cand | Gold-in-Cand(True) | FSH@10 | R@1 | H@1 | R@3 | H@3 | R@5 | H@5 | R@10 | H@10 | R@20 | H@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all-mpnet-base-v2 | 0.4898 | 0.8571 | 0.9231 | 0.1154 | 0.1232 | 0.3571 | 0.2625 | 0.5357 | 0.3679 | 0.7143 | 0.4357 | 0.7500 | 0.6714 | 0.8571 |

---

## 3. Per-Model Detail

### all-mpnet-base-v2

- **MRR:** 0.4898
- **Gold-in-candidates:** 0.8571
- **Gold-in-candidates (true ceiling):** 0.9231
- **Grounding coverage:** 0.9286
- **Recall@k:** {"1": 0.1232142857142857, "3": 0.2625, "5": 0.3678571428571429, "10": 0.43571428571428567, "20": 0.6714285714285715}
- **Hit@k:** {"1": 0.35714285714285715, "3": 0.5357142857142857, "5": 0.7142857142857143, "10": 0.75, "20": 0.8571428571428571}
- **Full-set hit@k:** {"1": 0.0, "3": 0.038461538461538464, "5": 0.07692307692307693, "10": 0.11538461538461539, "20": 0.46153846153846156}
- **Answer similarity@k:** {"1": 0.5311, "3": 0.463, "5": 0.4407, "10": 0.3884, "20": 0.3508}
- **Failure counts:** {"hit": 24, "grounding_failure": 2, "retrieval_miss": 2}
- **Failure buckets:** {"success": 24, "no_gold_defined": 2, "gold_not_in_candidates": 2}
- **Embedding time (s):** 30.14
- **Scoring time (s):** 0.01

---

## 4. Per-Suite Breakdown

| Suite | MRR | R@5 | H@5 | R@10 | H@10 | FSH@10 | N |
|-------|-----|-----|-----|------|------|--------|---|
| blind | 0.6400 | 0.3700 | 0.8000 | 0.4700 | 0.8000 | 0.1111 | 10 |
| state | 0.4396 | 0.4250 | 0.7500 | 0.4750 | 0.7500 | 0.1250 | 8 |
| grounding | 0.0970 | 0.1250 | 0.2500 | 0.2500 | 0.5000 | 0.0000 | 4 |
| temporal | 0.6667 | 0.6000 | 1.0000 | 0.6000 | 1.0000 | 0.5000 | 2 |
| constraint | 0.7500 | 0.5833 | 1.0000 | 0.5833 | 1.0000 | 0.0000 | 2 |
| conceptual | 0.2885 | 0.1667 | 0.5000 | 0.1667 | 0.5000 | 0.0000 | 2 |

---

## 5. Per-Tier Breakdown (R8 Gold Taxonomy)

| Tier | MRR | R@5 | H@5 | R@10 | H@10 | FSH@10 | N |
|------|-----|-----|-----|------|------|--------|---|
| T1 | 0.6400 | 0.3700 | 0.8000 | 0.4700 | 0.8000 | 0.1111 | 10 |
| T2 | 0.3254 | 0.3250 | 0.5833 | 0.4000 | 0.6667 | 0.0909 | 12 |
| T3 | 0.5684 | 0.4500 | 0.8333 | 0.4500 | 0.8333 | 0.1667 | 6 |

---

## 6. Failure Analysis

| Model | hit | retrieval_miss | rank_miss | grounding_failure |
|-------|-----|----------------|-----------|-------------------|
| all-mpnet-base-v2 | 24 | 2 | 0 | 2 |

### Failure Buckets

| Model | no_gold_defined | gold_not_in_candidates | gold_in_candidates_but_low_rank | grounding_or_answer_failure_after_retrieval |
|-------|------------------|------------------------|----------------------------------|----------------------------------------------|
| all-mpnet-base-v2 | 2 | 2 | 0 | 0 |

---

## 7. Gold Grounding Audit

Sample (first 10): query_id, method, count.
- `dnd5e_blind_001_01`: prefilled, count=3
- `dnd5e_blind_001_02`: prefilled, count=5
- `dnd5e_blind_001_03`: page_anchored_skipped, count=0
- `dnd5e_blind_001_04`: prefilled, count=3
- `dnd5e_blind_001_05`: prefilled, count=2
- `dnd5e_blind_001_06`: prefilled, count=4
- `dnd5e_blind_001_07`: prefilled, count=3
- `dnd5e_blind_001_08`: prefilled, count=3
- `dnd5e_blind_001_09`: prefilled, count=3
- `dnd5e_blind_001_10`: prefilled, count=3
- ... and 18 more (see grounding_audit.json).

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
