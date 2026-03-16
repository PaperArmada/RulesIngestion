from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from retrieval_lab.answer_eval.schema import (
    ANSWER_JSON_SCHEMA,
    AnswerResponse,
    parse_answer_response,
)


def _parsed_response_to_dict(parsed: Any) -> Dict[str, Any]:
    if isinstance(parsed, dict):
        return parsed
    if hasattr(parsed, "model_dump"):
        dumped = parsed.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    raise ValueError("answer-eval parsed response must be a JSON object")


def _extract_output_blocks_text(resp: Any) -> str:
    """Extract text from Responses API output; prefer structured block.parsed when present."""
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


def _extract_raw_text(resp: Any) -> str:
    """Get raw JSON string from response: output_parsed, then output_text, then output blocks."""
    parsed_output = getattr(resp, "output_parsed", None)
    if parsed_output is not None:
        try:
            return json.dumps(_parsed_response_to_dict(parsed_output), ensure_ascii=False)
        except Exception:
            pass
    raw_text = getattr(resp, "output_text", None) or ""
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text
    return _extract_output_blocks_text(resp)


def _render_evidence(evidence: List[Dict[str, Any]], *, max_chars_per_unit: int = 1200) -> str:
    lines: List[str] = []
    for ev in evidence:
        cid = str(ev.get("chunk_id") or "")
        text = str(ev.get("text") or "")
        if max_chars_per_unit > 0 and len(text) > max_chars_per_unit:
            text = text[: max_chars_per_unit].rstrip() + "…"
        lines.append(f"[{cid}]\n{text}".strip())
    return "\n\n".join(lines)


def _answer_eval_model_supports_reasoning(model_id: str) -> bool:
    """True if model accepts reasoning parameter (e.g. gpt-5.x, o-series)."""
    m = str(model_id or "").strip().lower()
    return m.startswith("gpt-5") or m.startswith("o")


@dataclass
class OpenAIAnswerGenerator:
    model_id: str
    max_output_tokens: int = 800
    api_key: Optional[str] = None
    # Reasoning effort: "none" (omit param), "low", "medium", "high". Only used when model supports it.
    reasoning_effort: str = "none"

    def generate(
        self,
        *,
        question: str,
        evidence: List[Dict[str, Any]],
        expected_answer_summary: str = "",
    ) -> AnswerResponse:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=self.api_key)

        system = (
            "You are a rules-lawyer assistant. "
            "Answer ONLY using the provided EvidenceUnits. "
            "If the evidence is insufficient, refuse."
        )
        user = (
            "Return STRICT JSON.\n\n"
            f"Question: {question.strip()}\n"
            f"Expected summary (for calibration only): {expected_answer_summary.strip()}\n\n"
            "EvidenceUnits (cite by ID in brackets):\n"
            f"{_render_evidence(evidence)}\n\n"
            "JSON requirements:\n"
            '- "answer": string (empty if refusing)\n'
            '- "citations": array of EvidenceUnit IDs you used (subset of provided IDs)\n'
            '- "refusal": boolean (true if insufficient evidence)\n'
            '- "uncertainty": optional string (brief)\n'
        )

        kwargs: Dict[str, Any] = {
            "model": self.model_id,
            "max_output_tokens": int(self.max_output_tokens),
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # gpt-5-mini/nano do not support temperature; only add for models that do.
        if "gpt-5-mini" not in self.model_id and "gpt-5-nano" not in self.model_id:
            kwargs["temperature"] = 0
        # Reasoning: only for models that support it; "none" => omit (no reasoning tokens).
        effort = str(self.reasoning_effort or "none").strip().lower()
        if _answer_eval_model_supports_reasoning(self.model_id) and effort and effort != "none":
            kwargs["reasoning"] = {"effort": effort}
        # Structured output: send schema so the API returns parseable JSON (Responses API).
        kwargs["response_format"] = {"type": "json_schema", "json_schema": ANSWER_JSON_SCHEMA}

        try:
            resp = client.responses.create(**kwargs)
        except TypeError as exc:
            if "response_format" not in str(exc):
                raise
            kwargs.pop("response_format", None)
            resp = client.responses.create(**kwargs)
        raw_text = _extract_raw_text(resp)
        if not raw_text:
            try:
                raw_text = json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception:
                raw_text = ""
        parsed, _debug = parse_answer_response(raw_text)
        return parsed

