from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from scripts.discover_deterministic_edges_text import (
    _build_anchor_variants,
    _extract_heading_text,
    _normalize_label,
    _normalize_title,
    _strip_heading_numbers,
)


def _load_enriched(path: Path) -> Tuple[str, List[Dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    doc_id = payload.get("document") or path.stem.replace(".enriched", "")
    chunks = payload.get("chunks", [])
    return doc_id, chunks if isinstance(chunks, list) else []


def _parse_doc_page_offset(doc_id: str) -> Optional[int]:
    matches = re.findall(r"-(\d{1,4})-(\d{1,4})(?=\D|$)", doc_id)
    if not matches:
        return None
    start_label, end_label = matches[-1]
    try:
        start = int(start_label)
        end = int(end_label)
    except ValueError:
        return None
    if start > end:
        return None
    return start


def _extract_page_from_chunk(chunk: Dict[str, Any]) -> Optional[int]:
    chunk_id = chunk.get("id", "") or ""
    match = re.search(r"/page/(\d+)/", chunk_id)
    parsed_page = int(match.group(1)) if match else None
    page_value = chunk.get("page")
    if parsed_page is not None:
        return parsed_page
    if isinstance(page_value, int):
        return page_value
    try:
        return int(page_value)
    except (TypeError, ValueError):
        return None


def _extract_table_labels(text: str) -> List[str]:
    labels: List[str] = []
    if not text:
        return labels
    pattern = re.compile(r"\b(?:Table|TABLE)\s+([A-Za-z]?\d+(?:[.\-–]\d+)*)")
    for match in pattern.findall(text):
        normalized = _normalize_label(match)
        if normalized:
            labels.append(normalized)
    return labels


def _extract_table_caption(text: str) -> Optional[str]:
    if not text:
        return None
    pattern = re.compile(
        r"\b(?:Table|TABLE)\s+[A-Za-z]?\d+(?:[.\-–]\d+)*\s*[:\-–]\s*(.+)$"
    )
    for line in text.splitlines():
        match = pattern.search(line.strip())
        if match:
            caption = _normalize_title(match.group(1))
            return caption if caption else None
    return None


def _extract_figure_labels(text: str) -> List[str]:
    labels: List[str] = []
    if not text:
        return labels
    pattern = re.compile(r"\b(?:Figure|FIGURE)\s+([A-Za-z]?\d+(?:[.\-–]\d+)*)")
    for match in pattern.findall(text):
        normalized = _normalize_label(match)
        if normalized:
            labels.append(normalized)
    return labels


def _extract_figure_caption(text: str) -> Optional[str]:
    if not text:
        return None
    pattern = re.compile(
        r"\b(?:Figure|FIGURE)\s+[A-Za-z]?\d+(?:[.\-–]\d+)*\s*[:\-–]\s*(.+)$"
    )
    for line in text.splitlines():
        match = pattern.search(line.strip())
        if match:
            caption = _normalize_title(match.group(1))
            return caption if caption else None
    return None


def _extract_chapter_label(title: str) -> Optional[str]:
    if not title:
        return None
    pattern = re.compile(r"\bChapter\s+(\d+|[IVXLC]+)\b", re.IGNORECASE)
    match = pattern.search(title)
    if not match:
        return None
    return _normalize_label(match.group(1))


def _build_page_text_index(
    chunks: List[Dict[str, Any]],
    page_offset: Optional[int],
) -> Dict[str, List[Tuple[str, Optional[str], Optional[str], Optional[str]]]]:
    page_map: Dict[str, List[Tuple[str, Optional[str], Optional[str], Optional[str]]]] = (
        defaultdict(list)
    )
    for chunk in chunks:
        chunk_id = chunk.get("id")
        if not chunk_id:
            continue
        page_value = _extract_page_from_chunk(chunk)
        if page_value is None:
            continue
        page_label = _normalize_label(str(page_value))
        if not page_label:
            continue
        block_type = chunk.get("block_type") or ""
        text = chunk.get("text", "") or ""
        heading_text = (
            _extract_heading_text(text)
            if block_type in {"SectionHeader", "Title"}
            else ""
        )
        section_path = chunk.get("section_path") or []
        section_tail = section_path[-1] if section_path else ""
        first_line = text.splitlines()[0].strip() if text else ""
        entry = (
            chunk_id,
            block_type,
            heading_text or None,
            section_tail or None,
            first_line or None,
        )
        page_map[page_label].append(entry)
        if page_offset is not None:
            printed_page = page_value + page_offset
            printed_label = _normalize_label(str(printed_page))
            if printed_label:
                page_map[printed_label].append(entry)
        page_map[f"page {page_label}"].append(entry)
        if page_offset is not None:
            printed_page = page_value + page_offset
            printed_label = _normalize_label(str(printed_page))
            if printed_label:
                page_map[f"page {printed_label}"].append(entry)
    return page_map


def _build_indices(
    chunks: List[Dict[str, Any]],
    doc_id: str,
    page_offset: Optional[int],
) -> Dict[str, Dict[str, Set[str]]]:
    indices: Dict[str, Dict[str, Set[str]]] = {
        "table": defaultdict(set),
        "figure": defaultdict(set),
        "chapter": defaultdict(set),
        "section": defaultdict(set),
        "section_exact": defaultdict(set),
        "page": defaultdict(set),
    }
    for chunk in chunks:
        chunk_id = chunk.get("id")
        if not chunk_id:
            continue

        page_value = _extract_page_from_chunk(chunk)
        if page_value is not None:
            page_label = _normalize_label(str(page_value))
            if page_label:
                indices["page"][page_label].add(chunk_id)
                indices["page"][f"page {page_label}"].add(chunk_id)
            if page_offset is not None:
                printed_page = page_value + page_offset
                printed_label = _normalize_label(str(printed_page))
                if printed_label:
                    indices["page"][printed_label].add(chunk_id)
                    indices["page"][f"page {printed_label}"].add(chunk_id)

        section_path = chunk.get("section_path") or []
        section_key = " > ".join(section_path) if section_path else ""
        if section_key:
            section_id = f"{doc_id}::section::{section_key}"
            for idx in range(len(section_path)):
                heading = " ".join(section_path[idx:])
                for anchor in _build_anchor_variants(heading):
                    indices["section"][anchor].add(section_id)
                stripped_heading = _strip_heading_numbers(heading)
                if stripped_heading and stripped_heading != heading:
                    for anchor in _build_anchor_variants(stripped_heading):
                        indices["section"][anchor].add(section_id)
                exact_heading = _normalize_title(heading)
                if exact_heading:
                    indices["section_exact"][exact_heading].add(section_id)
            for segment in section_path:
                chapter_label = _extract_chapter_label(segment)
                if chapter_label:
                    indices["chapter"][chapter_label].add(section_id)
                    indices["chapter"][f"chapter {chapter_label}"].add(section_id)

        text = chunk.get("text", "") or ""
        content_kind = chunk.get("content_kind", "")
        block_type = chunk.get("block_type", "")

        if block_type in {"SectionHeader", "Title"}:
            heading_text = _extract_heading_text(text)
            if heading_text:
                heading_id = f"{doc_id}::heading::{chunk_id}"
                for anchor in _build_anchor_variants(heading_text):
                    indices["section"][anchor].add(heading_id)
                stripped_heading = _strip_heading_numbers(heading_text)
                if stripped_heading and stripped_heading != heading_text:
                    for anchor in _build_anchor_variants(stripped_heading):
                        indices["section"][anchor].add(heading_id)
                exact_heading = _normalize_title(heading_text)
                if exact_heading:
                    indices["section_exact"][exact_heading].add(heading_id)
                chapter_label = _extract_chapter_label(heading_text)
                if chapter_label:
                    indices["chapter"][chapter_label].add(heading_id)
                    indices["chapter"][f"chapter {chapter_label}"].add(heading_id)

        if content_kind == "table" or block_type == "Table":
            labels = _extract_table_labels(text) or [
                _normalize_label(segment)
                for segment in section_path
                if segment.lower().startswith("table")
            ]
            caption = _extract_table_caption(text)
            for label in labels:
                if label:
                    indices["table"][label].add(chunk_id)
                    indices["table"][f"table {label}"].add(chunk_id)
                    if caption:
                        indices["table"][caption].add(chunk_id)
                        indices["table"][f"table {label} {caption}"].add(chunk_id)

        if content_kind == "image" or block_type == "Picture":
            labels = _extract_figure_labels(text) or [
                _normalize_label(segment)
                for segment in section_path
                if segment.lower().startswith("figure")
            ]
            caption = _extract_figure_caption(text)
            for label in labels:
                if label:
                    indices["figure"][label].add(chunk_id)
                    indices["figure"][f"figure {label}"].add(chunk_id)
                    if caption:
                        indices["figure"][caption].add(chunk_id)
                        indices["figure"][f"figure {label} {caption}"].add(chunk_id)

    return indices


def _build_section_header_index(
    chunks: List[Dict[str, Any]],
) -> Dict[str, str]:
    header_index: Dict[str, str] = {}
    for chunk in chunks:
        chunk_id = chunk.get("id")
        if not chunk_id:
            continue
        block_type = chunk.get("block_type") or ""
        if block_type not in {"SectionHeader", "Title"}:
            continue
        section_path = chunk.get("section_path") or []
        if not section_path:
            continue
        section_key = " > ".join(section_path)
        if section_key and section_key not in header_index:
            header_index[section_key] = chunk_id
    return header_index
