from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


CONTRACT_VERSION = "retrieval_lab_benchmark_contract_v2"
SUPPORTED_CONTRACT_VERSIONS = frozenset({
    "retrieval_lab_benchmark_contract_v1",
    CONTRACT_VERSION,
})


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def benchmark_contract_sidecar_path(benchmark_path: Path) -> Path:
    return benchmark_path.with_suffix(".contract.json")


def _sha256_jsonable(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _path_contract_matches(benchmark_value: str, current_value: str) -> bool:
    left = str(benchmark_value or "").strip().replace("\\", "/")
    right = str(current_value or "").strip().replace("\\", "/")
    if not left or not right:
        return left == right
    if left == right:
        return True
    return right.endswith(f"/{left}") or left.endswith(f"/{right}")


def benchmark_query_alignment_summary(
    queries: Iterable[Dict[str, Any]],
    *,
    corpus_ids: Iterable[str],
) -> Dict[str, Any]:
    corpus_id_set = {str(cid).strip() for cid in corpus_ids if str(cid).strip()}
    per_query: List[Dict[str, Any]] = []
    queries_total = 0
    queries_with_contract_ids = 0
    queries_with_missing_ids = 0
    queries_with_no_surviving_ids = 0
    missing_gold_ids_total = 0
    missing_id_set: set[str] = set()

    for query in queries:
        queries_total += 1
        qid = str(query.get("id") or "")
        gold_locations = query.get("gold_locations") or {}
        if isinstance(gold_locations, dict) and gold_locations:
            contract_ids = [str(x).strip() for x in gold_locations.keys() if str(x).strip()]
        else:
            contract_ids = [str(x).strip() for x in (query.get("gold_unit_ids") or []) if str(x).strip()]
        if not contract_ids:
            continue
        queries_with_contract_ids += 1
        present_ids = [cid for cid in contract_ids if cid in corpus_id_set]
        missing_ids = [cid for cid in contract_ids if cid not in corpus_id_set]
        if missing_ids:
            queries_with_missing_ids += 1
            missing_gold_ids_total += len(missing_ids)
            missing_id_set.update(missing_ids)
        if not present_ids:
            queries_with_no_surviving_ids += 1
        per_query.append(
            {
                "query_id": qid,
                "contract_gold_ids": contract_ids,
                "present_gold_ids": present_ids,
                "missing_gold_ids": missing_ids,
                "contract_gold_count": len(contract_ids),
                "present_gold_count": len(present_ids),
                "missing_gold_count": len(missing_ids),
            }
        )

    return {
        "queries_total": queries_total,
        "queries_with_contract_gold_ids": queries_with_contract_ids,
        "queries_with_missing_gold_ids": queries_with_missing_ids,
        "queries_with_no_surviving_gold_ids": queries_with_no_surviving_ids,
        "missing_gold_ids_total": missing_gold_ids_total,
        "missing_gold_ids_unique": sorted(missing_id_set),
        "per_query": per_query,
    }


def build_benchmark_contract(
    *,
    benchmark_path: Path,
    benchmark_sha256: Optional[str] = None,
    query_count: int,
    run_id: str,
    substrate_version: Optional[str],
    corpus_fingerprint: str,
    corpus_unit_count: int,
    benchmark_kind: str = "manual",
    lineage: Optional[Dict[str, Any]] = None,
    alignment_summary: Optional[Dict[str, Any]] = None,
    benchmark_definition_path: Optional[str] = None,
    benchmark_definition_sha256: Optional[str] = None,
    benchmark_surface: str = "active",
    corpus_content_fingerprint: Optional[str] = None,
    corpus_index_path: Optional[str] = None,
    corpus_index_sha256: Optional[str] = None,
    corpus_recipe: Optional[Dict[str, Any]] = None,
    projection_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    benchmark_path = benchmark_path.resolve()
    benchmark_sha = str(benchmark_sha256 or _sha256_file(benchmark_path))
    definition_path = str(Path(benchmark_definition_path).resolve()) if benchmark_definition_path else str(benchmark_path)
    definition_sha = str(benchmark_definition_sha256 or benchmark_sha)
    projection = {
        "path": str(benchmark_path),
        "sha256": benchmark_sha,
        "query_count": int(query_count),
        "benchmark_kind": str(benchmark_kind),
        "benchmark_surface": str(benchmark_surface or "active"),
    }
    return {
        "version": CONTRACT_VERSION,
        "benchmark_path": str(benchmark_path),
        "benchmark_sha256": benchmark_sha,
        "query_count": int(query_count),
        "benchmark_kind": str(benchmark_kind),
        "benchmark_surface": str(benchmark_surface or "active"),
        "benchmark_definition": {
            "path": definition_path,
            "sha256": definition_sha,
        },
        "benchmark_projection": projection,
        "run_contract": {
            "run_id": str(run_id),
            "substrate_version": str(substrate_version or ""),
            "corpus_fingerprint": str(corpus_fingerprint),
            "corpus_content_fingerprint": str(corpus_content_fingerprint or ""),
            "corpus_unit_count": int(corpus_unit_count),
            "corpus_index_path": str(Path(corpus_index_path).resolve()) if corpus_index_path else "",
            "corpus_index_sha256": str(corpus_index_sha256 or ""),
            "corpus_recipe": dict(corpus_recipe or {}),
        },
        "lineage": dict(lineage or {}),
        "alignment_summary": dict(alignment_summary or {}),
        "projection_metadata": dict(projection_metadata or {}),
    }


def write_benchmark_contract(contract_path: Path, contract: Dict[str, Any]) -> None:
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract, indent=2), encoding="utf-8")


def load_benchmark_contract(contract_path: Path) -> Dict[str, Any]:
    return json.loads(contract_path.read_text(encoding="utf-8"))


def load_benchmark_definition(benchmark_path: Path) -> Dict[str, Any]:
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def validate_benchmark_metadata_contract(
    *,
    benchmark_path: Path,
    query_count: int,
    alignment_summary: Dict[str, Any],
    substrate_version: Optional[str],
    corpus_recipe: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = load_benchmark_definition(benchmark_path)
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    queries = payload.get("queries") if isinstance(payload, dict) else None
    errors: List[str] = []
    metadata = metadata if isinstance(metadata, dict) else {}
    queries = queries if isinstance(queries, list) else []
    if not metadata:
        errors.append("benchmark metadata missing from benchmark definition")

    current_recipe = dict(corpus_recipe or {})
    expected_substrate_version = str(substrate_version or "").strip()
    metadata_substrate_version = str(metadata.get("substrate_version") or "").strip()
    if expected_substrate_version != metadata_substrate_version:
        errors.append(
            "benchmark metadata substrate_version mismatch: "
            f"benchmark={metadata_substrate_version!r} current={expected_substrate_version!r}"
        )

    expected_substrate_path = str(current_recipe.get("substrate_path") or "").strip()
    metadata_substrate_path = str(metadata.get("substrate_path") or "").strip()
    if expected_substrate_path and not _path_contract_matches(metadata_substrate_path, expected_substrate_path):
        errors.append(
            "benchmark metadata substrate_path mismatch: "
            f"benchmark={metadata_substrate_path!r} current={expected_substrate_path!r}"
        )

    expected_document_id = str(current_recipe.get("document_id") or "").strip()
    metadata_document_id = str(metadata.get("document_id") or "").strip()
    if expected_document_id and metadata_document_id != expected_document_id:
        errors.append(
            "benchmark metadata document_id mismatch: "
            f"benchmark={metadata_document_id!r} current={expected_document_id!r}"
        )

    chunk_recipe = metadata.get("chunk_recipe") if isinstance(metadata.get("chunk_recipe"), dict) else {}
    if current_recipe:
        expected_min_chars = current_recipe.get("min_chars")
        if expected_min_chars is not None and chunk_recipe.get("min_chars") != expected_min_chars:
            errors.append(
                "benchmark metadata chunk_recipe.min_chars mismatch: "
                f"benchmark={chunk_recipe.get('min_chars')!r} current={expected_min_chars!r}"
            )
        expected_merge_chunks = current_recipe.get("merge_chunks")
        if expected_merge_chunks is not None and bool(chunk_recipe.get("merge_chunks")) != bool(expected_merge_chunks):
            errors.append(
                "benchmark metadata chunk_recipe.merge_chunks mismatch: "
                f"benchmark={chunk_recipe.get('merge_chunks')!r} current={expected_merge_chunks!r}"
            )
        expected_merge_max_chars = current_recipe.get("merge_max_chars")
        if expected_merge_max_chars is not None and chunk_recipe.get("merge_max_chars") != expected_merge_max_chars:
            errors.append(
                "benchmark metadata chunk_recipe.merge_max_chars mismatch: "
                f"benchmark={chunk_recipe.get('merge_max_chars')!r} current={expected_merge_max_chars!r}"
            )

    if queries and len(queries) != int(query_count):
        errors.append(
            f"benchmark query count mismatch: benchmark={len(queries)} current={query_count}"
        )

    if int(alignment_summary.get("missing_gold_ids_total", 0) or 0) > 0:
        errors.append(
            "benchmark definition points at corpus-missing gold ids: "
            f"{int(alignment_summary.get('missing_gold_ids_total', 0))} missing id reference(s)"
        )

    return {
        "contract_path": "",
        "benchmark_path": str(benchmark_path.resolve()),
        "valid": not errors,
        "errors": errors,
        "contract": {
            "source": "benchmark_metadata",
            "metadata": metadata,
        },
        "alignment_summary": alignment_summary,
    }


def validate_benchmark_contract(
    *,
    benchmark_path: Path,
    contract_path: Path,
    query_count: int,
    run_id: str,
    substrate_version: Optional[str],
    corpus_fingerprint: str,
    alignment_summary: Dict[str, Any],
    benchmark_surface: Optional[str] = None,
    corpus_content_fingerprint: Optional[str] = None,
    corpus_index_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    contract = load_benchmark_contract(contract_path)
    errors: List[str] = []
    actual_sha = _sha256_file(benchmark_path)
    expected_sha = str(contract.get("benchmark_sha256") or "").strip()
    version = str(contract.get("version") or "").strip()
    if version not in SUPPORTED_CONTRACT_VERSIONS:
        errors.append(
            "contract version mismatch: "
            f"supported={sorted(SUPPORTED_CONTRACT_VERSIONS)} got {contract.get('version')!r}"
        )
    if str(contract.get("benchmark_path") or "") != str(benchmark_path.resolve()):
        errors.append("benchmark path mismatch between input benchmark and contract")
    if expected_sha != actual_sha:
        errors.append(
            "benchmark hash mismatch: "
            f"contract={expected_sha[:12]} current={actual_sha[:12]}"
        )
    if int(contract.get("query_count", -1)) != int(query_count):
        errors.append(
            f"benchmark query count mismatch: contract={contract.get('query_count')} current={query_count}"
        )
    run_contract = contract.get("run_contract") or {}
    if str(run_contract.get("run_id") or "") != str(run_id):
        errors.append(
            f"benchmark run_id mismatch: contract={run_contract.get('run_id')!r} current={run_id!r}"
        )
    if str(run_contract.get("substrate_version") or "") != str(substrate_version or ""):
        errors.append(
            "benchmark substrate_version mismatch: "
            f"contract={run_contract.get('substrate_version')!r} current={str(substrate_version or '')!r}"
        )
    if str(run_contract.get("corpus_fingerprint") or "") != str(corpus_fingerprint):
        errors.append(
            "benchmark corpus_fingerprint mismatch: "
            f"contract={str(run_contract.get('corpus_fingerprint') or '')[:12]} "
            f"current={corpus_fingerprint[:12]}"
        )
    contract_content_fp = str(run_contract.get("corpus_content_fingerprint") or "").strip()
    if contract_content_fp and corpus_content_fingerprint and contract_content_fp != str(corpus_content_fingerprint):
        errors.append(
            "benchmark corpus_content_fingerprint mismatch: "
            f"contract={contract_content_fp[:12]} current={str(corpus_content_fingerprint)[:12]}"
        )
    contract_index_sha = str(run_contract.get("corpus_index_sha256") or "").strip()
    if contract_index_sha and corpus_index_sha256 and contract_index_sha != str(corpus_index_sha256):
        errors.append(
            "benchmark corpus_index_sha256 mismatch: "
            f"contract={contract_index_sha[:12]} current={str(corpus_index_sha256)[:12]}"
        )
    contract_surface = str(
        (contract.get("benchmark_projection") or {}).get("benchmark_surface")
        or contract.get("benchmark_surface")
        or ""
    ).strip()
    if contract_surface and benchmark_surface and contract_surface != str(benchmark_surface):
        errors.append(
            f"benchmark surface mismatch: contract={contract_surface!r} current={str(benchmark_surface)!r}"
        )
    if int(alignment_summary.get("missing_gold_ids_total", 0) or 0) > 0:
        errors.append(
            "benchmark contract points at corpus-missing gold ids: "
            f"{int(alignment_summary.get('missing_gold_ids_total', 0))} missing id reference(s)"
        )

    return {
        "contract_path": str(contract_path.resolve()),
        "benchmark_path": str(benchmark_path.resolve()),
        "valid": not errors,
        "errors": errors,
        "contract": contract,
        "alignment_summary": alignment_summary,
    }


def build_prod_readiness_artifact(
    *,
    experiment_id: str,
    experiment_name: str,
    run_id: str,
    selected_surface: str,
    selected_model_id: str,
    benchmark_projection_path: str,
    benchmark_projection_sha256: str,
    benchmark_contract_path: str,
    benchmark_contract_sha256: str,
    corpus_fingerprint: str,
    corpus_content_fingerprint: str,
    corpus_index_path: str,
    corpus_index_sha256: str,
    contract_validations: List[Dict[str, Any]],
    metrics_by_model: Dict[str, Dict[str, Any]],
    bundle_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contract_valid = bool(contract_validations) and all(v.get("valid") for v in contract_validations)
    selected_metrics = dict(metrics_by_model.get(selected_model_id) or {})
    bundle_metadata = dict(bundle_metadata or {})
    metrics_summary = {
        "mrr": selected_metrics.get("mrr"),
        "gold_in_candidates_true_ceiling": selected_metrics.get("gold_in_candidates_true_ceiling"),
        "required_full_set_hit_at_10": (selected_metrics.get("required_full_set_hit_at_k") or {}).get(10),
        "outcome_classification": selected_metrics.get("outcome_classification"),
    }
    artifact = {
        "version": "retrieval_lab_prod_readiness_v1",
        "experiment_id": str(experiment_id),
        "experiment_name": str(experiment_name),
        "run_id": str(run_id),
        "selected_surface": str(selected_surface),
        "selected_model_id": str(selected_model_id),
        "contract_valid": contract_valid,
        "promotion_ready": contract_valid,
        "benchmark_projection": {
            "path": str(Path(benchmark_projection_path).resolve()),
            "sha256": str(benchmark_projection_sha256),
        },
        "benchmark_contract": {
            "path": str(Path(benchmark_contract_path).resolve()),
            "sha256": str(benchmark_contract_sha256),
        },
        "corpus_contract": {
            "corpus_fingerprint": str(corpus_fingerprint),
            "corpus_content_fingerprint": str(corpus_content_fingerprint),
            "corpus_index_path": str(Path(corpus_index_path).resolve()),
            "corpus_index_sha256": str(corpus_index_sha256),
        },
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
        "metrics_summary": metrics_summary,
        "contract_validation_summary": {
            "batch_count": len(contract_validations),
            "failed_batches": [
                {
                    "benchmark_path": validation.get("benchmark_path", ""),
                    "errors": list(validation.get("errors") or []),
                }
                for validation in contract_validations
                if not validation.get("valid")
            ],
            "summary_sha256": _sha256_jsonable(
                [
                    {
                        "benchmark_path": validation.get("benchmark_path", ""),
                        "valid": bool(validation.get("valid")),
                        "errors": list(validation.get("errors") or []),
                    }
                    for validation in contract_validations
                ]
            ),
        },
    }
    return artifact
