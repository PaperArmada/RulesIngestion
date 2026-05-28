"""Orchestrator: compose glossary + clusters + metadata + crossref into one
`corpus_self_portrait.json` document.

The output shape is what the classifier / routing layer expects to receive
as context. Schema:

  {
    "corpus_id": str,
    "document_id": str,
    "generated_at": ISO8601,
    "substrate_summary": { unit_count, page_count, recipe },
    "glossary":   { terms: [...], acronyms: [...], stats: {...} },
    "clusters":   { chosen_k, inertias, clusters: [...] },
    "metadata_index": { by_unit, summary, stats },
    "crossref":   { edges, stats },
  }
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

from tinker.cache import TinkerCache
from tinker.introspect.clusters import build_clusters
from tinker.introspect.crossref import build_crossref_graph
from tinker.introspect.glossary import build_glossary
from tinker.introspect.metadata import build_metadata_index
from tinker.substrate import Unit, load_corpus


def _log(msg: str) -> None:
    """Stdout logger that flushes immediately for visible progress."""
    print(msg, flush=True)


def build_self_portrait(
    substrate_dir: str | Path,
    document_id: str,
    *,
    out_path: Path | None = None,
    cache_path: Path | None = None,
    corpus_id: str | None = None,
    use_llm: bool = True,
    llm_glossary_max_units: int = 50,
    cluster_k_range: tuple[int, int] = (6, 16),
    recipe_min_chars: int = 100,
    recipe_merge_chunks: bool = True,
    recipe_merge_max_chars: int = 2000,
    progress: bool = True,
) -> dict[str, Any]:
    """End-to-end build. Writes `corpus_self_portrait.json` to *out_path*.

    If out_path is None, derives it from `out/tinker/<corpus_id>/`.
    """
    corpus_id = corpus_id or document_id
    out_path = (
        Path(out_path)
        if out_path is not None
        else Path("out/tinker") / corpus_id / "corpus_self_portrait.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cache_path = (
        Path(cache_path)
        if cache_path is not None
        else out_path.parent / "caches" / "llm_cache.sqlite"
    )
    cache = TinkerCache(cache_path)

    log = _log if progress else (lambda _msg: None)

    log(f"[1/5] loading substrate from {substrate_dir} (document={document_id})")
    units = load_corpus(
        substrate_dir,
        document_id,
        min_chars=recipe_min_chars,
        merge_chunks=recipe_merge_chunks,
        merge_max_chars=recipe_merge_max_chars,
    )
    pages = sorted({u.page for u in units if u.page >= 0})

    substrate_summary: dict[str, Any] = {
        "unit_count": len(units),
        "page_count": len(pages),
        "recipe": {
            "min_chars": recipe_min_chars,
            "merge_chunks": recipe_merge_chunks,
            "merge_max_chars": recipe_merge_max_chars,
        },
    }
    log(f"      -> {len(units)} units, {len(pages)} pages")

    log("[2/5] glossary (regex" + (" + LLM" if use_llm else "") + ")")
    glossary = build_glossary(
        units, cache, use_llm=use_llm, llm_max_units=llm_glossary_max_units
    )
    log(f"      -> {glossary['stats']}")

    log("[3/5] structural clusters (KMeans + label_cluster)")
    clusters = build_clusters(
        units, cache, k_range=cluster_k_range, use_llm_labels=use_llm
    )
    log(
        f"      -> chosen_k={clusters['chosen_k']}, "
        f"{len(clusters['clusters'])} clusters"
    )

    log("[4/5] typed metadata index (regex)")
    metadata = build_metadata_index(units)
    log(f"      -> {metadata['stats']}")

    log("[5/5] cross-reference graph")
    crossref = build_crossref_graph(units, glossary["terms"])
    log(f"      -> {crossref['stats']}")

    portrait: dict[str, Any] = {
        "corpus_id": corpus_id,
        "document_id": document_id,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "substrate_summary": substrate_summary,
        "glossary": glossary,
        "clusters": clusters,
        "metadata_index": metadata,
        "crossref": crossref,
    }
    out_path.write_text(json.dumps(portrait, indent=2, ensure_ascii=False))
    if progress:
        size_kb = out_path.stat().st_size / 1024
        log(f"Wrote {out_path} ({size_kb:.1f} KB)")
    return portrait
