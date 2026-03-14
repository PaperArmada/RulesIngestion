"""Determinism tests for Stage A (and Stage B) per v1 contract."""

from __future__ import annotations

import json

from extraction.ast_parser import parse_markdown_to_ast
from extraction.unit_identity import compute_evidence_unit_id


SAMPLE_MARKDOWN = """# Combat

When you take the Attack action, you can make one melee or ranged attack.

## Actions

Attack is the most common action.
"""


def test_stage_a_parse_determinism() -> None:
    """Same input -> byte-identical AST output (Stage A determinism)."""
    fp = "test_fp_123"
    ast1 = parse_markdown_to_ast(SAMPLE_MARKDOWN, fp)
    ast2 = parse_markdown_to_ast(SAMPLE_MARKDOWN, fp)
    json1 = json.dumps(ast1.to_dict(), sort_keys=True)
    json2 = json.dumps(ast2.to_dict(), sort_keys=True)
    assert json1 == json2
    assert ast1.content_hash == ast2.content_hash


def test_evidence_unit_id_is_deterministic_for_same_provenance() -> None:
    kwargs = {
        "text": "Attack is the most common action.",
        "structural_path": ["Combat", "Actions"],
        "page_fingerprint": "test_fp_123",
        "source_line_start": 5,
        "source_line_end": 5,
        "unit_type": "prose",
    }

    first_id = compute_evidence_unit_id(**kwargs)
    second_id = compute_evidence_unit_id(**kwargs)

    assert first_id == second_id


def test_evidence_unit_id_changes_when_structural_path_changes() -> None:
    base_kwargs = {
        "text": "Attack is the most common action.",
        "page_fingerprint": "test_fp_123",
        "source_line_start": 5,
        "source_line_end": 5,
        "unit_type": "prose",
    }

    first_id = compute_evidence_unit_id(
        structural_path=["Combat", "Actions"],
        **base_kwargs,
    )
    rebound_id = compute_evidence_unit_id(
        structural_path=["Rules", "Actions"],
        **base_kwargs,
    )

    assert first_id != rebound_id
