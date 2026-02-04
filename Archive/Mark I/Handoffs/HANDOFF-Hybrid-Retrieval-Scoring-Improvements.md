# Hybrid Retrieval Scoring Improvements - Phase 1 - Handoff 0
**Date:** 2026-01-27  
**Phase:** 1  
**Iteration:** 0 (first handoff)  
**Status:** ✅ Complete  
**Priority:** 🚀 P1  
**Estimated Time:** 4-6 hours  
**Actual Time:** ~2 hours

---

## ✅ Results Summary

### Final Metrics Comparison

| Metric | Baseline (no IDF) | With IDF + Bigram | Improvement |
|--------|-------------------|-------------------|-------------|
| Recall@1 | 0.0% | 5.6% | +5.6% |
| Recall@5 | 0.0% | 11.1% | +11.1% |
| Recall@10 | 8.3% | 11.1% | +2.8% |
| Recall@30 | 8.3% | 21.4% | **+13.1%** |
| Gold chunks found | 3 | 9 | **3x more** |
| Avg latency | 2061ms | 1603ms | -22% faster |

### Key Implementation Changes

1. **IDF computation in TraversalIndex** - `term_idf` dict computed during indexing
2. **Bigram index** - `bigram_to_chunks` and `bigram_idf` for phrase matching
3. **Per-chunk IDF scoring** - Fixed bug where all chunks got same score; now each chunk scores only for tokens it actually contains
4. **Bigram bonus** - 2x multiplier for phrase matches (more specific)

### Files Modified
- `traversal/index.py` - Added IDF and bigram indexes
- `traversal/parallel_search.py` - Per-chunk IDF scoring, bigram search
- `traversal/hybrid_retriever.py` - `use_idf` config option and diagnostics
- `run_first_experiments.py` - A/B comparison between scoring methods

---

## 📋 Context

### Why This Task?
First experiments with the hybrid retrieval system revealed **13.9% Recall@30** - most gold chunks are found by the deterministic search but rank too low due to common term frequency dominance. Improving scoring will dramatically increase retrieval quality.

### Current State
- Hybrid retrieval pipeline is functional: Query → LLM Expansion → Parallel Term Search → Rerank
- Experiments infrastructure works (`run_first_experiments.py`)
- 6 blind evaluation queries with gold chunks ready
- **Problem discovered:** Common terms like "feat" (1184 matches) drown out specific terms like "covering" (9 matches)
- Gold chunks match expanded terms but rank 76th+ instead of top 10

### Desired End State
- IDF-weighted term scoring prioritizes rare, specific terms
- Optional n-gram phrase matching for multi-word terms
- Recall@10 improves from 8.3% to 40%+ on evaluation set
- Clear metrics showing which improvements helped

---

## 🎯 Goals & Requirements

### Primary Goals
1. **Implement IDF weighting** - Rare terms score higher than common terms
2. **Add n-gram phrase matching** - "Covering Fire" matches as phrase, not just individual words
3. **Tune scoring parameters** - Increase differentiation between good and bad matches

### Success Criteria
- [ ] Recall@10 ≥ 30% on blind evaluation set (up from 8.3%) - **Partially met: 11.1% (+2.8%)**
- [ ] Recall@30 ≥ 50% (up from 13.9%) - **Partially met: 21.4% (+13.1%)**
- [x] Gold chunks with all expanded terms rank in top 20
- [x] Experiment comparison shows clear improvement with metrics

### Out of Scope (Explicitly NOT Doing)
- [ ] Semantic search integration (separate task)
- [ ] New LLM models for expansion (API compatibility issues noted)
- [ ] Graph traversal from matched chunks (future enhancement)

---

## 📐 Technical Approach

### Architecture Overview
```
Current Flow:
Query → LLM Expansion → [term1, term2, ...] → Parallel Search → Score → Rank

Enhanced Flow:
Query → LLM Expansion → [term1, term2, ...]
                              ↓
                    ┌─────────┴─────────┐
                    │                   │
              Token Search         Phrase Search
              (with IDF)           (n-grams)
                    │                   │
                    └─────────┬─────────┘
                              ↓
                      Combine Scores
                              ↓
                         Rerank
```

### Key Insight from Experiments

```
Expanded term: "Covering Fire feat"
Tokens: [covering, fire, feat]

Token frequencies in index:
  - "covering": 9 chunks  (IDF = log(23248/9) = 7.86)
  - "fire": 270 chunks    (IDF = log(23248/270) = 4.45)
  - "feat": 1184 chunks   (IDF = log(23248/1184) = 2.98)

Current: Each token scores 1.0 (all equal)
Improved: covering=7.86, fire=4.45, feat=2.98

Gold chunk contains all three → high IDF sum
Generic chunk contains only "feat" → low IDF sum
```

### Files to Create
- None (enhance existing files)

### Files to Modify
- `traversal/index.py` - Add IDF computation and n-gram index
- `traversal/parallel_search.py` - Use IDF-weighted scoring
- `traversal/reranker.py` - Adjust score normalization for IDF
- `run_first_experiments.py` - Add comparison between old/new scoring

### Dependencies
- External: None (pure Python, no new libraries)
- Internal: Existing TraversalIndex, parallel_search, reranker modules

---

## 📋 Implementation Steps

### Phase 1: IDF Weighting (Estimated: 2-3 hours)
**Goal:** Rare terms score higher than common terms

**Tasks:**
1. [ ] Add IDF computation to `TraversalIndex.build()`
   ```python
   # In index.py, add to TraversalIndex dataclass:
   term_idf: Dict[str, float] = field(default_factory=dict)
   
   # Compute during _index_chunks():
   total_chunks = len(chunks)
   for term, chunk_ids in term_to_chunks.items():
       df = len(chunk_ids)  # document frequency
       idf = math.log(total_chunks / df) if df > 0 else 0
       self.term_idf[term] = idf
   ```

2. [ ] Update `search_term()` in `parallel_search.py` to return IDF score
   ```python
   # Return IDF-weighted score instead of just hit count
   term_score = sum(index.term_idf.get(token, 1.0) for token in tokens)
   ```

3. [ ] Update `compute_chunk_scores()` to use IDF
   ```python
   # Instead of counting terms, sum IDF-weighted scores
   for chunk_id in result.chunk_ids:
       idf_score = sum(index.term_idf.get(t, 1.0) for t in tokens)
       chunk_scores[chunk_id] += idf_score
   ```

4. [ ] Run experiment to compare before/after

**Acceptance:**
- [ ] IDF values computed for all terms in index
- [ ] Rare terms (coverage < 0.1%) have IDF > 5.0
- [ ] Common terms (coverage > 5%) have IDF < 3.0
- [ ] Gold chunks rank higher than before

---

### Phase 2: N-Gram Phrase Matching (Estimated: 2-3 hours)
**Goal:** Match multi-word phrases, not just individual tokens

**Tasks:**
1. [ ] Add bigram index to `TraversalIndex`
   ```python
   # In index.py:
   bigram_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
   
   # During indexing, create bigrams from adjacent tokens:
   for i in range(len(tokens) - 1):
       bigram = f"{tokens[i]}_{tokens[i+1]}"
       bigram_to_chunks[bigram].add(chunk_id)
   ```

2. [ ] Update `search_term()` to check bigrams
   ```python
   # For multi-word terms, try bigram match first
   tokens = tokenize_and_normalize(term)
   if len(tokens) >= 2:
       for i in range(len(tokens) - 1):
           bigram = f"{tokens[i]}_{tokens[i+1]}"
           if bigram in index.bigram_to_chunks:
               chunk_ids |= index.bigram_to_chunks[bigram]
               # Bigram matches get bonus (more specific)
               search_type = "bigram"
   ```

3. [ ] Add bigram bonus to scoring
   ```python
   # Bigram matches score higher than single-token matches
   BIGRAM_BONUS = 2.0  # Tunable parameter
   if search_type == "bigram":
       term_score *= BIGRAM_BONUS
   ```

4. [ ] Run experiment to measure improvement

**Acceptance:**
- [ ] "covering_fire" bigram exists in index
- [ ] Phrase matches rank higher than token-only matches
- [ ] Combined IDF + bigram scoring shows improvement

---

## 🧪 Testing Plan

### Unit Tests
- [ ] `test_idf_computation()` - Verify IDF formula produces expected values
- [ ] `test_rare_term_high_idf()` - Rare terms have high IDF
- [ ] `test_common_term_low_idf()` - Common terms have low IDF
- [ ] `test_bigram_indexing()` - Bigrams correctly indexed
- [ ] `test_bigram_search()` - Bigram search returns correct chunks

### Integration Tests
- [ ] `test_idf_weighted_retrieval()` - End-to-end with IDF
- [ ] `test_phrase_matching_retrieval()` - End-to-end with bigrams

### Manual Testing Checklist
- [ ] Run `run_first_experiments.py` with old scoring
- [ ] Run again with IDF scoring
- [ ] Run again with IDF + bigram scoring
- [ ] Compare Recall@K across all three

### Edge Cases to Test
- [ ] Single-character terms (should be filtered)
- [ ] Terms with no matches (should not crash)
- [ ] Empty queries (should return empty results)
- [ ] Terms that become stopwords after tokenization

---

## 🐛 Known Issues & Constraints

### Technical Constraints
- Python 3.11+ required (already in project)
- Index build time may increase slightly with bigrams
- Memory usage increases for bigram index (monitor)

### Known Bugs to Work Around
- gpt-5-mini/nano don't support temperature parameter (use gpt-5.2 only for now)
- Some enriched chunk IDs have special characters in paths

### Risks & Mitigations
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| IDF over-weights rare typos | Medium | Low | Filter terms with df < 2 |
| Bigram index too large | Low | Medium | Limit to terms appearing in expanded queries |
| Score normalization breaks | Medium | High | Test with edge cases before/after |

---

## 📚 Reference Materials

### Related Documents
- `RulesIngestion/Docs/HYBRID_RETRIEVAL.md` - Architecture overview
- `RulesIngestion/traversal/index.py` - TraversalIndex implementation
- `RulesIngestion/traversal/parallel_search.py` - Current search implementation
- `RulesIngestion/traversal/reranker.py` - Score combination logic
- `RulesIngestion/experiments/metrics.py` - Recall@K computation

### Experiment Results (Baseline)
Location: `RulesIngestion/experiments/results/run-20260127-193900-001.json`

Key metrics:
```json
{
  "avg_recall_at_k": {
    "1": 0.0,
    "5": 0.028,
    "10": 0.083,
    "30": 0.139
  },
  "attribution": {
    "deterministic_only": 4,
    "neither": 24
  }
}
```

### Evaluation Queries
Location: `RulesIngestion/blind_eval/batches/batch_001.json`

6 complete queries with gold chunk IDs (4 more are TODO).

### IDF Formula Reference
```python
# Standard TF-IDF inverse document frequency
IDF(term) = log(N / df(term))

# Where:
#   N = total documents (chunks)
#   df(term) = documents containing term

# Example from our index:
#   "covering": IDF = log(23248 / 9) = 7.86
#   "feat": IDF = log(23248 / 1184) = 2.98
```

### Pattern to Follow
From `traversal/index.py` existing structure:

```python
@dataclass
class TraversalIndex:
    # Existing indexes
    term_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    
    # ADD: IDF weights
    term_idf: Dict[str, float] = field(default_factory=dict)
    
    # ADD: Bigram index
    bigram_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    bigram_idf: Dict[str, float] = field(default_factory=dict)
```

---

## 💬 Open Questions

- [ ] Should we also add trigrams for 3-word phrases?
- [ ] What's the right bigram bonus multiplier (1.5x, 2x, 3x)?
- [ ] Should IDF be capped to prevent extreme values for hapax legomena?
- [ ] Should we pre-compute IDF or compute on-demand?

---

## 📊 Progress Tracking

### Session 1: 2026-01-27 (~2 hours)
- [x] Phase 1: IDF Weighting implemented
- [x] Phase 2: Bigram matching implemented
- [x] Bug fix: Per-chunk IDF scoring (was giving all chunks same score)
- [x] Experiments run: Baseline vs IDF comparison
- [x] Results: R@10 improved from 8.3% → 11.1%, R@30 from 8.3% → 21.4%

---

## 🚀 Next Steps

### Immediate (This Task)
- [x] Implement IDF weighting
- [x] Implement bigram matching
- [x] Run comparative experiments
- [x] Document results

### Session 2: 2026-01-28 - RRF + Traversal Enhancement (~1 hour)
- [x] Implement RRF (Reciprocal Rank Fusion) as alternative to weighted sum
- [x] Add traversal depth-based ranking (`traverse_with_ranks`)
- [x] Implement 3-way RRF fusion (det + sem + traversal)
- [x] Run comparative experiments across 5 strategies

#### RRF Results Summary

| Strategy | R@5 | R@10 | R@30 | Gold Found | Avg Latency |
|----------|-----|------|------|------------|-------------|
| Weighted Sum (50/50) | 13.7% | 21.6% | 29.9% | 13/28 | 1865ms |
| 2-Way RRF (det + sem) | 7.9% | 13.1% | 29.8% | 13/28 | 1419ms |
| **3-Way RRF (det + sem + trav)** | **15.9%** | 18.7% | 29.8% | 12/28 | 1435ms |
| Det-Heavy RRF (70/30 + trav) | 13.7% | 16.4% | 27.5% | 13/28 | 1617ms |
| Sem-Heavy RRF (30/70 + trav) | 4.8% | 7.5% | 24.2% | 13/28 | 1456ms |

**Key Insights:**
1. **3-Way RRF achieves best R@5 (15.9%)** - traversal helps early ranking
2. **Traversal is essentially free** - adds ~16ms to get BFS depth ranks
3. **2-Way RRF alone underperforms weighted sum** - needs traversal signal
4. **Gold chunks rank earlier with traversal** - ranks [3, 3, 3] vs [6, 4, 1]

### Follow-Up Tasks (Future)
- [x] Semantic search integration (completed!)
- [x] Graph traversal from matched chunks (depth-based ranking)
- [ ] Query intent → scoring strategy mapping
- [ ] Complete remaining 4 evaluation queries
- [ ] Tune RRF k parameter (currently k=60)
- [ ] Try RRF with anchor-boosted traversal ranking

### Spawned Investigations (2026-01-28)
Two critical issues discovered during pipeline comparison:

1. **`HANDOFF-Missing-Gold-Chunks-Investigation.md`**
   - 54% of gold chunks (15/28) NOT found by ANY pipeline
   - This is a retrieval ceiling problem
   - Need to understand indexing/embedding gaps

2. **`HANDOFF-Ranking-Degradation-Debug.md`**
   - Weighted Sum finds 19/28 but only 26.6% R@30
   - Gold chunks being retrieved but ranked 30+
   - Need to debug score fusion

### Blocked By
- None - can start immediately

---

**Created:** 2026-01-27  
**Last Updated:** 2026-01-27  
**Owner:** [Agent]  
**Status:** Ready for implementation
