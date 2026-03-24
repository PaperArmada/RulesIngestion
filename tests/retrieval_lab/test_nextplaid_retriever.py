from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from typing import Any, Dict, List, Optional, Tuple

import pytest

from retrieval_lab.retrievers.nextplaid import (
    NextPlaidError,
    NextPlaidRetriever,
    NextPlaidSearchParams,
)


class _CallRecorder:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, Optional[Dict[str, Any]], float]] = []

    def transport(
        self,
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]],
        timeout_sec: float,
    ) -> Dict[str, Any]:
        self.calls.append((method, url, payload, timeout_sec))
        if url.endswith("/health"):
            return {"status": "ok"}
        if url.endswith("/search_with_encoding"):
            return {
                "results": [
                    {
                        "latency_ms": 3.0,
                        "hits": [{"id": "u1", "score": 0.9, "metadata": {"page": 1}}],
                    }
                ]
            }
        return {}


def test_search_forwards_params_and_parses_hits() -> None:
    rec = _CallRecorder()
    r = NextPlaidRetriever("http://example.test", transport=rec.transport)
    params = NextPlaidSearchParams(top_k=20, n_ivf_probe=8, n_full_scores=4096)
    results = r.search_with_encoding("idx", ["hello"], params)

    assert len(results) == 1
    assert results[0].hits[0].raw_id == "u1"
    assert results[0].hits[0].score == pytest.approx(0.9)

    method, url, payload, _ = rec.calls[-1]
    assert method == "POST"
    assert url.endswith("/indices/idx/search_with_encoding")
    assert payload is not None
    assert payload["params"] == {"top_k": 20, "n_ivf_probe": 8, "n_full_scores": 4096}


def test_map_hits_to_unit_ids_reports_missing_ids() -> None:
    rec = _CallRecorder()
    r = NextPlaidRetriever("http://example.test", transport=rec.transport)
    res = r.search_with_encoding("idx", ["hello"], NextPlaidSearchParams())
    mapped = r.map_hits_to_unit_ids(res[0].hits, {"u1": {"id": "canon_1"}})
    assert mapped["mapped_unit_ids"] == ["canon_1"]
    assert mapped["missing_result_ids"] == []

    mapped_missing = r.map_hits_to_unit_ids(res[0].hits, {})
    assert mapped_missing["mapped_unit_ids"] == []
    assert mapped_missing["missing_result_ids"] == ["u1"]


def test_length_mismatch_raises_error() -> None:
    def bad_transport(_: str, __: str, ___: Optional[Dict[str, Any]], ____: float) -> Dict[str, Any]:
        return {"results": []}

    r = NextPlaidRetriever("http://example.test", transport=bad_transport)
    with pytest.raises(NextPlaidError):
        r.search_with_encoding("idx", ["q1"], NextPlaidSearchParams())


def test_controlled_http_integration() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if self.path.endswith("/search_with_encoding"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "results": [
                                {"hits": [{"id": "u1", "score": 1.0, "metadata": {}}]},
                                {"hits": [{"id": "u2", "score": 0.5, "metadata": {}}]},
                            ]
                        }
                    ).encode("utf-8")
                )
                return
            if self.path == "/indices":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            if self.path.startswith("/indices/"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        retriever = NextPlaidRetriever(base)
        assert retriever.health()["status"] == "ok"
        retriever.create_index("idx", 4)
        retriever.add_documents("idx", ["a"], [{"unit_id": "u1"}])
        results = retriever.search_with_encoding("idx", ["q1", "q2"], NextPlaidSearchParams())
        assert [h.raw_id for h in results[0].hits] == ["u1"]
        assert [h.raw_id for h in results[1].hits] == ["u2"]
    finally:
        server.shutdown()
        server.server_close()


def test_search_parses_document_ids_shape_and_metadata_unit_id_mapping() -> None:
    def transport(_: str, __: str, ___: Optional[Dict[str, Any]], ____: float) -> Dict[str, Any]:
        return {
            "results": [
                {
                    "query_id": 0,
                    "document_ids": [101, 202],
                    "scores": [1.0, 0.5],
                    "metadata": [{"unit_id": "u_101"}, {"unit_id": "u_202"}],
                }
            ]
        }

    r = NextPlaidRetriever("http://example.test", transport=transport)
    res = r.search_with_encoding("idx", ["q1"], NextPlaidSearchParams())
    assert [h.raw_id for h in res[0].hits] == ["101", "202"]
    mapped = r.map_hits_to_unit_ids(res[0].hits, {})
    assert mapped["mapped_unit_ids"] == ["u_101", "u_202"]
    assert mapped["missing_result_ids"] == []

