"""RuleFact extraction from ClauseUnits using Mentions as anchors.

RuleFacts are semantic atomic claims extracted from clauses, providing
typed, traversable assertions about game rules.

This is Phase 3 of the fact-based retrieval architecture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Pattern, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .clause_units import ClauseUnit
    from .mentions import Mention


class FactType(Enum):
    """Classification of fact semantics."""
    
    # Core rule facts
    GRANTS = "grants"           # Subject grants something to target
    REQUIRES = "requires"       # Subject requires condition to use
    FREQUENCY = "frequency"     # Usage/frequency limits
    MODIFIES = "modifies"       # Subject modifies target value/state
    TRIGGERS = "triggers"       # Subject causes target to happen
    PREVENTS = "prevents"       # Subject prevents target
    APPLIES_TO = "applies_to"   # Subject applies to target scope
    
    # Outcome facts (success/failure semantics)
    ON_SUCCESS = "on_success"   # What happens on success
    ON_FAILURE = "on_failure"   # What happens on failure (FIRST-CLASS)
    ON_CRITICAL = "on_critical" # Critical success/failure outcomes
    
    # Override/exception facts
    OVERRIDES = "overrides"     # Subject overrides default behavior
    INSTEAD_OF = "instead_of"   # Subject replaces target
    UNLESS = "unless"           # Exception condition
    
    # Scope/applicability facts
    LEVEL_GATE = "level_gate"   # Requires minimum level
    ROLE_GATE = "role_gate"     # Requires specific role (ancestry/class)
    TRAIT_GATE = "trait_gate"   # Requires specific trait
    
    # Partial/incomplete
    PARTIAL = "partial"         # Incomplete extraction (has gaps)
    UNKNOWN = "unknown"         # Could not classify


class Modality(Enum):
    """How mandatory is this fact?"""
    MUST = "must"               # Required, no choice
    MAY = "may"                 # Optional
    CAN = "can"                 # Capability
    AUTOMATIC = "automatic"     # Happens without choice
    CONDITIONAL = "conditional" # Depends on condition
    UNKNOWN = "unknown"


_NUMERIC_OVERRIDE_TARGET = re.compile(r"^[\s\-\+\u2013\u2014]*\d+(?:\.\d+)?%?[\s]*$")
_TEMPORAL_OVERRIDE_TARGET = re.compile(
    r"\bthe\s+previous\s+day\b|\b(previous|next)\s+(day|round|turn)\b",
    re.IGNORECASE,
)

_PROCEDURE_TARGETS = [
    ("procedure:recovery_check", re.compile(r"\brecovery check(s)?\b", re.IGNORECASE)),
    (
        "procedure:knocked_out_transition",
        re.compile(r"\bknock(?:s|ed|ing)?\s+out\b|\bknocked out\b|\bunconscious\b", re.IGNORECASE),
    ),
    (
        "procedure:roll_strike",
        re.compile(
            r"\broll(?:ing)?\s+(?:to\s+)?strike\b|\broll\s+a\s+strike\b|\bmake(?:s|ing)?\s+a\s+strike\b|\bstrike\s+roll\b",
            re.IGNORECASE,
        ),
    ),
    (
        "procedure:critical_resolution",
        re.compile(r"\bcritical\s+(hit|success|failure)\b|\bon a critical\b", re.IGNORECASE),
    ),
    (
        "procedure:gain_dying",
        re.compile(
            r"\b(?:gain|gains|gaining|acquire|acquires|become|becomes|enter|enters)\s+dying\b|\bdying condition\b",
            re.IGNORECASE,
        ),
    ),
    ("procedure:persistent_damage_tick", re.compile(r"\bpersistent damage\b", re.IGNORECASE)),
    ("procedure:perception_check", re.compile(r"\bperception check(s)?\b", re.IGNORECASE)),
    ("procedure:initiative_roll", re.compile(r"\binitiative roll\b|\broll(?:ing)? initiative\b", re.IGNORECASE)),
    ("procedure:initiative", re.compile(r"\binitiative\b", re.IGNORECASE)),
    ("procedure:attack_resolution", re.compile(r"\battack roll\b|\bmissed attack\b|\battack misses\b", re.IGNORECASE)),
    ("procedure:miss_resolution", re.compile(r"\bon a miss\b|\bmiss(?:es|ed)?\b", re.IGNORECASE)),
    (
        "procedure:apply_damage",
        re.compile(r"\b(?:apply|applies|take|takes|taking|deal|deals|receive|receives)\s+damage\b|\bdamage is applied\b", re.IGNORECASE),
    ),
    (
        "procedure:damage_roll",
        re.compile(
            r"\bdamage roll\b|\broll damage\b|\bdamage dice\b|\bdamage die\b|\bdie size\b|\bweapon damage dice\b|\bnormal weapon damage dice\b|\bnormal die size\b",
            re.IGNORECASE,
        ),
    ),
    (
        "procedure:dying",
        re.compile(
            r"\b(dying|death|perish)\b|\bdie\b(?!\s+(?:size|roll|dice)\b)",
            re.IGNORECASE,
        ),
    ),
    ("procedure:movement", re.compile(r"\bmove action\b|\bmovement\b", re.IGNORECASE)),
]


def _normalize_override_target(target: Optional[str]) -> Optional[str]:
    if not target:
        return None
    cleaned = " ".join(str(target).split())
    cleaned = cleaned.replace("\u2013", "-").replace("\u2014", "-")
    if _NUMERIC_OVERRIDE_TARGET.match(cleaned):
        return f"noise:numeric:{cleaned}"
    if _TEMPORAL_OVERRIDE_TARGET.search(cleaned):
        return f"noise:temporal:{cleaned.lower()}"
    for token, pattern in _PROCEDURE_TARGETS:
        if pattern.search(cleaned):
            return token
    return cleaned


@dataclass
class RuleFact:
    """A semantic atomic claim extracted from a clause."""
    
    # Identity
    fact_id: str                    # Unique ID: {clause_id}::fact_{order}
    fact_type: FactType             # Classification of the fact
    
    # Core triple structure (subject-predicate-object)
    subject: Optional[str]          # What this fact is about (normalized)
    subject_type: Optional[str]     # Type of subject (feat, spell, ancestry, etc.)
    predicate: str                  # The relation/action (grants, requires, etc.)
    object: Optional[str]           # Target/result (normalized), if applicable
    object_type: Optional[str]      # Type of object, if applicable
    
    # Semantic context
    modality: Modality              # Must/may/can/automatic/conditional
    condition: Optional[str]        # Triggering condition (if conditional)
    scope: Optional[str]            # Who/what this applies to
    
    # Provenance (traceability)
    clause_id: str                  # Parent clause
    mention_ids: List[str] = field(default_factory=list)  # Mentions used to extract this fact
    evidence_span: Tuple[int, int] = field(default_factory=lambda: (0, 0))  # Char offsets in clause text
    
    # Quality indicators
    confidence: float = 1.0         # 1.0 for pattern match, <1.0 for heuristic
    extraction_method: str = "pattern"  # pattern | heuristic | llm
    is_complete: bool = True        # False if PartialFact
    
    # Optional: failure/override semantics
    failure_outcome: Optional[str] = None   # What happens on failure
    override_target: Optional[str] = None   # What this overrides (for OVERRIDES type)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "fact_type": self.fact_type.value,
            "subject": self.subject,
            "subject_type": self.subject_type,
            "predicate": self.predicate,
            "object": self.object,
            "object_type": self.object_type,
            "modality": self.modality.value,
            "condition": self.condition,
            "scope": self.scope,
            "clause_id": self.clause_id,
            "mention_ids": self.mention_ids,
            "evidence_span": list(self.evidence_span),
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
            "is_complete": self.is_complete,
            "failure_outcome": self.failure_outcome,
            "override_target": self.override_target,
        }
    
    @classmethod
    def partial(
        cls,
        clause_id: str,
        order: int,
        subject: Optional[str] = None,
        subject_type: Optional[str] = None,
        predicate: str = "unknown",
        object: Optional[str] = None,
        object_type: Optional[str] = None,
        modality: Modality = Modality.UNKNOWN,
        condition: Optional[str] = None,
        scope: Optional[str] = None,
        mention_ids: Optional[List[str]] = None,
        evidence_span: Tuple[int, int] = (0, 0),
        **kwargs
    ) -> "RuleFact":
        """Create a PartialFact with incomplete extraction."""
        return cls(
            fact_id=f"{clause_id}::fact_{order}",
            fact_type=FactType.PARTIAL,
            subject=subject,
            subject_type=subject_type,
            predicate=predicate,
            object=object,
            object_type=object_type,
            modality=modality,
            condition=condition,
            scope=scope,
            clause_id=clause_id,
            mention_ids=mention_ids or [],
            evidence_span=evidence_span,
            confidence=0.5,
            extraction_method="heuristic",
            is_complete=False,
        )


# =============================================================================
# Pattern Definitions
# =============================================================================

@dataclass
class FactPattern:
    """A pattern that extracts RuleFacts from clauses."""
    
    name: str
    pattern: Pattern
    fact_type: FactType
    modality: Modality = Modality.UNKNOWN
    
    def __hash__(self):
        return hash(self.name)


# Outcome patterns (success/failure semantics)
OUTCOME_PATTERNS = [
    # "On a success, you deal damage"
    FactPattern(
        name="on_success",
        pattern=re.compile(
            r'\b(?:on\s+a?\s*)?(?:success|successful)\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.ON_SUCCESS,
        modality=Modality.CONDITIONAL,
    ),
    
    # "On a failure, the target is unaffected"
    FactPattern(
        name="on_failure",
        pattern=re.compile(
            r'\b(?:on\s+a?\s*)?(?:failure|failed)\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.ON_FAILURE,
        modality=Modality.CONDITIONAL,
    ),
    
    # "Critical Success: Deal double damage"
    FactPattern(
        name="critical_success",
        pattern=re.compile(
            r'\bcritical\s+success\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.ON_CRITICAL,
        modality=Modality.CONDITIONAL,
    ),
    
    # "Critical Failure: You fall prone"
    FactPattern(
        name="critical_failure",
        pattern=re.compile(
            r'\bcritical\s+failure\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.ON_FAILURE,  # Treat as failure variant
        modality=Modality.CONDITIONAL,
    ),
    
    # "Success:" at start of line/clause
    FactPattern(
        name="success_label",
        pattern=re.compile(
            r'^success\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE | re.MULTILINE
        ),
        fact_type=FactType.ON_SUCCESS,
        modality=Modality.CONDITIONAL,
    ),
    
    # "Failure:" at start of line/clause
    FactPattern(
        name="failure_label",
        pattern=re.compile(
            r'^failure\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE | re.MULTILINE
        ),
        fact_type=FactType.ON_FAILURE,
        modality=Modality.CONDITIONAL,
    ),
]

# Level gate patterns
LEVEL_PATTERNS = [
    # "At 5th level, you gain..."
    FactPattern(
        name="at_level",
        pattern=re.compile(
            r'\bat\s+(\d+)(?:st|nd|rd|th)\s+level\s*[,:]\s*(?:you\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.LEVEL_GATE,
        modality=Modality.AUTOMATIC,
    ),
    
    # "Prerequisite: Level 9"
    FactPattern(
        name="prereq_level",
        pattern=re.compile(
            r'\bprerequisite[s]?\s*[,:]\s*.*?level\s+(\d+)',
            re.IGNORECASE
        ),
        fact_type=FactType.LEVEL_GATE,
        modality=Modality.MUST,
    ),
    
    # "requires level 9" or "require level 5"
    FactPattern(
        name="requires_level",
        pattern=re.compile(
            r'\brequire[s]?\s+level\s+(\d+)',
            re.IGNORECASE
        ),
        fact_type=FactType.LEVEL_GATE,
        modality=Modality.MUST,
    ),

    # "FEAT 5" (feat header level gate)
    FactPattern(
        name="feat_header_level",
        pattern=re.compile(
            r'\bfeat\s+(\d{1,2})\b',
            re.IGNORECASE
        ),
        fact_type=FactType.LEVEL_GATE,
        modality=Modality.MUST,
    ),

]


def _build_ruleset_level_patterns(resolved_config: Optional[Any]) -> List[FactPattern]:
    """Build ruleset-specific level gate patterns from config."""
    if not resolved_config:
        return []
    det_rules = getattr(resolved_config, "deterministic_rules", None)
    if not isinstance(det_rules, dict):
        return []
    title_terms = det_rules.get("level_gate_title_terms") or det_rules.get("level_gate_titles") or []
    patterns: List[FactPattern] = []
    for term in title_terms:
        normalized = str(term).strip()
        if not normalized:
            continue
        patterns.append(
            FactPattern(
                name=f"title_level_{normalized.lower().replace(' ', '_')}",
                pattern=re.compile(
                    rf'\b{re.escape(normalized)}\s+(\d{{1,2}})\b',
                    re.IGNORECASE,
                ),
                fact_type=FactType.LEVEL_GATE,
                modality=Modality.MUST,
            )
        )
    return patterns

# Grants/provides patterns
GRANTS_PATTERNS = [
    # "You gain a +2 bonus"
    FactPattern(
        name="you_gain",
        pattern=re.compile(
            r'\byou\s+gain\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.GRANTS,
        modality=Modality.AUTOMATIC,
    ),
    
    # "X gains Y" (e.g., "A Lashunta gains telepathy")
    FactPattern(
        name="subject_gains",
        pattern=re.compile(
            r'\b\w+\s+gains\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.GRANTS,
        modality=Modality.AUTOMATIC,
    ),
    
    # "This grants you..."
    FactPattern(
        name="this_grants",
        pattern=re.compile(
            r'\b(?:this|it)\s+grants\s+(?:you\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.GRANTS,
        modality=Modality.AUTOMATIC,
    ),
    
    # "grants a +2 bonus"
    FactPattern(
        name="grants_bonus",
        pattern=re.compile(
            r'\bgrants\s+(?:a\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.GRANTS,
        modality=Modality.AUTOMATIC,
    ),

    # "Lashuntas produce pheromones"
    FactPattern(
        name="produces",
        pattern=re.compile(
            r'\bproduce[s]?\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.GRANTS,
        modality=Modality.AUTOMATIC,
    ),
]

# Descriptive patterns (subject traits/qualities)
MODIFIES_PATTERNS = [
    # "Damayas tend to be tall and graceful"
    FactPattern(
        name="tend_to_be",
        pattern=re.compile(
            r'^\s*[A-Z][A-Za-z\'-]+(?:\s+[A-Z][A-Za-z\'-]+)?\s+tend\s+to\s+be\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.MODIFIES,
        modality=Modality.AUTOMATIC,
    ),
    # "Korashas are shorter, more muscular"
    FactPattern(
        name="are_statement",
        pattern=re.compile(
            r'^\s*[A-Z][A-Za-z\'-]+(?:\s+[A-Z][A-Za-z\'-]+)?\s+are\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.MODIFIES,
        modality=Modality.AUTOMATIC,
    ),
]

# Requires/prerequisite patterns
REQUIRES_PATTERNS = [
    # "Requires: trained in Athletics"
    FactPattern(
        name="requires",
        pattern=re.compile(
            r'\brequire[s]?\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.REQUIRES,
        modality=Modality.MUST,
    ),
    
    # "You must be trained in..."
    FactPattern(
        name="must_be",
        pattern=re.compile(
            r'\byou\s+must\s+(?:be\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.REQUIRES,
        modality=Modality.MUST,
    ),
    
    # "Prerequisites:" (captures everything after)
    FactPattern(
        name="prerequisites",
        pattern=re.compile(
            r'\bprerequisite[s]?\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.REQUIRES,
        modality=Modality.MUST,
    ),

    # "**Prerequisites** Vent Gas" (markdown header)
    FactPattern(
        name="prerequisites_markdown_header",
        pattern=re.compile(
            r'\*+\s*prerequisite[s]?\s*\*+\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.REQUIRES,
        modality=Modality.MUST,
    ),

    # "Prerequisites Vent Gas" (no colon)
    FactPattern(
        name="prerequisites_inline",
        pattern=re.compile(
            r'\bprerequisite[s]?\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.REQUIRES,
        modality=Modality.MUST,
    ),
]

# Frequency/usage limit patterns
FREQUENCY_PATTERNS = [
    # "Frequency: once per day" / "Frequency: 1/hour"
    FactPattern(
        name="frequency_label",
        pattern=re.compile(
            r'\bfrequency\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.FREQUENCY,
        modality=Modality.MUST,
    ),
    # "frequency of once per 10 minutes"
    FactPattern(
        name="frequency_of",
        pattern=re.compile(
            r'\bfrequency\s+of\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.FREQUENCY,
        modality=Modality.MUST,
    ),
]

# Override patterns
OVERRIDE_PATTERNS = [
    # "You X instead of Y"
    FactPattern(
        name="instead_of_inline",
        pattern=re.compile(
            r"^(?!\s*instead\s+of\b)(.+?)\s+instead of\s+(.+?)(?:\.|$)",
            re.IGNORECASE,
        ),
        fact_type=FactType.INSTEAD_OF,
        modality=Modality.MAY,
    ),
    
    # "rather than X, you Y"
    FactPattern(
        name="rather_than",
        pattern=re.compile(
            r"\brather than\s+([^,]+?),\s*(.+?)(?:\.|$)",
            re.IGNORECASE,
        ),
        fact_type=FactType.INSTEAD_OF,
        modality=Modality.MAY,
    ),
    
    # "this replaces X"
    FactPattern(
        name="replaces",
        pattern=re.compile(
            r"\b(?:this|that|it)\s+replaces?\s+(?:the\s+)?(.+?)(?:\.|$)",
            re.IGNORECASE,
        ),
        fact_type=FactType.OVERRIDES,
        modality=Modality.AUTOMATIC,
    ),
    
    # "Instead, you may..."
    FactPattern(
        name="instead",
        pattern=re.compile(
            r'\binstead\s*[,:]\s*(?:you\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.INSTEAD_OF,
        modality=Modality.MAY,
    ),
    
    # "This overrides the normal..."
    FactPattern(
        name="overrides",
        pattern=re.compile(
            r'\b(?:this\s+)?override[s]?\s+(?:the\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.OVERRIDES,
        modality=Modality.AUTOMATIC,
    ),
    
    # "instead of X, you Y"
    FactPattern(
        name="instead_of",
        pattern=re.compile(
            r'\binstead\s+of\s+(.+?),\s*(?:you\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.INSTEAD_OF,
        modality=Modality.MAY,
    ),
]

# Applies-to patterns
APPLIES_TO_PATTERNS = [
    # "This affects creatures within..."
    FactPattern(
        name="affects",
        pattern=re.compile(
            r'\b(?:this\s+)?affect[s]?\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.APPLIES_TO,
        modality=Modality.AUTOMATIC,
    ),
    
    # "Targets: one creature"
    FactPattern(
        name="targets",
        pattern=re.compile(
            r'\btarget[s]?\s*[,:]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.APPLIES_TO,
        modality=Modality.MUST,
    ),
    
    # "applies to all creatures"
    FactPattern(
        name="applies_to",
        pattern=re.compile(
            r'\bappl(?:y|ies)\s+to\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.APPLIES_TO,
        modality=Modality.AUTOMATIC,
    ),
]

# Triggers patterns
TRIGGERS_PATTERNS = [
    # "When you hit, deal damage"
    FactPattern(
        name="when_triggers",
        pattern=re.compile(
            r'\bwhen\s+(?:you\s+)?(.+?),\s*(?:you\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.TRIGGERS,
        modality=Modality.CONDITIONAL,
    ),
    
    # "If you succeed, X happens"
    FactPattern(
        name="if_triggers",
        pattern=re.compile(
            r'\bif\s+(?:you\s+)?(.+?),\s*(?:you\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.TRIGGERS,
        modality=Modality.CONDITIONAL,
    ),

    # "Trigger: A creature misses you"
    FactPattern(
        name="trigger_label",
        pattern=re.compile(
            r'\btrigger[s]?\s*[,:-]\s*(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.TRIGGERS,
        modality=Modality.CONDITIONAL,
    ),
]

# Unless/exception patterns
UNLESS_PATTERNS = [
    # "unless you have resistance"
    FactPattern(
        name="unless",
        pattern=re.compile(
            r'\bunless\s+(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.UNLESS,
        modality=Modality.CONDITIONAL,
    ),
    
    # "except when..."
    FactPattern(
        name="except",
        pattern=re.compile(
            r'\bexcept\s+(?:when\s+)?(.+?)(?:\.|$)',
            re.IGNORECASE
        ),
        fact_type=FactType.UNLESS,
        modality=Modality.CONDITIONAL,
    ),
]

def _get_fact_patterns(resolved_config: Optional[Any]) -> List[FactPattern]:
    """Return base patterns plus any ruleset-specific extensions."""
    return (
        OUTCOME_PATTERNS
        + LEVEL_PATTERNS
        + _build_ruleset_level_patterns(resolved_config)
        + GRANTS_PATTERNS
        + REQUIRES_PATTERNS
        + FREQUENCY_PATTERNS
        + OVERRIDE_PATTERNS
        + APPLIES_TO_PATTERNS
        + TRIGGERS_PATTERNS
        + UNLESS_PATTERNS
        + MODIFIES_PATTERNS
    )


# Backwards-compatible export for tests/utilities expecting a static list.
ALL_FACT_PATTERNS: List[FactPattern] = _get_fact_patterns(None)


# =============================================================================
# Extraction Functions
# =============================================================================

def _identify_subject(
    mentions: List["Mention"], 
    hint: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Identify the subject of facts from mentions.
    
    Priority:
    1. MECHANIC type mention (feat, spell, ability name)
    2. ROLE type mention (ancestry, class)
    3. Subject hint from section header
    4. First entity_type mention
    """
    # Lazy import to avoid circular dependency
    from .mentions import MentionType
    
    # Priority 1: Mechanic mentions (feat/spell name)
    mechanic_mentions = [m for m in mentions if m.mention_type == MentionType.MECHANIC]
    if mechanic_mentions:
        m = mechanic_mentions[0]
        return (m.normalized, "mechanic")
    
    # Priority 2: Role mentions
    role_mentions = [m for m in mentions if m.mention_type == MentionType.ROLE]
    if role_mentions:
        m = role_mentions[0]
        return (m.normalized, "role")
    
    # Priority 3: Hint from parent
    if hint:
        return (hint.lower(), "inherited")
    
    # Priority 4: Entity type mentions
    entity_mentions = [m for m in mentions if m.mention_type == MentionType.ENTITY_TYPE]
    if entity_mentions:
        m = entity_mentions[0]
        return (m.normalized, "entity")
    
    return (None, None)


def _infer_subject_hint_from_clause(text: str) -> Optional[str]:
    """Infer a subject hint from clause text when mentions are absent."""
    if not text:
        return None
    bold_match = re.search(r"\*\*([^*]+)\*\*", text)
    if bold_match:
        return bold_match.group(1).strip().lower()

    lead_match = re.match(
        r"^\s*([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?)\s+"
        r"(tend\s+to\s+be|are|is|produce|produces|have|has|gain|gains)\b",
        text,
    )
    if lead_match:
        return lead_match.group(1).strip().lower()

    return None


def _find_overlapping_mentions(
    mentions: List["Mention"], 
    span: Tuple[int, int]
) -> List["Mention"]:
    """Find mentions whose spans overlap with the given range."""
    start, end = span
    overlapping = []
    for m in mentions:
        m_start, m_end = m.span_offsets
        if m_start < end and m_end > start:
            overlapping.append(m)
    return overlapping


def _infer_object_type(
    mentions: List["Mention"], 
    object_text: Optional[str] = None
) -> Optional[str]:
    """Infer object type from overlapping mentions or text analysis."""
    from .mentions import MentionType
    
    if not mentions:
        return None
    
    # Use highest-confidence mention type
    type_priority = [
        MentionType.CONDITION,
        MentionType.LEVEL,
        MentionType.NUMERIC_TERM,
        MentionType.ROLE,
        MentionType.ENTITY_TYPE,
    ]
    
    for mt in type_priority:
        matching = [m for m in mentions if m.mention_type == mt]
        if matching:
            return mt.value
    
    return "text"


def _extract_condition(text: str, match: re.Match) -> Optional[str]:
    """Extract triggering condition from surrounding text."""
    # Look for "when/if/while" before the match
    prefix = text[:match.start()]
    condition_match = re.search(
        r'\b(when|if|while|after|before|unless)\s+(.+?)(?:,|$)',
        prefix,
        re.IGNORECASE
    )
    if condition_match:
        return condition_match.group(2).strip()
    return None


def _extract_scope(mentions: List["Mention"]) -> Optional[str]:
    """Extract scope from role/level mentions."""
    from .mentions import MentionType
    
    role_mentions = [m for m in mentions if m.mention_type == MentionType.ROLE]
    level_mentions = [m for m in mentions if m.mention_type == MentionType.LEVEL]
    
    parts = []
    if role_mentions:
        parts.append(role_mentions[0].normalized)
    if level_mentions:
        parts.append(level_mentions[0].normalized)
    
    return "; ".join(parts) if parts else None


def _ensure_failure_facts(
    facts: List[RuleFact], 
    clause: "ClauseUnit",
    mentions: List["Mention"]
) -> List[RuleFact]:
    """
    Ensure that for every ON_SUCCESS fact, an ON_FAILURE fact exists
    if there's failure language in the clause.
    
    This makes failure semantics first-class.
    """
    has_success = any(f.fact_type == FactType.ON_SUCCESS for f in facts)
    has_failure = any(f.fact_type == FactType.ON_FAILURE for f in facts)
    
    if has_success and not has_failure:
        # Check if clause mentions failure
        if re.search(r'\b(fail|failure|failed)\b', clause.text, re.IGNORECASE):
            # Create implicit failure fact
            failure_fact = RuleFact.partial(
                clause_id=clause.clause_id,
                order=len(facts),
                subject=facts[0].subject if facts else None,
                subject_type=facts[0].subject_type if facts else None,
                predicate="on_failure",
                object="(implicit - failure mentioned but not specified)",
                mention_ids=[],
                evidence_span=(0, len(clause.text)),
            )
            failure_fact.fact_type = FactType.ON_FAILURE
            facts.append(failure_fact)
    
    return facts


def extract_rule_facts(
    clause: "ClauseUnit", 
    mentions: List["Mention"],
    subject_hint: Optional[str] = None,
    resolved_config: Optional[Any] = None,
) -> List[RuleFact]:
    """
    Extract RuleFacts from a clause using its mentions as anchors.
    
    Strategy:
    1. Identify subject from mentions (highest confidence entity)
    2. Apply pattern matching for predicates/outcomes
    3. Link objects to relevant mentions
    4. Create explicit failure facts when "on failure" detected
    5. Mark incomplete extractions as PartialFacts
    
    Args:
        clause: The ClauseUnit to extract from
        mentions: Mentions already extracted from this clause
        subject_hint: Optional subject from parent section header
        
    Returns:
        List of RuleFacts (may include PartialFacts)
    """
    # Handle empty clause
    if not clause.text or not clause.text.strip():
        return []
    
    facts = []
    fact_counter = 0
    
    # Step 1: Identify subject from mentions or hint
    if not subject_hint:
        subject_hint = _infer_subject_hint_from_clause(clause.text)
    subject, subject_type = _identify_subject(mentions, subject_hint)
    
    # Step 2: Apply all patterns
    for pattern in _get_fact_patterns(resolved_config):
        matches = pattern.pattern.finditer(clause.text)
        for match in matches:
            # Extract object from match groups
            # For patterns with multiple groups, use the last non-empty group
            # (e.g., "at 5th level, you gain X" -> group 1 is level, group 2 is ability)
            object_text = None
            if match.lastindex and match.lastindex >= 1:
                # Try last group first (most specific content)
                for group_idx in range(match.lastindex, 0, -1):
                    group_val = match.group(group_idx)
                    if group_val and group_val.strip():
                        object_text = group_val.strip()
                        break
            
            # Find mentions that overlap with the match
            match_mentions = _find_overlapping_mentions(
                mentions, 
                (match.start(), match.end())
            )
            
            # Determine object type from mentions
            object_type = _infer_object_type(match_mentions, object_text)
            
            # Extract condition from context
            condition = _extract_condition(clause.text, match)
            
            # Extract scope from role/level mentions
            scope = _extract_scope(mentions)
            
            # Determine if fact is complete
            is_complete = bool(subject and object_text)

            extraction_method = "pattern"
            if pattern.name == "prerequisites_markdown_header":
                extraction_method = "prerequisites_markdown_header"
            
            override_target = None
            if pattern.fact_type in {FactType.OVERRIDES, FactType.INSTEAD_OF}:
                if pattern.name == "overrides" and object_text:
                    override_target = object_text
                elif pattern.name == "instead_of":
                    override_target = match.group(1).strip() if match.group(1) else None
                elif pattern.name == "instead_of_inline":
                    override_target = match.group(2).strip() if match.group(2) else None
                elif pattern.name == "rather_than":
                    override_target = match.group(1).strip() if match.group(1) else None
                elif pattern.name == "replaces":
                    override_target = match.group(1).strip() if match.group(1) else None
            override_target = _normalize_override_target(override_target)
            if not override_target and pattern.fact_type in {FactType.OVERRIDES, FactType.INSTEAD_OF}:
                override_target = _normalize_override_target(clause.text)

            # Create fact
            fact = RuleFact(
                fact_id=f"{clause.clause_id}::fact_{fact_counter}",
                fact_type=pattern.fact_type,
                subject=subject,
                subject_type=subject_type,
                predicate=pattern.fact_type.value,
                object=object_text,
                object_type=object_type,
                modality=pattern.modality,
                condition=condition,
                scope=scope,
                clause_id=clause.clause_id,
                mention_ids=[m.mention_id for m in match_mentions],
                evidence_span=(match.start(), match.end()),
                confidence=1.0 if subject else 0.7,
                extraction_method=extraction_method,
                is_complete=is_complete,
                override_target=override_target,
            )
            facts.append(fact)
            fact_counter += 1
    
    # Step 3: Create explicit failure facts for outcome patterns
    facts = _ensure_failure_facts(facts, clause, mentions)
    
    return facts


# =============================================================================
# Batch Processing
# =============================================================================

def extract_facts_from_chunks(
    chunks: List[Dict[str, Any]],
    include_partial: bool = True,
    vocabularies: Optional[Dict[str, Set[str]]] = None
) -> Dict[str, Any]:
    """
    Extract RuleFacts from all chunks.
    
    Args:
        chunks: List of EnrichedChunk dicts
        include_partial: Whether to include PartialFacts in output
        
    Returns:
        Dict with 'facts', 'stats', and 'by_type' keys
    """
    from .clause_units import extract_clause_units
    from .mentions import extract_mentions
    from .chunks import EnrichedChunk
    from collections import defaultdict
    
    all_facts = []
    fact_type_counts = defaultdict(int)
    total_clauses = 0
    clauses_with_facts = 0
    
    for chunk_dict in chunks:
        # Handle both dict and EnrichedChunk
        if isinstance(chunk_dict, dict):
            chunk = EnrichedChunk(**chunk_dict)
        else:
            chunk = chunk_dict
        
        # Extract clauses
        clauses = extract_clause_units(chunk)
        
        for clause in clauses:
            total_clauses += 1
            
            # Extract mentions
            mentions_list = extract_mentions(clause, vocabularies=vocabularies)
            
            # Extract facts
            facts = extract_rule_facts(clause, mentions_list)
            
            # Filter partial facts if requested
            if not include_partial:
                facts = [f for f in facts if f.is_complete]
            
            if facts:
                clauses_with_facts += 1
            
            for fact in facts:
                fact_type_counts[fact.fact_type.value] += 1
                all_facts.append(fact.to_dict())
    
    return {
        "facts": all_facts,
        "stats": {
            "total_clauses": total_clauses,
            "clauses_with_facts": clauses_with_facts,
            "total_facts": len(all_facts),
            "facts_per_clause": len(all_facts) / max(total_clauses, 1),
            "coverage": clauses_with_facts / max(total_clauses, 1),
        },
        "by_type": dict(fact_type_counts),
    }
