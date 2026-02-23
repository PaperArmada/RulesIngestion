"""Experiment configuration: YAML loading, validation, model resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Optional YAML: allow running without pyyaml for tests that only need defaults
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


@dataclass
class ParentFetchConfig:
    """R2: Configuration for parent-fetch enrichment of retrieval results."""

    depth: int = 1
    char_cap: int = 2000
    enabled: bool = False


@dataclass
class RetrievalPolicy:
    """R7: Per-corpus retrieval policy (mode, fusion, reranker, parent-fetch)."""

    corpus_id: str
    mode: str = "hybrid"
    fusion_k: int = 60  # RRF constant k
    parent_fetch_config: Optional[ParentFetchConfig] = None
    reranker: Optional[str] = None


@dataclass
class CrossrefConfig:
    enabled: bool = False
    expand_top_k: int = 10
    expand_per_hit: int = 2
    expand_total_cap: int = 20


@dataclass
class DualListConfig:
    enabled: bool = False
    ku: int = 12
    kf: int = 12
    kfinal: int = 10
    qu: int = 6
    family_window: int = 3
    family_max_units: int = 6
    family_direction: str = "symmetric"


@dataclass
class PairingConfig:
    enabled: bool = False
    emax: int = 6


@dataclass
class OnlyAddFusionConfig:
    """Only-add fusion policy for query enhancement multi-query runs.

    Goal: expansions can increase candidate coverage without evicting (or demoting)
    the locked-in baseline prefix.
    """

    # Safety invariant: should be >= max(top_k) for your evaluation.
    baseline_keep_n: int = 20
    variant_k_per_query: int = 20
    # Admission pool size for only-add fusion. Keep evaluation top-k unchanged; only the pool grows.
    admission_cutoff: int = 50
    # Number of baseline items to hard-lock at the front of the final ranking.
    # Diagnostic knob: set < max(top_k) to allow tail rerank to move new candidates into top-20
    # while still keeping the very top stable (e.g. lock top-10, evaluate top-20).
    prefix_lock_n: int = 20
    # Optional diagnostic: rerank the tail segment (positions prefix_lock_n+1..admission_cutoff).
    # none | lexical | cross_encoder | cascade (lexical then cross_encoder if still missing @eval_k)
    tail_rerank: str = "none"
    # Limit rerank compute: only rerank the first R tail items after the lock.
    tail_rerank_window: int = 50
    # If set, appended candidates are assigned scores below the baseline band.
    append_score_band: float = 1e-6
    # Future: rerank union with baseline locks. Not enabled by default.
    rerank_union: bool = False


@dataclass
class QueryEnhancementConfig:
    enabled: bool = False
    profile_path: str = ""
    mode: str = "none"  # none | dict | llm | llm+dict | decompose
    fusion_mode: str = "only_add"  # only_add | rrf | union_rerank
    only_add: OnlyAddFusionConfig = field(default_factory=OnlyAddFusionConfig)


@dataclass
class ExperimentConfig:
    """Configuration for a single retrieval lab experiment."""

    experiment_name: str
    substrate_path: str
    document_id: str
    query_batches: List[str]
    models: List[str]
    retrieval_mode: str = "dense"
    top_k: List[int] = field(default_factory=lambda: [1, 3, 5, 10, 20])
    output_dir: str = "out/retrieval_lab/experiments"
    mongo_uri: Optional[str] = None
    reuse_embeddings: bool = True
    # Substrate version: when set, run_id = retrieval_lab_{document_id}_{substrate_version}.
    # Re-embed only when extraction/substrate changes (bump version).
    substrate_version: Optional[str] = None
    # Pass trust_remote_code=True when loading models (nomic, bge-m3, gte-multilingual, etc.)
    trust_remote_code: bool = False
    # Gold grounding (corpus-wide semantic mode)
    gold_semantic_top_n: int = 5
    gold_jaccard_threshold: float = 0.15
    # Embedding batch size
    batch_size: int = 16
    # Optional seed for reproducibility in harness runs.
    seed: Optional[int] = None
    # Expand top-k with context then re-rank: append prev/next N chunks (document order), re-embed, re-rank.
    expand_context: bool = False
    expand_context_n: int = 1
    # Exclude units with len(text) < min_chars when loading substrate (reduces spell-header/metadata noise; requires re-embed).
    min_chars: Optional[int] = None
    # Post-hoc heading merge: merge consecutive units sharing the same structural_path.
    # Produces richer chunks (e.g. full spell entries) without changing Stage B extraction.
    # Requires re-embed when toggled (new substrate_version).
    merge_chunks: bool = False
    merge_max_chars: int = 2000
    # R7: RRF fusion constant k (default 60). Overridden by per-corpus policy if set.
    rrf_k: int = 60
    # BM25 tuning knobs.
    bm25_tokenizer_mode: str = "basic"  # basic | hyphenated
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    bm25_query_mode: str = "question_only"  # question_only | question_plus_summary | weighted
    bm25_query_weight_question: int = 1
    bm25_query_weight_summary: int = 1
    # Two-stage retrieval: Stage1 admission (expanded query), Stage2 rerank (strict query).
    two_stage_retrieval: bool = False
    stage1_admission_k: int = 100
    stage1_query_mode: str = "question_plus_summary"  # question_only | question_plus_summary | weighted
    stage2_query_mode: str = "question_only"  # question_only | question_plus_summary | weighted
    stage2_rerank_method: str = "dense"  # dense | cross_encoder
    # Raw-first merge-rerank policy:
    # 1) retrieve + rerank on unmerged units
    # 2) promote to merged candidates
    # 3) rerank merged candidates
    raw_first_merge_rerank: bool = False
    raw_stage1_admission_k: int = 100
    raw_merge_rerank_top_k: int = 20
    # If enabled, final merged score is floored by normalized best raw score.
    raw_merge_score_floor: bool = True
    # If enabled, enforce deadline-style rank floor using best raw rank as deadline.
    raw_merge_rank_floor: bool = True
    # Optional bonus applied to merged candidates that include more admitted raw sources.
    raw_merge_coverage_bonus: float = 0.0
    # R7: Per-corpus retrieval policies (corpus_id -> RetrievalPolicy). Optional.
    retrieval_policies: Optional[Dict[str, RetrievalPolicy]] = None
    # R9: Unit-type soft boost. Add delta to score when query-type heuristic matches unit_type (0=off).
    unit_type_boost: float = 0.0
    # R2: Parent-fetch enrichment (depth, char_cap, enabled).
    parent_fetch_depth: int = 1
    parent_fetch_cap: int = 2000
    parent_fetch_enabled: bool = False
    # R11: Cross-encoder reranker model name (optional). When set, re-rank hybrid top-50 to top-10.
    reranker: Optional[str] = None
    # R6: Expand candidate set using co_retrieval_hints (when hint.related_topic matches unit topic_tags).
    co_retrieval_expand: bool = False
    # Phase-0 metric contract and guardrails.
    guardrail_t1_mrr_drop_max: float = 0.02
    # A1: retrieval-only clause-family projection substrate.
    clause_family_projection: bool = False
    clause_family_window: int = 2
    clause_family_max_units: int = 6
    clause_family_direction: str = "symmetric"
    # B1: deterministic cross-reference sidecar expansion.
    crossref_sidecar_expand: bool = False
    crossref_expand_top_k: int = 10
    crossref_expand_per_hit: int = 2
    crossref_expand_total_cap: int = 20
    # H7: minimal deterministic A′ co-retrieval hint generation.
    a_prime_generate_minimal: bool = False
    # A1.2: dual-list fusion (Index_U canonical + Index_F clause-family).
    dual_list_fusion: bool = False
    dual_list_ku: int = 12
    dual_list_kf: int = 12
    dual_list_kfinal: int = 10
    dual_list_qu: int = 6
    dual_list_family_window: int = 3
    dual_list_family_max_units: int = 6
    dual_list_family_direction: str = "symmetric"
    # B1 replacement: dependency-oriented pairing edges (delta→base, exception→base).
    dependency_pairing_expand: bool = False
    dependency_pairing_emax: int = 6
    # Optional path to baseline metrics.json for report delta section.
    baseline_metrics_path: Optional[str] = None
    # Grouped options (wave-2 structure). Flat keys remain authoritative for backward compatibility.
    crossref: CrossrefConfig = field(default_factory=CrossrefConfig)
    dual_list: DualListConfig = field(default_factory=DualListConfig)
    pairing: PairingConfig = field(default_factory=PairingConfig)
    # Query enhancement (pre-retrieval expansion/decomposition).
    query_enhancement: QueryEnhancementConfig = field(default_factory=QueryEnhancementConfig)

    def get_policy(self, corpus_id: str) -> RetrievalPolicy:
        """Get retrieval policy for corpus. Falls back to default policy from config."""
        if self.retrieval_policies and corpus_id in self.retrieval_policies:
            return self.retrieval_policies[corpus_id]
        return RetrievalPolicy(corpus_id=corpus_id, mode=self.retrieval_mode, fusion_k=self.rrf_k)

    def resolve_paths(self, base_dir: Optional[Path] = None) -> None:
        """Resolve substrate_path and query_batches relative to base_dir (typically cwd)."""
        base = base_dir or Path.cwd()
        self.substrate_path = str((base / self.substrate_path).resolve())
        self.query_batches = [str((base / p).resolve()) for p in self.query_batches]
        self.output_dir = str((base / self.output_dir).resolve())
        if self.baseline_metrics_path:
            self.baseline_metrics_path = str((base / self.baseline_metrics_path).resolve())
        if self.query_enhancement.profile_path:
            self.query_enhancement.profile_path = str((base / self.query_enhancement.profile_path).resolve())

    def validate(self, embed_only: bool = False, eval_only: bool = False) -> None:
        """Raise ValueError if config is invalid. Use embed_only=True or eval_only=True for single-step validation."""
        if not self.substrate_path:
            raise ValueError("substrate_path is required")
        if not Path(self.substrate_path).exists():
            raise ValueError(f"substrate_path does not exist: {self.substrate_path}")
        if self.retrieval_mode not in ("dense", "hybrid", "hybrid+rerank", "bm25"):
            raise ValueError("retrieval_mode must be 'dense', 'hybrid', 'hybrid+rerank', or 'bm25'")
        if self.retrieval_mode == "hybrid+rerank" and not self.reranker:
            raise ValueError("retrieval_mode='hybrid+rerank' requires reranker")
        if self.retrieval_mode == "bm25" and self.dual_list_fusion:
            raise ValueError("dual_list_fusion is not supported in bm25 mode")
        if self.bm25_tokenizer_mode not in ("basic", "hyphenated"):
            raise ValueError("bm25_tokenizer_mode must be 'basic' or 'hyphenated'")
        if self.bm25_query_mode not in ("question_only", "question_plus_summary", "weighted"):
            raise ValueError("bm25_query_mode must be 'question_only', 'question_plus_summary', or 'weighted'")
        if self.bm25_k1 <= 0:
            raise ValueError("bm25_k1 must be > 0")
        if not (0 <= self.bm25_b <= 1):
            raise ValueError("bm25_b must be in [0, 1]")
        if self.bm25_query_weight_question < 1 or self.bm25_query_weight_summary < 1:
            raise ValueError("bm25 query weights must be >= 1")
        if self.stage1_query_mode not in ("question_only", "question_plus_summary", "weighted"):
            raise ValueError("stage1_query_mode must be 'question_only', 'question_plus_summary', or 'weighted'")
        if self.stage2_query_mode not in ("question_only", "question_plus_summary", "weighted"):
            raise ValueError("stage2_query_mode must be 'question_only', 'question_plus_summary', or 'weighted'")
        if self.stage2_rerank_method not in ("dense", "cross_encoder"):
            raise ValueError("stage2_rerank_method must be 'dense' or 'cross_encoder'")
        if self.stage1_admission_k < 1:
            raise ValueError("stage1_admission_k must be >= 1")
        if self.two_stage_retrieval and self.retrieval_mode == "bm25":
            raise ValueError("two_stage_retrieval is currently supported only for dense/hybrid retrieval modes")
        if self.two_stage_retrieval and self.stage2_rerank_method == "cross_encoder" and not self.reranker:
            raise ValueError("two_stage_retrieval with stage2_rerank_method='cross_encoder' requires reranker")
        if self.raw_first_merge_rerank:
            if self.retrieval_mode not in ("hybrid", "hybrid+rerank"):
                raise ValueError("raw_first_merge_rerank requires retrieval_mode='hybrid' or 'hybrid+rerank'")
            if self.merge_chunks:
                raise ValueError("raw_first_merge_rerank requires merge_chunks=false (raw substrate admission)")
            if self.raw_stage1_admission_k < 1:
                raise ValueError("raw_stage1_admission_k must be >= 1")
            if self.raw_merge_rerank_top_k < 1:
                raise ValueError("raw_merge_rerank_top_k must be >= 1")
            if self.raw_merge_rerank_top_k < max(self.top_k):
                raise ValueError("raw_merge_rerank_top_k must be >= max(top_k)")
            if self.raw_merge_coverage_bonus < 0:
                raise ValueError("raw_merge_coverage_bonus must be >= 0")
        if not self.models and self.retrieval_mode != "bm25":
            raise ValueError("models must be non-empty")
        if embed_only:
            return
        if eval_only:
            if not self.query_batches:
                raise ValueError("query_batches required for eval-only")
            for p in self.query_batches:
                if not Path(p).exists():
                    raise ValueError(f"query batch file not found: {p}")
            return
        if not self.experiment_name or not self.experiment_name.strip():
            raise ValueError("experiment_name is required")
        if not self.query_batches:
            raise ValueError("query_batches must be non-empty")
        for p in self.query_batches:
            if not Path(p).exists():
                raise ValueError(f"query batch file not found: {p}")
        if not self.top_k:
            raise ValueError("top_k must be non-empty")
        if self.dual_list_fusion and self.dual_list_kfinal < max(self.top_k):
            raise ValueError("dual_list_kfinal must be >= max(top_k) when dual_list_fusion is enabled")
        qe = self.query_enhancement
        if qe.enabled:
            if qe.mode not in ("none", "dict", "llm", "llm+dict", "decompose"):
                raise ValueError(f"query_enhancement.mode must be none/dict/llm/llm+dict/decompose, got {qe.mode!r}")
            if qe.fusion_mode not in ("only_add", "rrf", "union_rerank"):
                raise ValueError(
                    f"query_enhancement.fusion_mode must be only_add/rrf/union_rerank, got {qe.fusion_mode!r}"
                )
            if qe.mode != "none" and not qe.profile_path:
                raise ValueError("query_enhancement.profile_path required when mode != 'none'")
            if qe.profile_path and not Path(qe.profile_path).exists():
                raise ValueError(f"query_enhancement.profile_path not found: {qe.profile_path}")
            if qe.fusion_mode == "only_add":
                oa = qe.only_add
                if oa.baseline_keep_n < 1:
                    raise ValueError("query_enhancement.only_add.baseline_keep_n must be >= 1")
                if oa.variant_k_per_query < 1:
                    raise ValueError("query_enhancement.only_add.variant_k_per_query must be >= 1")
                if oa.admission_cutoff < 0:
                    raise ValueError("query_enhancement.only_add.admission_cutoff must be >= 0 (0 uses default cutoff)")
                if oa.append_score_band < 0:
                    raise ValueError("query_enhancement.only_add.append_score_band must be >= 0")
                if oa.prefix_lock_n < 1:
                    raise ValueError("query_enhancement.only_add.prefix_lock_n must be >= 1")
                if oa.prefix_lock_n > oa.baseline_keep_n:
                    raise ValueError("query_enhancement.only_add.prefix_lock_n must be <= baseline_keep_n")
                if oa.tail_rerank not in ("none", "lexical", "cross_encoder", "cascade"):
                    raise ValueError("query_enhancement.only_add.tail_rerank must be none/lexical/cross_encoder/cascade")
                if oa.tail_rerank_window < 1:
                    raise ValueError("query_enhancement.only_add.tail_rerank_window must be >= 1")
                eval_k = max(self.top_k) if self.top_k else 0
                if eval_k and oa.baseline_keep_n < eval_k:
                    raise ValueError(
                        f"query_enhancement.only_add.baseline_keep_n must be >= max(top_k)={eval_k} for only_add safety"
                    )
                if oa.admission_cutoff and oa.admission_cutoff < oa.baseline_keep_n:
                    raise ValueError("query_enhancement.only_add.admission_cutoff must be >= baseline_keep_n (or 0)")

    @classmethod
    def from_yaml(cls, path: Path, base_dir: Optional[Path] = None) -> "ExperimentConfig":
        """Load config from a YAML file."""
        if not _HAS_YAML:
            raise RuntimeError("PyYAML is required to load config from YAML. Install with: pip install pyyaml")
        resolved = path if path.is_absolute() else (base_dir or Path.cwd()) / path
        if not resolved.exists():
            raise FileNotFoundError(f"Config file not found: {resolved}")
        data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        return cls.from_dict(data or {}, base_dir=resolved.parent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Optional[Path] = None) -> "ExperimentConfig":
        """Build config from a dictionary (e.g. from YAML or CLI)."""
        top_k_raw = data.get("top_k", [1, 3, 5, 10, 20])
        if isinstance(top_k_raw, list):
            top_k = [int(x) for x in top_k_raw]
        else:
            top_k = [int(x) for x in str(top_k_raw).split(",") if x.strip()]
        crossref = _parse_crossref(data)
        dual_list = _parse_dual_list(data)
        pairing = _parse_pairing(data)
        query_enhancement = _parse_query_enhancement(data)
        cfg = cls(
            experiment_name=str(data.get("experiment_name", "unnamed_experiment")),
            substrate_path=str(data.get("substrate_path", "")),
            document_id=str(data.get("document_id", "")),
            query_batches=list(data.get("query_batches", [])),
            models=list(data.get("models", [])),
            retrieval_mode=str(data.get("retrieval_mode", "dense")),
            top_k=top_k,
            output_dir=str(data.get("output_dir", "out/retrieval_lab/experiments")),
            mongo_uri=data.get("mongo_uri"),
            reuse_embeddings=bool(data.get("reuse_embeddings", True)),
            substrate_version=data.get("substrate_version"),
            trust_remote_code=bool(data.get("trust_remote_code", False)),
            gold_semantic_top_n=int(data.get("gold_semantic_top_n", 5)),
            gold_jaccard_threshold=float(data.get("gold_jaccard_threshold", 0.15)),
            batch_size=int(data.get("batch_size", 16)),
            seed=int(data["seed"]) if data.get("seed") is not None else None,
            expand_context=bool(data.get("expand_context", False)),
            expand_context_n=int(data.get("expand_context_n", 1)),
            bm25_tokenizer_mode=str(data.get("bm25_tokenizer_mode", "basic")),
            bm25_k1=float(data.get("bm25_k1", 1.5)),
            bm25_b=float(data.get("bm25_b", 0.75)),
            bm25_query_mode=str(data.get("bm25_query_mode", "question_only")),
            bm25_query_weight_question=int(data.get("bm25_query_weight_question", 1)),
            bm25_query_weight_summary=int(data.get("bm25_query_weight_summary", 1)),
            two_stage_retrieval=bool(data.get("two_stage_retrieval", False)),
            stage1_admission_k=int(data.get("stage1_admission_k", 100)),
            stage1_query_mode=str(data.get("stage1_query_mode", "question_plus_summary")),
            stage2_query_mode=str(data.get("stage2_query_mode", "question_only")),
            stage2_rerank_method=str(data.get("stage2_rerank_method", "dense")),
            raw_first_merge_rerank=bool(data.get("raw_first_merge_rerank", False)),
            raw_stage1_admission_k=int(data.get("raw_stage1_admission_k", 100)),
            raw_merge_rerank_top_k=int(data.get("raw_merge_rerank_top_k", 20)),
            raw_merge_score_floor=bool(data.get("raw_merge_score_floor", True)),
            raw_merge_rank_floor=bool(data.get("raw_merge_rank_floor", True)),
            raw_merge_coverage_bonus=float(data.get("raw_merge_coverage_bonus", 0.0)),
            min_chars=int(data["min_chars"]) if data.get("min_chars") is not None else None,
            merge_chunks=bool(data.get("merge_chunks", False)),
            merge_max_chars=int(data.get("merge_max_chars", 2000)),
            rrf_k=int(data.get("rrf_k", 60)),
            retrieval_policies=_parse_retrieval_policies(data.get("retrieval_policies")),
            unit_type_boost=float(data.get("unit_type_boost", 0.0)),
            parent_fetch_depth=int(data.get("parent_fetch_depth", 1)),
            parent_fetch_cap=int(data.get("parent_fetch_cap", 2000)),
            parent_fetch_enabled=bool(data.get("parent_fetch_enabled", False)),
            reranker=str(data["reranker"]) if data.get("reranker") else None,
            co_retrieval_expand=bool(data.get("co_retrieval_expand", False)),
            guardrail_t1_mrr_drop_max=float(data.get("guardrail_t1_mrr_drop_max", 0.02)),
            clause_family_projection=bool(data.get("clause_family_projection", False)),
            clause_family_window=int(data.get("clause_family_window", 2)),
            clause_family_max_units=int(data.get("clause_family_max_units", 6)),
            clause_family_direction=str(data.get("clause_family_direction", "symmetric")),
            crossref_sidecar_expand=crossref.enabled,
            crossref_expand_top_k=crossref.expand_top_k,
            crossref_expand_per_hit=crossref.expand_per_hit,
            crossref_expand_total_cap=crossref.expand_total_cap,
            a_prime_generate_minimal=bool(data.get("a_prime_generate_minimal", False)),
            dual_list_fusion=dual_list.enabled,
            dual_list_ku=dual_list.ku,
            dual_list_kf=dual_list.kf,
            dual_list_kfinal=dual_list.kfinal,
            dual_list_qu=dual_list.qu,
            dual_list_family_window=dual_list.family_window,
            dual_list_family_max_units=dual_list.family_max_units,
            dual_list_family_direction=dual_list.family_direction,
            dependency_pairing_expand=pairing.enabled,
            dependency_pairing_emax=pairing.emax,
            baseline_metrics_path=str(data["baseline_metrics_path"]) if data.get("baseline_metrics_path") else None,
            crossref=crossref,
            dual_list=dual_list,
            pairing=pairing,
            query_enhancement=query_enhancement,
        )
        return cfg


def _parse_retrieval_policies(data: Any) -> Optional[Dict[str, RetrievalPolicy]]:
    """Parse retrieval_policies from YAML dict. Keys are corpus_id."""
    if not data or not isinstance(data, dict):
        return None
    out: Dict[str, RetrievalPolicy] = {}
    for corpus_id, raw in data.items():
        if not isinstance(raw, dict):
            continue
        pf = raw.get("parent_fetch_config")
        parent_fetch = None
        if isinstance(pf, dict):
            parent_fetch = ParentFetchConfig(
                depth=int(pf.get("depth", 1)),
                char_cap=int(pf.get("char_cap", 2000)),
                enabled=bool(pf.get("enabled", False)),
            )
        out[str(corpus_id)] = RetrievalPolicy(
            corpus_id=str(corpus_id),
            mode=str(raw.get("mode", "hybrid")),
            fusion_k=int(raw.get("fusion_k", raw.get("fusion_alpha", 60))),
            parent_fetch_config=parent_fetch,
            reranker=str(raw["reranker"]) if raw.get("reranker") else None,
        )
    return out if out else None


def _parse_crossref(data: Dict[str, Any]) -> CrossrefConfig:
    raw = data.get("crossref")
    if isinstance(raw, dict):
        return CrossrefConfig(
            enabled=bool(raw.get("enabled", data.get("crossref_sidecar_expand", False))),
            expand_top_k=int(raw.get("expand_top_k", data.get("crossref_expand_top_k", 10))),
            expand_per_hit=int(raw.get("expand_per_hit", data.get("crossref_expand_per_hit", 2))),
            expand_total_cap=int(raw.get("expand_total_cap", data.get("crossref_expand_total_cap", 20))),
        )
    return CrossrefConfig(
        enabled=bool(data.get("crossref_sidecar_expand", False)),
        expand_top_k=int(data.get("crossref_expand_top_k", 10)),
        expand_per_hit=int(data.get("crossref_expand_per_hit", 2)),
        expand_total_cap=int(data.get("crossref_expand_total_cap", 20)),
    )


def _parse_dual_list(data: Dict[str, Any]) -> DualListConfig:
    raw = data.get("dual_list")
    if isinstance(raw, dict):
        return DualListConfig(
            enabled=bool(raw.get("enabled", data.get("dual_list_fusion", False))),
            ku=int(raw.get("ku", data.get("dual_list_ku", 12))),
            kf=int(raw.get("kf", data.get("dual_list_kf", 12))),
            kfinal=int(raw.get("kfinal", data.get("dual_list_kfinal", 10))),
            qu=int(raw.get("qu", data.get("dual_list_qu", 6))),
            family_window=int(raw.get("family_window", data.get("dual_list_family_window", 3))),
            family_max_units=int(raw.get("family_max_units", data.get("dual_list_family_max_units", 6))),
            family_direction=str(raw.get("family_direction", data.get("dual_list_family_direction", "symmetric"))),
        )
    return DualListConfig(
        enabled=bool(data.get("dual_list_fusion", False)),
        ku=int(data.get("dual_list_ku", 12)),
        kf=int(data.get("dual_list_kf", 12)),
        kfinal=int(data.get("dual_list_kfinal", 10)),
        qu=int(data.get("dual_list_qu", 6)),
        family_window=int(data.get("dual_list_family_window", 3)),
        family_max_units=int(data.get("dual_list_family_max_units", 6)),
        family_direction=str(data.get("dual_list_family_direction", "symmetric")),
    )


def _parse_pairing(data: Dict[str, Any]) -> PairingConfig:
    raw = data.get("pairing")
    if isinstance(raw, dict):
        return PairingConfig(
            enabled=bool(raw.get("enabled", data.get("dependency_pairing_expand", False))),
            emax=int(raw.get("emax", data.get("dependency_pairing_emax", 6))),
        )
    return PairingConfig(
        enabled=bool(data.get("dependency_pairing_expand", False)),
        emax=int(data.get("dependency_pairing_emax", 6)),
    )


def _parse_query_enhancement(data: Dict[str, Any]) -> QueryEnhancementConfig:
    raw = data.get("query_enhancement")
    if isinstance(raw, dict):
        raw_only_add = raw.get("only_add")
        only_add_cfg = OnlyAddFusionConfig()
        if isinstance(raw_only_add, dict):
            only_add_cfg = OnlyAddFusionConfig(
                baseline_keep_n=int(raw_only_add.get("baseline_keep_n", only_add_cfg.baseline_keep_n)),
                variant_k_per_query=int(raw_only_add.get("variant_k_per_query", only_add_cfg.variant_k_per_query)),
                admission_cutoff=int(raw_only_add.get("admission_cutoff", only_add_cfg.admission_cutoff)),
                prefix_lock_n=int(raw_only_add.get("prefix_lock_n", only_add_cfg.prefix_lock_n)),
                tail_rerank=str(raw_only_add.get("tail_rerank", only_add_cfg.tail_rerank)),
                tail_rerank_window=int(raw_only_add.get("tail_rerank_window", only_add_cfg.tail_rerank_window)),
                append_score_band=float(raw_only_add.get("append_score_band", only_add_cfg.append_score_band)),
                rerank_union=bool(raw_only_add.get("rerank_union", only_add_cfg.rerank_union)),
            )
        return QueryEnhancementConfig(
            enabled=bool(raw.get("enabled", False)),
            profile_path=str(raw.get("profile_path", "")),
            mode=str(raw.get("mode", "none")),
            fusion_mode=str(raw.get("fusion_mode", "only_add")),
            only_add=only_add_cfg,
        )
    return QueryEnhancementConfig()


def resolve_model_id(model_id: str, registry: Optional[Dict[str, Any]] = None) -> str:
    """
    Resolve model_id to the underlying HuggingFace model name.
    If registry is provided and contains model_id, use its model_name; else return model_id as-is.
    """
    if registry is None:
        return model_id
    spec = registry.get(model_id)
    if spec is not None and hasattr(spec, "model_name"):
        return spec.model_name
    return model_id
