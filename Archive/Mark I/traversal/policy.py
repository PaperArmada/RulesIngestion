"""
Traversal policies per query intent.

Traversal policy is conditional logic, not intelligence.
Different intents get different edge types and depths.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Set


class Intent(Enum):
    """Query intent types."""
    DEFINITION = auto()   # "What is X?", "What does X do?"
    PROCEDURE = auto()    # "How do I X?", "Steps for X"
    EXCEPTION = auto()    # "Does X apply when Y?"
    COMPARISON = auto()   # "X vs Y", "Difference between X and Y"
    LOOKUP = auto()       # "What's the DC for X?", "Table of X"
    UNKNOWN = auto()      # Fallback for ambiguous queries


@dataclass
class TraversalPolicy:
    """
    Policy controlling how traversal behaves.
    
    Attributes:
        allow_edges: Set of edge relation types to follow
        max_depth: Maximum BFS traversal depth
        include_siblings: Whether to include section siblings
        chunk_limit: Maximum chunks to return
    """
    allow_edges: Set[str]
    max_depth: int
    include_siblings: bool = False
    chunk_limit: int = 50


@dataclass
class TraversalBudget:
    """
    Budget constraints for traversal.
    
    Attributes:
        max_nodes: Maximum number of nodes to visit
        max_depth: Maximum traversal depth
    """
    max_nodes: int = 2000
    max_depth: int = 3


# Policy table mapping intent to traversal rules
# Based on user spec:
# - definition: wide context (section → chapter → glossary), depth 2
# - procedure: linear rules (section → next), depth 1
# - exception: narrow (section → exception_to), depth 2
# - comparison: lateral (section siblings + same tag), depth 1
# - lookup: direct (table / figure references only), depth 1

INTENT_POLICIES = {
    Intent.DEFINITION: TraversalPolicy(
        allow_edges={
            "contains",           # Document/section contains chunks
            "next",               # Sequential adjacency
            "describes",          # Chunk describes entity
            "mentioned_in",       # Entity mentioned in chunk
            "mentions_same_entity",  # Chunks mentioning same entity
        },
        max_depth=2,
        include_siblings=True,
        chunk_limit=100,
    ),
    
    Intent.PROCEDURE: TraversalPolicy(
        allow_edges={
            "next",               # Sequential - follow the procedure
            "contains",           # Stay within section
        },
        max_depth=1,
        include_siblings=False,
        chunk_limit=30,
    ),
    
    Intent.EXCEPTION: TraversalPolicy(
        allow_edges={
            "contains",
            "next",
            "mentions_same_entity",
        },
        max_depth=2,
        include_siblings=False,
        chunk_limit=50,
    ),
    
    Intent.COMPARISON: TraversalPolicy(
        allow_edges={
            "mentions_same_entity",  # Chunks about same entities
            "contains",
        },
        max_depth=1,
        include_siblings=True,  # Include siblings for lateral comparison
        chunk_limit=50,
    ),
    
    Intent.LOOKUP: TraversalPolicy(
        allow_edges={
            "contains",           # Direct containment
            "next",               # Adjacent table cells
        },
        max_depth=1,
        include_siblings=False,
        chunk_limit=20,
    ),
    
    Intent.UNKNOWN: TraversalPolicy(
        # Fallback: use permissive definition-style policy
        allow_edges={
            "contains",
            "next",
            "describes",
            "mentioned_in",
            "mentions_same_entity",
        },
        max_depth=2,
        include_siblings=True,
        chunk_limit=100,
    ),
}


def get_policy(intent: Intent) -> TraversalPolicy:
    """Get traversal policy for an intent."""
    return INTENT_POLICIES.get(intent, INTENT_POLICIES[Intent.UNKNOWN])
