from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

ALLOWED_RATIONALE_TAGS: Tuple[str, ...] = (
    "direct_rule",
    "high_specificity",
    "required_anchor_likely",
    "complements_other_evidence",
    "exception_rule",
    "definition_link",
    "table_lookup",
    "generic_context",
    "distractor_risk",
)

_DEFAULT_TEMPLATE_ID = "pf2e_listwise_v1"


class LLMRerankValidationError(ValueError):
    """Raised when the reranker response fails hard validation."""

    def __init__(self, message: str, *, record_path: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.record_path = record_path
        self.metadata = metadata or {}


class RationaleTagEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    tags: List[str] = Field(min_length=1, max_length=4)


class ListwiseRerankResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_count_expected: int = Field(ge=1)
    ordered_candidate_tokens: List[str] = Field(min_length=1)
    rationale_tags: List[RationaleTagEntry]


def _stable_baseline_order(candidates: List[Dict[str, Any]]) -> List[str]:
    ranked = sorted(
        candidates,
        key=lambda c: (
            int(c.get("baseline_rank", 10**9)),
            str(c.get("candidate_id", "")),
        ),
    )
    return [str(c.get("candidate_id", "")) for c in ranked if str(c.get("candidate_id", "")).strip()]


def _alpha_prefix(index: int) -> str:
    out: List[str] = []
    n = int(index)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out.append(chr(ord("A") + rem))
    return "".join(reversed(out)) or "A"


def _build_prompt_token_maps(candidates: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str]]:
    baseline_order = _stable_baseline_order(candidates)
    width = max(3, len(str(len(baseline_order))))
    token_to_id: Dict[str, str] = {}
    id_to_token: Dict[str, str] = {}
    for idx, candidate_id in enumerate(baseline_order, start=1):
        token = f"{_alpha_prefix(idx)}{idx:0{width}d}"
        token_to_id[token] = candidate_id
        id_to_token[candidate_id] = token
    return token_to_id, id_to_token


def _candidate_payload(candidates: List[Dict[str, Any]], *, id_to_token: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for c in candidates:
        candidate_id = str(c.get("candidate_id", ""))
        payload.append(
            {
                "candidate_id": candidate_id,
                "prompt_token": str((id_to_token or {}).get(candidate_id, "")),
                "baseline_rank": int(c.get("baseline_rank", 0)),
                "structural_path": list(c.get("structural_path") or []),
                "unit_type": str(c.get("unit_type", "")),
                "excerpt": str(c.get("excerpt", "")),
            }
        )
    return payload


def _render_candidates_for_prompt(candidates: List[Dict[str, Any]], *, id_to_token: Dict[str, str]) -> str:
    lines: List[str] = []
    for c in candidates:
        candidate_id = str(c.get("candidate_id", "")).strip()
        prompt_token = str(id_to_token.get(candidate_id, "")).strip()
        baseline_rank = int(c.get("baseline_rank", 0))
        unit_type = str(c.get("unit_type", "")).strip()
        structural_path = " > ".join(str(x) for x in (c.get("structural_path") or []))
        excerpt = str(c.get("excerpt", "")).strip()
        lines.append(
            (
                f"[token={prompt_token} baseline_rank={baseline_rank} unit_type={unit_type} path={structural_path}]\n"
                f"{excerpt}"
            ).strip()
        )
    return "\n\n".join(lines)


def _build_messages(
    *,
    query: str,
    candidates: List[Dict[str, Any]],
    prompt_template_id: str,
    id_to_token: Dict[str, str],
) -> Tuple[str, str]:
    allowed = ", ".join(ALLOWED_RATIONALE_TAGS)
    token_list = [id_to_token[cid] for cid in _stable_baseline_order(candidates) if cid in id_to_token]
    token_count = len(token_list)
    token_inventory = ", ".join(token_list)
    example_tokens = token_list[: min(3, len(token_list))]
    example_payload = {
        "candidate_count_expected": len(example_tokens),
        "ordered_candidate_tokens": example_tokens,
        "rationale_tags": ([{"token": example_tokens[0], "tags": ["direct_rule"]}] if example_tokens else []),
    }
    system = (
        "You are a TTRPG Rules Lawyer of the first class, you think about the meta and the importance of the rules in the context of the game."
        "You are a retrieval reranker."
        "Reorder only the provided candidates by expected usefulness for answering the question. "
        "You must not invent candidate tokens and must output strict JSON only. "
        "Before producing your final answer, verify that every provided token appears exactly once in ordered_candidate_tokens."
    )
    user = (
        f"Prompt template: {prompt_template_id}\n\n"
        f"Question:\n{query.strip()}\n\n"
        f"Candidate token count: {token_count}\n"
        f"Candidate token inventory: {token_inventory}\n\n"
        "Candidates:\n"
        f"{_render_candidates_for_prompt(candidates, id_to_token=id_to_token)}\n\n"
        "Output requirements:\n"
        '- Return JSON with keys: "candidate_count_expected", "ordered_candidate_tokens", "rationale_tags".\n'
        f"- candidate_count_expected: must be exactly {token_count}.\n"
        f"- ordered_candidate_tokens: a full ordering over all {token_count} provided tokens exactly once.\n"
        f'- rationale_tags: optional array of objects shaped like {{"token": "A001", "tags": ["direct_rule"]}}. Allowed tags: {allowed}.\n'
        "- Do not include any token that is not in the provided list.\n"
        "- Do not omit any provided token.\n"
        "- Do not repeat any token.\n"
        "- Do not stop at the top results; continue until every token from the inventory appears exactly once.\n"
        "- If your draft output has fewer than the full token count, revise it before answering.\n"
        "- If your draft output has more than the full token count, revise it before answering.\n"
        "- If your draft output includes a token not in the inventory, revise it before answering.\n"
        "- If your draft output repeats any token, revise it before answering.\n"
        "- Prefer evidence that helps complete multi-obligation chains over generic context.\n"
        "\nExample output shape:\n"
        f"{json.dumps(example_payload, ensure_ascii=True)}\n"
        "\nSelf-check before answering:\n"
        f"1. candidate_count_expected must equal {token_count}.\n"
        f"2. Count ordered_candidate_tokens. It must equal {token_count}.\n"
        f"3. Compare ordered_candidate_tokens against this exact inventory: {token_inventory}.\n"
        "4. Only after the set matches exactly with no duplicates, return the JSON.\n"
    )
    return system, user


def _response_format() -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "retrieval_listwise_rerank",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidate_count_expected", "ordered_candidate_tokens", "rationale_tags"],
                "properties": {
                    "candidate_count_expected": {
                        "type": "integer",
                        "minimum": 1,
                    },
                    "ordered_candidate_tokens": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "rationale_tags": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": list(ALLOWED_RATIONALE_TAGS),
                            },
                            "minItems": 1,
                            "maxItems": 4,
                        },
                    },
                },
            },
        },
    }


def _extract_raw_text(resp: Any) -> str:
    raw_text = getattr(resp, "output_text", None) or ""
    if raw_text:
        return raw_text
    try:
        return json.dumps(resp.model_dump(), ensure_ascii=False)
    except Exception:
        return ""


def _response_status(resp: Any) -> str:
    return str(getattr(resp, "status", "") or "").strip()


def _response_incomplete_reason(resp: Any) -> str:
    details = getattr(resp, "incomplete_details", None)
    if details is None and hasattr(resp, "model_dump"):
        try:
            dumped = resp.model_dump()
            if isinstance(dumped, dict):
                details = dumped.get("incomplete_details")
        except Exception:
            details = None
    if isinstance(details, dict):
        return str(details.get("reason") or "").strip()
    return str(getattr(details, "reason", "") or "").strip()


def _extract_output_blocks_text(resp: Any) -> str:
    chunks: List[str] = []
    for item in getattr(resp, "output", None) or []:
        for block in getattr(item, "content", None) or []:
            parsed = getattr(block, "parsed", None)
            if parsed is not None:
                try:
                    return json.dumps(_parsed_response_to_dict(parsed), ensure_ascii=False)
                except Exception:
                    pass
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


def _strip_json_code_fence(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if not lines:
        return text
    first = lines[0].strip()
    if not first.startswith("```"):
        return text
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _parse_json(raw_text: str) -> Dict[str, Any]:
    parsed = json.loads(_strip_json_code_fence(raw_text))
    if not isinstance(parsed, dict):
        raise ValueError("reranker response must be a JSON object")
    return parsed


def _parsed_response_to_dict(parsed: Any) -> Dict[str, Any]:
    if isinstance(parsed, ListwiseRerankResponse):
        return parsed.model_dump(mode="json")
    if isinstance(parsed, dict):
        return parsed
    if hasattr(parsed, "model_dump"):
        dumped = parsed.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    raise ValueError("reranker parsed response must be a JSON object")


def _extract_parsed_payload(resp: Any) -> Tuple[Optional[Dict[str, Any]], str]:
    parsed_output = getattr(resp, "output_parsed", None)
    if parsed_output is not None:
        return _parsed_response_to_dict(parsed_output), ""
    raw_text = getattr(resp, "output_text", None) or ""
    if isinstance(raw_text, str) and raw_text.strip():
        return _parse_json(raw_text), raw_text
    block_text = _extract_output_blocks_text(resp)
    if block_text:
        return _parse_json(block_text), block_text
    return None, ""


def _normalize_response(
    *,
    parsed: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    token_to_id: Dict[str, str],
) -> Tuple[List[str], Dict[str, List[str]], str, Dict[str, Any]]:
    baseline_order = _stable_baseline_order(candidates)
    valid_tokens = set(token_to_id)
    raw_tokens = parsed.get("ordered_candidate_tokens")
    declared_count = parsed.get("candidate_count_expected")
    fallback_reason = ""
    declared_count_matches_input = isinstance(declared_count, int) and int(declared_count) == len(baseline_order)
    if not isinstance(declared_count, int):
        fallback_reason = "missing_or_invalid_candidate_count_expected"
    elif int(declared_count) != len(baseline_order):
        fallback_reason = "candidate_count_mismatch"
    if not isinstance(raw_tokens, list):
        raw_tokens = []
        fallback_reason = "missing_or_invalid_ordered_candidate_tokens"
    raw_tokens_str = [str(item).strip() for item in raw_tokens if str(item).strip()]
    raw_unique_tokens = set(raw_tokens_str)
    extra_tokens = sorted([token for token in raw_unique_tokens if token not in valid_tokens])
    missing_tokens = sorted([token for token in valid_tokens if token not in raw_unique_tokens])
    duplicate_count = max(0, len(raw_tokens_str) - len(raw_unique_tokens))
    exact_set_match = not extra_tokens and not missing_tokens and duplicate_count == 0
    ordered: List[str] = []
    seen_tokens: set[str] = set()
    for item in raw_tokens:
        token = str(item).strip()
        if not token or token in seen_tokens or token not in valid_tokens:
            continue
        ordered.append(str(token_to_id[token]))
        seen_tokens.add(token)
    validation = {
        "exact_set_match": exact_set_match,
        "declared_candidate_count": declared_count,
        "declared_candidate_count_matches_input": declared_count_matches_input,
        "missing_ids": [str(token_to_id[token]) for token in missing_tokens],
        "extra_ids": extra_tokens,
        "missing_tokens": missing_tokens,
        "extra_tokens": extra_tokens,
        "duplicate_count": duplicate_count,
        "input_candidate_count": len(baseline_order),
        "returned_candidate_count": len(raw_tokens_str),
        "returned_unique_candidate_count": len(raw_unique_tokens),
    }
    if not exact_set_match:
        ordered = list(baseline_order)
        fallback_reason = fallback_reason or "candidate_id_set_mismatch"
    elif not ordered:
        ordered = list(baseline_order)
        fallback_reason = fallback_reason or "empty_or_invalid_ranking"
    raw_tags = parsed.get("rationale_tags")
    tags_out: Dict[str, List[str]] = {}
    if exact_set_match and isinstance(raw_tags, list):
        for entry in raw_tags:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("token") or "").strip()
            tags = entry.get("tags")
            if key not in valid_tokens or not isinstance(tags, list):
                continue
            clean: List[str] = []
            for t in tags:
                tag = str(t).strip()
                if tag in ALLOWED_RATIONALE_TAGS and tag not in clean:
                    clean.append(tag)
                if len(clean) >= 4:
                    break
            if clean:
                tags_out[str(token_to_id[key])] = clean
    elif exact_set_match and isinstance(raw_tags, dict):
        for token, tags in raw_tags.items():
            key = str(token).strip()
            if key not in valid_tokens or not isinstance(tags, list):
                continue
            clean: List[str] = []
            for t in tags:
                tag = str(t).strip()
                if tag in ALLOWED_RATIONALE_TAGS and tag not in clean:
                    clean.append(tag)
                if len(clean) >= 4:
                    break
            if clean:
                tags_out[str(token_to_id[key])] = clean
    return ordered, tags_out, fallback_reason, validation


def _compute_prompt_hash(system: str, user: str, prompt_template_id: str) -> str:
    payload = {
        "prompt_template_id": prompt_template_id,
        "system": system,
        "user": user,
        "allowed_rationale_tags": list(ALLOWED_RATIONALE_TAGS),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _model_supports_temperature(model_id: str) -> bool:
    model = str(model_id or "").strip().lower()
    return not model.startswith("gpt-5")


def _model_supports_reasoning_controls(model_id: str) -> bool:
    model = str(model_id or "").strip().lower()
    return model.startswith("gpt-5") or model.startswith("o")


def _cache_path(cache_dir: Optional[str], cache_key: str) -> Optional[Path]:
    if not cache_dir:
        return None
    path = Path(cache_dir).expanduser().resolve() / f"{cache_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _failure_record_path(cache_dir: Optional[str], cache_key: str) -> Path:
    base = Path(cache_dir).expanduser().resolve() if cache_dir else (Path.cwd() / ".llm_rerank_failures").resolve()
    path = base / "failures" / f"{cache_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_failure_record(
    *,
    cache_dir: Optional[str],
    cache_key: str,
    payload: Dict[str, Any],
) -> str:
    path = _failure_record_path(cache_dir, cache_key)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _raise_validation_error(
    *,
    reason: str,
    cache_dir: Optional[str],
    cache_key: str,
    payload: Dict[str, Any],
    metadata: Dict[str, Any],
) -> None:
    record_path = _write_failure_record(cache_dir=cache_dir, cache_key=cache_key, payload=payload)
    raise LLMRerankValidationError(
        f"LLM reranker validation failed: {reason}. Record: {record_path}",
        record_path=record_path,
        metadata=metadata,
    )


def rerank_candidates_listwise(
    *,
    query: str,
    candidates: List[Dict[str, Any]],
    model_id: str,
    max_output_tokens: int = 3000,
    api_key: Optional[str] = None,
    prompt_template_id: str = _DEFAULT_TEMPLATE_ID,
    cache_dir: Optional[str] = None,
) -> Dict[str, Any]:
    baseline_order = _stable_baseline_order(candidates)
    token_to_id, id_to_token = _build_prompt_token_maps(candidates)
    if not baseline_order:
        return {
            "ordered_candidate_ids": [],
            "rationale_tags": {},
            "metadata": {
                "cache_hit": False,
                "fallback_reason": "no_candidates",
                "model_id": model_id,
                "prompt_template_id": prompt_template_id,
                "prompt_hash": "",
            },
        }

    prompt_template_id = str(prompt_template_id or _DEFAULT_TEMPLATE_ID).strip() or _DEFAULT_TEMPLATE_ID
    system, user = _build_messages(
        query=query,
        candidates=candidates,
        prompt_template_id=prompt_template_id,
        id_to_token=id_to_token,
    )
    prompt_hash = _compute_prompt_hash(system, user, prompt_template_id)
    cache_payload = {
        "model_id": model_id,
        "query": str(query or ""),
        "candidates": _candidate_payload(candidates, id_to_token=id_to_token),
        "prompt_hash": prompt_hash,
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    cpath = _cache_path(cache_dir, cache_key)
    if cpath and cpath.exists():
        cached = json.loads(cpath.read_text(encoding="utf-8"))
        parsed_cached = cached.get("parsed") if isinstance(cached, dict) else None
        if isinstance(parsed_cached, dict):
            ordered, tags, fallback_reason, validation = _normalize_response(
                parsed=parsed_cached,
                candidates=candidates,
                token_to_id=token_to_id,
            )
            metadata = {
                "cache_hit": True,
                "fallback_reason": fallback_reason or str(cached.get("fallback_reason") or ""),
                "model_id": model_id,
                "prompt_template_id": prompt_template_id,
                "prompt_hash": prompt_hash,
                **validation,
            }
            if metadata["fallback_reason"]:
                _raise_validation_error(
                    reason=str(metadata["fallback_reason"]),
                    cache_dir=cache_dir,
                    cache_key=cache_key,
                    payload={
                        "cache_key": cache_key,
                        "source": "cache",
                        "model_id": model_id,
                        "prompt_template_id": prompt_template_id,
                        "prompt_hash": prompt_hash,
                        "query": str(query or ""),
                        "candidates": _candidate_payload(candidates, id_to_token=id_to_token),
                        "prompt_token_map": token_to_id,
                        "parsed": parsed_cached,
                        "metadata": metadata,
                    },
                    metadata=metadata,
                )
            return {
                "ordered_candidate_ids": ordered,
                "rationale_tags": tags,
                "metadata": metadata,
            }

    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=api_key)
    parse_kwargs: Dict[str, Any] = {
        "model": model_id,
        "max_output_tokens": int(max_output_tokens),
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "text_format": ListwiseRerankResponse,
        "text": {"verbosity": "low"},
    }
    if _model_supports_temperature(model_id):
        parse_kwargs["temperature"] = 0
    if _model_supports_reasoning_controls(model_id):
        parse_kwargs["reasoning"] = {"effort": "low"}
    fallback_reason = ""
    resp = client.responses.parse(**parse_kwargs)

    raw_text = _extract_raw_text(resp)
    parsed: Dict[str, Any]
    try:
        extracted_parsed, extracted_text = _extract_parsed_payload(resp)
        if extracted_parsed is None:
            incomplete_reason = _response_incomplete_reason(resp)
            status = _response_status(resp)
            if incomplete_reason:
                raise ValueError(f"incomplete_response:{incomplete_reason}")
            if status and status != "completed":
                raise ValueError(f"response_status:{status}")
            raise ValueError("no_parseable_output")
        parsed = _parsed_response_to_dict(ListwiseRerankResponse.model_validate(extracted_parsed))
        if extracted_text:
            raw_text = extracted_text
    except Exception:
        incomplete_reason = _response_incomplete_reason(resp)
        status = _response_status(resp)
        response_failure_reason = "invalid_json_response"
        if incomplete_reason:
            response_failure_reason = f"incomplete_response_{incomplete_reason}"
        elif status and status != "completed":
            response_failure_reason = f"response_status_{status}"
        metadata = {
            "cache_hit": False,
            "fallback_reason": response_failure_reason,
            "model_id": model_id,
            "prompt_template_id": prompt_template_id,
            "prompt_hash": prompt_hash,
            "response_status": status,
            "incomplete_reason": incomplete_reason,
            "exact_set_match": False,
            "declared_candidate_count": None,
            "declared_candidate_count_matches_input": False,
            "missing_ids": list(baseline_order),
            "missing_tokens": sorted(token_to_id.keys()),
            "extra_ids": [],
            "extra_tokens": [],
            "duplicate_count": 0,
            "input_candidate_count": len(baseline_order),
            "returned_candidate_count": 0,
            "returned_unique_candidate_count": 0,
        }
        _raise_validation_error(
            reason=response_failure_reason,
            cache_dir=cache_dir,
            cache_key=cache_key,
            payload={
                "cache_key": cache_key,
                "source": "live_response",
                "model_id": model_id,
                "prompt_template_id": prompt_template_id,
                "prompt_hash": prompt_hash,
                "query": str(query or ""),
                "candidates": _candidate_payload(candidates, id_to_token=id_to_token),
                "prompt_token_map": token_to_id,
                "raw_text": raw_text,
                "metadata": metadata,
            },
            metadata=metadata,
        )
    ordered, tags, normalize_fallback, validation = _normalize_response(
        parsed=parsed,
        candidates=candidates,
        token_to_id=token_to_id,
    )
    if normalize_fallback:
        fallback_reason = normalize_fallback
    metadata = {
        "cache_hit": False,
        "fallback_reason": fallback_reason,
        "model_id": model_id,
        "prompt_template_id": prompt_template_id,
        "prompt_hash": prompt_hash,
        **validation,
    }
    if fallback_reason:
        _raise_validation_error(
            reason=fallback_reason,
            cache_dir=cache_dir,
            cache_key=cache_key,
            payload={
                "cache_key": cache_key,
                "source": "live_response",
                "model_id": model_id,
                "prompt_template_id": prompt_template_id,
                "prompt_hash": prompt_hash,
                "query": str(query or ""),
                "candidates": _candidate_payload(candidates, id_to_token=id_to_token),
                "prompt_token_map": token_to_id,
                "raw_text": raw_text,
                "parsed": parsed,
                "metadata": metadata,
            },
            metadata=metadata,
        )

    if cpath:
        cpath.write_text(
            json.dumps(
                {
                    "cache_key": cache_key,
                    "model_id": model_id,
                    "prompt_template_id": prompt_template_id,
                    "prompt_hash": prompt_hash,
                    "parsed": parsed,
                    "fallback_reason": fallback_reason,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    return {
        "ordered_candidate_ids": ordered,
        "rationale_tags": tags,
        "metadata": metadata,
    }
