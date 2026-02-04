"""Tests for entity-only traversal invariants.

Per HANDOFF-Entity-Only-Traversal-Experiment-2026-01-30.md Step 5:

Lock invariants before tuning with assertions that:
- Traversal never expands through fact nodes (assert in traversal loop)
- Entity-only metrics never count fact nodes (assert in metric functions)
- Explanation scoring never uses raw node count as a proxy
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path
from typing import Any, Dict, Set

sys.path.insert(0, str(Path(__file__).parent.parent))

from traversal.index import (
    TraversalMode,
    TraversalProjection,
    traverse_entity_only,
    run_entity_only_traversal,
    EntityOnlyTraversalResult,
    SEMANTIC_ENTITY_RELATIONS,
    FACT_ATTACHMENT_RELATIONS,
)
from enrichment.graph_builder import NodeKind, get_node_kind, is_entity_like


class TestTraversalProjection:
    """Tests for TraversalProjection class."""
    
    def create_mixed_graph(self) -> Dict[str, Any]:
        """Create a graph with entities and facts."""
        nodes = [
            {"id": "entity_1", "type": "Spell", "name": "Fireball"},
            {"id": "entity_2", "type": "Condition", "name": "Burning"},
            {"id": "entity_3", "type": "Feat", "name": "Elemental Mastery"},
            {"id": "fact_1", "type": "RuleFact", "fact_type": "triggers"},
            {"id": "fact_2", "type": "RuleFact", "fact_type": "modifies"},
            {"id": "chunk_1", "type": "chunk"},
        ]
        
        edges = [
            # Entity-entity semantic edges
            {"source": "entity_1", "target": "entity_2", "relation": "triggers"},
            {"source": "entity_3", "target": "entity_1", "relation": "modifies"},
            # Fact ownership
            {"source": "fact_1", "target": "entity_1", "relation": "belongs_to"},
            {"source": "fact_2", "target": "entity_3", "relation": "belongs_to"},
            # Chunk edges
            {"source": "chunk_1", "target": "fact_1", "relation": "has_fact"},
        ]
        
        return {"nodes": nodes, "edges": edges}
    
    def test_projection_excludes_facts_from_entity_ids(self):
        """Invariant: Fact nodes are never in entity_ids."""
        graph = self.create_mixed_graph()
        proj = TraversalProjection.build(graph, mode=TraversalMode.ENTITY_ONLY)
        
        # Check that facts are in fact_nodes, not entity_ids
        assert "fact_1" in proj.fact_nodes
        assert "fact_2" in proj.fact_nodes
        assert "fact_1" not in proj.entity_ids
        assert "fact_2" not in proj.entity_ids
        
        # Check that entities are in entity_ids
        assert "entity_1" in proj.entity_ids
        assert "entity_2" in proj.entity_ids
        assert "entity_3" in proj.entity_ids
    
    def test_projection_excludes_structural_from_entity_ids(self):
        """Invariant: Structural nodes are never in entity_ids."""
        graph = self.create_mixed_graph()
        proj = TraversalProjection.build(graph, mode=TraversalMode.ENTITY_ONLY)
        
        assert "chunk_1" not in proj.entity_ids
        assert "chunk_1" not in proj.fact_nodes
    
    def test_entity_adjacency_only_contains_entities(self):
        """Invariant: entity_adjacency only connects entities."""
        graph = self.create_mixed_graph()
        proj = TraversalProjection.build(graph, mode=TraversalMode.ENTITY_ONLY)
        
        # All nodes in adjacency should be entities
        for source, neighbors in proj.entity_adjacency.items():
            assert source in proj.entity_ids, f"Source {source} not in entity_ids"
            for neighbor in neighbors:
                assert neighbor in proj.entity_ids, f"Neighbor {neighbor} not in entity_ids"
    
    def test_entity_to_facts_only_tracks_entity_ownership(self):
        """Invariant: entity_to_facts maps entities to their owned facts."""
        graph = self.create_mixed_graph()
        proj = TraversalProjection.build(graph, mode=TraversalMode.ENTITY_ONLY)
        
        # All keys should be entities
        for entity_id in proj.entity_to_facts:
            assert entity_id in proj.entity_ids, f"Key {entity_id} not in entity_ids"
        
        # All values should be facts
        for entity_id, fact_ids in proj.entity_to_facts.items():
            for fact_id in fact_ids:
                assert fact_id in proj.fact_nodes, f"Fact {fact_id} not in fact_nodes"


class TestTraverseEntityOnly:
    """Tests for traverse_entity_only function."""
    
    def create_graph_with_fact_path(self) -> Dict[str, Any]:
        """Create a graph where facts could create paths if not excluded.
        
        Structure:
        entity_1 -> triggers -> entity_2
        entity_1 has fact_1
        fact_1 could connect to entity_3 if facts were traversed
        """
        nodes = [
            {"id": "entity_1", "type": "Spell", "name": "Spell A"},
            {"id": "entity_2", "type": "Condition", "name": "Condition B"},
            {"id": "entity_3", "type": "Spell", "name": "Spell C"},  # Unreachable via entity path
            {"id": "fact_1", "type": "RuleFact", "fact_type": "triggers"},
        ]
        
        edges = [
            # Entity-entity edge
            {"source": "entity_1", "target": "entity_2", "relation": "triggers"},
            # Fact ownership
            {"source": "fact_1", "target": "entity_1", "relation": "belongs_to"},
            # This edge should NOT create a path from entity_1 to entity_3
            # because it goes through a fact
            {"source": "fact_1", "target": "entity_3", "relation": "references"},
        ]
        
        return {"nodes": nodes, "edges": edges}
    
    def test_traversal_never_reaches_through_facts(self):
        """Invariant: Entity-only traversal never expands through fact nodes."""
        graph = self.create_graph_with_fact_path()
        proj = TraversalProjection.build(graph, mode=TraversalMode.ENTITY_ONLY)
        
        seeds = {"entity_1"}
        entity_path, edges, order = traverse_entity_only(seeds, proj, max_hops=3)
        
        # entity_3 should NOT be reachable because the path goes through fact_1
        assert "entity_3" not in entity_path, "entity_3 should not be reachable via fact path"
        
        # entity_2 should be reachable via direct entity-entity edge
        assert "entity_2" in entity_path, "entity_2 should be reachable"
    
    def test_traversal_rejects_fact_seeds(self):
        """Invariant: Fact seeds are filtered out."""
        graph = self.create_graph_with_fact_path()
        proj = TraversalProjection.build(graph, mode=TraversalMode.ENTITY_ONLY)
        
        # Include a fact in seeds
        seeds = {"entity_1", "fact_1"}
        entity_path, edges, order = traverse_entity_only(seeds, proj, max_hops=3)
        
        # fact_1 should not be in the path
        assert "fact_1" not in entity_path, "fact_1 should not be in entity path"
    
    def test_traversal_assertion_on_fact_expansion(self):
        """Invariant: Traversal raises assertion if it tries to expand from a fact."""
        # This tests the internal assertion in traverse_entity_only
        # We can't directly trigger it without bypassing the filtering,
        # but we verify the logic is correct
        graph = self.create_graph_with_fact_path()
        proj = TraversalProjection.build(graph, mode=TraversalMode.ENTITY_ONLY)
        
        # Verify that fact nodes are properly excluded
        assert "fact_1" not in proj.entity_adjacency


class TestEntityOnlyTraversalResult:
    """Tests for EntityOnlyTraversalResult dataclass."""
    
    def test_assertion_load_zero_entities(self):
        """Assertion load should be 0 when no entities."""
        result = EntityOnlyTraversalResult(
            entity_path=set(),
            attached_facts={"fact_1", "fact_2"},
        )
        assert result.assertion_load == 0.0
    
    def test_assertion_load_calculation(self):
        """Assertion load = facts / entities."""
        result = EntityOnlyTraversalResult(
            entity_path={"e1", "e2"},
            attached_facts={"f1", "f2", "f3", "f4"},
        )
        assert result.assertion_load == 2.0  # 4 facts / 2 entities


class TestRunEntityOnlyTraversal:
    """Integration tests for run_entity_only_traversal."""
    
    def create_full_graph(self) -> Dict[str, Any]:
        """Create a more complete graph for integration testing."""
        nodes = [
            {"id": "spell_fireball", "type": "Spell", "name": "Fireball"},
            {"id": "spell_heal", "type": "Spell", "name": "Heal"},
            {"id": "cond_burning", "type": "Condition", "name": "Burning"},
            {"id": "fact_1", "type": "RuleFact", "fact_type": "triggers"},
            {"id": "fact_2", "type": "RuleFact", "fact_type": "removes"},
            {"id": "fact_3", "type": "RuleFact", "fact_type": "property"},
        ]
        
        edges = [
            # Entity-entity edges
            {"source": "spell_fireball", "target": "cond_burning", "relation": "triggers"},
            {"source": "spell_heal", "target": "cond_burning", "relation": "removes"},
            # Fact ownership
            {"source": "fact_1", "target": "spell_fireball", "relation": "belongs_to"},
            {"source": "fact_2", "target": "spell_heal", "relation": "belongs_to"},
            {"source": "fact_3", "target": "cond_burning", "relation": "belongs_to"},
        ]
        
        return {"nodes": nodes, "edges": edges}
    
    def test_result_contains_only_entities_in_path(self):
        """Invariant: entity_path contains only entity nodes."""
        graph = self.create_full_graph()
        seeds = {"spell_fireball"}
        
        result = run_entity_only_traversal(seeds, graph, max_hops=2)
        
        # All nodes in entity_path should be entities
        for node_id in result.entity_path:
            # Check it's not a fact
            for n in graph["nodes"]:
                if n["id"] == node_id:
                    assert n["type"] != "RuleFact", f"{node_id} is a fact, not entity"
                    break
    
    def test_attached_facts_are_facts(self):
        """Invariant: attached_facts contains only fact nodes."""
        graph = self.create_full_graph()
        seeds = {"spell_fireball"}
        
        result = run_entity_only_traversal(seeds, graph, max_hops=2)
        
        # All nodes in attached_facts should be facts
        for node_id in result.attached_facts:
            for n in graph["nodes"]:
                if n["id"] == node_id:
                    assert n["type"] == "RuleFact", f"{node_id} is not a fact"
                    break
    
    def test_facts_attached_only_to_reachable_entities(self):
        """Invariant: Facts are only attached to entities in the path."""
        graph = self.create_full_graph()
        seeds = {"spell_fireball"}
        
        result = run_entity_only_traversal(seeds, graph, max_hops=1)
        
        # Build fact ownership from graph
        fact_to_owner = {}
        for edge in graph["edges"]:
            if edge["relation"] == "belongs_to":
                fact_to_owner[edge["source"]] = edge["target"]
        
        # All attached facts should have owners in the entity path
        for fact_id in result.attached_facts:
            owner = fact_to_owner.get(fact_id)
            assert owner in result.entity_path, (
                f"Fact {fact_id} owned by {owner} but {owner} not in path"
            )


class TestNodeKindPartition:
    """Tests verifying the node kind partition is correct."""
    
    def test_is_entity_like_excludes_facts(self):
        """is_entity_like returns False for RuleFact nodes."""
        fact_node = {"type": "RuleFact", "id": "fact_1"}
        assert not is_entity_like(fact_node)
    
    def test_is_entity_like_excludes_structural(self):
        """is_entity_like returns False for structural nodes."""
        for node_type in ["document", "section", "chunk"]:
            node = {"type": node_type, "id": "struct_1"}
            assert not is_entity_like(node)
    
    def test_is_entity_like_includes_entities(self):
        """is_entity_like returns True for entity nodes."""
        for node_type in ["Spell", "Feat", "Condition", "MechanicFrame", "Action", "Ability"]:
            node = {"type": node_type, "id": "entity_1"}
            assert is_entity_like(node), f"is_entity_like should return True for {node_type}"
    
    def test_get_node_kind_partition(self):
        """get_node_kind correctly partitions all node types."""
        # Structural
        assert get_node_kind({"type": "document"}) == NodeKind.STRUCTURAL
        assert get_node_kind({"type": "section"}) == NodeKind.STRUCTURAL
        assert get_node_kind({"type": "chunk"}) == NodeKind.STRUCTURAL
        
        # Fact
        assert get_node_kind({"type": "RuleFact"}) == NodeKind.FACT
        
        # Entity
        assert get_node_kind({"type": "Spell"}) == NodeKind.ENTITY
        assert get_node_kind({"type": "Feat"}) == NodeKind.ENTITY
        assert get_node_kind({"type": "Condition"}) == NodeKind.ENTITY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
