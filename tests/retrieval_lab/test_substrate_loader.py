from __future__ import annotations

import json

from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_units_by_heading,
)


def test_load_evidence_units_from_minimal_fixture(substrate_minimal_path) -> None:
    corpus = load_evidence_units(substrate_minimal_path, "TestDoc")
    assert len(corpus) == 2
    assert {u["id"] for u in corpus} == {"u1", "u2"}
    assert all(u["page"] == 1 for u in corpus)


def test_load_evidence_units_uses_numeric_page_order(tmp_path) -> None:
    for page, unit_id in ((1, "u1"), (11, "u11"), (109, "u109")):
        page_dir = tmp_path / f"TestDoc_p{page}"
        page_dir.mkdir()
        (page_dir / "stageB.evidence_units.json").write_text(
            json.dumps(
                {
                    "units": [
                        {
                            "unit_id": unit_id,
                            "text": f"page {page}",
                            "structural_path": ["Rules"],
                            "unit_type": "prose",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    corpus = load_evidence_units(tmp_path, "TestDoc")

    assert [unit["page"] for unit in corpus] == [1, 11, 109]
    assert [unit["id"] for unit in corpus] == ["u1", "u11", "u109"]


def test_merge_units_by_heading_keeps_or_merges_consistently() -> None:
    corpus = [
        {
            "id": "a1",
            "text": "First sentence.",
            "page": 1,
            "structural_path": ["Combat", "Initiative"],
            "unit_type": "prose",
            "document_id": "TestDoc",
        },
        {
            "id": "a2",
            "text": "Second sentence.",
            "page": 1,
            "structural_path": ["Combat", "Initiative"],
            "unit_type": "prose",
            "document_id": "TestDoc",
        },
    ]
    merged = merge_units_by_heading(corpus, max_chars=500)
    assert len(merged) == 1
    assert merged[0]["source_unit_ids"] == ["a1", "a2"]


def test_fold_under_threshold_into_adjacent_prepends_and_appends() -> None:
    """Under-threshold units are folded into next (prepend) or last on page (append); none dropped."""
    corpus = [
        {"id": "tiny1", "text": "Hi.", "page": 1, "structural_path": ["A"], "unit_type": "prose", "document_id": "D"},
        {"id": "big1", "text": "Long enough unit here.", "page": 1, "structural_path": ["A"], "unit_type": "prose", "document_id": "D"},
        {"id": "tiny2", "text": "Bye.", "page": 1, "structural_path": ["A"], "unit_type": "prose", "document_id": "D"},
        {"id": "big2", "text": "Another long unit.", "page": 2, "structural_path": ["B"], "unit_type": "prose", "document_id": "D"},
    ]
    folded = fold_under_threshold_into_adjacent(corpus, min_chars=10)
    assert len(folded) == 2
    # tiny1 prepended into big1; tiny2 appended into same (last on page 1)
    assert "Hi." in folded[0]["text"] and "Long enough unit here." in folded[0]["text"] and "Bye." in folded[0]["text"]
    assert len(folded[0]["source_unit_ids"]) == 3
    assert folded[1]["text"] == "Another long unit."
    assert folded[1]["source_unit_ids"] == ["big2"]


def test_merge_units_by_heading_keeps_table_as_standalone_chunk() -> None:
    corpus = [
        {
            "id": "p1",
            "text": "Class progression intro.",
            "page": 10,
            "structural_path": ["Cleric"],
            "unit_type": "prose",
            "document_id": "TestDoc",
        },
        {
            "id": "t1",
            "text": "<table><tr><td>Level</td><td>Slots</td></tr><tr><td>1</td><td>1</td></tr></table>",
            "page": 10,
            "structural_path": ["Cleric"],
            "unit_type": "table",
            "document_id": "TestDoc",
        },
        {
            "id": "p2",
            "text": "Table footnote and clarifications.",
            "page": 10,
            "structural_path": ["Cleric"],
            "unit_type": "prose",
            "document_id": "TestDoc",
        },
    ]
    merged = merge_units_by_heading(corpus, max_chars=60)
    assert len(merged) == 3
    assert [u["unit_type"] for u in merged] == ["prose", "table", "prose"]
    assert merged[1]["id"] == "t1"
    assert merged[1]["source_unit_ids"] == ["t1"]
