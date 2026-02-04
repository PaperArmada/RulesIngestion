from __future__ import annotations

import re


def _normalize_label(label: str) -> str:
    if not label:
        return ""
    cleaned = label.replace("–", "-").replace("—", "-")
    cleaned = re.sub(r"[\s]+", " ", cleaned.strip())
    cleaned = cleaned.strip(" .,:;()[]{}")
    return cleaned.lower()


def _normalize_title(title: str) -> str:
    cleaned = title.replace("–", "-").replace("—", "-")
    cleaned = re.sub(r"[`*_]+", "", cleaned)
    cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
    cleaned = re.sub(r"^\s*[\-\*•\d\.\)]*\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned.strip())
    cleaned = cleaned.strip(" .,:;()[]{}")
    return cleaned.lower()


def _strip_heading_numbers(title: str) -> str:
    if not title:
        return ""
    return re.sub(r"^\s*(?:\d+|[IVXLC]+)(?:[\.\-–]\d+)*\s*", "", title).strip()


def _build_anchor_variants(base: str, include_section: bool = True) -> list[str]:
    normalized = _normalize_title(base)
    if not normalized:
        return []
    anchors = {normalized}
    if include_section:
        anchors.add(f"{normalized} section")
        anchors.add(f"the {normalized} section")
        anchors.add(f"{normalized} rules")
        anchors.add(f"rules for {normalized}")
    return sorted(anchors)


def _extract_heading_text(text: str) -> str:
    if not text:
        return ""
    line = text.splitlines()[0].strip()
    line = re.sub(r"^[#\s]+", "", line)
    line = line.replace("**", "").strip()
    return line


def _extract_page_cue_title(text: str) -> str:
    if not text:
        return ""
    candidate = re.sub(
        r"\(.*?page[s]?\s+\d{1,4}.*?\)", "", text, flags=re.IGNORECASE
    )
    candidate = re.sub(
        r"\bpage[s]?\s+\d{1,4}\b", "", candidate, flags=re.IGNORECASE
    )
    candidate = candidate.strip().strip("-–—:,;.")
    if "[" in candidate:
        candidate = candidate.split("[", 1)[0].strip()
    if "—" in candidate:
        candidate = candidate.split("—", 1)[0].strip()
    if "–" in candidate:
        candidate = candidate.split("–", 1)[0].strip()
    return candidate


def _clean_page_cue_title(candidate: str) -> str:
    if not candidate:
        return ""
    cleaned = re.sub(r"[`*_]+", "", candidate)
    cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
    cleaned = cleaned.strip().strip("-–—:;,.()[]")
    cleaned = re.sub(r"^\s*[\-\*•\d\.\)]*\s*", "", cleaned)
    cleaned = re.sub(
        r"^\s*(?:optionally\s*,?\s*)?"
        r"(?:add|apply|grant|give|increase|decrease|reduce|choose|select|use)\b\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:see|refer to|as described in|as detailed in)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip().strip("-–—:;,.()[]")
    cleaned = re.sub(r"\[[^\]]+\]", "", cleaned).strip()
    return cleaned


def _extract_page_cue_title_from_match(text: str, match: re.Match) -> str:
    if not text:
        return ""
    start = match.start()
    line_start = text.rfind("\n", 0, start)
    line_start = 0 if line_start == -1 else line_start + 1
    line_end = text.find("\n", start)
    line_end = len(text) if line_end == -1 else line_end
    line = text[line_start:line_end]
    line_prefix = line[: max(0, start - line_start)]
    candidate = _clean_page_cue_title(line_prefix)
    if candidate:
        return candidate
    return _clean_page_cue_title(_extract_page_cue_title(text))


def _trim_label_suffixes(label: str) -> list[str]:
    if not label:
        return []
    lowered = label.lower()
    cut_tokens = [" for ", " to ", " of ", " in ", " with ", " on "]
    candidates: set[str] = set()
    for token in cut_tokens:
        if token in lowered:
            prefix = label[: lowered.index(token)].strip()
            if prefix:
                candidates.add(prefix)
            break
    return sorted(candidates)
