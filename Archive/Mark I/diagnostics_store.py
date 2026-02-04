"""Diagnostics persistence utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

from config_store import (
    DEFAULT_DB_NAME,
    ENRICHMENT_RUNS_COLLECTION,
    RUN_INPUTS_COLLECTION,
    RUN_OUTPUTS_COLLECTION,
    get_mongo_client,
)

try:
    from pymongo.collection import Collection
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise RuntimeError("pymongo is required for MongoDB persistence helpers.") from exc


DIAGNOSTICS_COLLECTION = "ruleset_config_diagnostics"
RUN_STATUS_VALUES = {"pending", "running", "succeeded", "failed", "partial"}


class DiagnosticsRetentionPolicy(BaseModel):
    """Retention policy for diagnostics records."""

    retention_days: int = 30
    scope: str = "config_generation"


class GenerationDiagnostics(BaseModel):
    """Diagnostics record for failed config generation attempts."""

    ruleset_id: str
    doc_signature: str
    attempt_number: int
    profile_summary: Optional[str] = None
    prompt_payload: Optional[dict] = None
    model_output: Optional[str] = None
    validation_errors: List[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


class EnrichmentRunRecord(BaseModel):
    """Metadata record for a single enrichment run."""

    run_id: str
    ruleset_id: str
    config_version: str
    source_fingerprint: str
    status: str = "pending"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    inputs_snapshot_id: Optional[str] = None
    outputs_snapshot_id: Optional[str] = None
    error_summary: Optional[str] = None


class RunInputsSnapshot(BaseModel):
    """Snapshot of inputs used for a run."""

    run_id: str
    marker_output: dict
    config_snapshot: dict
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunOutputsSnapshot(BaseModel):
    """Snapshot of outputs produced by a run."""

    run_id: str
    enriched: dict
    coalesced: dict
    graph: dict
    llm_review: Optional[dict] = None
    evaluation_queries: Optional[dict] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def get_diagnostics_collection(client, db_name: str = DEFAULT_DB_NAME) -> Collection:
    return client[db_name][DIAGNOSTICS_COLLECTION]


def get_enrichment_runs_collection(client, db_name: str = DEFAULT_DB_NAME) -> Collection:
    return client[db_name][ENRICHMENT_RUNS_COLLECTION]


def get_run_inputs_collection(client, db_name: str = DEFAULT_DB_NAME) -> Collection:
    return client[db_name][RUN_INPUTS_COLLECTION]


def get_run_outputs_collection(client, db_name: str = DEFAULT_DB_NAME) -> Collection:
    return client[db_name][RUN_OUTPUTS_COLLECTION]


def apply_retention_policy(
    diagnostics: GenerationDiagnostics, policy: DiagnosticsRetentionPolicy
) -> GenerationDiagnostics:
    """Apply retention expiry if not already set."""
    if diagnostics.expires_at is None:
        diagnostics.expires_at = diagnostics.created_at + timedelta(days=policy.retention_days)
    return diagnostics


def save_generation_diagnostics(
    diagnostics: GenerationDiagnostics,
    mongo_uri: str,
    policy: Optional[DiagnosticsRetentionPolicy] = None,
    db_name: str = DEFAULT_DB_NAME,
) -> str:
    policy = policy or DiagnosticsRetentionPolicy()
    diagnostics = apply_retention_policy(diagnostics, policy)
    client = get_mongo_client(mongo_uri)
    collection = get_diagnostics_collection(client, db_name)
    payload = diagnostics.model_dump() if hasattr(diagnostics, "model_dump") else diagnostics.dict()
    result = collection.insert_one(payload)
    return str(result.inserted_id)


def save_enrichment_run(
    record: EnrichmentRunRecord, mongo_uri: str, db_name: str = DEFAULT_DB_NAME
) -> str:
    client = get_mongo_client(mongo_uri)
    collection = get_enrichment_runs_collection(client, db_name)
    payload = record.model_dump() if hasattr(record, "model_dump") else record.dict()
    if payload["status"] not in RUN_STATUS_VALUES:
        raise ValueError(f"Invalid run status: {payload['status']}")
    result = collection.replace_one({"run_id": record.run_id}, payload, upsert=True)
    if result.upserted_id:
        return str(result.upserted_id)
    doc = collection.find_one({"run_id": record.run_id})
    return str(doc.get("_id")) if doc else ""


def save_run_inputs(
    snapshot: RunInputsSnapshot, mongo_uri: str, db_name: str = DEFAULT_DB_NAME
) -> str:
    client = get_mongo_client(mongo_uri)
    collection = get_run_inputs_collection(client, db_name)
    payload = snapshot.model_dump() if hasattr(snapshot, "model_dump") else snapshot.dict()
    result = collection.insert_one(payload)
    return str(result.inserted_id)


def save_run_outputs(
    snapshot: RunOutputsSnapshot, mongo_uri: str, db_name: str = DEFAULT_DB_NAME
) -> str:
    client = get_mongo_client(mongo_uri)
    collection = get_run_outputs_collection(client, db_name)
    payload = snapshot.model_dump() if hasattr(snapshot, "model_dump") else snapshot.dict()
    result = collection.insert_one(payload)
    return str(result.inserted_id)
