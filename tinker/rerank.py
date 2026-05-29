"""Cross-encoder reranker adapter for tinker.

Wraps `retrieval_lab.reranker.rerank_candidates` with a default model of
`BAAI/bge-reranker-v2-m3` (current open-standard cross-encoder for 2026,
per Docs/Design/MODELS-Intent-Routed-Retrieval.md).

The model is loaded lazily on first call to `load_reranker()` and cached
at module level so subsequent calls reuse the same instance.

Device selection: defaults to CUDA when available (~30x speedup on the
RTX 4080 for a 100-candidate pool vs CPU). Set TINKER_RERANK_DEVICE=cpu
to force CPU.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def _maybe_enable_hf_offline(model_name: str) -> None:
    """If the model is already in the local HF cache, pin offline mode.

    sentence-transformers fires a `HEAD` against huggingface.co on every
    load to validate cache freshness, which prints an "unauthenticated
    request" warning and adds a network round-trip. When the model is
    cached, we don't need that check — HF_HUB_OFFLINE=1 short-circuits
    it. If the model isn't cached yet, we leave the env var alone so
    the first-time download can happen normally.
    """
    if os.environ.get("HF_HUB_OFFLINE"):
        return
    hub_root = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))) / "hub"
    if not hub_root.is_dir():
        return
    # repo-id "BAAI/bge-reranker-v2-m3" lands at "models--BAAI--bge-reranker-v2-m3".
    repo_dir = hub_root / ("models--" + model_name.replace("/", "--"))
    if not repo_dir.is_dir():
        return
    snapshots = repo_dir / "snapshots"
    if snapshots.is_dir() and any(snapshots.iterdir()):
        os.environ["HF_HUB_OFFLINE"] = "1"


# Pin offline mode for the default reranker model at import time (the most
# common case). Other models picked at runtime will fall through to the
# online path naturally.
_maybe_enable_hf_offline(DEFAULT_RERANKER_MODEL)


from retrieval_lab.reranker import (  # noqa: E402  imports after env tweak
    load_cross_encoder,
    rerank_candidates,
)

_LOADED: dict[str, Any] = {}


def _pick_device() -> str:
    override = os.environ.get("TINKER_RERANK_DEVICE")
    if override:
        return override
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def load_reranker(model_name: str = DEFAULT_RERANKER_MODEL) -> Any:
    """Load a cross-encoder, cached at module level by model_name.

    First call for a given model triggers a download (~2 GB for
    bge-reranker-v2-m3) into the local Hugging Face cache. Subsequent
    calls return the cached instance.

    Device is picked once at first load and frozen for the module's
    lifetime; subsequent calls return the cached instance regardless of
    the env var.
    """
    if model_name not in _LOADED:
        device = _pick_device()
        # retrieval_lab.reranker.load_cross_encoder ignores device kwargs,
        # so reach into sentence-transformers directly when we want CUDA.
        if device != "cpu":
            from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]

            _LOADED[model_name] = CrossEncoder(model_name, device=device)
        else:
            _LOADED[model_name] = load_cross_encoder(model_name)
    return _LOADED[model_name]


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    top_k: int = 10,
    model_name: str = DEFAULT_RERANKER_MODEL,
    text_key: str = "text",
    id_key: str = "id",
) -> list[dict[str, Any]]:
    """Rerank candidates by query-text relevance.

    candidates: list of dicts each with `text_key` ("text") and `id_key`
        ("id"). The default `id_key` matches what
        `retrieval_lab.substrate_loader.load_evidence_units` returns.
    Returns the top_k candidates sorted by rerank score descending, with
    a new `rerank_score` field added.
    """
    model = load_reranker(model_name)
    return rerank_candidates(
        query=query,
        candidates=candidates,
        model=model,
        top_k=top_k,
        text_key=text_key,
        id_key=id_key,
    )
