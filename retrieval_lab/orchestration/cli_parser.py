"""CLI parser construction for retrieval_lab.run_experiment."""

from __future__ import annotations

import argparse


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieval Lab: embed substrate (once) and/or run retrieval evals over EvidenceUnits.",
    )
    parser.add_argument("--config", type=str, help="Path to experiment YAML config")
    parser.add_argument("--substrate", type=str, help="Substrate path (overrides config)")
    parser.add_argument("--document-id", type=str, default="DnD_PHB_5.5", help="Document ID for substrate")
    parser.add_argument(
        "--substrate-version",
        type=str,
        default=None,
        help="Substrate version (e.g. v1, 20260208). Run_id becomes retrieval_lab_{document_id}_{version}. Re-embed only when extraction changes.",
    )
    parser.add_argument("--batches", type=str, nargs="+", help="Query batch JSON paths (overrides config)")
    parser.add_argument("--models", type=str, nargs="+", help="Model IDs (overrides config)")
    parser.add_argument("--top-k", type=str, default="1,3,5,10,20", help="Comma-separated top-k values")
    parser.add_argument("--output", type=str, help="Output directory (overrides config)")
    parser.add_argument("--reuse-embeddings", action="store_true", default=True, help="Use MongoDB cache for embeddings")
    parser.add_argument("--no-reuse-embeddings", action="store_false", dest="reuse_embeddings")
    parser.add_argument("--mongo-uri", type=str, default=None, help="MongoDB URI (default: MONGODB_URI env)")
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help="Only embed the substrate (all models); save to MongoDB. Do not run queries or report. Re-run when extraction/substrate changes.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Eval-only: use this embedding run_id (no embedding). Requires embeddings already in MongoDB for this run_id and all --models.",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Pass trust_remote_code=True when loading models (required for nomic-embed-text-v2, bge-m3, gte-multilingual-base).",
    )
    parser.add_argument("--parent-fetch-depth", type=int, default=1, help="R2: Parent-fetch structural_path depth")
    parser.add_argument("--parent-fetch-cap", type=int, default=2000, help="R2: Parent-fetch char cap per scope")
    parser.add_argument("--parent-fetch", action="store_true", dest="parent_fetch_enabled", help="R2: Enable parent-fetch enrichment")
    parser.add_argument("--reranker", type=str, default=None, help="R11: Cross-encoder model name (e.g. cross-encoder/ms-marco-MiniLM-L6-v2). Re-rank hybrid top-50 to top-10.")
    parser.add_argument("--clause-family-projection", action="store_true", help="A1: enable retrieval-only clause-family projection substrate")
    parser.add_argument("--crossref-sidecar-expand", action="store_true", help="B1: enable deterministic sidecar expansion")
    parser.add_argument("--crossref-expand-top-k", type=int, default=10, help="B1: consider top-k anchors for sidecar expansion")
    parser.add_argument("--crossref-expand-per-hit", type=int, default=2, help="B1: max expansions per anchor")
    parser.add_argument("--crossref-expand-total-cap", type=int, default=20, help="B1/H7: max expansions added per query")
    parser.add_argument("--a-prime-generate-minimal", action="store_true", help="H7: synthesize minimal deterministic A′ hints in-memory when missing")
    parser.add_argument("--dual-list-fusion", action="store_true", help="A1.2: retrieve from Index_U + Index_F (clause-family), fuse with quota interleave")
    parser.add_argument("--dual-list-ku", type=int, default=12, help="A1.2: top-K from unit index")
    parser.add_argument("--dual-list-kf", type=int, default=12, help="A1.2: top-K from family index")
    parser.add_argument("--dual-list-kfinal", type=int, default=10, help="A1.2: final candidate cap")
    parser.add_argument("--dual-list-qu", type=int, default=6, help="A1.2: quota unit hits first")
    parser.add_argument("--dependency-pairing-expand", action="store_true", help="B1: expand with delta→base and exception→base pairing edges")
    parser.add_argument("--dependency-pairing-emax", type=int, default=6, help="B1: max paired adds per query")
    return parser
