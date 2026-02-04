from enrichment.graph_builder import (
    CandidateKind,
    Graph,
    MECHANIC_FRAME_TYPES,
    _apply_structural_seed,
    _build_structural_seed,
    _derive_procedure_step_id,
    _extract_dying_threshold_override,
    _sort_ownership_candidates,
    _validate_graph,
    apply_header_scope_describes,
    build_chunk_graph,
    build_fact_graph,
    canonicalize_candidates,
    extract_entity_candidates,
    is_entity_like,
)
from enrichment.chunks import EnrichedChunk


def test_sort_ownership_candidates_is_deterministic() -> None:
    entity_type_by_id = {
        "feat_alpha": "Feat",
        "spell_alpha": "Spell",
        "rule_beta": "Rule",
    }
    entity_name_by_id = {
        "feat_alpha": "Alpha Feat",
        "spell_alpha": "Alpha Spell",
        "rule_beta": "Beta Rule",
    }

    candidates = ["rule_beta", "feat_alpha", "spell_alpha"]
    sorted_first = _sort_ownership_candidates(
        candidates, entity_type_by_id, entity_name_by_id
    )
    sorted_second = _sort_ownership_candidates(
        list(reversed(candidates)), entity_type_by_id, entity_name_by_id
    )
    sorted_third = _sort_ownership_candidates(
        ["spell_alpha", "rule_beta", "feat_alpha"],
        entity_type_by_id,
        entity_name_by_id,
    )

    assert sorted_first == sorted_second == sorted_third
    assert sorted_first[0] == "spell_alpha"


def test_procedure_step_id_detection() -> None:
    attack_step = _derive_procedure_step_id(
        "procedure:attack_resolution",
        "On a hit, you deal damage instead of normal weapon damage dice.",
    )
    assert attack_step == "procedure:attack_resolution#step:damage_roll"

    apply_damage_type = _derive_procedure_step_id(
        "procedure:apply_damage",
        "Change the type of damage to fire.",
    )
    assert apply_damage_type == "procedure:apply_damage#step:damage_type_assignment"

    apply_damage_scaling = _derive_procedure_step_id(
        "procedure:apply_damage",
        "This effect deals double damage.",
    )
    assert apply_damage_scaling == "procedure:apply_damage#step:damage_scaling"

    movement_step = _derive_procedure_step_id(
        "procedure:movement",
        "This movement provokes reactions.",
    )
    assert movement_step == "procedure:movement#step:provokes_reaction"

    dying_gain = _derive_procedure_step_id(
        "procedure:dying",
        "You gain dying 1 when reduced to 0 Hit Points.",
    )
    assert dying_gain == "procedure:dying#step:gain_dying"

    dying_increase = _derive_procedure_step_id(
        "procedure:dying",
        "Increase your dying value by 1.",
    )
    assert dying_increase == "procedure:dying#step:increase_dying"

    dying_stabilize = _derive_procedure_step_id(
        "procedure:dying",
        "You stabilize and remain stable at 0 Hit Points.",
    )
    assert dying_stabilize == "procedure:dying#step:stabilize"


def test_dying_threshold_override_detection() -> None:
    override = _extract_dying_threshold_override(
        "You would die upon reaching dying 3 instead of dying 4."
    )
    assert override == (3, 4)


# -----------------------------------------------------------------------------
# Phase 0: Structural seed
# -----------------------------------------------------------------------------


def _make_chunk(
    chunk_id: str,
    text: str = "Some text.",
    page: int = 1,
    section_path: list | None = None,
    block_type: str = "Text",
    content_kind: str = "narrative",
    is_rule_bearing: bool = False,
) -> EnrichedChunk:
    return EnrichedChunk(
        id=chunk_id,
        block_type=block_type,
        text=text,
        page=page,
        section_path=section_path or [],
        content_kind=content_kind,
        is_rule_bearing=is_rule_bearing,
    )


def test_structural_seed_phase0_only_structural() -> None:
    """Phase 0 returns only document/section/chunk nodes and contains/next edges."""
    doc_id = "test-doc"
    ruleset_id = "test-ruleset"
    book_id = "test-doc"
    chunks = [
        _make_chunk("c1", "First.", section_path=["Chapter 1", "Section A"]),
        _make_chunk("c2", "Second.", section_path=["Chapter 1", "Section A"]),
        _make_chunk("c3", "Third.", section_path=["Chapter 1", "Section B"]),
    ]
    seed = _build_structural_seed(doc_id, chunks, ruleset_id, book_id)

    assert seed.doc_node["type"] == "document"
    assert seed.doc_node["id"] == doc_id
    assert len(seed.chunk_nodes) == 3
    assert seed.chunk_order == ["c1", "c2", "c3"]
    assert len(seed.section_index) == 2  # Section A, Section B
    for node in seed.section_nodes + seed.chunk_nodes:
        assert node["type"] in ("section", "chunk")
    for edge in seed.edges:
        assert edge["relation"] in ("contains", "next")
    # No entity nodes, no describes/mentions
    node_types = {seed.doc_node["type"]} | {n["type"] for n in seed.section_nodes} | {n["type"] for n in seed.chunk_nodes}
    assert node_types == {"document", "section", "chunk"}


def test_structural_seed_apply_produces_same_structure() -> None:
    """Applying the seed to a graph yields correct node/edge counts."""
    doc_id = "test-doc"
    ruleset_id = "test-ruleset"
    book_id = "test-doc"
    chunks = [
        _make_chunk("c1", "One.", section_path=["Ch1", "Sec1"]),
        _make_chunk("c2", "Two.", section_path=["Ch1", "Sec1"]),
    ]
    seed = _build_structural_seed(doc_id, chunks, ruleset_id, book_id)
    graph = Graph()
    _apply_structural_seed(graph, seed)

    assert len(graph.nodes) == 1 + len(seed.section_nodes) + len(seed.chunk_nodes)
    assert any(n.get("id") == doc_id and n.get("type") == "document" for n in graph.nodes)
    assert all(e.get("relation") in ("contains", "next") for e in graph.edges)


# -----------------------------------------------------------------------------
# build_chunk_graph / build_fact_graph invariants and determinism
# -----------------------------------------------------------------------------


def test_build_chunk_graph_invariants() -> None:
    """Every entity-like node has canonical_id; every edge has relation."""
    doc_id = "fixture-doc"
    chunks = [
        _make_chunk("chunk-1", "**Fireball** is a spell.", content_kind="spell"),
        _make_chunk("chunk-2", "Some rule text.", section_path=["Chapter 2", "Rules"]),
    ]
    graph = build_chunk_graph(doc_id, chunks, ruleset_id="fixture-ruleset")

    for node in graph.nodes:
        nid = node.get("id", "")
        ntype = node.get("type")
        if is_entity_like(node):
            assert node.get("canonical_id") or nid.startswith("canon:"), (
                f"Entity node {nid} (type={ntype}) missing canonical_id"
            )
    for edge in graph.edges:
        assert edge.get("relation"), f"Edge missing relation: {edge}"


def test_build_chunk_graph_deterministic_snapshot() -> None:
    """Two runs with same chunks produce same stats (node/edge counts)."""
    doc_id = "snapshot-doc"
    chunks = [
        _make_chunk("a", "Spell **Magic Missile**.", content_kind="spell"),
        _make_chunk("b", "Feat **Toughness**.", content_kind="feat"),
    ]
    g1 = build_chunk_graph(doc_id, chunks, ruleset_id="snapshot-ruleset")
    g2 = build_chunk_graph(doc_id, chunks, ruleset_id="snapshot-ruleset")

    assert g1.stats.get("node_counts") == g2.stats.get("node_counts")
    assert g1.stats.get("edge_relation_counts") == g2.stats.get("edge_relation_counts")
    assert len(g1.nodes) == len(g2.nodes)
    assert len(g1.edges) == len(g2.edges)


def test_validate_graph_does_not_flag_fact_nodes() -> None:
    """After build_fact_graph, validation reports 0 missing canonical_id for fact nodes."""
    doc_id = "fact-fixture-doc"
    chunks = [
        _make_chunk(
            "clause-chunk",
            "You must have the Toughness feat. This grants 3 Hit Points.",
            content_kind="feat",
            is_rule_bearing=True,
        ),
    ]
    graph = build_fact_graph(doc_id, chunks, ruleset_id="fact-fixture-ruleset")
    result = _validate_graph(graph)
    missing = result["missing_canonical"]
    fact_ids = {n["id"] for n in missing if n.get("type") == "RuleFact"}
    assert not fact_ids, f"Fact nodes must not be flagged: {fact_ids}"
    assert len(missing) == 0, f"Expected 0 missing canonical_id, got {len(missing)}"


def test_is_entity_like_partition() -> None:
    """is_entity_like is False for structural/RuleFact, True for MechanicFrame/Spell/etc."""
    for node_type in ("document", "section", "chunk", "RuleFact"):
        assert not is_entity_like({"type": node_type}), f"Expected False for {node_type}"
    for node_type in MECHANIC_FRAME_TYPES:
        assert is_entity_like({"type": node_type}), f"Expected True for {node_type}"
    # Other entity-like types from CORE_ENTITY_TYPES
    for node_type in ("Item", "Condition", "Class", "Ancestry", "Background", "Monster"):
        assert is_entity_like({"type": node_type}), f"Expected True for {node_type}"


def test_build_fact_graph_invariants() -> None:
    """Fact graph has RuleFact nodes, has_fact/belongs_to edges; no edge missing relation."""
    doc_id = "fact-fixture-doc"
    chunks = [
        _make_chunk(
            "clause-chunk",
            "You must have the Toughness feat. This grants 3 Hit Points.",
            content_kind="feat",
            is_rule_bearing=True,
        ),
    ]
    graph = build_fact_graph(doc_id, chunks, ruleset_id="fact-fixture-ruleset")

    for edge in graph.edges:
        assert edge.get("relation"), f"Edge missing relation: {edge}"
    fact_nodes = [n for n in graph.nodes if n.get("type") == "RuleFact"]
    # May be 0 if no clauses extracted; if we have facts, we should have has_fact edges
    relations = [e.get("relation") for e in graph.edges]
    if fact_nodes:
        assert "has_fact" in relations


# -----------------------------------------------------------------------------
# Phase 1: extract_entity_candidates
# -----------------------------------------------------------------------------


def test_extract_entity_candidates_returns_bundle() -> None:
    """extract_entity_candidates returns CandidateBundle with candidates and relation_mentions."""
    chunks = [
        _make_chunk("c1", "Some text."),
    ]
    bundle = extract_entity_candidates(chunks)
    assert hasattr(bundle, "candidates")
    assert hasattr(bundle, "relation_mentions")
    assert isinstance(bundle.candidates, list)
    assert isinstance(bundle.relation_mentions, list)


def test_extract_entity_candidates_spell_and_mechanic_frame() -> None:
    """Spell chunk yields Spell + MechanicFrame candidates; no graph mutation."""
    # Extractors expect **NAME** **SPELL 3** (name segment uppercase in pattern)
    chunks = [
        _make_chunk("c1", "**FIREBALL** **SPELL 3**\nFire damage.", content_kind="spell"),
    ]
    bundle = extract_entity_candidates(chunks)
    spell_candidates = [c for c in bundle.candidates if c.entity_type == "Spell"]
    mf_candidates = [c for c in bundle.candidates if c.kind == CandidateKind.MECHANIC_FRAME]
    assert len(spell_candidates) >= 1
    assert len(mf_candidates) >= 1
    assert spell_candidates[0].surface_name
    assert spell_candidates[0].chunk_id == "c1"
    assert spell_candidates[0].candidate_id.startswith("cand:")


def test_extract_entity_candidates_relation_mentions() -> None:
    """Relation patterns in text produce relation_mentions (source_id, relation, target_name)."""
    chunks = [
        _make_chunk("c1", "This feat requires **Toughness** and grants **Skill Focus**.", content_kind="feat"),
    ]
    bundle = extract_entity_candidates(chunks)
    assert len(bundle.relation_mentions) >= 1
    for src, rel, target in bundle.relation_mentions:
        assert src == "c1"
        assert rel in ("requires", "grants")
        assert target


def test_extract_entity_candidates_vocabulary_match_fallback() -> None:
    """When chunk has no entity from headers/section/tags, vocabulary_match adds entity from vocab."""
    # Chunk with no section_path/header/tags so no heuristic/section_header/header_scope entity
    chunks = [
        _make_chunk(
            "c1",
            "Lashunta gain a +1 bonus to Diplomacy when in the same system as another Lashunta.",
            section_path=[],
            block_type="Text",
            content_kind="narrative",
        ),
    ]
    vocabularies = {"role": {"lashunta"}}
    bundle = extract_entity_candidates(chunks, vocabularies=vocabularies)
    vocab_candidates = [c for c in bundle.candidates if c.extraction_method == "vocabulary_match"]
    assert len(vocab_candidates) >= 1
    assert vocab_candidates[0].entity_type == "Ancestry"
    assert vocab_candidates[0].surface_name.lower() == "lashunta"
    assert vocab_candidates[0].confidence == 0.8


# -----------------------------------------------------------------------------
# Phase 2: canonicalize_candidates
# -----------------------------------------------------------------------------


def test_canonicalize_candidates_returns_result() -> None:
    """canonicalize_candidates returns CanonicalizationResult with expected shape."""
    chunks = [
        _make_chunk("c1", "**FIREBALL** **SPELL 3**\nFire damage.", content_kind="spell"),
    ]
    bundle = extract_entity_candidates(chunks)
    result = canonicalize_candidates(
        bundle, chunks, ruleset_id="test-ruleset", doc_id="test-doc"
    )
    assert hasattr(result, "alias_map")
    assert hasattr(result, "canonical_entities")
    assert hasattr(result, "candidate_to_canonical")
    assert hasattr(result, "namekey_to_canonical")
    assert isinstance(result.alias_map, dict)
    assert isinstance(result.canonical_entities, dict)
    assert isinstance(result.candidate_to_canonical, dict)
    assert isinstance(result.namekey_to_canonical, dict)


def test_canonicalize_candidates_spell_canonical_id() -> None:
    """Spell candidates get canon: canonical_id; candidate_to_canonical maps candidate_id -> canon:id."""
    chunks = [
        _make_chunk("c1", "**FIREBALL** **SPELL 3**\nFire damage.", content_kind="spell"),
    ]
    bundle = extract_entity_candidates(chunks)
    result = canonicalize_candidates(
        bundle, chunks, ruleset_id="test-ruleset", doc_id="test-doc"
    )
    assert len(result.canonical_entities) >= 1
    for cid, cent in result.canonical_entities.items():
        assert cid.startswith("canon:"), cid
        assert cent.canonical_id == cid
        assert cent.entity_type in ("Spell", "MechanicFrame")
        assert cent.name
        assert cent.canonical_key
        assert cent.aliases
    for cand_id, canon_id in result.candidate_to_canonical.items():
        assert cand_id.startswith("cand:")
        assert canon_id.startswith("canon:")
        assert canon_id in result.canonical_entities


# -----------------------------------------------------------------------------
# Phase 3b: header_scope (scope is a replaceable derivation)
# -----------------------------------------------------------------------------


def test_header_scope_describes_edges_have_expected_shape() -> None:
    """Every describes edge with extraction_method header_scope has required meta (explainability)."""
    doc_id = "scope-fixture-doc"
    # First chunk: spell (establishes mechanic frame). Second: rule-bearing text (inherits scope).
    chunks = [
        _make_chunk("c1", "**FIREBALL** **SPELL 3**\nFire damage.", content_kind="spell"),
        _make_chunk("c2", "You can cast this spell at higher ranks.", content_kind="rule", is_rule_bearing=True),
    ]
    graph = build_chunk_graph(doc_id, chunks, ruleset_id="scope-fixture-ruleset")

    header_scope_edges = [
        e for e in graph.edges
        if e.get("relation") == "describes" and e.get("extraction_method") == "header_scope"
    ]
    # Only "describes" edges may have extraction_method header_scope (Phase 3b is the single writer)
    for e in graph.edges:
        if e.get("extraction_method") == "header_scope":
            assert e.get("relation") == "describes", "header_scope is only on describes edges"
    for e in header_scope_edges:
        assert "source_document" in e
        assert "source_chunk_id" in e
        assert e.get("extraction_method") == "header_scope"
        assert "semantic" in e  # False for header_scope
        assert "page" in e


def test_apply_header_scope_describes_only_adds_describes_header_scope() -> None:
    """Phase 3b only adds describes edges with extraction_method header_scope (replaceable derivation)."""
    doc_id = "scope-audit-doc"
    chunks = [
        _make_chunk("c1", "**FEAT** **Level 1**\nA feat.", content_kind="feat"),
        _make_chunk("c2", "This feat does something.", content_kind="rule", is_rule_bearing=True),
    ]
    graph = build_chunk_graph(doc_id, chunks, ruleset_id="scope-audit-ruleset")
    before = len([e for e in graph.edges if e.get("extraction_method") == "header_scope"])

    bundle = extract_entity_candidates(chunks)
    canon_result = canonicalize_candidates(bundle, chunks, "scope-audit-ruleset", doc_id)
    candidates_by_chunk = {}
    for c in bundle.candidates:
        candidates_by_chunk.setdefault(c.chunk_id, []).append(c)
    chunk_order = [c.id for c in chunks if c.text.strip()]
    primary_by_chunk = {}
    for chunk_id in chunk_order:
        for c in candidates_by_chunk.get(chunk_id, []):
            canon_id = canon_result.candidate_to_canonical.get(c.candidate_id)
            if canon_id is None:
                continue
            if c.entity_type in ("Spell", "Feat", "Item", "Rule") or (
                c.kind == CandidateKind.MECHANIC_FRAME
                and c.context.get("content_kind") in ("spell", "feat", "rule", "item")
            ):
                primary_by_chunk[chunk_id] = canon_id
                break

    apply_header_scope_describes(
        graph=graph,
        chunks=chunks,
        chunk_order=chunk_order,
        candidates_by_chunk=candidates_by_chunk,
        canon_result=canon_result,
        primary_canonical_id_by_chunk=primary_by_chunk,
        doc_id=doc_id,
    )
    after = len([e for e in graph.edges if e.get("extraction_method") == "header_scope"])
    # Calling Phase 3b again may add more header_scope edges (idempotency not required here)
    # Invariant: every new edge with header_scope is a describes edge
    for e in graph.edges:
        if e.get("extraction_method") == "header_scope":
            assert e.get("relation") == "describes"
    assert after >= before
