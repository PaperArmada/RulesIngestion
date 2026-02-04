# CDS v0.2 → Spec Alignment: Concrete Change Proposals

**Date:** 2026-02-02  
**Prerequisite:** `CDS_V02_TO_SPECS_MAPPING.md`

---

## Phase A: Foundation (Low-Risk Enum + Path Alignment)

**Goal:** Add spec-compliant enums and store `section_path` per chunk without changing runtime behavior. No T3 risk.

### A1. Add LayoutTier, SectionRole, ContentKind enums

**File:** `cds/constraint_engine.py` (or new `cds/enums.py`)

```python
# Add after QueryIntent enum
class LayoutTier(str, Enum):
    MAIN = "main"
    SIDEBAR = "sidebar"
    CALLOUT = "callout"
    EXAMPLE_BOX = "example_box"
    VARIANT_BOX = "variant_box"
    FOOTNOTE = "footnote"
    TABLE = "table"
    CAPTION = "caption"
    UNKNOWN = "unknown"

class SectionRole(str, Enum):
    CORE_RULES = "core_rules"
    INTRO = "intro"
    GLOSSARY = "glossary"
    SUMMARY = "summary"
    OPTIONS = "options"
    VARIANTS = "variants"
    EXAMPLES = "examples"
    REFERENCE = "reference"
    OTHER = "other"
    UNKNOWN = "unknown"

class ContentKind(str, Enum):
    PROCEDURE = "procedure"
    RULE = "rule"
    DEFINITION = "definition"
    EXAMPLE = "example"
    REFERENCE = "reference"
    TABLE = "table"
    NARRATIVE = "narrative"
    UNKNOWN = "unknown"
```

**Effort:** ~30 min

---

### A2. Derive LayoutTier and ContentKind from existing ChunkFacts

**File:** `cds/chunk_facts_adapter.py`

Add deterministic derivation (no new inference surface):

```python
def _derive_layout_tier(chunk: Dict[str, Any], section_path: List[str]) -> LayoutTier:
    bt = (chunk.get("block_type") or "Text").lower()
    ct = (chunk.get("container_type") or "").lower()
    # Parser-emitted or explicit container types
    if ct in {"examplebox", "example_box"}: return LayoutTier.EXAMPLE_BOX
    if ct in {"variantbox", "variant_box", "optionalrule"}: return LayoutTier.VARIANT_BOX
    if chunk.get("is_callout"): return LayoutTier.CALLOUT
    if bt == "table": return LayoutTier.TABLE
    # Section path keywords (explicit structure)
    for s in section_path:
        sl = s.lower()
        if "example" in sl or "sample" in sl: return LayoutTier.EXAMPLE_BOX
        if "variant" in sl or "optional" in sl: return LayoutTier.VARIANT_BOX
    return LayoutTier.MAIN  # default

def _derive_content_kind(
    has_example: bool, has_variant: bool, has_def: bool, block_type: str
) -> ContentKind:
    if has_example: return ContentKind.EXAMPLE
    if has_variant: return ContentKind.RULE  # variant rules are still rules
    if has_def: return ContentKind.DEFINITION
    if (block_type or "").lower() == "table": return ContentKind.TABLE
    return ContentKind.RULE  # default for main text
```

**File:** `cds/constraint_engine.py` — extend `ChunkFacts`:

```python
# Add optional fields (default UNKNOWN for backward compat)
layout_tier: LayoutTier = LayoutTier.UNKNOWN
content_kind: ContentKind = ContentKind.UNKNOWN
section_role: SectionRole = SectionRole.UNKNOWN
section_path: Tuple[str, ...] = ()  # full path for address
```

**Effort:** ~1 hr

---

### A3. Store section_path in ChunkFacts

**File:** `cds/chunk_facts_adapter.py` — `build_chunk_facts`:

- Pass resolved `section_path` (list) into ChunkFacts.
- In `ChunkFacts`, add `section_path: Tuple[str, ...]` (already proposed in A2).

**File:** `cds/cds_builder.py` — ensure chunk dict passed to `build_chunk_facts` has `section_path` populated (already done via `_get_resolved_section_path`).

**File:** `experiments/cds_v2_integration.py` — `load_chunk_facts_from_cds_payload`:

- If CDS payload includes `section_path` per chunk_facts, load it.
- Schema: add optional `section_path` to chunk_facts definition.

**Effort:** ~45 min

---

### A4. Derive SectionRole from section path (deterministic)

**File:** `cds/chunk_facts_adapter.py`:

```python
def _derive_section_role(section_path: List[str]) -> SectionRole:
    for s in section_path:
        sl = s.lower()
        if "example" in sl or "sample" in sl: return SectionRole.EXAMPLES
        if "variant" in sl or "optional" in sl or "alternate" in sl: return SectionRole.VARIANTS
        if "glossary" in sl: return SectionRole.GLOSSARY
        if "summary" in sl or "overview" in sl: return SectionRole.SUMMARY
        if "introduction" in sl or "intro" in sl: return SectionRole.INTRO
        if "reference" in sl or "index" in sl: return SectionRole.REFERENCE
    return SectionRole.CORE_RULES  # default
```

**Effort:** ~30 min

---

**Phase A summary:** Enums + derived fields. No change to admissibility/conflict logic. T3 unchanged. Enables Phase B.

---

## Phase B: LayoutTier-Based Eligibility (Phase3 §3.1)

**Goal:** Extend eligibility gate to use `layout_tier` (example_box, caption, footnote) in addition to explicit labels. Must remain conservative to satisfy T3.

### B1. Add LayoutTier-based admissibility rule

**File:** `cds/constraint_engine.py`

New rule (conservative: only deny when layout_tier is explicitly example_box/variant_box AND query is non-example):

```python
class DenyLayoutTierExampleVariantForNonExampleQueries(AdmissibilityRule):
    """Drop example_box/variant_box layout tiers unless query asks for example/variant."""
    rule_id = "A4_deny_layout_tier_example_variant_non_example"

    def decide(self, ctx: QueryContext, chunk: ChunkFacts) -> AdmissibilityDecision:
        if ctx.intent == QueryIntent.UNKNOWN:
            return AdmissibilityDecision.UNKNOWN
        if ctx.intent in {QueryIntent.EXAMPLE_REQUEST} or ctx.flags.get("allow_variants"):
            return AdmissibilityDecision.UNKNOWN
        tier = getattr(chunk, "layout_tier", None) or LayoutTier.UNKNOWN
        if tier in {LayoutTier.EXAMPLE_BOX, LayoutTier.VARIANT_BOX}:
            return AdmissibilityDecision.DENY
        return AdmissibilityDecision.UNKNOWN
```

**Integration:** Add to `build_minimal_engine()` admissibility list. Order after A1/A2 so explicit-label rules run first.

**Guard:** Only deny when `layout_tier` is _not_ UNKNOWN. If UNKNOWN, fall back to existing has_example_label/has_variant_label rules.

**Effort:** ~45 min

---

### B2. Optional: Extend to caption/footnote

Phase3 spec says drop `caption` and `footnote` unless query asks. Add only if parser provides `block_type` or `container_type` for these. Check enrichment output first.

**Effort:** ~30 min (if supported by parser)

---

**Phase B summary:** Expands eligibility without changing conflict resolution. Run T3 suite after; if T3 fails, gate new rule behind `allow_layout_tier_eligibility` flag and default off.

---

## Phase C: Authority Key and Precedence Rerank (Phase3 §3.2)

**Goal:** Implement `authority_key(chunk)` and use it for tie-breaking when conflict rules return UNKNOWN.

### C1. Implement authority_key(chunk)

**File:** New `cds/authority.py` or extend `cds/constraint_engine.py`

```python
# Dominance order: higher rank = more authoritative
SECTION_ROLE_RANK = {
    SectionRole.CORE_RULES: 7,
    SectionRole.INTRO: 6,
    SectionRole.SUMMARY: 5,
    SectionRole.GLOSSARY: 4,
    SectionRole.OPTIONS: 3,
    SectionRole.VARIANTS: 2,
    SectionRole.EXAMPLES: 1,
    SectionRole.REFERENCE: 0,
    SectionRole.OTHER: 0,
    SectionRole.UNKNOWN: -1,
}
LAYOUT_TIER_RANK = {
    LayoutTier.MAIN: 7,
    LayoutTier.SIDEBAR: 6,
    LayoutTier.CALLOUT: 5,
    LayoutTier.TABLE: 4,
    LayoutTier.EXAMPLE_BOX: 2,
    LayoutTier.VARIANT_BOX: 1,
    LayoutTier.FOOTNOTE: 0,
    LayoutTier.CAPTION: 0,
    LayoutTier.UNKNOWN: -1,
}
CONTENT_KIND_RANK = {
    ContentKind.PROCEDURE: 7,
    ContentKind.RULE: 6,
    ContentKind.DEFINITION: 5,
    ContentKind.REFERENCE: 4,
    ContentKind.TABLE: 3,
    ContentKind.EXAMPLE: 2,
    ContentKind.NARRATIVE: 1,
    ContentKind.UNKNOWN: -1,
}

def authority_key(cf: ChunkFacts) -> Tuple[int, int, int, int, str]:
    """Lexicographic tuple for precedence. Higher = more authoritative."""
    sr = getattr(cf, "section_role", SectionRole.UNKNOWN) or SectionRole.UNKNOWN
    lt = getattr(cf, "layout_tier", LayoutTier.UNKNOWN) or LayoutTier.UNKNOWN
    ck = getattr(cf, "content_kind", ContentKind.UNKNOWN) or ContentKind.UNKNOWN
    depth = len(getattr(cf, "section_path", ()) or ())
    return (
        SECTION_ROLE_RANK.get(sr, -1),
        LAYOUT_TIER_RANK.get(lt, -1),
        CONTENT_KIND_RANK.get(ck, -1),
        depth,  # structural specificity
        cf.chunk_id,  # stable tie-break
    )
```

**Effort:** ~45 min

---

### C2. Use authority_key when conflict rules return UNKNOWN

**File:** `cds/constraint_engine.py` — `ConstraintEngine.select`:

```python
def select(self, ctx: QueryContext, candidates: Sequence[ChunkFacts]) -> Optional[ChunkFacts]:
    pool = self.filter_candidates(ctx, candidates)
    if not pool:
        return None
    # Sort by authority_key descending (higher = better), then baseline order
    pool_sorted = sorted(pool, key=lambda c: (authority_key(c), -c.ordinal), reverse=True)
    # For backward compat: if all authority_keys equal, keep baseline order
    return pool_sorted[0] if pool_sorted else None
```

**Alternative (safer):** Only apply authority_key when at least one chunk has non-UNKNOWN layout_tier/section_role. Otherwise preserve baseline order. Add flag `use_authority_key_rerank: bool = True`.

**Effort:** ~30 min

---

**Phase C summary:** Enables Phase3-style precedence. Measure authority inversion rate before/after.

---

## Phase D: Diagnostics (Phase3 §5)

**Goal:** Log authority metadata and detect inversions.

### D1. Log top N candidates with authority metadata

**File:** `experiments/rule_fact_benchmark_eval.py`

In `_run_gold_gap_audit` or equivalent, when gold is reachable but not selected:

```python
if gold_in_candidates and selected_chunk_id != gold_chunk_id:
    top_n = ranked_chunks[:5]
    for cid in top_n:
        cf = cds_engine.chunk_facts_index.get(cid)
        if cf:
            meta = {
                "chunk_id": cid,
                "section_role": getattr(cf, "section_role", None),
                "layout_tier": getattr(cf, "layout_tier", None),
                "content_kind": getattr(cf, "content_kind", None),
                "ordinal": cf.ordinal,
            }
            logger.info("CDS candidate: %s", meta)
```

**Effort:** ~30 min

---

### D2. Log if gold filtered by eligibility

**File:** `experiments/cds_v2_integration.py` — `BenchmarkConstraintEngine.filter_candidates`:

- Return `(kept, rejected)` where `rejected` maps chunk_id → reason.
- In benchmark, if gold_chunk_id in rejected, log: `"T3 audit: gold filtered by eligibility"` + reason.

**Effort:** ~20 min (already returns rejected in some paths; ensure gold-filtered case is logged)

---

### D3. Authority inversion detection

**File:** `experiments/rule_fact_benchmark_eval.py`

When gold in candidates, selected != gold, and `use_authority_key_rerank`:

```python
gold_cf = cds_engine.chunk_facts_index.get(gold_chunk_id)
sel_cf = cds_engine.chunk_facts_index.get(selected_chunk_id)
if gold_cf and sel_cf:
    if authority_key(gold_cf) > authority_key(sel_cf):
        logger.warning("Authority inversion: gold > selected for query %s", query_id)
```

**Effort:** ~30 min

---

**Phase D summary:** Observability without behavior change. Enables debugging and metric tracking.

---

## Phase E: ALS and Coverage Metrics (Authority Legibility §6)

**Goal:** Compute Authority Legibility Score and coverage rates for diagnostics.

### E1. Add compute_als() function

**File:** `cds/authority.py` or `cds/constraint_engine.py`

```python
def compute_als(chunk_facts_list: List[ChunkFacts]) -> Dict[str, float]:
    n = len(chunk_facts_list)
    if n == 0:
        return {"ALS": 1.0, "layout_coverage": 1.0, "section_role_coverage": 1.0, "content_kind_coverage": 1.0}
    layout_ok = sum(1 for c in chunk_facts_list if getattr(c, "layout_tier", None) != LayoutTier.UNKNOWN)
    role_ok = sum(1 for c in chunk_facts_list if getattr(c, "section_role", None) != SectionRole.UNKNOWN)
    kind_ok = sum(1 for c in chunk_facts_list if getattr(c, "content_kind", None) != ContentKind.UNKNOWN)
    missing = n - min(layout_ok, role_ok, kind_ok)  # conservative
    return {
        "ALS": 1.0 - (missing / n),
        "layout_coverage_rate": layout_ok / n,
        "section_role_coverage_rate": role_ok / n,
        "content_kind_coverage_rate": kind_ok / n,
    }
```

**Effort:** ~30 min

---

### E2. Emit ALS in CDS build summary

**File:** `cds/cds_builder.py` or `merge_enriched_outputs.py`

After building CDS, call `compute_als(chunk_facts_list)` and add to summary dict / log.

**Effort:** ~15 min

---

## Phase F: Schema and Payload Extensions (CDS Schema §2)

**Goal:** Align CDS payload with spec document/section structure. Optional, lower priority.

### F1. Document-level metadata

**File:** `cds/cds_builder.py` — `build_cds_from_chunks`:

- Add `title`, `page_count` if available from run metadata.
- Add `version: "cds-0.2"`.

**Effort:** ~20 min

---

### F2. Section node: parent_section_id, depth, page_start/end

**File:** `cds/cds_builder.py` — `_build_section_nodes`:

- Compute `parent_section_id` from path (parent = path[:-1]).
- Compute `depth = len(path)`.
- `page_start`/`page_end`: requires page info per section; defer until enrichment provides it.

**Effort:** ~45 min (parent/depth); page range TBD

---

## Recommended Implementation Order

| Phase                      | Effort   | T3 Risk              | Value                          |
| -------------------------- | -------- | -------------------- | ------------------------------ |
| A (Foundation)             | ~2.5 hr  | None                 | Enables B–E                    |
| B (LayoutTier eligibility) | ~1 hr    | Low (gate with flag) | Phase3 §3.1 alignment          |
| C (Authority key)          | ~1.25 hr | Low                  | Phase3 §3.2, precedence        |
| D (Diagnostics)            | ~1.5 hr  | None                 | Debugging, inversion tracking  |
| E (ALS)                    | ~45 min  | None                 | Legibility measurement         |
| F (Schema extensions)      | ~1 hr    | None                 | Spec alignment, lower priority |

**Suggested sequence:** A → D → E (foundation + observability), then B → C (behavioral changes) with T3 runs after each.

---

## Backward Compatibility

- All new ChunkFacts fields use defaults (UNKNOWN, empty tuple) so existing CDS payloads without them still load.
- New admissibility rules are additive; existing rules unchanged.
- Authority key rerank can be disabled via `use_authority_key_rerank=False` if it regresses metrics.
