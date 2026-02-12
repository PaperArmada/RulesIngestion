"""Determinism tests for Stage A (and Stage B) per v1 contract."""

from __future__ import annotations

import json
import pytest

from extraction.ast_parser import parse_markdown_to_ast


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
