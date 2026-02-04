"""
Lightweight HTTP service for the rules ingestion pipeline.

Usage:
    uv run uvicorn ingestion_service:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from rules_ingestion_pipeline import (
    enrich_existing_chunks,
    process_pdf,
    load_marker_chunks,
    resolve_ruleset_config,
    generate_config_with_llm,
)
from config_profile import resolve_mongo_uri
from config_store import (
    ensure_indexes,
    fetch_latest_ruleset_config,
    get_mongo_client,
)
from diagnostics_store import (
    EnrichmentRunRecord,
    get_enrichment_runs_collection,
    get_run_outputs_collection,
    save_enrichment_run,
)


app = FastAPI(title="Rules Ingestion Service", version="0.1.0")
executor = ThreadPoolExecutor(max_workers=10)


class JobStatus(BaseModel):
    job_id: str
    status: str
    detail: Optional[str] = None
    document: Optional[str] = None
    enriched_path: Optional[str] = None
    graph_path: Optional[str] = None
    metrics_path: Optional[str] = None


class IngestRequest(BaseModel):
    source: str = Field(..., description="PDF path or Marker chunks JSON path")
    output_dir: str = Field(..., description="Output directory for enriched files")
    doc_id: Optional[str] = Field(None, description="Optional document ID")
    use_llm: bool = Field(False, description="Use LLM for better table extraction")
    enrich_only: bool = Field(False, description="Skip extraction, enrich existing chunks")
    markdown_source: Optional[str] = Field(
        None, description="Marker markdown output for metrics"
    )


class IngestResponse(BaseModel):
    job_id: str
    status: str


class ConfigGenerateRequest(BaseModel):
    ruleset_id: str
    marker_output_id: str
    source_fingerprint: str
    force_regenerate: bool = False


class RulesetConfigResponse(BaseModel):
    id: str
    ruleset_id: str
    version: str
    source_fingerprint: Optional[str]
    config_payload: Dict[str, Any]
    status: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RunCreateRequest(BaseModel):
    ruleset_id: str
    config_version: str
    source_fingerprint: str


class EnrichmentRunResponse(BaseModel):
    id: str
    ruleset_id: str
    config_version: str
    source_fingerprint: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    inputs_snapshot: Optional[str] = None
    outputs_snapshot: Optional[str] = None
    error_summary: Optional[str] = None


class EvaluationQueryResponse(BaseModel):
    id: str
    run_id: str
    query_text: str
    query_type: str
    content_kind: str
    expected_chunk_ids: List[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


jobs: Dict[str, JobStatus] = {}


def _run_ingest(job_id: str, request: IngestRequest) -> None:
    source = Path(request.source)
    output_dir = Path(request.output_dir)
    doc_id = request.doc_id or source.stem

    if not source.exists():
        jobs[job_id] = JobStatus(
            job_id=job_id,
            status="failed",
            detail=f"Source not found: {source}",
        )
        return

    if request.markdown_source:
        markdown_path = Path(request.markdown_source)
        if not markdown_path.exists():
            jobs[job_id] = JobStatus(
                job_id=job_id,
                status="failed",
                detail=f"Markdown source not found: {markdown_path}",
            )
            return

    try:
        if request.enrich_only:
            enrich_existing_chunks(
                str(source),
                str(output_dir),
                doc_id,
                request.markdown_source,
            )
        else:
            process_pdf(
                str(source),
                str(output_dir),
                request.use_llm,
                doc_id,
                request.markdown_source,
            )
    except ValueError as exc:
        jobs[job_id] = JobStatus(
            job_id=job_id,
            status="failed",
            detail=str(exc),
        )
        return
    except Exception as exc:
        jobs[job_id] = JobStatus(
            job_id=job_id,
            status="failed",
            detail=str(exc),
        )
        return

    enriched_dir = output_dir / "enriched"
    enriched_path = enriched_dir / f"{doc_id}.enriched.json"
    graph_path = enriched_dir / f"{doc_id}.graph.json"
    metrics_path = enriched_dir / f"{doc_id}.metrics.json"

    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="completed",
        document=doc_id,
        enriched_path=str(enriched_path),
        graph_path=str(graph_path),
        metrics_path=str(metrics_path) if metrics_path.exists() else None,
    )


@app.post("/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest) -> IngestResponse:
    job_id = str(uuid4())
    jobs[job_id] = JobStatus(job_id=job_id, status="queued")
    executor.submit(_run_ingest, job_id, request)
    return IngestResponse(job_id=job_id, status="queued")


@app.get("/ingest/{job_id}", response_model=JobStatus)
def ingest_status(job_id: str) -> JobStatus:
    status = jobs.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


def _resolve_marker_path(marker_output_id: str) -> Path:
    marker_path = Path(marker_output_id)
    if marker_path.is_file():
        return marker_path
    if marker_path.is_dir():
        for candidate in marker_path.iterdir():
            if candidate.suffix == ".json" and "_meta" not in candidate.name:
                return candidate
    raise FileNotFoundError(f"No marker chunks JSON found at {marker_output_id}")


def _config_to_response(config) -> RulesetConfigResponse:
    payload = config.model_dump(mode="json") if hasattr(config, "model_dump") else config.dict()
    return RulesetConfigResponse(
        id=payload.get("id", ""),
        ruleset_id=payload["ruleset_id"],
        version=payload["version"],
        source_fingerprint=payload.get("source_fingerprint"),
        config_payload=payload,
        status=payload.get("status"),
        created_at=payload.get("created_at", datetime.now(timezone.utc)),
        updated_at=payload.get("updated_at", datetime.now(timezone.utc)),
    )


@app.post("/api/rules-ingestion/configs/generate", response_model=RulesetConfigResponse)
def generate_ruleset_config(request: ConfigGenerateRequest) -> RulesetConfigResponse:
    mongo_uri = resolve_mongo_uri()
    client = get_mongo_client(mongo_uri)
    ensure_indexes(client)

    marker_chunks_path = _resolve_marker_path(request.marker_output_id)
    raw_blocks = load_marker_chunks(marker_chunks_path)

    llm_model = os.getenv("OPENAI_MODEL", "gpt-5.2-codex")
    llm_api_key = os.getenv("OPENAI_API_KEY")

    drift_detector = (lambda *_args: True) if request.force_regenerate else None

    config = resolve_ruleset_config(
        ruleset_id=request.ruleset_id,
        raw_blocks=raw_blocks,
        mongo_uri=mongo_uri,
        generator=lambda profile: generate_config_with_llm(
            profile,
            mongo_uri=mongo_uri,
            llm_model=llm_model,
            api_key=llm_api_key,
        ),
        drift_detector=drift_detector,
    )
    return _config_to_response(config)


@app.get("/api/rules-ingestion/configs/{ruleset_id}", response_model=RulesetConfigResponse)
def get_ruleset_config(ruleset_id: str) -> RulesetConfigResponse:
    mongo_uri = resolve_mongo_uri()
    config = fetch_latest_ruleset_config(ruleset_id, mongo_uri)
    if not config:
        raise HTTPException(status_code=404, detail="Ruleset config not found")
    return _config_to_response(config)


@app.post("/api/rules-ingestion/runs", response_model=EnrichmentRunResponse)
def start_enrichment_run(request: RunCreateRequest) -> EnrichmentRunResponse:
    mongo_uri = resolve_mongo_uri()
    record = EnrichmentRunRecord(
        run_id=str(uuid4()),
        ruleset_id=request.ruleset_id,
        config_version=request.config_version,
        source_fingerprint=request.source_fingerprint,
        status="pending",
    )
    run_id = save_enrichment_run(record, mongo_uri)
    return EnrichmentRunResponse(
        id=run_id,
        ruleset_id=record.ruleset_id,
        config_version=record.config_version,
        source_fingerprint=record.source_fingerprint,
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        inputs_snapshot=record.inputs_snapshot_id,
        outputs_snapshot=record.outputs_snapshot_id,
        error_summary=record.error_summary,
    )


@app.get("/api/rules-ingestion/runs/{run_id}", response_model=EnrichmentRunResponse)
def get_enrichment_run(run_id: str) -> EnrichmentRunResponse:
    mongo_uri = resolve_mongo_uri()
    client = get_mongo_client(mongo_uri)
    collection = get_enrichment_runs_collection(client)
    doc = collection.find_one({"run_id": run_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found")
    return EnrichmentRunResponse(
        id=str(doc.get("_id", run_id)),
        ruleset_id=doc["ruleset_id"],
        config_version=doc["config_version"],
        source_fingerprint=doc["source_fingerprint"],
        status=doc["status"],
        started_at=doc["started_at"],
        completed_at=doc.get("completed_at"),
        inputs_snapshot=doc.get("inputs_snapshot_id"),
        outputs_snapshot=doc.get("outputs_snapshot_id"),
        error_summary=doc.get("error_summary"),
    )


@app.get(
    "/api/rules-ingestion/runs/{run_id}/queries",
    response_model=List[EvaluationQueryResponse],
)
def get_run_queries(run_id: str) -> List[EvaluationQueryResponse]:
    mongo_uri = resolve_mongo_uri()
    client = get_mongo_client(mongo_uri)
    collection = get_run_outputs_collection(client)
    doc = collection.find_one({"run_id": run_id})
    if not doc:
        return []
    queries = doc.get("evaluation_queries") or []
    if isinstance(queries, dict) and "queries" in queries:
        queries = queries["queries"]
    response: List[EvaluationQueryResponse] = []
    for idx, entry in enumerate(queries):
        response.append(
            EvaluationQueryResponse(
                id=entry.get("id", f"{run_id}-{idx}"),
                run_id=run_id,
                query_text=entry.get("query_text", ""),
                query_type=entry.get("query_type", ""),
                content_kind=entry.get("content_kind", ""),
                expected_chunk_ids=entry.get("expected_chunk_ids", []),
            )
        )
    return response
