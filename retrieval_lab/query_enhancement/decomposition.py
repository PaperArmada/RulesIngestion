"""Responses API query decomposition for retrieval-oriented multihop search."""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple

from retrieval_lab.query_enhancement.profile import QueryExpansionProfile

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")

_DECOMPOSITION_PROMPT_TEMPLATE = """You split a tabletop RPG rules question into retrieval queries.

Goal:
- Return the smallest set of retrieval queries needed to retrieve the rule passages required by the question.

Rules:
- Produce retrieval queries only, never answers.
- Use only vocabulary that already appears in the question.
- Do not introduce synonyms, broader categories, external rule terms, section names, or inferred entities.
- Keep each retrieval query short, literal, and close to the question wording.
- Split only when the question contains multiple distinct retrieval obligations.
- If one retrieval query is enough, return exactly one.
- Avoid near-duplicate rewrites.

Allowed vocabulary from the question:
{query_vocab_summary}

Return strict JSON only."""

DECOMPOSITION_JSON_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "name": "retrieval_query_decomposition_v2",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["retrieval_queries"],
        "properties": {
            "retrieval_queries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["query", "must_include_terms"],
                    "properties": {
                        "query": {"type": "string"},
                        "must_include_terms": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            }
        },
    },
}


def _query_tokens(text: str) -> List[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "")]


def _query_vocabulary_summary(query: str) -> str:
    seen: set[str] = set()
    ordered: List[str] = []
    for token in _query_tokens(query):
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ", ".join(ordered) if ordered else "(empty query)"


def _uses_only_query_vocabulary(candidate_query: str, original_query: str) -> bool:
    allowed = set(_query_tokens(original_query))
    if not allowed:
        return False
    candidate_tokens = set(_query_tokens(candidate_query))
    if not candidate_tokens:
        return False
    extra = candidate_tokens - allowed
    if extra:
        logger.info(
            "Rejecting decomposition query with out-of-query vocabulary. query=%r candidate=%r extra=%s",
            original_query[:160],
            candidate_query[:160],
            sorted(extra),
        )
        return False
    return True


def _extract_output_blocks_text(resp: Any) -> str:
    chunks: List[str] = []
    for item in getattr(resp, "output", None) or []:
        for block in getattr(item, "content", None) or []:
            parsed = getattr(block, "parsed", None)
            if parsed is not None:
                if isinstance(parsed, dict):
                    return json.dumps(parsed, ensure_ascii=False)
                if hasattr(parsed, "model_dump"):
                    dumped = parsed.model_dump(mode="json")
                    if isinstance(dumped, dict):
                        return json.dumps(dumped, ensure_ascii=False)
            block_type = str(getattr(block, "type", "") or "").strip()
            if block_type in {"output_text", "text"}:
                text = getattr(block, "text", None)
                if isinstance(text, str) and text.strip():
                    chunks.append(text)
                elif isinstance(text, dict):
                    value = str(text.get("value") or "").strip()
                    if value:
                        chunks.append(value)
    return "\n".join(chunks).strip()


def _extract_raw_text(resp: Any) -> str:
    parsed_output = getattr(resp, "output_parsed", None)
    if parsed_output is not None:
        if isinstance(parsed_output, dict):
            return json.dumps(parsed_output, ensure_ascii=False)
        if hasattr(parsed_output, "model_dump"):
            dumped = parsed_output.model_dump(mode="json")
            if isinstance(dumped, dict):
                return json.dumps(dumped, ensure_ascii=False)
    raw_text = getattr(resp, "output_text", None) or ""
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text
    return _extract_output_blocks_text(resp)


@lru_cache(maxsize=1)
def _load_model_policy() -> Dict[str, Any]:
    model_policy_path = Path(__file__).resolve().parents[3] / "MODEL_POLICY.json"
    if not model_policy_path.exists():
        raise FileNotFoundError(f"MODEL_POLICY.json not found: {model_policy_path}")
    return json.loads(model_policy_path.read_text(encoding="utf-8"))


def resolve_decomposition_model(profile: QueryExpansionProfile) -> str:
    explicit = str(profile.decomposition.model_id or "").strip()
    if explicit:
        return explicit

    policy = _load_model_policy()
    actions = policy.get("actions", {})
    models = policy.get("models", {})
    role = str(actions.get("structured_generation", "")).strip()
    model_id = str(models.get(role, "")).strip()
    if not model_id:
        raise ValueError("No decomposition model configured and MODEL_POLICY.json has no structured_generation model")
    return model_id


def _supports_reasoning(model_id: str) -> bool:
    model = str(model_id or "").strip().lower()
    return model.startswith("gpt-5") or model.startswith("o")


def _supports_temperature(model_id: str) -> bool:
    model = str(model_id or "").strip().lower()
    return not model.startswith("gpt-5")


def build_decomposition_prompts(query: str, profile: QueryExpansionProfile) -> Tuple[str, str]:
    _ = profile
    developer = _DECOMPOSITION_PROMPT_TEMPLATE.format(
        query_vocab_summary=_query_vocabulary_summary(query),
    )
    user = f"Question:\n{query.strip()}"
    return developer, user


def decomposition_prompt_hash(profile: QueryExpansionProfile) -> str:
    prompt_template_id = str(profile.decomposition.prompt_template_id or "retrieval_query_decomposition_v2").strip()
    payload = {
        "prompt_template_id": prompt_template_id,
        "prompt_template": _DECOMPOSITION_PROMPT_TEMPLATE,
        "schema": DECOMPOSITION_JSON_SCHEMA,
        "output_schema_version": profile.decomposition.output_schema_version,
    }
    rendered = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def decomposition_cache_signature(profile: QueryExpansionProfile) -> Tuple[str, str]:
    return resolve_decomposition_model(profile), decomposition_prompt_hash(profile)


def parse_decomposition_response(raw_text: str, *, original_query: str = "") -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("Decomposition response is not valid JSON: %s", raw_text[:400])
        return []

    retrieval_queries = data.get("retrieval_queries", [])
    if not isinstance(retrieval_queries, list):
        logger.warning("Decomposition response retrieval_queries is not a list")
        return []

    results: List[Dict[str, Any]] = []
    for index, item in enumerate(retrieval_queries, start=1):
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        if not query:
            continue
        if original_query and not _uses_only_query_vocabulary(query, original_query):
            continue
        must_include_terms = item.get("must_include_terms", [])
        must_include_terms_clean = [
            term
            for term in must_include_terms
            if isinstance(term, str)
            and term.strip()
            and (not original_query or _uses_only_query_vocabulary(term, original_query))
        ]
        results.append(
            {
                "q": query,
                "source": "decompose",
                "intent": f"retrieval_query:{index}",
                "must_include_terms": must_include_terms_clean,
                "notes": "responses_decompose_query_vocab_only",
            }
        )
    return results


def decompose_query(query: str, profile: QueryExpansionProfile) -> List[Dict[str, Any]]:
    from openai import OpenAI  # type: ignore

    model_id = resolve_decomposition_model(profile)
    developer_prompt, user_prompt = build_decomposition_prompts(query, profile)

    kwargs: Dict[str, Any] = {
        "model": model_id,
        "input": [
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "text": {"format": DECOMPOSITION_JSON_SCHEMA},
    }

    if _supports_temperature(model_id):
        kwargs["temperature"] = 0

    effort = str(profile.decomposition.reasoning_effort or "none").strip().lower()
    if _supports_reasoning(model_id) and effort and effort != "none":
        kwargs["reasoning"] = {"effort": effort}

    client = OpenAI()
    response = client.responses.create(**kwargs)
    raw_text = _extract_raw_text(response)
    return parse_decomposition_response(raw_text, original_query=query)
