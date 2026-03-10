from __future__ import annotations

from retrieval_lab.corpus_fingerprint import (
    build_corpus_index_payload,
    corpus_content_fingerprint_from_units,
)


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
