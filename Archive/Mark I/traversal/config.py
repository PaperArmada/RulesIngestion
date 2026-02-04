"""
Traversal configuration system.

Manages all configurable elements of the traversal system:
- Priority game terms (conditions, spells, feats)
- Document selection keywords
- Intent classification patterns
- Traversal policies per intent

Supports:
- Extraction from enriched data
- Per-ruleset config files
- Runtime override
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .policy import Intent, TraversalPolicy


@dataclass
class TraversalConfig:
    """
    Complete configuration for traversal-only retrieval.
    
    Can be:
    - Built from defaults
    - Extracted from enriched data
    - Loaded from JSON config file
    - Combined (defaults + extracted + overrides)
    """
    
    # Ruleset identification
    ruleset_id: str = "generic"
    
    # Priority game terms - always anchor to matching chunks
    condition_names: Set[str] = field(default_factory=set)
    spell_names: Set[str] = field(default_factory=set)
    feat_names: Set[str] = field(default_factory=set)
    item_names: Set[str] = field(default_factory=set)
    action_names: Set[str] = field(default_factory=set)
    
    # Document selection keywords
    player_keywords: Set[str] = field(default_factory=set)
    gm_keywords: Set[str] = field(default_factory=set)
    
    # Intent classification patterns (regex)
    intent_patterns: Dict[str, List[str]] = field(default_factory=dict)
    
    # Traversal policies per intent
    policies: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Phase 3 (seed contract): when True, find_anchor_nodes reorders anchors by
    # authority-for-seeding (definition/canonical first) before capping.
    # See Docs/PLAN-Failure-Taxonomy-And-Constraints.md §4.1 (If A dominant).
    use_authority_for_seeding: bool = False

    @property
    def priority_game_terms(self) -> Set[str]:
        """All game terms that should get priority anchoring."""
        return (
            self.condition_names |
            self.spell_names |
            self.feat_names |
            self.item_names |
            self.action_names
        )
    
    def get_policy(self, intent: Intent) -> TraversalPolicy:
        """Get traversal policy for an intent."""
        intent_name = intent.name.lower()
        if intent_name in self.policies:
            policy_dict = self.policies[intent_name]
            return TraversalPolicy(
                allow_edges=set(policy_dict.get("allow_edges", [])),
                max_depth=policy_dict.get("max_depth", 2),
                include_siblings=policy_dict.get("include_siblings", False),
                chunk_limit=policy_dict.get("chunk_limit", 50),
            )
        # Fall back to defaults
        from .policy import INTENT_POLICIES
        return INTENT_POLICIES.get(intent, INTENT_POLICIES[Intent.UNKNOWN])
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "ruleset_id": self.ruleset_id,
            "condition_names": sorted(self.condition_names),
            "spell_names": sorted(self.spell_names),
            "feat_names": sorted(self.feat_names),
            "item_names": sorted(self.item_names),
            "action_names": sorted(self.action_names),
            "player_keywords": sorted(self.player_keywords),
            "gm_keywords": sorted(self.gm_keywords),
            "intent_patterns": self.intent_patterns,
            "policies": self.policies,
            "use_authority_for_seeding": self.use_authority_for_seeding,
        }
    
    def save(self, path: Path) -> None:
        """Save config to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> "TraversalConfig":
        """Load config from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            ruleset_id=data.get("ruleset_id", "generic"),
            condition_names=set(data.get("condition_names", [])),
            spell_names=set(data.get("spell_names", [])),
            feat_names=set(data.get("feat_names", [])),
            item_names=set(data.get("item_names", [])),
            action_names=set(data.get("action_names", [])),
            player_keywords=set(data.get("player_keywords", [])),
            gm_keywords=set(data.get("gm_keywords", [])),
            intent_patterns=data.get("intent_patterns", {}),
            policies=data.get("policies", {}),
            use_authority_for_seeding=bool(data.get("use_authority_for_seeding", False)),
        )
    
    def save_to_mongo(
        self,
        mongo_uri: str,
        version: str = "v1",
        db_name: str = "rules_ingestion",
    ) -> str:
        """
        Save config to MongoDB.
        
        Args:
            mongo_uri: MongoDB connection URI
            version: Version string for the config
            db_name: Database name
            
        Returns:
            Inserted/updated document ID as string
        """
        from .store import save_traversal_config
        return save_traversal_config(self, mongo_uri, version, db_name)
    
    @classmethod
    def load_from_mongo(
        cls,
        ruleset_id: str,
        mongo_uri: str,
        version: Optional[str] = None,
        db_name: str = "rules_ingestion",
    ) -> Optional["TraversalConfig"]:
        """
        Load config from MongoDB.
        
        Args:
            ruleset_id: Ruleset identifier
            mongo_uri: MongoDB connection URI
            version: Specific version to fetch (None = latest)
            db_name: Database name
            
        Returns:
            TraversalConfig or None if not found
        """
        from .store import fetch_traversal_config
        return fetch_traversal_config(ruleset_id, mongo_uri, version, db_name)
    
    @classmethod
    def from_defaults(cls, ruleset_id: str = "generic") -> "TraversalConfig":
        """Create config with sensible defaults."""
        return cls(
            ruleset_id=ruleset_id,
            # Default condition names (cross-system common conditions)
            condition_names={
                "blinded", "broken", "clumsy", "confused", "controlled",
                "dazzled", "deafened", "doomed", "drained", "dying",
                "encumbered", "enfeebled", "fascinated", "fatigued",
                "fleeing", "frightened", "grabbed", "hidden", "immobilized",
                "invisible", "observed", "paralyzed", "persistent",
                "petrified", "prone", "quickened", "restrained", "sickened",
                "slowed", "stunned", "stupefied", "unconscious", "undetected",
                "unfriendly", "unnoticed", "wounded",
                # SF2e specific
                "flat-footed", "offguard", "off-guard",
            },
            player_keywords={
                "character", "player", "ancestry", "class", "feat", "spell",
                "background", "skill", "ability", "level", "equipment",
                "armor", "weapon", "item", "heritage", "archetype",
            },
            gm_keywords={
                "gm", "gamemaster", "game master", "npc", "creature",
                "monster", "hazard", "encounter", "trap", "environment",
                "difficulty", "treasure", "reward", "adventure", "campaign",
            },
        )
    
    @classmethod
    def extract_from_chunks(
        cls,
        chunks: List[Dict[str, Any]],
        ruleset_id: str = "extracted",
    ) -> "TraversalConfig":
        """
        Extract configuration from enriched chunks.
        
        Uses content_kind and tags to find game term definitions.
        """
        config = cls(ruleset_id=ruleset_id)
        
        # Group chunks by content_kind
        by_kind: Dict[str, List[Dict]] = {}
        for chunk in chunks:
            kind = chunk.get("content_kind", "").lower()
            if kind:
                by_kind.setdefault(kind, []).append(chunk)
        
        # Extract spell names from spell chunks
        for chunk in by_kind.get("spell", []):
            name = _extract_game_term_name(chunk)
            if name:
                config.spell_names.add(name)
        
        # Extract feat names from feat chunks
        for chunk in by_kind.get("feat", []):
            name = _extract_game_term_name(chunk)
            if name:
                config.feat_names.add(name)
        
        # Extract condition names from chunks tagged 'conditions'
        # Focus on chunks that look like definitions (content_kind='rule')
        for chunk in chunks:
            if "conditions" in chunk.get("tags", []):
                if chunk.get("content_kind") == "rule":
                    name = _extract_condition_name(chunk)
                    if name:
                        config.condition_names.add(name)
        
        return config
    
    def merge_with(self, other: "TraversalConfig") -> "TraversalConfig":
        """
        Merge with another config. Other takes precedence for conflicts.
        Sets are unioned.
        """
        return TraversalConfig(
            ruleset_id=other.ruleset_id or self.ruleset_id,
            condition_names=self.condition_names | other.condition_names,
            spell_names=self.spell_names | other.spell_names,
            feat_names=self.feat_names | other.feat_names,
            item_names=self.item_names | other.item_names,
            action_names=self.action_names | other.action_names,
            player_keywords=self.player_keywords | other.player_keywords,
            gm_keywords=self.gm_keywords | other.gm_keywords,
            intent_patterns={**self.intent_patterns, **other.intent_patterns},
            policies={**self.policies, **other.policies},
            use_authority_for_seeding=other.use_authority_for_seeding or self.use_authority_for_seeding,
        )


def _extract_game_term_name(chunk: Dict[str, Any]) -> Optional[str]:
    """
    Extract game term name from a chunk.
    
    Looks for patterns like:
    - **Fireball** Spell 3
    - Fireball [two-actions] Spell 3
    """
    text = chunk.get("text", "")
    if not text:
        return None
    
    # Try to find bold name at start: **Name**
    match = re.match(r"\*\*([A-Za-z][A-Za-z\s\-']+)\*\*", text)
    if match:
        name = match.group(1).strip().lower()
        # Clean up multi-word names
        name = re.sub(r"\s+", " ", name)
        return name if len(name) > 1 else None
    
    # Try first capitalized word(s) before action symbols
    match = re.match(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text)
    if match:
        name = match.group(1).strip().lower()
        return name if len(name) > 2 else None
    
    return None


def _extract_condition_name(chunk: Dict[str, Any]) -> Optional[str]:
    """
    Extract condition name from a condition definition chunk.
    
    Condition definitions typically start with the condition name
    followed by a description of its effects.
    """
    text = chunk.get("text", "")
    if not text:
        return None
    
    # Pattern: "You're [condition_effect]" or "[Condition] You..."
    # Try to find the first word if it looks like a condition name
    
    # Check for pattern like "Grabbed You're held..."
    # First word before "You" or description
    words = text.split()
    if not words:
        return None
    
    first_word = words[0].lower()
    
    # Skip common non-condition starters
    skip_words = {"you", "you're", "your", "the", "a", "an", "if", "when", "this"}
    if first_word in skip_words:
        return None
    
    # Clean up
    name = re.sub(r"[^a-z\-]", "", first_word)
    
    return name if len(name) > 2 else None


def build_config(
    chunks: List[Dict[str, Any]],
    ruleset_id: str,
    config_path: Optional[Path] = None,
) -> TraversalConfig:
    """
    Build complete traversal config.
    
    Priority (later overrides earlier):
    1. Defaults
    2. Extracted from chunks
    3. Loaded from config file (if provided)
    """
    # Start with defaults
    config = TraversalConfig.from_defaults(ruleset_id)
    
    # Merge with extracted
    extracted = TraversalConfig.extract_from_chunks(chunks, ruleset_id)
    config = config.merge_with(extracted)
    
    # Merge with file config if provided
    if config_path and config_path.exists():
        file_config = TraversalConfig.load(config_path)
        config = config.merge_with(file_config)

    # Env override for Phase 3 seed contract (baseline vs contract in Phase 4)
    env_flag = os.environ.get("RULES_USE_AUTHORITY_FOR_SEEDING", "").strip().lower()
    if env_flag in ("1", "true", "yes"):
        config.use_authority_for_seeding = True

    return config
