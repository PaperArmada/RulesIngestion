from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from enrichment import (
    EnrichedChunk,
    extract_feat_title_from_text,
    extract_feat_titles_from_markdown,
    extract_spell_title_from_text,
    extract_spell_titles_from_markdown,
    extract_text_from_html,
    normalize_space,
)


def _regex_count(markdown_text: str, pattern: str) -> int:
    return len(re.findall(pattern, markdown_text, flags=re.MULTILINE))


def _normalize_title(text: str) -> str:
    cleaned = normalize_space(text).strip()
    # Remove markdown emphasis
    cleaned = cleaned.replace("*", "")
    # Remove action icons like [two-actions]
    cleaned = re.sub(r"\[[^\]]+\]", " ", cleaned)
    # Remove common type suffixes (SPELL 4, CANTRIP 1, FEAT 2)
    cleaned = re.sub(r"\b(SPELL|CANTRIP|FEAT)\s+\d+\b", " ", cleaned, flags=re.IGNORECASE)
    # Remove leading numeric prefixes like "CHAPTER 7:" or "7."
    cleaned = re.sub(r"^(CHAPTER|PART|SECTION)\s+\d+\s*[:\-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\d+\s*[:\.\-]?\s*", "", cleaned)
    # Strip non-title characters
    cleaned = re.sub(r"[^A-Za-z0-9\s'\-]", "", cleaned)
    return normalize_space(cleaned).upper()


def extract_toc_titles_from_markdown(markdown_text: str) -> List[str]:
    """Extract likely TOC section titles from Marker markdown output."""
    titles: List[str] = []
    heading_titles: List[str] = []
    bold_titles: List[str] = []
    lines = markdown_text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Bold headings like **SPELLS**
        bold_match = re.match(r"^\*\*([^*]+)\*\*$", stripped)
        if bold_match:
            raw = bold_match.group(1)
            # Skip spell/feat title lines
            if re.search(r"\b(SPELL|CANTRIP|FEAT)\b", raw, flags=re.IGNORECASE):
                continue
            # Skip lines with lowercase words (likely list entries)
            if re.search(r"[a-z]", raw):
                continue
            title = _normalize_title(raw)
            # Prefer shorter TOC-style headings
            if title and len(title) <= 40:
                bold_titles.append(title)
            continue

        # Markdown headings like # CHAPTER 7: SPELLS
        md_match = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if md_match:
            raw = md_match.group(1)
            if re.search(r"\b(SPELL|CANTRIP|FEAT)\b", raw, flags=re.IGNORECASE):
                continue
            title = _normalize_title(raw)
            if title and len(title) <= 60:
                heading_titles.append(title)

    # Prefer explicit markdown headings, fallback to bold headings
    titles = heading_titles if heading_titles else bold_titles

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def extract_section_titles_from_chunks(raw_chunks: List[Dict[str, Any]]) -> List[str]:
    """Extract section titles from JSON block types and section hierarchy."""
    titles: List[str] = []

    for chunk in raw_chunks:
        if chunk.get("block_type") == "SectionHeader":
            text = extract_text_from_html(chunk.get("html", ""))
            title = _normalize_title(text)
            if title:
                titles.append(title)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def build_metrics_report(
    markdown_path: str,
    raw_chunks: List[Dict[str, Any]],
    enriched_chunks: List[EnrichedChunk],
    doc_id: str,
) -> Dict[str, Any]:
    """Build a metrics report comparing JSON extraction to markdown regex counts."""
    markdown_path = Path(markdown_path)
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown source not found: {markdown_path}")

    markdown_text = markdown_path.read_text(encoding="utf-8")

    # JSON counts by block type
    block_type_counts = Counter()
    for chunk in raw_chunks:
        block_type = chunk.get("block_type", "Unknown")
        block_type_counts[block_type] += 1

    # Enriched counts by content kind
    content_kind_counts = Counter()
    for chunk in enriched_chunks:
        content_kind_counts[chunk.content_kind] += 1

    # Markdown regex counts
    regex_patterns = [
        {"name": "markdown_heading", "pattern": r"^#{1,6}\s+"},
        {"name": "bold_heading", "pattern": r"^\*\*.+\*\*$"},
        {"name": "table_row", "pattern": r"^\|.*\|$"},
        {"name": "spell_title", "pattern": r"^\*\*[A-Z][A-Z0-9\s'\-]+\*\*(?:\s*\[.*?\])?\s*\*\*(SPELL|CANTRIP)\s+\d+\*\*"},
        {"name": "feat_title", "pattern": r"^\*\*[A-Z][A-Z0-9\s'\-]+\*\*\s*\*\*FEAT\s+\d+\*\*"},
    ]
    regex_counts = {p["name"]: _regex_count(markdown_text, p["pattern"]) for p in regex_patterns}

    # Dynamic TOC/section review
    toc_titles = extract_toc_titles_from_markdown(markdown_text)
    section_titles = extract_section_titles_from_chunks(raw_chunks)

    toc_title_counts = {}
    for title in toc_titles:
        if not title:
            continue
        pattern = rf"\\b{re.escape(title)}\\b"
        toc_title_counts[title] = _regex_count(markdown_text, pattern)

    section_title_counts = {}
    for title in section_titles:
        if not title:
            continue
        pattern = rf"\\b{re.escape(title)}\\b"
        section_title_counts[title] = _regex_count(markdown_text, pattern)

    # Titles missing from markdown or sections
    toc_title_set = set(toc_titles)
    section_title_set = set(section_titles)
    missing_toc_in_sections = sorted(toc_title_set - section_title_set)[:100]
    extra_section_titles = sorted(section_title_set - toc_title_set)[:100]

    # Direct title extraction (more accurate for spells/feats)
    markdown_spell_titles = extract_spell_titles_from_markdown(markdown_text)
    markdown_feat_titles = extract_feat_titles_from_markdown(markdown_text)

    enriched_spell_titles = [
        extract_spell_title_from_text(c.text)
        for c in enriched_chunks
        if c.content_kind == "spell"
    ]
    enriched_spell_titles = [t for t in enriched_spell_titles if t]

    enriched_feat_titles = [
        extract_feat_title_from_text(c.text)
        for c in enriched_chunks
        if c.content_kind == "feat"
    ]
    enriched_feat_titles = [t for t in enriched_feat_titles if t]

    markdown_spell_set = set(markdown_spell_titles)
    markdown_feat_set = set(markdown_feat_titles)
    enriched_spell_set = set(enriched_spell_titles)
    enriched_feat_set = set(enriched_feat_titles)

    # Coverage comparisons
    comparisons = [
        {
            "name": "spell_titles",
            "markdown_count": len(markdown_spell_titles),
            "enriched_count": len(enriched_spell_titles),
            "missing_in_enriched": sorted(markdown_spell_set - enriched_spell_set)[:50],
            "extra_in_enriched": sorted(enriched_spell_set - markdown_spell_set)[:50],
        },
        {
            "name": "feat_titles",
            "markdown_count": len(markdown_feat_titles),
            "enriched_count": len(enriched_feat_titles),
            "missing_in_enriched": sorted(markdown_feat_set - enriched_feat_set)[:50],
            "extra_in_enriched": sorted(enriched_feat_set - markdown_feat_set)[:50],
        },
    ]

    # Coverage thresholds
    min_coverage = 0.99
    coverage_results = []

    def _coverage(name: str, total: int, missing: int) -> Dict[str, Any]:
        ratio = 1.0 if total == 0 else (total - missing) / total
        result = {
            "name": name,
            "total": total,
            "missing": missing,
            "coverage": round(ratio, 4),
            "min_required": min_coverage,
            "passes": ratio >= min_coverage,
        }
        return result

    coverage_results.append(
        _coverage("toc_titles_vs_sections", len(toc_title_set), len(missing_toc_in_sections))
    )

    # Compare markdown headings to SectionHeader count (proxy for structure coverage)
    section_header_count = block_type_counts.get("SectionHeader", 0)
    markdown_heading_count = regex_counts.get("markdown_heading", 0) + regex_counts.get("bold_heading", 0)
    missing_heading = max(section_header_count - markdown_heading_count, 0)
    coverage_results.append(
        _coverage("section_headers_vs_markdown_headings", section_header_count, missing_heading)
    )

    # Enforce strict coverage
    failed = [c for c in coverage_results if not c["passes"]]
    if failed:
        failure_summary = ", ".join(
            f"{c['name']}={c['coverage']:.2%}" for c in failed
        )
        raise ValueError(
            f"Coverage check failed (< {min_coverage:.0%}): {failure_summary}"
        )

    # Review config for adaptive checks
    review_config = {
        "doc_id": doc_id,
        "json_block_type_counts": dict(block_type_counts),
        "enriched_content_kind_counts": dict(content_kind_counts),
        "toc_titles": toc_titles,
        "section_titles": section_titles,
        "toc_title_counts_in_markdown": toc_title_counts,
        "section_title_counts_in_markdown": section_title_counts,
        "missing_toc_in_sections": missing_toc_in_sections,
        "extra_section_titles": extra_section_titles,
        "markdown_regex_patterns": regex_patterns,
        "markdown_regex_counts": regex_counts,
        "comparisons": comparisons,
        "coverage_results": coverage_results,
        "notes": [
            "Counts are approximate; Markdown patterns depend on formatting.",
            "Use comparisons.missing_in_enriched to prioritize manual review.",
            "Use missing_toc_in_sections to spot TOC headings not found in sections.",
            f"Minimum coverage enforced: {min_coverage:.0%}.",
        ],
    }

    return review_config
