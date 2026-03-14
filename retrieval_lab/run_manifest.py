from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_file_record(path_str: str) -> Dict[str, Any]:
    p = Path(path_str)
    if not path_str:
        return {"path": "", "exists": False}
    if not p.exists():
        return {"path": str(p), "exists": False}
    try:
        st = p.stat()
        return {
            "path": str(p),
            "exists": True,
            "size_bytes": int(st.st_size),
            "mtime_epoch": float(st.st_mtime),
            "sha256": _sha256_file(p),
        }
    except Exception as e:
        return {"path": str(p), "exists": True, "error": str(e)}


def build_run_manifest(
    *,
    experiment_id: str,
    argv: List[str],
    config_dict: Dict[str, Any],
    source_config_path: Optional[str] = None,
    query_batch_paths: Optional[List[str]] = None,
    query_batch_contract_paths: Optional[List[str]] = None,
    enhancement_profile_path: Optional[str] = None,
    benchmark_definition_snapshot_paths: Optional[List[str]] = None,
    benchmark_projection_snapshot_paths: Optional[List[str]] = None,
    corpus_index_path: Optional[str] = None,
    prod_readiness_path: Optional[str] = None,
    run_keys: Optional[Dict[str, Any]] = None,
    bundle_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    query_batch_paths = query_batch_paths or list(config_dict.get("query_batch_paths") or [])
    query_batch_contract_paths = query_batch_contract_paths or []
    benchmark_definition_snapshot_paths = benchmark_definition_snapshot_paths or []
    benchmark_projection_snapshot_paths = benchmark_projection_snapshot_paths or []

    env_subset = {
        "cwd": str(Path.cwd()),
        "python": os.environ.get("PYTHON", ""),
        "openai_api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
    }

    bundle_metadata = dict(bundle_metadata or {})
    manifest = {
        "version": "retrieval_lab_manifest_v1",
        "created_at": now,
        "experiment_id": experiment_id,
        "command": {"argv": list(argv)},
        "inputs": {
            "config_yaml": _safe_file_record(source_config_path or ""),
            "query_batches": [_safe_file_record(p) for p in query_batch_paths],
            "query_batch_contracts": [_safe_file_record(p) for p in query_batch_contract_paths],
            "enhancement_profile": _safe_file_record(enhancement_profile_path or ""),
            "benchmark_definition_snapshots": [
                _safe_file_record(p) for p in benchmark_definition_snapshot_paths
            ],
            "benchmark_projection_snapshots": [
                _safe_file_record(p) for p in benchmark_projection_snapshot_paths
            ],
            "corpus_index": _safe_file_record(corpus_index_path or ""),
            "prod_readiness": _safe_file_record(prod_readiness_path or ""),
        },
        "config": config_dict,
        "run_keys": run_keys or {},
        "bundle": {
            "kind": str(bundle_metadata.get("bundle_kind") or ""),
            "member_role": str(bundle_metadata.get("bundle_member_role") or ""),
            "member_mode_hint": str(bundle_metadata.get("bundle_member_mode_hint") or ""),
            "member_status": str(bundle_metadata.get("bundle_member_status") or ""),
            "baseline_package_dir": str(bundle_metadata.get("baseline_package_dir") or ""),
            "baseline_package_stamp": str(bundle_metadata.get("baseline_package_stamp") or ""),
        },
        "freeze": {
            "git_commit_sha": str(bundle_metadata.get("git_commit_sha") or ""),
            "git_tag": str(bundle_metadata.get("git_tag") or ""),
            "python_version": str(bundle_metadata.get("python_version") or ""),
            "uv_lock_path": str(bundle_metadata.get("uv_lock_path") or ""),
            "uv_lock_sha256": str(bundle_metadata.get("uv_lock_sha256") or ""),
        },
        "env": env_subset,
    }
    return manifest

