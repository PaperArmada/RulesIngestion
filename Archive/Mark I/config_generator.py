"""Ruleset config generation utilities."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from pydantic import BaseModel, Field

from config_profile import RulesetProfile, evaluate_profile_quality

if TYPE_CHECKING:
    from diagnostics_store import GenerationDiagnostics

class RulesetConfiguration(BaseModel):
    """Configuration for deterministic and non-deterministic enrichment."""

    ruleset_id: str
    doc_signature: str
    version: str
    source_fingerprint: Optional[str] = None
    schema_version: Optional[str] = "1.0"
    deterministic_rules: Dict[str, Any]
    deterministic_rules_evidence: Optional[List[Dict[str, Any]]] = None
    nondeterministic_flags: List[str]
    drift_criteria: Dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def generate_ruleset_config_with_retries(
    profile,
    generator: Callable[[Any, int], Dict[str, Any]],
    validator: Optional[Callable[[Dict[str, Any]], RulesetConfiguration]] = None,
    max_retries: int = 3,
) -> RulesetConfiguration:
    """Retry schema validation failures up to max_retries."""
    errors: List[str] = []
    validator = validator or (lambda payload: RulesetConfiguration(**payload))

    for attempt in range(1, max_retries + 1):
        payload = generator(profile, attempt)
        try:
            return validator(payload)
        except Exception as exc:  # pragma: no cover - exercised in tests
            errors.append(str(exc))

    if errors:
        raise ValueError(errors[-1])
    raise ValueError("config generation failed")


def _summarize_profile(profile: RulesetProfile) -> str:
    noise_count = len(profile.noise_headings) if hasattr(profile, "noise_headings") else 0
    sample_count = len(profile.samples or [])
    return (
        f"core_headings={len(profile.heading_hierarchy)}, "
        f"noise_headings={noise_count}, "
        f"block_types={len(profile.block_type_distribution)}, "
        f"samples={sample_count}"
    )


def generate_ruleset_config_with_diagnostics(
    profile: RulesetProfile,
    generator: Callable[[RulesetProfile, int], Dict[str, Any]],
    validator: Optional[Callable[[Dict[str, Any]], RulesetConfiguration]] = None,
    prompt_payload: Optional[dict] = None,
    max_retries: int = 3,
    profile_summary_builder: Callable[[RulesetProfile], str] = _summarize_profile,
) -> Tuple[Optional[RulesetConfiguration], Optional["GenerationDiagnostics"]]:
    errors: List[str] = []
    validator = validator or (lambda payload: RulesetConfiguration(**payload))
    last_output: Optional[Dict[str, Any]] = None

    quality_errors = evaluate_profile_quality(profile)
    if quality_errors:
        from diagnostics_store import GenerationDiagnostics

        diagnostics = GenerationDiagnostics(
            ruleset_id=profile.ruleset_id,
            doc_signature=profile.doc_signature,
            attempt_number=0,
            profile_summary=profile_summary_builder(profile),
            prompt_payload=prompt_payload,
            model_output=None,
            validation_errors=quality_errors,
        )
        return None, diagnostics

    for attempt in range(1, max_retries + 1):
        payload = generator(profile, attempt)
        last_output = payload
        try:
            return validator(payload), None
        except Exception as exc:
            errors.append(str(exc))

    from diagnostics_store import GenerationDiagnostics

    diagnostics = GenerationDiagnostics(
        ruleset_id=profile.ruleset_id,
        doc_signature=profile.doc_signature,
        attempt_number=max_retries,
        profile_summary=profile_summary_builder(profile),
        prompt_payload=prompt_payload,
        model_output=json.dumps(last_output, ensure_ascii=True) if last_output else None,
        validation_errors=errors or ["validation failed"],
    )
    return None, diagnostics
