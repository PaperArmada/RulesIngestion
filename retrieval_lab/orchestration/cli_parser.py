"""CLI parser construction for retrieval_lab.run_experiment."""

from __future__ import annotations

import argparse

from retrieval_lab.config import (
    CC_BM25_NORMALIZATION_DEFAULT,
    CC_LAMBDA_DEFAULT,
    HYBRID_FUSION_METHOD_DEFAULT,
)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieval Lab: embed substrate (once) and/or run retrieval evals over EvidenceUnits.",
    )
    parser.add_argument("--config", type=str, help="Path to experiment YAML config")
    parser.add_argument("--experiment-name", type=str, default=None, help="Override experiment_name from config")
    parser.add_argument("--substrate", type=str, help="Substrate path (overrides config)")
    parser.add_argument("--document-id", type=str, default="DnD_PHB_5.5", help="Document ID for substrate")
    parser.add_argument(
        "--substrate-version",
        type=str,
        default=None,
        help="Substrate version (e.g. v1, 20260208). Run_id becomes retrieval_lab_{document_id}_{version}. Re-embed only when extraction changes.",
    )
    parser.add_argument(
        "--embedding-enrichment-profile",
        type=str,
        default=None,
        help="Embedding text profile: baseline (text only) | path | type | table_title | topic_tags | co_retrieval_hints | page | full. Run_id gets _embed_{profile} suffix.",
    )
    parser.add_argument(
        "--recipe-mode",
        type=str,
        choices=["standardized", "recommended"],
        default=None,
        help="Embedding recipe mode for bakeoff runs.",
    )
    parser.add_argument(
        "--embedding-pooling",
        type=str,
        choices=["mean", "model_default"],
        default=None,
        help="Embedding pooling behavior used by active backend.",
    )
    parser.add_argument(
        "--embedding-normalize",
        action="store_true",
        dest="embedding_normalize",
        help="Enable L2 normalization for embeddings.",
    )
    parser.add_argument(
        "--no-embedding-normalize",
        action="store_false",
        dest="embedding_normalize",
        help="Disable L2 normalization for embeddings.",
    )
    parser.set_defaults(embedding_normalize=None)
    parser.add_argument(
        "--embedding-max-seq-len",
        type=int,
        default=None,
        help="Max sequence length for embedding inference.",
    )
    parser.add_argument(
        "--embedding-similarity-metric",
        type=str,
        choices=["cosine", "dot"],
        default=None,
        help="Similarity interpretation metadata for bakeoff provenance.",
    )
    parser.add_argument(
        "--embedding-query-prefix",
        type=str,
        default=None,
        help="Optional query prefix for embedding text formatting.",
    )
    parser.add_argument(
        "--embedding-passage-prefix",
        type=str,
        default=None,
        help="Optional passage prefix for embedding text formatting.",
    )
    parser.add_argument(
        "--recipe-fail-on-missing-source",
        action="store_true",
        dest="recipe_fail_on_missing_source",
        help="Fail when recommended recipe source/revision metadata is missing.",
    )
    parser.add_argument(
        "--no-recipe-fail-on-missing-source",
        action="store_false",
        dest="recipe_fail_on_missing_source",
        help="Allow recommended recipe with incomplete source metadata.",
    )
    parser.set_defaults(recipe_fail_on_missing_source=None)
    parser.add_argument("--batches", type=str, nargs="+", help="Query batch JSON paths (overrides config)")
    parser.add_argument("--models", type=str, nargs="+", help="Model IDs (overrides config)")
    parser.add_argument("--top-k", type=str, default=None, help="Comma-separated top-k values (overrides config)")
    parser.add_argument("--rrf-k", type=int, default=None, help="Override RRF fusion constant k")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed for reproducible harness runs")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Embedding batch size override (default comes from config, typically 16).",
    )
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
    parser.add_argument("--parent-fetch-depth", type=int, default=None, help="R2: Parent-fetch structural_path depth")
    parser.add_argument("--parent-fetch-cap", type=int, default=None, help="R2: Parent-fetch char cap per scope")
    parser.add_argument("--parent-fetch", action="store_true", dest="parent_fetch_enabled", help="R2: Enable parent-fetch enrichment")
    parser.add_argument("--reranker", type=str, default=None, help="R11: Cross-encoder model name (e.g. cross-encoder/ms-marco-MiniLM-L6-v2). Re-rank hybrid top-50 to top-10.")
    parser.add_argument("--clause-family-projection", action="store_true", help="A1: enable retrieval-only clause-family projection substrate")
    parser.add_argument("--crossref-sidecar-expand", action="store_true", help="B1: enable deterministic sidecar expansion")
    parser.add_argument("--crossref-expand-top-k", type=int, default=None, help="B1: consider top-k anchors for sidecar expansion")
    parser.add_argument("--crossref-expand-per-hit", type=int, default=None, help="B1: max expansions per anchor")
    parser.add_argument("--crossref-expand-total-cap", type=int, default=None, help="B1/H7: max expansions added per query")
    parser.add_argument("--a-prime-generate-minimal", action="store_true", help="H7: synthesize minimal deterministic A′ hints in-memory when missing")
    parser.add_argument("--dual-list-fusion", action="store_true", help="A1.2: retrieve from Index_U + Index_F (clause-family), fuse with quota interleave")
    parser.add_argument("--dual-list-ku", type=int, default=None, help="A1.2: top-K from unit index")
    parser.add_argument("--dual-list-kf", type=int, default=None, help="A1.2: top-K from family index")
    parser.add_argument("--dual-list-kfinal", type=int, default=None, help="A1.2: final candidate cap")
    parser.add_argument("--dual-list-qu", type=int, default=None, help="A1.2: quota unit hits first")
    parser.add_argument("--dependency-pairing-expand", action="store_true", help="B1: expand with delta→base and exception→base pairing edges")
    parser.add_argument("--dependency-pairing-emax", type=int, default=None, help="B1: max paired adds per query")
    parser.add_argument("--retrieval-mode", type=str, choices=["dense", "hybrid", "hybrid+rerank", "bm25"], default=None, help="Override retrieval mode from config")
    parser.add_argument("--bm25-budget", type=int, default=None, help="BM25 candidate list depth (Ks) for hybrid retrieval")
    parser.add_argument("--dense-budget", type=int, default=None, help="Dense candidate list depth (Ku) for hybrid retrieval")
    parser.add_argument(
        "--hybrid-fusion-method",
        type=str,
        choices=["rrf", "cc"],
        default=None,
        help=f"Hybrid fusion override. Validated default is {HYBRID_FUSION_METHOD_DEFAULT}; rrf is comparison-only.",
    )
    parser.add_argument(
        "--cc-lambda",
        type=float,
        default=None,
        help=f"CC fusion override for dense weight. Validated default is {CC_LAMBDA_DEFAULT}.",
    )
    parser.add_argument(
        "--cc-bm25-normalization",
        type=str,
        choices=["atan", "minmax"],
        default=None,
        help=f"CC BM25 normalization override. Validated default is {CC_BM25_NORMALIZATION_DEFAULT}.",
    )
    parser.add_argument("--bm25-enrichment-profile", type=str, default=None, help="BM25-specific enrichment profile (decoupled from dense embedding text)")
    parser.add_argument("--bm25-tokenizer-mode", type=str, choices=["basic", "hyphenated"], default=None, help="BM25 tokenizer mode")
    parser.add_argument("--bm25-k1", type=float, default=None, help="BM25 k1 parameter")
    parser.add_argument("--bm25-b", type=float, default=None, help="BM25 b parameter")
    parser.add_argument("--bm25-query-mode", type=str, choices=["question_only", "question_plus_summary", "weighted"], default=None, help="BM25 query text construction mode")
    parser.add_argument("--bm25-query-weight-question", type=int, default=None, help="BM25 weighted mode: question multiplier")
    parser.add_argument("--bm25-query-weight-summary", type=int, default=None, help="BM25 weighted mode: expected_answer_summary multiplier")
    parser.add_argument("--two-stage-retrieval", action="store_true", help="Enable Stage1 admission + Stage2 rerank flow (dense/hybrid modes)")
    parser.add_argument("--stage1-admission-k", type=int, default=None, help="Stage1 candidate pool size before Stage2 rerank")
    parser.add_argument("--stage1-query-mode", type=str, choices=["question_only", "question_plus_summary", "weighted"], default=None, help="Stage1 query representation mode")
    parser.add_argument("--stage2-query-mode", type=str, choices=["question_only", "question_plus_summary", "weighted"], default=None, help="Stage2 rerank query representation mode")
    parser.add_argument("--stage2-rerank-method", type=str, choices=["dense", "cross_encoder"], default=None, help="Stage2 rerank scoring method")
    parser.add_argument("--merge-chunks", action="store_true", dest="merge_chunks", help="Enable heading-based chunk merge before embedding/retrieval")
    parser.add_argument("--no-merge-chunks", action="store_false", dest="merge_chunks")
    parser.set_defaults(merge_chunks=None)
    parser.add_argument("--merge-max-chars", type=int, default=None, help="Max characters per merged chunk when merge is enabled")
    parser.add_argument("--min-chars", type=int, default=None, help="Fold units shorter than this threshold into adjacent units before heading merge")
    parser.add_argument("--raw-first-merge-rerank", action="store_true", help="Run hybrid retrieval/rerank on raw units, then promote to merged chunks and rerank merged candidates")
    parser.add_argument("--raw-stage1-admission-k", type=int, default=None, help="Raw top-k candidates admitted before merged promotion")
    parser.add_argument("--raw-merge-rerank-top-k", type=int, default=None, help="Final top-k kept after merged rerank")
    parser.add_argument("--raw-merge-score-floor", action="store_true", dest="raw_merge_score_floor", help="Floor merged score by normalized best raw score")
    parser.add_argument("--no-raw-merge-score-floor", action="store_false", dest="raw_merge_score_floor")
    parser.set_defaults(raw_merge_score_floor=None)
    parser.add_argument("--raw-merge-rank-floor", action="store_true", dest="raw_merge_rank_floor", help="Apply deadline-style rank floor using best raw rank")
    parser.add_argument("--no-raw-merge-rank-floor", action="store_false", dest="raw_merge_rank_floor")
    parser.set_defaults(raw_merge_rank_floor=None)
    parser.add_argument("--raw-merge-coverage-bonus", type=float, default=None, help="Optional bonus for merged candidates covering more admitted raw sources")
    parser.add_argument("--baseline-metrics", type=str, default=None, help="Optional baseline metrics.json path for failure-bucket delta reporting")
    parser.add_argument("--answer-eval", action="store_true", help="Run answer-generation evaluation pass (OpenAI; writes answer_eval.json)")
    parser.add_argument("--answer-model", type=str, default=None, help="Answer-eval LLM model id (e.g. gpt-4o-mini)")
    parser.add_argument("--answer-top-k", type=int, default=None, help="Answer-eval uses top-k retrieved EvidenceUnits (default: max(top_k))")
    parser.add_argument("--answer-max-queries", type=int, default=None, help="Answer-eval max queries (deterministic: sorted by query_id)")
    parser.add_argument("--answer-max-chars-per-unit", type=int, default=None, help="Answer-eval evidence truncation per unit (chars)")
    parser.add_argument("--answer-eval-models", type=str, default=None, help="Comma-separated retrieval model IDs to evaluate (default: first model only)")
    parser.add_argument("--auto-gold-review", action="store_true", help="Run LLM review over top-k retrieval candidates and apply benchmark gold")
    parser.add_argument("--auto-gold-model", type=str, default=None, help="Auto-gold reviewer LLM model id (e.g. gpt-4o-mini)")
    parser.add_argument("--auto-gold-retrieval-model", type=str, default=None, help="Retrieval model whose ranked candidates should drive gold review (default: first available)")
    parser.add_argument("--auto-gold-top-k", type=int, default=None, help="How many retrieved chunks per query to review and persist in the auto-gold artifact")
    parser.add_argument("--auto-gold-max-queries", type=int, default=None, help="Limit auto-gold review to the first N queries (0 means all)")
    parser.add_argument("--auto-gold-max-chars-per-chunk", type=int, default=None, help="Truncate candidate text to this many chars for LLM review")
    parser.add_argument("--auto-gold-challenge-sample", type=int, default=None, help="Extra hard-but-successful queries to include in the human review queue")
    parser.add_argument("--auto-gold-max-required-overlap", type=int, default=None, help="Flag queries when the same required chunk appears in more than this many queries")
    parser.add_argument(
        "--allow-benchmark-contract-mismatch",
        action="store_true",
        help="Noisy override: continue even when a benchmark contract is missing, mismatched, or points at dead corpus ids.",
    )
    parser.add_argument("--enhancement-mode", type=str, choices=["none", "dict", "llm", "llm+dict", "decompose"], default=None, help="Query enhancement mode (overrides config)")
    parser.add_argument("--enhancement-profile", type=str, default=None, help="Path to QueryExpansionProfile JSON (overrides config)")
    parser.add_argument(
        "--enhancement-fusion-mode",
        type=str,
        choices=["only_add", "rrf", "union_rerank"],
        default=None,
        help="Query enhancement fusion policy (overrides config). Default for QE runs is only_add.",
    )
    parser.add_argument(
        "--onlyadd-prefix-lock-n",
        type=int,
        default=None,
        help="only_add: hard-lock this many baseline items at the front (diagnostic knob).",
    )
    parser.add_argument(
        "--onlyadd-tail-rerank",
        type=str,
        choices=["none", "lexical", "cross_encoder", "cascade"],
        default=None,
        help="only_add: rerank tail segment (positions prefix_lock_n+1..admission_cutoff). Diagnostic knob.",
    )
    parser.add_argument(
        "--onlyadd-tail-rerank-window",
        type=int,
        default=None,
        help="only_add: rerank window size (R). Only rerank positions prefix_lock_n+1..prefix_lock_n+R.",
    )
    return parser
