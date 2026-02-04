from __future__ import annotations

from enrichment.chunks import EnrichedChunk
from enrichment.fact_relations import RelationType, generate_fact_relations
from enrichment.rule_facts import FactType, Modality, RuleFact


def _fact(
    fact_id: str,
    fact_type: FactType,
    clause_id: str,
    subject: str = "test-subject",
    scope: str | None = None,
) -> RuleFact:
    return RuleFact(
        fact_id=fact_id,
        fact_type=fact_type,
        subject=subject,
        subject_type="rule",
        predicate=fact_type.value,
        object="test-object",
        object_type="rule",
        modality=Modality.CONDITIONAL,
        condition=None,
        scope=scope,
        clause_id=clause_id,
        mention_ids=[],
        evidence_span=(0, 10),
        confidence=1.0,
        extraction_method="pattern",
        is_complete=True,
    )


def test_success_failure_relations() -> None:
    chunk = EnrichedChunk(
        id="chunk_1",
        block_type="Text",
        text="Success: hit. Failure: miss.",
        page=1,
        section_path=["Combat", "Strikes"],
    )

    facts = [
        _fact("chunk_1::clause_0::fact_0", FactType.ON_SUCCESS, "chunk_1::clause_0"),
        _fact("chunk_1::clause_0::fact_1", FactType.ON_FAILURE, "chunk_1::clause_0"),
    ]

    relations = generate_fact_relations(facts, [chunk])
    relation_types = {(r.relation_type, r.source_fact_id, r.target_fact_id) for r in relations}

    assert (RelationType.HAS_FAILURE_MODE, facts[0].fact_id, facts[1].fact_id) in relation_types
    assert (RelationType.CONTRASTS_WITH, facts[0].fact_id, facts[1].fact_id) in relation_types
    assert (RelationType.CONTRASTS_WITH, facts[1].fact_id, facts[0].fact_id) in relation_types


def test_level_and_role_relations() -> None:
    chunk_a = EnrichedChunk(
        id="chunk_a",
        block_type="Text",
        text="At 5th level, you gain a bonus.",
        page=10,
        section_path=["Ancestries", "Lashunta"],
    )
    chunk_b = EnrichedChunk(
        id="chunk_b",
        block_type="Text",
        text="Lashunta feat applies here.",
        page=55,
        section_path=["Feats", "General"],
    )

    facts = [
        _fact(
            "chunk_a::clause_0::fact_0",
            FactType.GRANTS,
            "chunk_a::clause_0",
            scope="level:5; role:lashunta",
        ),
        _fact(
            "chunk_a::clause_0::fact_1",
            FactType.LEVEL_GATE,
            "chunk_a::clause_0",
            scope="level:5",
        ),
        _fact(
            "chunk_b::clause_0::fact_0",
            FactType.GRANTS,
            "chunk_b::clause_0",
            scope="role:lashunta",
        ),
    ]

    relations = generate_fact_relations(facts, [chunk_a, chunk_b], allow_cross_section=True)
    relation_types = {(r.relation_type, r.source_fact_id, r.target_fact_id) for r in relations}

    assert (RelationType.REQUIRES_LEVEL, facts[0].fact_id, facts[1].fact_id) in relation_types
    assert (
        RelationType.APPLIES_TO_ROLE,
        facts[0].fact_id,
        facts[2].fact_id,
    ) in relation_types


def test_same_mechanic_frame_relations() -> None:
    chunk = EnrichedChunk(
        id="chunk_c",
        block_type="Text",
        text="Feat effects.",
        page=2,
        section_path=["Feats", "Covering Fire"],
    )

    facts = [
        _fact("chunk_c::clause_0::fact_0", FactType.GRANTS, "chunk_c::clause_0"),
        _fact("chunk_c::clause_1::fact_0", FactType.FREQUENCY, "chunk_c::clause_1"),
    ]

    relations = generate_fact_relations(
        facts,
        [chunk],
        fact_owner_by_id={
            facts[0].fact_id: "frame_covering_fire",
            facts[1].fact_id: "frame_covering_fire",
        },
    )
    relation_types = {(r.relation_type, r.source_fact_id, r.target_fact_id) for r in relations}

    assert (
        RelationType.SAME_MECHANIC_FRAME,
        facts[0].fact_id,
        facts[1].fact_id,
    ) in relation_types


def test_requires_level_supports_relations() -> None:
    chunk = EnrichedChunk(
        id="chunk_d",
        block_type="Text",
        text="Level gates in two frames.",
        page=3,
        section_path=["Feats", "Level 5"],
    )

    level_fact = _fact(
        "chunk_d::clause_0::fact_0",
        FactType.LEVEL_GATE,
        "chunk_d::clause_0",
        scope="level:5",
    )
    target_fact = _fact(
        "chunk_d::clause_1::fact_0",
        FactType.GRANTS,
        "chunk_d::clause_1",
        scope="level:5",
    )

    relations = generate_fact_relations(
        [level_fact, target_fact],
        [chunk],
        fact_owner_by_id={
            level_fact.fact_id: "frame_level_gate",
            target_fact.fact_id: "frame_target",
        },
    )
    relation_types = {(r.relation_type, r.source_fact_id, r.target_fact_id) for r in relations}

    assert (
        RelationType.REQUIRES_LEVEL_SUPPORTS,
        level_fact.fact_id,
        target_fact.fact_id,
    ) in relation_types


def test_replaces_effect_relations() -> None:
    chunk = EnrichedChunk(
        id="chunk_e",
        block_type="Text",
        text="Instead of recovery checks, you regain 1 HP.",
        page=4,
        section_path=["Ancestries", "Android"],
    )

    override_fact = _fact(
        "chunk_e::clause_0::fact_0",
        FactType.INSTEAD_OF,
        "chunk_e::clause_0",
    )
    override_fact.override_target = "recovery checks"
    target_fact = _fact(
        "chunk_e::clause_1::fact_0",
        FactType.GRANTS,
        "chunk_e::clause_1",
    )

    relations = generate_fact_relations(
        [override_fact, target_fact],
        [chunk],
        fact_owner_by_id={
            override_fact.fact_id: "frame_revivification",
            target_fact.fact_id: "frame_recovery_checks",
        },
        owner_name_by_id={
            "frame_revivification": "Revivification Protocol",
            "frame_recovery_checks": "Recovery Checks",
        },
        allow_cross_section=True,
    )
    relation_types = {(r.relation_type, r.source_fact_id, r.target_fact_id) for r in relations}

    assert (
        RelationType.REPLACES_EFFECT,
        override_fact.fact_id,
        target_fact.fact_id,
    ) in relation_types
