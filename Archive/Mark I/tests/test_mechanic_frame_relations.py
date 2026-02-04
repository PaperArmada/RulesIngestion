from __future__ import annotations

from enrichment.graph_builder import (
    Graph,
    _add_mechanic_frame_relations,
    _apply_phase1_polish,
    _normalize_entity_key,
)
from enrichment.rule_facts import FactType, Modality, RuleFact


def _fact(
    fact_id: str,
    fact_type: FactType,
    clause_id: str,
    subject: str = "Vent Gas",
    obj: str | None = None,
) -> RuleFact:
    return RuleFact(
        fact_id=fact_id,
        fact_type=fact_type,
        subject=subject,
        subject_type="feat",
        predicate=fact_type.value,
        object=obj,
        object_type="spell" if obj else None,
        modality=Modality.MUST,
        condition=None,
        scope=None,
        clause_id=clause_id,
        mention_ids=[],
        evidence_span=(0, 10),
        confidence=1.0,
        extraction_method="pattern",
        is_complete=True,
    )


def test_requires_mechanic_links_frames() -> None:
    graph = Graph()
    graph.add_node("frame_vent", "MechanicFrame", {"name": "Vent Gas"})
    graph.add_node("frame_gust", "Spell", {"name": "Gust of Wind"})

    fact = _fact(
        "chunk_1::clause_0::fact_0",
        FactType.REQUIRES,
        "chunk_1::clause_0",
        obj="Gust of Wind",
    )

    added = _add_mechanic_frame_relations(
        graph=graph,
        facts=[fact],
        clause_mechanic_keys={
            fact.clause_id: {_normalize_entity_key("Gust of Wind")},
        },
        entity_name_by_id={
            "frame_vent": "Vent Gas",
            "frame_gust": "Gust of Wind",
        },
        entity_type_by_id={
            "frame_vent": "MechanicFrame",
            "frame_gust": "Spell",
        },
        fact_owner_by_id={fact.fact_id: "frame_vent"},
        fact_chunk_by_id={fact.fact_id: "chunk_1"},
        doc_id="doc_1",
    )

    assert added == 1
    assert any(
        edge.get("relation") == "requires_mechanic"
        and edge.get("source") == "frame_vent"
        and edge.get("target") == "frame_gust"
        for edge in graph.edges
    )


def test_reference_mechanic_from_mentions() -> None:
    graph = Graph()
    graph.add_node("frame_vent", "MechanicFrame", {"name": "Vent Gas"})
    graph.add_node("frame_gust", "Spell", {"name": "Gust of Wind"})

    fact = _fact(
        "chunk_2::clause_0::fact_0",
        FactType.GRANTS,
        "chunk_2::clause_0",
    )

    added = _add_mechanic_frame_relations(
        graph=graph,
        facts=[fact],
        clause_mechanic_keys={
            fact.clause_id: {_normalize_entity_key("Gust of Wind")},
        },
        entity_name_by_id={
            "frame_vent": "Vent Gas",
            "frame_gust": "Gust of Wind",
        },
        entity_type_by_id={
            "frame_vent": "MechanicFrame",
            "frame_gust": "Spell",
        },
        fact_owner_by_id={fact.fact_id: "frame_vent"},
        fact_chunk_by_id={fact.fact_id: "chunk_2"},
        doc_id="doc_1",
    )

    assert added == 1
    assert any(
        edge.get("relation") == "references_mechanic"
        and edge.get("source") == "frame_vent"
        and edge.get("target") == "frame_gust"
        for edge in graph.edges
    )


def test_phase1_polish_structural_behavioral_when_only_gates() -> None:
    graph = Graph()
    graph.add_node(
        "frame_gate",
        "MechanicFrame",
        {"name": "Level 6", "mechanic_kind": "behavioral"},
    )

    fact = _fact(
        "chunk_3::clause_0::fact_0",
        FactType.LEVEL_GATE,
        "chunk_3::clause_0",
        obj="6",
    )

    _apply_phase1_polish(
        graph=graph,
        facts=[fact],
        relations=[],
        fact_owner_by_id={fact.fact_id: "frame_gate"},
        entity_type_by_id={"frame_gate": "MechanicFrame"},
    )

    node = next(node for node in graph.nodes if node.get("id") == "frame_gate")
    assert node.get("mechanic_kind") == "structural_behavioral"
    assert node.get("retrieval_target") is False


def test_phase1_polish_retrieval_target_for_negative_override() -> None:
    graph = Graph()
    graph.add_node(
        "frame_override",
        "MechanicFrame",
        {"name": "Shield Block", "mechanic_kind": "behavioral"},
    )

    fact = _fact(
        "chunk_4::clause_0::fact_0",
        FactType.PREVENTS,
        "chunk_4::clause_0",
        obj="damage",
    )

    _apply_phase1_polish(
        graph=graph,
        facts=[fact],
        relations=[],
        fact_owner_by_id={fact.fact_id: "frame_override"},
        entity_type_by_id={"frame_override": "MechanicFrame"},
    )

    node = next(node for node in graph.nodes if node.get("id") == "frame_override")
    assert node.get("retrieval_target") is True
