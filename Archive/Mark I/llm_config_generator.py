"""LLM-backed ruleset config generation."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel

from config_profile import RulesetProfile

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise RuntimeError("openai package is required for LLM config generation.") from exc


DEFAULT_LLM_MODEL = "gpt-5.2-codex"
DEFAULT_EVAL_MODEL_ID = "gpt-5-chat-latest"
LLM_METADATA_FIELDS = {"config_notes", "version_tags"}
LLM_EVIDENCE_FIELDS = {
    "entity_aliases",
    "entity_blacklist",
    "entity_type_overrides",
    "abbreviation_patterns",
    "content_kind_overrides",
    "high_value_tags",
    "evaluation_query_type_overrides",
    "evaluation_query_templates",
}
LLM_WRITABLE_FIELDS = LLM_METADATA_FIELDS | LLM_EVIDENCE_FIELDS
REQUIRED_KEYS = {
    "ruleset_id",
    "doc_signature",
    "version",
    "schema_version",
    "deterministic_rules",
    "nondeterministic_flags",
    "drift_criteria",
}


class StringPair(BaseModel):
    key: str
    value: str


class FloatPair(BaseModel):
    key: str
    value: float


class IntPair(BaseModel):
    key: str
    value: int


class RelationPattern(BaseModel):
    relation: str
    pattern: str


class EvalBestPracticeDefaults(BaseModel):
    expand_gold: bool
    graph_boost: float
    graph_boost_source: str
    graph_boost_seed_top_n: int
    graph_boost_depth: int
    graph_boost_top_k: Optional[int]
    graph_boost_decay: float


class EvidenceItem(BaseModel):
    field: str
    key: Optional[str] = None
    value: Optional[str] = None
    source_heading: str
    sample_snippet: str


class DeterministicRulesPayload(BaseModel):
    entity_aliases: Optional[List[StringPair]] = None
    entity_blacklist: Optional[List[str]] = None
    entity_type_overrides: Optional[List[StringPair]] = None
    abbreviation_patterns: Optional[List[str]] = None
    graph_edge_weights: Optional[List[FloatPair]] = None
    graph_relation_patterns: Optional[List[RelationPattern]] = None
    graph_relation_target_limit: Optional[int] = None
    graph_chunk_adjacency_limit: Optional[int] = None
    graph_skip_relations: Optional[List[str]] = None
    content_kind_overrides: Optional[List[StringPair]] = None
    high_value_tags: Optional[List[str]] = None
    merge_spell_blocks: Optional[bool] = None
    merge_spell_max_blocks: Optional[int] = None
    min_chunk_chars: Optional[int] = None
    max_chunk_chars: Optional[int] = None
    evaluation_query_type_defaults: Optional[List[StringPair]] = None
    evaluation_query_type_overrides: Optional[List[StringPair]] = None
    evaluation_query_templates: Optional[List[StringPair]] = None
    evaluation_query_max_per_kind: Optional[int] = None
    evaluation_paragraph_min_chars: Optional[int] = None
    evaluation_hypothetical_answer_max_chars: Optional[int] = None
    evaluation_hypothetical_answer_strategy: Optional[str] = None
    eval_default_model_id: Optional[str] = None
    eval_query_limit: Optional[int] = None
    eval_query_seed: Optional[int] = None
    eval_document_prefixes: Optional[List[str]] = None
    eval_best_practice_defaults: Optional[EvalBestPracticeDefaults] = None
    config_notes: Optional[str] = None
    version_tags: Optional[List[str]] = None


class DriftCriteriaPayload(BaseModel):
    heading_hierarchy: List[str]
    block_type_distribution: List[IntPair]


class RulesetConfigPayload(BaseModel):
    ruleset_id: str
    doc_signature: str
    version: str
    schema_version: str
    deterministic_rules: DeterministicRulesPayload
    deterministic_rules_evidence: Optional[List[EvidenceItem]] = None
    nondeterministic_flags: List[str]
    drift_criteria: DriftCriteriaPayload


def build_config_prompt(profile: RulesetProfile) -> str:
    profile_payload = {
        "ruleset_id": profile.ruleset_id,
        "doc_signature": profile.doc_signature,
        "heading_hierarchy": profile.heading_hierarchy,
        "noise_headings": profile.noise_headings,
        "block_type_distribution": profile.block_type_distribution,
        "samples": profile.samples or [],
    }

    schema_hint = {
        "ruleset_id": "string",
        "doc_signature": "string",
        "version": "string (semantic or date)",
        "schema_version": "string",
        "deterministic_rules": {
            "entity_aliases": [{"key": "alias", "value": "canonical"}],
            "entity_blacklist": ["string"],
            "entity_type_overrides": [{"key": "entity_name", "value": "EntityType"}],
            "abbreviation_patterns": ["regex string"],
            "content_kind_overrides": [{"key": "section_or_tag", "value": "content_kind"}],
            "high_value_tags": ["string"],
            "evaluation_query_type_overrides": [{"key": "content_kind", "value": "query_type"}],
            "evaluation_query_templates": [{"key": "content_kind", "value": "Prompt with {label}"}],
            "config_notes": "string",
            "version_tags": ["string"],
        },
        "deterministic_rules_evidence": [
            {
                "field": "entity_aliases",
                "key": "alias",
                "value": "canonical",
                "source_heading": "Heading from profile",
                "sample_snippet": "Snippet copied from profile samples",
            }
        ],
        "nondeterministic_flags": ["string"],
        "drift_criteria": {
            "heading_hierarchy": ["string"],
            "block_type_distribution": [{"key": "BlockType", "value": "count"}],
        },
    }

    return (
        "You are generating a ruleset enrichment configuration. "
        "Return ONLY a valid JSON object matching the schema hint.\n\n"
        f"Schema hint:\n{json.dumps(schema_hint, indent=2)}\n\n"
        "Profile input:\n"
        f"{json.dumps(profile_payload, indent=2)}\n\n"
        "Rules:\n"
        "- Include drift_criteria.heading_hierarchy and drift_criteria.block_type_distribution "
        "matching the profile.\n"
        "- Use nondeterministic_flags as lowercase keywords for paragraph-level LLM targeting.\n"
        "- Use key/value pair lists for map-like fields (e.g., entity_aliases, content_kind_overrides).\n"
        "- Only set deterministic_rules fields listed in the schema hint.\n"
        "- deterministic_rules.entity_aliases: map aliases to canonical names.\n"
        "- deterministic_rules.entity_blacklist: list names to drop from graph.\n"
        "- deterministic_rules.entity_type_overrides: map entity name -> type label.\n"
        "- deterministic_rules.abbreviation_patterns: regexes to detect abbreviation/canonical pairs.\n"
        "- deterministic_rules.content_kind_overrides: section/tag -> content_kind mapping.\n"
        "- deterministic_rules.high_value_tags: tags to keep (override defaults).\n"
        "- deterministic_rules.evaluation_query_type_overrides: map content_kind -> query_type.\n"
        "- deterministic_rules.evaluation_query_templates: map content_kind -> prompt (use {label}).\n"
        "- deterministic_rules.config_notes: short rationale string for this config.\n"
        "- deterministic_rules.version_tags: short labels for experiment tracking.\n"
        "- For every item you set in deterministic_rules, add a matching entry in "
        "deterministic_rules_evidence with source_heading + sample_snippet from the profile input.\n"
        "- If you cannot provide grounded evidence for an item, omit that override entirely.\n"
        "- If there is insufficient signal, return empty lists/maps and set "
        "deterministic_rules.config_notes to 'insufficient signal'.\n"
        "- Do NOT use placeholder names like important_tag_1 or unwanted_entity_1.\n"
        "- Do not include extra keys.\n"
    )


def parse_llm_response(text: str) -> Dict[str, Any]:
    return json.loads(text)


PLACEHOLDER_TOKENS: Sequence[str] = (
    "important_tag_1",
    "important_tag_2",
    "unwanted_entity_1",
    "unwanted_entity_2",
    "alias",
    "canonical",
    "prefix_1",
    "prefix_2",
    "prompt with {label}",
)


def _collect_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        collected: list[str] = []
        for item in value:
            collected.extend(_collect_strings(item))
        return collected
    if isinstance(value, dict):
        collected = []
        for item in value.values():
            collected.extend(_collect_strings(item))
        return collected
    return []


def _contains_placeholders(payload: Dict[str, Any]) -> Optional[str]:
    for text in _collect_strings(payload):
        lowered = text.lower()
        for token in PLACEHOLDER_TOKENS:
            if " " in token or "{" in token:
                if token in lowered:
                    return text
                continue
            if re.search(rf"\b{re.escape(token)}\b", lowered):
                return text
    return None


def _map_pairs_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        mapped: Dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if key is None:
                continue
            mapped[str(key)] = item.get("value")
        return mapped
    return {}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _evidence_is_grounded(
    profile: RulesetProfile, source_heading: Optional[str], sample_snippet: Optional[str]
) -> bool:
    if not source_heading or not sample_snippet:
        return False
    heading_lookup = {_normalize_text(h) for h in profile.heading_hierarchy}
    if _normalize_text(source_heading) not in heading_lookup:
        return False
    normalized_snippet = _normalize_text(sample_snippet)
    for sample in profile.samples or []:
        if normalized_snippet and normalized_snippet in _normalize_text(sample):
            return True
    return False


def _build_evidence_lookup(
    profile: RulesetProfile, evidence_items: Optional[List[Dict[str, Any]]]
) -> Dict[str, List[Dict[str, Any]]]:
    if not evidence_items:
        return {}
    lookup: Dict[str, List[Dict[str, Any]]] = {}
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        if not field:
            continue
        if not _evidence_is_grounded(
            profile, item.get("source_heading"), item.get("sample_snippet")
        ):
            continue
        lookup.setdefault(str(field), []).append(item)
    return lookup


def _evidence_matches_key_value(
    evidence_items: List[Dict[str, Any]], key: Optional[str], value: Any
) -> bool:
    for evidence in evidence_items:
        evidence_key = evidence.get("key")
        evidence_value = evidence.get("value")
        if key is None:
            if evidence_value is None:
                continue
            if str(evidence_value) == str(value):
                return True
        else:
            if evidence_key is None:
                continue
            if str(evidence_key) != str(key):
                continue
            if evidence_value is not None and str(evidence_value) != str(value):
                continue
            return True
    return False


def _filter_deterministic_rules(
    profile: RulesetProfile,
    deterministic: Dict[str, Any],
    evidence_items: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    evidence_lookup = _build_evidence_lookup(profile, evidence_items)
    filtered: Dict[str, Any] = {}
    for field, value in deterministic.items():
        if field in LLM_METADATA_FIELDS:
            filtered[field] = value
            continue
        if field not in LLM_EVIDENCE_FIELDS:
            continue
        evidence_for_field = evidence_lookup.get(field, [])
        if isinstance(value, dict):
            kept: Dict[str, Any] = {}
            for key, item_value in value.items():
                if _evidence_matches_key_value(evidence_for_field, key, item_value):
                    kept[key] = item_value
            if kept:
                filtered[field] = kept
        elif isinstance(value, list):
            kept_list = [
                item
                for item in value
                if _evidence_matches_key_value(evidence_for_field, None, item)
            ]
            if kept_list:
                filtered[field] = kept_list
    return filtered


def normalize_llm_payload(profile: RulesetProfile, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    drift = dict(payload.get("drift_criteria") or {})
    drift["heading_hierarchy"] = profile.heading_hierarchy
    drift_block_types = drift.get("block_type_distribution")
    drift["block_type_distribution"] = _map_pairs_to_dict(drift_block_types)
    drift["block_type_distribution"] = profile.block_type_distribution
    payload["drift_criteria"] = drift

    deterministic = payload.get("deterministic_rules")
    if isinstance(deterministic, dict):
        for field_name in (
            "entity_aliases",
            "entity_type_overrides",
            "graph_edge_weights",
            "content_kind_overrides",
            "evaluation_query_type_defaults",
            "evaluation_query_type_overrides",
            "evaluation_query_templates",
        ):
            if field_name in deterministic:
                deterministic[field_name] = _map_pairs_to_dict(deterministic[field_name])

        templates = deterministic.get("evaluation_query_templates")
        if isinstance(templates, dict):
            cleaned: Dict[str, Any] = {}
            for key, value in templates.items():
                if isinstance(value, str) and _contains_placeholders({"value": value}):
                    continue
                cleaned[key] = value
            if cleaned:
                deterministic["evaluation_query_templates"] = cleaned
            else:
                deterministic.pop("evaluation_query_templates", None)

        deterministic = _filter_deterministic_rules(
            profile, deterministic, payload.get("deterministic_rules_evidence")
        )
        deterministic["eval_default_model_id"] = DEFAULT_EVAL_MODEL_ID
        payload["deterministic_rules"] = deterministic

    return payload


def _collect_missing_evidence(
    profile: RulesetProfile,
    deterministic: Dict[str, Any],
    evidence_items: Optional[List[Dict[str, Any]]],
) -> List[str]:
    missing: List[str] = []
    evidence_lookup = _build_evidence_lookup(profile, evidence_items)
    for field, value in deterministic.items():
        if field in LLM_METADATA_FIELDS:
            continue
        if field not in LLM_EVIDENCE_FIELDS:
            continue
        evidence_for_field = evidence_lookup.get(field, [])
        if isinstance(value, dict):
            for key, item_value in value.items():
                if not _evidence_matches_key_value(evidence_for_field, key, item_value):
                    missing.append(f"{field}:{key}")
        elif isinstance(value, list):
            for item in value:
                if not _evidence_matches_key_value(evidence_for_field, None, item):
                    missing.append(f"{field}:{item}")
    return missing


def validate_config_payload(profile: RulesetProfile, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("LLM payload must be a JSON object.")
    missing = [key for key in REQUIRED_KEYS if key not in payload]
    if missing:
        raise ValueError(f"LLM payload missing keys: {', '.join(missing)}")
    if payload.get("ruleset_id") != profile.ruleset_id:
        raise ValueError("LLM payload ruleset_id does not match profile.")
    if payload.get("doc_signature") != profile.doc_signature:
        raise ValueError("LLM payload doc_signature does not match profile.")
    drift = payload.get("drift_criteria") or {}
    if "heading_hierarchy" not in drift or "block_type_distribution" not in drift:
        raise ValueError("LLM payload drift_criteria is incomplete.")
    if drift.get("heading_hierarchy") != profile.heading_hierarchy:
        raise ValueError("LLM payload drift_criteria.heading_hierarchy does not match profile.")
    if drift.get("block_type_distribution") != profile.block_type_distribution:
        raise ValueError("LLM payload drift_criteria.block_type_distribution does not match profile.")
    placeholder = _contains_placeholders(payload)
    if placeholder:
        raise ValueError(f"LLM payload contains placeholder value: {placeholder}")
    deterministic = payload.get("deterministic_rules") or {}
    if isinstance(deterministic, dict):
        missing = _collect_missing_evidence(
            profile, deterministic, payload.get("deterministic_rules_evidence")
        )
        if missing:
            missing_preview = ", ".join(missing[:5])
            suffix = "..." if len(missing) > 5 else ""
            raise ValueError(
                "LLM payload missing evidence for deterministic overrides: "
                f"{missing_preview}{suffix}"
            )
    return payload


def generate_ruleset_config_payload(
    profile: RulesetProfile,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    prompt: Optional[str] = None,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for LLM config generation.")

    model = model or os.getenv("OPENAI_MODEL", DEFAULT_LLM_MODEL)
    prompt = prompt or build_config_prompt(profile)

    client = OpenAI(api_key=api_key)
    request_payload = {
        "model": model,
        "input": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "text_format": RulesetConfigPayload,
    }
    if temperature is not None and not model.startswith("gpt-5"):
        request_payload["temperature"] = temperature

    response = client.responses.parse(**request_payload)
    payload_model = response.output_parsed
    if payload_model is None:
        raise ValueError("LLM payload is missing or incomplete.")
    if hasattr(payload_model, "model_dump"):
        return payload_model.model_dump(mode="json")
    return payload_model.dict()
