"""Auto-generate the enumeration eval from discovered facets.

No hand-authoring: for each qualified facet channel, emit (NL query, gold set)
pairs for its highest-coverage values. Gold is facet membership by construction,
so this tests the route's query-form detection + facet resolution + complete
scan, on whatever facets a corpus exposes — SWCR today, a different corpus
unchanged tomorrow.

Query phrasing is templated per token_type so the NL reads naturally while the
underlying target stays (channel, value):
  ordinal  -> "List every <label> <value> entry."   (e.g. Spell Level 3)
  bareword -> "List everything whose <label> is <value>."
  integer  -> "List every entry with <label> <value>."
  dice     -> "List everything with a <label> of <value>."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tinker.introspect.facets import FacetChannel, channel_key


@dataclass(frozen=True)
class AutoEnumQuery:
    id: str
    question: str
    channel: str          # e.g. "Spell Level/ordinal"
    label: str
    token_type: str
    value: str
    gold_unit_ids: list[str]

    @property
    def set_size(self) -> int:
        return len(self.gold_unit_ids)


_ORDINAL_SUFFIX = {"1": "1st", "2": "2nd", "3": "3rd"}


def _ordinalize(v: str) -> str:
    return _ORDINAL_SUFFIX.get(v, f"{v}th") if v.isdigit() else v


def _phrase(label: str, token_type: str, value: str) -> str:
    label_l = label.strip()
    if token_type == "ordinal":
        return f"List every {label_l} {_ordinalize(value)} entry."
    if token_type == "bareword":
        return f"List everything whose {label_l} is {value}."
    if token_type == "dice":
        return f"List everything with {label_l} of {value}."
    return f"List every entry with {label_l} {value}."


def generate_queries(
    channels: list[FacetChannel],
    *,
    min_set_size: int = 8,
    values_per_channel: int = 3,
    max_queries: int = 40,
) -> list[AutoEnumQuery]:
    """Emit templated enumeration queries for the top values of each channel.

    Picks the highest-coverage values per channel (those are the ones where the
    set-completion-vs-top-K contrast is sharpest). Skips values below
    `min_set_size`. Caps total queries for a tractable eval.
    """
    out: list[AutoEnumQuery] = []
    for ch in channels:
        ranked = sorted(ch.values.items(), key=lambda kv: -len(kv[1]))
        taken = 0
        for value, ids in ranked:
            if len(ids) < min_set_size:
                break  # ranked desc; nothing smaller will qualify
            if taken >= values_per_channel:
                break
            ckey = channel_key(ch)
            qid = f"auto_{ch.label.lower().replace(' ', '_')}_{ch.token_type}_{value}"
            out.append(AutoEnumQuery(
                id=qid,
                question=_phrase(ch.label, ch.token_type, value),
                channel=ckey,
                label=ch.label,
                token_type=ch.token_type,
                value=value,
                gold_unit_ids=sorted(ids),
            ))
            taken += 1
    out.sort(key=lambda q: -q.set_size)
    return out[:max_queries]


def to_gold_dict(queries: list[AutoEnumQuery]) -> dict[str, Any]:
    return {
        q.id: {
            "question": q.question,
            "channel": q.channel,
            "label": q.label,
            "token_type": q.token_type,
            "value": q.value,
            "gold_unit_ids": q.gold_unit_ids,
            "set_size": q.set_size,
        }
        for q in queries
    }
