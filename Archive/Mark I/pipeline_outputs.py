"""Output helpers for rules ingestion pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from enrichment import EnrichedChunk


def write_enrichment_outputs(
    enriched_dir: Path,
    doc_id: str,
    enriched_chunks: list[EnrichedChunk],
    coalesced_chunks: list[EnrichedChunk],
    graph: Any,
    review_payload: Optional[dict],
    evaluation_queries: list[dict],
    metrics: Optional[dict],
) -> Dict[str, Any]:
    enriched_dir.mkdir(parents=True, exist_ok=True)

    enriched_payload = {
        "document": doc_id,
        "chunks": [c.to_dict() for c in enriched_chunks],
    }
    chunks_output = enriched_dir / f"{doc_id}.enriched.json"
    with open(chunks_output, "w", encoding="utf-8") as handle:
        json.dump(enriched_payload, handle, indent=2)

    coalesced_payload = {
        "document": doc_id,
        "chunks": [c.to_dict() for c in coalesced_chunks],
    }
    coalesced_output = enriched_dir / f"{doc_id}.coalesced.json"
    with open(coalesced_output, "w", encoding="utf-8") as handle:
        json.dump(coalesced_payload, handle, indent=2)

    graph_payload = graph.to_dict()
    graph_output = enriched_dir / f"{doc_id}.graph.json"
    with open(graph_output, "w", encoding="utf-8") as handle:
        json.dump(graph_payload, handle, indent=2)

    evaluation_payload = {"document": doc_id, "queries": evaluation_queries}
    evaluation_output = enriched_dir / f"{doc_id}.evaluation_queries.json"
    with open(evaluation_output, "w", encoding="utf-8") as handle:
        json.dump(evaluation_payload, handle, indent=2)

    if review_payload:
        review_output = enriched_dir / f"{doc_id}.llm_review.json"
        with open(review_output, "w", encoding="utf-8") as handle:
            json.dump(review_payload, handle, indent=2)

    if metrics is not None:
        metrics_output = enriched_dir / f"{doc_id}.metrics.json"
        with open(metrics_output, "w", encoding="utf-8") as handle:
            json.dump(metrics, handle, indent=2)

    return {
        "enriched": enriched_payload,
        "coalesced": coalesced_payload,
        "graph": graph_payload,
        "llm_review": review_payload,
        "evaluation_queries": evaluation_payload,
    }
