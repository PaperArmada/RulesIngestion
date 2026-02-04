from scripts import discover_deterministic_edges as dde
from scripts.discover_deterministic_edges_indexing import _build_section_header_index
from scripts.discover_deterministic_edges_candidates import _select_page_targets


def _chunk(
    chunk_id: str,
    text: str,
    *,
    block_type: str = "Text",
    content_kind: str = "",
    page: int | None = None,
    section_path: list[str] | None = None,
) -> dict:
    return {
        "id": chunk_id,
        "block_type": block_type,
        "content_kind": content_kind,
        "text": text,
        "page": page,
        "section_path": section_path or [],
    }


def test_extract_candidates_resolves_table_reference() -> None:
    doc_id = "doc"
    chunks = [
        _chunk(
            "doc/page/1/chunk/table-3-1",
            "Table 3-1: Combat Bonuses",
            block_type="Table",
            content_kind="table",
            page=1,
            section_path=["Tables", "Combat Bonuses"],
        ),
        _chunk(
            "doc/page/1/chunk/text-1",
            "See Table 3-1 for bonuses.",
            block_type="Text",
            page=1,
        ),
    ]
    indices = dde._build_indices(chunks, doc_id, page_offset=None)
    page_text_index = dde._build_page_text_index(chunks, page_offset=None)

    candidates, _ = dde._extract_candidates(chunks, doc_id, indices, page_text_index)

    table_candidates = [
        c for c in candidates if c.get("relation") == "references_table"
    ]
    assert table_candidates
    assert table_candidates[0]["resolution_count"] == 1
    assert table_candidates[0]["resolved_targets"] == ["doc/page/1/chunk/table-3-1"]


def test_extract_candidates_resolves_named_section_reference() -> None:
    doc_id = "doc"
    chunks = [
        _chunk(
            "doc/page/5/chunk/section-starship",
            "Starship Combat",
            block_type="SectionHeader",
            page=5,
            section_path=["Chapter 5", "Starship Combat"],
        ),
        _chunk(
            "doc/page/5/chunk/text-2",
            "As described in Starship Combat, apply these rules.",
            block_type="Text",
            page=5,
        ),
    ]
    indices = dde._build_indices(chunks, doc_id, page_offset=None)
    page_text_index = dde._build_page_text_index(chunks, page_offset=None)

    candidates, _ = dde._extract_candidates(chunks, doc_id, indices, page_text_index)

    section_candidates = [
        c for c in candidates if c.get("relation") == "references_named_section"
    ]
    assert section_candidates
    assert section_candidates[0]["resolution_count"] == 2
    assert set(section_candidates[0]["resolved_targets"]) == {
        "doc::heading::doc/page/5/chunk/section-starship",
        "doc::section::Chapter 5 > Starship Combat",
    }


def test_page_reference_prefers_heading_matching_cue_title() -> None:
    doc_id = "doc"
    chunks = [
        _chunk(
            "doc/page/12/chunk/section-damage",
            "Damage",
            block_type="SectionHeader",
            page=12,
            section_path=["Combat", "Damage"],
        ),
        _chunk(
            "doc/page/12/chunk/section-adjustments",
            "Damage Adjustments",
            block_type="SectionHeader",
            page=12,
            section_path=["Combat", "Damage Adjustments"],
        ),
        _chunk(
            "doc/page/5/chunk/text-3",
            "Damage (page 12) applies in this scenario.",
            block_type="Text",
            page=5,
        ),
    ]
    indices = dde._build_indices(chunks, doc_id, page_offset=None)
    page_text_index = dde._build_page_text_index(chunks, page_offset=None)

    candidates, _ = dde._extract_candidates(chunks, doc_id, indices, page_text_index)

    page_candidates = [
        c for c in candidates if c.get("relation") == "references_page"
    ]
    assert page_candidates
    assert page_candidates[0]["resolution_count"] == 1
    assert page_candidates[0]["resolved_targets"] == [
        "doc/page/12/chunk/section-damage"
    ]


def test_run_ocr_spelling_gates_reports_unresolved_rate() -> None:
    summary = dde._run_ocr_spelling_gates(
        candidates=[
            {
                "relation": "references_table",
                "resolution_count": 0,
            }
        ],
        indices={"section_exact": {}, "table": {}, "figure": {}, "chapter": {}},
        chunks=[_chunk("doc/page/1/chunk/text-4", "Regular text here.")],
        unresolved_rate_max=0.0,
        suspect_token_rate_max=1.0,
        near_duplicate_max=100,
        near_duplicate_rate_max=1.0,
        allow_gate_fail=True,
    )

    assert summary["gate_failures"]
    assert summary["unresolved_rate"] == 1.0


def test_extract_candidates_adds_defines_term_edge() -> None:
    doc_id = "doc"
    chunks = [
        _chunk(
            "doc/page/2/chunk/text-1",
            "Drift travel means faster-than-light travel.",
            block_type="Text",
            page=2,
        )
    ]
    indices = dde._build_indices(chunks, doc_id, page_offset=None)
    page_text_index = dde._build_page_text_index(chunks, page_offset=None)

    candidates, _ = dde._extract_candidates(chunks, doc_id, indices, page_text_index)

    term_candidates = [c for c in candidates if c.get("relation") == "defines_term"]
    assert term_candidates
    assert term_candidates[0]["resolution_count"] == 1
    assert term_candidates[0]["resolved_targets"] == ["canon:term:drift travel"]


def test_extract_candidates_adds_mentions_term_edge() -> None:
    doc_id = "doc"
    chunks = [
        _chunk(
            "doc/page/1/chunk/def-1",
            "Gravity well means a dense gravitational region.",
            block_type="Text",
            page=1,
        ),
        _chunk(
            "doc/page/1/chunk/text-2",
            "Ships avoid the gravity well when possible.",
            block_type="Text",
            page=1,
        ),
    ]
    indices = dde._build_indices(chunks, doc_id, page_offset=None)
    page_text_index = dde._build_page_text_index(chunks, page_offset=None)

    candidates, _ = dde._extract_candidates(chunks, doc_id, indices, page_text_index)

    mention_candidates = [c for c in candidates if c.get("relation") == "mentions_term"]
    assert mention_candidates
    assert mention_candidates[0]["resolved_targets"] == ["canon:term:gravity well"]


def test_extract_candidates_adds_in_section_edge() -> None:
    doc_id = "doc"
    chunks = [
        _chunk(
            "doc/page/1/chunk/header-1",
            "Faction Overview",
            block_type="SectionHeader",
            page=1,
            section_path=["Factions", "Faction Overview"],
        ),
        _chunk(
            "doc/page/1/chunk/text-2",
            "Faction rules live here.",
            block_type="Text",
            page=1,
            section_path=["Factions", "Faction Overview"],
        ),
    ]
    indices = dde._build_indices(chunks, doc_id, page_offset=None)
    page_text_index = dde._build_page_text_index(chunks, page_offset=None)
    section_header_index = _build_section_header_index(chunks)

    candidates, _ = dde._extract_candidates(
        chunks, doc_id, indices, page_text_index, section_header_index
    )

    section_candidates = [c for c in candidates if c.get("relation") == "in_section"]
    assert section_candidates
    assert section_candidates[0]["resolved_targets"] == ["doc/page/1/chunk/header-1"]


def test_select_page_targets_falls_back_to_single_heading() -> None:
    page_text_index = {
        "12": [
            ("chunk-a", "SectionHeader", "Quick Start", "Quick Start", "Quick Start"),
            ("chunk-b", "Text", None, None, "Random text"),
        ]
    }

    selected = _select_page_targets("12", page_text_index, "")

    assert selected == ["chunk-a"]
