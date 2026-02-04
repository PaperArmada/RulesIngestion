"""
Auto-infer mention_type_mappings from document structure.

This module provides dynamic inference of entity_type -> mention_type mappings
by scanning chunk metadata (tags, content_kind). This eliminates the need for
manual per-ruleset configuration.

Usage:
    from enrichment.mention_type_inference import infer_mention_type_mappings
    
    # From enriched data
    mappings = infer_mention_type_mappings(enriched_data)
    # Returns: {"role": {"ancestry", "class"}, "mechanic": {"feat", "spell"}, ...}
    
    # Or from file
    mappings = infer_mention_type_mappings_from_file(enriched_path)
"""
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, List, Optional, Union

# Cross-system seed mapping: normalized_tag -> mention_type
# This small vocabulary covers SF2e, PF2e, D&D 5e, and most TTRPGs
TAG_TO_MENTION_TYPE: Dict[str, str] = {
    # Role-related (character identity)
    "ancestry": "role",
    "ancestries": "role",
    "race": "role",
    "races": "role",
    "species": "role",
    "class": "role",
    "classes": "role",
    "archetype": "role",
    "archetypes": "role",
    "background": "role",
    "backgrounds": "role",
    "heritage": "role",
    "heritages": "role",
    "subclass": "role",
    "subclasses": "role",
    
    # Mechanic-related (actions/abilities)
    "feat": "mechanic",
    "feats": "mechanic",
    "spell": "mechanic",
    "spells": "mechanic",
    "ability": "mechanic",
    "abilities": "mechanic",
    "action": "mechanic",
    "actions": "mechanic",
    "skill": "mechanic",
    "skills": "mechanic",
    "item": "mechanic",
    "items": "mechanic",
    "equipment": "mechanic",
    "weapon": "mechanic",
    "weapons": "mechanic",
    "armor": "mechanic",
    
    # Condition-related
    "condition": "condition",
    "conditions": "condition",
    "status": "condition",
}

# Content-kind -> mention_type (supplementary signal)
CONTENT_KIND_TO_MENTION_TYPE: Dict[str, Optional[str]] = {
    "feat": "mechanic",
    "spell": "mechanic",
    "rule": None,  # Too generic
    "narrative": None,
    "table": None,
}


def singularize(word: str) -> str:
    """
    Simple singularization for TTRPG entity types.
    
    Handles common patterns:
    - ancestries -> ancestry
    - classes -> class
    - feats -> feat
    """
    word = word.lower().strip()
    
    # Special cases - words that shouldn't be singularized or need special handling
    special_cases = {
        "classes": "class",
        "class": "class",  # Already singular, don't strip 's'
        "species": "species",  # Already singular
        "status": "status",  # Already singular
    }
    if word in special_cases:
        return special_cases[word]
    
    # Pattern: -ies -> -y
    if word.endswith("ies"):
        return word[:-3] + "y"
    
    # Pattern: -es -> (drop) for words like "races" but NOT "classes"
    if word.endswith("es") and len(word) > 3:
        return word[:-2]
    
    # Pattern: -s -> (drop) but not for words ending in 'ss'
    if word.endswith("s") and len(word) > 2 and not word.endswith("ss"):
        return word[:-1]
    
    return word


def infer_mention_type_mappings(
    enriched_data: Union[dict, List[dict]],
    merge_with_defaults: bool = True
) -> Dict[str, Set[str]]:
    """
    Infer entity_type -> mention_type mapping from enriched chunk metadata.
    
    Scans chunk tags and content_kind to discover entity types, then maps
    them to mention types using the cross-system seed vocabulary.
    
    Args:
        enriched_data: Either the full enriched dict with 'chunks' key,
                       or a list of chunk dicts directly
        merge_with_defaults: If True, include unmapped common entity types
                            from default mapping
    
    Returns:
        Dict mapping mention_type -> set of entity_types
        Example: {"role": {"ancestry", "class"}, "mechanic": {"feat", "spell"}}
    """
    # Handle both formats
    if isinstance(enriched_data, dict):
        chunks = enriched_data.get("chunks", [])
    else:
        chunks = enriched_data
    
    # Collect all unique tags and content_kinds
    discovered_entity_types: Set[str] = set()
    
    for chunk in chunks:
        # Tags
        for tag in chunk.get("tags", []):
            normalized = tag.lower().strip()
            discovered_entity_types.add(normalized)
        
        # Content kind
        ck = chunk.get("content_kind")
        if ck and ck in CONTENT_KIND_TO_MENTION_TYPE:
            if CONTENT_KIND_TO_MENTION_TYPE[ck]:  # Not None
                discovered_entity_types.add(ck.lower())
    
    # Map discovered entity types to mention types
    mappings: Dict[str, Set[str]] = defaultdict(set)
    unmapped: List[str] = []
    
    for entity_type in discovered_entity_types:
        # Try both original and singularized forms
        forms_to_try = [entity_type, singularize(entity_type)]
        
        mapped = False
        for form in forms_to_try:
            if form in TAG_TO_MENTION_TYPE:
                mention_type = TAG_TO_MENTION_TYPE[form]
                # Add the SINGULARIZED form for consistency
                mappings[mention_type].add(singularize(entity_type))
                mapped = True
                break
        
        if not mapped and entity_type not in {"combat", "character_creation", "playing_the_game"}:
            # Skip known non-entity tags
            unmapped.append(entity_type)
    
    if merge_with_defaults:
        # Ensure common entity types are present even if not in document
        default_mappings = {
            "role": {"ancestry", "class", "archetype", "background", "heritage", "race"},
            "mechanic": {"feat", "spell", "ability", "action", "skill", "item"},
            "condition": {"condition", "status"},
        }
        for mt, entity_types in default_mappings.items():
            mappings[mt].update(entity_types)
    
    return dict(mappings)


def infer_mention_type_mappings_from_file(
    enriched_path: Union[str, Path],
    merge_with_defaults: bool = True
) -> Dict[str, Set[str]]:
    """
    Load enriched data from file and infer mappings.
    
    Args:
        enriched_path: Path to merged.enriched.json or similar
        merge_with_defaults: If True, include default entity types
    
    Returns:
        Dict mapping mention_type -> set of entity_types
    """
    with open(enriched_path) as f:
        data = json.load(f)
    
    return infer_mention_type_mappings(data, merge_with_defaults)


def get_entity_type_to_mention_type(
    mappings: Dict[str, Set[str]]
) -> Dict[str, str]:
    """
    Invert the mappings for lookup: entity_type -> mention_type.
    
    Args:
        mappings: Dict from mention_type -> set of entity_types
    
    Returns:
        Dict from entity_type -> mention_type
    """
    inverted: Dict[str, str] = {}
    for mention_type, entity_types in mappings.items():
        for et in entity_types:
            inverted[et] = mention_type
    return inverted
