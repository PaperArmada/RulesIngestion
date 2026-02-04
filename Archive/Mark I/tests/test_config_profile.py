from config_profile import (
    RulesetProfile,
    build_ruleset_profile,
    compute_doc_signature,
    detect_structure_drift,
)


def test_build_ruleset_profile_extracts_heading_hierarchy_and_distribution() -> None:
    raw_blocks = [
        {"block_type": "SectionHeader", "html": "<h1>Chapter 1: Intro</h1>"},
        {"block_type": "Text", "html": "<p>Some intro text.</p>"},
        {"block_type": "SectionHeader", "html": "<h2>Combat</h2>"},
        {"block_type": "Text", "html": "<p>Rules text.</p>"},
        {"block_type": "Table", "html": "<table><tr><td>Row</td></tr></table>"},
    ]

    profile = build_ruleset_profile(raw_blocks, ruleset_id="sf2e", sample_size=2)

    assert profile.ruleset_id == "sf2e"
    assert profile.heading_hierarchy == ["Chapter 1: Intro", "Combat"]
    assert profile.block_type_distribution == {"SectionHeader": 2, "Text": 2, "Table": 1}
    assert profile.samples is not None
    assert len(profile.samples) == 2
    assert profile.doc_signature == compute_doc_signature(
        profile.heading_hierarchy, profile.block_type_distribution
    )


def test_detect_structure_drift_requires_heading_and_distribution_change() -> None:
    base = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="base",
        heading_hierarchy=["A", "B"],
        block_type_distribution={"Text": 2},
    )

    headings_changed = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="h",
        heading_hierarchy=["A", "C"],
        block_type_distribution={"Text": 2},
    )

    distribution_changed = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="d",
        heading_hierarchy=["A", "B"],
        block_type_distribution={"Text": 3},
    )

    both_changed = RulesetProfile(
        ruleset_id="sf2e",
        doc_signature="b",
        heading_hierarchy=["A", "C"],
        block_type_distribution={"Text": 3},
    )

    assert detect_structure_drift(base, headings_changed) is False
    assert detect_structure_drift(base, distribution_changed) is False
    assert detect_structure_drift(base, both_changed) is True
