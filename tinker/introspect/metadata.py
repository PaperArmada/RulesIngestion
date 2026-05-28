"""Opportunistic typed-metadata extraction from EvidenceUnits.

Walks units and extracts attribute hits via regex (no LLM). Output is a
per-unit attribute index and a top-level summary of attribute distributions.

The attributes targeted here are tuned to OSR D&D-style rulebooks (SWCR):
class names, spell level, hit dice, armor class, damage dice, alignment.
Generalizes adequately to other systems for v0 but is not designed to be
exhaustive.
"""

from __future__ import annotations

import collections
import re
from typing import Any

from tinker.substrate import Unit


_CLASSES = (
    "Fighter",
    "Cleric",
    "Magic-User",
    "Thief",
    "Assassin",
    "Druid",
    "Monk",
    "Paladin",
    "Ranger",
    "Bard",
    "Wizard",
    "Sorcerer",
)

_ALIGNMENTS = ("Lawful", "Neutral", "Chaotic", "Good", "Evil")

# spell level: "1st-level", "2nd-level", "third-level", "level 1 spell"
_RE_SPELL_LEVEL = re.compile(
    r"\b(\d)(?:st|nd|rd|th)[- ]level\b|\blevel\s+(\d)\s+spell\b",
    re.IGNORECASE,
)
# Hit Dice e.g. "HD: 3" or "Hit Dice: 3+1"
_RE_HD = re.compile(
    r"\b(?:HD|Hit Dice)\s*[:.]?\s*(\d+(?:\s*\+\s*\d+)?)",
    re.IGNORECASE,
)
# AC e.g. "AC: 5" or "Armor Class: 6 [13]"
_RE_AC = re.compile(
    r"\b(?:AC|Armor Class)\s*[:.]?\s*(\d+(?:\s*\[\s*\d+\s*\])?)",
    re.IGNORECASE,
)
# Damage dice e.g. "1d6", "2d8+1", "1d4+2"
_RE_DAMAGE = re.compile(r"\b(\d*d\d+(?:\s*[+\-]\s*\d+)?)", re.IGNORECASE)
# Save categories e.g. "Saving Throw: 14"
_RE_SAVE = re.compile(r"\bSaving Throw\b\s*[:.]?\s*(\d+)", re.IGNORECASE)


def _hits(rex: re.Pattern[str], text: str) -> list[str]:
    out: list[str] = []
    for m in rex.finditer(text):
        try:
            captures = [g for g in m.groups() if g]
            if captures:
                out.append(captures[0].strip())
        except IndexError:
            continue
    return out


def _classes_mentioned(text: str) -> list[str]:
    out = []
    for c in _CLASSES:
        # word boundary or 's' suffix
        if re.search(rf"\b{re.escape(c)}s?\b", text):
            out.append(c)
    return out


def _alignment_mentioned(text: str) -> list[str]:
    return [a for a in _ALIGNMENTS if re.search(rf"\b{a}\b", text)]


def build_metadata_index(units: list[Unit]) -> dict[str, Any]:
    """Per-unit metadata index + corpus-level summary.

    Returns
    -------
    {
      "by_unit": { unit_id: { "classes": [...], "spell_levels": [...],
                              "hit_dice": [...], "armor_class": [...],
                              "damage_dice": [...], "saving_throws": [...],
                              "alignment": [...] } },
      "summary": { attribute_name: Counter-like dict of value -> count },
    }
    """
    by_unit: dict[str, dict[str, Any]] = {}
    summary: dict[str, collections.Counter] = {
        "classes": collections.Counter(),
        "spell_levels": collections.Counter(),
        "hit_dice": collections.Counter(),
        "armor_class": collections.Counter(),
        "damage_dice": collections.Counter(),
        "saving_throws": collections.Counter(),
        "alignment": collections.Counter(),
    }

    for u in units:
        text = u.text
        classes = _classes_mentioned(text)
        spell_levels = _hits(_RE_SPELL_LEVEL, text)
        hd = _hits(_RE_HD, text)
        ac = _hits(_RE_AC, text)
        damage = _hits(_RE_DAMAGE, text)
        saves = _hits(_RE_SAVE, text)
        align = _alignment_mentioned(text)

        attrs: dict[str, list[str]] = {}
        if classes:
            attrs["classes"] = classes
            for c in classes:
                summary["classes"][c] += 1
        if spell_levels:
            attrs["spell_levels"] = spell_levels
            for s in spell_levels:
                summary["spell_levels"][s] += 1
        if hd:
            attrs["hit_dice"] = hd
            for v in hd:
                summary["hit_dice"][v] += 1
        if ac:
            attrs["armor_class"] = ac
            for v in ac:
                summary["armor_class"][v] += 1
        if damage:
            attrs["damage_dice"] = damage
            for v in damage:
                summary["damage_dice"][v] += 1
        if saves:
            attrs["saving_throws"] = saves
            for v in saves:
                summary["saving_throws"][v] += 1
        if align:
            attrs["alignment"] = align
            for v in align:
                summary["alignment"][v] += 1

        if attrs:
            by_unit[u.id] = attrs

    return {
        "by_unit": by_unit,
        "summary": {k: dict(v.most_common(20)) for k, v in summary.items()},
        "stats": {
            "total_units": len(units),
            "units_with_metadata": len(by_unit),
        },
    }
