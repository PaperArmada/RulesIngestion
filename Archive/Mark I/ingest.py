"""Single entry-point CLI for rules ingestion + evaluation presets."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional


DEFAULT_PROFILE = "full"
DEFAULT_SKIP_PATTERN = "Cover|INTRO"


def _run_cmd(cmd: List[str], cwd: Path) -> None:
    print(f"🚀 Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _find_latest_run(runs_dir: Path) -> Optional[Path]:
    if not runs_dir.exists():
        return None
    candidates = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates)[-1]


def _iter_pdfs(source_dir: Path, skip_pattern: str) -> Iterable[Path]:
    for pdf_path in sorted(source_dir.glob("*.pdf")):
        stem = pdf_path.stem
        if skip_pattern and stem and re.search(skip_pattern, stem):
            print(f"⏭️  Skipping low-signal: {stem}")
            continue
        yield pdf_path


def _load_gate_summaries(enriched_dir: Path) -> List[dict]:
    summaries: List[dict] = []
    for path in sorted(enriched_dir.rglob("*.edge_gates.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            payload["path"] = str(path)
            summaries.append(payload)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠️  Failed to load gate summary {path}: {exc}")
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rules ingestion orchestrator (single entry point)."
    )
    parser.add_argument("--ruleset", required=True, help="Ruleset directory (e.g., StarFinder2e)")
    parser.add_argument(
        "--ruleset-id",
        default=None,
        help="Ruleset ID for config/graph (defaults to --ruleset)",
    )
    parser.add_argument("--book", required=True, help="Book ID (e.g., AlienCore)")
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        choices=["full", "enrich-only", "eval-only"],
        help="Preset profile: full | enrich-only | eval-only",
    )
    parser.add_argument("--source-dir", default=None, help="Override source PDF directory")
    parser.add_argument("--output-root", default=None, help="Override outputs root directory")
    parser.add_argument("--run-slug", default=None, help="Run slug (default: timestamp)")
    parser.add_argument("--run-dir", default=None, help="Explicit run directory (eval-only)")
    parser.add_argument("--skip-pattern", default=DEFAULT_SKIP_PATTERN, help="Regex to skip PDFs")
    parser.add_argument("--use-llm", action="store_true", help="Enable Marker LLM extraction")
    parser.add_argument("--auto-config", action="store_true", help="Generate ruleset config via LLM")
    parser.add_argument("--llm-pre-enrich", action="store_true", help="LLM paragraph enrichment")
    parser.add_argument("--llm-review", action="store_true", help="LLM review pass")
    parser.add_argument("--llm-review-limit", type=int, default=10, help="LLM review limit")
    parser.add_argument("--force-regenerate-config", action="store_true", help="Regenerate ruleset config")
    parser.add_argument("--allow-config-failure", action="store_true", help="Continue on config failure")
    parser.add_argument(
        "--auto-config-per-doc",
        action="store_true",
        help="Generate ruleset config for every PDF (default: only once per run)",
    )
    parser.add_argument("--edge-eval", action="store_true", help="Run edge eval after merge")
    parser.add_argument("--edge-seed-max", type=int, default=500, help="Edge-seeded query cap")
    parser.add_argument(
        "--edge-skip-gates",
        action="store_true",
        help="Skip OCR/spelling gates during deterministic edge discovery",
    )
    parser.add_argument(
        "--edge-allow-gate-fail",
        action="store_true",
        help="Continue edge discovery even if OCR/spelling gates fail",
    )
    parser.add_argument(
        "--edge-unresolved-rate-max",
        type=float,
        default=None,
        help="Override unresolved strict reference gate threshold",
    )
    parser.add_argument(
        "--edge-suspect-token-rate-max",
        type=float,
        default=None,
        help="Override suspect token gate threshold",
    )
    parser.add_argument(
        "--edge-near-duplicate-max",
        type=int,
        default=None,
        help="Override near-duplicate title count threshold",
    )
    parser.add_argument(
        "--edge-near-duplicate-rate-max",
        type=float,
        default=None,
        help="Override near-duplicate title rate threshold",
    )
    parser.add_argument(
        "--edge-gate-prompt",
        action="store_true",
        help="Prompt for confirmation after OCR/spelling gate summary",
    )
    # Traversal-only retrieval options
    parser.add_argument(
        "--build-traversal-index",
        action="store_true",
        help="Build traversal index from graph and chunks",
    )
    parser.add_argument(
        "--eval-traversal-recall",
        action="store_true",
        help="Run traversal-only recall evaluation",
    )
    parser.add_argument(
        "--benchmark-path",
        default=None,
        help="Path to benchmark dataset JSON for traversal recall",
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent
    ruleset_dir = root_dir / "Rules" / args.ruleset / args.book
    if not ruleset_dir.exists():
        raise FileNotFoundError(f"Ruleset/book directory not found: {ruleset_dir}")

    ruleset_id = args.ruleset_id or args.ruleset
    source_dir = Path(args.source_dir) if args.source_dir else (ruleset_dir / "source")
    output_root = Path(args.output_root) if args.output_root else (ruleset_dir / "outputs")
    runs_dir = output_root / "runs"
    run_slug = args.run_slug or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = Path(args.run_dir) if args.run_dir else (runs_dir / run_slug)
    enriched_dir = run_dir / "enriched"

    if args.profile in {"full", "enrich-only"}:
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {source_dir}")
        run_dir.mkdir(parents=True, exist_ok=True)

        pdfs = list(_iter_pdfs(source_dir, args.skip_pattern))
        if not pdfs:
            raise FileNotFoundError(f"No PDFs found in {source_dir}")

        for index, pdf_path in enumerate(pdfs):
            stem = pdf_path.stem
            safe_stem = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in stem)
            doc_id = f"{ruleset_id}-{safe_stem}"
            should_auto_config = args.auto_config and (args.auto_config_per_doc or index == 0)
            cmd = [
                "uv",
                "run",
                "python",
                "rules_ingestion_pipeline.py",
                str(pdf_path),
                "--output-dir",
                str(run_dir),
                "--doc-id",
                doc_id,
                "--ruleset-id",
                ruleset_id,
            ]
            if args.use_llm:
                cmd.append("--use-llm")
            if should_auto_config:
                cmd.append("--auto-config")
            if args.llm_pre_enrich:
                cmd.append("--llm-pre-enrich")
            if args.llm_review:
                cmd.append("--llm-review")
                cmd.extend(["--llm-review-limit", str(args.llm_review_limit)])
            if args.force_regenerate_config and should_auto_config:
                cmd.append("--force-regenerate-config")
            if args.allow_config_failure or should_auto_config:
                cmd.append("--allow-config-failure")
            _run_cmd(cmd, root_dir)

    if args.profile in {"full", "eval-only"}:
        if not run_dir.exists():
            latest = _find_latest_run(runs_dir)
            if latest is None:
                raise FileNotFoundError(f"No runs found in {runs_dir}")
            run_dir = latest
            enriched_dir = run_dir / "enriched"
            print(f"📌 Using latest run: {run_dir}")
        if not enriched_dir.exists():
            raise FileNotFoundError(f"Missing enriched outputs: {enriched_dir}")

        edge_cmd = [
            "uv",
            "run",
            "python",
            "scripts/discover_deterministic_edges.py",
            str(enriched_dir),
            "--write",
            "--write-gate-summary",
        ]
        if args.edge_skip_gates:
            edge_cmd.append("--skip-gates")
        if args.edge_allow_gate_fail:
            edge_cmd.append("--allow-gate-fail")
        if args.edge_unresolved_rate_max is not None:
            edge_cmd.extend(["--unresolved-rate-max", str(args.edge_unresolved_rate_max)])
        if args.edge_suspect_token_rate_max is not None:
            edge_cmd.extend(
                ["--suspect-token-rate-max", str(args.edge_suspect_token_rate_max)]
            )
        if args.edge_near_duplicate_max is not None:
            edge_cmd.extend(["--near-duplicate-max", str(args.edge_near_duplicate_max)])
        if args.edge_near_duplicate_rate_max is not None:
            edge_cmd.extend(
                ["--near-duplicate-rate-max", str(args.edge_near_duplicate_rate_max)]
            )
        _run_cmd(edge_cmd, root_dir)

        if args.edge_gate_prompt:
            summaries = _load_gate_summaries(enriched_dir)
            failures = [
                summary
                for summary in summaries
                if summary.get("gates", {}).get("gate_failures")
            ]
            if summaries:
                print(
                    "🧪 Gate summaries: "
                    f"{len(summaries)} docs, {len(failures)} with failures"
                )
            else:
                print("⚠️  No gate summaries found; skipping prompt.")
            if failures:
                for summary in failures:
                    doc_id = summary.get("document", "unknown")
                    gates = summary.get("gates", {})
                    failures_list = gates.get("gate_failures", [])
                    print(f"  - {doc_id}: {', '.join(failures_list)}")
                response = input("Continue with merge despite gate failures? [y/N] ")
                if response.strip().lower() not in {"y", "yes"}:
                    print("🛑 Aborting before merge.")
                    sys.exit(1)

        merge_cmd = [
            "uv",
            "run",
            "python",
            "merge_enriched_outputs.py",
            "--enriched-dir",
            str(enriched_dir),
            "--output-prefix",
            "merged",
            "--edge-candidates-dir",
            str(enriched_dir),
        ]
        if args.edge_eval or args.profile == "full":
            merge_cmd.append("--edge-eval")
            merge_cmd.extend(["--edge-seed-max", str(args.edge_seed_max)])
        _run_cmd(merge_cmd, root_dir)

    # Traversal index building
    if args.build_traversal_index:
        print("📊 Building traversal index...")
        graph_path = enriched_dir / "merged.graph.json"
        chunks_path = enriched_dir / "merged.enriched.json"
        index_path = enriched_dir / "merged.traversal_index.json"
        
        if not graph_path.exists():
            print(f"⚠️  Graph file not found: {graph_path}")
        elif not chunks_path.exists():
            print(f"⚠️  Chunks file not found: {chunks_path}")
        else:
            from traversal.index import TraversalIndex
            
            with open(graph_path) as f:
                graph = json.load(f)
            with open(chunks_path) as f:
                chunks_data = json.load(f)
                chunks = chunks_data.get("chunks", chunks_data) if isinstance(chunks_data, dict) else chunks_data
            
            index = TraversalIndex.build(graph, chunks)
            index.save(index_path)
            print(f"✅ Traversal index saved to {index_path}")
            print(f"   Chunks: {index.total_chunks}, Edges: {index.total_edges}")
            print(f"   Terms indexed: {len(index.term_to_chunks)}")
            print(f"   Tags indexed: {len(index.tag_to_chunks)}")
            print(f"   Entities indexed: {len(index.entity_name_to_id)}")

    # Traversal recall evaluation
    if args.eval_traversal_recall:
        print("🔬 Running traversal recall evaluation...")
        graph_path = enriched_dir / "merged.graph.json"
        chunks_path = enriched_dir / "merged.enriched.json"
        
        # Find benchmark path
        benchmark_path = None
        if args.benchmark_path:
            benchmark_path = Path(args.benchmark_path)
        else:
            # Try default benchmark location
            benchmark_dir = root_dir / "Rules" / args.ruleset / "Benchmark"
            candidates = list(benchmark_dir.glob("*benchmark*.json")) if benchmark_dir.exists() else []
            if candidates:
                benchmark_path = candidates[0]
        
        if not benchmark_path or not benchmark_path.exists():
            print(f"⚠️  Benchmark file not found. Specify with --benchmark-path")
        elif not graph_path.exists():
            print(f"⚠️  Graph file not found: {graph_path}")
        elif not chunks_path.exists():
            print(f"⚠️  Chunks file not found: {chunks_path}")
        else:
            from evaluation.benchmark.traversal_recall import run_traversal_recall_from_files
            
            output_path = enriched_dir / "traversal_recall_results.json"
            result = run_traversal_recall_from_files(
                graph_path=graph_path,
                chunks_path=chunks_path,
                queries_path=benchmark_path,
                output_path=output_path,
                verbose=True,
            )
            print(f"\n📊 Traversal Recall Results:")
            print(f"   Recall: {result.recall:.2%}")
            print(f"   Avg candidate fraction: {result.avg_candidate_fraction:.2%}")
            print(f"   Queries evaluated: {result.total_queries}")
            print(f"   Results saved to: {output_path}")

    print("✨ Done.")


if __name__ == "__main__":
    main()
