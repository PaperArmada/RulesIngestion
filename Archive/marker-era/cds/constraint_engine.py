"""
CDS Constraint Engine v0.2

A late-only constraint engine that enforces UNKNOWN-default semantics.
Constraints are evaluated on already-retrieved candidates; they never
alter retrieval, seeding, or expansion.

Key invariants:
- UNKNOWN never denies (only explicit DENY denies)
- Conflict resolution returns A_OVER_B, B_OVER_A, or UNKNOWN (no scores)
- T3: If baseline had gold reachable, admissibility must not filter all gold
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


# -------------------------
# Core enums (explicit)
# -------------------------


class QueryIntent(str, Enum):
    DEFINITION = "definition"
    PROCEDURE = "procedure"
    CONSTRAINT = "constraint"
    LOOKUP = "lookup"
    EXAMPLE_REQUEST = "example_request"
    UNKNOWN = "unknown"


class AdmissibilityDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class ConflictDecision(str, Enum):
    A_OVER_B = "A_OVER_B"
    B_OVER_A = "B_OVER_A"
    UNKNOWN = "UNKNOWN"


class LayoutTier(str, Enum):
    """Spec-aligned layout channel (CDS schema §3.2)."""

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
    """Spec-aligned section role (CDS schema §3.1)."""

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
    """Spec-aligned content kind (CDS schema §3.3)."""

    PROCEDURE = "procedure"
    RULE = "rule"
    DEFINITION = "definition"
    EXAMPLE = "example"
    REFERENCE = "reference"
    TABLE = "table"
    NARRATIVE = "narrative"
    UNKNOWN = "unknown"


# -------------------------
# Query context (late-only)
# -------------------------


@dataclass(frozen=True)
class QueryContext:
    intent: QueryIntent
    flags: Dict[str, bool]

    def __post_init__(self) -> None:
        # Ensure flags is a proper dict (frozen=True means we can't modify)
        object.__setattr__(self, "flags", dict(self.flags) if self.flags else {})


# -------------------------
# ChunkFacts (observed only)
# -------------------------


@dataclass(frozen=True)
class ChunkFacts:
    """
    Observed facts about a chunk. Only fields that are:
    - Explicitly present in ingestion metadata, OR
    - Deterministic transforms of explicit metadata with no semantic guess

    No inferred signals (voice, chapter role, etc.) are allowed here.
    """

    chunk_id: str
    section_id: str
    ordinal: int

    # layout
    block_type: str
    container_type: Optional[str]
    is_callout: Optional[bool]
    page: Optional[int]

    # explicit rhetoric (from anchored label patterns)
    has_example_label: bool
    has_variant_label: bool
    has_definition_label: bool

    # explicit references (resolved_section_id, confidence)
    explicit_section_refs: Tuple[Tuple[Optional[str], str], ...]

    # Spec-aligned derived fields (Authority Legibility; default for backward compat)
    section_path: Tuple[str, ...] = ()
    layout_tier: LayoutTier = LayoutTier.UNKNOWN
    content_kind: ContentKind = ContentKind.UNKNOWN
    section_role: SectionRole = SectionRole.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "chunk_id": self.chunk_id,
            "section_id": self.section_id,
            "ordinal": self.ordinal,
            "layout": {
                "block_type": self.block_type,
                "container_type": self.container_type,
                "is_callout": self.is_callout,
                "page": self.page,
            },
            "rhetoric_explicit": {
                "has_example_label": self.has_example_label,
                "has_variant_label": self.has_variant_label,
                "has_definition_label": self.has_definition_label,
            },
            "references_explicit": {
                "explicit_section_refs": [
                    {
                        "raw_text": "",  # Not stored in ChunkFacts for compactness
                        "resolved_section_id": ref[0],
                        "resolution_confidence": ref[1],
                    }
                    for ref in self.explicit_section_refs
                ],
                "explicit_page_refs": [],  # Page refs extracted separately
            },
            "provenance": {
                "derived_from": ["enriched_chunk"],
                "notes": "Built from EnrichedChunk via chunk_facts_adapter",
            },
            "section_path": list(self.section_path),
            "layout_tier": self.layout_tier.value,
            "content_kind": self.content_kind.value,
            "section_role": self.section_role.value,
        }


# -------------------------
# Conservative intent classifier
# -------------------------

# Patterns ordered for specificity (more specific first)
_INTENT_PATTERNS: List[Tuple[QueryIntent, re.Pattern[str]]] = [
    (
        QueryIntent.EXAMPLE_REQUEST,
        re.compile(
            r"^\s*(give|show)\s+me\s+an?\s+example\b|"
            r"\bexample\s+of\b|"
            r"^\s*example\s*:",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.DEFINITION,
        re.compile(
            r"^\s*(what\s+is|what\s+are|define|meaning\s+of|what\s+does\s+\S+\s+mean)\b",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.PROCEDURE,
        re.compile(
            r"^\s*(how\s+do\s+i|how\s+to|steps?\s+to|how\s+does)\b",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.CONSTRAINT,
        re.compile(
            r"\b(can\s+i|may\s+i|must\s+i|is\s+it\s+allowed|am\s+i\s+allowed|"
            r"is\s+\S+\s+allowed|are\s+\S+\s+allowed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.LOOKUP,
        re.compile(
            r"\b(table\b|dc\b|cost\b|damage\b|range\b|duration\b|"
            r"what\s+is\s+the\s+dc|what\s+is\s+the\s+cost|"
            r"how\s+much\s+does)\b",
            re.IGNORECASE,
        ),
    ),
]


def derive_query_context(
    question_text: str, flags: Optional[Dict[str, bool]] = None
) -> QueryContext:
    """
    Conservatively classify query intent from question text.

    Returns UNKNOWN if:
    - No patterns match
    - Multiple patterns match (ambiguous)
    """
    flags = dict(flags or {})
    text = question_text or ""

    hits: List[QueryIntent] = []
    for intent, pat in _INTENT_PATTERNS:
        if pat.search(text):
            hits.append(intent)

    # Conservative: if 0 or >1 intents match, return UNKNOWN (no denials apply)
    if len(hits) == 1:
        return QueryContext(intent=hits[0], flags=flags)
    return QueryContext(intent=QueryIntent.UNKNOWN, flags=flags)


# -------------------------
# Rule interfaces
# -------------------------


class AdmissibilityRule:
    """Base class for admissibility rules."""

    rule_id: str

    def decide(self, ctx: QueryContext, chunk: ChunkFacts) -> AdmissibilityDecision:
        raise NotImplementedError


class ConflictRule:
    """Base class for conflict resolution rules."""

    rule_id: str

    def compare(
        self, ctx: QueryContext, a: ChunkFacts, b: ChunkFacts
    ) -> ConflictDecision:
        raise NotImplementedError


# -------------------------
# Minimal safe rules (explicit-only)
# -------------------------


class DenyExplicitExamplesForNonExampleQueries(AdmissibilityRule):
    """A1: Non-example queries deny explicitly labeled examples."""

    rule_id = "A1_deny_explicit_examples_non_example_queries"

    def decide(self, ctx: QueryContext, chunk: ChunkFacts) -> AdmissibilityDecision:
        if ctx.intent in {
            QueryIntent.DEFINITION,
            QueryIntent.PROCEDURE,
            QueryIntent.CONSTRAINT,
            QueryIntent.LOOKUP,
        }:
            if chunk.has_example_label is True:
                return AdmissibilityDecision.DENY
        return AdmissibilityDecision.UNKNOWN


class AllowExplicitExamplesForExampleRequests(AdmissibilityRule):
    """A0: Example-only queries can allow examples."""

    rule_id = "A0_allow_explicit_examples_example_request"

    def decide(self, ctx: QueryContext, chunk: ChunkFacts) -> AdmissibilityDecision:
        if ctx.intent == QueryIntent.EXAMPLE_REQUEST:
            if chunk.has_example_label is True:
                return AdmissibilityDecision.ALLOW
        return AdmissibilityDecision.UNKNOWN


class DenyExplicitVariantsUnlessAllowed(AdmissibilityRule):
    """A2: Variant rules are inadmissible unless user asked for variants."""

    rule_id = "A2_deny_explicit_variants_unless_allowed"

    # Container types that indicate variant/optional rules
    VARIANT_CONTAINER_TYPES = {"variantbox", "optionalrule", "alternaterule"}

    def decide(self, ctx: QueryContext, chunk: ChunkFacts) -> AdmissibilityDecision:
        # If intent unknown, do not deny.
        if ctx.intent == QueryIntent.UNKNOWN:
            return AdmissibilityDecision.UNKNOWN

        allow_variants = bool(ctx.flags.get("allow_variants", False))
        if allow_variants:
            return AdmissibilityDecision.UNKNOWN

        if chunk.has_variant_label is True:
            return AdmissibilityDecision.DENY

        # If parser marks a variant container type, it is still "explicit markup"
        if chunk.container_type is not None:
            if chunk.container_type.lower() in self.VARIANT_CONTAINER_TYPES:
                return AdmissibilityDecision.DENY

        return AdmissibilityDecision.UNKNOWN


class AllowTablesForLookup(AdmissibilityRule):
    """A3: Lookup queries allow tables/references."""

    rule_id = "A3_allow_tables_lookup"

    def decide(self, ctx: QueryContext, chunk: ChunkFacts) -> AdmissibilityDecision:
        if ctx.intent == QueryIntent.LOOKUP:
            if chunk.block_type.lower() == "table":
                return AdmissibilityDecision.ALLOW
        return AdmissibilityDecision.UNKNOWN


class DenyLayoutTierExampleVariantForNonExampleQueries(AdmissibilityRule):
    """
    A4: Drop example_box/variant_box layout tiers unless query asks for example/variant.

    Phase3 §3.1 alignment. Only denies when layout_tier is explicitly EXAMPLE_BOX or
    VARIANT_BOX (not UNKNOWN). Conservative: if layout_tier is UNKNOWN, returns UNKNOWN.
    """

    rule_id = "A4_deny_layout_tier_example_variant_non_example"

    def decide(self, ctx: QueryContext, chunk: ChunkFacts) -> AdmissibilityDecision:
        if ctx.intent == QueryIntent.UNKNOWN:
            return AdmissibilityDecision.UNKNOWN
        if ctx.intent == QueryIntent.EXAMPLE_REQUEST or ctx.flags.get("allow_variants"):
            return AdmissibilityDecision.UNKNOWN
        tier = getattr(chunk, "layout_tier", None) or LayoutTier.UNKNOWN
        if tier == LayoutTier.UNKNOWN:
            return AdmissibilityDecision.UNKNOWN
        if tier in (LayoutTier.EXAMPLE_BOX, LayoutTier.VARIANT_BOX):
            return AdmissibilityDecision.DENY
        return AdmissibilityDecision.UNKNOWN


class NonExampleOutranksExample(ConflictRule):
    """C0: Core text outranks explicit examples."""

    rule_id = "C0_non_example_outranks_example"

    def compare(
        self, ctx: QueryContext, a: ChunkFacts, b: ChunkFacts
    ) -> ConflictDecision:
        a_is_ex = a.has_example_label is True
        b_is_ex = b.has_example_label is True
        if a_is_ex != b_is_ex:
            return ConflictDecision.B_OVER_A if a_is_ex else ConflictDecision.A_OVER_B
        return ConflictDecision.UNKNOWN


class NonVariantOutranksVariantUnlessAllowed(ConflictRule):
    """C1: Non-variant outranks variant (unless allow_variants true)."""

    rule_id = "C1_non_variant_outranks_variant_unless_allowed"

    VARIANT_CONTAINER_TYPES = {"variantbox", "optionalrule", "alternaterule"}

    def _is_variant(self, chunk: ChunkFacts) -> bool:
        if chunk.has_variant_label is True:
            return True
        if chunk.container_type is not None:
            if chunk.container_type.lower() in self.VARIANT_CONTAINER_TYPES:
                return True
        return False

    def compare(
        self, ctx: QueryContext, a: ChunkFacts, b: ChunkFacts
    ) -> ConflictDecision:
        if bool(ctx.flags.get("allow_variants", False)):
            return ConflictDecision.UNKNOWN

        a_is_var = self._is_variant(a)
        b_is_var = self._is_variant(b)
        if a_is_var != b_is_var:
            return ConflictDecision.B_OVER_A if a_is_var else ConflictDecision.A_OVER_B
        return ConflictDecision.UNKNOWN


class ResolvedUniqueReferenceOutranksLocal(ConflictRule):
    """
    C3: Explicit deferral / reference outranks local text.

    If chunk A contains an explicit, uniquely-resolved section reference to B's section,
    then B outranks A (B is the deferred authority).
    """

    rule_id = "C3_resolved_unique_reference_outranks_local"

    def compare(
        self, ctx: QueryContext, a: ChunkFacts, b: ChunkFacts
    ) -> ConflictDecision:
        # Only if A explicitly references B's section with resolved_unique confidence
        for resolved_section_id, confidence in a.explicit_section_refs:
            if confidence == "resolved_unique" and resolved_section_id is not None:
                if resolved_section_id == b.section_id:
                    return ConflictDecision.B_OVER_A

        # Symmetric check: if B references A's section, then A outranks B
        for resolved_section_id, confidence in b.explicit_section_refs:
            if confidence == "resolved_unique" and resolved_section_id is not None:
                if resolved_section_id == a.section_id:
                    return ConflictDecision.A_OVER_B

        return ConflictDecision.UNKNOWN


# -------------------------
# Constraint engine (late-only)
# -------------------------


@dataclass
class ConstraintEngine:
    """
    Late-only constraint engine.

    Operates only on already-retrieved candidate sets.
    Never alters retrieval, seeding, or expansion.
    """

    admissibility_rules: List[AdmissibilityRule]
    conflict_rules: List[ConflictRule]

    def admissibility(
        self, ctx: QueryContext, chunk: ChunkFacts
    ) -> AdmissibilityDecision:
        """
        Evaluate admissibility for a single chunk.

        UNKNOWN-default invariant:
        - Only explicit DENY denies.
        - UNKNOWN does not deny.
        - ALLOW can be used for positive selection but must not be required.
        """
        decisions: List[AdmissibilityDecision] = []
        for r in self.admissibility_rules:
            try:
                decisions.append(r.decide(ctx, chunk))
            except Exception:
                # Safety: any rule failure becomes UNKNOWN (never denies).
                decisions.append(AdmissibilityDecision.UNKNOWN)

        # Priority: DENY > ALLOW > UNKNOWN
        if AdmissibilityDecision.DENY in decisions:
            return AdmissibilityDecision.DENY
        if AdmissibilityDecision.ALLOW in decisions:
            return AdmissibilityDecision.ALLOW
        return AdmissibilityDecision.UNKNOWN

    def filter_candidates(
        self, ctx: QueryContext, candidates: Sequence[ChunkFacts]
    ) -> List[ChunkFacts]:
        """
        Late-only admissibility filter.

        Returns candidates that are not explicitly DENY'd.
        """
        kept: List[ChunkFacts] = []
        for c in candidates:
            d = self.admissibility(ctx, c)
            if d == AdmissibilityDecision.DENY:
                continue
            kept.append(c)
        return kept

    def compare(
        self, ctx: QueryContext, a: ChunkFacts, b: ChunkFacts
    ) -> ConflictDecision:
        """
        Compare two chunks for conflict resolution.

        UNKNOWN-default invariant: no inferred ordering.
        First rule to return non-UNKNOWN wins.
        """
        for r in self.conflict_rules:
            try:
                d = r.compare(ctx, a, b)
            except Exception:
                d = ConflictDecision.UNKNOWN
            if d != ConflictDecision.UNKNOWN:
                return d
        return ConflictDecision.UNKNOWN

    def select(
        self, ctx: QueryContext, candidates: Sequence[ChunkFacts]
    ) -> Optional[ChunkFacts]:
        """
        Deterministic selection from candidate pool.

        - Start with baseline order provided by retrieval (do not reorder globally).
        - Optionally drop DENY (filter_candidates).
        - Apply pairwise conflict rules only as local dominance checks.
        - If UNKNOWN everywhere, keep the first candidate in baseline order.
        """
        pool = self.filter_candidates(ctx, candidates)
        if not pool:
            return None

        winner = pool[0]
        for challenger in pool[1:]:
            d = self.compare(ctx, winner, challenger)
            if d == ConflictDecision.B_OVER_A:
                winner = challenger
            elif d == ConflictDecision.A_OVER_B:
                pass
            else:
                # UNKNOWN: do nothing; baseline stability preserved.
                pass
        return winner


# -------------------------
# T3 Harness (non-regression guard)
# -------------------------


@dataclass(frozen=True)
class T3Result:
    """Result of T3 enforcement check for a single query."""

    query_id: str
    passed: bool
    reason: str
    baseline_has_gold: bool
    filtered_has_gold: bool
    baseline_candidate_count: int
    filtered_candidate_count: int


def enforce_t3_for_query(
    query_id: str,
    ctx: QueryContext,
    engine: ConstraintEngine,
    candidates_k: Sequence[ChunkFacts],
    gold_chunk_ids: Set[str],
) -> T3Result:
    """
    T3: If baseline candidate set K contains any gold, admissibility must not filter all gold out.

    - This does NOT require selection to pick gold.
    - This only guards the admissibility layer from destroying reachability.
    """
    baseline_ids = [c.chunk_id for c in candidates_k]
    baseline_gold = any(cid in gold_chunk_ids for cid in baseline_ids)

    filtered = engine.filter_candidates(ctx, candidates_k)
    filtered_ids = [c.chunk_id for c in filtered]
    filtered_gold = any(cid in gold_chunk_ids for cid in filtered_ids)

    if baseline_gold and not filtered_gold:
        return T3Result(
            query_id=query_id,
            passed=False,
            reason="T3 violation: baseline had gold reachable, admissibility filtered all gold candidates.",
            baseline_has_gold=True,
            filtered_has_gold=False,
            baseline_candidate_count=len(baseline_ids),
            filtered_candidate_count=len(filtered_ids),
        )

    return T3Result(
        query_id=query_id,
        passed=True,
        reason="ok",
        baseline_has_gold=baseline_gold,
        filtered_has_gold=filtered_gold,
        baseline_candidate_count=len(baseline_ids),
        filtered_candidate_count=len(filtered_ids),
    )


def enforce_t3_suite(
    suite: Iterable[
        Tuple[str, str, Sequence[ChunkFacts], Set[str], Optional[Dict[str, bool]]]
    ],
    engine: ConstraintEngine,
) -> List[T3Result]:
    """
    Enforce T3 across a test suite.

    suite items: (query_id, question_text, candidates_k, gold_chunk_ids, flags)
    - candidates_k must be produced by baseline retrieval and passed in unchanged (late-only).
    """
    results: List[T3Result] = []
    for query_id, question_text, candidates_k, gold_ids, flags in suite:
        ctx = derive_query_context(question_text, flags=flags)
        results.append(
            enforce_t3_for_query(query_id, ctx, engine, candidates_k, gold_ids)
        )
    return results


# -------------------------
# Engine factory (minimal)
# -------------------------


def compute_als_from_chunk_facts_dicts(
    chunk_facts_dicts: List[Dict[str, Any]]
) -> Dict[str, float]:
    """
    Compute ALS from chunk_facts dicts (e.g. from CDS payload).

    Checks layout_tier, section_role, content_kind for non-unknown values.
    """
    n = len(chunk_facts_dicts)
    if n == 0:
        return {
            "ALS": 1.0,
            "layout_coverage_rate": 1.0,
            "section_role_coverage_rate": 1.0,
            "content_kind_coverage_rate": 1.0,
        }
    layout_ok = sum(
        1
        for c in chunk_facts_dicts
        if c.get("layout_tier", "unknown") not in ("unknown", "")
    )
    role_ok = sum(
        1
        for c in chunk_facts_dicts
        if c.get("section_role", "unknown") not in ("unknown", "")
    )
    kind_ok = sum(
        1
        for c in chunk_facts_dicts
        if c.get("content_kind", "unknown") not in ("unknown", "")
    )
    missing = n - min(layout_ok, role_ok, kind_ok)
    return {
        "ALS": 1.0 - (missing / n),
        "layout_coverage_rate": layout_ok / n,
        "section_role_coverage_rate": role_ok / n,
        "content_kind_coverage_rate": kind_ok / n,
    }


# Authority key dominance ranks (Phase3 §3.2; higher = more authoritative)
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
    """
    Lexicographic tuple for precedence (Phase3 §3.2).

    Higher = more authoritative. Used for tie-breaking when conflict rules
    return UNKNOWN.
    """
    sr = getattr(cf, "section_role", SectionRole.UNKNOWN) or SectionRole.UNKNOWN
    lt = getattr(cf, "layout_tier", LayoutTier.UNKNOWN) or LayoutTier.UNKNOWN
    ck = getattr(cf, "content_kind", ContentKind.UNKNOWN) or ContentKind.UNKNOWN
    depth = len(getattr(cf, "section_path", ()) or ())
    return (
        SECTION_ROLE_RANK.get(sr, -1),
        LAYOUT_TIER_RANK.get(lt, -1),
        CONTENT_KIND_RANK.get(ck, -1),
        depth,
        cf.chunk_id,
    )


def compute_als(chunk_facts_list: List[ChunkFacts]) -> Dict[str, float]:
    """
    Compute Authority Legibility Score and coverage rates (Authority Legibility §6).

    Returns dict with ALS, layout_coverage_rate, section_role_coverage_rate,
    content_kind_coverage_rate. Used for corpus-level diagnostics.
    """
    n = len(chunk_facts_list)
    if n == 0:
        return {
            "ALS": 1.0,
            "layout_coverage_rate": 1.0,
            "section_role_coverage_rate": 1.0,
            "content_kind_coverage_rate": 1.0,
        }
    layout_ok = sum(
        1
        for c in chunk_facts_list
        if getattr(c, "layout_tier", LayoutTier.UNKNOWN) != LayoutTier.UNKNOWN
    )
    role_ok = sum(
        1
        for c in chunk_facts_list
        if getattr(c, "section_role", SectionRole.UNKNOWN) != SectionRole.UNKNOWN
    )
    kind_ok = sum(
        1
        for c in chunk_facts_list
        if getattr(c, "content_kind", ContentKind.UNKNOWN) != ContentKind.UNKNOWN
    )
    missing = n - min(layout_ok, role_ok, kind_ok)
    return {
        "ALS": 1.0 - (missing / n),
        "layout_coverage_rate": layout_ok / n,
        "section_role_coverage_rate": role_ok / n,
        "content_kind_coverage_rate": kind_ok / n,
    }


def build_minimal_engine() -> ConstraintEngine:
    """
    Build a minimal constraint engine with safe, explicit-only rules.

    These rules only trigger on explicitly labeled content:
    - Explicit "Example:" labels
    - Explicit "Variant/Optional/Alternative" labels
    - Parser-emitted container types
    """
    admissibility = [
        AllowExplicitExamplesForExampleRequests(),
        DenyExplicitExamplesForNonExampleQueries(),
        DenyExplicitVariantsUnlessAllowed(),
        DenyLayoutTierExampleVariantForNonExampleQueries(),
        AllowTablesForLookup(),
    ]
    conflict = [
        ResolvedUniqueReferenceOutranksLocal(),
        NonVariantOutranksVariantUnlessAllowed(),
        NonExampleOutranksExample(),
    ]
    return ConstraintEngine(
        admissibility_rules=admissibility, conflict_rules=conflict
    )
