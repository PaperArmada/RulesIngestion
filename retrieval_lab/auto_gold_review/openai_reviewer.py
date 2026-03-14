from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from retrieval_lab.auto_gold_review.schema import (
    GOLD_REVIEW_JSON_SCHEMA,
    GoldReviewResponse,
    parse_gold_review_response,
)


def _render_candidates(candidates: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for candidate in candidates:
        chunk_id = str(candidate.get("chunk_id") or "")
        rank = int(candidate.get("rank") or 0)
        score = float(candidate.get("score") or 0.0)
        page = candidate.get("page")
        structural_path = " > ".join(str(x) for x in (candidate.get("structural_path") or []))
        text = str(candidate.get("text") or "")
        header = f"[rank={rank} id={chunk_id} score={score:.4f} page={page} path={structural_path}]".strip()
        blocks.append(f"{header}\n{text}".strip())
    return "\n\n".join(blocks)


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
        system = (
            "You are reviewing retrieval candidates to assign benchmark gold evidence. "
            "Choose the minimal required anchors needed to operationalize the answer. "
            "Supporting gold may add context or cover secondary facets. "
            "You must only choose chunk IDs from the provided candidates."
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
            "Candidate chunks:\n"
            f"{_render_candidates(candidates)}\n\n"
            "Review rules:\n"
            "- required_gold must be the minimal chunk IDs needed for a correct grounded answer.\n"
            "- supporting_gold may include extra chunks that help but are not strictly required.\n"
            "- required_gold_rationale must explain why each required chunk is necessary.\n"
            "- confidence must be one of low, medium, high.\n"
            "- Set needs_human_review=true when the evidence is ambiguous, weak, or multi-part enough to warrant sampling.\n"
            "- Use review_flags for issues like multi_part_question, weak_anchor, close_second_choice, or no_clear_required_anchor.\n"
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
        raw_text = getattr(resp, "output_text", None) or ""
        if not raw_text:
            try:
                raw_text = json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception:
                raw_text = ""
        parsed, _debug = parse_gold_review_response(raw_text)
        return parsed
