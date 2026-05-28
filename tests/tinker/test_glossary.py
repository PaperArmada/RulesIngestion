"""Tests for tinker.introspect.glossary."""

from __future__ import annotations

from pathlib import Path

import pytest

from tinker.cache import TinkerCache
from tinker.introspect.glossary import (
    _extract_acronyms_regex,
    _extract_terms_regex,
    build_glossary,
)
from tinker.substrate import Unit


def _u(uid: str, text: str, path: tuple[str, ...] = ()) -> Unit:
    return Unit(
        id=uid,
        text=text,
        page=0,
        structural_path=path,
        unit_type="prose",
        document_id="test",
    )


def test_regex_bold_colon_term() -> None:
    units = [
        _u("u1", "**Poison:** Assassins use poison on weapons to inflict damage."),
        _u("u2", "**Trap Sense:** Thieves have keen senses for noticing traps."),
    ]
    out = _extract_terms_regex(units)
    assert {t["term"] for t in out} == {"Poison", "Trap Sense"}
    assert all(t["source"] == "regex" for t in out)


def test_regex_bold_trailing_colon() -> None:
    units = [_u("u1", "**Fireball**: a third-level magic-user spell.")]
    out = _extract_terms_regex(units)
    assert any(t["term"] == "Fireball" for t in out)


def test_regex_dedups_terms_case_insensitive() -> None:
    units = [
        _u("u1", "**Poison:** definition one of length over twenty chars."),
        _u("u2", "**poison:** definition two of length over twenty chars."),
    ]
    out = _extract_terms_regex(units)
    assert len([t for t in out if t["term"].lower() == "poison"]) == 1


def test_regex_rejects_short_uppercase_garbage() -> None:
    units = [
        _u(
            "u1",
            "**ZZ:** this matches the colon pattern but ZZ is all-caps short.",
        )
    ]
    out = _extract_terms_regex(units)
    assert not any(t["term"] == "ZZ" for t in out)


def test_acronym_trailing_pattern() -> None:
    # The "PHRASE (ACRO)" pattern intentionally requires title-cased phrase
    # (each word capitalized), matching how rulebooks introduce acronyms.
    units = [_u("u1", "Hit Points (HP) are tracked per character.")]
    out = _extract_acronyms_regex(units)
    assert any(a["acronym"] == "HP" for a in out)


def test_acronym_leading_pattern() -> None:
    units = [_u("u1", "Use AC (Armor Class) as the defense stat.")]
    out = _extract_acronyms_regex(units)
    assert any(a["acronym"] == "AC" for a in out)


def test_build_glossary_without_llm(tmp_path: Path) -> None:
    units = [
        _u("u1", "**Cleric:** divine spellcasting class with healing focus."),
        _u("u2", "**Fighter:** martial class with high HD and combat skill."),
        _u("u3", "Game Master (GM) controls the world and NPCs."),
    ]
    cache = TinkerCache(tmp_path / "c.sqlite")
    out = build_glossary(units, cache, use_llm=False)
    terms = {t["term"] for t in out["terms"]}
    assert "Cleric" in terms
    assert "Fighter" in terms
    acros = {a["acronym"] for a in out["acronyms"]}
    assert "GM" in acros
    # No LLM calls when use_llm=False
    assert out["stats"]["llm_calls_attempted"] == 0
    assert out["stats"]["llm_terms"] == 0


def test_build_glossary_llm_path_uses_cache(tmp_path: Path, monkeypatch) -> None:
    # Build a unit that won't match the regex but has a term-like leaf heading.
    units = [
        _u(
            "u1",
            "Once per day a Bard can charm an audience of NPCs into helping.",
            path=("Bard Abilities", "Charm Audience"),
        ),
    ]
    cache = TinkerCache(tmp_path / "c.sqlite")
    fake_response = {
        "terms": [
            {
                "term": "Charm Audience",
                "definition": "Bard ability to charm onlookers once per day.",
            }
        ],
        "acronyms": [],
    }

    calls = {"n": 0}

    def fake_extract(text: str, *, think: bool | None = None) -> dict:
        calls["n"] += 1
        return fake_response

    monkeypatch.setattr(
        "tinker.introspect.glossary.tinker_llm.extract_glossary", fake_extract
    )
    out1 = build_glossary(units, cache, use_llm=True, llm_max_units=10)
    out2 = build_glossary(units, cache, use_llm=True, llm_max_units=10)

    assert any(t["term"] == "Charm Audience" for t in out1["terms"])
    assert any(t["term"] == "Charm Audience" for t in out2["terms"])
    # Second build should be a cache hit; only one LLM call.
    assert calls["n"] == 1


def test_build_glossary_llm_skips_already_seen_terms(tmp_path: Path, monkeypatch) -> None:
    units = [
        _u(
            "u1",
            "**Poison:** Assassins use poison on weapons (matches regex).",
            path=("Assassin", "Poison"),
        ),
    ]
    cache = TinkerCache(tmp_path / "c.sqlite")
    calls = {"n": 0}

    def fake_extract(text: str, *, think: bool | None = None) -> dict:
        calls["n"] += 1
        return {"terms": [], "acronyms": []}

    monkeypatch.setattr(
        "tinker.introspect.glossary.tinker_llm.extract_glossary", fake_extract
    )
    build_glossary(units, cache, use_llm=True, llm_max_units=10)
    # "Poison" already matched by regex → not sent to LLM.
    assert calls["n"] == 0
