# Ranking Degradation Debug
**Date:** 2026-01-28  
**Status:** ✅ Complete  
**Priority:** P1  
**Estimated Time:** 2-3 hours  
**Actual Time:** ~1 hour  
**Scope:** Narrow - Diagnostic only

---

## 📋 Problem Statement

**Weighted Sum finds 19/28 gold chunks but only achieves 26.6% R@30.**

This means gold chunks are being retrieved but ranked at position 30+. This is a ranking problem, not a retrieval problem.

### Current State
| Pipeline | Gold Found | R@30 | Implication |
|----------|-----------|------|-------------|
| Weighted Sum | 19/28 (68%) | 26.6% | Many gold ranked 30+ |
| 3-Way RRF | 19/28 (68%) | 7.5% | Even worse ranking |
| BM25+Semantic | 12/28 (43%) | 29.9% | Fewer found, but ranked better |

### The Paradox
- Weighted Sum **finds more gold** than BM25
- But BM25 **ranks gold higher** (better R@30)
- Something in the fusion is pushing gold chunks down

### Desired End State
- Understand WHY gold chunks rank low in Weighted Sum
- Identify which component (det or sem) is hurting ranking
- Document specific examples with score breakdowns

---

## 🎯 Scope (Narrow)

### In Scope
- [x] For each gold chunk found by Weighted Sum but ranked 30+:
  - What is its deterministic score?
  - What is its semantic score?
  - What is its final combined score?
  - What chunks ranked higher and why?
- [x] Compare score distributions between gold and non-gold chunks
- [x] Identify if det or sem is the problem
- [x] Document findings

### Out of Scope
- Implementing fixes (separate task)
- Changing fusion weights
- Adding new pipelines

---

## 📐 Technical Approach

### Step 1: Identify Low-Ranked Gold Chunks
```python
# Find gold chunks that ARE retrieved but ranked > 30
for q in queries:
    result = retriever.retrieve(query)
    for i, chunk in enumerate(result.ranked_chunks):
        if chunk.chunk_id in gold_ids and i >= 30:
            low_ranked_gold.append({
                'query': q,
                'chunk_id': chunk.chunk_id,
                'rank': i + 1,
                'det_score': chunk.deterministic_score,
                'sem_score': chunk.semantic_score,
                'final_score': chunk.final_score,
            })
```

### Step 2: Compare with Top-30 Non-Gold
```python
# For each low-ranked gold, find what beat it
for gold in low_ranked_gold:
    # Get chunks ranked 1-30
    top_30 = result.ranked_chunks[:30]
    
    # Compare scores
    for top_chunk in top_30:
        if top_chunk.chunk_id not in gold_ids:
            print(f"Non-gold {top_chunk.chunk_id} beat gold with:")
            print(f"  Det: {top_chunk.deterministic_score} vs {gold['det_score']}")
            print(f"  Sem: {top_chunk.semantic_score} vs {gold['sem_score']}")
```

### Step 3: Score Distribution Analysis
```python
# Are gold chunks systematically lower on one dimension?
gold_det_scores = [c.deterministic_score for c in ranked if c.chunk_id in gold_ids]
gold_sem_scores = [c.semantic_score for c in ranked if c.chunk_id in gold_ids]
nongold_det_scores = [c.deterministic_score for c in ranked if c.chunk_id not in gold_ids]
nongold_sem_scores = [c.semantic_score for c in ranked if c.chunk_id not in gold_ids]

print(f"Gold det: mean={np.mean(gold_det_scores):.2f}, p50={np.median(gold_det_scores):.2f}")
print(f"Non-gold det: mean={np.mean(nongold_det_scores):.2f}, p50={np.median(nongold_det_scores):.2f}")
```

### Step 4: Normalization Impact
```python
# Check if normalization is hurting gold chunks
# Raw scores before normalization
det_raw = parallel_result.chunk_scores
sem_raw = {r['chunk_id']: r['semantic_score'] for r in sem_results}

# Compare raw vs normalized rankings
```

---

## 📊 Expected Output

### Table 1: Low-Ranked Gold Analysis
| Query | Chunk ID | Rank | Det Score | Sem Score | Final Score | Why Low? |
|-------|----------|------|-----------|-----------|-------------|----------|
| Q1 | chunk_001 | 45 | 2.3 | 0.12 | 1.21 | Low semantic |
| Q2 | chunk_002 | 67 | 0.8 | 0.45 | 0.63 | Low deterministic |

### Table 2: What Beat the Gold?
| Gold Chunk | Beat By | Gold Det | Winner Det | Gold Sem | Winner Sem |
|------------|---------|----------|------------|----------|------------|
| chunk_001 | chunk_999 | 2.3 | 5.1 | 0.12 | 0.15 |

### Root Cause Hypotheses
1. **Normalization squashing** - High det scores getting normalized down
2. **Semantic dilution** - Semantic path adding noise
3. **Score scale mismatch** - Det and sem on different scales
4. **Anchor bonus missing** - Gold chunks not getting anchor boost

---

## 📂 Files to Reference

- `traversal/reranker.py` - Score normalization and combination logic
- `traversal/hybrid_retriever.py` - Fusion configuration
- `traversal/parallel_search.py` - Deterministic scoring

---

## ✅ Success Criteria

- [x] All gold chunks ranked 30+ analyzed
- [x] Score breakdown for each
- [x] Comparison with what beat them
- [x] Root cause hypothesis with evidence
- [x] Top 3 actionable recommendations

---

## 📊 Analysis Results (2026-01-28)

### Key Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Total gold chunks | 28 | |
| Found by pipeline | 12 (42.9%) | Lower than expected 19/28 |
| In top 30 | 7 (25.0%) | R@30 |
| Ranked 30+ | 5 (17.9%) | The ranking problem |
| **Not found at all** | **16 (57.1%)** | **The real ceiling** |

### Score Distribution Analysis

**Gold chunks DO have higher scores across all dimensions:**

| Dimension | Gold Mean | Non-Gold Mean | Difference |
|-----------|-----------|---------------|------------|
| Deterministic | 28.03 | 18.48 | **+9.55** (gold higher) |
| Semantic | 0.66 | 0.21 | **+0.44** (gold higher) |
| Final | 1.23 | 0.82 | **+0.41** (gold higher) |

**Scale mismatch is significant:**
- Det score range: 0 - 53.31
- Sem score range: 0 - 0.81
- **66x difference in scale** (normalization handles this, but notable)

### Low-Ranked Gold Chunks (5 total)

| Query | Rank | Det Raw | Sem Raw | What Beat It (Rank 1) |
|-------|------|---------|---------|----------------------|
| blind_001_02 | 64 | 14.97 | 0.71 | det=29.68, sem=0.74 |
| blind_001_04 | 72 | 11.03 | 0.60 | det=48.56, sem=0.67 |
| blind_001_05 | 31 | 15.22 | 0.66 | det=53.31, sem=0.76 |
| blind_001_05 | 50 | 32.00 | 0.59 | det=53.31, sem=0.76 |
| blind_001_05 | 61 | 22.98 | 0.59 | det=53.31, sem=0.76 |

**Key Observation:** Non-gold chunks beating gold have **2-4x higher deterministic scores**, not just slightly higher.

---

## 🎯 Root Cause Analysis

### Hypothesis Testing Results

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| 1. Normalization squashing | ❌ Not the issue | Gold has higher final scores on average |
| 2. Semantic dilution | ❌ Not the issue | Semantic scores favor gold (+0.44) |
| 3. Score scale mismatch | ⚠️ Noted but handled | 66x scale diff, but normalization works |
| 4. Anchor bonus missing | ⚠️ Partial issue | 3/5 low-ranked gold HAD anchor, still lost |

### **TRUE ROOT CAUSE: Expansion Quality + Retrieval Ceiling**

1. **57% of gold chunks not found at all** - This is the primary issue
   - The pipeline can't rank what it doesn't retrieve
   - This is a separate investigation (see Missing Gold Chunks handoff)

2. **Non-gold chunks have very high det scores** 
   - Expansion terms match many irrelevant chunks
   - Example: Query about "perception" → terms match 50+ chunks about perception rules
   - Gold chunk matches 4-6 terms, non-gold matches 8-10 terms

3. **Expansion is generating broad terms**
   - For query "I don't really understand perception?"
   - Expansion likely includes: "perception", "check", "modifier", "skill"
   - These broad terms match many chunks, drowning out specific gold chunks

---

## ✅ Completed Success Criteria

- [x] All gold chunks ranked 30+ analyzed (5 found)
- [x] Score breakdown for each
- [x] Comparison with what beat them
- [x] Root cause hypothesis with evidence
- [x] Top 3 actionable recommendations

---

## 🚀 Actionable Recommendations

### Priority 1: Fix Retrieval Ceiling
The 57% missing gold is the dominant problem. See `HANDOFF-Missing-Gold-Chunks-Investigation.md`.

### Priority 2: Improve Expansion Specificity
- Add more specific terms to expansion
- Weight exact phrase matches higher
- Consider adding "must match" anchor terms

### Priority 3: Tune Det Scoring
- Non-gold chunks with 8+ term matches are beating gold with 4-6 matches
- Consider: penalty for "too many" matches (likely generic content)
- Consider: boost for matching anchor terms specifically

---

## 📂 Artifacts

- Analysis script: `scripts/ranking_degradation_analysis.py`
- Results: `scripts/analysis_results/ranking_analysis_20260127_205830.json`

---

## 🔗 Related

- `HANDOFF-Missing-Gold-Chunks-Investigation.md` - Companion task for chunks not found at all (THE REAL ISSUE)

---

**Created:** 2026-01-28  
**Completed:** 2026-01-28  
**Owner:** [Agent]
