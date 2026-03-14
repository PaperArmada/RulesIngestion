from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


VALID_CONFIDENCE = frozenset({"low", "medium", "high"})


@dataclass(frozen=True)
class GoldReviewResponse:
    required_gold: List[str]
    supporting_gold: List[str]
    required_gold_rationale: Dict[str, str]
    confidence: str = "low"
    review_flags: List[str] = field(default_factory=list)
    needs_human_review: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "required_gold": list(self.required_gold),
            "supporting_gold": list(self.supporting_gold),
            "required_gold_rationale": dict(self.required_gold_rationale),
            "confidence": self.confidence,
            "review_flags": list(self.review_flags),
            "needs_human_review": bool(self.needs_human_review),
            "notes": self.notes,
        }


GOLD_REVIEW_JSON_SCHEMA: Dict[str, Any] = {
    "name": "retrieval_lab_gold_review",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "required_gold": {
                "type": "array",
                "items": {"type": "string"},
            },
            "supporting_gold": {
                "type": "array",
                "items": {"type": "string"},
            },
            "required_gold_rationale": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "review_flags": {
                "type": "array",
                "items": {"type": "string"},
            },
            "needs_human_review": {"type": "boolean"},
            "notes": {"type": "string"},
        },
        "required": [
            "required_gold",
            "supporting_gold",
            "required_gold_rationale",
            "confidence",
            "review_flags",
            "needs_human_review",
        ],
    },
    "strict": True,
}


def parse_gold_review_response(raw_text: str) -> Tuple[GoldReviewResponse, Dict[str, Any]]:
    debug: Dict[str, Any] = {"raw_text": raw_text}
    try:
        payload = json.loads(raw_text)
    except Exception as e:
        debug["parse_error"] = str(e)
        return GoldReviewResponse([], [], {}, confidence="low", review_flags=["parse_error"], needs_human_review=True), debug

    if not isinstance(payload, dict):
        debug["parse_error"] = "not_a_dict"
        return GoldReviewResponse([], [], {}, confidence="low", review_flags=["parse_error"], needs_human_review=True), debug

    def _string_list(value: Any) -> List[str]:
        out: List[str] = []
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text:
                    out.append(text)
        return out

    required_gold = _string_list(payload.get("required_gold"))
    supporting_gold = _string_list(payload.get("supporting_gold"))
    rationales_raw = payload.get("required_gold_rationale")
    rationales: Dict[str, str] = {}
    if isinstance(rationales_raw, dict):
        for key, value in rationales_raw.items():
            k = str(key).strip()
            v = str(value).strip()
            if k and v:
                rationales[k] = v
    confidence = str(payload.get("confidence") or "low").strip().lower()
    if confidence not in VALID_CONFIDENCE:
        confidence = "low"
    review_flags = _string_list(payload.get("review_flags"))
    needs_human_review = bool(payload.get("needs_human_review", False))
    notes = str(payload.get("notes") or "")
    return (
        GoldReviewResponse(
            required_gold=required_gold,
            supporting_gold=supporting_gold,
            required_gold_rationale=rationales,
            confidence=confidence,
            review_flags=review_flags,
            needs_human_review=needs_human_review,
            notes=notes,
        ),
        debug,
    )
