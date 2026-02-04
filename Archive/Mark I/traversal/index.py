"""
TraversalIndex: Pre-built indexes for fast anchor node lookup.

The graph is just nodes and edges - no fast lookups.
This module builds indexes from graph + enriched chunks for O(1) anchor finding.

TraversalProjection: Entity-only graph view for traversal experiments.
Per HANDOFF-Entity-Only-Traversal-Experiment-2026-01-30.md:
- Facts may only be included in an explanation after an entity path is selected.
- Facts never create new entity reachability.
"""

from __future__ import annotations

import math
import re
import json
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from enrichment.graph_builder import is_entity_like, get_node_kind, NodeKind


class TraversalMode(str, Enum):
    """Traversal mode for entity-only experiments.
    
    FULL: Current behavior (entity + fact mixed traversal).
    ENTITY_ONLY: Entity-only projection - facts excluded from frontier expansion.
    """
    FULL = "full"
    ENTITY_ONLY = "entity"


# Semantic edges between entities (used in entity-only projection)
# These edges represent reasoning relationships, not structural containment
# E1/E2/E3/E4: HANDOFF-Semantic-Edge-Enrichment-Under-Expressivity-Experiment
SEMANTIC_ENTITY_RELATIONS = {
    "requires",
    "modifies",
    "replaces_effect",
    "overrides",
    "triggers",
    "contrasts_with",
    "overridden_by",
    "changes_outcome",
    "unless",
    "suppresses",
    "excludes_outcome",
    "references_mechanic",
    "requires_mechanic",
    "modifies_mechanic",
    "affects",
    "results_in",
    "part_of",
    "branches_from",
    "step_of",
    "precedes",
    "follows",
    "requires_condition",
    "negated_by",
    "affects_stat",
    "affects_condition",
    # Entity-to-entity structural edges (collapsed from entity→chunk→entity)
    "structural_coreference",
    "mentions_same_entity",
}

# Edges that connect entities to facts (excluded from entity-only traversal)
FACT_ATTACHMENT_RELATIONS = {
    "has_fact",
    "belongs_to",
    "asserts_about",
}

# Causal entity–entity edges (subset of SEMANTIC_ENTITY_RELATIONS).
# Used for edge-selectivity experiments: HANDOFF-Entity-Entity-Edge-Selectivity-Experiment.
# E1–E4 enrichment: procedural flow, conditional, effect–target, replacement semantics.
CAUSAL_ENTITY_RELATIONS = {
    "triggers",
    "requires",
    "replaces_effect",
    "modifies",
    "overrides",
    "modifies_mechanic",
    "requires_mechanic",
    "changes_outcome",
    "unless",
    "suppresses",
    "excludes_outcome",
    "affects",
    "results_in",
    "step_of",
    "precedes",
    "follows",
    "requires_condition",
    "negated_by",
    "affects_stat",
    "affects_condition",
}


class EdgeVariant(str, Enum):
    """Edge expansion variant for entity-only traversal experiments.

    BASELINE: All semantic entity–entity edges expand the frontier.
    A: Beyond depth 1, only causal edges expand (depth >= 1 → causal only).
    B: At all depths, only causal edges expand.
    C: Priority ordering: expand via causal edges first, then other semantic (same BFS level).
    D: Beyond depth 2, only causal edges expand (depth >= 2 → causal only).
    """
    BASELINE = "baseline"
    A = "A"   # causal-only beyond depth 1
    B = "B"   # causal-only at all depths
    C = "C"   # causal-first priority
    D = "D"   # causal-only beyond depth 2


@dataclass
class TraversalProjection:
    """Entity-only view of the graph for traversal.
    
    In ENTITY_ONLY mode:
      - nodes: only is_entity_like(node) returns True
      - edges: only semantic entity–entity edges
      - facts excluded from frontier expansion
    
    Facts may still be CONSULTED after traversal, but they must not
    EXPAND the search frontier.
    """
    
    # Entity-only node set
    entity_ids: Set[str] = field(default_factory=set)
    
    # Entity-to-entity adjacency (only semantic edges)
    entity_adjacency: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Edge types for entity-entity edges
    entity_edge_types: Dict[Tuple[str, str], str] = field(default_factory=dict)
    
    # Fact attachment: entity_id → {fact_ids that belong to it}
    entity_to_facts: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Reverse mapping: fact_id → {entity_ids that own it}
    # Used to map fact seeds to owning entities for entity-only traversal
    fact_to_entities: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Fact nodes (for post-hoc attachment)
    fact_nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Mode used to build this projection
    mode: TraversalMode = TraversalMode.ENTITY_ONLY
    
    @classmethod
    def build(
        cls,
        graph: Dict[str, Any],
        mode: TraversalMode = TraversalMode.ENTITY_ONLY,
    ) -> "TraversalProjection":
        """Build a traversal projection from graph.
        
        Args:
            graph: Dict with "nodes" and "edges" lists
            mode: ENTITY_ONLY (default) or FULL
            
        Returns:
            TraversalProjection with entity-only adjacency
        """
        proj = cls(mode=mode)
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        
        # Partition nodes by kind
        for node in nodes:
            node_id = node.get("id", "")
            if not node_id:
                continue
            kind = get_node_kind(node)
            if kind == NodeKind.ENTITY:
                proj.entity_ids.add(node_id)
            elif kind == NodeKind.FACT:
                proj.fact_nodes[node_id] = node
        
        # Build entity-to-entity adjacency and fact attachments
        entity_adjacency: Dict[str, Set[str]] = defaultdict(set)
        entity_to_facts: Dict[str, Set[str]] = defaultdict(set)
        fact_to_entities: Dict[str, Set[str]] = defaultdict(set)
        
        for edge in edges:
            source = edge.get("source", "")
            target = edge.get("target", "")
            relation = edge.get("relation", "")
            
            if not source or not target:
                continue
            
            # Track fact attachments (entity owns fact)
            if relation in FACT_ATTACHMENT_RELATIONS:
                if relation == "belongs_to" and source in proj.fact_nodes:
                    # fact → entity ownership
                    if target in proj.entity_ids:
                        entity_to_facts[target].add(source)
                        fact_to_entities[source].add(target)  # Reverse mapping
                elif relation == "has_fact" and target in proj.fact_nodes:
                    # chunk/entity → fact
                    pass  # We track via belongs_to
                continue
            
            # In ENTITY_ONLY mode, only include entity-entity semantic edges
            if mode == TraversalMode.ENTITY_ONLY:
                if source not in proj.entity_ids or target not in proj.entity_ids:
                    continue
                if relation not in SEMANTIC_ENTITY_RELATIONS:
                    continue
            
            # Build bidirectional adjacency for entity-entity edges
            if source in proj.entity_ids and target in proj.entity_ids:
                entity_adjacency[source].add(target)
                entity_adjacency[target].add(source)
                proj.entity_edge_types[(source, target)] = relation
                proj.entity_edge_types[(target, source)] = relation
        
        proj.entity_adjacency = dict(entity_adjacency)
        proj.entity_to_facts = dict(entity_to_facts)
        proj.fact_to_entities = dict(fact_to_entities)
        
        return proj
    
    def get_entity_neighbors(
        self,
        entity_id: str,
        allowed_relations: Optional[Set[str]] = None,
    ) -> Set[str]:
        """Get entity neighbors of an entity node.
        
        Args:
            entity_id: The entity to get neighbors for
            allowed_relations: If provided, only return neighbors connected
                              by these relation types
                              
        Returns:
            Set of neighbor entity IDs (never includes facts)
        """
        neighbors = self.entity_adjacency.get(entity_id, set())
        
        if allowed_relations is None:
            return neighbors
        
        # Filter by relation type
        filtered = set()
        for neighbor in neighbors:
            relation = self.entity_edge_types.get((entity_id, neighbor), "")
            if relation in allowed_relations:
                filtered.add(neighbor)
        return filtered
    
    def attach_facts_post_hoc(
        self,
        entity_path: Set[str],
    ) -> Set[str]:
        """Attach facts to a selected entity path.
        
        Per the assertion attachment rule:
        > Facts may only be included in an explanation after an entity path is selected.
        
        This ensures facts never create new entity reachability.
        
        Args:
            entity_path: Set of entity IDs selected by traversal
            
        Returns:
            Set of fact IDs attached to the entity path
        """
        attached_facts: Set[str] = set()
        for entity_id in entity_path:
            facts = self.entity_to_facts.get(entity_id, set())
            attached_facts.update(facts)
        return attached_facts
    
    def map_seeds_to_entities(
        self,
        seeds: Set[str],
    ) -> Set[str]:
        """Map mixed seeds (facts + entities) to entity seeds only.
        
        For entity-only traversal, fact seeds must be mapped to their owning
        entities via belongs_to edges. This ensures entity-only traversal
        starts from entities, not facts.
        
        Args:
            seeds: Mixed set of fact IDs and/or entity IDs
            
        Returns:
            Set of entity IDs (facts mapped to their owners, entities passed through)
        """
        entity_seeds: Set[str] = set()
        for seed in seeds:
            if seed in self.entity_ids:
                # Already an entity
                entity_seeds.add(seed)
            elif seed in self.fact_nodes:
                # Map fact to owning entities
                owners = self.fact_to_entities.get(seed, set())
                entity_seeds.update(owners)
        return entity_seeds


# Common English stopwords to filter from term index
STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "this", "that", "these", "those", "it", "its", "you", "your", "we",
    "our", "they", "their", "he", "she", "him", "her", "his", "i", "my",
    "me", "what", "which", "who", "whom", "how", "when", "where", "why",
    "if", "then", "else", "so", "than", "too", "very", "just", "only",
    "also", "not", "no", "yes", "all", "any", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "into", "through",
    "during", "before", "after", "above", "below", "between", "under",
    "again", "further", "once", "here", "there", "about", "up", "down",
})


def tokenize_and_normalize(text: str) -> List[str]:
    """
    Tokenize text into normalized lowercase terms.
    
    - Converts to lowercase
    - Splits on non-alphanumeric characters
    - Filters stopwords
    - Filters very short tokens (< 2 chars)
    """
    if not text:
        return []
    
    # Lowercase and split on non-alphanumeric
    text_lower = text.lower()
    tokens = re.split(r"[^a-z0-9]+", text_lower)
    
    # Filter stopwords and short tokens
    return [
        t for t in tokens
        if t and len(t) >= 2 and t not in STOPWORDS
    ]


@dataclass
class TraversalIndex:
    """
    Pre-built indexes for fast anchor node lookup.
    
    Indexes:
    - term_to_chunks: "fireball" → {chunk_ids...}
    - section_title_to_chunks: "conditions" → {chunk_ids...}
    - content_kind_to_chunks: "spell" → {chunk_ids...}
    - tag_to_chunks: "actions" → {chunk_ids...}
    - trait_to_chunks: "mental" → {chunk_ids...}
    - entity_name_to_id: "fireball" → canonical entity ID
    - entity_to_chunks: entity_id → {chunk_ids that mention it}
    - adjacency: node_id → {neighbor_ids...} (bidirectional)
    - edge_types: (source, target) → relation type
    - chunk_by_id: chunk_id → chunk dict
    """
    
    # Text-based lookups (normalized lowercase)
    term_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    section_title_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    
    # IDF weights for term scoring (rare terms score higher)
    term_idf: Dict[str, float] = field(default_factory=dict)
    
    # Bigram indexes for phrase matching
    bigram_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    bigram_idf: Dict[str, float] = field(default_factory=dict)
    
    # Structural lookups
    content_kind_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    tag_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    trait_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Entity lookups
    entity_name_to_id: Dict[str, str] = field(default_factory=dict)
    entity_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Graph adjacency (bidirectional)
    adjacency: Dict[str, Set[str]] = field(default_factory=dict)
    edge_types: Dict[Tuple[str, str], str] = field(default_factory=dict)
    
    # Chunk metadata
    chunk_by_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Stats
    total_chunks: int = 0
    total_edges: int = 0
    
    @classmethod
    def build(
        cls,
        graph: Dict[str, Any],
        chunks: List[Dict[str, Any]],
    ) -> "TraversalIndex":
        """
        Build index from graph and enriched chunks.
        
        Args:
            graph: Dict with "nodes" and "edges" lists
            chunks: List of enriched chunk dicts
            
        Returns:
            TraversalIndex with all indexes populated
        """
        index = cls()
        
        # Build chunk-based indexes
        index._index_chunks(chunks)
        
        # Build graph-based indexes
        index._index_graph(graph)
        
        return index
    
    def _index_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """Build indexes from enriched chunks."""
        term_to_chunks: Dict[str, Set[str]] = defaultdict(set)
        section_title_to_chunks: Dict[str, Set[str]] = defaultdict(set)
        content_kind_to_chunks: Dict[str, Set[str]] = defaultdict(set)
        tag_to_chunks: Dict[str, Set[str]] = defaultdict(set)
        trait_to_chunks: Dict[str, Set[str]] = defaultdict(set)
        
        for chunk in chunks:
            chunk_id = chunk.get("id", "")
            if not chunk_id:
                continue
            
            # Store chunk by ID
            self.chunk_by_id[chunk_id] = chunk
            
            # Index text terms
            text = chunk.get("text", "")
            terms = tokenize_and_normalize(text)
            for term in terms:
                term_to_chunks[term].add(chunk_id)
            
            # Index section path
            section_path = chunk.get("section_path", [])
            if section_path:
                # Index each section title
                for title in section_path:
                    title_lower = title.lower().strip()
                    if title_lower:
                        section_title_to_chunks[title_lower].add(chunk_id)
                # Also index individual words from section titles
                for title in section_path:
                    for term in tokenize_and_normalize(title):
                        section_title_to_chunks[term].add(chunk_id)
            
            # Index content kind
            content_kind = chunk.get("content_kind", "")
            if content_kind:
                kind_lower = content_kind.lower()
                content_kind_to_chunks[kind_lower].add(chunk_id)
            
            # Index tags
            for tag in chunk.get("tags", []):
                tag_lower = tag.lower().strip()
                if tag_lower:
                    tag_to_chunks[tag_lower].add(chunk_id)
            
            # Index traits
            for trait in chunk.get("traits", []):
                trait_lower = trait.lower().strip()
                if trait_lower:
                    trait_to_chunks[trait_lower].add(chunk_id)
        
        # Convert to regular dicts
        self.term_to_chunks = dict(term_to_chunks)
        self.section_title_to_chunks = dict(section_title_to_chunks)
        self.content_kind_to_chunks = dict(content_kind_to_chunks)
        self.tag_to_chunks = dict(tag_to_chunks)
        self.trait_to_chunks = dict(trait_to_chunks)
        self.total_chunks = len(self.chunk_by_id)
        
        # Compute IDF weights for all terms
        # IDF(term) = log(N / df) where N = total chunks, df = document frequency
        total_chunks = self.total_chunks
        if total_chunks > 0:
            for term, chunk_ids in self.term_to_chunks.items():
                df = len(chunk_ids)  # document frequency
                if df > 0:
                    self.term_idf[term] = math.log(total_chunks / df)
                else:
                    self.term_idf[term] = 0.0
        
        # Build bigram index for phrase matching
        bigram_to_chunks: Dict[str, Set[str]] = defaultdict(set)
        
        for chunk in chunks:
            chunk_id = chunk.get("id", "")
            if not chunk_id:
                continue
            
            text = chunk.get("text", "")
            tokens = tokenize_and_normalize(text)
            
            # Create bigrams from adjacent tokens
            for i in range(len(tokens) - 1):
                bigram = f"{tokens[i]}_{tokens[i+1]}"
                bigram_to_chunks[bigram].add(chunk_id)
        
        self.bigram_to_chunks = dict(bigram_to_chunks)
        
        # Compute IDF for bigrams
        if total_chunks > 0:
            for bigram, chunk_ids in self.bigram_to_chunks.items():
                df = len(chunk_ids)
                if df > 0:
                    self.bigram_idf[bigram] = math.log(total_chunks / df)
                else:
                    self.bigram_idf[bigram] = 0.0
    
    def _index_graph(self, graph: Dict[str, Any]) -> None:
        """Build indexes from graph structure."""
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        
        entity_ids = {n["id"] for n in nodes if is_entity_like(n)}
        
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        edge_types: Dict[Tuple[str, str], str] = {}
        entity_to_chunks: Dict[str, Set[str]] = defaultdict(set)
        entity_name_to_id: Dict[str, str] = {}
        
        # Index entity nodes only (exclude structural, fact)
        for node in nodes:
            if not is_entity_like(node):
                continue
            node_id = node.get("id", "")
            name = node.get("name", "")
            normalized_name = node.get("normalized_name", name)
            canonical_key = node.get("canonical_key", "")
            
            if canonical_key:
                entity_name_to_id[canonical_key] = node_id
            if normalized_name:
                entity_name_to_id[normalized_name.lower()] = node_id
            if name:
                entity_name_to_id[name.lower()] = node_id
        
        # Index edges
        for edge in edges:
            source = edge.get("source", "")
            target = edge.get("target", "")
            relation = edge.get("relation", "")
            
            if not source or not target:
                continue
            
            # Build bidirectional adjacency
            adjacency[source].add(target)
            adjacency[target].add(source)
            
            # Store edge types
            edge_types[(source, target)] = relation
            edge_types[(target, source)] = relation  # Bidirectional
            
            # Track entity-to-chunk relationships (only for entity nodes)
            if relation in ("describes", "mentioned_in"):
                if source in entity_ids:
                    entity_to_chunks[source].add(target)
                if target in entity_ids:
                    entity_to_chunks[target].add(source)
            
            # Track mentions_same_entity edges
            if relation == "mentions_same_entity":
                entity_id = edge.get("entity_id", "")
                if entity_id and entity_id in entity_ids:
                    entity_to_chunks[entity_id].add(source)
                    entity_to_chunks[entity_id].add(target)
        
        self.adjacency = dict(adjacency)
        self.edge_types = edge_types
        self.entity_to_chunks = dict(entity_to_chunks)
        self.entity_name_to_id = entity_name_to_id
        self.total_edges = len(edges)
    
    def get_neighbors(
        self,
        node_id: str,
        allowed_relations: Optional[Set[str]] = None,
    ) -> Set[str]:
        """
        Get neighbors of a node, optionally filtered by relation type.
        
        Args:
            node_id: The node to get neighbors for
            allowed_relations: If provided, only return neighbors connected
                              by these relation types
                              
        Returns:
            Set of neighbor node IDs
        """
        neighbors = self.adjacency.get(node_id, set())
        
        if allowed_relations is None:
            return neighbors
        
        # Filter by relation type
        filtered = set()
        for neighbor in neighbors:
            relation = self.edge_types.get((node_id, neighbor), "")
            if relation in allowed_relations:
                filtered.add(neighbor)
        return filtered
    
    def save(self, path: Path) -> None:
        """Save index to JSON file."""
        data = {
            "term_to_chunks": {k: list(v) for k, v in self.term_to_chunks.items()},
            "section_title_to_chunks": {k: list(v) for k, v in self.section_title_to_chunks.items()},
            "content_kind_to_chunks": {k: list(v) for k, v in self.content_kind_to_chunks.items()},
            "tag_to_chunks": {k: list(v) for k, v in self.tag_to_chunks.items()},
            "trait_to_chunks": {k: list(v) for k, v in self.trait_to_chunks.items()},
            "entity_name_to_id": self.entity_name_to_id,
            "entity_to_chunks": {k: list(v) for k, v in self.entity_to_chunks.items()},
            "adjacency": {k: list(v) for k, v in self.adjacency.items()},
            # IDF weights
            "term_idf": self.term_idf,
            # Bigram indexes
            "bigram_to_chunks": {k: list(v) for k, v in self.bigram_to_chunks.items()},
            "bigram_idf": self.bigram_idf,
            # Don't save edge_types (too large) - rebuild from graph
            # Don't save chunk_by_id (too large) - reload from chunks
            "total_chunks": self.total_chunks,
            "total_edges": self.total_edges,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Path, chunks: Optional[List[Dict]] = None) -> "TraversalIndex":
        """Load index from JSON file."""
        with open(path) as f:
            data = json.load(f)
        
        index = cls(
            term_to_chunks={k: set(v) for k, v in data.get("term_to_chunks", {}).items()},
            section_title_to_chunks={k: set(v) for k, v in data.get("section_title_to_chunks", {}).items()},
            content_kind_to_chunks={k: set(v) for k, v in data.get("content_kind_to_chunks", {}).items()},
            tag_to_chunks={k: set(v) for k, v in data.get("tag_to_chunks", {}).items()},
            trait_to_chunks={k: set(v) for k, v in data.get("trait_to_chunks", {}).items()},
            entity_name_to_id=data.get("entity_name_to_id", {}),
            entity_to_chunks={k: set(v) for k, v in data.get("entity_to_chunks", {}).items()},
            adjacency={k: set(v) for k, v in data.get("adjacency", {}).items()},
            # IDF weights
            term_idf=data.get("term_idf", {}),
            # Bigram indexes
            bigram_to_chunks={k: set(v) for k, v in data.get("bigram_to_chunks", {}).items()},
            bigram_idf=data.get("bigram_idf", {}),
            total_chunks=data.get("total_chunks", 0),
            total_edges=data.get("total_edges", 0),
        )
        
        # Rebuild chunk_by_id if chunks provided
        if chunks:
            for chunk in chunks:
                chunk_id = chunk.get("id", "")
                if chunk_id:
                    index.chunk_by_id[chunk_id] = chunk
        
        return index


def traverse_entity_only(
    seeds: Set[str],
    projection: TraversalProjection,
    max_hops: int = 3,
    edge_variant: Optional[EdgeVariant] = None,
) -> Tuple[Set[str], List[Tuple[str, str, str]], List[str]]:
    """Entity-only BFS traversal.

    Per HANDOFF-Entity-Only-Traversal-Experiment-2026-01-30.md:
    - Traversal chooses entity paths first.
    - Facts are attached post hoc as supporting assertions.
    - Facts never create new entity reachability.

    Edge selectivity (HANDOFF-Entity-Entity-Edge-Selectivity-Experiment):
    - edge_variant=None or BASELINE: all semantic edges expand.
    - A: beyond depth 1, only causal edges expand.
    - B: at all depths, only causal edges expand.
    - C: causal neighbors expanded first (priority ordering), then others.
    - D: beyond depth 2, only causal edges expand.

    Args:
        seeds: Set of entity IDs to start from
        projection: TraversalProjection with entity-only adjacency
        max_hops: Maximum traversal depth
        edge_variant: Optional EdgeVariant for selective expansion (None = BASELINE)

    Returns:
        Tuple of:
        - reachable: Set of reachable entity IDs
        - traversed_edges: List of (source, target, relation) tuples
        - visited_order: List of entity IDs in visit order

    Raises:
        AssertionError: If traversal attempts to expand through a fact node
    """
    if not seeds:
        return set(), [], []

    variant = edge_variant if edge_variant is not None else EdgeVariant.BASELINE

    # Filter seeds to only entities (invariant check)
    entity_seeds = {s for s in seeds if s in projection.entity_ids}

    # Invariant: seeds must be entities in entity-only mode
    non_entity_seeds = seeds - entity_seeds
    if non_entity_seeds and projection.mode == TraversalMode.ENTITY_ONLY:
        # Log but don't fail - just filter them out
        pass

    ordered_seeds = sorted(entity_seeds)
    visited = set(ordered_seeds)
    visited_order = list(ordered_seeds)
    queue: List[Tuple[str, int]] = [(seed, 0) for seed in ordered_seeds]
    traversed_edges: List[Tuple[str, str, str]] = []

    while queue:
        node, depth = queue.pop(0)
        if depth >= max_hops:
            continue

        # INVARIANT: Never expand through fact nodes
        assert node not in projection.fact_nodes, (
            f"Traversal attempted to expand through fact node: {node}"
        )

        # Allowed relations for this expansion step (depth = current node depth)
        allowed_relations: Optional[Set[str]] = None
        if variant == EdgeVariant.BASELINE:
            allowed_relations = None
        elif variant == EdgeVariant.A:
            allowed_relations = CAUSAL_ENTITY_RELATIONS if depth >= 1 else None
        elif variant == EdgeVariant.B:
            allowed_relations = CAUSAL_ENTITY_RELATIONS
        elif variant == EdgeVariant.D:
            allowed_relations = CAUSAL_ENTITY_RELATIONS if depth >= 2 else None
        # C: priority ordering (causal first, then rest) — handled below

        if variant == EdgeVariant.C:
            # Priority: expand causal neighbors first, then other semantic
            all_neighbors = projection.entity_adjacency.get(node, set())
            causal_neighbors = projection.get_entity_neighbors(node, CAUSAL_ENTITY_RELATIONS)
            other_neighbors = all_neighbors - causal_neighbors
            neighbor_order: List[str] = list(causal_neighbors) + list(other_neighbors)
        else:
            if allowed_relations is not None:
                neighbor_order = list(projection.get_entity_neighbors(node, allowed_relations))
            else:
                neighbor_order = list(projection.entity_adjacency.get(node, set()))

        for neighbor in neighbor_order:
            if neighbor in visited:
                continue

            # INVARIANT: Neighbors must be entities, not facts
            assert neighbor in projection.entity_ids, (
                f"Traversal found non-entity neighbor: {neighbor}"
            )

            visited.add(neighbor)
            visited_order.append(neighbor)
            relation = projection.entity_edge_types.get((node, neighbor), "")
            traversed_edges.append((node, neighbor, relation))
            queue.append((neighbor, depth + 1))

    return visited, traversed_edges, visited_order


@dataclass
class EntityOnlyTraversalResult:
    """Result of entity-only traversal with post-hoc fact attachment.
    
    Separates what traversal decided (entity paths) from what explanations
    contain (attached facts).
    """
    
    # Entity path chosen by traversal
    entity_path: Set[str] = field(default_factory=set)
    
    # Facts attached post-hoc to the entity path
    attached_facts: Set[str] = field(default_factory=set)
    
    # Traversal metadata
    traversal_depth: int = 0
    traversed_edges: List[Tuple[str, str, str]] = field(default_factory=list)
    visited_order: List[str] = field(default_factory=list)
    
    @property
    def total_entity_count(self) -> int:
        """Number of entities in the explanation."""
        return len(self.entity_path)
    
    @property
    def total_fact_count(self) -> int:
        """Number of facts attached to the explanation."""
        return len(self.attached_facts)
    
    @property
    def assertion_load(self) -> float:
        """Average facts per entity. 0 if no entities."""
        if not self.entity_path:
            return 0.0
        return len(self.attached_facts) / len(self.entity_path)


def run_entity_only_traversal(
    seeds: Set[str],
    graph: Dict[str, Any],
    max_hops: int = 3,
    mode: TraversalMode = TraversalMode.ENTITY_ONLY,
    edge_variant: Optional[EdgeVariant] = None,
) -> EntityOnlyTraversalResult:
    """Run entity-only traversal and attach facts post-hoc.

    This is the main entry point for the entity-only experiment.

    Args:
        seeds: Set of entity IDs to start from
        graph: Dict with "nodes" and "edges" lists
        max_hops: Maximum traversal depth
        mode: ENTITY_ONLY (default) or FULL
        edge_variant: Optional EdgeVariant for selective edge expansion (HANDOFF-Entity-Entity-Edge-Selectivity)

    Returns:
        EntityOnlyTraversalResult with entity path and attached facts
    """
    # Build entity-only projection
    projection = TraversalProjection.build(graph, mode=mode)

    # Run traversal
    entity_path, traversed_edges, visited_order = traverse_entity_only(
        seeds, projection, max_hops, edge_variant=edge_variant
    )
    
    # Attach facts post-hoc
    attached_facts = projection.attach_facts_post_hoc(entity_path)
    
    # Compute traversal depth
    traversal_depth = 0
    if visited_order:
        # Depth is the maximum hop count from any seed
        seed_set = {s for s in seeds if s in projection.entity_ids}
        for i, node in enumerate(visited_order):
            if node not in seed_set:
                # Count edges to reach this node
                depth = sum(1 for src, tgt, _ in traversed_edges if tgt == node)
                traversal_depth = max(traversal_depth, depth)
    
    return EntityOnlyTraversalResult(
        entity_path=entity_path,
        attached_facts=attached_facts,
        traversal_depth=traversal_depth,
        traversed_edges=traversed_edges,
        visited_order=visited_order,
    )
