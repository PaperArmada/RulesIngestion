"""
Legacy gate helpers used by chunker (Stage A / MarkerStream path).
_weird_ratio: proportion of non-alphanumeric / non-printable chars (M-A8 style).
"""

from __future__ import annotations


def _weird_ratio(text: str) -> float:
    """Non-printable or symbol chars / total chars. Used for table-like recategorization."""
    if not text:
        return 0.0
    total = len(text)
    weird = 0
    for c in text:
        if not c.isalnum() and not c.isspace() and ord(c) < 128:
            weird += 1
        elif ord(c) >= 128 or not c.isprintable():
            weird += 1
    return weird / total
