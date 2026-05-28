"""Tests for tinker.introspect.crossref."""

from __future__ import annotations

from tinker.introspect.crossref import build_crossref_graph
from tinker.substrate import Unit


def _u(uid: str, text: str) -> Unit:
    return Unit(
        id=uid, text=text, page=0, structural_path=(), unit_type="prose", document_id="t"
    )


def test_edge_from_mention_to_defining_unit() -> None:
    units = [
        _u("def-cleric", "**Cleric:** A divine spellcaster."),
        _u("usage", "The Cleric class gets two spells per day at level 1."),
    ]
    glossary = [
        {"term": "Cleric", "definition": "...", "source_unit_id": "def-cleric"},
    ]
    g = build_crossref_graph(units, glossary)
    assert g["stats"]["edges"] == 1
    edge = g["edges"][0]
    assert edge["source_unit_id"] == "usage"
    assert edge["target_term"] == "Cleric"
    assert edge["target_unit_id"] == "def-cleric"


def test_self_reference_skipped() -> None:
    units = [_u("u1", "**Cleric:** A divine spellcaster. The Cleric heals allies.")]
    glossary = [
        {"term": "Cleric", "definition": "...", "source_unit_id": "u1"},
    ]
    g = build_crossref_graph(units, glossary)
    assert g["stats"]["edges"] == 0


def test_long_term_wins_over_short() -> None:
    # Both "Magic" and "Magic-User" are glossary terms. The text contains
    # "Magic-User"; the longer term should win the match.
    units = [_u("u1", "A Magic-User casts spells.")]
    glossary = [
        {"term": "Magic-User", "definition": "...", "source_unit_id": "def-mu"},
        {"term": "Magic", "definition": "...", "source_unit_id": "def-magic"},
    ]
    g = build_crossref_graph(units, glossary)
    targets = [e["target_term"] for e in g["edges"]]
    assert "Magic-User" in targets
    assert "Magic" not in targets


def test_dedup_per_source_target_pair() -> None:
    units = [_u("u1", "Cleric Cleric Cleric — many mentions of Cleric.")]
    glossary = [{"term": "Cleric", "definition": "...", "source_unit_id": "def-c"}]
    g = build_crossref_graph(units, glossary)
    assert g["stats"]["edges"] == 1


def test_empty_glossary_returns_empty_graph() -> None:
    units = [_u("u1", "Anything goes here.")]
    g = build_crossref_graph(units, [])
    assert g["stats"]["edges"] == 0
    assert g["edges"] == []
