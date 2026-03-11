"""Tests for Stage A' (enrichment schemas, fingerprint, gates, cache)."""

from __future__ import annotations

import pytest

from extraction.schemas import EvidenceUnit
from extraction.schemas_a_prime import (
    APrimeEnrichment,
    TOPIC_TAGS_VOCABULARY,
    compute_input_fingerprint,
    MechanicAtom,
)
from extraction.gates_a_prime import run_stage_a_prime_gates
from extraction.stage_a_prime import _cache_key, _validate_surface_forms_substrings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_unit() -> EvidenceUnit:
    return EvidenceUnit(
        unit_id="abc123",
        unit_type="prose",
        text="When you take the Attack action, you can make one melee or ranged attack.",
        structural_path=["Combat", "Actions"],
        ordering_key=0,
        page_fingerprint="fp456",
        content_hash="ch789",
        source_line_start=0,
        source_line_end=5,
        anomaly_flags=[],
    )


@pytest.fixture
def valid_enrichment_payload() -> dict:
    return {
        "enrichment_version": "A_PRIME_V1",
        "model_id": "gpt-4o-mini",
        "prompt_id": "A_PRIME_PROMPT_V1",
        "input_fingerprint": "fp",
        "created_at": "2025-01-01T00:00:00Z",
        "authority": "none",
        "source": "llm_annotation",
        "admissibility": "non_evidence",
        "stage_c_visibility": "hidden",
        "citation_policy": "never_cite",
        "summary_1s": "This unit describes how the Attack action allows one melee or ranged attack.",
        "summary_3b": "- The Attack action allows you to make one melee or ranged attack.\n- You choose between melee or ranged when you take the action.\n- Only one attack is granted per use of the Attack action.",
        "topic_tags": ["actions", "attacks"],
        "mechanic_atoms": [
            {
                "type": "procedure_step",
                "surface_forms": ["Attack action", "one melee or ranged attack"],
                "paraphrases": ["taking the Attack action lets you make an attack"],
                "requires_parent": False,
                "risk_flags": [],
            }
        ],
        "questions_answered": [
            "What does the Attack action allow a character to do when they take it?",
            "Can you make a melee attack with the Attack action?",
            "How many attacks does the Attack action grant when you use it?",
        ],
        "lexical_anchors": ["Attack action", "melee", "ranged", "attack", "action"],
    }


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def test_compute_input_fingerprint_determinism(sample_unit: EvidenceUnit) -> None:
    a = compute_input_fingerprint(sample_unit)
    b = compute_input_fingerprint(sample_unit)
    assert a == b
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


def test_compute_input_fingerprint_different_for_different_text(sample_unit: EvidenceUnit) -> None:
    fp1 = compute_input_fingerprint(sample_unit)
    other = EvidenceUnit(
        unit_id="other",
        unit_type="prose",
        text="Different text.",
        structural_path=sample_unit.structural_path,
        ordering_key=0,
        page_fingerprint=sample_unit.page_fingerprint,
        content_hash="x",
        source_line_start=0,
        source_line_end=1,
        anomaly_flags=[],
    )
    fp2 = compute_input_fingerprint(other)
    assert fp1 != fp2


def test_compute_input_fingerprint_different_for_different_path(sample_unit: EvidenceUnit) -> None:
    fp1 = compute_input_fingerprint(sample_unit)
    other = EvidenceUnit(
        unit_id="other",
        unit_type=sample_unit.unit_type,
        text=sample_unit.text,
        structural_path=["Spells"],
        ordering_key=0,
        page_fingerprint=sample_unit.page_fingerprint,
        content_hash=sample_unit.content_hash,
        source_line_start=0,
        source_line_end=5,
        anomaly_flags=[],
    )
    fp2 = compute_input_fingerprint(other)
    assert fp1 != fp2


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_aprime_enrichment_schema_valid(valid_enrichment_payload: dict) -> None:
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    assert enr.enrichment_version == "A_PRIME_V1"
    assert enr.topic_tags == ["actions", "attacks"]
    assert len(enr.mechanic_atoms) == 1
    assert enr.mechanic_atoms[0].type == "procedure_step"
    assert len(enr.questions_answered) == 3
    assert len(enr.lexical_anchors) == 5


def test_aprime_enrichment_schema_invalid_topic_tag_is_dropped(valid_enrichment_payload: dict) -> None:
    valid_enrichment_payload["topic_tags"] = ["actions", "invalid_tag"]
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    assert enr.topic_tags == ["actions"]


def test_aprime_enrichment_schema_summary_1s_word_count(valid_enrichment_payload: dict) -> None:
    valid_enrichment_payload["summary_1s"] = "Too short."
    with pytest.raises(ValueError, match="summary_1s must be 5-30 words"):
        APrimeEnrichment.model_validate(valid_enrichment_payload)


def test_aprime_enrichment_schema_summary_3b_bullets_warn_only(valid_enrichment_payload: dict) -> None:
    valid_enrichment_payload["summary_3b"] = "- One\n- Two"
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    assert enr.summary_3b == "- One\n- Two"


def test_aprime_enrichment_schema_lexical_anchors_length(valid_enrichment_payload: dict) -> None:
    valid_enrichment_payload["lexical_anchors"] = []
    with pytest.raises(ValueError, match="lexical_anchors must have at least 1 item"):
        APrimeEnrichment.model_validate(valid_enrichment_payload)


def test_mechanic_atom_risk_flags(valid_enrichment_payload: dict) -> None:
    valid_enrichment_payload["mechanic_atoms"] = [
        {
            "type": "procedure_step",
            "surface_forms": ["Attack"],
            "paraphrases": ["attack"],
            "requires_parent": True,
            "risk_flags": ["delta_only"],
        }
    ]
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    assert enr.mechanic_atoms[0].risk_flags == ["delta_only"]


def test_mechanic_atom_invalid_risk_flag(valid_enrichment_payload: dict) -> None:
    valid_enrichment_payload["mechanic_atoms"] = [
        {
            "type": "procedure_step",
            "surface_forms": ["Attack"],
            "paraphrases": ["attack"],
            "requires_parent": False,
            "risk_flags": ["invalid_flag"],
        }
    ]
    with pytest.raises(Exception, match="Input should be|risk_flag"):
        APrimeEnrichment.model_validate(valid_enrichment_payload)


# ---------------------------------------------------------------------------
# Substring validation
# ---------------------------------------------------------------------------


def test_validate_surface_forms_substrings_pass(valid_enrichment_payload: dict, sample_unit: EvidenceUnit) -> None:
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    _validate_surface_forms_substrings(enr, sample_unit.text)


def test_validate_surface_forms_substrings_fail_drops_bad_atoms(valid_enrichment_payload: dict, sample_unit: EvidenceUnit) -> None:
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    enr.mechanic_atoms[0].surface_forms.append("not in text xyz")
    _validate_surface_forms_substrings(enr, sample_unit.text)
    assert enr.mechanic_atoms == []


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def test_cache_key_determinism() -> None:
    a = _cache_key("fp1", "A_PRIME_PROMPT_V1", "gpt-4o-mini")
    b = _cache_key("fp1", "A_PRIME_PROMPT_V1", "gpt-4o-mini")
    assert a == b


def test_cache_key_different_for_different_inputs() -> None:
    a = _cache_key("fp1", "A_PRIME_PROMPT_V1", "gpt-4o-mini")
    b = _cache_key("fp2", "A_PRIME_PROMPT_V1", "gpt-4o-mini")
    assert a != b


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def test_gate_substring_enforcement_pass(sample_unit: EvidenceUnit, valid_enrichment_payload: dict) -> None:
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    enrichments = [(sample_unit.unit_id, enr)]
    unit_by_id = {sample_unit.unit_id: sample_unit}
    diagnostics = run_stage_a_prime_gates(enrichments, unit_by_id)
    substring_diag = next(d for d in diagnostics if d.gate_name == "a_prime_substring_enforcement")
    assert substring_diag.passed


def test_gate_substring_enforcement_fail(sample_unit: EvidenceUnit, valid_enrichment_payload: dict) -> None:
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    enr.mechanic_atoms[0].surface_forms = ["not in verbatim text at all"]
    enrichments = [(sample_unit.unit_id, enr)]
    unit_by_id = {sample_unit.unit_id: sample_unit}
    diagnostics = run_stage_a_prime_gates(enrichments, unit_by_id)
    substring_diag = next(d for d in diagnostics if d.gate_name == "a_prime_substring_enforcement")
    assert not substring_diag.passed
    assert substring_diag.detail["violation_count"] >= 1


def test_gate_fragment_flagging_fail(valid_enrichment_payload: dict) -> None:
    valid_enrichment_payload["mechanic_atoms"] = [
        {
            "type": "procedure_step",
            "surface_forms": ["delta"],
            "paraphrases": ["delta"],
            "requires_parent": False,
            "risk_flags": ["delta_only"],
        }
    ]
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    enrichments = [("u1", enr)]
    unit_by_id = {"u1": EvidenceUnit(
        unit_id="u1", unit_type="prose", text="delta", structural_path=[],
        ordering_key=0, page_fingerprint="", content_hash="", source_line_start=0, source_line_end=0, anomaly_flags=[],
    )}
    diagnostics = run_stage_a_prime_gates(enrichments, unit_by_id)
    fragment_diag = next(d for d in diagnostics if d.gate_name == "a_prime_fragment_flagging")
    assert not fragment_diag.passed


def test_gate_fragment_flagging_pass(valid_enrichment_payload: dict) -> None:
    valid_enrichment_payload["mechanic_atoms"] = [
        {
            "type": "procedure_step",
            "surface_forms": ["delta"],
            "paraphrases": ["delta"],
            "requires_parent": True,
            "risk_flags": ["delta_only"],
        }
    ]
    enr = APrimeEnrichment.model_validate(valid_enrichment_payload)
    enrichments = [("u1", enr)]
    unit_by_id = {"u1": EvidenceUnit(
        unit_id="u1", unit_type="prose", text="delta", structural_path=[],
        ordering_key=0, page_fingerprint="", content_hash="", source_line_start=0, source_line_end=0, anomaly_flags=[],
    )}
    diagnostics = run_stage_a_prime_gates(enrichments, unit_by_id)
    fragment_diag = next(d for d in diagnostics if d.gate_name == "a_prime_fragment_flagging")
    assert fragment_diag.passed


# ---------------------------------------------------------------------------
# Topic tags vocabulary
# ---------------------------------------------------------------------------


def test_topic_tags_vocabulary_contains_expected() -> None:
    assert "actions" in TOPIC_TAGS_VOCABULARY
    assert "attacks" in TOPIC_TAGS_VOCABULARY
    assert "spellcasting" in TOPIC_TAGS_VOCABULARY
    assert "conditions" in TOPIC_TAGS_VOCABULARY
