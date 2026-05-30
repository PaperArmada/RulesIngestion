"""Set-completion metrics for enumeration eval.

Enumeration correctness is set membership, not ranking: did you return exactly
the matching set? So we score set precision / recall / F1 and exact-set-match,
not MRR / recall@K.
"""

from __future__ import annotations


def set_scores(returned: set[str], gold: set[str]) -> dict[str, float]:
    if not returned and not gold:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "exact": 1.0,
                "n_returned": 0, "n_gold": 0}
    tp = len(returned & gold)
    precision = tp / len(returned) if returned else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact": 1.0 if returned == gold else 0.0,
        "n_returned": len(returned),
        "n_gold": len(gold),
    }
