"""Shared evaluation utilities for RulesIngestion and RulesLawyer."""

from evaluation.benchmark import BenchmarkStoreOps, run_embedding_benchmark
from evaluation.model_registry import EmbeddingModelSpec, MODEL_REGISTRY

__all__ = [
    "BenchmarkStoreOps",
    "EmbeddingModelSpec",
    "MODEL_REGISTRY",
    "run_embedding_benchmark",
]
