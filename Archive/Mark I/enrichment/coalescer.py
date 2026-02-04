"""Chunk coalescing utilities."""

from __future__ import annotations

from typing import List

from .chunks import EnrichedChunk


def coalesce_chunks(
    chunks: List[EnrichedChunk],
    min_chars: int = 400,
    max_chars: int = 800,
) -> List[EnrichedChunk]:
    """Merge adjacent chunks until a minimum length is reached."""
    if not chunks:
        return []

    coalesced: List[EnrichedChunk] = []
    buffer: List[EnrichedChunk] = []
    buffer_len = 0

    def _flush() -> None:
        nonlocal buffer_len
        if not buffer:
            return
        text_parts = [c.text for c in buffer if c.text]
        merged_text = "\n\n".join(text_parts)
        content_kinds = {c.content_kind for c in buffer}
        spell_stats = (
            buffer[0].spell_stats
            if len({tuple(c.spell_stats.items()) for c in buffer}) == 1
            else {}
        )
        merged = EnrichedChunk(
            id=f"coalesced-{buffer[0].id}",
            block_type="Coalesced",
            text=merged_text,
            page=buffer[0].page,
            bbox=buffer[0].bbox,
            section_hierarchy=buffer[0].section_hierarchy,
            content_kind=buffer[0].content_kind if len(content_kinds) == 1 else "mixed",
            is_rule_bearing=any(c.is_rule_bearing for c in buffer),
            tags=sorted({tag for c in buffer for tag in c.tags}),
            traits=sorted({trait for c in buffer for trait in c.traits}),
            spell_rank=buffer[0].spell_rank if len({c.spell_rank for c in buffer}) == 1 else None,
            traditions=sorted({t for c in buffer for t in c.traditions}),
            spell_stats=spell_stats,
            section_path=buffer[0].section_path,
        )
        coalesced.append(merged)
        buffer.clear()
        buffer_len = 0

    for chunk in chunks:
        if not chunk.text.strip():
            continue

        is_header = chunk.block_type in {"SectionHeader", "Title"}
        section_changed = (
            buffer
            and chunk.section_path
            and buffer[0].section_path
            and chunk.section_path != buffer[0].section_path
        )

        if is_header and buffer:
            _flush()

        if section_changed and buffer_len >= min_chars:
            _flush()

        proposed_len = buffer_len + len(chunk.text)
        if buffer and buffer_len >= min_chars and proposed_len > max_chars:
            _flush()

        buffer.append(chunk)
        buffer_len += len(chunk.text)

        if buffer_len >= max_chars:
            _flush()

    _flush()
    return coalesced
