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


# A field label, either bolded (**Label:**) or plain (Label:). Plain labels
# must be TitleCase 1-3 word phrases to avoid matching mid-sentence colons.
# Captured by position so the value can be sliced up to the NEXT label — this
# is typography-robust (works whether or not bold survived PDF extraction).
_LABEL_POS_RE = re.compile(
    r"\*\*\s*([A-Za-z][A-Za-z /\-]{1,28}?)\s*:\s*\*\*"          # **Label:**
    r"|(?:^|[\s\-—])([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,2})\s*:(?!\*)"  # Plain Label:
)

_PHRASE_MAX_LEN = 40  # values longer than this are prose, not a facet value

_ORDINAL_RE = re.compile(r"\b(\d{1,2})\s*(?:st|nd|rd|th)\b", re.IGNORECASE)
_DICE_RE = re.compile(r"\b(\d*d\d+)\b", re.IGNORECASE)
_INT_RE = re.compile(r"(?<![\dd])\b(\d{1,3})\b")
# Capitalized multiword barewords (e.g. class names "Magic-User", "Cleric").
_BAREWORD_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:-[A-Z][A-Za-z]+)?)\b")
# Per-glyph spacing artifacts seen in some PDFs (e.g. the 5e SRD): tab,
# carriage return, non-breaking space sprinkled between characters/words.
_WS_ARTIFACT_RE = re.compile(r"[\t\r\xa0]+")


def _normalize(text: str) -> str:
    """Strip per-glyph spacing artifacts and collapse whitespace.

    Keeps `*` (bold markers) and newlines structure-light but removes the
    tab/CR/nbsp noise that scrambles label detection on some PDFs.
    """
    text = _WS_ARTIFACT_RE.sub(" ", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text


def _clean_phrase(value: str) -> str | None:
    """Normalize a whole field value into a candidate 'phrase' facet value.

    Returns None if it looks like prose (too long) or is empty. Trailing
    punctuation and bold markers are stripped; case is lowered so
    'Instantaneous' and 'instantaneous' collapse.
    """
    v = value.strip().strip("*").strip()
    v = re.sub(r"[\s]+", " ", v)
    v = v.rstrip(".,;:—-").strip()
    if not v or len(v) > _PHRASE_MAX_LEN:
        return None
    # Drop values that are clearly sentence fragments (contain a verb-y comma
    # cascade) only by length heuristic above; keep short structured phrases.
    return v.lower()

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

    General token types only — no corpus-specific field knowledge. Emits both
    fine-grained typed tokens (ordinal/integer/dice/bareword) AND a coarse
    'phrase' token holding the whole cleaned value. The statistical qualifier
    then selects whichever representation forms a tight enumerable channel:
    phrase wins for fields like Casting Time ('1 bonus action'); typed tokens
    win for fields like Spell Level ('Cleric, 3rd Level' -> ordinal 3).
    """
    out: list[tuple[str, str]] = []
    phrase = _clean_phrase(value)
    if phrase is not None:
        out.append(("phrase", phrase))
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


def _extract_labeled_values(text: str) -> list[tuple[str, str]]:
    """Find (label, value) pairs by slicing each label to the next label.

    Typography-robust: matches bold or plain TitleCase labels, slices the value
    from the label's colon to the start of the next label (capped), so it does
    not depend on bold markers surviving PDF extraction.
    """
    text = _normalize(text)
    matches = list(_LABEL_POS_RE.finditer(text))
    pairs: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        label = (m.group(1) or m.group(2) or "").strip()
        if not label:
            continue
        value_start = m.end()
        value_end = matches[i + 1].start() if i + 1 < len(matches) else min(
            len(text), value_start + 120
        )
        value = text[value_start:value_end]
        pairs.append((label, value))
    return pairs


def discover_facets(
    units: Iterable[Any],
    *,
    min_coverage_floor: int = 6,
    min_coverage_frac: float = 0.015,
    max_cardinality: int = 30,
    min_units_per_value: float = 2.0,
) -> list[FacetChannel]:
    """Discover enumerable facet channels across the corpus.

    `units` is any iterable of objects with `.id` and `.text`. Qualification
    encodes the statistical signature of an enumerable attribute and adapts to
    corpus SIZE so the same code applies flexibly to corpora large and small:
    a channel must cover at least `max(min_coverage_floor, frac * n_units)`
    units, hold <= `max_cardinality` discrete values, and average
    >= `min_units_per_value` units per value. The coverage threshold is
    relative (a fraction of the corpus) with an absolute floor, rather than a
    hardcoded count tuned to one corpus.
    """
    units = list(units)
    n_units = len(units)
    min_coverage = max(min_coverage_floor, round(min_coverage_frac * n_units))

    # (label, token_type, token) -> set of unit_ids
    index: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for u in units:
        text = getattr(u, "text", "") or ""
        uid = getattr(u, "id")
        for raw_label, value in _extract_labeled_values(text):
            label = " ".join(raw_label.split()).title()
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
