"""QueryExpansionProfile: corpus-specific vocabulary, synonyms, and rewrite policies."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import blake3

logger = logging.getLogger(__name__)

_DICE_RE = re.compile(r"\b(\d*)\s*d\s*(\d+)\b", re.IGNORECASE)


@dataclass
class SynonymSet:
    name: str
    canonical: str
    variants: List[str]
    notes: str = ""

    def all_terms(self) -> List[str]:
        return [self.canonical] + list(self.variants)


@dataclass
class TermBooster:
    concept: str
    boosters: List[str]
    weight_hint: float = 1.0


@dataclass
class NormalizationConfig:
    lowercase: bool = True
    unicode_nfkc: bool = True
    strip_punct: bool = False
    dice_normalization: bool = True
    stopword_policy: str = "none"  # none | light | bm25_default


@dataclass
class AllowedVocab:
    top_keywords: List[str] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)


@dataclass
class DriftGuardConfig:
    enabled: bool = False
    method: str = "lexical_overlap"  # embedding_similarity | lexical_overlap
    threshold: float = 0.3


@dataclass
class PoliciesConfig:
    max_expanded_queries: int = 3
    include_original: bool = True
    require_facet_diversity: bool = True
    drift_guard: DriftGuardConfig = field(default_factory=DriftGuardConfig)


@dataclass
class DecompositionConfig:
    enabled: bool = False
    when: str = "multi_hop_only"  # multi_hop_only | always | never
    model_id: str = ""
    reasoning_effort: str = "none"
    prompt_template_id: str = "retrieval_query_decomposition_v2"
    output_schema_version: str = "v1"
    max_subqueries: Optional[int] = None  # legacy: ignored by Responses-based decomposition


@dataclass
class LLMRewriteConfig:
    enabled: bool = False
    model_id: str = ""
    temperature: float = 0.0
    top_p: float = 1.0
    prompt_template_id: str = ""
    prompt_hash: str = ""
    output_schema_version: str = "v1"


@dataclass
class CacheConfig:
    enabled: bool = True
    cache_dir: str = ".qe_cache"


@dataclass
class QueryExpansionProfile:
    """Corpus-specific query expansion profile. Versioned artifact alongside corpus builds."""

    profile_id: str
    corpus_id: str
    corpus_hash: str = ""
    profile_version: str = "0.1.0"

    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    synonym_sets: List[SynonymSet] = field(default_factory=list)
    term_boosters: List[TermBooster] = field(default_factory=list)
    allowed_vocab: AllowedVocab = field(default_factory=AllowedVocab)
    policies: PoliciesConfig = field(default_factory=PoliciesConfig)
    decomposition: DecompositionConfig = field(default_factory=DecompositionConfig)
    llm_rewrite: LLMRewriteConfig = field(default_factory=LLMRewriteConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)

    def compute_hash(self) -> str:
        """Stable hash of profile content (sorted-key canonical JSON -> blake3)."""
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain dict (suitable for JSON)."""
        return _dataclass_to_dict(self)


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclass instances to dicts."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _dataclass_to_dict(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, list):
        return [_dataclass_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    return obj


def _canonical_hash(data: Dict[str, Any]) -> str:
    """Compute blake3 hash of canonical (sorted-key) JSON."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return blake3.blake3(canonical.encode("utf-8")).hexdigest()


def load_profile(path: str | Path) -> QueryExpansionProfile:
    """Load a QueryExpansionProfile from a JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Profile not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return _profile_from_dict(data)


def _profile_from_dict(data: Dict[str, Any]) -> QueryExpansionProfile:
    """Build profile from a parsed JSON dict."""
    norm_raw = data.get("normalization", {})
    normalization = NormalizationConfig(
        lowercase=bool(norm_raw.get("lowercase", True)),
        unicode_nfkc=bool(norm_raw.get("unicode_nfkc", True)),
        strip_punct=bool(norm_raw.get("strip_punct", False)),
        dice_normalization=bool(norm_raw.get("dice_normalization", True)),
        stopword_policy=str(norm_raw.get("stopword_policy", "none")),
    )

    synonym_sets = [
        SynonymSet(
            name=str(s.get("name", "")),
            canonical=str(s.get("canonical", "")),
            variants=list(s.get("variants", [])),
            notes=str(s.get("notes", "")),
        )
        for s in data.get("synonym_sets", [])
    ]

    term_boosters = [
        TermBooster(
            concept=str(t.get("concept", "")),
            boosters=list(t.get("boosters", [])),
            weight_hint=float(t.get("weight_hint", 1.0)),
        )
        for t in data.get("term_boosters", [])
    ]

    av_raw = data.get("allowed_vocab", {})
    allowed_vocab = AllowedVocab(
        top_keywords=list(av_raw.get("top_keywords", [])),
        headings=list(av_raw.get("headings", [])),
        entities=list(av_raw.get("entities", [])),
    )

    pol_raw = data.get("policies", {})
    dg_raw = pol_raw.get("drift_guard", {})
    policies = PoliciesConfig(
        max_expanded_queries=int(pol_raw.get("max_expanded_queries", 3)),
        include_original=bool(pol_raw.get("include_original", True)),
        require_facet_diversity=bool(pol_raw.get("require_facet_diversity", True)),
        drift_guard=DriftGuardConfig(
            enabled=bool(dg_raw.get("enabled", False)),
            method=str(dg_raw.get("method", "lexical_overlap")),
            threshold=float(dg_raw.get("threshold", 0.3)),
        ),
    )

    dec_raw = data.get("decomposition", {})
    decomposition = DecompositionConfig(
        enabled=bool(dec_raw.get("enabled", False)),
        when=str(dec_raw.get("when", "multi_hop_only")),
        model_id=str(dec_raw.get("model_id", "")),
        reasoning_effort=str(dec_raw.get("reasoning_effort", "none")),
        prompt_template_id=str(dec_raw.get("prompt_template_id", "retrieval_query_decomposition_v2")),
        output_schema_version=str(dec_raw.get("output_schema_version", "v1")),
        max_subqueries=(
            int(dec_raw["max_subqueries"])
            if dec_raw.get("max_subqueries") is not None
            else None
        ),
    )

    llm_raw = data.get("llm_rewrite", {})
    llm_rewrite = LLMRewriteConfig(
        enabled=bool(llm_raw.get("enabled", False)),
        model_id=str(llm_raw.get("model_id", "")),
        temperature=float(llm_raw.get("temperature", 0.0)),
        top_p=float(llm_raw.get("top_p", 1.0)),
        prompt_template_id=str(llm_raw.get("prompt_template_id", "")),
        prompt_hash=str(llm_raw.get("prompt_hash", "")),
        output_schema_version=str(llm_raw.get("output_schema_version", "v1")),
    )

    cache_raw = data.get("cache", {})
    cache = CacheConfig(
        enabled=bool(cache_raw.get("enabled", True)),
        cache_dir=str(cache_raw.get("cache_dir", ".qe_cache")),
    )

    return QueryExpansionProfile(
        profile_id=str(data.get("profile_id", "")),
        corpus_id=str(data.get("corpus_id", "")),
        corpus_hash=str(data.get("corpus_hash", "")),
        profile_version=str(data.get("profile_version", "0.1.0")),
        normalization=normalization,
        synonym_sets=synonym_sets,
        term_boosters=term_boosters,
        allowed_vocab=allowed_vocab,
        policies=policies,
        decomposition=decomposition,
        llm_rewrite=llm_rewrite,
        cache=cache,
    )


def normalize_query(text: str, profile: QueryExpansionProfile) -> str:
    """Apply deterministic normalization to a query string."""
    norm = profile.normalization
    result = text

    if norm.unicode_nfkc:
        result = unicodedata.normalize("NFKC", result)

    if norm.dice_normalization:
        result = _DICE_RE.sub(lambda m: f"{m.group(1)}d{m.group(2)}", result)

    if norm.lowercase:
        result = result.lower()

    if norm.strip_punct:
        result = re.sub(r"[^\w\s]", " ", result)
        result = re.sub(r"\s+", " ", result).strip()

    return result


def validate_profile(profile: QueryExpansionProfile) -> List[str]:
    """Return list of validation errors (empty = valid)."""
    errors: List[str] = []
    if not profile.profile_id:
        errors.append("profile_id is required")
    if not profile.corpus_id:
        errors.append("corpus_id is required")
    if profile.normalization.stopword_policy not in ("none", "light", "bm25_default"):
        errors.append(f"invalid stopword_policy: {profile.normalization.stopword_policy}")
    if profile.policies.max_expanded_queries < 1:
        errors.append("max_expanded_queries must be >= 1")
    if profile.decomposition.when not in ("multi_hop_only", "always", "never"):
        errors.append(f"invalid decomposition.when: {profile.decomposition.when}")
    if profile.decomposition.reasoning_effort not in ("none", "low", "medium", "high"):
        errors.append(f"invalid decomposition.reasoning_effort: {profile.decomposition.reasoning_effort}")
    if profile.llm_rewrite.enabled:
        if not profile.llm_rewrite.model_id:
            errors.append("llm_rewrite.model_id required when llm_rewrite is enabled")
        if profile.llm_rewrite.temperature != 0.0:
            errors.append(f"llm_rewrite.temperature must be 0.0 for determinism, got {profile.llm_rewrite.temperature}")
    for i, ss in enumerate(profile.synonym_sets):
        if not ss.canonical:
            errors.append(f"synonym_sets[{i}].canonical is required")
        if not ss.variants:
            errors.append(f"synonym_sets[{i}].variants must be non-empty")
    return errors
