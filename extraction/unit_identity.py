from __future__ import annotations

import blake3


def compute_evidence_unit_id(
    *,
    text: str,
    structural_path: list[str],
    page_fingerprint: str,
    source_line_start: int,
    source_line_end: int,
    unit_type: str,
) -> str:
    """Build a deterministic, corpus-safe EvidenceUnit identity.

    The text/path pair alone is not unique at corpus scale because repeated
    boilerplate can legitimately recur under the same heading path. Including
    page-local provenance keeps the ID stable for a fixed Stage A/B realization
    while eliminating those collisions.
    """
    path_str = " > ".join(structural_path)
    payload = "\n".join(
        (
            page_fingerprint,
            str(source_line_start),
            str(source_line_end),
            unit_type,
            path_str,
            text,
        )
    )
    return blake3.blake3(payload.encode("utf-8")).hexdigest()
