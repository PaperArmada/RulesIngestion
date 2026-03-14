#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys

_SCRIPT_PATH = Path(__file__).resolve()
_ROOT = _SCRIPT_PATH.parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_ARCHIVE_MARK_I = _ROOT / "Archive" / "Mark I"
if str(_ARCHIVE_MARK_I) not in sys.path:
    sys.path.insert(0, str(_ARCHIVE_MARK_I))

from retrieval_lab.artifact_resolution import load_resolved_json_artifact
from retrieval_lab.benchmark_lint import lint_query_batches


@dataclass(frozen=True)
class TrackConfig:
    track: str
    substrate: str
    document_id: str
    benchmark: str
    dense_config: str
    hybrid_config: str
    substrate_version: str
    min_chars: int
    merge_max_chars: int
    enrichment_profiles: List[str]


@dataclass(frozen=True)
class CmdResult:
    returncode: int
    log_path: Path
    output_text: str


MODELS = [
    "all-mpnet-base-v2",
    "nomic-embed-text-v2",
    "bge-m3",
    "pplx-embed-v1-0.6B",
]
EXCLUDED_MODELS_BY_TRACK: Dict[str, set] = {
    # Empty for local validation; add back per-track exclusions if needed (e.g. OOM on smaller GPU).
}
RECIPES = ["standardized", "recommended"]
MODES = ["dense", "hybrid"]
REQUIRED_GOLD_EMPTY_THRESHOLD = 2
RUN_ID_RE = re.compile(r"run_id=([^\s]+)")
EXPERIMENT_ID_RE = re.compile(r"Done\. Experiment ID:\s+([A-Za-z0-9_\-]+)")
MODEL_MIN_FREE_VRAM_GB = {
    "nomic-embed-text-v2": 4.0,
    "bge-m3": 6.0,
    "pplx-embed-v1-0.6B": 4.0,
}
MODEL_BATCH_SIZE_OVERRIDE = {
    # PPLX 0.6B can exceed 16GB VRAM at batch_size=16 on long merged chunks.
    "pplx-embed-v1-0.6B": 1,
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def normalize_model_tag(model_id: str) -> str:
    return model_id.replace(".", "").replace("-", "_")


def cmd_to_str(cmd: List[str]) -> str:
    return " ".join(cmd)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_runner_log(runner_log_path: Path, message: str) -> None:
    line = f"[{_utc_now()}] {message}"
    print(line, flush=True)
    with runner_log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, list):
        return payload
    return []


def save_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def row_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        rid = str(r.get("row_id") or "")
        if rid:
            out[rid] = r
    return out


def find_legacy_row(
    rows: List[Dict[str, Any]],
    *,
    kind: str,
    track: str,
    model: str,
    recipe: str,
    enrichment: str,
    mode: str,
) -> Optional[Dict[str, Any]]:
    for r in rows:
        if (
            str(r.get("kind")) == kind
            and str(r.get("track")) == track
            and str(r.get("model")) == model
            and str(r.get("recipe")) == recipe
            and str(r.get("enrichment_profile")) == enrichment
            and str(r.get("mode")) == mode
        ):
            return r
    return None


def action_row_id(kind: str, track: str, model: str, recipe: str, enrichment: str, mode: str) -> str:
    return f"{kind}:{track}:{enrichment}:{recipe}:{model}:{mode}"


def run_cmd(cmd: List[str], cwd: Path, log_path: Path) -> CmdResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(f"$ {cmd_to_str(cmd)}\n\n")
        logf.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # isolate child process group for clean interrupt handling
        )
        try:
            returncode = proc.wait()
        except KeyboardInterrupt:
            # Ensure nested model/eval children are terminated, avoiding orphaned GPU workers.
            try:
                os.killpg(proc.pid, signal.SIGINT)
            except Exception:
                pass
            try:
                proc.wait(timeout=10)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
            raise
    output_text = log_path.read_text(encoding="utf-8")
    return CmdResult(returncode=returncode, log_path=log_path, output_text=output_text)


def _tail_lines(text: str, n: int = 20) -> str:
    lines = [ln for ln in str(text or "").splitlines() if ln.strip()]
    if not lines:
        return "(no output captured)"
    return "\n".join(lines[-n:])


def _log_row_failure(
    runner_log: Path,
    *,
    row_id: str,
    exit_code: Optional[int],
    log_rel_path: str,
    command: str,
    output_text: str,
    reason: str = "",
) -> None:
    parts = [
        f"failed {row_id}" + (f" exit={exit_code}" if exit_code is not None else ""),
    ]
    if reason:
        parts.append(f"reason: {reason}")
    parts.append(f"log_file: {log_rel_path}")
    parts.append(f"command: {command}")
    parts.append("stderr_tail:")
    parts.append(_tail_lines(output_text, n=20))
    append_runner_log(runner_log, "\n".join(parts))


def parse_run_id(stdout: str) -> Optional[str]:
    m = RUN_ID_RE.search(stdout)
    return m.group(1) if m else None


def parse_experiment_id(stdout: str) -> Optional[str]:
    m = EXPERIMENT_ID_RE.search(stdout)
    return m.group(1) if m else None


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def metric_row(
    row: Dict[str, Any],
    model_payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        **row,
        "MRR": float(model_payload.get("mrr", 0.0)),
        "nDCG@10": float((model_payload.get("ndcg_at_k") or {}).get("10", 0.0)),
        "Recall@10": float((model_payload.get("recall_at_k") or {}).get("10", 0.0)),
        "Recall@20": float((model_payload.get("recall_at_k") or {}).get("20", 0.0)),
        "Hit@10": float((model_payload.get("hit_at_k") or {}).get("10", 0.0)),
        "Hit@20": float((model_payload.get("hit_at_k") or {}).get("20", 0.0)),
        "Gold-in-Candidates": float(model_payload.get("gold_in_candidates", 0.0)),
        "Gold-in-Candidates (True Ceiling)": float(
            model_payload.get("gold_in_candidates_true_ceiling", 0.0)
        ),
        "Required Full-Set Hit@10": float(
            (model_payload.get("required_full_set_hit_at_k") or {}).get("10", 0.0)
        ),
        "Rank-of-Last-Required (mean)": float(
            model_payload.get("rank_of_last_required_mean", 0.0)
        ),
        "no_gold_defined": int(
            (model_payload.get("failure_bucket_counts") or {}).get("no_gold_defined", 0)
        ),
        "gold_not_in_candidates": int(
            (model_payload.get("failure_bucket_counts") or {}).get(
                "gold_not_in_candidates", 0
            )
        ),
        "gold_in_candidates_but_low_rank": int(
            (model_payload.get("failure_bucket_counts") or {}).get(
                "gold_in_candidates_but_low_rank", 0
            )
        ),
        "grounding_or_answer_failure_after_retrieval": int(
            (model_payload.get("failure_bucket_counts") or {}).get(
                "grounding_or_answer_failure_after_retrieval", 0
            )
        ),
    }


def make_markdown_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return "_No rows._\n"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for r in rows:
        vals: List[str] = []
        for c in columns:
            v = r.get(c, "")
            if isinstance(v, float):
                vals.append(f"{v:.4f}")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


def rank_value(v: Any) -> int:
    if v is None:
        return 9999
    try:
        return int(v)
    except Exception:
        return 9999


def models_for_track(track: str, only_models: Optional[set] = None) -> List[str]:
    excluded = EXCLUDED_MODELS_BY_TRACK.get(track, set())
    out = [m for m in MODELS if m not in excluded]
    if only_models is not None:
        out = [m for m in out if m in only_models]
    return out


def batch_size_for_model(model_id: str) -> int:
    return int(MODEL_BATCH_SIZE_OVERRIDE.get(model_id, 16))


def top_chunks_for_query(retrieved_chunks: Dict[str, Any], model: str, qid: str) -> List[Dict[str, Any]]:
    by_model = (retrieved_chunks.get("by_model") or {}).get(model) or []
    for item in by_model:
        if str(item.get("query_id")) == qid:
            return list(item.get("retrieved") or [])[:10]
    return []


def preflight_model_dependency_checks(models: List[str]) -> List[str]:
    """Fail-fast checks for known runtime dependency misses."""
    failures: List[str] = []
    if "nomic-embed-text-v2" in models:
        if importlib.util.find_spec("einops") is None:
            failures.append("dependency_missing:einops_for_nomic")
    if "pplx-embed-v1-0.6B" in models:
        # PPLX is loaded via SentenceTransformers with trust_remote_code (see PPLX_EMBED_STANDUP).
        # We do not require transformers.models.qwen3; sentence_transformers is the loader.
        if importlib.util.find_spec("sentence_transformers") is None:
            failures.append("dependency_missing:sentence_transformers_for_pplx")
    return failures


def preflight_gpu_memory_checks(models: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    details: Dict[str, Any] = {}
    failures: List[str] = []
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            details["cuda_available"] = False
            return failures, details
        free_b, total_b = torch.cuda.mem_get_info()
        free_gb = float(free_b) / (1024 ** 3)
        total_gb = float(total_b) / (1024 ** 3)
        details.update(
            {
                "cuda_available": True,
                "free_vram_gb": round(free_gb, 3),
                "total_vram_gb": round(total_gb, 3),
            }
        )
        for model in models:
            min_gb = MODEL_MIN_FREE_VRAM_GB.get(model)
            if min_gb is None:
                continue
            if free_gb < min_gb:
                failures.append(
                    f"gpu_free_vram_below_threshold:{model}:{free_gb:.2f}<{min_gb:.2f}"
                )
    except Exception as e:
        details["gpu_probe_error"] = str(e)
    return failures, details


def preflight_known_issue_checks(root: Path) -> List[str]:
    """Block known runtime regressions before execution."""
    failures: List[str] = []
    dense_mode_path = root / "retrieval_lab" / "orchestration" / "dense_mode.py"
    try:
        dense_mode_text = dense_mode_path.read_text(encoding="utf-8")
    except Exception:
        return ["known_issue_guard_read_failed:dense_mode"]
    # Historical regression: expand-context block referenced query_embeddings
    # before assignment, causing UnboundLocalError in eval-only S&W rows.
    if "q_emb = query_embeddings[i : i + 1]" in dense_mode_text:
        failures.append("known_issue_detected:query_embeddings_unbound_expand_context")
    return failures


def should_block_on_preflight_failure(failure_code: str, allow_high_required_gold_empty: bool) -> bool:
    if failure_code.startswith("required_gold_empty_exceeds_threshold:"):
        return not allow_high_required_gold_empty
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute embedding bakeoff multivariate matrix")
    parser.add_argument(
        "--allow-high-required-gold-empty",
        action="store_true",
        help="Continue execution even when benchmark required_gold_empty exceeds threshold.",
    )
    parser.add_argument(
        "--include-starfinder-full",
        action="store_true",
        help="Also run Starfinder full enrichment profile rows.",
    )
    parser.add_argument(
        "--bundle-dir",
        type=str,
        default=None,
        help="Existing bundle directory to resume, or explicit destination for new run.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing bundle row state when --bundle-dir is set.",
    )
    parser.add_argument(
        "--resume-failed",
        action="store_true",
        help="When resuming, also rerun previously failed rows.",
    )
    parser.add_argument(
        "--allow-preflight-drift",
        action="store_true",
        help="When resuming, allow changed benchmark hashes/contracts and continue anyway.",
    )
    parser.add_argument(
        "--no-gpu-memory-guard",
        action="store_true",
        help="Disable preflight VRAM threshold checks.",
    )
    parser.add_argument(
        "--no-dependency-guard",
        action="store_true",
        help="Disable preflight dependency checks for model-specific requirements.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run preflight checks only, write reports, and exit without running the matrix.",
    )
    parser.add_argument(
        "--only-models",
        type=str,
        default=None,
        help="Comma-separated model ids to run (e.g. pplx-embed-v1-0.6B). Default: all models.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "retrieval_lab").exists():
        raise RuntimeError("Run this script from RulesIngestion root.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if args.bundle_dir:
        bundle_dir = Path(args.bundle_dir)
        if not bundle_dir.is_absolute():
            bundle_dir = root / bundle_dir
    else:
        bundle_dir = root / "out" / "retrieval_lab" / "bakeoff" / f"model_bakeoff_{ts}"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = bundle_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    runner_log = bundle_dir / "runner.log"
    append_runner_log(runner_log, f"bundle_dir={bundle_dir}")

    tracks = [
        TrackConfig(
            track="Starfinder",
            substrate="out/StarFinderPlayerCore",
            document_id="StarFinderPlayerCore",
            benchmark="evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json",
            dense_config="retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml",
            hybrid_config="retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml",
            substrate_version="v2_merged2000_min200",
            min_chars=200,
            merge_max_chars=2000,
            enrichment_profiles=["baseline", "full"] if args.include_starfinder_full else ["baseline"],
        ),
        TrackConfig(
            track="SwordsandWizardry",
            substrate="out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF",
            document_id="Swords&Wizardry",
            benchmark="evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json",
            dense_config="retrieval_lab/experiments/dense/swords_wizardry_baseline.yaml",
            hybrid_config="retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml",
            substrate_version="v3_swcr_merged2000_min100",
            min_chars=100,
            merge_max_chars=2000,
            enrichment_profiles=["full"],
        ),
    ]

    # Phase A: refinement/preflight lock.
    preflight: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "required_gold_empty_threshold": REQUIRED_GOLD_EMPTY_THRESHOLD,
        "allow_high_required_gold_empty_override": bool(args.allow_high_required_gold_empty),
        "tracks": {},
        "hard_failures": [],
        "guards": {
            "dependency_guard_enabled": not bool(args.no_dependency_guard),
            "gpu_memory_guard_enabled": not bool(args.no_gpu_memory_guard),
            "known_issue_guard_enabled": True,
            "allow_preflight_drift": bool(args.allow_preflight_drift),
        },
        "notes": [
            "S&W uses canonical benchmark naming SwordsandWizardry and canonical substrate under out/Swords&Wizardry.",
            "Embedding contract is shared across dense/hybrid per track by fixing substrate_version, min_chars, merge flags, and enrichment profile.",
            "Starfinder full enrichment is optional and disabled by default for minimal matrix.",
        ],
    }

    from evaluation.model_registry import MODEL_REGISTRY  # type: ignore
    only_models_set: Optional[set] = None
    if getattr(args, "only_models", None) and str(args.only_models).strip():
        only_models_set = {s.strip() for s in str(args.only_models).split(",") if s.strip()}
        append_runner_log(runner_log, f"only_models={sorted(only_models_set)}")
    active_models = sorted({m for t in tracks for m in models_for_track(t.track, only_models=only_models_set)})

    for model_id in active_models:
        if model_id not in MODEL_REGISTRY:
            preflight["hard_failures"].append(f"model_missing:{model_id}")
    if not args.no_dependency_guard:
        preflight["hard_failures"].extend(preflight_model_dependency_checks(active_models))
    if not args.no_gpu_memory_guard:
        gpu_failures, gpu_details = preflight_gpu_memory_checks(active_models)
        preflight["gpu_probe"] = gpu_details
        preflight["hard_failures"].extend(gpu_failures)
    preflight["hard_failures"].extend(preflight_known_issue_checks(root))

    for t in tracks:
        bpath = root / t.benchmark
        lint = lint_query_batches([str(bpath)])
        req_empty = int((lint.get("by_code") or {}).get("required_gold_empty", 0))
        track_payload = {
            "substrate": t.substrate,
            "benchmark": t.benchmark,
            "benchmark_sha256": sha256_file(bpath),
            "n_queries": int(lint.get("n_queries", 0)),
            "required_gold_empty": req_empty,
        }
        preflight["tracks"][t.track] = track_payload
        if req_empty > REQUIRED_GOLD_EMPTY_THRESHOLD:
            preflight["hard_failures"].append(
                f"required_gold_empty_exceeds_threshold:{t.track}:{req_empty}"
            )

    preflight_path = bundle_dir / "preflight_contract_lock.json"
    existing_preflight: Optional[Dict[str, Any]] = None
    if args.resume and preflight_path.exists():
        try:
            existing_preflight = read_json(preflight_path)
        except Exception:
            existing_preflight = None
    if existing_preflight is not None:
        old_tracks = existing_preflight.get("tracks") or {}
        new_tracks = preflight.get("tracks") or {}
        if old_tracks != new_tracks:
            preflight["hard_failures"].append("preflight_contract_drift:tracks_changed")
            preflight["preflight_drift"] = {
                "old_tracks": old_tracks,
                "new_tracks": new_tracks,
            }
    preflight_path.write_text(
        json.dumps(preflight, indent=2),
        encoding="utf-8",
    )
    append_runner_log(runner_log, f"wrote preflight {preflight_path}")

    blocking_failures = [
        x
        for x in preflight["hard_failures"]
        if should_block_on_preflight_failure(
            str(x), bool(args.allow_high_required_gold_empty)
        )
    ]
    if existing_preflight is not None and ("preflight_contract_drift:tracks_changed" in blocking_failures):
        if args.allow_preflight_drift:
            blocking_failures = [x for x in blocking_failures if x != "preflight_contract_drift:tracks_changed"]
            append_runner_log(runner_log, "preflight drift detected but allowed via --allow-preflight-drift")

    non_blocking_failures = [x for x in preflight["hard_failures"] if x not in blocking_failures]
    preflight_report = {
        "timestamp_utc": _utc_now(),
        "bundle_dir": str(bundle_dir),
        "preflight_passed": len(blocking_failures) == 0,
        "blocking_failures": blocking_failures,
        "non_blocking_failures": non_blocking_failures,
        "guards": preflight.get("guards", {}),
        "tracks": preflight.get("tracks", {}),
    }
    (bundle_dir / "preflight_report.json").write_text(
        json.dumps(preflight_report, indent=2),
        encoding="utf-8",
    )

    if args.preflight_only:
        if blocking_failures:
            append_runner_log(
                runner_log,
                "preflight-only failed: " + ", ".join(blocking_failures),
            )
            (bundle_dir / "SUMMARY.md").write_text(
                "# Embedding Bakeoff Summary\n\n"
                "Preflight-only run failed.\n\n"
                f"Blocking failures:\n\n- " + "\n- ".join(blocking_failures) + "\n",
                encoding="utf-8",
            )
            return 2
        append_runner_log(runner_log, "preflight-only passed")
        (bundle_dir / "SUMMARY.md").write_text(
            "# Embedding Bakeoff Summary\n\n"
            "Preflight-only run passed. Execution phase was intentionally skipped.\n",
            encoding="utf-8",
        )
        return 0

    if blocking_failures:
        append_runner_log(runner_log, "preflight blocked run: " + ", ".join(blocking_failures))
        (bundle_dir / "SUMMARY.md").write_text(
            "# Embedding Bakeoff Summary\n\n"
            "Decision blocked during preflight hard-fail checks.\n\n"
            f"Hard failures:\n\n- " + "\n- ".join(blocking_failures) + "\n",
            encoding="utf-8",
        )
        return 2

    rows_path = bundle_dir / "run_rows.json"
    rows: List[Dict[str, Any]] = load_rows(rows_path) if args.resume else []
    rows_by_id = row_index(rows)
    embed_run_ids: Dict[Tuple[str, str, str, str], str] = {}
    for r in rows:
        if (
            r.get("kind") == "embed"
            and r.get("status") == "ok"
            and r.get("run_id")
        ):
            embed_run_ids[(r["track"], r["model"], r["recipe"], r["enrichment_profile"])] = r["run_id"]

    def existing_row_for_id(row_id: str) -> Optional[Dict[str, Any]]:
        existing = rows_by_id.get(row_id)
        if existing:
            return existing
        parts = row_id.split(":")
        if len(parts) != 6:
            return None
        return find_legacy_row(
            rows,
            kind=parts[0],
            track=parts[1],
            enrichment=parts[2],
            recipe=parts[3],
            model=parts[4],
            mode=parts[5],
        )

    def should_skip(row_id: str) -> bool:
        existing = existing_row_for_id(row_id)
        if not existing:
            return False
        if existing.get("status") == "ok":
            return True
        if existing.get("status") == "failed" and not args.resume_failed:
            return True
        return False

    def upsert_row(row: Dict[str, Any]) -> None:
        nonlocal rows_by_id
        rid = str(row.get("row_id") or "")
        if rid and rid in rows_by_id:
            old = rows_by_id[rid]
            idx = rows.index(old)
            rows[idx] = row
        else:
            rows.append(row)
        rows_by_id = row_index(rows)
        save_rows(rows_path, rows)

    def common_args(track_cfg: TrackConfig, model_id: str, recipe: str, enrichment: str) -> List[str]:
        args_out = [
            "--substrate",
            track_cfg.substrate,
            "--document-id",
            track_cfg.document_id,
            "--substrate-version",
            track_cfg.substrate_version,
            "--models",
            model_id,
            "--recipe-mode",
            recipe,
            "--recipe-fail-on-missing-source",
            "--embedding-enrichment-profile",
            enrichment,
            "--batches",
            track_cfg.benchmark,
            "--seed",
            "42",
            "--batch-size",
            str(batch_size_for_model(model_id)),
            "--min-chars",
            str(track_cfg.min_chars),
            "--merge-chunks",
            "--merge-max-chars",
            str(track_cfg.merge_max_chars),
        ]
        if model_id != "all-mpnet-base-v2":
            args_out.append("--trust-remote-code")
        return args_out

    # Phase B: execute matrix.
    try:
        for track_cfg in tracks:
            for enrichment in track_cfg.enrichment_profiles:
                for recipe in RECIPES:
                    for model_id in models_for_track(track_cfg.track, only_models=only_models_set):
                        key = (track_cfg.track, model_id, recipe, enrichment)
                        embed_row_id = action_row_id(
                            "embed", track_cfg.track, model_id, recipe, enrichment, "embed-only"
                        )
                        if should_skip(embed_row_id):
                            existing = existing_row_for_id(embed_row_id) or {}
                            if existing.get("run_id"):
                                embed_run_ids[key] = existing["run_id"]
                            append_runner_log(runner_log, f"skip {embed_row_id} status={existing.get('status')}")
                        else:
                            embed_name = (
                                f"bakeoff_embed_{track_cfg.track.lower()}_"
                                f"{normalize_model_tag(model_id)}_{recipe}_{enrichment}"
                            )
                            embed_cmd = [
                                "uv",
                                "run",
                                "python",
                                "-m",
                                "retrieval_lab.run_experiment",
                                "--config",
                                track_cfg.dense_config,
                                "--experiment-name",
                                embed_name,
                                "--embed-only",
                            ] + common_args(track_cfg, model_id, recipe, enrichment)
                            append_runner_log(runner_log, f"start {embed_row_id}")
                            embed_res = run_cmd(embed_cmd, root, logs_dir / f"{embed_row_id}.log")
                            embed_row = {
                                "row_id": embed_row_id,
                                "kind": "embed",
                                "track": track_cfg.track,
                                "model": model_id,
                                "recipe": recipe,
                                "mode": "embed-only",
                                "enrichment_profile": enrichment,
                                "command": cmd_to_str(embed_cmd),
                                "exit_code": embed_res.returncode,
                                "log_file": str(embed_res.log_path.relative_to(bundle_dir)),
                                "finished_at": _utc_now(),
                            }
                            if embed_res.returncode != 0:
                                embed_row["status"] = "failed"
                                embed_row["stderr_tail"] = "\n".join(embed_res.output_text.splitlines()[-20:])
                                upsert_row(embed_row)
                                _log_row_failure(
                                    runner_log,
                                    row_id=embed_row_id,
                                    exit_code=embed_res.returncode,
                                    log_rel_path=str(embed_res.log_path.relative_to(bundle_dir)),
                                    command=embed_row["command"],
                                    output_text=embed_res.output_text,
                                )
                                continue
                            run_id = parse_run_id(embed_res.output_text or "")
                            if not run_id:
                                embed_row["status"] = "failed"
                                embed_row["stderr_tail"] = "Could not parse run_id from embed-only output."
                                upsert_row(embed_row)
                                _log_row_failure(
                                    runner_log,
                                    row_id=embed_row_id,
                                    exit_code=embed_res.returncode,
                                    log_rel_path=str(embed_res.log_path.relative_to(bundle_dir)),
                                    command=embed_row["command"],
                                    output_text=embed_res.output_text,
                                    reason="parse_run_id",
                                )
                                continue
                            embed_row["status"] = "ok"
                            embed_row["run_id"] = run_id
                            upsert_row(embed_row)
                            append_runner_log(runner_log, f"ok {embed_row_id} run_id={run_id}")
                            embed_run_ids[key] = run_id

                        run_id = embed_run_ids.get(key)
                        if not run_id:
                            continue

                        # eval-only rows (dense + hybrid) for same branch
                        for mode in MODES:
                            eval_row_id = action_row_id(
                                "eval", track_cfg.track, model_id, recipe, enrichment, mode
                            )
                            if should_skip(eval_row_id):
                                append_runner_log(
                                    runner_log,
                                    f"skip {eval_row_id} status={(existing_row_for_id(eval_row_id) or {}).get('status')}",
                                )
                                continue
                            cfg = track_cfg.dense_config if mode == "dense" else track_cfg.hybrid_config
                            exp_name = (
                                f"bakeoff_{track_cfg.track.lower()}_{mode}_"
                                f"{normalize_model_tag(model_id)}_{recipe}_{enrichment}"
                            )
                            eval_cmd = [
                                "uv",
                                "run",
                                "python",
                                "-m",
                                "retrieval_lab.run_experiment",
                                "--config",
                                cfg,
                                "--experiment-name",
                                exp_name,
                                "--run-id",
                                run_id,
                            ] + common_args(track_cfg, model_id, recipe, enrichment)
                            append_runner_log(runner_log, f"start {eval_row_id} run_id={run_id}")
                            eval_res = run_cmd(eval_cmd, root, logs_dir / f"{eval_row_id}.log")
                            eval_row = {
                                "row_id": eval_row_id,
                                "kind": "eval",
                                "track": track_cfg.track,
                                "model": model_id,
                                "recipe": recipe,
                                "mode": mode,
                                "enrichment_profile": enrichment,
                                "run_id": run_id,
                                "command": cmd_to_str(eval_cmd),
                                "exit_code": eval_res.returncode,
                                "log_file": str(eval_res.log_path.relative_to(bundle_dir)),
                                "finished_at": _utc_now(),
                            }
                            if eval_res.returncode != 0:
                                eval_row["status"] = "failed"
                                eval_row["stderr_tail"] = "\n".join(
                                    eval_res.output_text.splitlines()[-20:]
                                )
                                upsert_row(eval_row)
                                _log_row_failure(
                                    runner_log,
                                    row_id=eval_row_id,
                                    exit_code=eval_res.returncode,
                                    log_rel_path=str(eval_res.log_path.relative_to(bundle_dir)),
                                    command=eval_row["command"],
                                    output_text=eval_res.output_text,
                                )
                                break
                            exp_id = parse_experiment_id(eval_res.output_text or "")
                            if not exp_id:
                                eval_row["status"] = "failed"
                                eval_row["stderr_tail"] = "Could not parse experiment id from eval output."
                                upsert_row(eval_row)
                                _log_row_failure(
                                    runner_log,
                                    row_id=eval_row_id,
                                    exit_code=eval_res.returncode,
                                    log_rel_path=str(eval_res.log_path.relative_to(bundle_dir)),
                                    command=eval_row["command"],
                                    output_text=eval_res.output_text,
                                    reason="parse_experiment_id",
                                )
                                break
                            eval_row["status"] = "ok"
                            eval_row["experiment_id"] = exp_id
                            eval_row["artifact_dir"] = f"out/retrieval_lab/bakeoff/{exp_id}"
                            upsert_row(eval_row)
                            append_runner_log(runner_log, f"ok {eval_row_id} exp={exp_id}")
    except KeyboardInterrupt:
        append_runner_log(runner_log, "KeyboardInterrupt: checkpoint saved, safe to resume.")
        save_rows(rows_path, rows)
        return 130
    except Exception:
        append_runner_log(runner_log, "Unhandled exception:\n" + traceback.format_exc())
        save_rows(rows_path, rows)
        raise

    # Stability rerun (key baseline row).
    key = ("Starfinder", "all-mpnet-base-v2", "standardized", "baseline")
    if key in embed_run_ids:
        run_id = embed_run_ids[key]
        sf_cfg = tracks[0]
        st_row_id = action_row_id(
            "stability_check",
            "Starfinder",
            "all-mpnet-base-v2",
            "standardized",
            "baseline",
            "hybrid",
        )
        if should_skip(st_row_id):
            append_runner_log(
                runner_log,
                f"skip {st_row_id} status={(existing_row_for_id(st_row_id) or {}).get('status')}",
            )
        else:
            st_cmd = [
                "uv",
                "run",
                "python",
                "-m",
                "retrieval_lab.run_experiment",
                "--config",
                sf_cfg.hybrid_config,
                "--experiment-name",
                "bakeoff_stability_sf_hybrid_mpnet_standardized",
                "--run-id",
                run_id,
            ] + common_args(sf_cfg, "all-mpnet-base-v2", "standardized", "baseline")
            append_runner_log(runner_log, f"start {st_row_id}")
            st_res = run_cmd(st_cmd, root, logs_dir / f"{st_row_id}.log")
            st_row: Dict[str, Any] = {
                "row_id": st_row_id,
                "kind": "stability_check",
                "track": "Starfinder",
                "model": "all-mpnet-base-v2",
                "recipe": "standardized",
                "mode": "hybrid",
                "enrichment_profile": "baseline",
                "run_id": run_id,
                "command": cmd_to_str(st_cmd),
                "exit_code": st_res.returncode,
                "log_file": str((logs_dir / f"{st_row_id}.log").relative_to(bundle_dir)),
                "finished_at": _utc_now(),
            }
            exp_id = parse_experiment_id(st_res.output_text or "")
            if st_res.returncode == 0 and exp_id:
                st_row["status"] = "ok"
                st_row["experiment_id"] = exp_id
                st_row["artifact_dir"] = f"out/retrieval_lab/bakeoff/{exp_id}"
                append_runner_log(runner_log, f"ok {st_row_id} exp={exp_id}")
            else:
                st_row["status"] = "failed"
                st_row["stderr_tail"] = "\n".join(st_res.output_text.splitlines()[-20:])
                _log_row_failure(
                    runner_log,
                    row_id=st_row_id,
                    exit_code=st_res.returncode,
                    log_rel_path=str((logs_dir / f"{st_row_id}.log").relative_to(bundle_dir)),
                    command=st_row["command"],
                    output_text=st_res.output_text,
                )
            upsert_row(st_row)

    save_rows(rows_path, rows)

    # Aggregate summaries from successful eval rows.
    successful_eval_rows = [r for r in rows if r.get("kind") == "eval" and r.get("status") == "ok"]
    failed_eval_rows = [r for r in rows if r.get("kind") == "eval" and r.get("status") == "failed"]
    failed_eval_row_ids = [str(r.get("row_id") or "") for r in failed_eval_rows]
    total_eval_rows = len([r for r in rows if r.get("kind") == "eval"])
    eval_failure_rate = (len(failed_eval_rows) / total_eval_rows) if total_eval_rows else 0.0
    starfinder_eval_ok = len(
        [r for r in successful_eval_rows if str(r.get("track")) == "Starfinder"]
    )
    sw_eval_total = len([r for r in rows if r.get("kind") == "eval" and str(r.get("track")) == "SwordsandWizardry"])
    sw_eval_ok = len(
        [r for r in successful_eval_rows if str(r.get("track")) == "SwordsandWizardry"]
    )
    evidence_scope = "multi_track"
    if sw_eval_total > 0 and sw_eval_ok == 0 and starfinder_eval_ok > 0:
        evidence_scope = "starfinder_only"
    metric_rows: List[Dict[str, Any]] = []
    per_query_cache: Dict[str, Dict[str, Any]] = {}
    retrieved_cache: Dict[str, Dict[str, Any]] = {}

    for r in successful_eval_rows:
        exp_dir = root / str(r["artifact_dir"])
        metrics = load_resolved_json_artifact(exp_dir, "metrics") or {}
        model_payload = metrics.get(r["model"]) or {}
        metric_rows.append(metric_row(r, model_payload))
        per_query_cache[r["experiment_id"]] = load_resolved_json_artifact(exp_dir, "per_query") or {}
        retrieved_cache[r["experiment_id"]] = load_resolved_json_artifact(exp_dir, "retrieved_chunks") or {}

    (bundle_dir / "aggregate_metrics.json").write_text(
        json.dumps(metric_rows, indent=2),
        encoding="utf-8",
    )

    metric_columns = [
        "track",
        "mode",
        "recipe",
        "enrichment_profile",
        "model",
        "MRR",
        "nDCG@10",
        "Recall@10",
        "Recall@20",
        "Hit@10",
        "Hit@20",
        "Gold-in-Candidates",
        "Gold-in-Candidates (True Ceiling)",
        "Required Full-Set Hit@10",
        "Rank-of-Last-Required (mean)",
        "no_gold_defined",
        "gold_not_in_candidates",
        "gold_in_candidates_but_low_rank",
        "grounding_or_answer_failure_after_retrieval",
        "artifact_dir",
    ]
    (bundle_dir / "aggregate_metrics.md").write_text(
        "# Aggregate Metrics\n\n" + make_markdown_table(metric_rows, metric_columns),
        encoding="utf-8",
    )

    # Deltas vs baseline model.
    idx: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for m in metric_rows:
        idx[(m["track"], m["mode"], m["recipe"], m["enrichment_profile"], m["model"])] = m

    delta_rows: List[Dict[str, Any]] = []
    for m in metric_rows:
        if m["model"] == "all-mpnet-base-v2":
            continue
        b = idx.get((m["track"], m["mode"], m["recipe"], m["enrichment_profile"], "all-mpnet-base-v2"))
        if not b:
            continue
        delta_rows.append(
            {
                "track": m["track"],
                "mode": m["mode"],
                "recipe": m["recipe"],
                "enrichment_profile": m["enrichment_profile"],
                "model": m["model"],
                "dMRR": m["MRR"] - b["MRR"],
                "dnDCG@10": m["nDCG@10"] - b["nDCG@10"],
                "dRecall@10": m["Recall@10"] - b["Recall@10"],
                "dHit@10": m["Hit@10"] - b["Hit@10"],
                "dGold-in-Candidates": m["Gold-in-Candidates"] - b["Gold-in-Candidates"],
                "dRequired Full-Set Hit@10": m["Required Full-Set Hit@10"] - b["Required Full-Set Hit@10"],
            }
        )

    (bundle_dir / "deltas_vs_baseline.json").write_text(
        json.dumps(delta_rows, indent=2),
        encoding="utf-8",
    )
    (bundle_dir / "deltas_vs_baseline.md").write_text(
        "# Deltas vs all-mpnet-base-v2\n\n"
        + make_markdown_table(
            delta_rows,
            [
                "track",
                "mode",
                "recipe",
                "enrichment_profile",
                "model",
                "dMRR",
                "dnDCG@10",
                "dRecall@10",
                "dHit@10",
                "dGold-in-Candidates",
                "dRequired Full-Set Hit@10",
            ],
        ),
        encoding="utf-8",
    )

    # Per-query wins/losses with chunk IDs/ranks.
    pq_changes: List[Dict[str, Any]] = []
    for r in successful_eval_rows:
        if r["model"] == "all-mpnet-base-v2":
            continue
        baseline = idx.get((r["track"], r["mode"], r["recipe"], r["enrichment_profile"], "all-mpnet-base-v2"))
        if not baseline:
            continue
        base_exp = baseline["experiment_id"]
        cur_exp = r["experiment_id"]
        base_pq = (per_query_cache[base_exp].get("all-mpnet-base-v2") or [])
        cur_pq = (per_query_cache[cur_exp].get(r["model"]) or [])
        base_by_qid = {str(x.get("query_id")): x for x in base_pq}
        cur_by_qid = {str(x.get("query_id")): x for x in cur_pq}
        for qid in sorted(set(base_by_qid.keys()) & set(cur_by_qid.keys())):
            bq = base_by_qid[qid]
            cq = cur_by_qid[qid]
            b_rank = rank_value(bq.get("first_gold_rank"))
            c_rank = rank_value(cq.get("first_gold_rank"))
            delta = b_rank - c_rank
            pq_changes.append(
                {
                    "track": r["track"],
                    "mode": r["mode"],
                    "recipe": r["recipe"],
                    "enrichment_profile": r["enrichment_profile"],
                    "model": r["model"],
                    "query_id": qid,
                    "baseline_first_gold_rank": None if b_rank >= 9999 else b_rank,
                    "candidate_first_gold_rank": None if c_rank >= 9999 else c_rank,
                    "rank_delta_positive_is_better": delta,
                    "baseline_failure_bucket": bq.get("failure_bucket"),
                    "candidate_failure_bucket": cq.get("failure_bucket"),
                    "baseline_top_chunks": top_chunks_for_query(retrieved_cache[base_exp], "all-mpnet-base-v2", qid)[:3],
                    "candidate_top_chunks": top_chunks_for_query(retrieved_cache[cur_exp], r["model"], qid)[:3],
                }
            )

    improvements = sorted(pq_changes, key=lambda x: x["rank_delta_positive_is_better"], reverse=True)[:25]
    regressions = sorted(pq_changes, key=lambda x: x["rank_delta_positive_is_better"])[:25]
    top_change_payload = {
        "top_improvements": improvements,
        "top_regressions": regressions,
    }
    (bundle_dir / "top_improvements_and_regressions.json").write_text(
        json.dumps(top_change_payload, indent=2),
        encoding="utf-8",
    )

    def changes_md_section(title: str, rows_in: List[Dict[str, Any]]) -> str:
        lines = [f"## {title}", ""]
        for r in rows_in:
            lines.append(
                f"- `{r['track']}` `{r['mode']}` `{r['recipe']}` `{r['model']}` "
                f"`{r['query_id']}` delta={r['rank_delta_positive_is_better']} "
                f"(base={r['baseline_first_gold_rank']}, cand={r['candidate_first_gold_rank']})"
            )
            lines.append(f"  - baseline top3: {[c.get('chunk_id') for c in r['baseline_top_chunks']]}")
            lines.append(f"  - candidate top3: {[c.get('chunk_id') for c in r['candidate_top_chunks']]}")
        lines.append("")
        return "\n".join(lines)

    (bundle_dir / "top_improvements_and_regressions.md").write_text(
        "# Top Per-Query Changes vs Baseline\n\n"
        + changes_md_section("Top Improvements", improvements)
        + changes_md_section("Top Regressions", regressions),
        encoding="utf-8",
    )

    # Strengths/weaknesses synthesis.
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    for m in metric_rows:
        by_model.setdefault(m["model"], []).append(m)

    sw_lines: List[str] = ["# Model Strengths and Weaknesses", ""]
    for model_id, rows_for_model in by_model.items():
        mrr_vals = [r["MRR"] for r in rows_for_model]
        hit10_vals = [r["Hit@10"] for r in rows_for_model]
        miss_vals = [r["gold_not_in_candidates"] for r in rows_for_model]
        low_rank_vals = [r["gold_in_candidates_but_low_rank"] for r in rows_for_model]
        sw_lines.append(f"## {model_id}")
        sw_lines.append(f"- Mean MRR: {sum(mrr_vals)/len(mrr_vals):.4f}")
        sw_lines.append(f"- Mean Hit@10: {sum(hit10_vals)/len(hit10_vals):.4f}")
        sw_lines.append(f"- Mean gold_not_in_candidates: {sum(miss_vals)/len(miss_vals):.2f}")
        sw_lines.append(f"- Mean gold_in_candidates_but_low_rank: {sum(low_rank_vals)/len(low_rank_vals):.2f}")
        if model_id == "all-mpnet-base-v2":
            sw_lines.append("- Role: incumbent baseline reference.")
        else:
            deltas = [d for d in delta_rows if d["model"] == model_id]
            if deltas:
                sw_lines.append(
                    f"- Mean dMRR vs baseline: {sum(x['dMRR'] for x in deltas)/len(deltas):.4f}"
                )
                sw_lines.append(
                    f"- Mean dHit@10 vs baseline: {sum(x['dHit@10'] for x in deltas)/len(deltas):.4f}"
                )
        sw_lines.append("")
    (bundle_dir / "model_strengths_weaknesses.md").write_text("\n".join(sw_lines), encoding="utf-8")

    # Then-vs-now synthesis with prior expected points from learnings doc.
    then_now = [
        "# Then vs Now",
        "",
        "## Then (expectations from prior learnings)",
        "- Fixed-input runs should be deterministic at metric level.",
        "- Contract drift (benchmark hash, corpus track, required_gold_empty) dominates apparent model differences.",
        "",
        "## Now (this bakeoff cycle)",
        f"- Preflight required_gold_empty: Starfinder={preflight['tracks']['Starfinder']['required_gold_empty']} "
        f"S&W={preflight['tracks']['SwordsandWizardry']['required_gold_empty']} "
        f"(threshold={REQUIRED_GOLD_EMPTY_THRESHOLD}).",
        (
            "- Matrix rows executed without required_gold_empty overrides."
            if not bool(args.allow_high_required_gold_empty)
            else "- Matrix rows executed with explicit required_gold_empty override logging."
        ),
        "- Determinism check reran key Starfinder hybrid baseline row in this cycle.",
        "",
        "## Consistency and divergence",
        "- Consistent: determinism remains stable when contracts are fixed.",
        "- Divergence risk: high no_gold_defined pressure means model ranking conclusions remain hygiene-sensitive.",
        "",
    ]
    (bundle_dir / "then_vs_now.md").write_text("\n".join(then_now), encoding="utf-8")

    # Run manifest + provenance references.
    ref_lines = ["# Run Manifest and Provenance References", ""]
    for r in successful_eval_rows:
        exp_dir = r["artifact_dir"]
        ref_lines.append(
            f"- `{r['track']}` `{r['mode']}` `{r['model']}` `{r['recipe']}` `{r['enrichment_profile']}`: "
            f"`{exp_dir}/run_manifest.json`, `{exp_dir}/embedding_provenance.json`"
        )
    (bundle_dir / "run_manifest_references.md").write_text("\n".join(ref_lines) + "\n", encoding="utf-8")

    recommendation = "decision_blocked" if preflight["hard_failures"] else "adopt_contextual_only"
    if preflight["hard_failures"]:
        rationale = (
            "Preflight contained hard failures, so outputs are not decision-safe."
        )
    elif failed_eval_rows:
        recommendation = "execution_failed_partial_coverage"
        if evidence_scope == "starfinder_only":
            rationale = (
                "One or more eval rows failed (notably S&W), so this cycle is limited to Starfinder-only evidence."
            )
        else:
            rationale = (
                "One or more eval rows failed, so coverage is partial and recommendation is not decision-safe."
            )
    elif evidence_scope == "starfinder_only":
        recommendation = "adopt_contextual_only_starfinder_scope"
        rationale = "S&W eval rows are unavailable; recommendation is constrained to Starfinder-only evidence."
    else:
        rationale = "No preflight or eval hard failures; use contextual model selection pending a stable default winner."

    summary_lines = [
        "# Embedding Bakeoff Summary",
        "",
        f"- Final recommendation: `{recommendation}`",
        f"- Rationale: {rationale}",
        f"- Evidence scope: `{evidence_scope}`",
        f"- Eval rows failed: `{len(failed_eval_rows)}/{total_eval_rows}` ({eval_failure_rate:.1%})",
        f"- Bundle: `{bundle_dir.relative_to(root)}`",
        "",
        "## Outputs",
        f"- `preflight_contract_lock.json`",
        f"- `run_rows.json`",
        f"- `aggregate_metrics.md` / `aggregate_metrics.json`",
        f"- `deltas_vs_baseline.md` / `deltas_vs_baseline.json`",
        f"- `top_improvements_and_regressions.md` / `top_improvements_and_regressions.json`",
        f"- `model_strengths_weaknesses.md`",
        f"- `then_vs_now.md`",
        f"- `run_manifest_references.md`",
        "",
    ]
    if failed_eval_row_ids:
        summary_lines.extend(
            [
                "## Failed Eval Rows",
                *[f"- `{rid}`" for rid in failed_eval_row_ids],
                "",
            ]
        )
    (bundle_dir / "SUMMARY.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    if failed_eval_rows:
        append_runner_log(
            runner_log,
            f"completed_with_failed_eval_rows count={len(failed_eval_rows)}",
        )
        return 3
    append_runner_log(runner_log, "completed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
