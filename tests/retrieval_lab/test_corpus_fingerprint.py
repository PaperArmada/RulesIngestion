from __future__ import annotations

import json

from retrieval_lab.corpus_fingerprint import (
    build_corpus_index_payload,
    corpus_content_fingerprint_from_units,
)
from retrieval_lab.substrate_loader import load_evidence_units


def test_content_fingerprint_changes_when_text_changes() -> None:
    corpus_a = [{"id": "u1", "page": 1, "structural_path": ["Combat"], "text": "Turn order.", "source_unit_ids": ["o1"]}]
    corpus_b = [{"id": "u1", "page": 1, "structural_path": ["Combat"], "text": "Different text.", "source_unit_ids": ["o1"]}]

    assert corpus_content_fingerprint_from_units(corpus_a) != corpus_content_fingerprint_from_units(corpus_b)


def test_content_fingerprint_changes_when_path_changes() -> None:
    corpus_a = [{"id": "u1", "page": 1, "structural_path": ["Combat"], "text": "Turn order.", "source_unit_ids": ["o1"]}]
    corpus_b = [{"id": "u1", "page": 1, "structural_path": ["Initiative"], "text": "Turn order.", "source_unit_ids": ["o1"]}]

    assert corpus_content_fingerprint_from_units(corpus_a) != corpus_content_fingerprint_from_units(corpus_b)


def test_build_corpus_index_payload_includes_content_records() -> None:
    payload = build_corpus_index_payload(
        run_id="run_123",
        substrate_version="v1",
        corpus=[
            {
                "id": "u1",
                "page": 2,
                "structural_path": ["Combat"],
                "text": "Turn order.",
                "source_unit_ids": ["o1", "o2"],
            }
        ],
    )

    assert payload["run_id"] == "run_123"
    assert payload["substrate_version"] == "v1"
    assert payload["ordered_corpus_records"][0]["chunk_id"] == "u1"
    assert payload["ordered_corpus_records"][0]["source_unit_ids"] == ["o1", "o2"]
    assert payload["corpus_content_fingerprint"]


def test_content_fingerprint_is_stable_for_numeric_page_sorted_loads(tmp_path) -> None:
    for page, unit_id in ((2, "u2"), (10, "u10"), (11, "u11")):
        page_dir = tmp_path / f"TestDoc_p{page}"
        page_dir.mkdir()
        (page_dir / "stageB.evidence_units.json").write_text(
            json.dumps(
                {
                    "units": [
                        {
                            "unit_id": unit_id,
                            "text": f"text {page}",
                            "structural_path": ["Rules"],
                            "unit_type": "prose",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    first = load_evidence_units(tmp_path, "TestDoc")
    second = load_evidence_units(tmp_path, "TestDoc")

    assert [unit["page"] for unit in first] == [2, 10, 11]
    assert corpus_content_fingerprint_from_units(first) == corpus_content_fingerprint_from_units(second)
