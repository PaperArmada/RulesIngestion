"""Enriched chunk data structures."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .extractors import (
    build_section_path,
    classify_content,
    extract_spell_rank,
    extract_spell_stats,
    extract_tags,
    extract_text_from_html,
    extract_traits,
    extract_traditions,
    is_rule_bearing,
)


@dataclass
class EnrichedChunk:
    """Marker chunk enhanced with TTRPG metadata."""

    id: str
    block_type: str
    text: str
    page: int
    bbox: List[float] = field(default_factory=list)
    section_hierarchy: Dict[str, Any] = field(default_factory=dict)

    content_kind: str = "narrative"  # spell, feat, item, rule, narrative, table, image
    is_rule_bearing: bool = False
    tags: List[str] = field(default_factory=list)
    traits: List[str] = field(default_factory=list)
    spell_rank: Optional[int] = None
    traditions: List[str] = field(default_factory=list)
    spell_stats: Dict[str, str] = field(default_factory=dict)
    section_path: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def enrich_chunk(chunk: Dict[str, Any]) -> EnrichedChunk:
    """Add TTRPG metadata to a Marker chunk."""
    html = chunk.get("html", "")
    text = extract_text_from_html(html)

    section_hierarchy = chunk.get("section_hierarchy", {})
    section_path = build_section_path(section_hierarchy)

    block_type = chunk.get("block_type", "Text")
    content_kind = classify_content(text, section_path, block_type)

    spell_rank = None
    traditions: List[str] = []
    spell_stats: Dict[str, str] = {}

    if content_kind == "spell":
        spell_rank = extract_spell_rank(text)
        traditions = extract_traditions(text)
        spell_stats = extract_spell_stats(text)

    return EnrichedChunk(
        id=chunk.get("id", str(uuid.uuid4())),
        block_type=block_type,
        text=text,
        page=chunk.get("page", 0),
        bbox=chunk.get("bbox", []),
        section_hierarchy=section_hierarchy,
        content_kind=content_kind,
        is_rule_bearing=is_rule_bearing(text),
        tags=extract_tags(section_path, text),
        traits=extract_traits(text),
        spell_rank=spell_rank,
        traditions=traditions,
        spell_stats=spell_stats,
        section_path=section_path,
    )
