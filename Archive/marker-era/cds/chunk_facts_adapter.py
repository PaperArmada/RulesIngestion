"""
ChunkFacts Adapter for CDS v0.2

Builds ChunkFacts from enriched chunks using only:
- Explicit metadata from the parser
- Anchored label patterns (deterministic, no semantic inference)

This adapter enforces the constraint that ChunkFacts contain only
observed or deterministically-derived facts.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .constraint_engine import (
    ChunkFacts,
    ContentKind,
    LayoutTier,
    SectionRole,
)


# -------------------------
# Anchored label patterns
# -------------------------

# These patterns are anchored to start-of-text or have clear word boundaries
# to minimize false positives. They only match explicit labels.

# Example labels: "Example:", "EXAMPLE:", "For example:", etc.
# Must be anchored near start or be a clear heading pattern
_EXAMPLE_LABEL_PATTERNS = [
    re.compile(r"^\s*example\s*:", re.IGNORECASE),
    re.compile(r"^\s*for\s+example\s*:", re.IGNORECASE),
    re.compile(r"^\s*sample\s*:", re.IGNORECASE),
    # Heading pattern: "Example" or "Examples" as full line
    re.compile(r"^\s*examples?\s*$", re.IGNORECASE | re.MULTILINE),
]

# Variant/Optional labels: must be explicit and anchored
_VARIANT_LABEL_PATTERNS = [
    re.compile(r"^\s*variant\s*:", re.IGNORECASE),
    re.compile(r"^\s*optional\s+rule\s*:", re.IGNORECASE),
    re.compile(r"^\s*alternative\s+rule\s*:", re.IGNORECASE),
    re.compile(r"^\s*alternate\s+rule\s*:", re.IGNORECASE),
    # Heading patterns
    re.compile(r"^\s*variant\s+rules?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*optional\s+rules?\s*$", re.IGNORECASE | re.MULTILINE),
]

# Definition labels: must be explicit
_DEFINITION_LABEL_PATTERNS = [
    re.compile(r"^\s*definition\s*:", re.IGNORECASE),
    re.compile(r"^\s*definitions?\s*$", re.IGNORECASE | re.MULTILINE),
]

# Section reference patterns for explicit deferrals
# Constrained to avoid matching common words
_SECTION_REF_PATTERNS = [
    # "see Section X" or "see the X section"
    re.compile(
        r"\bsee\s+(?:the\s+)?([A-Z][A-Za-z\s]+?)\s+(?:section|chapter|page)\b",
        re.IGNORECASE,
    ),
    # "refer to Section X"
    re.compile(
        r"\brefer\s+to\s+(?:the\s+)?([A-Z][A-Za-z\s]+?)\s+(?:section|chapter)\b",
        re.IGNORECASE,
    ),
    # "see page X" - returns page number
    re.compile(r"\bsee\s+page\s+(\d+)\b", re.IGNORECASE),
    # "(page X)" - parenthetical page reference
    re.compile(r"\(\s*page\s+(\d+)\s*\)", re.IGNORECASE),
]


def _has_example_label(text: str) -> bool:
    """Check if text has an explicit example label."""
    for pat in _EXAMPLE_LABEL_PATTERNS:
        if pat.search(text):
            return True
    return False


def _has_variant_label(text: str) -> bool:
    """Check if text has an explicit variant/optional label."""
    for pat in _VARIANT_LABEL_PATTERNS:
        if pat.search(text):
            return True
    return False


def _has_definition_label(text: str) -> bool:
    """Check if text has an explicit definition label."""
    for pat in _DEFINITION_LABEL_PATTERNS:
        if pat.search(text):
            return True
    return False


def _extract_section_refs(
    text: str, known_section_titles: Set[str]
) -> List[Tuple[str, Optional[str], str]]:
    """
    Extract explicit section references from text.

    Returns list of (raw_text, resolved_section_id, confidence).
    - resolved_section_id is None if unresolved
    - confidence is one of: "unresolved", "ambiguous", "resolved_unique"
    """
    refs: List[Tuple[str, Optional[str], str]] = []

    for pat in _SECTION_REF_PATTERNS:
        for match in pat.finditer(text):
            raw_text = match.group(0)
            target = match.group(1).strip() if match.groups() else ""

            # Skip page references (they're different)
            if target.isdigit():
                continue

            # Try to resolve against known section titles
            target_lower = target.lower()
            matches = [
                title
                for title in known_section_titles
                if title.lower() == target_lower
            ]

            if len(matches) == 1:
                refs.append((raw_text, matches[0], "resolved_unique"))
            elif len(matches) > 1:
                refs.append((raw_text, None, "ambiguous"))
            else:
                refs.append((raw_text, None, "unresolved"))

    return refs


def _extract_page_refs(text: str) -> List[int]:
    """Extract explicit page references from text."""
    pages: List[int] = []
    for pat in _SECTION_REF_PATTERNS:
        for match in pat.finditer(text):
            if match.groups():
                target = match.group(1)
                if target.isdigit():
                    pages.append(int(target))
    return pages


def _stable_section_id(section_path: List[str]) -> str:
    """
    Generate a stable section ID from section path.

    Uses SHA-256 of the full path to avoid collisions from slugification.
    """
    if not section_path:
        return "root"

    # Join with a delimiter that won't appear in titles
    path_str = "\x00".join(section_path)
    path_hash = hashlib.sha256(path_str.encode("utf-8")).hexdigest()[:12]

    # Include last title for readability
    last_title = section_path[-1].replace(" ", "_").replace("/", "_")[:30]
    return f"{last_title}_{path_hash}"


def _derive_layout_tier(
    chunk: Dict[str, Any], section_path: List[str]
) -> LayoutTier:
    """
    Derive LayoutTier from parser metadata and section path.

    Deterministic: only uses explicit block_type, container_type, is_callout,
    and section path keywords. No semantic inference.
    """
    bt = (chunk.get("block_type") or "Text").lower()
    ct = (chunk.get("container_type") or "").lower()
    # Parser-emitted or explicit container types
    if ct in {"examplebox", "example_box"}:
        return LayoutTier.EXAMPLE_BOX
    if ct in {"variantbox", "variant_box", "optionalrule", "alternaterule"}:
        return LayoutTier.VARIANT_BOX
    if chunk.get("is_callout"):
        return LayoutTier.CALLOUT
    if bt == "table":
        return LayoutTier.TABLE
    if bt == "footnote":
        return LayoutTier.FOOTNOTE
    if bt == "caption" or "caption" in ct:
        return LayoutTier.CAPTION
    # Section path keywords (explicit structure from headers)
    for s in section_path:
        sl = s.lower()
        if "example" in sl or "sample" in sl:
            return LayoutTier.EXAMPLE_BOX
        if "variant" in sl or "optional" in sl or "alternate" in sl:
            return LayoutTier.VARIANT_BOX
    return LayoutTier.MAIN


def _derive_content_kind(
    has_example: bool,
    has_variant: bool,
    has_def: bool,
    block_type: str,
) -> ContentKind:
    """
    Derive ContentKind from rhetoric labels and block type.

    Deterministic mapping: explicit labels take precedence.
    """
    if has_example:
        return ContentKind.EXAMPLE
    if has_def:
        return ContentKind.DEFINITION
    if (block_type or "").lower() == "table":
        return ContentKind.TABLE
    # Variant rules are still rules
    if has_variant:
        return ContentKind.RULE
    return ContentKind.RULE  # default for main text


def _derive_section_role(section_path: List[str]) -> SectionRole:
    """
    Derive SectionRole from section path (header titles).

    Deterministic: uses explicit header text keywords only.
    """
    for s in section_path:
        sl = s.lower()
        if "example" in sl or "sample" in sl:
            return SectionRole.EXAMPLES
        if "variant" in sl or "optional" in sl or "alternate" in sl:
            return SectionRole.VARIANTS
        if "glossary" in sl:
            return SectionRole.GLOSSARY
        if "summary" in sl or "overview" in sl:
            return SectionRole.SUMMARY
        if "introduction" in sl or "intro" in sl:
            return SectionRole.INTRO
        if "reference" in sl or "index" in sl:
            return SectionRole.REFERENCE
    return SectionRole.CORE_RULES


def build_chunk_facts(
    chunk: Dict[str, Any],
    ordinal: int,
    known_section_titles: Optional[Set[str]] = None,
) -> ChunkFacts:
    """
    Build ChunkFacts from an enriched chunk dictionary.

    Only uses:
    - Explicit fields from the chunk
    - Anchored label extractors (no semantic inference)

    Args:
        chunk: Enriched chunk dictionary with fields like id, block_type, text, etc.
        ordinal: Document-order index of this chunk
        known_section_titles: Set of known section titles for reference resolution

    Returns:
        ChunkFacts with only observed/deterministic facts
    """
    known_section_titles = known_section_titles or set()

    chunk_id = chunk.get("id", "")
    text = chunk.get("text", "")
    block_type = chunk.get("block_type", "Text")
    section_path = chunk.get("section_path", [])
    page = chunk.get("page")

    # Generate stable section ID from path
    section_id = _stable_section_id(section_path)

    # Parser-emitted container type (not always present)
    # This would come from explicit markup in the source document
    container_type = chunk.get("container_type")

    # is_callout from parser (not always present)
    is_callout = chunk.get("is_callout")

    # Extract explicit rhetoric labels using anchored patterns
    has_example_label = _has_example_label(text)
    has_variant_label = _has_variant_label(text)
    has_definition_label = _has_definition_label(text)

    # Check section path for structural rhetoric indicators
    # These are explicit because they come from actual section headers
    for section in section_path:
        section_lower = section.lower()
        # Variant/optional section indicators
        if any(kw in section_lower for kw in ("variant", "optional", "alternate")):
            has_variant_label = True
        # Example section indicators
        if any(kw in section_lower for kw in ("example", "sample")):
            has_example_label = True

    # Extract explicit section references
    section_refs = _extract_section_refs(text, known_section_titles)
    explicit_section_refs = tuple(
        (ref[1], ref[2]) for ref in section_refs  # (resolved_id, confidence)
    )

    # Derive spec-aligned enums (deterministic, no semantic inference)
    layout_tier = _derive_layout_tier(chunk, section_path)
    content_kind = _derive_content_kind(
        has_example_label, has_variant_label, has_definition_label, block_type
    )
    section_role = _derive_section_role(section_path)

    return ChunkFacts(
        chunk_id=chunk_id,
        section_id=section_id,
        ordinal=ordinal,
        block_type=block_type,
        container_type=container_type,
        is_callout=is_callout,
        page=page,
        has_example_label=has_example_label,
        has_variant_label=has_variant_label,
        has_definition_label=has_definition_label,
        explicit_section_refs=explicit_section_refs,
        section_path=tuple(section_path),
        layout_tier=layout_tier,
        content_kind=content_kind,
        section_role=section_role,
    )


def build_chunk_facts_index(
    chunks: List[Dict[str, Any]],
) -> Dict[str, ChunkFacts]:
    """
    Build an index of chunk_id -> ChunkFacts for all chunks.

    Args:
        chunks: List of enriched chunk dictionaries

    Returns:
        Dictionary mapping chunk_id to ChunkFacts
    """
    # First pass: collect all section titles for reference resolution
    known_section_titles: Set[str] = set()
    for chunk in chunks:
        section_path = chunk.get("section_path", [])
        for title in section_path:
            known_section_titles.add(title)

    # Second pass: build ChunkFacts with reference resolution
    index: Dict[str, ChunkFacts] = {}
    for ordinal, chunk in enumerate(chunks):
        facts = build_chunk_facts(chunk, ordinal, known_section_titles)
        index[facts.chunk_id] = facts

    return index


def chunks_to_chunk_facts_list(
    chunks: List[Dict[str, Any]],
) -> List[ChunkFacts]:
    """
    Convert a list of enriched chunks to ChunkFacts list.

    Maintains document order.
    """
    index = build_chunk_facts_index(chunks)
    return [index[chunk["id"]] for chunk in chunks if chunk.get("id") in index]
