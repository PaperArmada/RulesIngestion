#!/usr/bin/env python3
"""
Sample benchmark queries and resolve each gold chunk to page + snippet for manual curation.

Usage (from repo root):
  uv run python scripts/sample_gold_for_curation.py --corpus phb --sample 5
  uv run python scripts/sample_gold_for_curation.py --corpus starfinder --sample 10 --seed 42
  uv run python scripts/sample_gold_for_curation.py --corpus sw --sample 5
  uv run python scripts/sample_gold_for_curation.py --corpus pf2e --review-artifact out/retrieval_lab/experiments/.../auto_gold_review.json --queue-only

Prints a report: for each sampled query, every gold_unit_id with 1-based page and
a short text snippet so the user can open the source PDF and decide keep/expand/delete.
See handoffs/HANDOFF-2026-02-12-benchmark-gold-curation.md.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# Repo root = parent of scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from retrieval_lab.gold_grounding import flatten_query_batches
from retrieval_lab.substrate_loader import load_evidence_units

CORPUS_CONFIG = {
    "phb": {
        "substrate_path": REPO_ROOT / "out/DnD_PHB_5.5",
        "document_id": "DnD_PHB_5.5",
        "query_batches": [
            "evals/retrieval/PHB5e/dnd_5_e_equivalent_rag_eval_queries.json",
        ],
    },
    "starfinder": {
        "substrate_path": REPO_ROOT / "out/StarFinderPlayerCore",
        "document_id": "StarFinderPlayerCore",
        "query_batches": [
            "evals/retrieval/StarFinderPlayerCore/batch_001.json",
            "evals/retrieval/StarFinderPlayerCore/batch_002_state.json",
            "evals/retrieval/StarFinderPlayerCore/batch_003_grounding.json",
            "evals/retrieval/StarFinderPlayerCore/batch_004_temporal.json",
            "evals/retrieval/StarFinderPlayerCore/batch_005_constraints.json",
            "evals/retrieval/StarFinderPlayerCore/batch_006_conceptual.json",
        ],
    },
    "sw": {
        "substrate_path": REPO_ROOT / "out/Swords&Wizardry",
        "document_id": "Swords&Wizardry",
        "query_batches": [
            "evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json",
        ],
    },
    "pf2e": {
        "substrate_path": REPO_ROOT / "out/Pathfinder2ePlayerCore",
        "document_id": "Pathfinder2ePlayerCore",
        "query_batches": [
            "evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_50q_benchmark.json",
        ],
    },
}

SNIPPET_LEN = 120


def _page_display(unit: dict) -> str:
    p = unit.get("page")
    if isinstance(p, int) and p >= 0:
        return f"Page {p + 1}"
    return "unknown page"


def _load_review_rows(path: Path, *, queue_only: bool) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    rows = payload.get("review_queue") if queue_only else payload.get("recommendations")
    if not rows:
        rows = payload.get("review_queue") or []
    return [row for row in rows if isinstance(row, dict)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample benchmark queries and resolve gold chunks to page + snippet.")
    parser.add_argument("--corpus", choices=list(CORPUS_CONFIG), required=True, help="Corpus to sample from")
    parser.add_argument("--sample", type=int, default=5, help="Number of queries to sample (default 5)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--review-artifact", type=str, default=None, help="Optional auto_gold_review.json path")
    parser.add_argument("--queue-only", action="store_true", help="When using --review-artifact, sample only review_queue rows")
    args = parser.parse_args()

    cfg = CORPUS_CONFIG[args.corpus]
    batch_paths = [str(REPO_ROOT / p) for p in cfg["query_batches"]]
    substrate_path = cfg["substrate_path"]
    document_id = cfg["document_id"]

    if not substrate_path.is_dir():
        print(f"Substrate not found: {substrate_path}", file=sys.stderr)
        sys.exit(1)

    queries, _ = flatten_query_batches(batch_paths)
    query_by_id = {str(q.get("id") or ""): q for q in queries if q.get("id")}
    review_rows = _load_review_rows(Path(args.review_artifact), queue_only=bool(args.queue_only)) if args.review_artifact else []
    if review_rows:
        sample_pool = review_rows
    else:
        with_gold = [q for q in queries if q.get("gold_unit_ids")]
        if not with_gold:
            print("No queries with gold_unit_ids found.", file=sys.stderr)
            sys.exit(1)
        sample_pool = with_gold

    k = min(args.sample, len(sample_pool))
    if args.seed is not None:
        random.seed(args.seed)
    sampled = random.sample(sample_pool, k)

    units = load_evidence_units(str(substrate_path), document_id)
    unit_by_id = {u["id"]: u for u in units}

    print(f"# Curation sample: corpus={args.corpus} n={k} (seed={args.seed})")
    print()

    for row in sampled:
        if args.review_artifact:
            qid = str(row.get("query_id") or "")
            q = query_by_id.get(qid, {})
            question = row.get("question") or q.get("question") or ""
            summary = row.get("expected_answer_summary") or q.get("expected_answer_summary") or q.get("answer") or ""
            source_page = q.get("source_page")
            required = set(row.get("proposed_required_gold") or [])
            supporting = set(row.get("proposed_supporting_gold") or [])
            gold_ids = list(dict.fromkeys(list(required) + list(supporting)))
            confidence = row.get("confidence")
            queue_reasons = list(row.get("queue_reasons") or [])
            review_flags = list(row.get("review_flags") or [])
            candidate_by_id = {
                str(candidate.get("chunk_id") or ""): candidate
                for candidate in (row.get("top_candidates") or [])
                if str(candidate.get("chunk_id") or "").strip()
            }
        else:
            q = row
            qid = q.get("id", "")
            question = q.get("question", "")
            summary = q.get("expected_answer_summary") or q.get("answer") or ""
            source_page = q.get("source_page")
            gold_ids = list(q.get("gold_unit_ids") or [])
            required = set(q.get("required_gold") or [])
            supporting = set(q.get("supporting_gold") or [])
            confidence = None
            queue_reasons = []
            review_flags = []
            candidate_by_id = {}

        print(f"## Query id: {qid}")
        print(f"**Question:** {question}")
        print(f"**Expected answer summary:** {summary[:400]}{'...' if len(summary) > 400 else ''}")
        if source_page is not None and source_page != "":
            print(f"**Query-level source page:** {source_page}")
        if confidence is not None:
            print(f"**Confidence:** {confidence}")
        if queue_reasons:
            print(f"**Queue reasons:** {', '.join(queue_reasons)}")
        if review_flags:
            print(f"**Review flags:** {', '.join(review_flags)}")
        print()
        print("**Gold chunks:**")
        for uid in gold_ids:
            u = unit_by_id.get(uid)
            if u is None:
                candidate = candidate_by_id.get(uid, {})
                page = candidate.get("page")
                page_str = f"Page {page + 1}" if isinstance(page, int) and page >= 0 else "(unit not in corpus)"
                print(f"  - Unit ID: `{uid[:20]}...`  {page_str}")
                text = str(candidate.get("text") or "").replace("\n", " ").strip()
                if text:
                    snippet = text[:SNIPPET_LEN] + ("..." if len(text) > SNIPPET_LEN else "")
                    print(f"    Snippet: {snippet}")
                continue
            page_str = _page_display(u)
            text = (u.get("text") or "").replace("\n", " ").strip()
            snippet = text[:SNIPPET_LEN] + ("..." if len(text) > SNIPPET_LEN else "")
            role = "required" if uid in required else ("supporting" if uid in supporting else "")
            role_str = f" [{role}]" if role else ""
            print(f"  - Unit ID: `{uid[:24]}...`  {page_str}{role_str}")
            print(f"    Snippet: {snippet}")
        print()

    print("---")
    print("Reply with keep / expand (add unit IDs) / delete (unit IDs to remove) per query.")


if __name__ == "__main__":
    main()
