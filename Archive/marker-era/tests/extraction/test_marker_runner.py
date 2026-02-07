"""Tests for extraction.marker_runner: flatten, sort, MarkerStream."""

from extraction.marker_runner import (
    blocks_to_marker_stream,
    flatten_marker_tree,
    raw_to_blocks,
)
from extraction.schemas import MarkerBlock


def test_raw_to_blocks_list() -> None:
    raw = [{"block_type": "Text", "html": "<p>x</p>"}]
    assert len(raw_to_blocks(raw)) == 1


def test_raw_to_blocks_children() -> None:
    raw = {
        "children": [
            {"block_type": "Text", "html": "<p>a</p>"},
            {"block_type": "Title", "html": "<h1>b</h1>"},
        ],
    }
    blocks = raw_to_blocks(raw)
    assert len(blocks) == 2
    # Physical page inferred from top-level child index (avoids chapter-vs-page confusion).
    assert blocks[0].get("page") == 0
    assert blocks[1].get("page") == 1


def test_flatten_marker_tree() -> None:
    node = {
        "block_type": "Text",
        "html": "<p>root</p>",
        "children": [
            {"block_type": "Text", "html": "<p>child</p>"},
        ],
    }
    out = flatten_marker_tree(node)
    assert len(out) == 2
    assert any("root" in (b.get("html") or "") for b in out)
    assert any("child" in (b.get("html") or "") for b in out)


def test_blocks_to_marker_stream_sort() -> None:
    blocks = [
        {"block_type": "Text", "html": "<p>page1</p>", "page": 1, "bbox": [0, 10, 10, 20]},
        {"block_type": "Text", "html": "<p>page0</p>", "page": 0, "bbox": [0, 0, 10, 10]},
    ]
    stream = blocks_to_marker_stream(blocks, "doc1")
    assert len(stream) == 2
    assert stream[0].page_index <= stream[1].page_index
    assert stream[0].doc_id == "doc1"
    assert stream[0].block_ordinal in (0, 1)


def test_blocks_to_marker_stream_block_ordinal_per_page() -> None:
    blocks = [
        {"block_type": "Text", "html": "<p>a</p>", "page": 0},
        {"block_type": "Text", "html": "<p>b</p>", "page": 0},
        {"block_type": "Text", "html": "<p>c</p>", "page": 1},
    ]
    stream = blocks_to_marker_stream(blocks, "doc1")
    pages = [b.page_index for b in stream]
    ordinals = [b.block_ordinal for b in stream]
    assert stream[0].block_ordinal == 0
    assert stream[1].block_ordinal == 1
    assert stream[2].block_ordinal == 0  # first on page 1
