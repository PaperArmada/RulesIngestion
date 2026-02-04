from typing import List, Optional

from config_generator import RulesetConfiguration
from config_profile import RulesetProfile
from enrichment_planner import EnrichmentPlan
from rules_ingestion_pipeline import (
    execute_enrichment_plan,
    resolve_ruleset_config,
    run_config_generation_with_diagnostics,
)


def _make_config(ruleset_id: str, doc_signature: str, version: str) -> RulesetConfiguration:
    return RulesetConfiguration(
        ruleset_id=ruleset_id,
        doc_signature=doc_signature,
        version=version,
        deterministic_rules={},
        nondeterministic_flags=[],
        drift_criteria={},
    )


def test_resolve_ruleset_config_reuses_when_no_drift() -> None:
    base_profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A"],
        block_type_distribution={"SectionHeader": 1},
    )
    latest_config = _make_config("sf2e", "sig", "v1")

    saved_profiles: List[str] = []

    def fetch_latest_profile(_: str, __: str) -> Optional[RulesetProfile]:
        return base_profile

    def fetch_latest_config(_: str, __: str) -> Optional[RulesetConfiguration]:
        return latest_config

    def save_profile(_: RulesetProfile, __: str) -> str:
        saved_profiles.append("saved")
        return "profile-id"

    def save_config(_: RulesetConfiguration, __: str) -> str:
        raise AssertionError("config should not be regenerated when no drift")

    def drift_detector(_: RulesetProfile, __: RulesetProfile) -> bool:
        return False

    def generator(*_args, **_kwargs) -> RulesetConfiguration:
        raise AssertionError("generator should not be called when no drift")

    config = resolve_ruleset_config(
        ruleset_id="sf2e",
        raw_blocks=[{"block_type": "SectionHeader", "html": "<h1>A</h1>"}],
        mongo_uri="mongodb://localhost",
        fetch_latest_profile=fetch_latest_profile,
        fetch_latest_config=fetch_latest_config,
        save_profile=save_profile,
        save_config=save_config,
        drift_detector=drift_detector,
        generator=generator,
    )

    assert config == latest_config
    assert saved_profiles == ["saved"]


def test_resolve_ruleset_config_regenerates_on_drift() -> None:
    base_profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A"],
        block_type_distribution={"SectionHeader": 1},
    )
    regenerated = _make_config("sf2e", "sig-new", "v2")

    saved_profiles: List[str] = []
    saved_configs: List[str] = []

    def fetch_latest_profile(_: str, __: str) -> Optional[RulesetProfile]:
        return base_profile

    def fetch_latest_config(_: str, __: str) -> Optional[RulesetConfiguration]:
        return _make_config("sf2e", "sig", "v1")

    def save_profile(_: RulesetProfile, __: str) -> str:
        saved_profiles.append("saved")
        return "profile-id"

    def save_config(_: RulesetConfiguration, __: str) -> str:
        saved_configs.append("saved")
        return "config-id"

    def drift_detector(_: RulesetProfile, __: RulesetProfile) -> bool:
        return True

    def generator(*_args, **_kwargs) -> RulesetConfiguration:
        return regenerated

    config = resolve_ruleset_config(
        ruleset_id="sf2e",
        raw_blocks=[{"block_type": "SectionHeader", "html": "<h1>B</h1>"}],
        mongo_uri="mongodb://localhost",
        fetch_latest_profile=fetch_latest_profile,
        fetch_latest_config=fetch_latest_config,
        save_profile=save_profile,
        save_config=save_config,
        drift_detector=drift_detector,
        generator=generator,
    )

    assert config == regenerated
    assert saved_profiles == ["saved"]
    assert saved_configs == ["saved"]


def test_execute_enrichment_plan_routes_llm_targets_only() -> None:
    blocks = [
        {"id": "b1", "paragraphs": ["Flavor", "Spell text"]},
        {"id": "b2", "paragraphs": ["Plain text"]},
    ]
    plan = EnrichmentPlan(
        ruleset_id="sf2e",
        chapter_id="ch1",
        doc_signature="sig",
        deterministic_steps=["rule_based_enrichment"],
        nondeterministic_steps=["llm_enrichment"],
        nondeterministic_targets=[{"block_id": "b1", "paragraph_index": 1, "text": "Spell text"}],
    )

    deterministic_calls = []
    llm_calls = []

    def deterministic_enricher(block):
        deterministic_calls.append(block["id"])
        return block

    def llm_enricher(target):
        llm_calls.append(target)
        return {"target": target}

    execute_enrichment_plan(
        blocks=blocks,
        plan=plan,
        llm_enabled=True,
        deterministic_enricher=deterministic_enricher,
        llm_enricher=llm_enricher,
    )

    assert deterministic_calls == ["b1", "b2"]
    assert llm_calls == [{"block_id": "b1", "paragraph_index": 1, "text": "Spell text"}]


def test_config_generation_failure_persists_diagnostics() -> None:
    profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A", "B", "C"],
        block_type_distribution={"SectionHeader": 3, "Text": 1},
        samples=["Sample one", "Sample two"],
    )
    saved = []

    def generator(_profile, _attempt):
        return {"ruleset_id": "sf2e"}

    def validator(_payload):
        raise ValueError("invalid")

    def diagnostics_saver(diagnostics, _mongo_uri, _policy=None):
        saved.append(diagnostics)
        return "diagnostics-id"

    config, diagnostics = run_config_generation_with_diagnostics(
        profile=profile,
        generator=generator,
        validator=validator,
        mongo_uri="mongodb://localhost",
        prompt_payload={"prompt": "test"},
        diagnostics_saver=diagnostics_saver,
        max_retries=2,
    )

    assert config is None
    assert diagnostics is not None
    assert diagnostics.validation_errors == ["invalid", "invalid"]
    assert diagnostics.prompt_payload == {"prompt": "test"}
    assert saved == [diagnostics]


def test_config_generation_quality_gate_saves_diagnostics() -> None:
    profile = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="sig",
        heading_hierarchy=["A"],
        noise_headings=["Glossary", "Index"],
        block_type_distribution={"Text": 1},
        samples=["Only one sample"],
    )
    saved = []
    generator_calls = []

    def generator(_profile, _attempt):
        generator_calls.append("called")
        return {}

    def validator(_payload):
        return RulesetConfiguration(**_payload)

    def diagnostics_saver(diagnostics, _mongo_uri, _policy=None):
        saved.append(diagnostics)
        return "diagnostics-id"

    config, diagnostics = run_config_generation_with_diagnostics(
        profile=profile,
        generator=generator,
        validator=validator,
        mongo_uri="mongodb://localhost",
        prompt_payload={"prompt": "test"},
        diagnostics_saver=diagnostics_saver,
        max_retries=2,
    )

    assert config is None
    assert diagnostics is not None
    assert generator_calls == []
    assert diagnostics.validation_errors
    assert saved == [diagnostics]
