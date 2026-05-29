"""End-to-end smoke test for tinker.introspect.build.build_self_portrait.

Constructs a small in-memory substrate via monkeypatching `load_corpus`,
then runs the orchestrator with use_llm=False and asserts the output
shape matches the contract documented in build.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from tinker.introspect import build as build_mod
from tinker.substrate import Unit


def _u(uid: str, text: str, *, path: tuple[str, ...] = (), kind: str = "prose") -> Unit:
    return Unit(
        id=uid,
        text=text,
        page=int(uid[1:]) if uid[1:].isdigit() else 0,
        structural_path=path,
        unit_type=kind,
        document_id="test",
    )


def test_build_self_portrait_writes_full_document(tmp_path: Path, monkeypatch) -> None:
    units = [
        _u("u01", "**Cleric:** A divine spellcasting class with healing focus."),
        _u("u02", "**Fighter:** Martial class with high HD and combat skill."),
        _u("u03", "**Magic-User:** Arcane spellcasting class with low HP."),
        _u("u04", "**Thief:** Stealth class with backstab and lockpicking."),
        _u("u05", "**HD:** 3   **AC:** 5 [14]   **Damage:** 1d6   **Special:** Poison"),
        _u("u06", "**HD:** 5   **AC:** 6 [13]   **Damage:** 2d6   **Special:** Spells"),
        _u("u07", "A long descriptive paragraph about the world of Faerun and "
                 "its many magical lands, with no labels or stat-blocky markers."),
        _u("u08", "Another descriptive paragraph about gameplay style and tone, "
                 "discussing the Referee role and immersive storytelling."),
        _u("u09", "**Class Restrictions:** Only the Cleric class may cast cure spells."),
        _u("u10", "Saving Throw: 14 vs petrification. Hit Points (HP) are restored."),
    ]

    def fake_load_corpus(substrate_dir, document_id, **kw):
        return units

    monkeypatch.setattr(build_mod, "load_corpus", fake_load_corpus)

    out_path = tmp_path / "portrait.json"
    portrait = build_mod.build_self_portrait(
        substrate_dir=tmp_path / "ignored",
        document_id="test",
        out_path=out_path,
        cache_path=tmp_path / "cache.sqlite",
        corpus_id="test",
        use_llm=False,
        cluster_k_range=(2, 4),
        progress=False,
    )

    assert out_path.is_file()
    loaded = json.loads(out_path.read_text())
    # Same top-level shape; deep equality fails on JSON int-key coercion of
    # the inertias dict, so we check structural keys instead.
    assert set(loaded.keys()) == set(portrait.keys())
    assert loaded["substrate_summary"] == portrait["substrate_summary"]
    assert loaded["glossary"]["stats"] == portrait["glossary"]["stats"]

    # Required top-level keys.
    for key in ("corpus_id", "document_id", "generated_at",
                "substrate_summary", "glossary", "clusters",
                "metadata_index", "crossref"):
        assert key in portrait, f"missing key {key}"

    # Substrate summary records recipe used.
    assert portrait["substrate_summary"]["unit_count"] == 10
    assert "recipe" in portrait["substrate_summary"]

    # Glossary picked up the bold-colon class names.
    terms = {t["term"] for t in portrait["glossary"]["terms"]}
    assert {"Cleric", "Fighter", "Magic-User", "Thief"} <= terms

    # Acronyms saw HP.
    acros = {a["acronym"] for a in portrait["glossary"]["acronyms"]}
    assert "HP" in acros

    # Clusters were emitted; total membership equals input size.
    cluster_total = sum(c["size"] for c in portrait["clusters"]["clusters"])
    assert cluster_total == 10

    # Metadata index picked up classes and stat-block features.
    summary = portrait["metadata_index"]["summary"]
    assert summary["classes"].get("Cleric", 0) >= 2

    # Cross-references: u09 mentions "Cleric" (defined in u01) → at least
    # one edge with target_term "Cleric".
    edges = portrait["crossref"]["edges"]
    cleric_edges = [e for e in edges if e["target_term"] == "Cleric"]
    assert len(cleric_edges) >= 1
