"""
Structural identity for rule_block grouping.

Single source of truth for content path extraction and indexing.
Operates on chunks only; no extraction details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extraction.schemas import Chunk


def build_content_path_index(chunks: list["Chunk"]) -> dict[tuple[str, ...], list["Chunk"]]:
    """
    Build index: content_path -> [chunks with that exact path].

    Only index chunks with section_path length >= 2 (content chunks, not headers).
    Key is tuple for hashability.
    """
    index: dict[tuple[str, ...], list["Chunk"]] = {}
    for chunk in chunks:
        path = chunk.section_path or []
        if len(path) < 2:
            continue
        key = tuple(path)
        if key not in index:
            index[key] = []
        index[key].append(chunk)
    return index


def content_path_for_rule_header(
    header_chunk: "Chunk",
    chunks: list["Chunk"],
    header_index: int,
) -> tuple[str, ...] | None:
    """
    Find the content path for a rule that starts at header_chunk.

    A rule header has section_path length 1. Its content chunks have the same
    L1 and a longer path. The content path is the path of the first chunk
    AFTER header_index that:
      - has section_path length >= 2
      - has section_path[0] == header_chunk.section_path[0]

    Returns None if no such chunk exists.
    """
    header_path = header_chunk.section_path or []
    if len(header_path) != 1:
        return None

    l1 = header_path[0]
    for i in range(header_index + 1, len(chunks)):
        c = chunks[i]
        c_path = c.section_path or []
        if len(c_path) < 2:
            continue
        if c_path[0] == l1:
            return tuple(c_path)
    return None
