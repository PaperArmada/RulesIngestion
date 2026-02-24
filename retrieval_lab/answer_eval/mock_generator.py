from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from retrieval_lab.answer_eval.schema import AnswerResponse


@dataclass
class MockAnswerGenerator:
    """Deterministic answer generator for tests.

    Strategy:
    - If any evidence is provided: cite the first chunk_id and answer with a stub.
    - If no evidence: refuse.
    """

    def generate(self, *, question: str, evidence: List[Dict[str, Any]], expected_answer_summary: str = "") -> AnswerResponse:
        _ = (question, expected_answer_summary)
        if not evidence:
            return AnswerResponse(answer="", citations=[], refusal=True, uncertainty="no_evidence")
        first_id = str(evidence[0].get("chunk_id") or "")
        cites = [first_id] if first_id else []
        return AnswerResponse(answer="stub", citations=cites, refusal=False, uncertainty="")

