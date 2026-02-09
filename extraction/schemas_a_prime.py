"""
Stage A' (A-Prime) schemas: enrichment payloads for retrieval-only augmentation.

All A' outputs are non-evidence (authority=none, never_cite).
Schema version: A_PRIME_V1. See Docs/Design/stage_a_prime_contract.md.
"""

from __future__ import annotations

from typing import Any, Literal

import blake3
from pydantic import BaseModel, field_validator

from extraction.schemas import EvidenceUnit

# Allowed topic_tags vocabulary (initial set from contract)
TOPIC_TAGS_VOCABULARY: frozenset[str] = frozenset({
    "actions", "reactions", "initiative", "movement", "cover_concealment",
    "conditions", "dying", "death_and_dying", "healing", "attacks", "damage",
    "critical_hits", "resistance_weakness_immunity", "spells", "spellcasting",
    "spell_slots", "spell_heightening", "counteracting", "skill_checks",
    "perception", "stealth", "saves", "equipment", "weapons", "armor", "items",
    "traits", "keywords", "definitions", "procedures", "timing",
    "frequency_limits", "duration", "character_options", "feats", "class_features",
    "ancestry_features", "environment", "hazards", "afflictions", "poison_disease",
})

RISK_FLAGS: frozenset[str] = frozenset({
    "delta_only", "orphan_step", "example_only", "table_fragment",
    "term_without_definition", "negative_space",
})


class MechanicAtom(BaseModel):
    """Single mechanic atom: definition, procedure step, modifier, etc."""

    type: Literal[
        "definition", "procedure_step", "modifier", "permission",
        "prohibition", "frequency", "duration", "trigger",
        "exception", "table_rule",
    ]
    surface_forms: list[str]  # 1-4, must be exact substrings of verbatim_text
    paraphrases: list[str]    # 1-3
    requires_parent: bool
    risk_flags: list[
        Literal[
            "delta_only", "orphan_step", "example_only", "table_fragment",
            "term_without_definition", "negative_space",
        ]
    ] = []

    @field_validator("surface_forms")
    @classmethod
    def surface_forms_length(cls, v: list[str]) -> list[str]:
        if not (1 <= len(v) <= 4):
            raise ValueError("surface_forms must have 1-4 items")
        return v

    @field_validator("paraphrases")
    @classmethod
    def paraphrases_length(cls, v: list[str]) -> list[str]:
        if not (1 <= len(v) <= 3):
            raise ValueError("paraphrases must have 1-3 items")
        return v

    @field_validator("risk_flags")
    @classmethod
    def risk_flags_allowed(cls, v: list[str]) -> list[str]:
        for flag in v:
            if flag not in RISK_FLAGS:
                raise ValueError(f"risk_flag must be one of {sorted(RISK_FLAGS)}: got {flag!r}")
        return v


class APrimeEnrichment(BaseModel):
    """A_PRIME_V1 enrichment payload. Retrieval-only; never admissible as evidence."""

    enrichment_version: Literal["A_PRIME_V1"] = "A_PRIME_V1"
    model_id: str = ""
    prompt_id: Literal["A_PRIME_PROMPT_V1"] = "A_PRIME_PROMPT_V1"
    input_fingerprint: str = ""
    created_at: str = ""  # ISO-8601
    authority: Literal["none"] = "none"
    source: Literal["llm_annotation"] = "llm_annotation"
    admissibility: Literal["non_evidence"] = "non_evidence"
    stage_c_visibility: Literal["hidden"] = "hidden"
    citation_policy: Literal["never_cite"] = "never_cite"
    summary_1s: str = ""
    summary_3b: str = ""
    topic_tags: list[str] = []
    mechanic_atoms: list[MechanicAtom] = []
    questions_answered: list[str] = []
    lexical_anchors: list[str] = []

    @field_validator("summary_1s")
    @classmethod
    def summary_1s_word_count(cls, v: str) -> str:
        n = len(v.split())
        if not (5 <= n <= 30):
            raise ValueError(f"summary_1s must be 5-30 words, got {n}")
        return v

    @field_validator("summary_3b")
    @classmethod
    def summary_3b_bullets(cls, v: str) -> str:
        lines = [ln.strip() for ln in v.strip().split("\n") if ln.strip()]
        if not (1 <= len(lines) <= 3):
            raise ValueError("summary_3b must have 1-3 bullet lines")
        for line in lines:
            content = line.lstrip("-*•").strip()
            n = len(content.split())
            if not (4 <= n <= 18):
                raise ValueError(f"each summary_3b bullet must be 4-18 words, got {n}")
        return v

    @field_validator("topic_tags")
    @classmethod
    def topic_tags_vocabulary(cls, v: list[str]) -> list[str]:
        if not (0 <= len(v) <= 6):
            raise ValueError("topic_tags must have 0-6 items")
        for tag in v:
            if tag not in TOPIC_TAGS_VOCABULARY:
                raise ValueError(f"topic_tag must be in allowed vocabulary: got {tag!r}")
        return v

    @field_validator("mechanic_atoms")
    @classmethod
    def mechanic_atoms_length(cls, v: list[MechanicAtom]) -> list[MechanicAtom]:
        if len(v) > 8:
            raise ValueError("mechanic_atoms must have 0-8 items")
        return v

    @field_validator("questions_answered")
    @classmethod
    def questions_answered_length_and_words(cls, v: list[str]) -> list[str]:
        if not (1 <= len(v) <= 10):
            raise ValueError("questions_answered must have 1-10 items")
        for q in v:
            n = len(q.split())
            if not (5 <= n <= 18):
                raise ValueError(f"each question must be 5-18 words, got {n}")
        return v

    @field_validator("lexical_anchors")
    @classmethod
    def lexical_anchors_length(cls, v: list[str]) -> list[str]:
        if not (1 <= len(v) <= 20):
            raise ValueError("lexical_anchors must have 1-20 items")
        return v

    def model_dump_json_dict(self) -> dict[str, Any]:
        """Return dict suitable for JSON serialization (Pydantic v2)."""
        return self.model_dump()


def compute_input_fingerprint(unit: EvidenceUnit) -> str:
    """Compute deterministic fingerprint for caching.

    Hash input = verbatim_text + structural_path + unit_type + table_schema_if_any.
    EvidenceUnit has no table_schema in Mark III; we use empty string.
    """
    path_str = "|".join(unit.structural_path)
    table_schema = ""  # Mark III EvidenceUnit has no table_schema
    payload = f"{unit.text}|{path_str}|{unit.unit_type}|{table_schema}"
    return blake3.blake3(payload.encode("utf-8")).hexdigest()
