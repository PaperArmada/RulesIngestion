"""Helpers for turning judge-supplied indices into a gold-labels JSON.

Workflow:
  1. Load gold_candidates.json (produced by build_candidate_pool).
  2. Judge writes a dict mapping query_id to required/supporting CANDIDATE
     INDICES (not unit IDs). Indices refer to the order of candidates in
     gold_candidates.json -> queries[qid].candidates.
  3. apply_judgments() resolves indices to unit_ids and writes
     gold_labels.json in the shape the eval harness consumes.

Indices keep judge responses compact (one int per item) and immune to
unit-id collisions or transcription errors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_pools(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def apply_judgments(
    pools: dict[str, Any],
    judgments: dict[str, dict[str, list[int]]],
    *,
    notes: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Translate {qid: {required: [i,...], supporting: [j,...]}} into gold.

    Indices that fall outside a query's candidate list are silently
    dropped (with a count in the per-query 'dropped_indices' field).
    """
    gold: dict[str, dict[str, Any]] = {}
    for qid, judgment in judgments.items():
        if qid not in pools:
            continue
        candidates = pools[qid]["candidates"]
        n = len(candidates)
        req_ids: list[str] = []
        sup_ids: list[str] = []
        dropped: list[int] = []
        for idx in judgment.get("required", []):
            if 0 <= idx < n:
                req_ids.append(candidates[idx]["unit_id"])
            else:
                dropped.append(idx)
        for idx in judgment.get("supporting", []):
            if 0 <= idx < n:
                # If a unit was already tagged required, don't also list it as supporting.
                uid = candidates[idx]["unit_id"]
                if uid not in req_ids:
                    sup_ids.append(uid)
            else:
                dropped.append(idx)
        entry: dict[str, Any] = {
            "required": req_ids,
            "supporting": sup_ids,
        }
        if notes and qid in notes:
            entry["notes"] = notes[qid]
        if dropped:
            entry["dropped_indices"] = dropped
        gold[qid] = entry
    return gold


def write_gold(gold: dict[str, dict[str, Any]], out_path: Path | str) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gold, indent=2, sort_keys=True))
