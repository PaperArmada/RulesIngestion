# Fact-Based Retrieval Architecture
## Technical Documentation for RulesIngestion Pipeline

**Last Updated:** 2026-01-28  
**Status:** Phase 4 Complete (Query-side semantic traversal implemented)  
**Test Coverage:** 129 tests passing (25 ClauseUnits + 47 Mentions + 57 RuleFacts)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Phase 1: ClauseUnit Extraction](#phase-1-clauseunit-extraction)
4. [Phase 2: Mention Extraction](#phase-2-mention-extraction)
5. [Phase 3: RuleFact Extraction](#phase-3-rulefact-extraction)
6. [Phase 4: Typed Relations](#phase-4-typed-relations)
7. [End-to-End Pipeline](#end-to-end-pipeline)
8. [Strengths](#strengths)
9. [Weaknesses and Known Limitations](#weaknesses-and-known-limitations)
10. [File Reference](#file-reference)

---

## Executive Summary

The Fact-Based Retrieval Architecture is a four-phase pipeline that transforms TTRPG rulebook content from raw markdown chunks into a traversable semantic graph. The goal is to enable cross-chapter retrieval for complex, multi-mechanic queries like:

> "Suggest some complimentary feats for a Level 9 Lashunta Solarian"

### Current State

| Metric | Value |
|--------|-------|
| Test Coverage | 129 tests passing, 6 skipped |
| ClauseUnits | 32,271 extracted (avg 1.39 per chunk) |
| Mentions | 14,205+ extracted |
| RuleFacts | Pattern-based extraction with 30+ patterns |
| Benchmark Recall | **0/28** (current bottleneck: fact-to-mechanic alignment) |

### The Core Problem (Why Benchmark Fails)

Mention extraction works. Traversal works. The pipeline fails because:
1. **Mechanic names extracted from queries** (e.g., "Vent Gas", "Covering Fire")
2. **Mechanic names NOT in RuleFact subject/object fields** (facts use generic predicates)
3. **No bridge** between query-side mentions and ingestion-side facts

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RulesIngestion Pipeline                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  EnrichedChunk (400-800 chars)                                         │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Phase 1: ClauseUnit Extraction                                  │   │
│  │ - Split on sentence boundaries                                  │   │
│  │ - Handle TTRPG abbreviations (DC, CR, ft.)                     │   │
│  │ - Merge short fragments                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Phase 2: Mention Extraction                                     │   │
│  │ - Regex patterns (level, DC, conditions, outcomes)             │   │
│  │ - Vocabulary lookup (roles, mechanics from graph)              │   │
│  │ - Normalization (Level 9 → level:9)                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Phase 3: RuleFact Extraction                                    │   │
│  │ - Pattern matching (30+ patterns)                               │   │
│  │ - Subject/predicate/object triple                               │   │
│  │ - First-class failure semantics (ON_FAILURE facts)             │   │
│  │ - Scope from mentions (role:lashunta; level:9)                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Phase 4: Typed Relations                                        │   │
│  │ - Same-clause outcome pairing (success→failure)                │   │
│  │ - Cross-section role scope linking                             │   │
│  │ - Same-subject edges (deterministic)                           │   │
│  │ - Constrained structural edges (same-chunk)                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Graph Output                                                    │   │
│  │ - Fact nodes (type: RuleFact)                                  │   │
│  │ - Typed relation edges                                          │   │
│  │ - Chunk nodes (traceability)                                   │   │
│  │ - Document hierarchy edges                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: ClauseUnit Extraction

**File:** `enrichment/clause_units.py` (323 lines)  
**Tests:** `tests/test_clause_units.py` (25 tests passing)

### Purpose

Split EnrichedChunks (400-800 character markdown spans) into sentence-level ClauseUnits for finer-grained semantic processing.

### Data Model

```python
@dataclass
class ClauseUnit:
    clause_id: str                    # {chunk_id}::clause_{order}
    text: str                         # The sentence text
    parent_chunk_id: str              # Link back to EnrichedChunk.id
    order_in_chunk: int               # 0-indexed position
    char_offsets: Tuple[int, int]     # (start, end) in parent
    page: int = 0                     # Inherited from chunk
    section_path: List[str] = field(default_factory=list)
```

### Key Algorithm

```python
def extract_clause_units(chunk: "EnrichedChunk") -> List[ClauseUnit]:
    """
    1. Find sentence boundaries (. ! ?)
    2. Skip TTRPG abbreviations (DC 15., 10 ft., CR 5.)
    3. Handle numbered lists (1. First item)
    4. Merge short fragments (< 20 chars)
    """
```

### TTRPG-Aware Sentence Splitting

```python
ABBREVIATIONS = {
    "ft", "lbs", "sq", "vs", "etc", "min", "max",
    "e.g", "i.e", "Mr", "Mrs", "Dr", "pg", "pp",
}

# Game abbreviations that shouldn't split sentences
GAME_ABBREV_PATTERN = re.compile(r"\b(DC|CR|AC|HP|XP|GP|SP|CP|PP)\s+\d+\.")
```

### Statistics

- **Average clauses per chunk:** 1.39
- **Total clauses (PlayerCore):** ~32,271

---

## Phase 2: Mention Extraction

**Files:**
- `enrichment/mentions.py` (300 lines)
- `enrichment/vocabulary_loader.py` (474 lines)
- `enrichment/mention_type_inference.py` (225 lines)

**Tests:** `tests/test_mentions.py` (47 tests passing)

### Purpose

Extract **searchable semantic anchors** from clauses—entity references that can seed graph traversal.

### Data Model

```python
class MentionType(Enum):
    ROLE = "role"           # Ancestry, class, archetype
    LEVEL = "level"         # Character/spell level
    TRAIT = "trait"         # Action traits ([two-actions])
    MECHANIC = "mechanic"   # Feats, spells, abilities
    NUMERIC_TERM = "numeric_term"  # DC, CR, AC values
    ENTITY_TYPE = "entity_type"    # creature, object
    CONDITION = "condition"        # prone, stunned
    OUTCOME = "outcome"            # success, failure
    UNKNOWN = "unknown"

@dataclass
class Mention:
    mention_id: str              # {clause_id}::mention_{order}
    surface: str                 # Exact text ("Lashunta")
    normalized: str              # Canonical key ("role:lashunta")
    mention_type: MentionType
    clause_id: str
    span_offsets: Tuple[int, int]
    confidence: float = 1.0
    extraction_method: str = "regex"  # regex | vocabulary
```

### Two Extraction Strategies

#### 1. Regex Patterns (Deterministic)

```python
MENTION_PATTERNS = {
    "level_numeric": (
        re.compile(r'\b(?:level|Level)\s+(\d{1,2})\b'),
        MentionType.LEVEL
    ),
    "dc_value": (
        re.compile(r'\bDC\s*(\d{1,2})\b'),
        MentionType.NUMERIC_TERM
    ),
    "condition": (
        re.compile(r'\b(prone|stunned|frightened|...)\b', re.IGNORECASE),
        MentionType.CONDITION
    ),
    "success_outcome": (
        re.compile(r'\b(critical success|success|failure|critical failure)\b'),
        MentionType.OUTCOME
    ),
}
```

#### 2. Vocabulary Lookup (Graph-Derived)

```python
def extract_role_mentions(clause, vocabulary, mention_counter=0):
    """
    Match against role vocabulary loaded from graph.
    Example vocabulary: {"android", "lashunta", "solarian", ...}
    """
    mentions = []
    text_lower = clause.text.lower()
    
    for role in vocabulary:
        idx = text_lower.find(role)
        if idx != -1 and _is_word_boundary(text_lower, idx, len(role)):
            mentions.append(Mention(
                surface=clause.text[idx:idx + len(role)],
                normalized=f"role:{role}",
                mention_type=MentionType.ROLE,
                ...
            ))
    return mentions
```

### Vocabulary Loading (System-Agnostic)

```python
DEFAULT_MENTION_TYPE_MAPPINGS = {
    "role": {"ancestry", "class", "archetype", "background", "heritage"},
    "mechanic": {"feat", "spell", "ability", "action", "skill", "item"},
    "condition": {"condition", "status"},
}

def load_vocabulary_from_graph_data(graph, mention_type_mappings):
    """
    Extract vocabulary from graph nodes by entity type.
    No hardcoded entity names - all derived from data.
    """
    vocabularies = {mt: set() for mt in mention_type_mappings.keys()}
    
    for node in graph.get("nodes", []):
        node_type = node.get("type", "").lower()
        name = node.get("name", "")
        
        if node_type in entity_to_mention:
            mention_type = entity_to_mention[node_type]
            vocabularies[mention_type].add(name.lower())
    
    return vocabularies
```

### Mechanic Vocabulary Enrichment

```python
def _extract_mechanic_terms_from_chunk(chunk, mechanic_entity_types):
    """
    Extract mechanic names from chunk text using:
    1. Spell title patterns (**Spell Name** [rank X])
    2. Feat title patterns (**Feat Name** [reaction])
    3. Bold headings
    4. First-line titles
    5. Capitalized multi-word phrases in mechanic contexts
    """
```

### Compact Matching (Handles Typos)

```python
# "Side Step" matches "Sidestep" via compact (alnum-only) matching
compact_term = "".join(char for char in mechanic if char.isalnum())
compact_text = "".join(char for char in text_lower if char.isalnum())
```

---

## Phase 3: RuleFact Extraction

**File:** `enrichment/rule_facts.py` (903 lines)  
**Tests:** `tests/test_rule_facts.py` (57 tests passing, 4 skipped)

### Purpose

Extract **semantic atomic claims** from clauses—structured facts that can be traversed as graph nodes.

### Data Model

```python
class FactType(Enum):
    # Core rule facts
    GRANTS = "grants"
    REQUIRES = "requires"
    MODIFIES = "modifies"
    TRIGGERS = "triggers"
    PREVENTS = "prevents"
    APPLIES_TO = "applies_to"
    
    # Outcome facts (FIRST-CLASS failure semantics)
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"    # ← Critical: not inferred, explicit
    ON_CRITICAL = "on_critical"
    
    # Override/exception facts
    OVERRIDES = "overrides"
    INSTEAD_OF = "instead_of"
    UNLESS = "unless"
    
    # Gate facts
    LEVEL_GATE = "level_gate"
    ROLE_GATE = "role_gate"
    TRAIT_GATE = "trait_gate"
    
    # Incomplete
    PARTIAL = "partial"
    UNKNOWN = "unknown"

class Modality(Enum):
    MUST = "must"         # Required
    MAY = "may"           # Optional
    CAN = "can"           # Capability
    AUTOMATIC = "automatic"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"

@dataclass
class RuleFact:
    fact_id: str              # {clause_id}::fact_{order}
    fact_type: FactType
    
    # Core triple
    subject: Optional[str]    # What this fact is about
    subject_type: Optional[str]  # mechanic | role | entity
    predicate: str            # grants | requires | on_failure
    object: Optional[str]     # Target/result
    object_type: Optional[str]
    
    # Semantic context
    modality: Modality
    condition: Optional[str]  # Triggering condition
    scope: Optional[str]      # "role:lashunta; level:9"
    
    # Provenance
    clause_id: str
    mention_ids: List[str]
    evidence_span: Tuple[int, int]
    
    # Quality
    confidence: float = 1.0
    extraction_method: str = "pattern"
    is_complete: bool = True
    
    # Failure/override semantics
    failure_outcome: Optional[str] = None
    override_target: Optional[str] = None
```

### Pattern-Based Extraction (30+ Patterns)

```python
OUTCOME_PATTERNS = [
    FactPattern(
        name="on_success",
        pattern=re.compile(
            r'\b(?:on\s+a?\s*)?(?:success|successful)\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.ON_SUCCESS,
        modality=Modality.CONDITIONAL,
    ),
    FactPattern(
        name="on_failure",
        pattern=re.compile(
            r'\b(?:on\s+a?\s*)?(?:failure|failed)\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.ON_FAILURE,
        modality=Modality.CONDITIONAL,
    ),
    FactPattern(
        name="critical_failure",
        pattern=re.compile(
            r'\bcritical\s+failure\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.ON_FAILURE,  # Treated as failure variant
        modality=Modality.CONDITIONAL,
    ),
]

LEVEL_PATTERNS = [
    FactPattern(
        name="at_level",
        pattern=re.compile(
            r'\bat\s+(\d+)(?:st|nd|rd|th)\s+level\s*[,:]\s*(?:you\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.LEVEL_GATE,
        modality=Modality.AUTOMATIC,
    ),
    FactPattern(
        name="prereq_level",
        pattern=re.compile(
            r'\bprerequisite[s]?\s*[,:]\s*.*?level\s+(\d+)',
            re.IGNORECASE
        ),
        fact_type=FactType.LEVEL_GATE,
        modality=Modality.MUST,
    ),
]

GRANTS_PATTERNS = [
    FactPattern(
        name="you_gain",
        pattern=re.compile(r'\byou\s+gain\s+(.+?)(?:\.|$)', re.IGNORECASE),
        fact_type=FactType.GRANTS,
        modality=Modality.AUTOMATIC,
    ),
    FactPattern(
        name="subject_gains",
        pattern=re.compile(r'\b\w+\s+gains\s+(.+?)(?:\.|$)', re.IGNORECASE),
        fact_type=FactType.GRANTS,
        modality=Modality.AUTOMATIC,
    ),
]
```

### Subject Identification (Priority Order)

```python
def _identify_subject(mentions, hint=None):
    """
    Priority:
    1. MECHANIC mention (feat, spell name)
    2. ROLE mention (ancestry, class)
    3. Subject hint from section header
    4. ENTITY_TYPE mention
    """
    mechanic_mentions = [m for m in mentions if m.mention_type == MentionType.MECHANIC]
    if mechanic_mentions:
        return (mechanic_mentions[0].normalized, "mechanic")
    
    role_mentions = [m for m in mentions if m.mention_type == MentionType.ROLE]
    if role_mentions:
        return (role_mentions[0].normalized, "role")
    
    if hint:
        return (hint.lower(), "inherited")
    
    # ...
```

### Scope Extraction (Critical for Cross-Chapter)

```python
def _extract_scope(mentions):
    """Build scope string from role/level mentions."""
    role_mentions = [m for m in mentions if m.mention_type == MentionType.ROLE]
    level_mentions = [m for m in mentions if m.mention_type == MentionType.LEVEL]
    
    parts = []
    if role_mentions:
        parts.append(role_mentions[0].normalized)  # "role:lashunta"
    if level_mentions:
        parts.append(level_mentions[0].normalized)  # "level:9"
    
    return "; ".join(parts)  # "role:lashunta; level:9"
```

### First-Class Failure Semantics

```python
def _ensure_failure_facts(facts, clause, mentions):
    """
    If ON_SUCCESS exists without ON_FAILURE,
    create explicit ON_FAILURE fact if failure language present.
    
    Philosophy: Failure states must be nodes, not absence of success.
    """
    has_success = any(f.fact_type == FactType.ON_SUCCESS for f in facts)
    has_failure = any(f.fact_type == FactType.ON_FAILURE for f in facts)
    
    if has_success and not has_failure:
        if re.search(r'\b(fail|failure|failed)\b', clause.text, re.IGNORECASE):
            failure_fact = RuleFact.partial(
                clause_id=clause.clause_id,
                order=len(facts),
                subject=facts[0].subject if facts else None,
                predicate="on_failure",
                object="(implicit - failure mentioned but not specified)",
            )
            failure_fact.fact_type = FactType.ON_FAILURE
            facts.append(failure_fact)
```

---

## Phase 4: Typed Relations

**File:** `enrichment/fact_relations.py` (559 lines)

### Purpose

Generate **typed edges** between RuleFacts, enabling semantic graph traversal.

### Data Model

```python
class RelationType(Enum):
    # P0: Outcome relations (critical for failure/override traversal)
    HAS_FAILURE_MODE = "has_failure_mode"  # Success → Failure
    CONTRASTS_WITH = "contrasts_with"      # Success ↔ Failure (bidirectional)
    OVERRIDDEN_BY = "overridden_by"        # Failure → Override
    CHANGES_OUTCOME = "changes_outcome"    # Override → New result
    
    # P1: Scope relations (critical for cross-chapter)
    REQUIRES_LEVEL = "requires_level"      # Fact → Level gate
    APPLIES_TO_ROLE = "applies_to_role"    # Fact ↔ Same role scope
    
    # P2: Semantic relations
    TRIGGERS = "triggers"
    UNLESS = "unless"
    SAME_SUBJECT = "same_subject"
    
    # Structural relations
    IN_SAME_CLAUSE = "in_same_clause"
    IN_SAME_CHUNK = "in_same_chunk"

@dataclass
class FactRelation:
    relation_id: str
    relation_type: RelationType
    source_fact_id: str
    target_fact_id: str
    
    structural_distance: int = 0
    same_clause: bool = False
    same_chunk: bool = False
    same_section: bool = False
    
    inference_method: str = "pattern"  # pattern | scope | structural
    confidence: float = 1.0
```

### Relation Generation Strategies

#### 1. Same-Clause Outcome Pairing

```python
# For each clause, link success → failure facts
for clause_facts in by_clause.values():
    success = [f for f in clause_facts if f.fact_type == FactType.ON_SUCCESS]
    failure = [f for f in clause_facts if f.fact_type == FactType.ON_FAILURE]
    
    for success_fact in success:
        for failure_fact in failure:
            _add_relation(relations, seen,
                RelationType.HAS_FAILURE_MODE,
                success_fact, failure_fact,
                confidence=1.0
            )
            # Bidirectional contrast
            _add_relation(relations, seen,
                RelationType.CONTRASTS_WITH,
                success_fact, failure_fact
            )
            _add_relation(relations, seen,
                RelationType.CONTRASTS_WITH,
                failure_fact, success_fact
            )
```

#### 2. Cross-Section Role Scope Linking

```python
# Facts with same role scope (e.g., "role:lashunta") link across sections
for role_scope, scope_facts in by_role_scope.items():
    for idx, source in enumerate(ordered):
        for target in ordered[idx + 1:]:
            if _passes_hybrid_gating(source_ctx, target_ctx, allow_cross_section):
                _add_relation(relations, seen,
                    RelationType.APPLIES_TO_ROLE,
                    source, target,
                    inference_method="scope",
                    confidence=0.6
                )
```

#### 3. Same-Subject Linking (Deterministic)

```python
# Facts about same normalized subject link together
for subject_key, subject_facts in by_subject.items():
    for idx, source in enumerate(ordered):
        for target in ordered[idx + 1:]:
            _add_relation(relations, seen,
                RelationType.SAME_SUBJECT,
                source, target,
                inference_method="subject",
                confidence=0.7
            )
```

### Hybrid Gating (Structural + Semantic)

```python
def _passes_hybrid_gating(source_ctx, target_ctx, allow_cross_section, 
                          shared_subject, shared_role_scope):
    """
    Allow relations if:
    1. Same clause (always OK)
    2. Same section AND within 2 heading hops
    3. Cross-section ONLY if shared_subject OR shared_role_scope
    """
    if source_ctx.clause_id == target_ctx.clause_id:
        return True
    
    if source_ctx.section_path == target_ctx.section_path:
        return structural_distance <= STRUCTURAL_SECTION_HOPS
    
    if not allow_cross_section:
        return False
    
    return shared_subject or shared_role_scope
```

### Cardinality Limits (Prevent Explosion)

```python
MAX_ROLE_LINKS_PER_FACT = 2
MAX_SUBJECT_LINKS_PER_FACT = 4
MAX_CHUNK_LINKS_PER_FACT = 3
```

---

## End-to-End Pipeline

**File:** `enrichment/graph_builder.py` → `build_fact_graph()` (1320+ lines)

### Integration Function

```python
def build_fact_graph(
    doc_id: str,
    chunks: List[EnrichedChunk],
    ruleset_id: Optional[str] = None,
    resolved_config: Optional[Any] = None,
    include_fact_chunk_links: bool = True,
    include_partial: bool = False,
    allow_cross_section: bool = True,
    vocabularies: Optional[Dict[str, Set[str]]] = None,
    mention_type_mappings: Optional[Dict[str, Set[str]]] = None,
) -> Graph:
    """
    Build complete fact graph:
    1. Build base chunk graph (structural)
    2. Load vocabularies from graph data
    3. For each chunk:
       a. Extract clauses
       b. Extract mentions (with vocabularies)
       c. Extract facts (using mentions)
    4. Generate typed relations between facts
    5. Add fact nodes and relation edges to graph
    """
    graph = build_chunk_graph(doc_id, chunks, ...)
    
    if vocabularies is None:
        vocabularies = load_vocabulary_from_graph_data(graph.to_dict(), ...)
    
    facts = []
    for chunk in chunks:
        clauses = extract_clause_units(chunk)
        for clause in clauses:
            mentions = extract_mentions(clause, vocabularies=vocabularies)
            clause_facts = extract_rule_facts(clause, mentions, ...)
            facts.extend(clause_facts)
    
    relations = generate_fact_relations(facts, chunks, ...)
    
    # Add to graph...
    return graph
```

### Benchmark Evaluation (Query-Side Traversal)

**File:** `experiments/rule_fact_benchmark_eval.py`

```python
def _seed_facts(fact_nodes, query_mentions):
    """
    Seed traversal from facts matching query mentions.
    
    Matching logic:
    - role: terms → match against fact scope
    - level: terms → match against LEVEL_GATE facts
    - mechanic: terms → match against subject/object/condition
    """
    for fact_id, payload in fact_nodes.items():
        scope = payload.get("scope", "").lower()
        
        # Role-based seeding
        if role_terms and any(term in scope for term in role_terms):
            seeds.add(fact_id)
        
        # Level-based seeding
        if fact_type == "level_gate" and level_terms:
            if any(level in str(obj) for level in level_terms):
                seeds.add(fact_id)
        
        # Mechanic-based seeding
        if mechanic_terms:
            if subject in mechanic_terms:
                seeds.add(fact_id)
            elif any(name in obj_text or name in condition for name in mechanic_names):
                seeds.add(fact_id)

def _traverse(seeds, adjacency, max_hops=3):
    """BFS traversal from seed facts using typed relation edges."""
    visited = set(seeds)
    queue = deque([(seed, 0) for seed in seeds])
    while queue:
        node, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for neighbor in adjacency.get(node, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))
    return visited
```

---

## Strengths

### 1. System-Agnostic Design

All entity vocabularies derived from data, not hardcoded:

```python
DEFAULT_MENTION_TYPE_MAPPINGS = {
    "role": {"ancestry", "class", "archetype", ...},
    "mechanic": {"feat", "spell", "ability", ...},
}
# Works for SF2e, PF2e, D&D 5e without modification
```

### 2. First-Class Failure Semantics

Failure states are explicit nodes, not inferred:

```python
# Instead of: success → (absence = failure)
# We have:   success ←CONTRASTS_WITH→ failure
#            failure ←OVERRIDDEN_BY→ override
```

### 3. Deterministic Extraction

All extraction is pattern-based and reproducible:
- Same input → same ClauseUnits → same Mentions → same Facts → same Relations

### 4. Traceability

Complete provenance chain:

```
RuleFact.fact_id → clause_id → parent_chunk_id → page, section_path
         ↓
    mention_ids → span_offsets (exact text location)
         ↓
    evidence_span → original pattern match
```

### 5. Query-Side Only Changes

Benchmark improvements don't touch ingestion:
- Safer iteration
- No contamination of extraction pipelines
- Fast experimentation

### 6. Typed Relations with Confidence

```python
FactRelation(
    relation_type=RelationType.APPLIES_TO_ROLE,
    inference_method="scope",
    confidence=0.6,  # Lower than same-clause patterns
)
```

---

## Weaknesses and Known Limitations

### 1. Mechanic Vocabulary Noise

Table and section content introduces high-entropy tokens:

```
# From vocabulary:
"level", "fire", "damage", "target", "range"
# These match everywhere, not just mechanic names
```

### 2. Mechanic Titles Not in RuleFact Fields

**This is the primary bottleneck.**

```
Query mentions: mechanic:vent gas, role:barathu
RuleFact:
  subject: None (or generic)
  object: "release gas from vents"  # NOT "Vent Gas"
  
# The mechanic NAME is in the section header, not the clause text
```

### 3. Table-Driven Mechanics

Many mechanics exist only in table cells:

```
| Feat Name    | Prerequisites | Description |
| Vent Gas     | Barathu       | Release...  |

# "Vent Gas" is in TableCell, facts come from Description prose
```

### 4. Inconsistent Chunk Titles

```python
# Some chunks have explicit feat/spell titles
chunk.content_kind = "feat"
chunk.text = "**Feat Name** [reaction]\nDescription..."

# Others have titles only in section_path
chunk.content_kind = "rule"
chunk.section_path = ["Feats", "Feat Name"]
```

### 5. Seeding Brittleness

Even with query mentions, no facts are reachable if:
- Mechanic name not in subject/object/condition
- Role scope not populated
- Level gate pattern didn't match

### 6. Cross-Section Relation Sparsity

```python
# Facts link via shared role:lashunta
# But if fact.scope is empty, no cross-section link is created
```

### 7. Benchmark Recall: 0/28

Despite working extraction and traversal:

| Query | Mentions Found | Seeds | Reachable Facts | Gold Found |
|-------|---------------|-------|-----------------|------------|
| blind_001_01 | role:barathu | 3 | 5 | 0/3 |
| blind_001_02 | role:lashunta, level:9 | 0 | 0 | 0/5 |
| blind_001_03 | mechanic:redirect current | 0 | 0 | 0/3 |

---

## File Reference

### Core Pipeline Files

| File | Lines | Purpose |
|------|-------|---------|
| `enrichment/clause_units.py` | 323 | Phase 1: Sentence splitting |
| `enrichment/mentions.py` | 300 | Phase 2: Pattern matching |
| `enrichment/vocabulary_loader.py` | 474 | Phase 2: Graph-derived vocab |
| `enrichment/mention_type_inference.py` | 225 | Phase 2: Auto-mapping |
| `enrichment/rule_facts.py` | 903 | Phase 3: Fact extraction |
| `enrichment/fact_relations.py` | 559 | Phase 4: Typed edges |
| `enrichment/graph_builder.py` | 1320+ | Integration + build_fact_graph |

### Test Files

| File | Tests | Status |
|------|-------|--------|
| `tests/test_clause_units.py` | 25 | ✅ Passing |
| `tests/test_mentions.py` | 47 | ✅ Passing |
| `tests/test_rule_facts.py` | 57 | ✅ 57 passing, 4 skipped |
| `tests/test_mention_type_inference.py` | - | ✅ Passing |

### Experiment Files

| File | Purpose |
|------|---------|
| `experiments/rule_fact_benchmark_eval.py` | End-to-end benchmark |
| `experiments/fact_traversal_test.py` | Traversal validation |
| `experiments/mention_retrieval_test.py` | Mention-based indexing |

### Handoff Documents

| File | Content |
|------|---------|
| `handoffs/HANDOFF-ClauseUnit-Extraction-Phase1.md` | Phase 1 design |
| `handoffs/HANDOFF-Mention-Extraction-Phase2.md` | Phase 2 design |
| `handoffs/HANDOFF-RuleFact-Extraction-Phase3.md` | Phase 3 design |
| `handoffs/HANDOFF-TypedRelations-Phase4.md` | Phase 4 design |
| `handoffs/PROGRESS-Phase4-Query-Mechanic-Mentions.md` | Current status |

---

## Next Steps (From Progress Report)

### 1. Stabilize Mechanic Vocabularies

Tighten title extraction to capture mechanic names while suppressing:
- Generic tokens ("level", "fire", "damage")
- Role names (already in role vocabulary)
- Single-word tokens that are part of multi-word mechanics

### 2. Improve Mechanic-to-Fact Alignment

**Root cause fix:** Propagate mechanic titles into RuleFact subjects during extraction.

```python
# If section_path[-1] is a known mechanic title:
subject_hint = section_path[-1].lower()
facts = extract_rule_facts(clause, mentions, subject_hint=subject_hint)
```

### 3. Resolve Table-Driven Mechanics

Map table rows to explicit mechanic entities:
- Extract mechanic name from first column
- Apply as subject hint for facts from description column

### 4. Consider Section Header Propagation

When a SectionHeader chunk contains a mechanic name, propagate to subsequent Text chunks as subject_hint.

---

## Conclusion

The Fact-Based Retrieval Architecture successfully implements:
- Sentence-level clause extraction (Phase 1)
- Semantic mention extraction with graph-derived vocabularies (Phase 2)
- Pattern-based RuleFact extraction with first-class failure semantics (Phase 3)
- Typed relation generation with hybrid gating (Phase 4)

The current bottleneck is **fact alignment**: mechanic names from queries cannot find corresponding facts because mechanic titles are not encoded in RuleFact subject/object fields.

The path forward is **not more query heuristics**—it is improving how mechanic titles propagate into RuleFacts during ingestion, while maintaining the system-agnostic, deterministic principles that make this architecture portable across TTRPG systems.
