from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


_JSON_ARTIFACT_KINDS = frozenset({
    "metrics",
    "per_query",
    "retrieved_chunks",
    "failure_buckets",
    "benchmark",
    "benchmark_contract",
    "prod_readiness",
    "evaluation_surfaces",
})


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _surface_name(value: Any) -> str:
    return str(value or "").strip()


def _append_surface(labels: list[str], label: str) -> None:
    normalized = _surface_name(label)
    if normalized and normalized not in labels:
        labels.append(normalized)


def _candidate_surfaces(
    *,
    experiment_dir: Path,
    preferred_surface: Optional[str] = None,
) -> list[str]:
    labels: list[str] = []
    _append_surface(labels, preferred_surface or "")

    prod_readiness = _load_json_if_exists(experiment_dir / "prod_readiness.json")
    if isinstance(prod_readiness, dict):
        _append_surface(labels, prod_readiness.get("selected_surface"))

    surfaces_payload = _load_json_if_exists(experiment_dir / "evaluation_surfaces.json")
    if isinstance(surfaces_payload, dict):
        for label in surfaces_payload.keys():
            _append_surface(labels, label)

    # Prefer the clean subset when multiple surfaces exist.
    _append_surface(labels, "clean_subset")
    _append_surface(labels, "active")
    _append_surface(labels, "full_working_set")
    return labels


def _artifact_candidates(kind: str, surface: str) -> list[str]:
    if kind == "metrics":
        return ["metrics.json"] if surface == "active" else [f"metrics.{surface}.json"]
    if kind == "per_query":
        return ["per_query.json"] if surface == "active" else [f"per_query.{surface}.json"]
    if kind == "retrieved_chunks":
        return ["retrieved_chunks.json"] if surface == "active" else [f"retrieved_chunks.{surface}.json"]
    if kind == "failure_buckets":
        return ["failure_buckets.json"] if surface == "active" else [f"failure_buckets.{surface}.json"]
    if kind == "report":
        return ["REPORT.md"] if surface == "active" else [f"REPORT.{surface}.md"]
    if kind == "benchmark":
        return [f"benchmark.{surface}.json"]
    if kind == "benchmark_contract":
        return [f"benchmark.{surface}.contract.json"]
    if kind == "prod_readiness":
        return ["prod_readiness.json"]
    if kind == "evaluation_surfaces":
        return ["evaluation_surfaces.json"]
    raise ValueError(f"Unsupported artifact kind: {kind}")


def _resolve_artifact_for_surface(experiment_dir: Path, kind: str, surface: str) -> Optional[Path]:
    for name in _artifact_candidates(kind, surface):
        path = experiment_dir / name
        if path.exists():
            return path.resolve()
    return None


def resolve_artifact_path(
    experiment_dir: Path,
    kind: str,
    *,
    preferred_surface: Optional[str] = None,
) -> Optional[Path]:
    experiment_dir = Path(experiment_dir)
    if kind in {"prod_readiness", "evaluation_surfaces"}:
        return _resolve_artifact_for_surface(experiment_dir, kind, "active")

    for surface in _candidate_surfaces(experiment_dir=experiment_dir, preferred_surface=preferred_surface):
        path = _resolve_artifact_for_surface(experiment_dir, kind, surface)
        if path is not None:
            return path
    return None


def resolve_run_artifacts(
    experiment_dir: Path,
    *,
    preferred_surface: Optional[str] = None,
) -> Dict[str, Any]:
    experiment_dir = Path(experiment_dir)
    prod_readiness_path = resolve_artifact_path(experiment_dir, "prod_readiness")
    evaluation_surfaces_path = resolve_artifact_path(experiment_dir, "evaluation_surfaces")
    prod_readiness = _load_json_if_exists(prod_readiness_path) if prod_readiness_path else None
    evaluation_surfaces = _load_json_if_exists(evaluation_surfaces_path) if evaluation_surfaces_path else None

    selected_surface = _surface_name(preferred_surface or "")
    if not selected_surface and isinstance(prod_readiness, dict):
        selected_surface = _surface_name(prod_readiness.get("selected_surface"))

    resolved_surface = ""
    metrics_path: Optional[Path] = None
    for surface in _candidate_surfaces(experiment_dir=experiment_dir, preferred_surface=selected_surface):
        candidate = _resolve_artifact_for_surface(experiment_dir, "metrics", surface)
        if candidate is not None:
            resolved_surface = surface
            metrics_path = candidate
            break

    if not resolved_surface:
        resolved_surface = selected_surface or "active"

    artifacts: Dict[str, str] = {}
    for kind in (
        "metrics",
        "per_query",
        "retrieved_chunks",
        "failure_buckets",
        "report",
        "benchmark",
        "benchmark_contract",
    ):
        if kind == "metrics" and metrics_path is not None:
            artifacts[kind] = str(metrics_path)
            continue
        path = resolve_artifact_path(experiment_dir, kind, preferred_surface=resolved_surface)
        artifacts[kind] = str(path) if path is not None else ""

    return {
        "experiment_dir": str(experiment_dir.resolve()),
        "selected_surface": resolved_surface,
        "selected_model_id": str((prod_readiness or {}).get("selected_model_id") or ""),
        "prod_readiness_path": str(prod_readiness_path) if prod_readiness_path is not None else "",
        "evaluation_surfaces_path": (
            str(evaluation_surfaces_path) if evaluation_surfaces_path is not None else ""
        ),
        "artifacts": artifacts,
        "prod_readiness": prod_readiness if isinstance(prod_readiness, dict) else {},
        "evaluation_surfaces": evaluation_surfaces if isinstance(evaluation_surfaces, dict) else {},
    }


def load_resolved_json_artifact(
    experiment_dir: Path,
    kind: str,
    *,
    preferred_surface: Optional[str] = None,
) -> Any:
    if kind not in _JSON_ARTIFACT_KINDS:
        raise ValueError(f"{kind!r} is not a JSON artifact kind")

    resolved = resolve_run_artifacts(experiment_dir, preferred_surface=preferred_surface)
    if kind == "prod_readiness":
        path_str = resolved.get("prod_readiness_path") or ""
    elif kind == "evaluation_surfaces":
        path_str = resolved.get("evaluation_surfaces_path") or ""
    else:
        path_str = str((resolved.get("artifacts") or {}).get(kind) or "")
    if not path_str:
        return None
    return json.loads(Path(path_str).read_text(encoding="utf-8"))
