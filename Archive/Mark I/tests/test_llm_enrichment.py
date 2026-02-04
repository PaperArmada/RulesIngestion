from config_generator import RulesetConfiguration
from enrichment import EnrichedChunk
from llm_enrichment import build_review_prompt, extract_paragraph_targets, split_paragraphs


def test_split_paragraphs_drops_empty() -> None:
    text = "Para one.\n\n\nPara two.\n\n"
    paragraphs = split_paragraphs(text)
    assert paragraphs == ["Para one.", "Para two."]


def test_extract_paragraph_targets_uses_flags_and_min_chars() -> None:
    chunks = [
        EnrichedChunk(
            id="c1",
            block_type="Text",
            text="Short.\n\nThis is a spell paragraph with enough length to count.",
            page=1,
            content_kind="rule",
            section_path=["Magic"],
        )
    ]
    config = RulesetConfiguration(
        ruleset_id="sf2e",
        doc_signature="sig",
        version="v1",
        deterministic_rules={},
        nondeterministic_flags=["spell"],
        drift_criteria={},
    )

    targets = extract_paragraph_targets(chunks, config, min_chars=40)

    assert len(targets) == 1
    assert targets[0]["chunk_id"] == "c1"
    assert targets[0]["paragraph_index"] == 1


def test_build_review_prompt_requests_query() -> None:
    prompt = build_review_prompt({"text": "Chunk text."})
    assert "query" in prompt
