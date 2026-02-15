"""Deterministic benchmark integrity checks for retrieval evaluation batches."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set

from retrieval_lab.config import ExperimentConfig
from retrieval_lab.gold_grounding import (
    flatten_query_batches,
    resolve_gold_locations_to_current_corpus,
)
from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_units_by_heading,
)


def _iter_gold_ids(query: Dict[str, Any]) -> List[str]:
    required = query.get("required_gold") or []
    supporting = query.get("supporting_gold") or []
    legacy = query.get("gold_unit_ids") or []
    out: List[str] = []
    for group in (required, supporting, legacy):
        if isinstance(group, list):
            out.extend(str(x) for x in group if str(x).strip())
    # Deduplicate while preserving order.
    return list(dict.fromkeys(out))


def _trigrams(text: str) -> Set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if len(tokens) < 3:
        return set(tokens)
    return {" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)}


def _looks_header_only(text: str) -> bool:
    clean = text.strip()
    if not clean:
        return False
    words = clean.split()
    if len(words) <= 4 and clean[-1:] not in ".!?":
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\s\-/,:()]{0,48}", clean)) and clean[-1:] not in ".!?"


def _has_dangling_reference(text: str) -> bool:
    lowered = text.lower()
    cues = ("it ", "this ", "these ", "those ", "above", "below", "following", "former", "latter")
    return any(cue in lowered for cue in cues)


def _looks_fragmentary_procedure(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return False
    starts_like_fragment = lowered.startswith(("then ", "and ", "or ", "if ", "when "))
    too_short = len(lowered.split()) < 8
    has_no_terminal_punct = lowered[-1:] not in ".!?"
    return starts_like_fragment and (too_short or has_no_terminal_punct)


def run_integrity_checks(
    *,
    config: ExperimentConfig,
    min_gold_chars: int,
    min_gold_words: int,
    max_copy_overlap: float,
    audit_all_units: bool,
    max_header_only_ratio: float,
    max_dangling_reference_ratio: float,
    max_fragmentary_ratio: float,
) -> Dict[str, Any]:
    config.resolve_paths(Path.cwd())
    raw_corpus = load_evidence_units(config.substrate_path, config.document_id)
    corpus = raw_corpus
    min_chars = getattr(config, "min_chars", None)
    if min_chars is not None:
        corpus = fold_under_threshold_into_adjacent(corpus, min_chars)
    folded_corpus = corpus
    if getattr(config, "merge_chunks", False):
        corpus = merge_units_by_heading(
            corpus,
            max_chars=getattr(config, "merge_max_chars", 2000),
        )
    unit_by_id = {u["id"]: u for u in corpus if u.get("id")}
    queries, _ = flatten_query_batches(config.query_batches)
    queries, gold_resolution_summary = resolve_gold_locations_to_current_corpus(
        queries,
        folded_corpus=folded_corpus,
        merged_corpus=corpus,
    )

    missing_gold: List[Dict[str, str]] = []
    low_quality_gold: List[Dict[str, Any]] = []
    leakage_flags: List[Dict[str, Any]] = []
    quality_audit: Dict[str, Any] = {
        "unit_count": len(corpus),
        "too_short_count": 0,
        "dangling_reference_count": 0,
        "header_only_count": 0,
        "fragmentary_procedure_count": 0,
        "sample_flags": [],
        "failed": False,
    }

    for q in queries:
        qid = q.get("id", "")
        question = (q.get("question") or "").strip()
        question_trigrams = _trigrams(question)
        for gid in _iter_gold_ids(q):
            unit = unit_by_id.get(gid)
            if unit is None:
                missing_gold.append({"query_id": qid, "gold_id": gid})
                continue
            text = (unit.get("text") or "").strip()
            if len(text) < min_gold_chars or len(text.split()) < min_gold_words:
                low_quality_gold.append(
                    {
                        "query_id": qid,
                        "gold_id": gid,
                        "chars": len(text),
                        "words": len(text.split()),
                    }
                )
            gold_trigrams = _trigrams(text)
            if question_trigrams and gold_trigrams:
                overlap = len(question_trigrams & gold_trigrams) / max(len(question_trigrams), 1)
                if overlap > max_copy_overlap:
                    leakage_flags.append(
                        {
                            "query_id": qid,
                            "gold_id": gid,
                            "copy_overlap": round(overlap, 4),
                        }
                    )

    if audit_all_units:
        for unit in corpus:
            uid = unit.get("id", "")
            text = (unit.get("text") or "").strip()
            too_short = len(text) < min_gold_chars or len(text.split()) < min_gold_words
            dangling = _has_dangling_reference(text)
            header_only = _looks_header_only(text)
            fragmentary = _looks_fragmentary_procedure(text)
            quality_audit["too_short_count"] += 1 if too_short else 0
            quality_audit["dangling_reference_count"] += 1 if dangling else 0
            quality_audit["header_only_count"] += 1 if header_only else 0
            quality_audit["fragmentary_procedure_count"] += 1 if fragmentary else 0
            if (too_short or dangling or header_only or fragmentary) and len(quality_audit["sample_flags"]) < 25:
                quality_audit["sample_flags"].append(
                    {
                        "unit_id": uid,
                        "too_short": too_short,
                        "dangling_reference": dangling,
                        "header_only": header_only,
                        "fragmentary_procedure": fragmentary,
                    }
                )
        unit_count = max(quality_audit["unit_count"], 1)
        header_ratio = quality_audit["header_only_count"] / unit_count
        dangling_ratio = quality_audit["dangling_reference_count"] / unit_count
        fragmentary_ratio = quality_audit["fragmentary_procedure_count"] / unit_count
        quality_audit["header_only_ratio"] = round(header_ratio, 6)
        quality_audit["dangling_reference_ratio"] = round(dangling_ratio, 6)
        quality_audit["fragmentary_procedure_ratio"] = round(fragmentary_ratio, 6)
        quality_audit["thresholds"] = {
            "max_header_only_ratio": max_header_only_ratio,
            "max_dangling_reference_ratio": max_dangling_reference_ratio,
            "max_fragmentary_ratio": max_fragmentary_ratio,
        }
        quality_audit["failed"] = (
            header_ratio > max_header_only_ratio
            or dangling_ratio > max_dangling_reference_ratio
            or fragmentary_ratio > max_fragmentary_ratio
        )

    integrity_failed = bool(missing_gold or low_quality_gold or leakage_flags)
    summary_failed = integrity_failed or bool(quality_audit.get("failed"))
    return {
        "config": {
            "substrate_path": config.substrate_path,
            "document_id": config.document_id,
            "query_batches": config.query_batches,
        },
        "summary": {
            "query_count": len(queries),
            "unit_count": len(corpus),
            "missing_gold_count": len(missing_gold),
            "low_quality_gold_count": len(low_quality_gold),
            "copy_leakage_count": len(leakage_flags),
            "quality_audit_failed": bool(quality_audit.get("failed")),
            "failed": summary_failed,
            "gold_resolution_summary": gold_resolution_summary,
        },
        "failures": {
            "missing_gold": missing_gold,
            "low_quality_gold": low_quality_gold,
            "copy_leakage": leakage_flags,
        },
        "quality_audit": quality_audit,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark integrity checker for retrieval query batches.")
    parser.add_argument("--config", required=True, help="Experiment YAML config path")
    parser.add_argument("--out", default=None, help="Optional output path for integrity_check.json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any integrity failure")
    parser.add_argument("--policy", choices=["strict", "warn"], default="warn", help="Integrity policy mode")
    parser.add_argument("--min-gold-chars", type=int, default=40)
    parser.add_argument("--min-gold-words", type=int, default=6)
    parser.add_argument("--max-copy-overlap", type=float, default=0.8)
    parser.add_argument("--audit-all-units", action="store_true", help="Run contract quality audit across all EvidenceUnits")
    parser.add_argument("--max-header-only-ratio", type=float, default=0.08)
    parser.add_argument("--max-dangling-reference-ratio", type=float, default=0.25)
    parser.add_argument("--max-fragmentary-ratio", type=float, default=0.15)
    parser.add_argument("--report-md", default=None, help="Optional output path for markdown integrity summary")
    args = parser.parse_args()

    cfg = ExperimentConfig.from_yaml(Path(args.config))
    report = run_integrity_checks(
        config=cfg,
        min_gold_chars=args.min_gold_chars,
        min_gold_words=args.min_gold_words,
        max_copy_overlap=args.max_copy_overlap,
        audit_all_units=args.audit_all_units,
        max_header_only_ratio=args.max_header_only_ratio,
        max_dangling_reference_ratio=args.max_dangling_reference_ratio,
        max_fragmentary_ratio=args.max_fragmentary_ratio,
    )

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = Path(cfg.output_dir) / "integrity_check.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    policy = "strict" if args.strict or args.policy == "strict" else "warn"
    report["policy"] = policy
    report["status"] = "failed" if report["summary"]["failed"] else "passed"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.report_md:
        md_path = Path(args.report_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        summary = report["summary"]
        qa = report.get("quality_audit", {})
        md = [
            "# Benchmark Integrity Summary",
            "",
            f"- **Policy:** {policy}",
            f"- **Status:** {report['status']}",
            f"- **Queries:** {summary['query_count']}",
            f"- **Units:** {summary['unit_count']}",
            f"- **Missing gold:** {summary['missing_gold_count']}",
            f"- **Low-quality gold:** {summary['low_quality_gold_count']}",
            f"- **Copy leakage:** {summary['copy_leakage_count']}",
            f"- **Quality audit failed:** {summary.get('quality_audit_failed', False)}",
        ]
        if qa:
            md.extend(
                [
                    "",
                    "## EvidenceUnit Quality Audit",
                    "",
                    f"- Header-only ratio: {qa.get('header_only_ratio', 0)}",
                    f"- Dangling-reference ratio: {qa.get('dangling_reference_ratio', 0)}",
                    f"- Fragmentary-procedure ratio: {qa.get('fragmentary_procedure_ratio', 0)}",
                ]
            )
        md_path.write_text("\n".join(md), encoding="utf-8")

    summary = report["summary"]
    print(
        "Integrity summary: "
        f"queries={summary['query_count']} units={summary['unit_count']} "
        f"missing_gold={summary['missing_gold_count']} "
        f"low_quality={summary['low_quality_gold_count']} "
        f"copy_leakage={summary['copy_leakage_count']}"
    )

    if policy == "strict" and summary["failed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
