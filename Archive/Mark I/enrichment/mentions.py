"""Mention extraction from ClauseUnits.

Mentions are rule-bearing entity candidates extracted from clauses,
providing searchable anchors for cross-chapter retrieval.

This is Phase 2 of the fact-based retrieval architecture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Pattern, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .clause_units import ClauseUnit


class MentionType(Enum):
    """Closed vocabulary for mention types."""
    ROLE = "role"                    # Ancestry, class, archetype
    LEVEL = "level"                  # Character/spell level
    TRAIT = "trait"                  # Action traits, damage types, conditions
    MECHANIC = "mechanic"            # Named abilities, feats, spells
    NUMERIC_TERM = "numeric_term"    # DC, CR, AC, HP values
    ENTITY_TYPE = "entity_type"      # Creature, object, hazard
    CONDITION = "condition"          # Prone, stunned, frightened
    OUTCOME = "outcome"              # Success, failure, critical
    UNKNOWN = "unknown"              # Detected but unclassified


@dataclass
class Mention:
    """A rule-bearing entity candidate extracted from a clause."""
    
    mention_id: str                   # Unique ID: {clause_id}::mention_{order}
    surface: str                      # The exact text matched ("Lashunta", "DC 15")
    normalized: str                   # Canonical form ("lashunta", "dc:15")
    mention_type: MentionType         # Type from closed vocabulary
    
    clause_id: str                    # Parent clause
    span_offsets: Tuple[int, int]     # (start, end) in clause text
    
    # Optional metadata
    confidence: float = 1.0           # 1.0 for regex, <1.0 for heuristic
    extraction_method: str = "regex"  # regex | pattern | heuristic | vocabulary
    
    def to_dict(self) -> dict:
        return {
            "mention_id": self.mention_id,
            "surface": self.surface,
            "normalized": self.normalized,
            "mention_type": self.mention_type.value,
            "clause_id": self.clause_id,
            "span_offsets": list(self.span_offsets),
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
        }


def normalize_mention(surface: str, mention_type: MentionType) -> str:
    """Create canonical key from surface form."""
    if mention_type == MentionType.LEVEL:
        # Extract number: "Level 9" -> "level:9"
        match = re.search(r'\d+', surface)
        return f"level:{match.group()}" if match else f"level:{surface.lower()}"
    
    if mention_type == MentionType.ROLE:
        return f"role:{surface.lower()}"
    
    if mention_type == MentionType.NUMERIC_TERM:
        # "DC 15" -> "dc:15"
        # Handle cases like "DC15" and "DC 15"
        match = re.match(r'(DC|CR|AC|HP)\s*(\d+)', surface, re.IGNORECASE)
        if match:
            return f"{match.group(1).lower()}:{match.group(2)}"
        return surface.lower().replace(" ", ":")
    
    if mention_type == MentionType.CONDITION:
        return f"condition:{surface.lower().replace('-', '_')}"
    
    if mention_type == MentionType.OUTCOME:
        return f"outcome:{surface.lower().replace(' ', '_')}"
    
    if mention_type == MentionType.TRAIT:
        # "[two-actions]" -> "trait:two-actions"
        # Strip brackets if present
        clean = surface.strip("[]")
        return f"trait:{clean.lower()}"
    
    if mention_type == MentionType.ENTITY_TYPE:
        return f"entity:{surface.lower()}"
    
    # Default
    return surface.lower()


# Pattern definitions: each entry is (pattern, MentionType, normalize_fn_override)
# normalize_fn_override is optional - if None, uses normalize_mention()
MENTION_PATTERNS: Dict[str, Tuple[Pattern, MentionType]] = {
    # Level patterns
    "level_numeric": (
        re.compile(r'\b(?:level|Level)\s+(\d{1,2})\b'),
        MentionType.LEVEL
    ),
    "nth_level": (
        re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)[- ]level\b', re.IGNORECASE),
        MentionType.LEVEL
    ),
    "at_level": (
        re.compile(r'\bat\s+(\d{1,2})(?:st|nd|rd|th)\s+level\b', re.IGNORECASE),
        MentionType.LEVEL
    ),
    
    # Trait patterns (action economy)
    "action_icon": (
        re.compile(r'\[(one-action|two-actions|three-actions|reaction|free-action)\]'),
        MentionType.TRAIT
    ),
    "action_emoji": (
        re.compile(r'[◆◇⬡⟳]'),  # Common action symbols
        MentionType.TRAIT
    ),
    
    # Numeric game terms
    "dc_value": (
        re.compile(r'\bDC\s*(\d{1,2})\b'),
        MentionType.NUMERIC_TERM
    ),
    "cr_value": (
        re.compile(r'\bCR\s*(\d{1,2})\b'),
        MentionType.NUMERIC_TERM
    ),
    "ac_value": (
        re.compile(r'\bAC\s*(\d{1,2})\b'),
        MentionType.NUMERIC_TERM
    ),
    
    # Outcome patterns
    "success_outcome": (
        re.compile(r'\b(critical success|success|failure|critical failure)\b', re.IGNORECASE),
        MentionType.OUTCOME
    ),
    
    # Condition patterns (common TTRPG conditions)
    "condition": (
        re.compile(r'\b(prone|stunned|frightened|sickened|dazzled|blinded|'
                   r'deafened|fatigued|paralyzed|petrified|unconscious|'
                   r'grabbed|restrained|immobilized|flat-footed|concealed|'
                   r'hidden|invisible|observed|undetected|unnoticed)\b', re.IGNORECASE),
        MentionType.CONDITION
    ),
    
    # Entity type patterns
    "entity_creature": (
        re.compile(r'\b(creature|creatures|ally|allies|enemy|enemies|target|targets)\b', re.IGNORECASE),
        MentionType.ENTITY_TYPE
    ),
    "entity_object": (
        re.compile(r'\b(object|objects|item|items|weapon|armor|equipment)\b', re.IGNORECASE),
        MentionType.ENTITY_TYPE
    ),
}


def _extract_pattern_matches(
    clause_text: str,
    clause_id: str,
    start_order: int = 0
) -> List[Mention]:
    """
    Extract mentions from clause text using regex patterns.
    
    Args:
        clause_text: The text to extract from
        clause_id: The clause ID for building mention IDs
        start_order: Starting index for mention ordering
    
    Returns:
        List of Mention objects, sorted by span offset
    """
    matches: List[Tuple[int, int, str, MentionType]] = []  # (start, end, surface, type)
    
    for pattern_name, (pattern, mention_type) in MENTION_PATTERNS.items():
        for match in pattern.finditer(clause_text):
            start, end = match.start(), match.end()
            surface = match.group(0)
            matches.append((start, end, surface, mention_type))
    
    # Sort by start position, then by length (prefer longer matches)
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    
    # Deduplicate overlapping spans (prefer longer match at same position)
    deduplicated: List[Tuple[int, int, str, MentionType]] = []
    covered_ranges: List[Tuple[int, int]] = []
    
    for start, end, surface, mention_type in matches:
        # Check if this span overlaps with any already-covered range
        is_covered = False
        for cov_start, cov_end in covered_ranges:
            # Overlap if ranges intersect
            if not (end <= cov_start or start >= cov_end):
                is_covered = True
                break
        
        if not is_covered:
            deduplicated.append((start, end, surface, mention_type))
            covered_ranges.append((start, end))
    
    # Build Mention objects
    mentions = []
    for i, (start, end, surface, mention_type) in enumerate(deduplicated):
        normalized = normalize_mention(surface, mention_type)
        mention = Mention(
            mention_id=f"{clause_id}::mention_{start_order + i}",
            surface=surface,
            normalized=normalized,
            mention_type=mention_type,
            clause_id=clause_id,
            span_offsets=(start, end),
            confidence=1.0,
            extraction_method="regex",
        )
        mentions.append(mention)
    
    # Sort by span offset
    mentions.sort(key=lambda m: m.span_offsets[0])
    return mentions


def _merge_mentions(
    clause_id: str,
    mentions: List[Mention],
    start_order: int = 0
) -> List[Mention]:
    """Sort and de-duplicate mentions, then re-number IDs."""
    mentions.sort(key=lambda m: (m.span_offsets[0], m.span_offsets[1]))
    deduplicated: List[Mention] = []
    seen: Set[Tuple[Tuple[int, int], str, str]] = set()

    for mention in mentions:
        key = (mention.span_offsets, mention.mention_type.value, mention.normalized)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(mention)

    for i, mention in enumerate(deduplicated):
        mention.mention_id = f"{clause_id}::mention_{start_order + i}"

    return deduplicated


def extract_mentions(
    clause: "ClauseUnit",
    vocabularies: Optional[Dict[str, Set[str]]] = None
) -> List[Mention]:
    """
    Extract mentions from a clause using pattern matching.
    
    Strategy:
    1. Apply all regex patterns
    2. Deduplicate overlapping spans (prefer longer match)
    3. Normalize surface forms to canonical keys
    4. Return sorted by span offset
    
    Args:
        clause: The ClauseUnit to extract from
    
    Args:
        vocabularies: Optional vocabularies mapping (mention_type -> terms).
                      When provided, will augment regex matches with
                      vocabulary-based role/mechanic mentions.
    
    Returns:
        List of Mention objects, sorted by span offset
    """
    if not clause.text or not clause.text.strip():
        return []
    
    pattern_mentions = _extract_pattern_matches(clause.text, clause.clause_id)

    if not vocabularies:
        return pattern_mentions

    # Lazy import to avoid cycles
    from .vocabulary_loader import extract_vocabulary_mentions

    vocab_mentions = extract_vocabulary_mentions(
        clause,
        vocabularies=vocabularies,
        mention_counter=len(pattern_mentions)
    )

    return _merge_mentions(
        clause_id=clause.clause_id,
        mentions=pattern_mentions + vocab_mentions
    )
