"""
Comparative markdown report, metrics JSON, and glossary of metrics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _glossary_md() -> str:
    return """
## Glossary of Metrics

| Metric | Formula / Definition | Interpretation |
|--------|----------------------|----------------|
| **Recall@k** | (Number of gold units found in top-k) / (Total gold units per query), averaged over queries | Fraction of relevant evidence discoverable in the first k results. Higher is better. |
| **Hit@k** | Fraction of queries where at least one gold unit appears in top-k | Whether *any* relevant evidence surfaces per question. Simpler than recall. |
| **MRR** | Mean over queries of 1/rank of first gold hit; 0 if no gold in list | How high the first relevant result ranks. 1.0 = gold always at rank 1. |
| **Gold-in-Candidates** | Fraction of queries where any gold unit appears anywhere in the full ranked list | Ceiling check: if gold never appears, retrieval cannot succeed regardless of k. |
| **Grounding Coverage** | Fraction of queries where gold grounding found at least one EvidenceUnit | Measures eval set quality (and extraction coverage), not retrieval quality. |
| **Answer Similarity@k** | Mean cosine similarity between the query (expected_answer_summary) embedding and the embeddings of the top-k retrieved units | Model-agnostic relevance signal when gold IDs are uncertain (e.g. corpus-wide semantic grounding). |
| **Candidate Set Size** | Total number of EvidenceUnits in the corpus | Context for interpreting recall: larger corpus = harder retrieval problem. |

### Failure Types

| Type | Meaning |
|------|--------|
| **hit** | At least one gold unit appeared within the largest k evaluated. |
| **retrieval_miss** | Gold EvidenceUnit(s) exist but none appear in top-k for any k tested. |
| **rank_miss** | Gold was retrieved but ranked below the maximum k (e.g. beyond top-20). |
| **grounding_failure** | No EvidenceUnit could be mapped as gold for this query (eval set or extraction issue). |

### When to Worry

- **Low gold-in-candidates**: Either grounding is failing or the corpus does not contain the answer text; fix grounding or add evidence.
- **Low recall@k with high gold-in-candidates**: Retrieval or ranking is the bottleneck; consider better embeddings or hybrid retrieval.
- **Low grounding coverage**: Queries or expected_answer_summary do not align with EvidenceUnit text; review eval set or use semantic grounding.
"""


def generate_report(
    experiment_id: str,
    experiment_name: str,
    config: Dict[str, Any],
    corpus_stats: Dict[str, Any],
    grounding_summary: Dict[str, Any],
    results_by_model: Dict[str, Dict[str, Any]],
    grounding_audit: List[Dict[str, Any]],
    per_query_by_model: Dict[str, List[Dict[str, Any]]],
    created_at: str,
) -> str:
    """
    Generate the main REPORT.md content as a string.
    """
    lines = [
        f"# Retrieval Lab Report: {experiment_name}",
        "",
        f"**Experiment ID:** `{experiment_id}`",
        f"**Created:** {created_at}",
        "",
        "---",
        "",
        "## 1. Experiment Summary",
        "",
        f"- **Substrate:** {config.get('substrate_path', 'N/A')}",
        f"- **Document ID:** {config.get('document_id', 'N/A')}",
        f"- **Substrate version:** {config.get('substrate_version') or 'content hash'}",
        f"- **Embedding run_id:** {config.get('run_id', 'N/A')}",
        f"- **Models:** {', '.join(config.get('models', []))}",
        f"- **Top-k values:** {config.get('top_k', [])}",
        f"- **Retrieval mode:** {config.get('retrieval_mode', 'dense')}",
        f"- **Corpus unit count:** {corpus_stats.get('unit_count', 'N/A')}",
        f"- **Corpus page count:** {corpus_stats.get('page_count', 'N/A')}",
        "",
        "### Grounding Summary",
        "",
        f"- **Total queries:** {grounding_summary.get('total_queries', 0)}",
        f"- **Grounded:** {grounding_summary.get('grounded', 0)}",
        f"- **Ungrounded:** {grounding_summary.get('ungrounded', 0)}",
        f"- **Method:** {grounding_summary.get('method', 'N/A')}",
        "",
    ]
    grounded = grounding_summary.get("grounded", 0)
    total_q = grounding_summary.get("total_queries", 0)
    if total_q and grounded == 0:
        lines.extend([
            "**Note:** No queries have gold EvidenceUnits set (100% grounding_failure). "
            "Recall@k, Hit@k, and MRR are 0 until gold is applied. "
            "Use **Answer similarity@k** below as a relevance signal. "
            "For S&W: fill `gold_unit_ids` in `nominated_gold_per_query.json`, run `apply_nominated_gold_sw.py`, then re-run for benchmark metrics.",
            "",
        ])
    lines.extend([
        "---",
        "",
        "## 2. Model Comparison",
        "",
    ])
    # Table: model | MRR | Gold-in-Cand | R@k | H@k for every k in config
    top_k = config.get("top_k", [1, 3, 5, 10, 20])
    header = "| Model | MRR | Gold-in-Cand |"
    for k in top_k:
        header += f" R@{k} | H@{k} |"
    lines.append(header)
    lines.append("|" + "---|" * (3 + len(top_k) * 2) + "")
    for model_id, res in results_by_model.items():
        row = f"| {model_id} | {res.get('mrr', 0):.4f} | {res.get('gold_in_candidates', 0):.4f} |"
        for k in top_k:
            r = res.get("recall_at_k", {})
            h = res.get("hit_at_k", {})
            row += f" {r.get(k, 0):.4f} | {h.get(k, 0):.4f} |"
        lines.append(row)
    lines.extend(["", "---", "", "## 3. Per-Model Detail", ""])
    for model_id, res in results_by_model.items():
        lines.append(f"### {model_id}")
        lines.append("")
        lines.append(f"- **MRR:** {res.get('mrr', 0):.4f}")
        lines.append(f"- **Gold-in-candidates:** {res.get('gold_in_candidates', 0):.4f}")
        lines.append(f"- **Grounding coverage:** {res.get('grounding_coverage', 0):.4f}")
        lines.append("- **Recall@k:** " + json.dumps(res.get("recall_at_k", {})))
        lines.append("- **Hit@k:** " + json.dumps(res.get("hit_at_k", {})))
        if res.get("answer_similarity_at_k"):
            lines.append("- **Answer similarity@k:** " + json.dumps(res["answer_similarity_at_k"]))
        lines.append("- **Failure counts:** " + json.dumps(res.get("failure_counts", {})))
        if res.get("embedding_time_sec") is not None:
            lines.append(f"- **Embedding time (s):** {res['embedding_time_sec']:.2f}")
        if res.get("scoring_time_sec") is not None:
            lines.append(f"- **Scoring time (s):** {res['scoring_time_sec']:.2f}")
        lines.append("")
    lines.extend(["---", "", "## 4. Per-Suite Breakdown", ""])
    # Per-suite table for first model (same structure for all)
    first_model_result = next(iter(results_by_model.values()), None) if results_by_model else None
    if first_model_result and first_model_result.get("per_suite"):
        lines.append("| Suite | MRR | R@5 | H@5 | R@10 | H@10 | N |")
        lines.append("|-------|-----|-----|-----|------|------|---|")
        for suite_name, su in first_model_result["per_suite"].items():
            n = su.get("n", 0)
            mrr = su.get("mrr", 0)
            r5 = su.get("recall_at_k", {}).get(5, 0)
            h5 = su.get("hit_at_k", {}).get(5, 0)
            r10 = su.get("recall_at_k", {}).get(10, 0)
            h10 = su.get("hit_at_k", {}).get(10, 0)
            lines.append(f"| {suite_name} | {mrr:.4f} | {r5:.4f} | {h5:.4f} | {r10:.4f} | {h10:.4f} | {n} |")
        lines.append("")
    lines.extend(["---", "", "## 5. Failure Analysis", ""])
    lines.append("| Model | hit | retrieval_miss | rank_miss | grounding_failure |")
    lines.append("|-------|-----|----------------|-----------|-------------------|")
    for model_id, res in results_by_model.items():
        fc = res.get("failure_counts", {})
        lines.append(
            f"| {model_id} | {fc.get('hit', 0)} | {fc.get('retrieval_miss', 0)} | "
            f"{fc.get('rank_miss', 0)} | {fc.get('grounding_failure', 0)} |"
        )
    lines.extend(["", "---", "", "## 6. Gold Grounding Audit", ""])
    lines.append("Sample (first 10): query_id, method, count.")
    for entry in grounding_audit[:10]:
        lines.append(f"- `{entry.get('query_id', '')}`: {entry.get('method', '')}, count={entry.get('count', 0)}")
    if len(grounding_audit) > 10:
        lines.append(f"- ... and {len(grounding_audit) - 10} more (see grounding_audit.json).")
    rubric_entries = [e for e in grounding_audit if e.get("refusal_acceptable") or e.get("accept_qualified_answer") or e.get("scoring_rubric")]
    if rubric_entries:
        lines.extend(["", "### Query rubric notes", ""])
        for e in rubric_entries:
            qid = e.get("query_id", "")
            parts = [f"**{qid}**"]
            if e.get("refusal_acceptable"):
                parts.append("refusal_acceptable")
            if e.get("accept_qualified_answer"):
                parts.append("accept_qualified_answer")
            if e.get("scoring_rubric"):
                parts.append(f"— {e['scoring_rubric']}")
            lines.append("- " + " ".join(parts))
        lines.append("")
    lines.append(_glossary_md())
    return "\n".join(lines)


def write_report_artifacts(
    output_dir: Path,
    experiment_id: str,
    experiment_name: str,
    config: Dict[str, Any],
    corpus_stats: Dict[str, Any],
    grounding_summary: Dict[str, Any],
    results_by_model: Dict[str, Dict[str, Any]],
    grounding_audit: List[Dict[str, Any]],
    per_query_by_model: Dict[str, List[Dict[str, Any]]],
    experiment_doc: Dict[str, Any],
    retrieved_chunks_by_model: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Path]:
    """
    Write REPORT.md, metrics.json, per_query.json, grounding_audit.json, experiment.json,
    and optionally retrieved_chunks.json (per-query retrieved chunk text for manual review) to output_dir.
    Returns dict of artifact name -> path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = experiment_doc.get("created_at", datetime.now(timezone.utc).isoformat())
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    report_md = generate_report(
        experiment_id=experiment_id,
        experiment_name=experiment_name,
        config=config,
        corpus_stats=corpus_stats,
        grounding_summary=grounding_summary,
        results_by_model=results_by_model,
        grounding_audit=grounding_audit,
        per_query_by_model=per_query_by_model,
        created_at=created_at,
    )
    report_path = output_dir / "REPORT.md"
    report_path.write_text(report_md, encoding="utf-8")
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(results_by_model, indent=2),
        encoding="utf-8",
    )
    per_query_path = output_dir / "per_query.json"
    per_query_path.write_text(
        json.dumps(per_query_by_model, indent=2),
        encoding="utf-8",
    )
    audit_path = output_dir / "grounding_audit.json"
    audit_path.write_text(
        json.dumps(grounding_audit, indent=2),
        encoding="utf-8",
    )
    exp_path = output_dir / "experiment.json"
    # Serialize experiment_doc for JSON (e.g. datetime -> str)
    exp_serializable = dict(experiment_doc)
    if "created_at" in exp_serializable and hasattr(exp_serializable["created_at"], "isoformat"):
        exp_serializable["created_at"] = exp_serializable["created_at"].isoformat()
    exp_path.write_text(
        json.dumps(exp_serializable, indent=2),
        encoding="utf-8",
    )
    result = {
        "REPORT.md": report_path,
        "metrics.json": metrics_path,
        "per_query.json": per_query_path,
        "grounding_audit.json": audit_path,
        "experiment.json": exp_path,
    }
    if retrieved_chunks_by_model:
        chunks_path = output_dir / "retrieved_chunks.json"
        chunks_path.write_text(
            json.dumps({"by_model": retrieved_chunks_by_model}, indent=2),
            encoding="utf-8",
        )
        result["retrieved_chunks.json"] = chunks_path
    return result
