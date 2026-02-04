"""Ruleset profiling utilities."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from enrichment import extract_text_from_html

MONGODB_URI_ENV = "MONGODB_URI"
DEFAULT_MONGODB_URI = "mongodb://localhost:27017"


def resolve_mongo_uri(mongo_uri: Optional[str] = None) -> str:
    """Resolve MongoDB URI from argument or environment."""
    if mongo_uri:
        return mongo_uri
    return os.getenv(MONGODB_URI_ENV, DEFAULT_MONGODB_URI)


class RulesetProfile(BaseModel):
    """Summary of a chapter's parsed structure."""

    ruleset_id: str
    doc_signature: str
    heading_hierarchy: List[str]
    noise_headings: List[str] = Field(default_factory=list)
    block_type_distribution: Dict[str, int]
    samples: Optional[List[str]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def compute_doc_signature(
    heading_hierarchy: List[str], block_type_distribution: Dict[str, int]
) -> str:
    """Compute stable signature from heading hierarchy and block distribution."""

    payload = {
        "heading_hierarchy": heading_hierarchy,
        "block_type_distribution": block_type_distribution,
    }
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


NOISE_HEADING_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\bglossary\b", re.IGNORECASE),
    re.compile(r"\bindex\b", re.IGNORECASE),
    re.compile(r"\bpaizo\b", re.IGNORECASE),
    re.compile(r"\borc notice\b", re.IGNORECASE),
    re.compile(r"\blicen[sc]e\b", re.IGNORECASE),
    re.compile(r"\bcopyright\b", re.IGNORECASE),
    re.compile(r"\blegal\b", re.IGNORECASE),
    re.compile(r"\bavailable\b", re.IGNORECASE),
    re.compile(r"\badvertisement\b", re.IGNORECASE),
    re.compile(r"\bcredits?\b", re.IGNORECASE),
    re.compile(r"\backnowledg", re.IGNORECASE),
)
MAX_SAMPLE_CHARS = 400


def _normalize_heading(text: str) -> str:
    cleaned = re.sub(r"[*_`]+", "", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _is_noise_heading(text: str) -> bool:
    if not text:
        return True
    normalized = _normalize_heading(text)
    if not normalized:
        return True
    return any(pattern.search(normalized) for pattern in NOISE_HEADING_PATTERNS)


def _truncate_sample(text: str) -> str:
    if len(text) <= MAX_SAMPLE_CHARS:
        return text
    return text[:MAX_SAMPLE_CHARS].rstrip()


def _select_samples(
    candidates: Sequence[Tuple[int, str]],
    total_blocks: int,
    sample_size: int,
) -> List[str]:
    if not candidates or sample_size <= 0:
        return []

    early: List[Tuple[int, str]] = []
    mid: List[Tuple[int, str]] = []
    late: List[Tuple[int, str]] = []
    for index, text in candidates:
        ratio = index / max(total_blocks - 1, 1)
        if ratio < 0.34:
            early.append((index, text))
        elif ratio < 0.67:
            mid.append((index, text))
        else:
            late.append((index, text))

    selected: List[Tuple[int, str]] = []
    for bucket in (early, mid, late):
        if bucket and len(selected) < sample_size:
            selected.append(bucket[0])

    if len(selected) < sample_size:
        for candidate in sorted(candidates, key=lambda item: item[0]):
            if candidate not in selected:
                selected.append(candidate)
                if len(selected) >= sample_size:
                    break

    return [_truncate_sample(text) for _, text in selected[:sample_size]]


def build_ruleset_profile(
    raw_blocks: List[Dict[str, Any]],
    ruleset_id: str,
    sample_size: int = 5,
) -> RulesetProfile:
    heading_hierarchy: List[str] = []
    noise_headings: List[str] = []
    block_type_distribution: Dict[str, int] = {}
    candidates_core: List[Tuple[int, str]] = []
    candidates_all: List[Tuple[int, str]] = []

    current_section_is_core: Optional[bool] = None

    for index, block in enumerate(raw_blocks):
        block_type = block.get("block_type", "Unknown")
        html = block.get("html", "") if isinstance(block, dict) else ""

        if block_type == "SectionHeader" and html:
            heading_text = extract_text_from_html(html).strip()
            if heading_text:
                if _is_noise_heading(heading_text):
                    noise_headings.append(heading_text)
                    current_section_is_core = False
                else:
                    heading_hierarchy.append(heading_text)
                    current_section_is_core = True

        if current_section_is_core:
            block_type_distribution[block_type] = block_type_distribution.get(block_type, 0) + 1

        if html:
            text = extract_text_from_html(html).strip()
            if text:
                candidates_all.append((index, text))
                if current_section_is_core:
                    candidates_core.append((index, text))

    sample_candidates = candidates_core if candidates_core else candidates_all
    samples = _select_samples(sample_candidates, len(raw_blocks), sample_size)
    doc_signature = compute_doc_signature(heading_hierarchy, block_type_distribution)

    return RulesetProfile(
        ruleset_id=ruleset_id,
        doc_signature=doc_signature,
        heading_hierarchy=heading_hierarchy,
        noise_headings=noise_headings,
        block_type_distribution=block_type_distribution,
        samples=samples,
    )


def evaluate_profile_quality(
    profile: RulesetProfile,
    min_core_headings: int = 3,
    min_samples: int = 2,
) -> List[str]:
    errors: List[str] = []
    core_count = len(profile.heading_hierarchy)
    noise_count = len(profile.noise_headings)
    if core_count < min_core_headings:
        errors.append(f"core headings below threshold ({core_count} < {min_core_headings})")
    if noise_count > core_count:
        errors.append("noise headings outnumber core headings")
    section_headers = profile.block_type_distribution.get("SectionHeader", 0)
    if section_headers <= 0:
        errors.append("no SectionHeader blocks in core distribution")
    if not profile.samples or len(profile.samples) < min_samples:
        errors.append("insufficient core samples for prompt grounding")
    return errors


def detect_structure_drift(base: RulesetProfile, candidate: RulesetProfile) -> bool:
    """Drift requires both heading hierarchy and block distribution changes."""
    headings_changed = base.heading_hierarchy != candidate.heading_hierarchy
    distribution_changed = base.block_type_distribution != candidate.block_type_distribution
    if headings_changed and not distribution_changed:
        print("🧭 Low drift detected (headings changed, distribution stable).")
    return headings_changed and distribution_changed
