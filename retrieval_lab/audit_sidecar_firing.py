"""B1.1 audit: quantify sidecar firing and expansion impact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from retrieval_lab.crossref_sidecar import build_crossref_sidecar, expand_ranked_with_sidecar
from retrieval_lab.substrate_loader import load_evidence_units


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tier_map_from_per_query(per_query_path: Path, model_id: str) -> Dict[str, str]:
    data = _load_json(per_query_path)
    rows = data.get(model_id, [])
    return {r.get("query_id", ""): r.get("tier", "NA") for r in rows if r.get("query_id")}


def _safe_rate(num: int, den: int) -> float:
    return float(num) / float(den) if den else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit crossref sidecar firing rate from retrieval outputs")
    parser.add_argument("--substrate-path", required=True, help="Path to substrate root")
    parser.add_argument("--document-id", required=True, help="Document id used for substrate loading")
    parser.add_argument("--retrieved-chunks", required=True, help="Path to retrieved_chunks.json")
    parser.add_argument("--per-query", required=True, help="Path to per_query.json (for tier mapping)")
    parser.add_argument("--model-id", default="all-mpnet-base-v2", help="Model key in retrieved/per_query")
    parser.add_argument("--anchor-top-k", type=int, default=10, help="Top-k anchors inspected for firing")
    parser.add_argument("--expand-top-k", type=int, default=10, help="Expansion anchor budget")
    parser.add_argument("--expand-per-hit", type=int, default=2, help="Expansion per anchor")
    parser.add_argument("--total-cap", type=int, default=20, help="Total expansion cap")
    parser.add_argument("--output-dir", required=True, help="Audit output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    corpus = load_evidence_units(Path(args.substrate_path).resolve(), args.document_id)
    sidecar = build_crossref_sidecar(corpus)

    retrieved = _load_json(Path(args.retrieved_chunks).resolve())
    by_model = retrieved.get("by_model", {})
    rows = by_model.get(args.model_id, [])
    if not rows:
        raise ValueError(f"Model {args.model_id} not found in retrieved_chunks by_model")

    tier_map = _tier_map_from_per_query(Path(args.per_query).resolve(), args.model_id)

    total_queries = 0
    total_anchors = 0
    anchors_with_edges = 0
    queries_with_firing = 0
    queries_with_additions = 0
    queries_with_gold_from_additions = 0
    added_candidates_total = 0
    added_into_topk_total = 0

    per_tier: Dict[str, Dict[str, int]] = {}
    samples_no_firing_t2: List[str] = []

    for row in rows:
        query_id = row.get("query_id", "")
        tier = tier_map.get(query_id, "NA")
        if tier not in per_tier:
            per_tier[tier] = {
                "queries": 0,
                "queries_with_firing": 0,
                "queries_with_additions": 0,
                "queries_with_gold_from_additions": 0,
            }
        per_tier[tier]["queries"] += 1

        retrieved_items = row.get("retrieved", [])
        ranked_ids = [it.get("chunk_id", "") for it in retrieved_items if it.get("chunk_id")]
        ranked_scores = [float(it.get("score", 0.0)) for it in retrieved_items if it.get("chunk_id")]
        if not ranked_ids:
            continue

        total_queries += 1
        anchors = ranked_ids[: max(0, args.anchor_top_k)]
        fired_count = sum(1 for cid in anchors if sidecar.get(cid))
        total_anchors += len(anchors)
        anchors_with_edges += fired_count
        query_fired = fired_count > 0
        if query_fired:
            queries_with_firing += 1
            per_tier[tier]["queries_with_firing"] += 1
        elif tier == "T2" and len(samples_no_firing_t2) < 8:
            samples_no_firing_t2.append(query_id)

        expanded_ids, _expanded_scores, provenance = expand_ranked_with_sidecar(
            ranked_ids=ranked_ids,
            score_list=ranked_scores,
            sidecar=sidecar,
            expand_top_k=args.expand_top_k,
            expand_per_hit=args.expand_per_hit,
            total_cap=args.total_cap,
        )
        added_ids = [p.get("chunk_id", "") for p in provenance if p.get("chunk_id")]
        added_set = set(added_ids)
        added_candidates_total += len(added_ids)
        if added_ids:
            queries_with_additions += 1
            per_tier[tier]["queries_with_additions"] += 1

        orig_topk = set(ranked_ids[: max(0, args.anchor_top_k)])
        expanded_topk = expanded_ids[: max(0, args.anchor_top_k)]
        added_into_topk = [cid for cid in expanded_topk if cid not in orig_topk]
        added_into_topk_total += len(added_into_topk)

        gold_set = set(row.get("gold_unit_ids", []) or [])
        added_gold = bool(added_set.intersection(gold_set))
        if added_gold:
            queries_with_gold_from_additions += 1
            per_tier[tier]["queries_with_gold_from_additions"] += 1

    report = {
        "model_id": args.model_id,
        "sidecar_units_with_edges": len(sidecar),
        "total_queries": total_queries,
        "anchor_top_k": args.anchor_top_k,
        "expand_top_k": args.expand_top_k,
        "expand_per_hit": args.expand_per_hit,
        "expand_total_cap": args.total_cap,
        "anchor_firing_rate": _safe_rate(anchors_with_edges, total_anchors),
        "query_firing_rate": _safe_rate(queries_with_firing, total_queries),
        "query_addition_rate": _safe_rate(queries_with_additions, total_queries),
        "query_added_gold_rate": _safe_rate(queries_with_gold_from_additions, total_queries),
        "avg_added_candidates_per_query": _safe_rate(added_candidates_total, total_queries),
        "avg_added_into_topk_per_query": _safe_rate(added_into_topk_total, total_queries),
        "counts": {
            "total_anchors": total_anchors,
            "anchors_with_edges": anchors_with_edges,
            "queries_with_firing": queries_with_firing,
            "queries_with_additions": queries_with_additions,
            "queries_with_gold_from_additions": queries_with_gold_from_additions,
            "added_candidates_total": added_candidates_total,
            "added_into_topk_total": added_into_topk_total,
        },
        "per_tier": per_tier,
        "samples_no_firing_t2": samples_no_firing_t2,
    }

    out_json = output_dir / f"B11_sidecar_firing_{args.model_id}.json"
    out_md = output_dir / f"B11_sidecar_firing_{args.model_id}.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append(f"# B1.1 Sidecar Firing Audit: {args.model_id}")
    lines.append("")
    lines.append(f"- Sidecar units with edges: {len(sidecar)}")
    lines.append(f"- Queries: {total_queries}")
    lines.append(f"- Anchor firing rate: {report['anchor_firing_rate']:.3f}")
    lines.append(f"- Query firing rate: {report['query_firing_rate']:.3f}")
    lines.append(f"- Query addition rate: {report['query_addition_rate']:.3f}")
    lines.append(f"- Query added-gold rate: {report['query_added_gold_rate']:.3f}")
    lines.append(f"- Avg added candidates/query: {report['avg_added_candidates_per_query']:.3f}")
    lines.append(f"- Avg added into top-{args.anchor_top_k}/query: {report['avg_added_into_topk_per_query']:.3f}")
    lines.append("")
    lines.append("## Per-tier")
    lines.append("")
    lines.append("| Tier | Queries | Firing | Additions | Added-gold |")
    lines.append("|------|---------|--------|-----------|-----------|")
    for tier in sorted(per_tier.keys()):
        r = per_tier[tier]
        lines.append(
            f"| {tier} | {r['queries']} | {r['queries_with_firing']} | "
            f"{r['queries_with_additions']} | {r['queries_with_gold_from_additions']} |"
        )
    if samples_no_firing_t2:
        lines.append("")
        lines.append("## Sample T2 queries with zero firing")
        lines.append("")
        for qid in samples_no_firing_t2:
            lines.append(f"- `{qid}`")

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {out_md}")
    print(f"Wrote: {out_json}")


if __name__ == "__main__":
    main()
