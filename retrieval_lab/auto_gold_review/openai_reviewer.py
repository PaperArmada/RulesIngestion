from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from retrieval_lab.auto_gold_review.schema import (
    GOLD_REVIEW_JSON_SCHEMA,
    GoldReviewResponse,
    parse_gold_review_response,
)


def _stable_candidate_order(candidates: List[Dict[str, Any]]) -> List[str]:
    ranked = sorted(
        candidates,
        key=lambda c: (
            int(c.get("rank") or 10**9),
            str(c.get("chunk_id") or ""),
        ),
    )
    return [str(c.get("chunk_id") or "") for c in ranked if str(c.get("chunk_id") or "").strip()]


def _alpha_prefix(index: int) -> str:
    out: List[str] = []
    n = int(index)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out.append(chr(ord("A") + rem))
    return "".join(reversed(out)) or "A"


def _build_prompt_token_maps(candidates: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str]]:
    ordered_ids = _stable_candidate_order(candidates)
    width = max(3, len(str(len(ordered_ids))))
    token_to_id: Dict[str, str] = {}
    id_to_token: Dict[str, str] = {}
    for idx, chunk_id in enumerate(ordered_ids, start=1):
        token = f"{_alpha_prefix(idx)}{idx:0{width}d}"
        token_to_id[token] = chunk_id
        id_to_token[chunk_id] = token
    return token_to_id, id_to_token


def _candidate_payload(candidates: List[Dict[str, Any]], *, id_to_token: Dict[str, str]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for candidate in candidates:
        chunk_id = str(candidate.get("chunk_id") or "").strip()
        payload.append(
            {
                "prompt_token": str(id_to_token.get(chunk_id, "")),
                "chunk_id": chunk_id,
                "rank": int(candidate.get("rank") or 0),
                "score": float(candidate.get("score") or 0.0),
                "page": candidate.get("page"),
                "structural_path": list(candidate.get("structural_path") or []),
                "source_unit_ids": list(candidate.get("source_unit_ids") or []),
                "text": str(candidate.get("text") or ""),
            }
        )
    return payload


def _parsed_response_to_dict(parsed: Any) -> Dict[str, Any]:
    if isinstance(parsed, dict):
        return parsed
    if hasattr(parsed, "model_dump"):
        dumped = parsed.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    raise ValueError("gold reviewer parsed response must be a JSON object")


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


def _extract_parsed_payload(resp: Any) -> Tuple[Optional[str], str]:
    parsed_output = getattr(resp, "output_parsed", None)
    if parsed_output is not None:
        try:
            return json.dumps(_parsed_response_to_dict(parsed_output), ensure_ascii=False), "output_parsed"
        except Exception:
            pass
    raw_text = getattr(resp, "output_text", None) or ""
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text, "output_text"
    block_text = _extract_output_blocks_text(resp)
    if block_text:
        return block_text, "output_blocks"
    return None, ""


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


def _render_candidates(candidates: List[Dict[str, Any]], *, id_to_token: Dict[str, str]) -> str:
    blocks: List[str] = []
    for candidate in candidates:
        chunk_id = str(candidate.get("chunk_id") or "")
        prompt_token = str(id_to_token.get(chunk_id, ""))
        rank = int(candidate.get("rank") or 0)
        score = float(candidate.get("score") or 0.0)
        page = candidate.get("page")
        structural_path = " > ".join(str(x) for x in (candidate.get("structural_path") or []))
        text = str(candidate.get("text") or "")
        header = (
            f"[token={prompt_token} rank={rank} score={score:.4f} page={page} path={structural_path}]"
        ).strip()
        blocks.append(f"{header}\n{text}".strip())
    return "\n\n".join(blocks)


def _map_prompt_tokens_to_candidate_ids(
    parsed: GoldReviewResponse,
    *,
    token_to_id: Dict[str, str],
    id_to_token: Dict[str, str],
    raw_text: str,
    extraction_source: str,
    response_status: str,
    incomplete_reason: str,
    candidates: List[Dict[str, Any]],
) -> GoldReviewResponse:
    def _map_items(items: List[str]) -> Tuple[List[str], List[str]]:
        mapped: List[str] = []
        invalid: List[str] = []
        for item in items:
            token = str(item).strip()
            if not token:
                continue
            candidate_id = token_to_id.get(token)
            if candidate_id:
                mapped.append(candidate_id)
            else:
                invalid.append(token)
        return mapped, invalid

    mapped_required, invalid_required = _map_items(parsed.required_gold)
    mapped_supporting, invalid_supporting = _map_items(parsed.supporting_gold)
    rationale: Dict[str, str] = {}
    invalid_rationale_keys: List[str] = []
    for key, value in (parsed.required_gold_rationale or {}).items():
        token = str(key).strip()
        candidate_id = token_to_id.get(token)
        if candidate_id:
            rationale[candidate_id] = str(value).strip()
        elif token:
            invalid_rationale_keys.append(token)

    review_flags = list(parsed.review_flags or [])
    invalid_references = invalid_required + invalid_supporting + invalid_rationale_keys
    if invalid_references and "invalid_candidate_reference" not in review_flags:
        review_flags.append("invalid_candidate_reference")

    metadata = dict(parsed.metadata or {})
    metadata.update(
        {
            "prompt_token_map": dict(token_to_id),
            "candidate_payload": _candidate_payload(candidates, id_to_token=id_to_token),
            "raw_required_tokens": list(parsed.required_gold or []),
            "raw_supporting_tokens": list(parsed.supporting_gold or []),
            "mapped_required_gold": mapped_required,
            "mapped_supporting_gold": mapped_supporting,
            "invalid_references": invalid_references,
            "response_status": response_status,
            "incomplete_reason": incomplete_reason,
            "extraction_source": extraction_source,
        }
    )
    if raw_text and ("parse_error" in review_flags or invalid_references):
        metadata["raw_response_text"] = raw_text

    return GoldReviewResponse(
        required_gold=mapped_required,
        supporting_gold=mapped_supporting,
        required_gold_rationale=rationale,
        confidence=parsed.confidence,
        review_flags=review_flags,
        needs_human_review=parsed.needs_human_review,
        notes=parsed.notes,
        metadata=metadata,
    )


@dataclass
class OpenAIGoldChunkReviewer:
    model_id: str
    max_output_tokens: int = 900
    api_key: Optional[str] = None

    def review(
        self,
        *,
        question: str,
        expected_answer_summary: str,
        notes: str,
        query_metadata: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> GoldReviewResponse:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=self.api_key)
        token_to_id, id_to_token = _build_prompt_token_maps(candidates)
        token_inventory = ", ".join(token_to_id.keys())
        system = (
            "You are reviewing retrieval candidates to assign benchmark gold evidence. "
            "Choose the minimal required anchors needed to operationalize the answer. "
            "Supporting gold may add context or cover secondary facets. "
            "You must only choose prompt tokens from the provided candidates. "
            "Do not reproduce chunk IDs."
        )
        user = (
            "Return STRICT JSON.\n\n"
            f"Query ID: {str(query_metadata.get('query_id') or '').strip()}\n"
            f"Tier: {str(query_metadata.get('tier') or '').strip()}\n"
            f"Suite: {str(query_metadata.get('suite') or '').strip()}\n"
            f"Question type: {str(query_metadata.get('question_type') or '').strip()}\n"
            f"Question: {question.strip()}\n"
            f"Expected answer summary: {expected_answer_summary.strip()}\n"
            f"Notes: {notes.strip()}\n\n"
            f"Candidate token inventory: {token_inventory}\n\n"
            "Candidate chunks:\n"
            f"{_render_candidates(candidates, id_to_token=id_to_token)}\n\n"
            "Review rules:\n"
            "- Use prompt tokens, not chunk IDs, in required_gold and supporting_gold.\n"
            "- required_gold must be the minimal prompt tokens needed for a correct grounded answer.\n"
            "- supporting_gold may include extra prompt tokens that help but are not strictly required.\n"
            "- required_gold_rationale must explain why each required prompt token is necessary.\n"
            "- confidence must be one of low, medium, high.\n"
            "- Set needs_human_review=true when the evidence is ambiguous, weak, or multi-part enough to warrant sampling.\n"
            "- Use review_flags for issues like multi_part_question, weak_anchor, close_second_choice, or no_clear_required_anchor.\n"
            "- Do not invent tokens, omit the token syntax, or copy long candidate hashes.\n"
        )
        kwargs: Dict[str, Any] = {
            "model": self.model_id,
            "temperature": 0,
            "max_output_tokens": int(self.max_output_tokens),
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": GOLD_REVIEW_JSON_SCHEMA}
        except Exception:
            pass
        try:
            resp = client.responses.create(**kwargs)
        except TypeError as exc:
            if "response_format" not in str(exc):
                raise
            kwargs.pop("response_format", None)
            resp = client.responses.create(**kwargs)
        raw_text, extraction_source = _extract_parsed_payload(resp)
        response_status = _response_status(resp)
        incomplete_reason = _response_incomplete_reason(resp)
        if not raw_text:
            try:
                raw_text = json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception:
                raw_text = ""
        parsed, debug = parse_gold_review_response(raw_text)
        parsed = GoldReviewResponse(
            required_gold=parsed.required_gold,
            supporting_gold=parsed.supporting_gold,
            required_gold_rationale=parsed.required_gold_rationale,
            confidence=parsed.confidence,
            review_flags=parsed.review_flags,
            needs_human_review=parsed.needs_human_review,
            notes=parsed.notes,
            metadata={
                "parse_debug": debug,
                "response_status": response_status,
                "incomplete_reason": incomplete_reason,
                "extraction_source": extraction_source,
            },
        )
        return _map_prompt_tokens_to_candidate_ids(
            parsed,
            token_to_id=token_to_id,
            id_to_token=id_to_token,
            raw_text=raw_text,
            extraction_source=extraction_source,
            response_status=response_status,
            incomplete_reason=incomplete_reason,
            candidates=candidates,
        )
