from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _stable_baseline_order(candidates: List[Dict[str, Any]]) -> List[str]:
    ranked = sorted(
        candidates,
        key=lambda c: (
            int(c.get("baseline_rank", 10**9)),
            str(c.get("candidate_id", "")),
        ),
    )
    return [str(c.get("candidate_id", "")) for c in ranked if str(c.get("candidate_id", "")).strip()]


def _candidate_payload(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for c in candidates:
        payload.append(
            {
                "candidate_id": str(c.get("candidate_id", "")),
                "baseline_rank": int(c.get("baseline_rank", 0)),
                "structural_path": list(c.get("structural_path") or []),
                "unit_type": str(c.get("unit_type", "")),
                "excerpt": str(c.get("excerpt", "")),
            }
        )
    return payload


def _render_candidates_for_prompt(candidates: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for c in candidates:
        candidate_id = str(c.get("candidate_id", "")).strip()
        baseline_rank = int(c.get("baseline_rank", 0))
        unit_type = str(c.get("unit_type", "")).strip()
        structural_path = " > ".join(str(x) for x in (c.get("structural_path") or []))
        excerpt = str(c.get("excerpt", "")).strip()
        lines.append(
            (
                f"[id={candidate_id} baseline_rank={baseline_rank} unit_type={unit_type} path={structural_path}]\n"
                f"{excerpt}"
            ).strip()
        )
    return "\n\n".join(lines)


def _build_messages(
    *,
    query: str,
    candidates: List[Dict[str, Any]],
    prompt_template_id: str,
) -> Tuple[str, str]:
    allowed = ", ".join(ALLOWED_RATIONALE_TAGS)
    system = (
        "You are a retrieval reranker for multihop rules questions. "
        "Reorder only the provided candidates by expected usefulness for answering the question. "
        "You must not invent candidate IDs and must output strict JSON only."
    )
    user = (
        f"Prompt template: {prompt_template_id}\n\n"
        f"Question:\n{query.strip()}\n\n"
        "Candidates:\n"
        f"{_render_candidates_for_prompt(candidates)}\n\n"
        "Output requirements:\n"
        '- Return JSON with keys: "ordered_candidate_ids", "rationale_tags".\n'
        "- ordered_candidate_ids: a full ordering over provided candidate IDs.\n"
        f"- rationale_tags: optional tag arrays keyed by candidate ID. Allowed tags: {allowed}.\n"
        "- Do not include any candidate ID that is not in the provided list.\n"
        "- Prefer evidence that helps complete multi-obligation chains over generic context.\n"
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
                "required": ["ordered_candidate_ids", "rationale_tags"],
                "properties": {
                    "ordered_candidate_ids": {
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


def _parse_json(raw_text: str) -> Dict[str, Any]:
    parsed = json.loads(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("reranker response must be a JSON object")
    return parsed


def _normalize_response(
    *,
    parsed: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> Tuple[List[str], Dict[str, List[str]], str]:
    baseline_order = _stable_baseline_order(candidates)
    valid_ids = set(baseline_order)
    raw_ids = parsed.get("ordered_candidate_ids")
    fallback_reason = ""
    if not isinstance(raw_ids, list):
        raw_ids = []
        fallback_reason = "missing_or_invalid_ordered_candidate_ids"
    ordered: List[str] = []
    seen: set[str] = set()
    for item in raw_ids:
        cid = str(item).strip()
        if not cid or cid in seen or cid not in valid_ids:
            continue
        ordered.append(cid)
        seen.add(cid)
    if not ordered:
        ordered = list(baseline_order)
        fallback_reason = fallback_reason or "empty_or_invalid_ranking"
    else:
        for cid in baseline_order:
            if cid not in seen:
                ordered.append(cid)
    raw_tags = parsed.get("rationale_tags")
    tags_out: Dict[str, List[str]] = {}
    if isinstance(raw_tags, dict):
        for cid, tags in raw_tags.items():
            key = str(cid).strip()
            if key not in valid_ids or not isinstance(tags, list):
                continue
            clean: List[str] = []
            for t in tags:
                tag = str(t).strip()
                if tag in ALLOWED_RATIONALE_TAGS and tag not in clean:
                    clean.append(tag)
                if len(clean) >= 4:
                    break
            if clean:
                tags_out[key] = clean
    return ordered, tags_out, fallback_reason


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


def _cache_path(cache_dir: Optional[str], cache_key: str) -> Optional[Path]:
    if not cache_dir:
        return None
    path = Path(cache_dir).expanduser().resolve() / f"{cache_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def rerank_candidates_listwise(
    *,
    query: str,
    candidates: List[Dict[str, Any]],
    model_id: str,
    max_output_tokens: int = 1200,
    api_key: Optional[str] = None,
    prompt_template_id: str = _DEFAULT_TEMPLATE_ID,
    cache_dir: Optional[str] = None,
) -> Dict[str, Any]:
    baseline_order = _stable_baseline_order(candidates)
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
    system, user = _build_messages(query=query, candidates=candidates, prompt_template_id=prompt_template_id)
    prompt_hash = _compute_prompt_hash(system, user, prompt_template_id)
    cache_payload = {
        "model_id": model_id,
        "query": str(query or ""),
        "candidates": _candidate_payload(candidates),
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
            ordered, tags, fallback_reason = _normalize_response(parsed=parsed_cached, candidates=candidates)
            return {
                "ordered_candidate_ids": ordered,
                "rationale_tags": tags,
                "metadata": {
                    "cache_hit": True,
                    "fallback_reason": fallback_reason or str(cached.get("fallback_reason") or ""),
                    "model_id": model_id,
                    "prompt_template_id": prompt_template_id,
                    "prompt_hash": prompt_hash,
                },
            }

    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=api_key)
    kwargs: Dict[str, Any] = {
        "model": model_id,
        "temperature": 0,
        "max_output_tokens": int(max_output_tokens),
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    fallback_reason = ""
    try:
        kwargs["response_format"] = _response_format()
    except Exception:
        pass
    try:
        resp = client.responses.create(**kwargs)
    except TypeError as exc:
        if "response_format" not in str(exc):
            raise
        kwargs.pop("response_format", None)
        resp = client.responses.create(**kwargs)

    raw_text = _extract_raw_text(resp)
    parsed: Dict[str, Any]
    try:
        parsed = _parse_json(raw_text)
    except Exception:
        parsed = {"ordered_candidate_ids": baseline_order, "rationale_tags": {}}
        fallback_reason = "invalid_json_response"
    ordered, tags, normalize_fallback = _normalize_response(parsed=parsed, candidates=candidates)
    if normalize_fallback:
        fallback_reason = normalize_fallback

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
        "metadata": {
            "cache_hit": False,
            "fallback_reason": fallback_reason,
            "model_id": model_id,
            "prompt_template_id": prompt_template_id,
            "prompt_hash": prompt_hash,
        },
    }
