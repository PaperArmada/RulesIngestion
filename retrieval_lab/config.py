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
        if self.retrieval_mode not in ("dense", "hybrid", "bm25"):
            raise ValueError("retrieval_mode must be 'dense', 'hybrid', or 'bm25'")

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
        return cls(
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
