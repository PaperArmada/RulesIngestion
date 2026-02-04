# Traversal Retrieval Improvement Analysis

**Date:** January 2026  
**Status:** Analysis Complete

---

## Summary

The traversal-only system achieves **96.30% recall** but fails on 1 query. Analysis reveals the failure stems from **upstream enrichment gaps**, not traversal algorithm issues.

---

## Failure Analysis

### Query 9 (The Single Traversal Failure)

**Query:** "Does being grabbed prevent you from casting spells with somatic or material components in Starfinder 2e?"

**Gold chunk:** Describes the "grabbed" condition and its effect on manipulate actions.

**Gold chunk text:**
> "You're held in place by another creature, giving you the offguard and immobilized conditions. If you attempt a **manipulate** action while grabbed, you must succeed at a DC 5 flat check or it's lost..."

### Root Causes Identified

| Issue | Impact | Root Cause |
|-------|--------|------------|
| **Vocabulary mismatch** | Query uses "spells/somatic/material", gold uses "manipulate action" | Semantic gap between user language and rules language |
| **Anchor ranking** | Gold chunk ranks #175 by term count, we take top 50 | Only matches "grabbed" (1 term) |
| **Traversal depth** | Path to gold is 5 hops, max_depth is 2 | Policy too restrictive |
| **Empty section_path** | Gold chunk has `section_path: []` | Enrichment didn't extract section structure |
| **No entity in graph** | "grabbed" not indexed as entity | Condition entities not extracted |
| **No condition section** | 0 chunks have "condition" in section_path | Systemic enrichment gap |

---

## Benchmark Quality Issues

Three queries have **no gold chunks labeled** in the benchmark:

| Query | Issue |
|-------|-------|
| Query 0 (Sniper's Scope) | Complex multi-section answer, not labeled |
| Query 10 (Material components + two-handed) | Cross-reference answer, not labeled |
| Query 13 (XP for starship scenes) | Missing relevant chunks |

**Action:** These need manual labeling before we can evaluate traversal performance on them.

---

## Improvement Strategies

### 1. Enrichment Pipeline Improvements (Upstream)

#### 1.1 Extract Condition Entities

**Current state:** Condition names like "grabbed", "stunned", "prone" are not extracted as graph entities.

**Improvement:**
```python
# In enrichment/graph_builder.py
CONDITION_NAMES = {
    "grabbed", "stunned", "prone", "flat-footed", "off-guard",
    "immobilized", "restrained", "hidden", "undetected", ...
}

def extract_condition_entities(chunk_text: str) -> List[Entity]:
    """Extract condition entities from chunk text."""
    entities = []
    for condition in CONDITION_NAMES:
        if condition.lower() in chunk_text.lower():
            entities.append(Entity(
                canonical_id=f"canon:sf2e:condition:{condition}",
                name=condition,
                type="condition",
            ))
    return entities
```

**Impact:** Queries mentioning conditions would find definition chunks via entity lookup.

#### 1.2 Fix Section Path Extraction

**Current state:** Many chunks have empty `section_path`.

**Improvement:** Debug why section extraction fails for condition definitions. Likely a PDF parsing issue in the Conditions chapter.

#### 1.3 Add Cross-Reference Edges

The rules mention "manipulate action" in the grabbed condition. We need edges linking:
- `grabbed` condition → `manipulate` action trait
- `Cast a Spell` action → `manipulate` trait

**Impact:** Traversal could follow: query → "spell" chunks → Cast a Spell → manipulate → grabbed.

---

### 2. Anchor Finding Improvements

#### 2.1 Guaranteed Critical Term Anchors

**Current:** Take top 50 by term count. 
**Problem:** Important single-term matches get dropped.

**Improvement:**
```python
def find_anchor_nodes(query: str, index: TraversalIndex) -> Set[str]:
    anchors = set()
    terms = tokenize_and_normalize(query)
    
    # NEW: Always include chunks matching game-term entities
    # (conditions, spells, feats, etc.)
    game_terms = detect_game_terms(terms)  # "grabbed" → condition
    for term in game_terms:
        if term in index.term_to_chunks:
            anchors |= index.term_to_chunks[term]
    
    # THEN: Add top-N by term frequency
    term_hits = count_term_hits(terms, index)
    sorted_chunks = sorted(term_hits.items(), key=lambda x: -x[1])
    for chunk_id, _ in sorted_chunks[:50]:
        anchors.add(chunk_id)
    
    return anchors
```

**Impact:** Condition/spell/feat names always become anchors regardless of term count.

#### 2.2 Tag-Based Anchor Boost

**Current:** Tag matching is just another anchor source.
**Improvement:** Prioritize chunks tagged with `conditions` when query mentions condition-related terms.

---

### 3. Traversal Policy Improvements

#### 3.1 Dynamic Depth Based on Query Complexity

**Current:** Fixed max_depth=2 for DEFINITION.
**Problem:** Complex exception queries need deeper traversal.

**Improvement:**
```python
def get_policy(intent: Intent, query: str) -> TraversalPolicy:
    base_policy = INTENT_POLICIES[intent]
    
    # Increase depth for complex queries
    if has_cross_reference_signal(query):
        return TraversalPolicy(
            allow_edges=base_policy.allow_edges,
            max_depth=base_policy.max_depth + 2,  # +2 for cross-refs
            include_siblings=base_policy.include_siblings,
            chunk_limit=base_policy.chunk_limit * 2,
        )
    
    return base_policy

def has_cross_reference_signal(query: str) -> bool:
    """Detect queries that likely need cross-reference traversal."""
    signals = [
        "prevent", "affect", "interact", "while", "when", "does X apply",
    ]
    return any(s in query.lower() for s in signals)
```

#### 3.2 Exception Intent Detection

Query 9 should be classified as EXCEPTION, not DEFINITION:
> "Does being grabbed **prevent** you from..."

**Improvement:** Add patterns to `classify_intent_rules`:
```python
EXCEPTION_PATTERNS = [
    r"does\s+.*\s+prevent",   # NEW
    r"can\s+.*\s+while",      # NEW
    r"does\s+.*\s+apply",
    r"unless",
]
```

---

### 4. New Index Types

#### 4.1 Condition Definition Index

```python
# condition_name → chunk_id of definition
condition_definitions: Dict[str, str] = {
    "grabbed": "sf2e-playercore-...::/page/13/Text/19",
    "stunned": "sf2e-playercore-...::/page/X/Text/Y",
}
```

Build this during index construction by:
1. Finding chunks with `content_kind="rule"` and `tags=["conditions"]`
2. Extracting condition name from first line of text

#### 4.2 Action-Trait Relationship Index

```python
# action → traits
action_traits: Dict[str, Set[str]] = {
    "Cast a Spell": {"manipulate", "concentrate"},
    "Strike": {"attack"},
}

# trait → chunks describing it
trait_chunks: Dict[str, Set[str]]
```

---

## Implementation Priority

### High Priority (Fix Query 9)

1. **Add exception intent patterns** for "prevent/while" queries
2. **Guarantee condition term anchors** - if query contains condition name, always anchor to it
3. **Increase depth for exception queries** to 3-4 hops

### Medium Priority (Systematic Improvement)

4. **Extract condition entities** in enrichment pipeline
5. **Fix section_path extraction** for condition chapter
6. **Add condition definition index**

### Low Priority (Future Robustness)

7. **Add action-trait relationship edges**
8. **Build cross-reference edge extractor**
9. **Label remaining benchmark queries**

---

## Quick Win: Fix Query 9

The fastest fix for Query 9 specifically:

```python
# In seeds.py
CONDITION_NAMES = {"grabbed", "stunned", "prone", ...}

def find_anchor_nodes(query: str, index: TraversalIndex) -> Set[str]:
    anchors = set()
    terms = tokenize_and_normalize(query)
    
    # PRIORITY 1: Condition names get ALL matching chunks
    for term in terms:
        if term in CONDITION_NAMES:
            if term in index.term_to_chunks:
                anchors |= index.term_to_chunks[term]
    
    # PRIORITY 2: Top-N by term frequency (existing logic)
    ...
```

This ensures "grabbed" chunks (including the gold chunk) become anchors, even with only 1 term match.

---

## Expected Impact

| Change | Recall Impact | Effort |
|--------|---------------|--------|
| Condition term priority | +1 query (96% → 100%) | Low |
| Exception intent patterns | Better policy selection | Low |
| Increase exception depth | More paths found | Low |
| Condition entity extraction | Systematic improvement | Medium |
| Section path fixes | Many chunks benefit | Medium |
| Cross-reference edges | Complex queries | High |

---

## Conclusion

The traversal system is working correctly - the failure is due to:
1. **Enrichment gaps** (no condition entities, empty section paths)
2. **Anchor ranking** (condition names should be prioritized)
3. **Intent classification** (query should be EXCEPTION, not DEFINITION)

All three are fixable with targeted improvements. The recommended quick win is **prioritizing condition/spell/feat names as anchors**, which should bring recall to 100%.
