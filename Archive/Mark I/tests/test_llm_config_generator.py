# Tests for LLM config generator utilities.

from config_profile import RulesetProfile
import pytest

from llm_config_generator import (
    build_config_prompt,
    normalize_llm_payload,
    parse_llm_response,
    validate_config_payload,
)


def test_build_config_prompt_includes_profile_fields() -> None:
    profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A", "B"],
        noise_headings=["Glossary"],
        block_type_distribution={"Text": 2},
        samples=["Sample text"],
    )

    prompt = build_config_prompt(profile)

    assert "ruleset_id" in prompt
    assert "sf2e" in prompt
    assert "heading_hierarchy" in prompt
    assert "noise_headings" in prompt
    assert "Sample text" in prompt


def test_parse_llm_response_loads_json() -> None:
    payload = parse_llm_response('{"ruleset_id":"sf2e","version":"v1"}')

    assert payload["ruleset_id"] == "sf2e"
    assert payload["version"] == "v1"


def test_validate_config_payload_rejects_placeholders() -> None:
    profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A", "B", "C"],
        block_type_distribution={"SectionHeader": 3, "Text": 1},
        samples=["Sample one", "Sample two"],
    )
    payload = {
        "ruleset_id": "sf2e",
        "doc_signature": "sig",
        "version": "v1",
        "schema_version": "1.0",
        "deterministic_rules": {
            "high_value_tags": ["important_tag_1"],
            "config_notes": "test",
        },
        "nondeterministic_flags": [],
        "drift_criteria": {
            "heading_hierarchy": ["A", "B", "C"],
            "block_type_distribution": {"SectionHeader": 3, "Text": 1},
        },
    }

    with pytest.raises(ValueError, match="placeholder value"):
        validate_config_payload(profile, payload)


def test_validate_config_payload_requires_evidence() -> None:
    profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A", "B", "C"],
        block_type_distribution={"SectionHeader": 3, "Text": 1},
        samples=["Sample one", "Sample two"],
    )
    payload = {
        "ruleset_id": "sf2e",
        "doc_signature": "sig",
        "version": "v1",
        "schema_version": "1.0",
        "deterministic_rules": {
            "entity_aliases": {"PC": "player character"},
            "config_notes": "test",
        },
        "nondeterministic_flags": [],
        "drift_criteria": {
            "heading_hierarchy": ["A", "B", "C"],
            "block_type_distribution": {"SectionHeader": 3, "Text": 1},
        },
    }

    with pytest.raises(ValueError, match="missing evidence"):
        validate_config_payload(profile, payload)


def test_normalize_llm_payload_filters_without_evidence() -> None:
    profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A", "B", "C"],
        block_type_distribution={"SectionHeader": 3, "Text": 1},
        samples=["Sample one", "Sample two"],
    )
    payload = {
        "ruleset_id": "sf2e",
        "doc_signature": "sig",
        "version": "v1",
        "schema_version": "1.0",
        "deterministic_rules": {
            "entity_aliases": [{"key": "PC", "value": "player character"}],
            "min_chunk_chars": 200,
            "config_notes": "test",
        },
        "nondeterministic_flags": [],
        "drift_criteria": {
            "heading_hierarchy": ["A", "B", "C"],
            "block_type_distribution": {"SectionHeader": 3, "Text": 1},
        },
    }

    normalized = normalize_llm_payload(profile, payload)
    deterministic = normalized["deterministic_rules"]
    assert "entity_aliases" not in deterministic
    assert "min_chunk_chars" not in deterministic
    assert deterministic["config_notes"] == "test"
