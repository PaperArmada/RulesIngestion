from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _git_output(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _infer_mode_label(name: str) -> str:
    normalized = str(name or "").lower()
    if "_c_" in normalized or "raw_first_merge_rerank" in normalized:
        return "C"
    if "_b_" in normalized or "merged_only" in normalized:
        return "B"
    if "_a_" in normalized or "raw_only" in normalized:
        return "A"
    return ""


def build_repo_freeze_metadata(repo_root: Path, *, package_dir: Optional[Path] = None) -> Dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    package_path = Path(package_dir).resolve() if package_dir is not None else None
    uv_lock_path = repo_root / "uv.lock"
    return {
        "baseline_package_dir": str(package_path) if package_path is not None else "",
        "baseline_package_stamp": package_path.name if package_path is not None else "",
        "git_commit_sha": _git_output(repo_root, "rev-parse", "HEAD"),
        "git_tag": _git_output(repo_root, "describe", "--tags", "--exact-match", "HEAD"),
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "uv_lock_path": str(uv_lock_path.resolve()) if uv_lock_path.exists() else "",
        "uv_lock_sha256": sha256_file(uv_lock_path) if uv_lock_path.exists() else "",
    }


def infer_run_bundle_metadata(
    *,
    repo_root: Path,
    run_dir: Path,
    experiment_name: Optional[str] = None,
) -> Dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    run_dir = Path(run_dir).resolve()
    package_dir = run_dir.parent
    in_baseline_package = package_dir.parent.name == "v1_baseline"
    experiment_label = str(experiment_name or run_dir.name)
    mode_hint = _infer_mode_label(experiment_label)

    metadata = {
        "bundle_kind": "",
        "bundle_member_role": "",
        "bundle_member_mode_hint": mode_hint,
        "bundle_member_status": "",
        "baseline_package_dir": "",
        "baseline_package_stamp": "",
        "git_commit_sha": "",
        "git_tag": "",
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "uv_lock_path": "",
        "uv_lock_sha256": "",
    }
    if not in_baseline_package:
        return metadata

    freeze = build_repo_freeze_metadata(repo_root, package_dir=package_dir)
    return {
        "bundle_kind": "v1_baseline_package",
        "bundle_member_role": "baseline_suite_run",
        "bundle_member_mode_hint": mode_hint,
        "bundle_member_status": "candidate_canonical" if mode_hint == "C" else "noncanonical_comparator",
        **freeze,
    }
