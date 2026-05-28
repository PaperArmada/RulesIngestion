"""Tests for tinker.introspect.metadata."""

from __future__ import annotations

from tinker.introspect.metadata import build_metadata_index
from tinker.substrate import Unit


def _u(uid: str, text: str) -> Unit:
    return Unit(
        id=uid, text=text, page=0, structural_path=(), unit_type="prose", document_id="t"
    )


def test_extracts_classes_and_hd() -> None:
    units = [
        _u(
            "u1",
            "A Fighter at level 3 has HD: 3 and rolls 1d6+2 damage with a longsword.",
        ),
        _u("u2", "Cleric and Magic-User both gain spells. AC: 5 [14]."),
    ]
    out = build_metadata_index(units)
    by_unit = out["by_unit"]
    assert "Fighter" in by_unit["u1"]["classes"]
    assert "3" in by_unit["u1"]["hit_dice"]
    assert "1d6+2" in by_unit["u1"]["damage_dice"]
    assert "Cleric" in by_unit["u2"]["classes"]
    assert "Magic-User" in by_unit["u2"]["classes"]
    assert "5 [14]" in by_unit["u2"]["armor_class"]


def test_summary_counts() -> None:
    units = [
        _u("u1", "Cleric and Fighter discuss."),
        _u("u2", "Another Cleric speaks."),
    ]
    out = build_metadata_index(units)
    assert out["summary"]["classes"]["Cleric"] == 2
    assert out["summary"]["classes"]["Fighter"] == 1
    assert out["stats"]["total_units"] == 2
    assert out["stats"]["units_with_metadata"] == 2


def test_no_metadata_units_omitted() -> None:
    units = [_u("u1", "Pure prose with nothing extractable.")]
    out = build_metadata_index(units)
    assert "u1" not in out["by_unit"]
    assert out["stats"]["units_with_metadata"] == 0
