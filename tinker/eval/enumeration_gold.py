"""Enumeration gold: NL queries with canonical metadata predicates.

The gold set for an enumeration query is the set of unit_ids that match the
*intended* predicate applied to `metadata_index.by_unit`. The metadata is the
ground truth for "all 3rd-level spells"; this gold therefore tests the
enumeration route's NL->predicate parsing + execution, NOT the metadata
extraction itself (that was M1). See MILESTONE-M7 §6 (gold circularity).

All by_unit fields are per-unit *lists*, so a clause matches when the unit's
list for that field intersects the clause's accepted values. Multiple clauses
are AND-combined. `damage_dice` is normalized (`d6` == `1d6`) because the M1
miner stored it inconsistently.

Queries deliberately span:
  - small sets (alignment, ~10-14) and large sets (Druid 87, spell L3 31),
    all far above any reasonable top-K, which is the structural point;
  - single-dimension and compound (class AND spell_level) predicates;
  - the clean dimensions (spell_levels, classes, alignment) plus a couple of
    normalized damage_dice. Messy dimensions (armor_class, hit_dice) are
    deferred per the milestone spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Clause:
    """One predicate clause.

    op="any_of": the unit's list for `field` must intersect `any_of`.
    op="exists":  the unit must carry a non-empty `field` (value ignored).
                  Used to force "is actually a spell" (spell_levels exists)
                  or "is a stat block" (armor_class exists), so a token-mention
                  class/damage tag doesn't pull in prose/table units.
    """
    field: str
    any_of: tuple[str, ...] = ()
    op: str = "any_of"


@dataclass(frozen=True)
class EnumQuery:
    id: str
    question: str
    clauses: tuple[Clause, ...]
    note: str = ""


def _normalize_damage(v: str) -> str:
    """Canonicalize damage-dice notation: 'd6' -> '1d6', strip spaces/case."""
    s = str(v).strip().lower().replace(" ", "")
    if s.startswith("d"):
        s = "1" + s
    return s


def _match_value(field_name: str, stored: str, wanted: str) -> bool:
    if field_name == "damage_dice":
        return _normalize_damage(stored) == _normalize_damage(wanted)
    return str(stored).strip() == str(wanted).strip()


def matches(unit_md: dict[str, Any], clauses: tuple[Clause, ...]) -> bool:
    """True if the unit satisfies every clause (AND), membership within (OR)."""
    for c in clauses:
        stored_list = unit_md.get(c.field)
        if not isinstance(stored_list, list) or not stored_list:
            return False
        if c.op == "exists":
            continue  # non-empty already confirmed above
        if not any(
            _match_value(c.field, s, w) for s in stored_list for w in c.any_of
        ):
            return False
    return True


def apply_query(by_unit: dict[str, dict[str, Any]], q: EnumQuery) -> list[str]:
    """Return the sorted complete set of unit_ids matching q's predicate."""
    return sorted(uid for uid, md in by_unit.items() if matches(md, q.clauses))


# ---------------------------------------------------------------------------
# The authored query set (14 queries).
# ---------------------------------------------------------------------------

# Revised after spot-check (see MILESTONE-M7 §6). Dropped: bare class queries
# for non-casters (Thief/Assassin/Paladin) and alignment queries — the
# classes/alignment tags are token-mentions, not is-a, so the gold was a
# grab-bag (and "Protection from Evil" was tagged alignment=Evil). Caster-class
# "spell" queries now require spell_levels to exist (forces a real spell entry);
# damage queries require armor_class to exist (forces a monster stat block, not
# a random-encounter table). Every kept query was verified by reading samples.
QUERIES: list[EnumQuery] = [
    # --- spell level, single dimension (verified: all matches are spells) ---
    EnumQuery("enum_spell_l1", "Show me all first-level spells.",
              (Clause("spell_levels", ("1",)),)),
    EnumQuery("enum_spell_l3", "List every spell of the 3rd level.",
              (Clause("spell_levels", ("3",)),)),
    EnumQuery("enum_spell_l6", "List all 6th-level spells.",
              (Clause("spell_levels", ("6",)),)),
    EnumQuery("enum_spell_l9", "What are all the 9th-level spells?",
              (Clause("spell_levels", ("9",)),)),
    # --- caster-class spell lists (class tag AND must actually be a spell) ---
    EnumQuery("enum_class_druid_spells", "Which spells are available to Druids?",
              (Clause("classes", ("Druid",)), Clause("spell_levels", op="exists")),
              note="exists(spell_levels) drops Druid class-feature units"),
    EnumQuery("enum_class_cleric_spells", "List every Cleric spell.",
              (Clause("classes", ("Cleric",)), Clause("spell_levels", op="exists"))),
    EnumQuery("enum_class_mu_spells", "What spells can a Magic-User cast?",
              (Clause("classes", ("Magic-User",)), Clause("spell_levels", op="exists")),
              note="'Magic-User' is distinct from 'Wizard' in SWCR"),
    # --- compound class AND specific level ---
    EnumQuery("enum_compound_cleric_l2", "List all 2nd-level Cleric spells.",
              (Clause("classes", ("Cleric",)), Clause("spell_levels", ("2",)))),
    EnumQuery("enum_compound_mu_l1", "Every 1st-level Magic-User spell.",
              (Clause("classes", ("Magic-User",)), Clause("spell_levels", ("1",)))),
]

# Dropped after spot-check: damage-by-monster queries. The M1 miner populated
# `armor_class` on only ~16 units and `hit_dice` on ~10 (vs hundreds of monster
# stat blocks in the text), so there is no reliable "is a monster" metadata
# signal to separate a real stat block from a gameplay-narrative chunk that
# merely contains a dice notation. Damage-based enumeration is not supportable
# on this corpus's metadata; revisit only if monster stat-block extraction
# improves. The spell domain (spell_levels + caster classes) is clean and
# well-covered, which is enough for a first paradigm test.
#
# Granularity note: chunks are not 1:1 with spells. A chunk tagged level 9 may
# lead with a different-level spell because it spans several. Gold is therefore
# "units whose metadata matches the predicate" at chunk granularity — exactly
# what the route scans — so it remains an internally consistent, fair test of
# NL->predicate + execution.


def build_gold(by_unit: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compute the gold set for every query. Returns the serializable gold dict."""
    out: dict[str, Any] = {}
    for q in QUERIES:
        ids = apply_query(by_unit, q)
        out[q.id] = {
            "question": q.question,
            "predicate": {
                "clauses": [
                    {"field": c.field, "op": c.op, "any_of": list(c.any_of)}
                    for c in q.clauses
                ],
            },
            "dimensions": sorted({c.field for c in q.clauses}),
            "gold_unit_ids": ids,
            "set_size": len(ids),
            "note": q.note,
        }
    return out
