"""Spell chunk merge helpers."""

from __future__ import annotations

import re
from typing import List, Optional

from .chunks import EnrichedChunk
from .extractors import SPELL_STAT_PREFIXES, TRAIT_KEYWORDS, extract_spell_stats, extract_traits, extract_traditions


def is_trait_line(text: str) -> bool:
    """Check if text is a trait line (ALL CAPS words that are trait keywords)."""
    clean = re.sub(r"\*\*", "", text).strip()
    if not clean:
        return False

    words = clean.split()
    if not words:
        return False

    upper_words = [w for w in words if w.isupper()]
    trait_hits = sum(1 for w in words if w.lower() in TRAIT_KEYWORDS)
    return len(upper_words) >= 2 and trait_hits >= 1


def is_spell_entry_title(text: str) -> bool:
    """Check if text looks like a spell entry title line."""
    if not text:
        return False
    pattern = r"\*\*[A-Z][A-Z\s']+\*\*(?:\s*\[.*?\])?\s*\*\*(SPELL|CANTRIP)\s+\d+\*\*"
    return re.search(pattern, text) is not None


def is_spell_continuation(chunk: EnrichedChunk) -> bool:
    """Check if a chunk is likely a continuation of a spell entry."""
    if chunk.block_type in {"SectionHeader", "Title"}:
        return False
    if is_spell_entry_title(chunk.text):
        return False
    lowered = chunk.text.strip().lower()
    return lowered.startswith(
        ("you ", "the ", "if ", "this ", "targets ", "range ", "defense ", "heightened")
    )


def merge_spell_chunks(chunks: List[EnrichedChunk]) -> List[EnrichedChunk]:
    """Merge adjacent spell-related chunks into complete spell entries."""
    if not chunks:
        return chunks

    merged: List[EnrichedChunk] = []
    current_spell: Optional[EnrichedChunk] = None
    spell_page: Optional[int] = None
    blocks_since_spell: int = 0
    max_blocks_to_merge: int = 10

    for chunk in chunks:
        if not chunk.text.strip():
            if current_spell is not None:
                blocks_since_spell += 1
            continue

        is_spell_title = (
            chunk.content_kind == "spell"
            and chunk.spell_rank is not None
            and is_spell_entry_title(chunk.text)
        )

        if is_spell_title:
            if current_spell is not None:
                merged.append(current_spell)

            current_spell = chunk
            spell_page = chunk.page
            blocks_since_spell = 0

        elif current_spell is not None and blocks_since_spell < max_blocks_to_merge:
            is_adjacent = (
                chunk.page is not None
                and spell_page is not None
                and abs(chunk.page - spell_page) <= 1
            )

            is_spell_content = (
                chunk.traditions
                or chunk.content_kind in ("spell", "rule")
                or any(prefix in chunk.text.lower() for prefix in SPELL_STAT_PREFIXES)
                or "heightened" in chunk.text.lower()
                or is_trait_line(chunk.text)
            )

            new_spell_title = (
                chunk.content_kind == "spell"
                and chunk.spell_rank is not None
                and is_spell_entry_title(chunk.text)
            )

            if new_spell_title:
                merged.append(current_spell)
                current_spell = chunk
                spell_page = chunk.page
                blocks_since_spell = 0
            elif is_adjacent and (is_spell_content or is_spell_continuation(chunk)):
                current_spell.text += "\n\n" + chunk.text
                if chunk.traditions and not current_spell.traditions:
                    current_spell.traditions = chunk.traditions
                if chunk.traits:
                    current_spell.traits = list(set(current_spell.traits + chunk.traits))
                if is_trait_line(chunk.text):
                    new_traits = extract_traits(chunk.text)
                    current_spell.traits = list(set(current_spell.traits + new_traits))
                if chunk.spell_stats:
                    current_spell.spell_stats.update(chunk.spell_stats)
                current_spell.spell_stats = extract_spell_stats(current_spell.text)
                if not current_spell.traditions:
                    current_spell.traditions = extract_traditions(current_spell.text)
                blocks_since_spell += 1
            else:
                merged.append(current_spell)
                current_spell = None
                spell_page = None
                blocks_since_spell = 0
                merged.append(chunk)
        else:
            if current_spell is not None:
                merged.append(current_spell)
                current_spell = None
                spell_page = None
                blocks_since_spell = 0
            merged.append(chunk)

    if current_spell is not None:
        merged.append(current_spell)

    return merged
