"""CLI override helpers for retrieval_lab.run_experiment."""

from __future__ import annotations

from typing import Any


def apply_cli_overrides(config: Any, args: Any) -> None:
    if args.substrate:
        config.substrate_path = args.substrate
    if args.batches:
        config.query_batches = args.batches
    if args.models:
        config.models = args.models
    if args.top_k:
        config.top_k = [int(x) for x in args.top_k.split(",") if x.strip()]
    if args.output:
        config.output_dir = args.output
    if args.mongo_uri is not None:
        config.mongo_uri = args.mongo_uri
    if args.substrate_version is not None:
        config.substrate_version = args.substrate_version
    if args.trust_remote_code:
        config.trust_remote_code = True
    if hasattr(args, "parent_fetch_depth"):
        config.parent_fetch_depth = args.parent_fetch_depth
    if hasattr(args, "parent_fetch_cap"):
        config.parent_fetch_cap = args.parent_fetch_cap
    if hasattr(args, "parent_fetch_enabled") and args.parent_fetch_enabled:
        config.parent_fetch_enabled = True
    if hasattr(args, "reranker") and args.reranker:
        config.reranker = args.reranker
    if getattr(args, "clause_family_projection", False):
        config.clause_family_projection = True
    if getattr(args, "crossref_sidecar_expand", False):
        config.crossref_sidecar_expand = True
    if hasattr(args, "crossref_expand_top_k"):
        config.crossref_expand_top_k = args.crossref_expand_top_k
    if hasattr(args, "crossref_expand_per_hit"):
        config.crossref_expand_per_hit = args.crossref_expand_per_hit
    if hasattr(args, "crossref_expand_total_cap"):
        config.crossref_expand_total_cap = args.crossref_expand_total_cap
    if getattr(args, "a_prime_generate_minimal", False):
        config.a_prime_generate_minimal = True
    if getattr(args, "dual_list_fusion", False):
        config.dual_list_fusion = True
    if hasattr(args, "dual_list_ku"):
        config.dual_list_ku = args.dual_list_ku
    if hasattr(args, "dual_list_kf"):
        config.dual_list_kf = args.dual_list_kf
    if hasattr(args, "dual_list_kfinal"):
        config.dual_list_kfinal = args.dual_list_kfinal
    if hasattr(args, "dual_list_qu"):
        config.dual_list_qu = args.dual_list_qu
    if getattr(args, "dependency_pairing_expand", False):
        config.dependency_pairing_expand = True
    if hasattr(args, "dependency_pairing_emax"):
        config.dependency_pairing_emax = args.dependency_pairing_emax
