from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class AnswerResponse:
    answer: str
    citations: List[str]
    refusal: bool = False
    uncertainty: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": list(self.citations),
            "refusal": bool(self.refusal),
            "uncertainty": self.uncertainty,
        }


ANSWER_JSON_SCHEMA: Dict[str, Any] = {
    "name": "retrieval_lab_answer",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "refusal": {"type": "boolean"},
            "uncertainty": {"type": "string"},
        },
        "required": ["answer", "citations", "refusal"],
    },
    "strict": True,
}


def _strip_json_code_fence(raw_text: str) -> str:
    """Strip optional markdown code fence so we can parse JSON from model output."""
    text = str(raw_text or "").strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if not lines:
        return text
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return "\n".join(lines[1:]).strip() if lines[0].strip().startswith("```") else text


def parse_answer_response(raw_text: str) -> Tuple[AnswerResponse, Dict[str, Any]]:
    """Parse an AnswerResponse from raw model text.

    Returns (response, debug) where debug includes parse errors and the raw text.
    """
    debug: Dict[str, Any] = {"raw_text": raw_text}
    text_to_parse = _strip_json_code_fence(raw_text)
    try:
        payload = json.loads(text_to_parse)
    except Exception as e:
        debug["parse_error"] = str(e)
        return AnswerResponse(answer="", citations=[], refusal=True, uncertainty="parse_error"), debug

    if not isinstance(payload, dict):
        debug["parse_error"] = "not_a_dict"
        return AnswerResponse(answer="", citations=[], refusal=True, uncertainty="parse_error"), debug

    answer = str(payload.get("answer") or "")
    citations_raw = payload.get("citations") or []
    citations: List[str] = []
    if isinstance(citations_raw, list):
        for c in citations_raw:
            s = str(c).strip()
            if s:
                citations.append(s)
    refusal = bool(payload.get("refusal", False))
    uncertainty = str(payload.get("uncertainty") or "")
    return AnswerResponse(answer=answer, citations=citations, refusal=refusal, uncertainty=uncertainty), debug

