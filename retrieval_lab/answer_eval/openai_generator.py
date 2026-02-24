from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from retrieval_lab.answer_eval.schema import ANSWER_JSON_SCHEMA, AnswerResponse, parse_answer_response


def _render_evidence(evidence: List[Dict[str, Any]], *, max_chars_per_unit: int = 1200) -> str:
    lines: List[str] = []
    for ev in evidence:
        cid = str(ev.get("chunk_id") or "")
        text = str(ev.get("text") or "")
        if max_chars_per_unit > 0 and len(text) > max_chars_per_unit:
            text = text[: max_chars_per_unit].rstrip() + "…"
        lines.append(f"[{cid}]\n{text}".strip())
    return "\n\n".join(lines)


@dataclass
class OpenAIAnswerGenerator:
    model_id: str
    max_output_tokens: int = 800
    api_key: Optional[str] = None

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
            "temperature": 0,
            "max_output_tokens": int(self.max_output_tokens),
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # Best-effort: ask for JSON schema. Some models/accounts may not support it.
        try:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": ANSWER_JSON_SCHEMA}
        except Exception:
            pass

        resp = client.responses.create(**kwargs)
        raw_text = getattr(resp, "output_text", None) or ""
        if not raw_text:
            # Fallback: attempt to stitch text outputs.
            try:
                raw_text = json.dumps(resp.model_dump(), ensure_ascii=False)
            except Exception:
                raw_text = ""
        parsed, _debug = parse_answer_response(raw_text)
        return parsed

