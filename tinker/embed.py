"""Corpus embedding via Ollama embedder with cache + on-disk artifact.

Output layout matches `retrieval_lab`'s embedding store so downstream code
that reads `corpus_index.json` + `corpus.npy` works identically:

  <out_dir>/corpus_index.json   # {model, ids, unit_id_to_index, dim, ...}
  <out_dir>/corpus.npy          # float32 ndarray [N, dim]

Cache: embeddings are stored in `tinker/caches/embed_cache.sqlite` (via
`tinker.cache.TinkerCache`) keyed by (model, sha256(text)). Repeated calls
on the same substrate avoid re-embedding.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from tinker import llm as tinker_llm
from tinker.cache import TinkerCache
from tinker.substrate import Unit


def embed_texts(
    texts: list[str],
    *,
    cache: TinkerCache,
    model: str = tinker_llm.MODEL_EMBEDDER,
    batch_size: int = 32,
    progress: bool = True,
) -> list[list[float]]:
    """Embed a list of texts, using cache for hits and Ollama for misses.

    Returns vectors in input order.
    """
    out: list[list[float] | None] = [None] * len(texts)
    pending_idx: list[int] = []
    pending_text: list[str] = []

    for i, t in enumerate(texts):
        hit = cache.get_embedding(model, t)
        if hit is not None:
            out[i] = hit
        else:
            pending_idx.append(i)
            pending_text.append(t)

    if not pending_text:
        if progress:
            print(f"  cache hit on all {len(texts)} texts")
        return [v for v in out if v is not None]  # type: ignore[misc]

    if progress:
        print(
            f"  cache: {len(texts) - len(pending_text)} hits, "
            f"{len(pending_text)} misses; embedding via {model}"
        )

    done = 0
    for chunk_start in range(0, len(pending_text), batch_size):
        chunk = pending_text[chunk_start : chunk_start + batch_size]
        t0 = time.perf_counter()
        vecs = tinker_llm.embed(chunk)
        elapsed = time.perf_counter() - t0
        for offset, vec in enumerate(vecs):
            idx_in_pending = chunk_start + offset
            out_index = pending_idx[idx_in_pending]
            out[out_index] = vec
            cache.put_embedding(model, pending_text[idx_in_pending], vec)
        done += len(chunk)
        if progress:
            rate = len(chunk) / max(elapsed, 1e-6)
            print(
                f"  embedded {done}/{len(pending_text)} "
                f"({rate:.1f}/s, {elapsed:.2f}s for batch)"
            )

    return [v for v in out if v is not None]  # type: ignore[misc]


def embed_corpus(
    units: list[Unit],
    out_dir: Path,
    *,
    cache: TinkerCache,
    model: str = tinker_llm.MODEL_EMBEDDER,
    batch_size: int = 32,
    progress: bool = True,
) -> tuple[list[str], np.ndarray]:
    """Embed corpus units and write the artifact pair to *out_dir*.

    Returns the (ordered_unit_ids, embedding_matrix) tuple. The numpy
    array is float32 of shape [N, dim] and is also persisted to
    `<out_dir>/corpus.npy`. The index sidecar at
    `<out_dir>/corpus_index.json` records the model, ids, and dimension.
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ids = [u.id for u in units]
    texts = [u.text for u in units]

    if progress:
        print(f"Embedding {len(texts)} units with {model}...")
    t0 = time.perf_counter()
    vecs = embed_texts(
        texts, cache=cache, model=model, batch_size=batch_size, progress=progress
    )
    elapsed = time.perf_counter() - t0

    arr = np.asarray(vecs, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[0] != len(texts):
        raise RuntimeError(
            f"unexpected embed shape {arr.shape} for {len(texts)} texts"
        )
    dim = int(arr.shape[1])

    npy_path = out_dir / "corpus.npy"
    np.save(npy_path, arr)

    index_path = out_dir / "corpus_index.json"
    index_path.write_text(
        json.dumps(
            {
                "model": model,
                "dim": dim,
                "count": len(ids),
                "unit_ids": ids,
                "unit_id_to_index": {uid: i for i, uid in enumerate(ids)},
            },
            indent=2,
        )
    )
    if progress:
        print(
            f"Wrote {len(ids)} embeddings ({dim}-dim) "
            f"to {npy_path} in {elapsed:.1f}s"
        )
    return ids, arr


def load_corpus_embeddings(
    out_dir: Path,
) -> tuple[list[str], dict[str, int], np.ndarray, dict]:
    """Read the corpus_index.json + corpus.npy pair written by embed_corpus.

    Returns (ordered_ids, unit_id_to_index, matrix, index_metadata).
    """
    out_dir = Path(out_dir).resolve()
    index_meta = json.loads((out_dir / "corpus_index.json").read_text())
    arr = np.load(out_dir / "corpus.npy")
    return (
        list(index_meta["unit_ids"]),
        dict(index_meta["unit_id_to_index"]),
        arr,
        index_meta,
    )
