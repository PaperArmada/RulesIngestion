# Missing Gold Chunks Investigation
**Date:** 2026-01-28  
**Status:** 🔴 Ready  
**Priority:** P1  
**Estimated Time:** 2-3 hours  
**Scope:** Narrow - Diagnostic only

---

## 📋 Problem Statement

**54% of gold chunks (15/28) are NOT found by ANY retrieval pipeline.**

This is a retrieval ceiling problem. No amount of ranking improvement will help if the chunks aren't even in the candidate set.

### Current State
- 6 evaluation queries with 28 total gold chunks
- Best pipeline (Weighted Sum) finds only 19/28 (68%)
- Union of ALL pipelines (Traversal + Semantic + Deterministic) finds only 13/28 (46%)
- **15 gold chunks are never retrieved by any method**

### Desired End State
- Understand WHY each missing chunk isn't being found
- Categorize root causes (indexing gap, query mismatch, embedding gap, etc.)
- Identify actionable fixes

---

## 🎯 Scope (Narrow)

### In Scope
- [ ] List all 15 missing gold chunk IDs
- [ ] For each missing chunk, determine:
  - Is it in the TraversalIndex? (term_to_chunks, section_title_to_chunks, etc.)
  - Is it in the embeddings collection?
  - What are its key terms/tokens?
  - Why didn't query expansion produce matching terms?
  - Why didn't semantic search rank it higher?
- [ ] Categorize failures by root cause
- [ ] Document findings

### Out of Scope
- Implementing fixes (separate task)
- Changing retrieval pipelines
- Adding new evaluation queries

---

## 📐 Technical Approach

### Step 1: Extract Missing Chunks
```python
# From previous analysis, these chunks were NOT found by any pipeline:
missing_gold_ids = all_gold - (traversal_gold | semantic_gold | deterministic_gold)
```

### Step 2: Check Index Coverage
For each missing chunk:
```python
chunk = chunk_lookup[chunk_id]
tokens = tokenize_and_normalize(chunk.get('text', ''))

# Is it indexed?
in_term_index = any(token in index.term_to_chunks for token in tokens)
in_section_index = chunk.get('section_title', '').lower() in index.section_title_to_chunks
in_embeddings = chunk_id in embedding_chunk_ids
```

### Step 3: Check Query-Chunk Alignment
For each (query, missing_chunk) pair:
```python
# What terms did expansion produce?
expansion = expander.expand(query)

# Do any expansion terms match chunk tokens?
chunk_tokens = set(tokenize_and_normalize(chunk['text']))
expansion_tokens = set()
for term in expansion.expanded_terms:
    expansion_tokens.update(tokenize_and_normalize(term))

overlap = chunk_tokens & expansion_tokens
```

### Step 4: Check Semantic Distance
```python
# What's the semantic similarity?
query_emb = model.encode(f'search_query: {query}')
chunk_emb = embeddings[chunk_id_to_idx[chunk_id]]
similarity = np.dot(query_emb, chunk_emb)

# What rank would this chunk get in pure semantic search?
all_sims = embeddings @ query_emb
rank = np.sum(all_sims > similarity) + 1
```

---

## 📊 Expected Output

A table like:

| Chunk ID | Query | In Index? | In Embeddings? | Term Overlap | Semantic Rank | Root Cause |
|----------|-------|-----------|----------------|--------------|---------------|------------|
| chunk_001 | Q1 | Yes | Yes | 0 terms | 15,234 | No term overlap + low semantic |
| chunk_002 | Q2 | No | Yes | N/A | 8,102 | Not indexed |
| ... | ... | ... | ... | ... | ... | ... |

### Root Cause Categories
1. **Not Indexed** - Chunk missing from TraversalIndex
2. **Not Embedded** - Chunk missing from embeddings collection
3. **Query Mismatch** - Expansion terms don't match chunk content
4. **Semantic Gap** - Embedding similarity too low
5. **Graph Disconnect** - Not reachable from any anchor

---

## 📂 Files to Read

- `blind_eval/batches/batch_001.json` - Evaluation queries with gold_chunk_ids
- `Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json` - Chunk data

---

## ✅ Success Criteria

- [ ] All 15 missing chunks analyzed
- [ ] Root cause identified for each
- [ ] Summary table produced
- [ ] Top 3 actionable recommendations documented

---

**Created:** 2026-01-28  
**Owner:** [Agent]
