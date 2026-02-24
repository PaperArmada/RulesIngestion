"""Tests for extraction.toc_binder — unit binding, page ranges, table caption binding."""

from __future__ import annotations

from extraction.schemas import EvidenceUnit
from extraction.toc_binder import (
    _find_deepest_covering_node,
    _bind_table_captions,
    bind_units_to_toc,
)
from extraction.toc_parser import TocNode, compute_page_ranges


def _unit(
    unit_id: str,
    *,
    text: str = "some text",
    structural_path: list[str] | None = None,
    page_fingerprint: str = "fp-1",
    unit_type: str = "prose",
    ordering_key: int = 0,
    anomaly_flags: list[str] | None = None,
    join_metadata: dict | None = None,
) -> EvidenceUnit:
    return EvidenceUnit(
        unit_id=unit_id,
        unit_type=unit_type,  # type: ignore[arg-type]
        text=text,
        structural_path=structural_path or [],
        ordering_key=ordering_key,
        page_fingerprint=page_fingerprint,
        content_hash="h",
        source_line_start=0,
        source_line_end=1,
        anomaly_flags=anomaly_flags or [],
        join_metadata=join_metadata,
    )


# ---------------------------------------------------------------------------
# _find_deepest_covering_node
# ---------------------------------------------------------------------------

def _make_swcr_tree() -> list[TocNode]:
    """Minimal SWCR-like tree: Player Guide > Choose a Character Class > Cleric."""
    cleric = TocNode("Cleric", page_num=10, depth=2)
    fighter = TocNode("Fighter", page_num=15, depth=2)
    choose_class = TocNode("Choose a Character Class", page_num=8, depth=1, children=[cleric, fighter])
    player_guide = TocNode("Player Guide", page_num=5, depth=0, children=[choose_class])
    spells = TocNode("Spells & Magic", page_num=49, depth=0)
    nodes = [player_guide, spells]
    compute_page_ranges(nodes, total_pages=100)
    return nodes


def test_deepest_covering_node_cleric():
    tree = _make_swcr_tree()
    path = _find_deepest_covering_node(11, tree)
    assert path == ["Player Guide", "Choose a Character Class", "Cleric"]


def test_deepest_covering_node_fighter():
    tree = _make_swcr_tree()
    path = _find_deepest_covering_node(15, tree)
    assert path == ["Player Guide", "Choose a Character Class", "Fighter"]


def test_deepest_covering_node_top_level():
    tree = _make_swcr_tree()
    path = _find_deepest_covering_node(50, tree)
    assert path == ["Spells & Magic"]


def test_deepest_covering_node_no_match():
    tree = _make_swcr_tree()
    path = _find_deepest_covering_node(3, tree)
    assert path is None


def test_deepest_covering_node_boundary():
    tree = _make_swcr_tree()
    path_start = _find_deepest_covering_node(10, tree)
    assert path_start == ["Player Guide", "Choose a Character Class", "Cleric"]

    path_end = _find_deepest_covering_node(14, tree)
    assert path_end == ["Player Guide", "Choose a Character Class", "Cleric"]


# ---------------------------------------------------------------------------
# bind_units_to_toc
# ---------------------------------------------------------------------------

def test_bind_units_basic():
    tree = _make_swcr_tree()
    fp_to_page = {"fp-cleric": 11, "fp-spells": 50}
    units = [
        _unit("u1", page_fingerprint="fp-cleric", structural_path=[], anomaly_flags=["no_heading_parent"]),
        _unit("u2", page_fingerprint="fp-spells", structural_path=["Spells"]),
    ]

    enriched, bindings = bind_units_to_toc(units, tree, fp_to_page)

    assert len(enriched) == 2
    assert enriched[0].structural_path == ["Player Guide", "Choose a Character Class", "Cleric"]
    assert "toc_structural_path" in enriched[0].anomaly_flags
    assert "no_heading_parent" not in enriched[0].anomaly_flags
    assert enriched[0].join_metadata["original_structural_path"] == []
    assert enriched[0].join_metadata["toc_bound"] is True

    assert enriched[1].structural_path == ["Spells & Magic", "Spells"]
    assert enriched[1].join_metadata["original_structural_path"] == ["Spells"]


def test_bind_units_no_page_mapping():
    tree = _make_swcr_tree()
    fp_to_page = {}
    units = [_unit("u1", page_fingerprint="unknown-fp")]

    enriched, bindings = bind_units_to_toc(units, tree, fp_to_page)

    assert len(enriched) == 1
    assert enriched[0].structural_path == []
    binding_status = [b["status"] for b in bindings]
    assert "no_page_mapping" in binding_status


def test_bind_units_no_toc_coverage():
    tree = _make_swcr_tree()
    fp_to_page = {"fp-frontmatter": 2}
    units = [_unit("u1", page_fingerprint="fp-frontmatter")]

    enriched, bindings = bind_units_to_toc(units, tree, fp_to_page)

    assert len(enriched) == 1
    assert enriched[0].structural_path == []
    binding_status = [b["status"] for b in bindings]
    assert "no_toc_coverage" in binding_status


def test_bind_preserves_existing_heading_not_in_toc():
    """If a unit has a structural_path element not in the TOC, it gets appended."""
    tree = _make_swcr_tree()
    fp_to_page = {"fp-cleric": 11}
    units = [
        _unit("u1", page_fingerprint="fp-cleric", structural_path=["Cleric Spells"]),
    ]

    enriched, _ = bind_units_to_toc(units, tree, fp_to_page)

    assert enriched[0].structural_path[-1] == "Cleric Spells"
    assert enriched[0].structural_path[:-1] == ["Player Guide", "Choose a Character Class", "Cleric"]


def test_bind_does_not_duplicate_existing_toc_heading():
    """If the existing heading matches a TOC node, don't duplicate it."""
    tree = _make_swcr_tree()
    fp_to_page = {"fp-cleric": 11}
    units = [
        _unit("u1", page_fingerprint="fp-cleric", structural_path=["Cleric"]),
    ]

    enriched, _ = bind_units_to_toc(units, tree, fp_to_page)

    assert enriched[0].structural_path == ["Player Guide", "Choose a Character Class", "Cleric"]


def test_bind_recomputes_unit_id():
    tree = _make_swcr_tree()
    fp_to_page = {"fp-cleric": 11}
    units = [
        _unit("old-id", page_fingerprint="fp-cleric", structural_path=[]),
    ]

    enriched, _ = bind_units_to_toc(units, tree, fp_to_page)

    assert enriched[0].unit_id != "old-id"


# ---------------------------------------------------------------------------
# Table caption binding
# ---------------------------------------------------------------------------

def test_table_caption_binding():
    units = [
        _unit("u-caption", text="Cleric Advancement Table", page_fingerprint="fp1", ordering_key=0),
        _unit("u-table", text="<table><tr><td>1</td></tr></table>", unit_type="table", page_fingerprint="fp1", ordering_key=1),
    ]

    bindings = _bind_table_captions(units)

    assert len(bindings) == 1
    assert bindings[0]["table_title"] == "Cleric Advancement Table"
    assert units[1].join_metadata is not None
    assert units[1].join_metadata["table_title"] == "Cleric Advancement Table"


def test_table_caption_not_bound_if_long():
    long_text = "A" * 100
    units = [
        _unit("u-caption", text=long_text, page_fingerprint="fp1", ordering_key=0),
        _unit("u-table", text="<table><tr><td>1</td></tr></table>", unit_type="table", page_fingerprint="fp1", ordering_key=1),
    ]

    bindings = _bind_table_captions(units)
    assert len(bindings) == 0


def test_table_caption_not_bound_across_pages():
    units = [
        _unit("u-caption", text="Table Title", page_fingerprint="fp1", ordering_key=0),
        _unit("u-table", text="<table><tr><td>1</td></tr></table>", unit_type="table", page_fingerprint="fp2", ordering_key=1),
    ]

    bindings = _bind_table_captions(units)
    assert len(bindings) == 0


def test_table_caption_first_unit_table_no_bind():
    units = [
        _unit("u-table", text="<table><tr><td>1</td></tr></table>", unit_type="table", page_fingerprint="fp1", ordering_key=0),
    ]

    bindings = _bind_table_captions(units)
    assert len(bindings) == 0


# ---------------------------------------------------------------------------
# Gate tests for TOC coverage and orphan-after-toc
# ---------------------------------------------------------------------------

def test_gate_toc_binding_coverage():
    from extraction.gates_b import gate_toc_binding_coverage

    units = [
        _unit("u1", anomaly_flags=["toc_structural_path"]),
        _unit("u2", anomaly_flags=["toc_structural_path"]),
        _unit("u3", anomaly_flags=[]),
    ]
    diag = gate_toc_binding_coverage(units)
    assert diag.passed is True
    assert abs(diag.detail["coverage"] - 0.6667) < 0.01


def test_gate_toc_binding_coverage_fails_low():
    from extraction.gates_b import gate_toc_binding_coverage

    units = [
        _unit("u1", anomaly_flags=["toc_structural_path"]),
        _unit("u2", anomaly_flags=[]),
        _unit("u3", anomaly_flags=[]),
        _unit("u4", anomaly_flags=[]),
        _unit("u5", anomaly_flags=[]),
    ]
    diag = gate_toc_binding_coverage(units, fail_threshold=0.50)
    assert diag.passed is False


def test_gate_orphan_after_toc():
    from extraction.gates_b import gate_orphan_after_toc

    units = [
        _unit("u1", structural_path=["Ch1"]),
        _unit("u2", structural_path=["Ch2"]),
        _unit("u3", structural_path=[]),
    ]
    diag = gate_orphan_after_toc(units, fail_threshold=0.50)
    assert diag.passed is True
    assert abs(diag.detail["orphan_rate"] - 0.3333) < 0.01


def test_gate_orphan_after_toc_fails_high():
    from extraction.gates_b import gate_orphan_after_toc

    units = [
        _unit("u1", structural_path=[]),
        _unit("u2", structural_path=[]),
        _unit("u3", structural_path=["Ch1"]),
    ]
    diag = gate_orphan_after_toc(units, fail_threshold=0.50)
    assert diag.passed is False
