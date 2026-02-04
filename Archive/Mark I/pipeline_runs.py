"""Run record helpers for rules ingestion pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple, Any, Dict
from uuid import uuid4

from config_generator import RulesetConfiguration
from diagnostics_store import (
    EnrichmentRunRecord,
    RunInputsSnapshot,
    RunOutputsSnapshot,
    save_enrichment_run,
    save_run_inputs,
    save_run_outputs,
)


def start_run_record(
    resolved_config: Optional[RulesetConfiguration],
    source_fingerprint: str,
    raw_blocks: list[dict],
    mongo_uri: Optional[str],
) -> Tuple[Optional[str], Optional[EnrichmentRunRecord]]:
    if not (resolved_config and mongo_uri):
        return None, None

    run_id = str(uuid4())
    run_record = EnrichmentRunRecord(
        run_id=run_id,
        ruleset_id=resolved_config.ruleset_id,
        config_version=resolved_config.version,
        source_fingerprint=source_fingerprint,
        status="running",
    )
    save_enrichment_run(run_record, mongo_uri)

    inputs_snapshot = RunInputsSnapshot(
        run_id=run_id,
        marker_output={"blocks": raw_blocks},
        config_snapshot=(
            resolved_config.model_dump(mode="json")
            if hasattr(resolved_config, "model_dump")
            else resolved_config.dict()
        ),
    )
    run_record.inputs_snapshot_id = save_run_inputs(inputs_snapshot, mongo_uri)
    save_enrichment_run(run_record, mongo_uri)
    return run_id, run_record


def finish_run_record(
    run_id: Optional[str],
    run_record: Optional[EnrichmentRunRecord],
    mongo_uri: Optional[str],
    outputs: Dict[str, Any],
) -> Optional[str]:
    if not (run_id and run_record and mongo_uri):
        return None

    outputs_snapshot = RunOutputsSnapshot(
        run_id=run_id,
        enriched=outputs["enriched"],
        coalesced=outputs["coalesced"],
        graph=outputs["graph"],
        llm_review=outputs.get("llm_review"),
        evaluation_queries=outputs["evaluation_queries"],
    )
    outputs_snapshot_id = save_run_outputs(outputs_snapshot, mongo_uri)
    run_record.outputs_snapshot_id = outputs_snapshot_id
    run_record.status = "succeeded"
    run_record.completed_at = datetime.now(timezone.utc)
    save_enrichment_run(run_record, mongo_uri)
    return outputs_snapshot_id
