"""Config-driven vocabulary loading for mention extraction.

This module loads vocabularies from graphs and configs without hardcoding
per-ruleset entity names. Both the entity_type -> mention_type mapping
AND the vocabulary terms come from config/graph data.

This is Phase 2 of the fact-based retrieval architecture.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING, Union

from .mention_type_inference import (
    infer_mention_type_mappings,
    infer_mention_type_mappings_from_file,
    singularize,
)
from .extractors import extract_feat_title_from_text, extract_spell_title_from_text, normalize_space

if TYPE_CHECKING:
    from .mentions import Mention
    from .clause_units import ClauseUnit


# Default cross-system mapping (used when no config or enriched data available)
# This covers common entity types across SF2e, PF2e, D&D 5e, and other TTRPGs
DEFAULT_MENTION_TYPE_MAPPINGS: Dict[str, Set[str]] = {
    "role": {"ancestry", "class", "archetype", "background", "heritage", "race", "species", "subclass"},
    "mechanic": {"mechanicframe", "feat", "spell", "ability", "action", "skill", "item", "equipment", "weapon", "armor"},
    "condition": {"condition", "status"},
}


def _normalize_mappings(mappings: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """Normalize mapping keys/values for consistent lookups."""
    normalized: Dict[str, Set[str]] = {}
    for mention_type, entity_types in mappings.items():
        if not mention_type:
            continue
        key = str(mention_type).lower()
        normalized[key] = {str(entity_type).lower() for entity_type in entity_types if entity_type}
    return normalized


def _normalize_vocab_term(term: str) -> str:
    return normalize_space(term).strip().lower()


def _extract_bold_title(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"\*\*([^*]+)\*\*", text)
    if not match:
        return None
    return normalize_space(match.group(1)).strip()


def _extract_mechanic_terms_from_chunk(
    chunk: Dict[str, Any],
    mechanic_entity_types: Set[str],
) -> List[str]:
    text = chunk.get("text") or ""
    if not text:
        return []

    content_kind = (chunk.get("content_kind") or "").lower()
    block_type = (chunk.get("block_type") or "").lower()
    tags = [singularize(tag.lower()) for tag in (chunk.get("tags") or []) if tag]

    is_mechanic_context = (
        singularize(content_kind) in mechanic_entity_types
        or any(tag in mechanic_entity_types for tag in tags)
    )
    allow_title_only = block_type in {"tablecell", "sectionheader", "title"}
    if not is_mechanic_context and not allow_title_only:
        return []

    terms: List[str] = []
    candidate: Optional[str] = None
    raw_candidate: Optional[str] = None

    if content_kind == "spell":
        raw_candidate = extract_spell_title_from_text(text)
        candidate = raw_candidate
    elif content_kind == "feat":
        raw_candidate = extract_feat_title_from_text(text)
        candidate = raw_candidate
    else:
        raw_candidate = _extract_bold_title(text)
        candidate = raw_candidate
        if not candidate:
            first_line = text.splitlines()[0] if text.splitlines() else text
            raw_candidate = first_line
            candidate = normalize_space(first_line).strip()

    if candidate:
        candidate = normalize_space(candidate).strip()
        if raw_candidate and any(char.isupper() for char in raw_candidate):
            if re.search(r"[A-Za-z]", candidate) and 3 <= len(candidate) <= 80:
                terms.append(candidate)

    if not terms and is_mechanic_context:
        pattern = re.compile(r"\b([A-Z][a-zA-Z']+(?:\s+[A-Z][a-zA-Z']+){1,3})\b")
        for match in pattern.findall(text):
            cleaned = normalize_space(match).strip()
            if 3 <= len(cleaned) <= 80:
                terms.append(cleaned)

    return terms


def load_mention_type_mappings(
    enriched_path: Optional[Path] = None,
    config: Optional["RulesetConfiguration"] = None  # noqa: F821
) -> Dict[str, Set[str]]:
    """
    Load entity_type -> mention_type mappings.
    
    Priority:
    1. Config override (if provided)
    2. Auto-infer from enriched data (if path provided)
    3. Fall back to defaults from inference module
    
    Args:
        enriched_path: Path to enriched JSON file for inference
        config: RulesetConfiguration with optional mention_type_mappings
    
    Returns:
        Dict mapping mention_type -> set of entity_types that map to it
        Example: {"role": {"ancestry", "class", "archetype", ...}}
    """
    # Priority 1: Config override
    if config is not None:
        det_rules = getattr(config, "deterministic_rules", None)
        if det_rules:
            mappings = det_rules.get("mention_type_mappings") if isinstance(det_rules, dict) else None
            if mappings:
                normalized = _normalize_mappings({k: set(v) for k, v in mappings.items()})
                normalized.setdefault("mechanic", set()).add("mechanicframe")
                return normalized
    
    # Priority 2: Auto-infer from enriched data
    if enriched_path and enriched_path.exists():
        normalized = _normalize_mappings(
            infer_mention_type_mappings_from_file(enriched_path, merge_with_defaults=True)
        )
        normalized.setdefault("mechanic", set()).add("mechanicframe")
        return normalized
    
    # Priority 3: Use defaults from inference module
    normalized = _normalize_mappings(infer_mention_type_mappings([], merge_with_defaults=True))
    normalized.setdefault("mechanic", set()).add("mechanicframe")
    return normalized


def load_vocabulary_from_graph(
    graph_path: Union[str, Path],
    mention_type_mappings: Optional[Dict[str, Set[str]]] = None
) -> Dict[str, Set[str]]:
    """
    Extract vocabulary sets from an existing enriched graph.
    
    Args:
        graph_path: Path to merged.graph.json or similar
        mention_type_mappings: entity_type -> mention_type mapping
                              (from config or default). If None, uses default.
    
    Returns:
        Dict mapping mention_type -> set of normalized entity names.
        Example: {"role": {"android", "lashunta", "solarian", ...}}
    """
    graph_path = Path(graph_path)
    
    if mention_type_mappings is None:
        mention_type_mappings = load_mention_type_mappings()
    
    with open(graph_path) as f:
        graph = json.load(f)

    return load_vocabulary_from_graph_data(graph, mention_type_mappings)


def load_vocabulary_from_graph_data(
    graph: Dict[str, Any],
    mention_type_mappings: Optional[Dict[str, Set[str]]] = None
) -> Dict[str, Set[str]]:
    """
    Extract vocabulary sets from a graph dict.

    Args:
        graph: Graph dict (same structure as merged.graph.json)
        mention_type_mappings: entity_type -> mention_type mapping
                              (from config or default). If None, uses default.

    Returns:
        Dict mapping mention_type -> set of normalized entity names.
    """
    if mention_type_mappings is None:
        mention_type_mappings = load_mention_type_mappings()

    # Initialize empty vocabularies for each mention type
    vocabularies: Dict[str, Set[str]] = {mt: set() for mt in mention_type_mappings.keys()}

    # Build reverse mapping: entity_type -> mention_type
    entity_to_mention: Dict[str, str] = {}
    for mention_type, entity_types in mention_type_mappings.items():
        for entity_type in entity_types:
            entity_to_mention[entity_type.lower()] = mention_type

    # Extract from entity nodes
    for node in graph.get("nodes", []):
        node_type = node.get("type", "").lower()
        name = node.get("normalized_name") or node.get("name", "")

        if not name:
            continue

        # Use config-driven mapping (no hardcoding!)
        if node_type in entity_to_mention:
            mention_type = entity_to_mention[node_type]
            vocabularies[mention_type].add(_normalize_vocab_term(name))

    # Supplement mechanic vocabulary from chunk text when available
    mechanic_entity_types = {t.lower() for t in mention_type_mappings.get("mechanic", set())}
    for chunk in graph.get("chunks", []):
        content_kind = singularize((chunk.get("content_kind") or "").lower())
        tags = [singularize(t.lower()) for t in (chunk.get("tags") or [])]
        block_type = (chunk.get("block_type") or "").lower()
        should_check = (
            content_kind in mechanic_entity_types
            or any(tag in mechanic_entity_types for tag in tags)
            or block_type in {"tablecell", "sectionheader", "title"}
        )
        if not should_check:
            continue

        for term in _extract_mechanic_terms_from_chunk(chunk, mechanic_entity_types):
            vocabularies["mechanic"].add(_normalize_vocab_term(term))

    if "mechanic" in vocabularies:
        role_vocab = vocabularies.get("role", set())
        condition_vocab = vocabularies.get("condition", set())
        mechanic_vocab = vocabularies["mechanic"]
        multi_word_tokens = {
            token
            for term in mechanic_vocab
            if " " in term
            for token in term.split()
        }
        filtered_mechanics = set()
        for term in mechanic_vocab:
            if term in role_vocab or term in condition_vocab:
                continue
            if " " in term:
                filtered_mechanics.add(term)
                continue
            if term in multi_word_tokens:
                continue
            if len(term) < 6:
                continue
            filtered_mechanics.add(term)
        vocabularies["mechanic"] = filtered_mechanics

    return vocabularies


def load_vocabulary_from_config(
    config: "RulesetConfiguration",  # noqa: F821
    mention_type_mappings: Optional[Dict[str, Set[str]]] = None
) -> Dict[str, Set[str]]:
    """
    Extract vocabulary from ruleset config's entity_type_overrides.
    
    Uses config-driven mapping to categorize entities.
    
    Args:
        config: RulesetConfiguration with entity_type_overrides
        mention_type_mappings: Optional pre-loaded mappings
    
    Returns:
        Dict mapping mention_type -> set of entity names
    """
    if mention_type_mappings is None:
        mention_type_mappings = load_mention_type_mappings(config=config)
    
    # Build reverse mapping
    entity_to_mention: Dict[str, str] = {}
    for mention_type, entity_types in mention_type_mappings.items():
        for entity_type in entity_types:
            entity_to_mention[entity_type.lower()] = mention_type
    
    # Initialize vocabularies
    vocabularies: Dict[str, Set[str]] = {mt: set() for mt in mention_type_mappings.keys()}
    
    det_rules = getattr(config, "deterministic_rules", None) or {}
    if isinstance(det_rules, dict):
        # entity_type_overrides: [{"key": "Lashunta", "value": "Ancestry"}]
        for override in det_rules.get("entity_type_overrides", []):
            entity_name = override.get("key", "").lower()
            entity_type = override.get("value", "").lower()
            
            # Use config-driven mapping
            if entity_type in entity_to_mention:
                mention_type = entity_to_mention[entity_type]
                vocabularies[mention_type].add(entity_name)
    
    return vocabularies


def _is_word_boundary(text: str, start: int, length: int) -> bool:
    """Check if match is at word boundaries."""
    if start > 0 and text[start - 1].isalnum():
        return False
    end = start + length
    if end < len(text) and text[end].isalnum():
        return False
    return True


def extract_role_mentions(
    clause: "ClauseUnit",
    vocabulary: Set[str],
    mention_counter: int = 0
) -> List["Mention"]:
    """
    Extract role mentions using vocabulary lookup.
    
    Args:
        clause: The clause to extract from
        vocabulary: Set of lowercase role terms (loaded from graph or config)
        mention_counter: Starting index for mention IDs
    
    Returns:
        List of Mention objects for role terms found
    """
    from .mentions import Mention, MentionType
    
    mentions = []
    text_lower = clause.text.lower()
    
    for role in vocabulary:
        start = 0
        while True:
            idx = text_lower.find(role, start)
            if idx == -1:
                break
            # Verify word boundary
            if _is_word_boundary(text_lower, idx, len(role)):
                surface = clause.text[idx:idx + len(role)]
                mentions.append(Mention(
                    mention_id=f"{clause.clause_id}::mention_{mention_counter + len(mentions)}",
                    surface=surface,
                    normalized=f"role:{role}",
                    mention_type=MentionType.ROLE,
                    clause_id=clause.clause_id,
                    span_offsets=(idx, idx + len(role)),
                    extraction_method="vocabulary",
                ))
            start = idx + 1
    
    return mentions


def extract_mechanic_mentions(
    clause: "ClauseUnit",
    vocabulary: Set[str],
    mention_counter: int = 0
) -> List["Mention"]:
    """
    Extract mechanic mentions (feats, spells, abilities) using vocabulary lookup.
    
    Args:
        clause: The clause to extract from
        vocabulary: Set of lowercase mechanic terms (loaded from graph or config)
        mention_counter: Starting index for mention IDs
    
    Returns:
        List of Mention objects for mechanic terms found
    """
    from .mentions import Mention, MentionType
    
    mentions = []
    text_lower = clause.text.lower()
    compact_chars: List[str] = []
    compact_to_original: List[int] = []
    for idx, char in enumerate(text_lower):
        if char.isalnum():
            compact_chars.append(char)
            compact_to_original.append(idx)
    compact_text = "".join(compact_chars)
    
    for mechanic in vocabulary:
        found_direct = False
        start = 0
        while True:
            idx = text_lower.find(mechanic, start)
            if idx == -1:
                break
            # Verify word boundary
            if _is_word_boundary(text_lower, idx, len(mechanic)):
                surface = clause.text[idx:idx + len(mechanic)]
                mentions.append(Mention(
                    mention_id=f"{clause.clause_id}::mention_{mention_counter + len(mentions)}",
                    surface=surface,
                    normalized=f"mechanic:{mechanic}",
                    mention_type=MentionType.MECHANIC,
                    clause_id=clause.clause_id,
                    span_offsets=(idx, idx + len(mechanic)),
                    extraction_method="vocabulary",
                ))
                found_direct = True
            start = idx + 1

        compact_term = "".join(char for char in mechanic if char.isalnum())
        if not compact_term or found_direct:
            continue

        search_start = 0
        while True:
            compact_idx = compact_text.find(compact_term, search_start)
            if compact_idx == -1:
                break
            start_idx = compact_to_original[compact_idx]
            end_idx = compact_to_original[compact_idx + len(compact_term) - 1] + 1
            if _is_word_boundary(text_lower, start_idx, end_idx - start_idx):
                surface = clause.text[start_idx:end_idx]
                mentions.append(Mention(
                    mention_id=f"{clause.clause_id}::mention_{mention_counter + len(mentions)}",
                    surface=surface,
                    normalized=f"mechanic:{mechanic}",
                    mention_type=MentionType.MECHANIC,
                    clause_id=clause.clause_id,
                    span_offsets=(start_idx, end_idx),
                    extraction_method="vocabulary",
                ))
            search_start = compact_idx + 1
    
    return mentions


def extract_vocabulary_mentions(
    clause: "ClauseUnit",
    vocabularies: Dict[str, Set[str]],
    mention_counter: int = 0
) -> List["Mention"]:
    """
    Extract mentions for all vocabulary types from a clause.
    
    Args:
        clause: The clause to extract from
        vocabularies: Dict mapping mention_type -> set of terms
        mention_counter: Starting index for mention IDs
    
    Returns:
        List of Mention objects, sorted by span offset
    """
    all_mentions = []
    
    # Extract each vocabulary type
    if "role" in vocabularies:
        all_mentions.extend(
            extract_role_mentions(clause, vocabularies["role"], mention_counter)
        )
    
    if "mechanic" in vocabularies:
        all_mentions.extend(
            extract_mechanic_mentions(clause, vocabularies["mechanic"], mention_counter + len(all_mentions))
        )
    
    # Sort by span offset
    all_mentions.sort(key=lambda m: m.span_offsets[0])
    
    # Re-number mention IDs after sorting
    for i, mention in enumerate(all_mentions):
        mention.mention_id = f"{clause.clause_id}::mention_{mention_counter + i}"
    
    return all_mentions
