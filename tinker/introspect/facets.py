"""Schema-free facet discovery.

Generalizes M1's hand-tuned metadata miners. Instead of regexes that know
"spell level" / "damage" / "class", this discovers enumerable facets from the
corpus's own structure, with no predefined field names:

  1. Extract `**Label:** value` pairs from unit text. Labeled fields are a
     general document feature (stat blocks, nutrition labels, spec sheets,
     legal headers, API docs).
  2. Decompose each value into TYPED atomic tokens. The token-type taxonomy
     (integer, ordinal, dice, bareword) is corpus-independent — it is not
     "spell level", it is "an ordinal token under the 'Spell Level' label".
  3. Build an inverted index: (label, token_type, token) -> set of unit_ids.
  4. Qualify facets statistically: a (label, token_type) channel is enumerable
     when its token vocabulary is discrete (bounded cardinality) and recurs
     across many units. This is pure distribution statistics — the same filter
     that, by hand, told us damage_dice/armor_class were too sparse to trust.

The output is an auto-discovered inverted index that should recover SWCR's
spell-level and class facets without naming them, and recover whatever a
different corpus exposes without code changes.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable


# `**Label:**  value` — bolded label, colon, then value up to the next bold
# marker or newline. Label is 1-3 short words (letters, spaces, slash, hyphen).
_LABEL_RE = re.compile(
    r"\*\*\s*([A-Za-z][A-Za-z /\-]{1,28}?)\s*:\s*\*\*\s*([^\n*]{1,160})"
)

_ORDINAL_RE = re.compile(r"\b(\d{1,2})\s*(?:st|nd|rd|th)\b", re.IGNORECASE)
_DICE_RE = re.compile(r"\b(\d*d\d+)\b", re.IGNORECASE)
_INT_RE = re.compile(r"(?<![\dd])\b(\d{1,3})\b")
# Capitalized multiword barewords (e.g. class names "Magic-User", "Cleric").
_BAREWORD_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:-[A-Z][A-Za-z]+)?)\b")

_STOPWORDS = {
    "The", "A", "An", "Of", "And", "Or", "See", "No", "None", "N", "Level",
    "Range", "Duration", "Feet", "Foot", "Turn", "Turns", "Round", "Rounds",
    "Hour", "Hours", "Minute", "Minutes", "Day", "Days", "Yards", "Mile",
    "Miles", "Caster", "Touch", "Until", "Immediate", "Permanent",
}


@dataclass(frozen=True)
class FacetChannel:
    """One (label, token_type) channel and its value -> unit_ids index."""
    label: str
    token_type: str          # "ordinal" | "integer" | "dice" | "bareword"
    values: dict[str, list[str]]  # token value -> sorted unit_ids

    @property
    def cardinality(self) -> int:
        return len(self.values)

    @property
    def coverage(self) -> int:
        return len({uid for ids in self.values.values() for uid in ids})

    def enumerability(self) -> float:
        """Heuristic score: reward broad coverage, penalize near-unique vocab.

        A good enumerable facet has many units spread over a SMALL number of
        recurring values. Free-text fields (cardinality ~ coverage) score low.
        """
        if self.cardinality == 0:
            return 0.0
        units_per_value = self.coverage / self.cardinality
        return self.coverage * (1.0 - 1.0 / max(units_per_value, 1.0))


def _tokenize_value(value: str) -> list[tuple[str, str]]:
    """Decompose a raw value string into (token_type, token) pairs.

    General token types only — no corpus-specific field knowledge.
    """
    out: list[tuple[str, str]] = []
    for m in _ORDINAL_RE.finditer(value):
        out.append(("ordinal", m.group(1)))
    for m in _DICE_RE.finditer(value):
        tok = m.group(1).lower()
        if tok.startswith("d"):
            tok = "1" + tok
        out.append(("dice", tok))
    consumed = set()
    for m in _ORDINAL_RE.finditer(value):
        consumed.update(range(m.start(), m.end()))
    for m in _DICE_RE.finditer(value):
        consumed.update(range(m.start(), m.end()))
    for m in _INT_RE.finditer(value):
        if not any(i in consumed for i in range(m.start(), m.end())):
            out.append(("integer", m.group(1)))
    for m in _BAREWORD_RE.finditer(value):
        w = m.group(1)
        if w not in _STOPWORDS and not w.isupper():
            out.append(("bareword", w))
    return out


def discover_facets(
    units: Iterable[Any],
    *,
    min_coverage: int = 12,
    max_cardinality: int = 30,
    min_units_per_value: float = 2.0,
) -> list[FacetChannel]:
    """Discover enumerable facet channels across the corpus.

    `units` is any iterable of objects with `.id` and `.text`. Qualification
    thresholds encode the statistical signature of an enumerable attribute and
    are corpus-independent (defaults tuned to "recurs across >=12 units, <=30
    discrete values, >=2 units per value on average").
    """
    # (label, token_type, token) -> set of unit_ids
    index: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for u in units:
        text = getattr(u, "text", "") or ""
        uid = getattr(u, "id")
        for lm in _LABEL_RE.finditer(text):
            label = " ".join(lm.group(1).split()).title()
            value = lm.group(2)
            for ttype, tok in _tokenize_value(value):
                index[(label, ttype, tok)].add(uid)

    # Regroup into channels keyed by (label, token_type).
    channels: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(dict)
    for (label, ttype, tok), ids in index.items():
        channels[(label, ttype)][tok] = sorted(ids)

    qualified: list[FacetChannel] = []
    for (label, ttype), values in channels.items():
        ch = FacetChannel(label=label, token_type=ttype, values=values)
        if ch.cardinality == 0 or ch.cardinality > max_cardinality:
            continue
        if ch.coverage < min_coverage:
            continue
        if ch.coverage / ch.cardinality < min_units_per_value:
            continue
        qualified.append(ch)

    qualified.sort(key=lambda c: c.enumerability(), reverse=True)
    return qualified


def channel_key(ch: FacetChannel) -> str:
    """Stable id for a channel, e.g. 'Spell Level/ordinal'."""
    return f"{ch.label}/{ch.token_type}"
