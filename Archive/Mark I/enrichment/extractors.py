"""Shared extraction and classification helpers for enrichment."""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .chunks import EnrichedChunk


# =============================================================================
# TTRPG VOCABULARIES (extracted from legacy pipeline)
# =============================================================================

SECTION_TAGS: Dict[str, str] = {
    "character creation": "character_creation",
    "leveling up": "leveling_up",
    "exploring the galaxy": "exploration",
    "religion": "religion",
    "ancestries": "ancestries",
    "backgrounds": "backgrounds",
    "classes": "classes",
    "skills": "skills",
    "feats": "feats",
    "equipment": "equipment",
    "spells": "spells",
    "playing the game": "playing_the_game",
    "conditions": "conditions",
    "glossary": "glossary",
    "index": "glossary",
    "introduction": "introduction",
    "encounters": "combat",
    "downtime": "downtime",
    "exploration": "exploration",
    "dice": "dice",
    "action": "actions",
    "saving throw": "saving_throws",
    "armor class": "ac",
    "hit points": "hp",
    "proficiency": "proficiency",
    "initiative": "initiative",
    "key terms": "glossary",
}

CONTENT_TYPE_BY_KIND: Dict[str, str] = {
    "rule": "rule",
    "constraint": "rule",
    "definition": "rule",
    "narrative": "narrative",
    "example": "example",
    "table": "table",
    "toc": "toc",
    "nav": "nav",
    "credits": "credits",
    "heading": "heading",
    "trait": "trait",
    "spell": "spell",
    "feat": "feat",
    "item": "item",
    "glossary": "other",
}

RULE_KEYWORDS = {
    "dc",
    "saving throw",
    "check",
    "action",
    "actions",
    "damage",
    "spell",
    "spells",
    "hit points",
    "armor class",
    "ac",
    "modifier",
    "proficiency",
    "initiative",
    "skill",
    "feat",
    "trait",
    "rarity",
}

TRAIT_KEYWORDS = {
    "attack",
    "auditory",
    "aura",
    "cold",
    "concentrate",
    "curse",
    "darkness",
    "emotion",
    "fire",
    "healing",
    "illusion",
    "incapacitation",
    "linguistic",
    "manipulate",
    "mental",
    "polymorph",
    "prediction",
    "radiation",
    "sonic",
    "subtle",
    "unholy",
    "visual",
    "vitality",
    "void",
    "detection",
}

CONSTRAINT_KEYWORDS = {
    "must",
    "cannot",
    "must not",
    "only if",
    "requires",
    "required",
    "prerequisite",
    "prerequisites",
}

SPELL_STAT_PREFIXES = (
    "cast",
    "range",
    "targets",
    "target",
    "area",
    "duration",
    "saving throw",
    "cost",
    "trigger",
    "requirements",
    "effect",
    "traditions",
    "defense",
)

# High-value tags to keep for RAG
HIGH_VALUE_TAGS = {
    "spells",
    "feats",
    "classes",
    "ancestries",
    "equipment",
    "conditions",
    "skills",
    "playing_the_game",
    "actions",
    "character_creation",
    "combat",
}


# =============================================================================
# HTML TEXT EXTRACTION
# =============================================================================

class HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML, preserving markdown-style formatting."""

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: List[str] = []
        self.in_bold = False
        self.in_italic = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in ("b", "strong"):
            self.text_parts.append("**")
            self.in_bold = True
        elif tag in ("i", "em"):
            self.text_parts.append("*")
            self.in_italic = True
        elif tag == "br":
            self.text_parts.append("\n")
        elif tag == "p":
            if self.text_parts and not self.text_parts[-1].endswith("\n"):
                self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("b", "strong") and self.in_bold:
            self.text_parts.append("**")
            self.in_bold = False
        elif tag in ("i", "em") and self.in_italic:
            self.text_parts.append("*")
            self.in_italic = False
        elif tag == "p":
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)

    def get_text(self) -> str:
        return "".join(self.text_parts).strip()


def extract_text_from_html(html: str) -> str:
    """Extract plain text from HTML content."""
    if not html:
        return ""
    parser = HTMLTextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()


# =============================================================================
# TTRPG CLASSIFICATION FUNCTIONS
# =============================================================================

def normalize_space(text: str) -> str:
    """Collapse whitespace to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def extract_tags(section_path: List[str], text: str, allow_text: bool = True) -> List[str]:
    """Extract TTRPG-relevant tags from section path and text."""
    tags: List[str] = []
    lower_section = " ".join(section_path).lower()

    for key, tag in SECTION_TAGS.items():
        if key in lower_section:
            tags.append(tag)

    if allow_text:
        lower_text = text.lower()
        for key, tag in SECTION_TAGS.items():
            if key in lower_text and tag not in tags:
                tags.append(tag)

    tags = [t for t in tags if t in HIGH_VALUE_TAGS]
    return sorted(set(tags))


def is_rule_bearing(text: str) -> bool:
    """Check if text contains mechanical rule keywords."""
    lower = text.lower()
    return any(keyword in lower for keyword in RULE_KEYWORDS)


def contains_constraints(text: str) -> bool:
    """Check if text contains constraint keywords."""
    lower = text.lower()
    return any(keyword in lower for keyword in CONSTRAINT_KEYWORDS)


def extract_traits(text: str) -> List[str]:
    """Extract trait keywords from text (usually in ALL CAPS lines)."""
    traits: List[str] = []
    trait_pattern = r"\*\*([A-Z][A-Z\s]+)\*\*"
    matches = re.findall(trait_pattern, text)

    for match in matches:
        words = match.split()
        for word in words:
            word_lower = word.lower()
            if word_lower in TRAIT_KEYWORDS:
                traits.append(word.upper())

    return sorted(set(traits))


def extract_spell_rank(text: str) -> Optional[int]:
    """Extract spell rank from Marker output like 'SPELL 8' or 'CANTRIP 1'."""
    match = re.search(r"\*\*(?:SPELL|CANTRIP)\s+(\d+)\*\*", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"(?:SPELL|CANTRIP)\s+(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def extract_traditions(text: str) -> List[str]:
    """Extract traditions from lines like '**Traditions** arcane, primal'."""
    match = re.search(r"\*\*Traditions\*\*\s+([^\n]+)", text, re.IGNORECASE)
    if match:
        traditions_str = match.group(1)
        traditions = re.split(r"[,;]", traditions_str)
        return [t.strip().lower() for t in traditions if t.strip()]

    match = re.search(r"Traditions\s+([^\n]+)", text, re.IGNORECASE)
    if match:
        traditions_str = match.group(1)
        traditions = re.split(r"[,;]", traditions_str)
        return [t.strip().lower() for t in traditions if t.strip()]

    return []


def extract_spell_titles_from_markdown(markdown_text: str) -> List[str]:
    """Extract spell names from Marker markdown output."""
    pattern = (
        r"^\*\*([A-Z][A-Z0-9\s'\-]+)\*\*(?:\s*\[.*?\])?\s*"
        r"\*\*(SPELL|CANTRIP)\s+\d+\*\*"
    )
    matches = re.findall(pattern, markdown_text, flags=re.MULTILINE)
    names = []
    for name, _ in matches:
        cleaned = normalize_space(name.replace("*", "")).strip()
        if cleaned:
            names.append(cleaned.upper())
    return names


def extract_spell_title_from_text(text: str) -> Optional[str]:
    """Extract a spell name from enriched chunk text."""
    if not text:
        return None
    pattern = (
        r"\*\*([A-Z][A-Z0-9\s'\-]+)\*\*(?:\s*\[.*?\])?\s*"
        r"\*\*(SPELL|CANTRIP)\s+\d+\*\*"
    )
    match = re.search(pattern, text)
    if match:
        return normalize_space(match.group(1)).strip().upper()
    return None


def extract_feat_titles_from_markdown(markdown_text: str) -> List[str]:
    """Extract feat names from Marker markdown output."""
    pattern = r"^\*\*([A-Z][A-Z0-9\s'\-]+?)\s*\*\*\s*(?:\[[^\]]+\]\s*)?\*\*FEAT\s+\d+\*\*"
    matches = re.findall(pattern, markdown_text, flags=re.MULTILINE)
    names = []
    for name in matches:
        cleaned = normalize_space(name.replace("*", "")).strip()
        if cleaned:
            names.append(cleaned.upper())
    return names


def extract_feat_title_from_text(text: str) -> Optional[str]:
    """Extract a feat name from enriched chunk text."""
    if not text:
        return None
    pattern = r"\*\*([A-Z][A-Z0-9\s'\-]+?)\s*\*\*\s*(?:\[[^\]]+\]\s*)?\*\*FEAT\s+\d+\*\*"
    match = re.search(pattern, text)
    if match:
        return normalize_space(match.group(1)).strip().upper()
    return None


# =============================================================================
# METRICS & REVIEW
# =============================================================================

def _regex_count(markdown_text: str, pattern: str) -> int:
    return len(re.findall(pattern, markdown_text, flags=re.MULTILINE))


def _normalize_title(text: str) -> str:
    cleaned = normalize_space(text).strip()
    cleaned = cleaned.replace("*", "")
    cleaned = re.sub(r"\[[^\]]+\]", " ", cleaned)
    cleaned = re.sub(r"\b(SPELL|CANTRIP|FEAT)\s+\d+\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(CHAPTER|PART|SECTION)\s+\d+\s*[:\-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\d+\s*[:\.\-]?\s*", "", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9\s'\-]", "", cleaned)
    return normalize_space(cleaned).upper()


def extract_toc_titles_from_markdown(markdown_text: str) -> List[str]:
    """Extract likely TOC section titles from Marker markdown output."""
    heading_titles: List[str] = []
    bold_titles: List[str] = []
    lines = markdown_text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        bold_match = re.match(r"^\*\*([^*]+)\*\*$", stripped)
        if bold_match:
            raw = bold_match.group(1)
            if re.search(r"\b(SPELL|CANTRIP|FEAT)\b", raw, flags=re.IGNORECASE):
                continue
            if re.search(r"[a-z]", raw):
                continue
            title = _normalize_title(raw)
            if title and len(title) <= 40:
                bold_titles.append(title)
            continue

        md_match = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if md_match:
            raw = md_match.group(1)
            if re.search(r"\b(SPELL|CANTRIP|FEAT)\b", raw, flags=re.IGNORECASE):
                continue
            title = _normalize_title(raw)
            if title and len(title) <= 60:
                heading_titles.append(title)

    titles = heading_titles if heading_titles else bold_titles

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
    enriched_chunks: List["EnrichedChunk"],
    doc_id: str,
) -> Dict[str, Any]:
    """Build a metrics report comparing JSON extraction to markdown regex counts."""
    markdown_path = Path(markdown_path)
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown source not found: {markdown_path}")

    markdown_text = markdown_path.read_text(encoding="utf-8")

    block_type_counts = Counter()
    for chunk in raw_chunks:
        block_type = chunk.get("block_type", "Unknown")
        block_type_counts[block_type] += 1

    content_kind_counts = Counter()
    for chunk in enriched_chunks:
        content_kind_counts[chunk.content_kind] += 1

    regex_patterns = [
        {"name": "markdown_heading", "pattern": r"^#{1,6}\s+"},
        {"name": "bold_heading", "pattern": r"^\*\*.+\*\*$"},
        {"name": "table_row", "pattern": r"^\|.*\|$"},
        {
            "name": "spell_title",
            "pattern": r"^\*\*[A-Z][A-Z0-9\s'\-]+\*\*(?:\s*\[.*?\])?\s*\*\*(SPELL|CANTRIP)\s+\d+\*\*",
        },
        {"name": "feat_title", "pattern": r"^\*\*[A-Z][A-Z0-9\s'\-]+\*\*\s*\*\*FEAT\s+\d+\*\*"},
    ]
    regex_counts = {p["name"]: _regex_count(markdown_text, p["pattern"]) for p in regex_patterns}

    toc_titles = extract_toc_titles_from_markdown(markdown_text)
    section_titles = extract_section_titles_from_chunks(raw_chunks)

    toc_title_counts = {}
    for title in toc_titles:
        if not title:
            continue
        pattern = rf"\b{re.escape(title)}\b"
        toc_title_counts[title] = _regex_count(markdown_text, pattern)

    section_title_counts = {}
    for title in section_titles:
        if not title:
            continue
        pattern = rf"\b{re.escape(title)}\b"
        section_title_counts[title] = _regex_count(markdown_text, pattern)

    toc_title_set = set(toc_titles)
    section_title_set = set(section_titles)
    missing_toc_in_sections = sorted(toc_title_set - section_title_set)[:100]
    extra_section_titles = sorted(section_title_set - toc_title_set)[:100]

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

    section_header_count = block_type_counts.get("SectionHeader", 0)
    markdown_heading_count = regex_counts.get("markdown_heading", 0) + regex_counts.get("bold_heading", 0)
    missing_heading = max(section_header_count - markdown_heading_count, 0)
    coverage_results.append(
        _coverage("section_headers_vs_markdown_headings", section_header_count, missing_heading)
    )

    failed = [c for c in coverage_results if not c["passes"]]
    if failed:
        failure_summary = ", ".join(f"{c['name']}={c['coverage']:.2%}" for c in failed)
        raise ValueError(f"Coverage check failed (< {min_coverage:.0%}): {failure_summary}")

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


def extract_spell_stats(text: str) -> Dict[str, str]:
    """Extract spell statistics (Range, Targets, Defense, etc.)."""
    stats: Dict[str, str] = {}
    for prefix in SPELL_STAT_PREFIXES:
        pattern = rf"\*\*{prefix.title()}\*\*\s+([^*\n;]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            stats[prefix] = match.group(1).strip()
    return stats


def is_spell_block(text: str) -> bool:
    """Check if text appears to be a spell entry."""
    if re.search(r"\*\*(?:SPELL|CANTRIP)\s+\d+\*\*", text, re.IGNORECASE):
        return True
    if re.search(r"(?:SPELL|CANTRIP)\s+\d+", text, re.IGNORECASE):
        return True
    if re.search(r"\*\*Traditions\*\*", text, re.IGNORECASE):
        return True
    return False


def is_feat_block(text: str) -> bool:
    """Check if text appears to be a feat entry."""
    if re.search(r"\*\*FEAT\s+\d+\*\*", text, re.IGNORECASE):
        return True
    if re.search(r"\*\*Prerequisites?\*\*", text, re.IGNORECASE):
        return True
    return False


def classify_content(text: str, section_path: List[str], block_type: str) -> str:
    """Classify block as spell/feat/item/rule/narrative/table."""
    if block_type == "Table":
        return "table"
    if block_type == "Picture":
        return "image"

    if is_spell_block(text):
        return "spell"
    if is_feat_block(text):
        return "feat"
    if contains_constraints(text):
        return "rule"
    if is_rule_bearing(text):
        return "rule"

    section_str = " ".join(section_path).lower()
    if "spell" in section_str:
        return "spell"
    if "feat" in section_str:
        return "feat"
    if "equipment" in section_str or "item" in section_str:
        return "item"

    return "narrative"


def build_section_path(section_hierarchy: Dict[str, Any]) -> List[str]:
    """Build a flat section path from Marker's nested section_hierarchy."""
    if not section_hierarchy:
        return []

    path: List[str] = []

    def extract_titles(node: Any) -> None:
        if isinstance(node, dict):
            if "title" in node:
                path.append(node["title"])
            for key, value in node.items():
                if key != "title":
                    extract_titles(value)
        elif isinstance(node, list):
            for item in node:
                extract_titles(item)

    extract_titles(section_hierarchy)
    return path
