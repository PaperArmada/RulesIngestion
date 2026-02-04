from __future__ import annotations

import re

CUE_KEYWORDS = [
    "see ",
    "refer to ",
    "as described in ",
    "as detailed in ",
    "defined as",
    "means ",
    "except as noted in ",
    "unless otherwise stated in ",
    "table ",
    "chapter ",
    "figure ",
]

REFERENCE_PATTERNS = [
    {
        "relation": "references_table",
        "target_type": "table",
        "regex": re.compile(
            r"\b(?:see|refer to|as described in|as detailed in|see also)?\s*"
            r"(?:Table|TABLE)\s+(?P<label>[A-Za-z]?\d+(?:[.\-–]\d+)*)",
            re.IGNORECASE,
        ),
    },
    {
        "relation": "references_figure",
        "target_type": "figure",
        "regex": re.compile(
            r"\b(?:see|refer to|as described in|as detailed in|see also)?\s*"
            r"(?:Figure|FIGURE)\s+(?P<label>[A-Za-z]?\d+(?:[.\-–]\d+)*)",
            re.IGNORECASE,
        ),
    },
    {
        "relation": "references_chapter",
        "target_type": "chapter",
        "regex": re.compile(
            r"\b(?:see|refer to|as described in|as detailed in|in)\s*"
            r"(?:Chapter|CHAPTER)\s+(?P<label>(?:\d+|[IVXLC]+))",
            re.IGNORECASE,
        ),
    },
    {
        "relation": "references_section",
        "target_type": "section",
        "regex": re.compile(
            r"\b(?:see|refer to|as described in|as detailed in|see also)\b\s*"
            r"(?:the\s+)?(?P<label>[A-Z][A-Za-z0-9][A-Za-z0-9 \-]{2,80})"
            r"(?:\s+(?P<section_word>section))?\b",
            re.IGNORECASE,
        ),
    },
    {
        "relation": "references_page",
        "target_type": "page",
        "regex": re.compile(
            r"\b(?:see|refer to|as described in|as detailed in)?\s*"
            r"(?:page|pages)\s+(?P<label>\d{1,4})\b",
            re.IGNORECASE,
        ),
    },
    {
        "relation": "defines_term",
        "target_type": "term",
        "regex": re.compile(
            r"\b(?P<label>[A-Z][A-Za-z0-9'’\- ]{2,60})\b\s+"
            r"(?:means|refers to|is defined as|is called)\b",
            re.IGNORECASE,
        ),
    },
]

STRICT_RELATIONS = {
    "references_named_section",
    "references_table",
    "references_figure",
    "references_chapter",
    "references_page",
}

DEFAULT_UNRESOLVED_RATE_MAX = 0.35
DEFAULT_SUSPECT_TOKEN_RATE_MAX = 0.02
DEFAULT_SUSPECT_TOKEN_MIN_TOKENS = 200
DEFAULT_NEAR_DUPLICATE_MAX = 12
DEFAULT_NEAR_DUPLICATE_RATE_MAX = 0.02
MAX_NEAR_DUPLICATE_SAMPLES = 25
