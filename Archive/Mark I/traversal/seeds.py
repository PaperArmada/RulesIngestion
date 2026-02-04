"""
Query to seed/anchor node mapping.

Seeds are graph-local starting points found via deterministic lookup.
No embeddings - just index lookups.

Phase 3 (seed contract): when use_authority_for_seeding is enabled, anchors are
reordered by authority-for-seeding score (definition/canonical first) so that
within max_anchors we prefer chunks that look like definitions or core rules.
See Docs/PLAN-Failure-Taxonomy-And-Constraints.md §4.1 (If A dominant).
"""

from __future__ import annotations

import re
from typing import Optional, Set, TYPE_CHECKING

from .index import TraversalIndex, tokenize_and_normalize

if TYPE_CHECKING:
    from .config import TraversalConfig

# Authority-for-seeding: section path keywords that suggest canonical/definition
# (higher = prefer when capping anchors). Used only when use_authority_for_seeding.
_SEEDING_AUTHORITY_SECTION_KEYWORDS = (
    ("definition", "definitions", "glossary", "overview", "introduction", "summary"),
    ("conditions", "condition", "rules", "rule", "core"),
    ("procedure", "procedures", "how", "step"),
)
# content_kind ordinal for seeding: rule/condition > spell/feat > other
_SEEDING_AUTHORITY_CONTENT_KIND = {"rule": 3, "condition": 3, "spell": 2, "feat": 2, "action": 2, "item": 2}


# Default document selection keywords (used if no config provided)
DEFAULT_PLAYER_KEYWORDS = {
    "character", "player", "ancestry", "class", "feat", "spell",
    "background", "skill", "ability", "level", "equipment", "armor",
    "weapon", "item", "heritage", "archetype",
}

DEFAULT_GM_KEYWORDS = {
    "gm", "gamemaster", "game master", "npc", "creature", "monster",
    "hazard", "encounter", "trap", "environment", "difficulty",
    "treasure", "reward", "adventure", "campaign", "setting",
}

# Default game terms that should ALWAYS anchor to their matching chunks
# Used if no config provided - prefer using TraversalConfig for ruleset-specific terms
DEFAULT_CONDITION_NAMES = {
    "blinded", "broken", "clumsy", "confused", "controlled", "dazzled",
    "deafened", "doomed", "drained", "dying", "encumbered", "enfeebled",
    "fascinated", "fatigued", "fleeing", "frightened", "grabbed", "hidden",
    "immobilized", "invisible", "observed", "off-guard", "paralyzed",
    "persistent", "petrified", "prone", "quickened", "restrained",
    "sickened", "slowed", "stunned", "stupefied", "unconscious",
    "undetected", "unfriendly", "unnoticed", "wounded",
    # Starfinder 2e specific
    "flat-footed", "offguard",
}

# Default priority terms (conditions only, without config)
DEFAULT_PRIORITY_GAME_TERMS = DEFAULT_CONDITION_NAMES


def _authority_score_for_seeding(chunk_id: str, index: TraversalIndex) -> float:
    """
    Authority score for seed selection (canonical-first).

    Uses existing chunk metadata only (section_path, content_kind). Higher score
    = prefer when capping anchors. Definition/glossary/core > procedure > other.
    Deterministic; no learning. See PLAN-Failure-Taxonomy-And-Constraints.md §4.1.
    """
    chunk = index.chunk_by_id.get(chunk_id)
    if not chunk:
        return 0.0
    score = 0.0
    section_path = chunk.get("section_path", [])
    path_lower = " ".join(section_path).lower()
    for tier, keywords in enumerate(_SEEDING_AUTHORITY_SECTION_KEYWORDS):
        if any(kw in path_lower for kw in keywords):
            score += 10.0 * (len(_SEEDING_AUTHORITY_SECTION_KEYWORDS) - tier)
            break
    content_kind = (chunk.get("content_kind") or "").lower()
    score += float(_SEEDING_AUTHORITY_CONTENT_KIND.get(content_kind, 0))
    return score


def select_documents(
    query: str,
    available_docs: Set[str],
    config: Optional["TraversalConfig"] = None,
) -> Set[str]:
    """
    Rule-based document selection based on query vocabulary.
    
    Selects documents that are likely relevant to the query.
    
    Args:
        query: The query string
        available_docs: Set of available document IDs
        config: Optional TraversalConfig for ruleset-specific keywords
        
    Returns:
        Subset of available_docs that are relevant
    """
    query_lower = query.lower()
    
    # Get keywords from config or defaults
    player_keywords = config.player_keywords if config else DEFAULT_PLAYER_KEYWORDS
    gm_keywords = config.gm_keywords if config else DEFAULT_GM_KEYWORDS
    
    # Check for explicit document mentions
    selected = set()
    
    for doc in available_docs:
        doc_lower = doc.lower()
        
        # Check if document name appears in query
        # Extract book name from doc ID (e.g., "sf2e-playercore-..." -> "playercore")
        parts = doc_lower.split("-")
        for part in parts:
            if part in query_lower:
                selected.add(doc)
                break
    
    if selected:
        return selected
    
    # Use keyword matching
    has_player_keywords = any(kw in query_lower for kw in player_keywords)
    has_gm_keywords = any(kw in query_lower for kw in gm_keywords)
    
    for doc in available_docs:
        doc_lower = doc.lower()
        
        if has_player_keywords and "player" in doc_lower:
            selected.add(doc)
        if has_gm_keywords and ("gm" in doc_lower or "master" in doc_lower):
            selected.add(doc)
    
    # If nothing matched, return all
    return selected if selected else available_docs


def find_anchor_nodes(
    query: str,
    index: TraversalIndex,
    max_anchors: int = 200,
    config: Optional["TraversalConfig"] = None,
) -> Set[str]:
    """
    Find graph-local starting points via index lookup.
    
    Anchor sources (in priority order):
    0. PRIORITY: Game terms (conditions, spells, etc.) - always included
    1. Exact term matches in chunk text (top 50 by term count)
    2. Section title matches
    3. Entity name matches
    4. Tag/trait matches
    5. Content kind matches (spell, feat, etc.)
    
    Args:
        query: The query string
        index: TraversalIndex with pre-built indexes
        max_anchors: Maximum number of anchor nodes to return
        config: Optional TraversalConfig with ruleset-specific game terms
        
    Returns:
        Set of chunk IDs to use as traversal seeds
    """
    anchors: Set[str] = set()
    
    # Tokenize query
    terms = tokenize_and_normalize(query)
    
    if not terms:
        return anchors
    
    # Get priority game terms from config or defaults
    priority_terms = config.priority_game_terms if config else DEFAULT_PRIORITY_GAME_TERMS
    
    # 0. PRIORITY: Game terms (conditions, spells, feats) get ALL matching chunks
    # This ensures we never miss the definition of a named game element
    for term in terms:
        if term in priority_terms:
            if term in index.term_to_chunks:
                # Add ALL chunks containing this game term
                anchors |= index.term_to_chunks[term]
    
    # 1. Exact term matches in chunk text
    # Prioritize chunks that match multiple query terms
    term_hits: dict[str, int] = {}
    for term in terms:
        if term in index.term_to_chunks:
            for chunk_id in index.term_to_chunks[term]:
                term_hits[chunk_id] = term_hits.get(chunk_id, 0) + 1
    
    # Sort by number of term hits (descending)
    sorted_chunks = sorted(term_hits.items(), key=lambda x: -x[1])
    
    # Add top chunks by term coverage
    for chunk_id, _ in sorted_chunks[:50]:
        anchors.add(chunk_id)
        if len(anchors) >= max_anchors:
            break
    
    # 2. Section title matches
    for term in terms:
        if term in index.section_title_to_chunks:
            for chunk_id in index.section_title_to_chunks[term]:
                anchors.add(chunk_id)
                if len(anchors) >= max_anchors:
                    break
    
    # 3. Entity name matches
    for term in terms:
        if term in index.entity_name_to_id:
            entity_id = index.entity_name_to_id[term]
            if entity_id in index.entity_to_chunks:
                for chunk_id in index.entity_to_chunks[entity_id]:
                    anchors.add(chunk_id)
                    if len(anchors) >= max_anchors:
                        break
    
    # 4. Tag/trait matches
    for term in terms:
        if term in index.tag_to_chunks:
            for chunk_id in index.tag_to_chunks[term]:
                anchors.add(chunk_id)
                if len(anchors) >= max_anchors:
                    break
        if term in index.trait_to_chunks:
            for chunk_id in index.trait_to_chunks[term]:
                anchors.add(chunk_id)
                if len(anchors) >= max_anchors:
                    break
    
    # 5. Content kind matches (check if any term looks like a content kind)
    content_kinds = {"spell", "feat", "item", "condition", "action", "rule", "trait"}
    for term in terms:
        if term in content_kinds and term in index.content_kind_to_chunks:
            for chunk_id in index.content_kind_to_chunks[term]:
                anchors.add(chunk_id)
                if len(anchors) >= max_anchors:
                    break

    # Phase 3 (seed contract): reorder by authority (canonical-first) and cap
    use_authority = config is not None and getattr(config, "use_authority_for_seeding", False)
    if use_authority and anchors:
        ordered = sorted(
            anchors,
            key=lambda cid: -_authority_score_for_seeding(cid, index),
        )
        anchors = set(ordered[:max_anchors])

    return anchors


def find_anchor_nodes_by_phrase(
    query: str,
    index: TraversalIndex,
    max_anchors: int = 100,
) -> Set[str]:
    """
    Find anchors using phrase matching (for multi-word entity names).
    
    This is more precise than single-term matching for named entities.
    """
    anchors: Set[str] = set()
    query_lower = query.lower()
    
    # Look for entity names in the query
    for entity_name, entity_id in index.entity_name_to_id.items():
        if entity_name in query_lower:
            if entity_id in index.entity_to_chunks:
                for chunk_id in index.entity_to_chunks[entity_id]:
                    anchors.add(chunk_id)
                    if len(anchors) >= max_anchors:
                        return anchors
    
    return anchors
