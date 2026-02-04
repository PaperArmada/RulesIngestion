"""ClauseUnit extraction from enriched chunks.

ClauseUnits are sentence-level units extracted from chunks, providing
finer-grained retrieval and serving as the foundation for fact extraction.

This is Phase 1 of the fact-based retrieval architecture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .chunks import EnrichedChunk


# Minimum clause length to avoid fragments
MIN_CLAUSE_LENGTH = 20


# Patterns that should NOT cause sentence splits
# These are common TTRPG abbreviations followed by periods
ABBREVIATIONS = {
    "ft",   # feet
    "lbs",  # pounds
    "lb",   # pound
    "oz",   # ounces
    "sq",   # square
    "vs",   # versus
    "etc",  # et cetera
    "min",  # minutes
    "max",  # maximum
    "avg",  # average
    "approx",  # approximately
    "e.g",  # for example
    "i.e",  # that is
    "Mr",
    "Mrs",
    "Ms",
    "Dr",
    "Prof",
    "Sr",
    "Jr",
    "No",   # Number
    "Vol",  # Volume
    "Ch",   # Chapter
    "Sec",  # Section
    "Fig",  # Figure
    "pg",   # page
    "pp",   # pages
}


def _build_abbreviation_pattern() -> re.Pattern:
    """Build regex pattern for abbreviations that shouldn't split sentences."""
    # Case-insensitive abbreviation matching
    abbrev_pattern = "|".join(re.escape(a) for a in ABBREVIATIONS)
    return re.compile(rf"(?i)\b({abbrev_pattern})\.$")


ABBREVIATION_PATTERN = _build_abbreviation_pattern()


# Pattern for numbered list items: "1." "2." etc. at sentence boundaries
NUMBERED_LIST_PATTERN = re.compile(r"^\d+\.\s")


# Pattern for detecting dice notation context (shouldn't split)
DICE_CONTEXT_PATTERN = re.compile(r"\d+d\d+")


# Pattern for game abbreviations that look like sentence ends
# DC 15. CR 5. AC 20. etc - these are often mid-sentence
GAME_ABBREV_PATTERN = re.compile(r"\b(DC|CR|AC|HP|XP|GP|SP|CP|PP)\s+\d+\.")


def _find_sentence_boundaries(text: str) -> List[int]:
    """
    Find positions where sentences end in the text.
    
    Returns list of indices where sentence-ending punctuation occurs,
    accounting for TTRPG-specific patterns that shouldn't split.
    """
    boundaries = []
    i = 0
    
    while i < len(text):
        char = text[i]
        
        # Check for sentence-ending punctuation
        if char in ".!?":
            # Look at context to decide if this is a real sentence boundary
            
            # Get text before this position for context
            before = text[:i+1]
            after = text[i+1:] if i + 1 < len(text) else ""
            
            is_boundary = True
            
            # Check 1: Abbreviation before period
            if char == "." and ABBREVIATION_PATTERN.search(before):
                is_boundary = False
            
            # Check 2: Numbered list item (e.g., "1. " at start of clause)
            # Look back to find if we're in a numbered list context
            if char == "." and i > 0:
                # Check if this is a numbered list item
                lookback = max(0, i - 3)
                lookback_text = text[lookback:i+1]
                if re.match(r"^\s*\d+\.$", lookback_text):
                    is_boundary = False
            
            # Check 3: Game abbreviation (DC 15., CR 5., etc.)
            if char == ".":
                lookback_start = max(0, i - 10)
                lookback_text = text[lookback_start:i+1]
                if GAME_ABBREV_PATTERN.search(lookback_text):
                    # Only not a boundary if followed by lowercase or conjunction
                    if after and after.lstrip() and after.lstrip()[0].islower():
                        is_boundary = False
            
            # Check 4: Must be followed by whitespace and capital (or end of text)
            if is_boundary and char == ".":
                after_stripped = after.lstrip()
                if after_stripped:
                    first_char = after_stripped[0]
                    # If followed by lowercase letter, likely not a sentence boundary
                    if first_char.islower():
                        is_boundary = False
                    # If followed by digit, could be a list - check more carefully
                    elif first_char.isdigit():
                        # Numbered list continuing - check if it's "2. Something"
                        if re.match(r"\d+\.\s+[A-Z]", after_stripped):
                            is_boundary = True
                        elif re.match(r"\d+\.\s+[a-z]", after_stripped):
                            is_boundary = False
            
            if is_boundary:
                boundaries.append(i)
        
        i += 1
    
    return boundaries


def _split_at_boundaries(text: str, boundaries: List[int]) -> List[Tuple[str, int, int]]:
    """
    Split text at the given boundary positions.
    
    Returns list of (clause_text, start_offset, end_offset) tuples.
    """
    if not boundaries:
        # No boundaries found - return entire text as single clause
        stripped = text.strip()
        if stripped:
            # Find actual start/end in original text
            start = text.index(stripped[0]) if stripped else 0
            end = start + len(stripped)
            return [(stripped, start, end)]
        return []
    
    clauses = []
    prev_end = 0
    
    for boundary in boundaries:
        # Extract text from previous end to this boundary (inclusive)
        clause_text = text[prev_end:boundary + 1].strip()
        if clause_text:
            # Find actual start position (accounting for leading whitespace)
            actual_start = prev_end
            while actual_start < boundary and text[actual_start].isspace():
                actual_start += 1
            clauses.append((clause_text, actual_start, boundary + 1))
        prev_end = boundary + 1
    
    # Handle remaining text after last boundary
    remaining = text[prev_end:].strip()
    if remaining:
        actual_start = prev_end
        while actual_start < len(text) and text[actual_start].isspace():
            actual_start += 1
        clauses.append((remaining, actual_start, len(text)))
    
    return clauses


def _merge_short_clauses(
    clauses: List[Tuple[str, int, int]], 
    min_length: int = MIN_CLAUSE_LENGTH
) -> List[Tuple[str, int, int]]:
    """
    Merge clauses that are too short with adjacent clauses.
    
    Short clauses are merged with the following clause when possible,
    or with the preceding clause if at the end.
    
    Only merge if the clause is VERY short (under min_length) AND looks
    like a fragment (no sentence-ending punctuation or very few words).
    """
    if not clauses:
        return []
    
    def is_fragment(text: str) -> bool:
        """Check if text is a fragment that should be merged."""
        # Too short to be a meaningful clause
        if len(text) < min_length:
            # But if it ends with sentence punctuation and has 2+ words, keep it
            words = text.split()
            has_ending = text.rstrip()[-1] in ".!?" if text.rstrip() else False
            if has_ending and len(words) >= 2:
                return False
            return True
        return False
    
    merged = []
    i = 0
    
    while i < len(clauses):
        text, start, end = clauses[i]
        
        # If this clause is a fragment, try to merge
        if is_fragment(text) and i < len(clauses) - 1:
            # Merge with next clause
            next_text, _, next_end = clauses[i + 1]
            # Reconstruct merged text with proper spacing
            merged_text = text + " " + next_text
            merged.append((merged_text.strip(), start, next_end))
            i += 2  # Skip the next clause since we merged it
        elif is_fragment(text) and merged:
            # At the end and a fragment - merge with previous
            prev_text, prev_start, _ = merged[-1]
            merged_text = prev_text + " " + text
            merged[-1] = (merged_text.strip(), prev_start, end)
            i += 1
        else:
            merged.append((text, start, end))
            i += 1
    
    return merged


@dataclass
class ClauseUnit:
    """A sentence-level unit extracted from a chunk."""
    
    clause_id: str                    # Unique ID: {chunk_id}::clause_{order}
    text: str                         # The sentence text
    parent_chunk_id: str              # Link to EnrichedChunk.id
    order_in_chunk: int               # 0-indexed position in chunk
    char_offsets: Tuple[int, int]     # (start, end) in parent chunk text
    
    # Inherited from parent chunk for convenience
    page: int = 0
    section_path: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "clause_id": self.clause_id,
            "text": self.text,
            "parent_chunk_id": self.parent_chunk_id,
            "order_in_chunk": self.order_in_chunk,
            "char_offsets": list(self.char_offsets),
            "page": self.page,
            "section_path": self.section_path,
        }


def extract_clause_units(chunk: "EnrichedChunk") -> List[ClauseUnit]:
    """
    Split chunk text into ClauseUnits using sentence boundaries.
    
    Rules:
    1. Split on sentence boundaries (. ! ?)
    2. Preserve offsets for traceability
    3. Handle TTRPG edge cases:
       - "1d6 + 5" should not split on period
       - "DC 15" should not split
       - Numbered lists "1. First item" should split correctly
       - Action icons "[one-action]" preserved
    4. Minimum clause length: 20 chars (avoid fragments)
    
    Args:
        chunk: An EnrichedChunk to extract clauses from
        
    Returns:
        List of ClauseUnit objects, empty if chunk has no valid text
    """
    text = chunk.text
    
    # Handle empty or whitespace-only text
    if not text or not text.strip():
        return []
    
    # Find sentence boundaries
    boundaries = _find_sentence_boundaries(text)
    
    # Split at boundaries
    raw_clauses = _split_at_boundaries(text, boundaries)
    
    # Merge short clauses
    merged_clauses = _merge_short_clauses(raw_clauses, MIN_CLAUSE_LENGTH)
    
    # Build ClauseUnit objects
    clause_units = []
    for order, (clause_text, start, end) in enumerate(merged_clauses):
        clause_id = f"{chunk.id}::clause_{order}"
        
        clause_unit = ClauseUnit(
            clause_id=clause_id,
            text=clause_text,
            parent_chunk_id=chunk.id,
            order_in_chunk=order,
            char_offsets=(start, end),
            page=chunk.page,
            section_path=list(chunk.section_path) if chunk.section_path else [],
        )
        clause_units.append(clause_unit)
    
    return clause_units
