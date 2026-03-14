"""Embed-only orchestration helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable

import numpy as np

from retrieval_lab.embedding_enrichment import build_embedding_text
from retrieval_lab.orchestration.config_access import read_run_flags
from retrieval_lab.store import save_cached_embeddings, save_embedding_run_metadata, substrate_run_id
from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_enrichments_into_corpus,
    merge_units_by_heading,
)


def run_embed_only(
    *,
    config: Any,
    load_model_fn: Any,
    encode_texts_fn: Any,
    model_registry: Dict[str, Any],
    trust_remote_models: Iterable[str],
    output_dir: Any,
) -> str:
    """Embed substrate and persist vectors. Logic mirrors run_experiment legacy path."""
    flags = read_run_flags(config)
    corpus = load_evidence_units(config.substrate_path, config.document_id)
    if not corpus:
        raise ValueError("Corpus is empty; no EvidenceUnits found.")
    if flags.min_chars is not None:
        corpus = fold_under_threshold_into_adjacent(corpus, flags.min_chars)
    if flags.merge_chunks:
        corpus = merge_units_by_heading(corpus, max_chars=flags.merge_max_chars)
    corpus = merge_enrichments_into_corpus(corpus, config.substrate_path)

    corpus_ids = [c["id"] for c in corpus]
    embed_profile = getattr(config, "embedding_enrichment_profile", None) or ""
    corpus_texts = [build_embedding_text(c, embed_profile or None) for c in corpus]
    substrate_version = config.substrate_version
    if embed_profile and str(embed_profile).strip().lower() not in ("", "baseline"):
        substrate_version = (substrate_version or "") + "_embed_" + str(embed_profile).strip()
    run_id = substrate_run_id(config.document_id, corpus_ids, substrate_version)

    for model_id in config.models:
        if model_id not in model_registry:
            raise ValueError(
                f"Model {model_id!r} not in active MODEL_REGISTRY; add it before embedding."
            )
        model_name = model_registry[model_id].model_name
        trust_remote = config.trust_remote_code or (model_id in trust_remote_models)
        model = load_model_fn(model_name, trust_remote_code=trust_remote)
        corpus_embeddings = encode_texts_fn(
            model,
            corpus_texts,
            batch_size=config.batch_size,
            model_id=model_id,
            text_role="passage",
            recipe_mode=getattr(config, "recipe_mode", "standardized"),
            pooling=getattr(config, "embedding_pooling", "mean"),
            normalize=bool(getattr(config, "embedding_normalize", True)),
            max_seq_len=getattr(config, "embedding_max_seq_len", None),
            query_prefix=str(getattr(config, "embedding_query_prefix", "")),
            passage_prefix=str(getattr(config, "embedding_passage_prefix", "")),
            fail_on_missing_source=bool(getattr(config, "recipe_fail_on_missing_source", True)),
        )
        records = [
            {"run_id": run_id, "model_id": model_id, "chunk_id": uid, "embedding": corpus_embeddings[i].tolist()}
            for i, uid in enumerate(corpus_ids)
        ]
        save_cached_embeddings(run_id, model_id, records, config.mongo_uri, clear_existing=True)
        save_embedding_run_metadata(run_id, model_id, len(corpus_ids), config.mongo_uri)
        np.save(output_dir / "embeddings" / f"{model_id}_corpus.npy", corpus_embeddings)
    return run_id
