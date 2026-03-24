"""NextPlaid retriever adapter used by targeted bakeoff scripts.

The adapter is intentionally small and deterministic:
- no query rewriting
- no reranking
- no post-retrieval expansion
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Dict, List, Mapping, Optional
from urllib import error, request


class NextPlaidError(RuntimeError):
    """Raised on transport/protocol issues with NextPlaid."""


@dataclass(frozen=True)
class NextPlaidSearchParams:
    """Search parameters passed through to NextPlaid."""

    top_k: int = 20
    n_ivf_probe: int = 8
    n_full_scores: int = 4096

    def to_dict(self) -> Dict[str, int]:
        return {
            "top_k": int(self.top_k),
            "n_ivf_probe": int(self.n_ivf_probe),
            "n_full_scores": int(self.n_full_scores),
        }


@dataclass(frozen=True)
class NextPlaidHit:
    """Single result row from NextPlaid."""

    raw_id: str
    score: float
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class NextPlaidQueryResult:
    """Per-query search response with latency and parsed hits."""

    query: str
    latency_ms: float
    hits: List[NextPlaidHit]
    raw_payload: Dict[str, Any]


def _default_transport(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]],
    timeout_sec: float,
) -> Dict[str, Any]:
    body: Optional[bytes] = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url=url, method=method.upper(), data=body, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise NextPlaidError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except error.URLError as exc:
        raise NextPlaidError(f"Failed request to {url}: {exc}") from exc

    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Some NextPlaid endpoints (notably async update routes) return plain text
        # like "Accepted". Preserve it in a normalized wrapper.
        return {"message": raw}
    if isinstance(parsed, str):
        return {"message": parsed}
    if not isinstance(parsed, dict):
        raise NextPlaidError(f"Unexpected payload type from {url}: {type(parsed)!r}")
    return parsed


class NextPlaidRetriever:
    """Thin client for the NextPlaid HTTP API."""

    def __init__(
        self,
        base_url: str,
        timeout_sec: float = 60.0,
        transport: Optional[Callable[[str, str, Optional[Dict[str, Any]], float], Dict[str, Any]]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = float(timeout_sec)
        self._transport = transport or _default_transport

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health", None)

    def create_index(self, index_name: str, nbits: int = 4) -> Dict[str, Any]:
        payload = {"name": str(index_name), "config": {"nbits": int(nbits)}}
        try:
            return self._request("POST", "/indices", payload)
        except NextPlaidError as exc:
            # NextPlaid returns 409 when the index already exists.
            # Treat that as non-fatal for idempotent build scripts.
            if "HTTP 409" not in str(exc):
                raise
            return {"name": str(index_name), "already_exists": True}

    def add_documents(
        self,
        index_name: str,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if metadata is None:
            metadata = [{} for _ in documents]
        if len(documents) != len(metadata):
            raise NextPlaidError("documents and metadata must have identical lengths")
        payload = {"documents": documents, "metadata": metadata}
        return self._request("POST", f"/indices/{index_name}/update_with_encoding", payload)

    def search_with_encoding(
        self,
        index_name: str,
        queries: List[str],
        params: NextPlaidSearchParams,
    ) -> List[NextPlaidQueryResult]:
        started = time.perf_counter()
        payload = {"queries": queries, "params": params.to_dict()}
        response = self._request("POST", f"/indices/{index_name}/search_with_encoding", payload)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        rows = self._extract_result_rows(response)
        if len(rows) != len(queries):
            raise NextPlaidError(
                f"Query/result length mismatch: queries={len(queries)} results={len(rows)}"
            )
        per_query_latency = elapsed_ms / max(1, len(queries))
        out: List[NextPlaidQueryResult] = []
        for idx, row in enumerate(rows):
            hits = self._extract_hits(row)
            out.append(
                NextPlaidQueryResult(
                    query=queries[idx],
                    latency_ms=float(row.get("latency_ms", per_query_latency)),
                    hits=hits,
                    raw_payload=dict(row),
                )
            )
        return out

    def map_hits_to_unit_ids(
        self,
        hits: List[NextPlaidHit],
        id_to_candidate: Mapping[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        mapped_unit_ids: List[str] = []
        missing_ids: List[str] = []
        for hit in hits:
            # NextPlaid 1.1.x may return integer document IDs in `document_ids`
            # and include canonical unit IDs in per-hit metadata.
            md_unit_id = str(hit.metadata.get("unit_id") or "").strip()
            if md_unit_id:
                mapped_unit_ids.append(md_unit_id)
                continue
            candidate = id_to_candidate.get(hit.raw_id)
            if candidate is None:
                missing_ids.append(hit.raw_id)
                continue
            unit_id = str(candidate.get("id") or "").strip()
            if unit_id:
                mapped_unit_ids.append(unit_id)
            else:
                missing_ids.append(hit.raw_id)
        return {
            "raw_result_ids": [h.raw_id for h in hits],
            "mapped_unit_ids": mapped_unit_ids,
            "missing_result_ids": missing_ids,
        }

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        return self._transport(method, url, payload, self.timeout_sec)

    @staticmethod
    def _extract_result_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = payload.get("results")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        # Some servers return single-query payloads with direct hits.
        if isinstance(payload.get("hits"), list):
            return [payload]
        raise NextPlaidError("search_with_encoding response missing `results` or `hits`")

    @staticmethod
    def _extract_hits(row: Dict[str, Any]) -> List[NextPlaidHit]:
        raw_hits = row.get("hits")
        if not isinstance(raw_hits, list):
            # NextPlaid 1.1.x search responses return:
            # { query_id, document_ids[], scores[], metadata[] }.
            doc_ids = row.get("document_ids")
            scores = row.get("scores")
            md_rows = row.get("metadata")
            if not isinstance(doc_ids, list):
                return []
            hits_from_arrays: List[NextPlaidHit] = []
            for idx, doc_id in enumerate(doc_ids):
                raw_id = str(doc_id).strip()
                if not raw_id:
                    continue
                score = 0.0
                if isinstance(scores, list) and idx < len(scores):
                    try:
                        score = float(scores[idx])
                    except (TypeError, ValueError):
                        score = 0.0
                metadata: Dict[str, Any] = {}
                if isinstance(md_rows, list) and idx < len(md_rows) and isinstance(md_rows[idx], dict):
                    metadata = dict(md_rows[idx])
                hits_from_arrays.append(NextPlaidHit(raw_id=raw_id, score=score, metadata=metadata))
            return hits_from_arrays
        hits: List[NextPlaidHit] = []
        for item in raw_hits:
            if not isinstance(item, dict):
                continue
            raw_id = str(
                item.get("id")
                or item.get("doc_id")
                or item.get("document_id")
                or item.get("chunk_id")
                or ""
            ).strip()
            if not raw_id:
                continue
            score = float(item.get("score", 0.0))
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            hits.append(NextPlaidHit(raw_id=raw_id, score=score, metadata=dict(metadata)))
        return hits

