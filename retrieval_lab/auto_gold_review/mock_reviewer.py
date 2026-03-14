from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from retrieval_lab.auto_gold_review.schema import GoldReviewResponse


@dataclass
class MockGoldChunkReviewer:
    responses_by_query_id: Dict[str, GoldReviewResponse] = field(default_factory=dict)

    def review(
        self,
        *,
        question: str,
        expected_answer_summary: str,
        notes: str,
        query_metadata: Dict[str, object],
        candidates: List[Dict[str, object]],
    ) -> GoldReviewResponse:
        query_id = str(query_metadata.get("query_id") or "")
        if query_id in self.responses_by_query_id:
            return self.responses_by_query_id[query_id]
        first = str((candidates[0] or {}).get("chunk_id") or "") if candidates else ""
        return GoldReviewResponse(
            required_gold=[first] if first else [],
            supporting_gold=[],
            required_gold_rationale={first: "Top candidate chosen by mock reviewer."} if first else {},
            confidence="high" if first else "low",
            review_flags=[] if first else ["no_clear_required_anchor"],
            needs_human_review=not bool(first),
        )
