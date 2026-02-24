"""Tests for extraction.toc_parser — TOC detection, flat entry extraction, and hierarchy reconstruction."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from extraction.toc_parser import (
    TocEntry,
    TocNode,
    _build_tree_from_parsed,
    _parse_entry_lines,
    _parse_hierarchy_response,
    _score_toc_page,
    build_flat_hierarchy,
    compute_page_ranges,
    detect_toc_pages,
    write_toc_artifacts,
    TocDetectionResult,
)


# ---------------------------------------------------------------------------
# _score_toc_page
# ---------------------------------------------------------------------------

_SAMPLE_TOC_MD = textwrap.dedent("""\
    ## TABLE OF CONTENTS

    Player Guide ..... 5
    Creating a Character ..... 5
    Roll Attribute Scores ..... 6
    Choose a Character Class ..... 8
    Assassin ..... 8
    Cleric ..... 10
    Fighter ..... 15
    Magic-User ..... 16
    Spells & Magic ..... 49
""")


def test_score_toc_page_high_score():
    score, entry_lines = _score_toc_page(_SAMPLE_TOC_MD)
    assert score >= 0.7, f"Expected >=0.7, got {score}"
    assert len(entry_lines) >= 5


def test_score_toc_page_no_toc():
    normal_page = "This is a normal page.\n\nSome content about fighters.\n\nMore text."
    score, entry_lines = _score_toc_page(normal_page)
    assert score < 0.5
    assert len(entry_lines) == 0


def test_score_toc_page_heading_only():
    heading_only = "## TABLE OF CONTENTS\n\nNo entries here, just some text."
    score, _ = _score_toc_page(heading_only)
    assert score == 0.5


def test_score_toc_page_with_ast():
    ast_dict = {
        "root": {
            "children": [
                {"node_type": "heading", "text": "Table of Contents"},
            ]
        }
    }
    score, _ = _score_toc_page("Just plain text, no headings", ast_dict)
    assert score >= 0.5


# ---------------------------------------------------------------------------
# _parse_entry_lines
# ---------------------------------------------------------------------------

def test_parse_entry_lines_dotted():
    lines = [
        "Player Guide ..... 5",
        "Creating a Character ..... 5",
        "Cleric ..... 10",
    ]
    entries = _parse_entry_lines(lines)
    assert len(entries) == 3
    assert entries[0].title == "Player Guide"
    assert entries[0].page_num == 5
    assert entries[2].title == "Cleric"
    assert entries[2].page_num == 10


def test_parse_entry_lines_dash():
    lines = [
        "Introduction -- 1",
        "Chapter One --- 5",
    ]
    entries = _parse_entry_lines(lines)
    assert len(entries) == 2
    assert entries[0].title == "Introduction"
    assert entries[0].page_num == 1


def test_parse_entry_lines_dedup():
    lines = [
        "Player Guide ..... 5",
        "Player Guide ..... 5",
    ]
    entries = _parse_entry_lines(lines)
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# detect_toc_pages (filesystem-based)
# ---------------------------------------------------------------------------

def test_detect_toc_pages_finds_toc(tmp_path):
    stem = "TestBook"
    page_dir = tmp_path / f"{stem}_p1"
    page_dir.mkdir()
    page_data = {
        "page_fingerprint": "fp1",
        "source_pdf": "test.pdf",
        "page_index": 1,
        "raw_markdown": _SAMPLE_TOC_MD,
    }
    (page_dir / "stageA.page.json").write_text(json.dumps(page_data))

    result = detect_toc_pages(tmp_path, stem, max_scan_pages=5)
    assert result.found is True
    assert result.score >= 0.7
    assert 1 in result.toc_pages
    assert len(result.entries) >= 5


def test_detect_toc_pages_no_match(tmp_path):
    stem = "TestBook"
    page_dir = tmp_path / f"{stem}_p0"
    page_dir.mkdir()
    page_data = {
        "page_fingerprint": "fp0",
        "source_pdf": "test.pdf",
        "page_index": 0,
        "raw_markdown": "Just a cover page with no TOC patterns.",
    }
    (page_dir / "stageA.page.json").write_text(json.dumps(page_data))

    result = detect_toc_pages(tmp_path, stem, max_scan_pages=5)
    assert result.found is False


# ---------------------------------------------------------------------------
# Hierarchy reconstruction
# ---------------------------------------------------------------------------

_FLAT_ENTRIES = [
    TocEntry("Player Guide", 5),
    TocEntry("Creating a Character", 5),
    TocEntry("Cleric", 10),
    TocEntry("Fighter", 15),
    TocEntry("Spells & Magic", 49),
]


def test_parse_hierarchy_response_valid():
    response = textwrap.dedent("""\
        Player Guide -- 5
          Creating a Character -- 5
          Cleric -- 10
          Fighter -- 15
        Spells & Magic -- 49
    """)
    nodes = _parse_hierarchy_response(response, _FLAT_ENTRIES)
    assert nodes is not None
    assert len(nodes) == 2
    assert nodes[0].title == "Player Guide"
    assert len(nodes[0].children) == 3
    assert nodes[0].children[1].title == "Cleric"
    assert nodes[1].title == "Spells & Magic"


def test_parse_hierarchy_response_rejects_extra_entry():
    response = textwrap.dedent("""\
        Player Guide -- 5
          Creating a Character -- 5
          Cleric -- 10
          Fighter -- 15
        Spells & Magic -- 49
        Hallucinated Entry -- 99
    """)
    result = _parse_hierarchy_response(response, _FLAT_ENTRIES)
    assert result is None


def test_parse_hierarchy_response_rejects_missing_entry():
    response = textwrap.dedent("""\
        Player Guide -- 5
          Creating a Character -- 5
          Cleric -- 10
        Spells & Magic -- 49
    """)
    result = _parse_hierarchy_response(response, _FLAT_ENTRIES)
    assert result is None


def test_parse_hierarchy_response_rejects_duplicate():
    response = textwrap.dedent("""\
        Player Guide -- 5
          Creating a Character -- 5
          Cleric -- 10
          Cleric -- 10
          Fighter -- 15
        Spells & Magic -- 49
    """)
    result = _parse_hierarchy_response(response, _FLAT_ENTRIES)
    assert result is None


def test_build_flat_hierarchy():
    nodes = build_flat_hierarchy(_FLAT_ENTRIES)
    assert len(nodes) == 5
    assert all(n.depth == 0 for n in nodes)
    assert all(len(n.children) == 0 for n in nodes)


# ---------------------------------------------------------------------------
# Page range computation
# ---------------------------------------------------------------------------

def test_compute_page_ranges_simple():
    nodes = [
        TocNode("Ch1", page_num=0, depth=0),
        TocNode("Ch2", page_num=10, depth=0),
        TocNode("Ch3", page_num=20, depth=0),
    ]
    compute_page_ranges(nodes, total_pages=30)
    assert nodes[0].page_end == 9
    assert nodes[1].page_end == 19
    assert nodes[2].page_end == 29


def test_compute_page_ranges_nested():
    child1 = TocNode("S1.1", page_num=2, depth=1)
    child2 = TocNode("S1.2", page_num=5, depth=1)
    parent = TocNode("Ch1", page_num=0, depth=0, children=[child1, child2])
    ch2 = TocNode("Ch2", page_num=10, depth=0)
    nodes = [parent, ch2]
    compute_page_ranges(nodes, total_pages=20)
    assert parent.page_end == 9
    assert child1.page_end == 4
    assert child2.page_end == 9
    assert ch2.page_end == 19


# ---------------------------------------------------------------------------
# _build_tree_from_parsed
# ---------------------------------------------------------------------------

def test_build_tree_from_parsed():
    parsed = [
        (0, "Ch1", 1),
        (1, "S1.1", 2),
        (1, "S1.2", 5),
        (0, "Ch2", 10),
    ]
    tree = _build_tree_from_parsed(parsed)
    assert len(tree) == 2
    assert tree[0].title == "Ch1"
    assert len(tree[0].children) == 2
    assert tree[0].children[0].title == "S1.1"
    assert tree[1].title == "Ch2"


# ---------------------------------------------------------------------------
# Artifact I/O
# ---------------------------------------------------------------------------

def test_write_toc_artifacts(tmp_path):
    detection = TocDetectionResult(
        found=True,
        score=0.9,
        toc_pages=[1],
        method="deterministic",
        entries=[TocEntry("Ch1", 5, "Ch1 ..... 5")],
        confidence="high",
    )
    tree = [TocNode("Ch1", page_num=5, page_end=20, depth=0)]
    write_toc_artifacts(tmp_path, detection, tree, "llm")

    assert (tmp_path / "toc_detection.json").exists()
    assert (tmp_path / "toc_entries.json").exists()
    assert (tmp_path / "toc_tree.json").exists()

    det = json.loads((tmp_path / "toc_detection.json").read_text())
    assert det["found"] is True
    assert det["entry_count"] == 1

    tree_data = json.loads((tmp_path / "toc_tree.json").read_text())
    assert tree_data["node_count"] == 1
    assert tree_data["hierarchy_method"] == "llm"


# ---------------------------------------------------------------------------
# TocNode serialization round-trip
# ---------------------------------------------------------------------------

def test_toc_node_round_trip():
    child = TocNode("S1", page_num=3, page_end=8, depth=1)
    node = TocNode("Ch1", page_num=1, page_end=10, depth=0, children=[child])
    d = node.to_dict()
    restored = TocNode.from_dict(d)
    assert restored.title == "Ch1"
    assert restored.page_num == 1
    assert restored.page_end == 10
    assert len(restored.children) == 1
    assert restored.children[0].title == "S1"


def test_toc_entry_round_trip():
    entry = TocEntry("Test", 42, "Test ..... 42")
    d = entry.to_dict()
    restored = TocEntry.from_dict(d)
    assert restored.title == "Test"
    assert restored.page_num == 42
    assert restored.raw_line == "Test ..... 42"
