"""Evaluation orchestration helpers extracted from run_experiment."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from retrieval_lab.crossref_sidecar import build_crossref_sidecar
from retrieval_lab.pairing_edges import build_dependency_pairing_edges


def prepare_expansion_indices(
    *,
    corpus: List[Dict[str, Any]],
    canonical_corpus: List[Dict[str, Any]],
    crossref_enabled: bool,
    pairing_enabled: bool,
) -> Tuple[Dict[str, List[str]], Dict[str, List[tuple]]]:
    crossref_sidecar: Dict[str, List[str]] = {}
    if crossref_enabled:
        crossref_sidecar = build_crossref_sidecar(corpus)

    pairing_edges: Dict[str, List[tuple]] = {}
    if pairing_enabled:
        pairing_edges = build_dependency_pairing_edges(canonical_corpus)
    return crossref_sidecar, pairing_edges
