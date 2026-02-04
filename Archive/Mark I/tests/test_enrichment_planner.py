from enrichment_planner import EnrichmentPlan, build_enrichment_plan
from config_generator import RulesetConfiguration


def test_build_enrichment_plan_structure() -> None:
    config = RulesetConfiguration(
        ruleset_id="sf2e",
        doc_signature="sig",
        version="v1",
        deterministic_rules={},
        nondeterministic_flags=["spell"],
        drift_criteria={},
    )

    blocks = [{"id": "b1", "paragraphs": ["A spell appears."]}]

    plan = build_enrichment_plan(
        ruleset_id="sf2e",
        chapter_id="ch1",
        doc_signature="sig",
        blocks=blocks,
        config=config,
    )

    assert isinstance(plan, EnrichmentPlan)
    assert plan.ruleset_id == "sf2e"
    assert plan.chapter_id == "ch1"
    assert plan.deterministic_steps == ["rule_based_enrichment"]
    assert plan.nondeterministic_steps == ["llm_enrichment"]
    assert len(plan.nondeterministic_targets) == 1


def test_paragraph_level_flagging() -> None:
    config = RulesetConfiguration(
        ruleset_id="sf2e",
        doc_signature="sig",
        version="v1",
        deterministic_rules={},
        nondeterministic_flags=["ritual", "spell"],
        drift_criteria={},
    )

    blocks = [
        {"id": "b1", "paragraphs": ["Flavor text.", "This is a ritual."]},
        {"id": "b2", "paragraphs": ["A spell effect here.", "Plain text."]},
    ]

    plan = build_enrichment_plan(
        ruleset_id="sf2e",
        chapter_id="ch1",
        doc_signature="sig",
        blocks=blocks,
        config=config,
    )

    targets = plan.nondeterministic_targets
    assert len(targets) == 2
    assert targets[0]["block_id"] == "b1"
    assert targets[0]["paragraph_index"] == 1
    assert targets[1]["block_id"] == "b2"
    assert targets[1]["paragraph_index"] == 0
