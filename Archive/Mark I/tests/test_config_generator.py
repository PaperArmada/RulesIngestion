from typing import Any, Dict, List

import pytest

from config_generator import (
    RulesetConfiguration,
    generate_ruleset_config_with_retries,
)
from config_profile import RulesetProfile


def test_generate_ruleset_config_retries_until_valid() -> None:
    profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A"],
        block_type_distribution={"Text": 1},
    )
    attempts: List[int] = []

    def generator(_: RulesetProfile, attempt: int) -> Dict[str, Any]:
        attempts.append(attempt)
        if attempt < 3:
            return {"ruleset_id": "sf2e"}
        return {
            "ruleset_id": "sf2e",
            "doc_signature": "sig",
            "version": "v1",
            "deterministic_rules": {},
            "nondeterministic_flags": [],
            "drift_criteria": {},
        }

    def validator(payload: Dict[str, Any]) -> RulesetConfiguration:
        if "version" not in payload:
            raise ValueError("missing version")
        return RulesetConfiguration(**payload)

    config = generate_ruleset_config_with_retries(
        profile, generator=generator, validator=validator, max_retries=3
    )

    assert config.version == "v1"
    assert attempts == [1, 2, 3]


def test_generate_ruleset_config_raises_after_max_retries() -> None:
    profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A"],
        block_type_distribution={"Text": 1},
    )
    attempts: List[int] = []

    def generator(_: RulesetProfile, attempt: int) -> Dict[str, Any]:
        attempts.append(attempt)
        return {"ruleset_id": "sf2e"}

    def validator(_: Dict[str, Any]) -> RulesetConfiguration:
        raise ValueError("invalid")

    with pytest.raises(ValueError, match="invalid"):
        generate_ruleset_config_with_retries(
            profile, generator=generator, validator=validator, max_retries=3
        )

    assert attempts == [1, 2, 3]
