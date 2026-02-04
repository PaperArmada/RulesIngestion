from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Dict, Optional, Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sentence_transformers import SentenceTransformer


@dataclass(frozen=True)
class EmbeddingModelSpec:
    model_id: str
    model_name: str


MODEL_REGISTRY: Dict[str, EmbeddingModelSpec] = {
    "bge-m3": EmbeddingModelSpec("bge-m3", "BAAI/bge-m3"),
    "gte-multilingual-base": EmbeddingModelSpec("gte-multilingual-base", "Alibaba-NLP/gte-multilingual-base"),
    "embedding-gemma-300m": EmbeddingModelSpec("embedding-gemma-300m", "google/embedding-gemma-300m"),
    "nomic-embed-text-v2": EmbeddingModelSpec("nomic-embed-text-v2", "nomic-ai/nomic-embed-text-v2-moe"),
    "qwen3-embedding-0.6b": EmbeddingModelSpec("qwen3-embedding-0.6b", "Qwen/Qwen3-Embedding-0.6B"),
    "all-mpnet-base-v2": EmbeddingModelSpec("all-mpnet-base-v2", "sentence-transformers/all-mpnet-base-v2"),
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

    cache_folder = resolve_cache_folder()
    model_kwargs = {
        "model_name_or_path": model_name,
        "device": "cpu",
        "trust_remote_code": trust_remote_code,
    }
    if cache_folder:
        model_kwargs["cache_folder"] = cache_folder
    return SentenceTransformer(**model_kwargs)


def encode_texts(
    model: "SentenceTransformer",
    texts: Sequence[str],
    batch_size: int = 16,
) -> np.ndarray:
    embeddings = model.encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return np.array(embeddings, dtype=np.float32)
