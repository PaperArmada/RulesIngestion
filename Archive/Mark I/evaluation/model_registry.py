from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sentence_transformers import SentenceTransformer


@dataclass(frozen=True)
class EmbeddingModelSpec:
    model_id: str
    model_name: str
    revision: str = ""
    recipe_source: str = ""
    recommended_query_prefix: str = ""
    recommended_passage_prefix: str = ""
    recommended_query_prompt_name: Optional[str] = None  # e.g. "query" for instruction models (used instead of prefix)
    recommended_pooling: str = "model_default"  # model_default | mean
    recommended_normalize: bool = True
    recommended_similarity_metric: str = "cosine"
    recommended_max_seq_len: Optional[int] = None


MODEL_REGISTRY: Dict[str, EmbeddingModelSpec] = {
    "bge-m3": EmbeddingModelSpec(
        "bge-m3",
        "BAAI/bge-m3",
        recipe_source="https://huggingface.co/BAAI/bge-m3",
        recommended_query_prefix="Represent this sentence for retrieving relevant passages: ",
        recommended_passage_prefix="",
    ),
    "gte-multilingual-base": EmbeddingModelSpec(
        "gte-multilingual-base",
        "Alibaba-NLP/gte-multilingual-base",
        recipe_source="https://huggingface.co/Alibaba-NLP/gte-multilingual-base",
    ),
    "embedding-gemma-300m": EmbeddingModelSpec(
        "embedding-gemma-300m",
        "google/embedding-gemma-300m",
        recipe_source="https://huggingface.co/google/embedding-gemma-300m",
    ),
    "nomic-embed-text-v2": EmbeddingModelSpec(
        "nomic-embed-text-v2",
        "nomic-ai/nomic-embed-text-v2-moe",
        recipe_source="https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe",
        recommended_query_prefix="search_query: ",
        recommended_passage_prefix="search_document: ",
    ),
    "qwen3-embedding-0.6b": EmbeddingModelSpec(
        "qwen3-embedding-0.6b",
        "Qwen/Qwen3-Embedding-0.6B",
        recipe_source="https://huggingface.co/Qwen/Qwen3-Embedding-0.6B",
        recommended_query_prompt_name="query",  # instruction model: use stored "query" prompt for queries
        recommended_passage_prefix="",  # documents encoded as-is
        recommended_pooling="model_default",
        recommended_normalize=True,
        recommended_similarity_metric="cosine",
    ),
    "all-mpnet-base-v2": EmbeddingModelSpec(
        "all-mpnet-base-v2",
        "sentence-transformers/all-mpnet-base-v2",
        recipe_source="https://huggingface.co/sentence-transformers/all-mpnet-base-v2",
    ),
    # New bakeoff candidates.
    "pplx-embed-v1-0.6B": EmbeddingModelSpec(
        "pplx-embed-v1-0.6B",
        "perplexity-ai/pplx-embed-v1-0.6B",
        recipe_source="https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6B",
        recommended_normalize=False,  # Unnormalized int8; compare via cosine (PPLX model card).
        recommended_query_prefix="",
        recommended_passage_prefix="",
    ),
    "pplx-embed-context-v1": EmbeddingModelSpec(
        "pplx-embed-context-v1",
        "perplexity-ai/pplx-embed-context-v1",
        recipe_source="https://huggingface.co/perplexity-ai/pplx-embed-context-v1",
    ),
    # jina-embeddings-v5-text-small: 677M params, Qwen3-0.6B-Base, last-token pooling.
    # Retrieval prompts: "Query: " (query) / "Document: " (passage).
    # CC BY-NC 4.0 — non-commercial use only.
    "jina-embeddings-v5-text-small": EmbeddingModelSpec(
        "jina-embeddings-v5-text-small",
        "jinaai/jina-embeddings-v5-text-small",
        recipe_source="https://huggingface.co/jinaai/jina-embeddings-v5-text-small",
        recommended_query_prefix="Query: ",
        recommended_passage_prefix="Document: ",
        recommended_pooling="model_default",
        recommended_normalize=True,
        recommended_similarity_metric="cosine",
    ),
}


def resolve_cache_folder() -> Optional[str]:
    cache_folder = (
        os.getenv("EMBEDDING_MODEL_PATH")
        or os.getenv("HF_HOME")
        or os.getenv("HUGGINGFACE_HUB_CACHE")
        or os.getenv("SENTENCE_TRANSFORMERS_HOME")
    )
    if cache_folder:
        Path(cache_folder).mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", cache_folder)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", cache_folder)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", cache_folder)
        return cache_folder
    return None


def load_model(model_name: str, trust_remote_code: bool = False) -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer  # type: ignore
    import torch  # type: ignore

    cache_folder = resolve_cache_folder()
    requested_device = (os.getenv("EMBEDDING_DEVICE") or "").strip()
    if requested_device:
        device = requested_device
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model_kwargs = {
        "model_name_or_path": model_name,
        "device": device,
        "trust_remote_code": trust_remote_code,
    }
    if cache_folder:
        model_kwargs["cache_folder"] = cache_folder
    model = SentenceTransformer(**model_kwargs)
    # Attach loader metadata used by bakeoff provenance.
    model._dm_loader_device = device  # type: ignore[attr-defined]
    model._dm_loader_module_path = __file__  # type: ignore[attr-defined]
    return model


def _apply_recipe_formatting(
    texts: Sequence[str],
    *,
    text_role: str,
    recipe_mode: str,
    model_id: Optional[str],
    query_prefix: str,
    passage_prefix: str,
) -> List[str]:
    formatted: List[str] = []
    spec = MODEL_REGISTRY.get(model_id or "")
    use_q = query_prefix
    use_p = passage_prefix
    if recipe_mode == "recommended" and spec:
        # Recommended recipe can override default prefixes.
        if not use_q:
            use_q = spec.recommended_query_prefix
        if not use_p:
            use_p = spec.recommended_passage_prefix
    prefix = use_q if text_role == "query" else use_p if text_role in ("passage", "candidate", "summary") else ""
    if not prefix:
        return [str(t) for t in texts]
    for t in texts:
        formatted.append(f"{prefix}{t}")
    return formatted


def _mean_pool_token_embeddings(token_embeddings: Any) -> np.ndarray:
    """Mean-pool token embeddings returned by SentenceTransformer.encode(..., output_value='token_embeddings')."""
    rows: List[np.ndarray] = []
    for te in token_embeddings:
        if te is None:
            rows.append(np.zeros((1,), dtype=np.float32))
            continue
        # te shape: [seq_len, hidden_dim]
        pooled = te.mean(dim=0)
        rows.append(pooled.detach().cpu().numpy())
    return np.array(rows, dtype=np.float32)


def _normalize_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return mat / norms


def encode_texts(
    model: "SentenceTransformer",
    texts: Sequence[str],
    batch_size: int = 16,
    *,
    model_id: Optional[str] = None,
    text_role: str = "passage",
    recipe_mode: str = "standardized",
    pooling: str = "mean",
    normalize: bool = True,
    max_seq_len: Optional[int] = None,
    query_prefix: str = "",
    passage_prefix: str = "",
    fail_on_missing_source: bool = False,
) -> np.ndarray:
    spec = MODEL_REGISTRY.get(model_id or "")
    if recipe_mode == "recommended" and fail_on_missing_source:
        if spec is None or not (spec.recipe_source or "").strip():
            raise ValueError(
                f"Recommended recipe requested but recipe source metadata is missing for model_id={model_id!r}."
            )

    use_pooling = pooling
    use_normalize = normalize
    use_max_seq_len = max_seq_len
    if recipe_mode == "recommended" and spec is not None:
        if spec.recommended_pooling:
            use_pooling = spec.recommended_pooling
        use_normalize = bool(spec.recommended_normalize)
        if spec.recommended_max_seq_len is not None:
            use_max_seq_len = int(spec.recommended_max_seq_len)

    if use_max_seq_len is not None:
        model.max_seq_length = int(use_max_seq_len)

    use_prompt_name: Optional[str] = None
    if recipe_mode == "recommended" and spec is not None and getattr(spec, "recommended_query_prompt_name", None):
        if text_role == "query":
            use_prompt_name = spec.recommended_query_prompt_name

    if use_prompt_name:
        formatted_texts = [str(t) for t in texts]
    else:
        formatted_texts = _apply_recipe_formatting(
            texts,
            text_role=text_role,
            recipe_mode=recipe_mode,
            model_id=model_id,
            query_prefix=query_prefix,
            passage_prefix=passage_prefix,
        )

    encode_kwargs: Dict[str, Any] = {
        "batch_size": batch_size,
        "normalize_embeddings": bool(use_normalize),
        "show_progress_bar": True,
    }
    if model_id == "jina-embeddings-v5-text-small":
        encode_kwargs["task"] = "retrieval"
    if use_prompt_name:
        encode_kwargs["prompt_name"] = use_prompt_name

    if use_pooling == "model_default":
        embeddings = model.encode(
            list(formatted_texts),
            **encode_kwargs,
        )
        return np.array(embeddings, dtype=np.float32)
    if use_pooling != "mean":
        raise ValueError(f"Unsupported embedding pooling mode: {use_pooling}")

    encode_kwargs.pop("normalize_embeddings", None)
    encode_kwargs["normalize_embeddings"] = False
    encode_kwargs["output_value"] = "token_embeddings"
    encode_kwargs["convert_to_numpy"] = False
    token_embeddings = model.encode(
        list(formatted_texts),
        **encode_kwargs,
    )
    pooled = _mean_pool_token_embeddings(token_embeddings)
    if use_normalize:
        pooled = _normalize_rows(pooled)
    return np.array(pooled, dtype=np.float32)
