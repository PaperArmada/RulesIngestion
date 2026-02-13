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
    # Grouped options (wave-2 structure). Flat keys remain authoritative for backward compatibility.
    crossref: CrossrefConfig = field(default_factory=CrossrefConfig)
    dual_list: DualListConfig = field(default_factory=DualListConfig)
    pairing: PairingConfig = field(default_factory=PairingConfig)

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

    def validate(self, embed_only: bool = False, eval_only: bool = False) -> None:
        """Raise ValueError if config is invalid. Use embed_only=True or eval_only=True for single-step validation."""
        if not self.substrate_path:
            raise ValueError("substrate_path is required")
        if not Path(self.substrate_path).exists():
            raise ValueError(f"substrate_path does not exist: {self.substrate_path}")
        if self.retrieval_mode not in ("dense", "hybrid", "hybrid+rerank", "bm25"):
            raise ValueError("retrieval_mode must be 'dense', 'hybrid', 'hybrid+rerank', or 'bm25'")
        if self.retrieval_mode == "bm25" and self.dual_list_fusion:
            raise ValueError("dual_list_fusion is not supported in bm25 mode")
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
            expand_context=bool(data.get("expand_context", False)),
            expand_context_n=int(data.get("expand_context_n", 1)),
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
            crossref=crossref,
            dual_list=dual_list,
            pairing=pairing,
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
