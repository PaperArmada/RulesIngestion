"""Tests for anchor_resolver: schema, resolution ladder, and drift prevention.

The drift prevention tests are the core proof that GoldAnchors survive
chunking strategy changes that would break raw unit-ID-based gold.
"""

from __future__ import annotations

import pytest

from retrieval_lab.anchor_schema import (
    AnchorResolution,
    GoldAnchor,
    generate_anchor_id,
    normalize_quote,
    quote_hash,
)
from retrieval_lab.anchor_resolver import (
    _jaccard_tokens,
    _paths_match,
    _token_overlap_recall,
    build_resolved_gold_sets,
    resolve_anchors,
    resolution_summary,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestAnchorSchema:
    def test_generate_anchor_id_deterministic(self):
        id1 = generate_anchor_id("DocA", 5, ["Combat", "Actions"], "When you attack")
        id2 = generate_anchor_id("DocA", 5, ["Combat", "Actions"], "When you attack")
        assert id1 == id2
        assert id1.startswith("ga_")

    def test_generate_anchor_id_differs_by_page(self):
        id1 = generate_anchor_id("DocA", 5, ["Combat"], "text")
        id2 = generate_anchor_id("DocA", 6, ["Combat"], "text")
        assert id1 != id2

    def test_generate_anchor_id_differs_by_path(self):
        id1 = generate_anchor_id("DocA", 5, ["Combat", "Actions"], "text")
        id2 = generate_anchor_id("DocA", 5, ["Combat", "Movement"], "text")
        assert id1 != id2

    def test_normalize_quote(self):
        assert normalize_quote("  Hello   World  ") == "hello world"
        assert normalize_quote("FOO\n\tBAR") == "foo bar"

    def test_quote_hash_deterministic(self):
        assert quote_hash("hello world") == quote_hash("  Hello   World  ")

    def test_gold_anchor_roundtrip(self):
        anchor = GoldAnchor(
            anchor_id="ga_test",
            document_id="TestDoc",
            anchor_type="prose",
            page=5,
            structural_path=["Combat", "Actions"],
            anchor_quote="When you attack a target.",
            quote_normalized_hash=quote_hash("When you attack a target."),
            cached_unit_ids=["unit_a"],
            cached_source_unit_ids=["src_1", "src_2"],
        )
        d = anchor.to_dict()
        restored = GoldAnchor.from_dict(d)
        assert restored.anchor_id == anchor.anchor_id
        assert restored.page == anchor.page
        assert restored.structural_path == anchor.structural_path
        assert restored.cached_unit_ids == anchor.cached_unit_ids

    def test_anchor_resolution_roundtrip(self):
        res = AnchorResolution(
            anchor_id="ga_test",
            substrate_version="v1",
            resolved_unit_ids=["u1", "u2"],
            resolution_status="split",
            resolved_by="source_unit_id_lineage",
            resolver_scores={"quote_overlap": 0.95},
        )
        d = res.to_dict()
        restored = AnchorResolution.from_dict(d)
        assert restored.resolution_status == "split"
        assert restored.resolved_unit_ids == ["u1", "u2"]


# ---------------------------------------------------------------------------
# Resolver helpers
# ---------------------------------------------------------------------------

class TestResolverHelpers:
    def test_jaccard_tokens_identical(self):
        assert _jaccard_tokens("hello world", "hello world") == 1.0

    def test_jaccard_tokens_partial(self):
        score = _jaccard_tokens("hello world foo", "hello world bar")
        assert 0.3 < score < 0.8

    def test_token_overlap_recall_full_containment(self):
        quote = "If an effect raises or lowers chances of success"
        text = "When two sides are opposed. If an effect raises or lowers chances of success, grant a bonus."
        assert _token_overlap_recall(quote, text) == pytest.approx(1.0)

    def test_jaccard_tokens_empty(self):
        assert _jaccard_tokens("", "hello") == 0.0
        assert _jaccard_tokens("hello", "") == 0.0

    def test_paths_match_exact(self):
        assert _paths_match(["Combat", "Actions"], ["Combat", "Actions"])

    def test_paths_match_case_insensitive(self):
        assert _paths_match(["COMBAT", "ACTIONS"], ["Combat", "Actions"])

    def test_paths_match_suffix(self):
        assert _paths_match(["Actions"], ["Combat", "Actions"])
        assert _paths_match(["Combat", "Actions"], ["Actions"])

    def test_paths_no_match(self):
        assert not _paths_match(["Combat"], ["Movement"])

    def test_paths_empty(self):
        assert not _paths_match([], ["Combat"])
        assert not _paths_match(["Combat"], [])


# ---------------------------------------------------------------------------
# Resolution ladder tests
# ---------------------------------------------------------------------------

def _make_anchor(
    anchor_id: str = "ga_test",
    page: int = 5,
    path: list[str] | None = None,
    quote: str = "When you take the Attack action, you make a melee or ranged attack.",
    cached_unit_ids: list[str] | None = None,
    cached_source_unit_ids: list[str] | None = None,
) -> GoldAnchor:
    return GoldAnchor(
        anchor_id=anchor_id,
        document_id="TestDoc",
        anchor_type="prose",
        page=page,
        structural_path=path or ["Combat", "Actions"],
        anchor_quote=quote,
        quote_normalized_hash=quote_hash(quote),
        cached_unit_ids=cached_unit_ids or [],
        cached_source_unit_ids=cached_source_unit_ids or [],
    )


class TestResolutionLadder:
    def test_step1_exact_cached_id(self):
        """Step 1: cached_unit_ids found directly in corpus."""
        corpus = [
            {"id": "unit_A", "text": "attack text", "page": 5,
             "structural_path": ["Combat", "Actions"], "source_unit_ids": []},
        ]
        anchor = _make_anchor(cached_unit_ids=["unit_A"])
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status == "exact"
        assert res["ga_test"].resolved_unit_ids == ["unit_A"]
        assert res["ga_test"].resolved_by == "cached_unit_ids"

    def test_step1_partial_cached_id(self):
        """Step 1: some cached IDs found, others missing."""
        corpus = [
            {"id": "unit_A", "text": "attack text", "page": 5,
             "structural_path": ["Combat", "Actions"], "source_unit_ids": []},
        ]
        anchor = _make_anchor(cached_unit_ids=["unit_A", "unit_B"])
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status == "approximate"
        assert res["ga_test"].resolved_unit_ids == ["unit_A"]

    def test_step2_lineage_merged(self):
        """Step 2: source unit IDs map to a merged corpus unit."""
        corpus = [
            {"id": "unit_merged", "text": "combined text about attacks and movement",
             "page": 5, "structural_path": ["Combat", "Actions"],
             "source_unit_ids": ["src_1", "src_2"]},
        ]
        anchor = _make_anchor(
            cached_unit_ids=["unit_old"],
            cached_source_unit_ids=["src_1"],
        )
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status in ("exact", "merged")
        assert "unit_merged" in res["ga_test"].resolved_unit_ids
        assert res["ga_test"].resolved_by == "source_unit_id_lineage"

    def test_step2_lineage_split(self):
        """Step 2: source IDs map to multiple corpus units (split scenario)."""
        corpus = [
            {"id": "unit_B", "text": "attack part 1", "page": 5,
             "structural_path": ["Combat", "Actions"],
             "source_unit_ids": ["src_1"]},
            {"id": "unit_C", "text": "attack part 2", "page": 5,
             "structural_path": ["Combat", "Actions"],
             "source_unit_ids": ["src_2"]},
        ]
        anchor = _make_anchor(
            cached_unit_ids=["unit_old"],
            cached_source_unit_ids=["src_1", "src_2"],
        )
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status == "split"
        assert set(res["ga_test"].resolved_unit_ids) == {"unit_B", "unit_C"}

    def test_step2_lineage_split_disambiguates_to_anchor_content(self):
        """Split lineage should collapse to the anchor's own page/path quote match."""
        corpus = [
            {
                "id": "unit_on_anchor_page",
                "text": "When you take the Attack action, you make a melee or ranged attack.",
                "page": 5,
                "structural_path": ["Combat", "Actions"],
                "source_unit_ids": ["src_1"],
            },
            {
                "id": "unit_other_page",
                "text": "Key terms and other unrelated text.",
                "page": 6,
                "structural_path": ["Combat", "Actions"],
                "source_unit_ids": ["src_2"],
            },
        ]
        anchor = _make_anchor(
            cached_unit_ids=["unit_old"],
            cached_source_unit_ids=["src_1", "src_2"],
        )
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status == "approximate"
        assert res["ga_test"].resolved_unit_ids == ["unit_on_anchor_page"]
        assert "lineage_split_disambiguated" in res["ga_test"].resolved_by

    def test_step2_lineage_exact_arbitrates_to_stronger_local(self):
        """Exact lineage can switch when local path+quote evidence is clearly stronger."""
        corpus = [
            {
                "id": "unit_lineage_exact",
                "text": "This text barely overlaps the attack quote and sits under another heading.",
                "page": 9,
                "structural_path": ["Lore"],
                "source_unit_ids": ["src_1"],
            },
            {
                "id": "unit_local_strong",
                "text": "When you take the Attack action, you make a melee or ranged attack.",
                "page": 5,
                "structural_path": ["Combat", "Actions"],
                "source_unit_ids": [],
            },
        ]
        anchor = _make_anchor(
            page=5,
            path=["Combat", "Actions"],
            cached_unit_ids=["unit_old"],
            cached_source_unit_ids=["src_1"],
        )
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status == "approximate"
        assert res["ga_test"].resolved_unit_ids == ["unit_local_strong"]
        assert "lineage_exact_arbitrated" in res["ga_test"].resolved_by

    def test_step3_page_path_quote(self):
        """Step 3: no ID match, but page + path + quote overlap resolves."""
        corpus = [
            {"id": "unit_new", "page": 5,
             "structural_path": ["Combat", "Actions"],
             "text": "When you take the Attack action, you make a melee or ranged attack against a creature.",
             "source_unit_ids": []},
            {"id": "unit_other", "page": 5,
             "structural_path": ["Combat", "Movement"],
             "text": "You can move up to your speed.",
             "source_unit_ids": []},
        ]
        anchor = _make_anchor()  # no cached IDs
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status == "approximate"
        assert res["ga_test"].resolved_unit_ids == ["unit_new"]
        assert res["ga_test"].resolved_by == "page_path_quote"

    def test_step4_nearby_page(self):
        """Step 4: content shifted to adjacent page."""
        corpus = [
            {"id": "unit_shifted", "page": 6,
             "structural_path": ["Combat", "Actions"],
             "text": "When you take the Attack action, you make a melee or ranged attack.",
             "source_unit_ids": []},
        ]
        anchor = _make_anchor(page=5)  # anchor says page 5, content moved to 6
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status == "approximate"
        assert res["ga_test"].resolved_unit_ids == ["unit_shifted"]
        assert "nearby_page" in res["ga_test"].resolved_by

    def test_step5_unresolved(self):
        """Step 5: nothing matches."""
        corpus = [
            {"id": "unit_unrelated", "page": 99,
             "structural_path": ["Spells"],
             "text": "Fireball deals 8d6 fire damage.",
             "source_unit_ids": []},
        ]
        anchor = _make_anchor()
        res = resolve_anchors({"ga_test": anchor}, corpus, "v1")

        assert res["ga_test"].resolution_status == "unresolved"
        assert res["ga_test"].resolved_unit_ids == []

    def test_quote_recall_resolves_low_jaccard_same_path(self):
        """Step 3 should resolve when quote containment is high but Jaccard is low."""
        anchor_quote = (
            "If an effect raises or lowers chances of success, "
            "grant a +1 circumstance bonus or a -1 circumstance penalty."
        )
        corpus = [
            {
                "id": "unit_off_session",
                "page": 491,
                "structural_path": ["OFF-SESSION GAMING"],
                "text": (
                    "When two sides are opposed, have one roll against the other's DC. "
                    "If an effect raises or lowers chances of success, grant a +1 circumstance bonus "
                    "or a -1 circumstance penalty. Then continue adjudicating."
                ),
                "source_unit_ids": [],
            },
        ]
        anchor = _make_anchor(
            page=491,
            path=["OFF-SESSION GAMING"],
            quote=anchor_quote,
        )
        res = resolve_anchors({"ga_test": anchor}, corpus, "v2")

        assert res["ga_test"].resolution_status == "approximate"
        assert res["ga_test"].resolved_unit_ids == ["unit_off_session"]
        assert res["ga_test"].resolved_by == "page_path_quote"

    def test_nearby_relaxed_path_resolves_heading_drift(self):
        """Step 5 should resolve nearby-page heading drift with strict quote containment."""
        anchor_quote = (
            "Recall Knowledge — Concentrate — You attempt a skill check to remember "
            "knowledge regarding a topic related to that skill."
        )
        corpus = [
            {
                "id": "unit_shifted_heading",
                "page": 238,  # shifted to adjacent page
                "structural_path": ["RECALL KNOWLEDGE [UNTRAINED]"],  # noisy path drift
                "text": (
                    "To remember useful information, you can attempt to Recall Knowledge. "
                    "Recall Knowledge — Concentrate — You attempt a skill check to remember "
                    "knowledge regarding a topic related to that skill."
                ),
                "source_unit_ids": [],
            },
        ]
        anchor = _make_anchor(
            page=239,
            path=["CONCENTRATE"],
            quote=anchor_quote,
        )
        res = resolve_anchors({"ga_test": anchor}, corpus, "v2")

        assert res["ga_test"].resolution_status == "approximate"
        assert res["ga_test"].resolved_unit_ids == ["unit_shifted_heading"]
        assert "relaxed_path_quote" in res["ga_test"].resolved_by


# ---------------------------------------------------------------------------
# Drift prevention tests — the core proof
# ---------------------------------------------------------------------------

class TestDriftPrevention:
    """Prove that GoldAnchors survive chunking changes that break raw unit IDs.

    Each test simulates a specific chunking strategy change and verifies
    that the anchor resolver finds the correct evidence despite the
    unit IDs changing.
    """

    def _make_v1_corpus(self) -> list[dict]:
        """Baseline corpus: 3 units on page 10 under 'Abilities > Strength'."""
        return [
            {"id": "v1_str_intro", "page": 10,
             "structural_path": ["Abilities", "Strength"],
             "text": "Strength measures your character's physical power. "
                     "It is important for melee combat and carrying capacity.",
             "source_unit_ids": []},
            {"id": "v1_str_checks", "page": 10,
             "structural_path": ["Abilities", "Strength"],
             "text": "Strength checks are used when you attempt to lift, push, "
                     "pull, or break something. Athletics is the main skill "
                     "associated with Strength.",
             "source_unit_ids": []},
            {"id": "v1_str_attacks", "page": 10,
             "structural_path": ["Abilities", "Strength"],
             "text": "You add your Strength modifier to melee weapon attack "
                     "and damage rolls.",
             "source_unit_ids": []},
        ]

    def _make_anchors(self) -> dict[str, GoldAnchor]:
        """Two anchors: one for the intro, one for the checks section."""
        return {
            "ga_str_intro": _make_anchor(
                anchor_id="ga_str_intro",
                page=10,
                path=["Abilities", "Strength"],
                quote="Strength measures your character's physical power.",
                cached_unit_ids=["v1_str_intro"],
                cached_source_unit_ids=["v1_str_intro"],
            ),
            "ga_str_checks": _make_anchor(
                anchor_id="ga_str_checks",
                page=10,
                path=["Abilities", "Strength"],
                quote="Strength checks are used when you attempt to lift, push, "
                      "pull, or break something.",
                cached_unit_ids=["v1_str_checks"],
                cached_source_unit_ids=["v1_str_checks"],
            ),
        }

    def test_baseline_exact_resolution(self):
        """Anchors resolve exactly against the corpus they were authored from."""
        corpus = self._make_v1_corpus()
        anchors = self._make_anchors()
        res = resolve_anchors(anchors, corpus, "v1")

        assert res["ga_str_intro"].resolution_status == "exact"
        assert res["ga_str_intro"].resolved_unit_ids == ["v1_str_intro"]
        assert res["ga_str_checks"].resolution_status == "exact"
        assert res["ga_str_checks"].resolved_unit_ids == ["v1_str_checks"]

    def test_drift_merge_units(self):
        """Simulate increasing min_chars: two small units merged into one.

        Without anchors, both v1_str_intro and v1_str_checks would be
        missing from the corpus, causing 2 gold misses.  With anchors,
        the resolver follows source_unit_id lineage to the merged unit.
        """
        corpus_v2 = [
            {"id": "v2_str_merged",
             "page": 10,
             "structural_path": ["Abilities", "Strength"],
             "text": "Strength measures your character's physical power. "
                     "It is important for melee combat and carrying capacity. "
                     "Strength checks are used when you attempt to lift, push, "
                     "pull, or break something. Athletics is the main skill "
                     "associated with Strength.",
             "source_unit_ids": ["v1_str_intro", "v1_str_checks"]},
            {"id": "v2_str_attacks",
             "page": 10,
             "structural_path": ["Abilities", "Strength"],
             "text": "You add your Strength modifier to melee weapon attack "
                     "and damage rolls.",
             "source_unit_ids": ["v1_str_attacks"]},
        ]
        anchors = self._make_anchors()
        res = resolve_anchors(anchors, corpus_v2, "v2")

        # Both anchors should resolve (not unresolved!)
        assert res["ga_str_intro"].resolution_status != "unresolved"
        assert res["ga_str_checks"].resolution_status != "unresolved"

        # Both should map to the merged unit via lineage
        assert "v2_str_merged" in res["ga_str_intro"].resolved_unit_ids
        assert "v2_str_merged" in res["ga_str_checks"].resolved_unit_ids

        summary = resolution_summary(res)
        assert summary["all_resolved"]

    def test_drift_split_unit(self):
        """Simulate decreasing min_chars: one unit split into two.

        Without anchors, v1_str_intro would be missing.  With anchors,
        the resolver finds the split fragments via quote matching.
        """
        corpus_v2 = [
            {"id": "v2_str_power",
             "page": 10,
             "structural_path": ["Abilities", "Strength"],
             "text": "Strength measures your character's physical power.",
             "source_unit_ids": []},
            {"id": "v2_str_combat",
             "page": 10,
             "structural_path": ["Abilities", "Strength"],
             "text": "It is important for melee combat and carrying capacity.",
             "source_unit_ids": []},
            {"id": "v2_str_checks",
             "page": 10,
             "structural_path": ["Abilities", "Strength"],
             "text": "Strength checks are used when you attempt to lift, push, "
                     "pull, or break something. Athletics is the main skill "
                     "associated with Strength.",
             "source_unit_ids": []},
        ]
        anchors = self._make_anchors()
        res = resolve_anchors(anchors, corpus_v2, "v2")

        # ga_str_intro: cached ID gone, no lineage, but quote matches v2_str_power
        assert res["ga_str_intro"].resolution_status != "unresolved"
        assert len(res["ga_str_intro"].resolved_unit_ids) >= 1

        # ga_str_checks: cached ID gone, but quote matches v2_str_checks
        assert res["ga_str_checks"].resolution_status != "unresolved"
        assert "v2_str_checks" in res["ga_str_checks"].resolved_unit_ids

    def test_drift_heading_path_change(self):
        """Simulate OCR improvement changing heading case.

        structural_path changes from ["Abilities", "Strength"] to
        ["ABILITIES", "STRENGTH"].  Suffix/case-insensitive matching
        should still resolve.
        """
        corpus_v2 = [
            {"id": "v2_str_intro",
             "page": 10,
             "structural_path": ["ABILITIES", "STRENGTH"],
             "text": "Strength measures your character's physical power. "
                     "It is important for melee combat and carrying capacity.",
             "source_unit_ids": []},
        ]
        anchors = {
            "ga_str_intro": _make_anchor(
                anchor_id="ga_str_intro",
                page=10,
                path=["Abilities", "Strength"],
                quote="Strength measures your character's physical power.",
            ),
        }
        res = resolve_anchors(anchors, corpus_v2, "v2")

        assert res["ga_str_intro"].resolution_status != "unresolved"
        assert "v2_str_intro" in res["ga_str_intro"].resolved_unit_ids

    def test_drift_page_boundary_shift(self):
        """Simulate re-extraction shifting content to adjacent page."""
        corpus_v2 = [
            {"id": "v2_str_intro",
             "page": 11,  # was page 10
             "structural_path": ["Abilities", "Strength"],
             "text": "Strength measures your character's physical power. "
                     "It is important for melee combat and carrying capacity.",
             "source_unit_ids": []},
        ]
        anchors = {
            "ga_str_intro": _make_anchor(
                anchor_id="ga_str_intro",
                page=10,
                path=["Abilities", "Strength"],
                quote="Strength measures your character's physical power.",
            ),
        }
        res = resolve_anchors(anchors, corpus_v2, "v2")

        assert res["ga_str_intro"].resolution_status != "unresolved"
        assert "v2_str_intro" in res["ga_str_intro"].resolved_unit_ids

    def test_combined_drift_merge_plus_path_change(self):
        """Multiple simultaneous changes: merge + heading case change.

        This is the hardest case — units merged AND headings changed.
        Lineage should handle the merge; path normalization handles the case.
        """
        corpus_v2 = [
            {"id": "v2_str_all",
             "page": 10,
             "structural_path": ["ABILITIES", "STRENGTH"],
             "text": "Strength measures your character's physical power. "
                     "It is important for melee combat and carrying capacity. "
                     "Strength checks are used when you attempt to lift, push, "
                     "pull, or break something.",
             "source_unit_ids": ["v1_str_intro", "v1_str_checks"]},
        ]
        anchors = self._make_anchors()
        res = resolve_anchors(anchors, corpus_v2, "v2")

        assert res["ga_str_intro"].resolution_status != "unresolved"
        assert res["ga_str_checks"].resolution_status != "unresolved"

        summary = resolution_summary(res)
        assert summary["all_resolved"]


# ---------------------------------------------------------------------------
# build_resolved_gold_sets tests
# ---------------------------------------------------------------------------

class TestBuildResolvedGoldSets:
    def test_queries_without_anchors_pass_through(self):
        queries = [{"id": "q1", "gold_unit_ids": ["u1"], "required_gold": ["u1"]}]
        result = build_resolved_gold_sets(queries, {})
        assert result[0]["required_gold"] == ["u1"]

    def test_queries_with_anchors_get_resolved_gold(self):
        queries = [
            {"id": "q1", "required_anchor_ids": ["ga_a"], "supporting_anchor_ids": ["ga_b"]},
        ]
        resolutions = {
            "ga_a": AnchorResolution("ga_a", "v1", ["u1", "u2"], "split", "lineage"),
            "ga_b": AnchorResolution("ga_b", "v1", ["u3"], "exact", "cached"),
        }
        result = build_resolved_gold_sets(queries, resolutions)

        assert result[0]["required_gold"] == ["u1", "u2"]
        assert result[0]["supporting_gold"] == ["u3"]
        assert result[0]["gold_unit_ids"] == ["u1", "u2", "u3"]

    def test_deduplication_across_required_and_supporting(self):
        """If a unit appears in both required and supporting, it stays only in required."""
        queries = [
            {"id": "q1", "required_anchor_ids": ["ga_a"], "supporting_anchor_ids": ["ga_b"]},
        ]
        resolutions = {
            "ga_a": AnchorResolution("ga_a", "v1", ["u1"], "exact", "cached"),
            "ga_b": AnchorResolution("ga_b", "v1", ["u1", "u2"], "exact", "cached"),
        }
        result = build_resolved_gold_sets(queries, resolutions)

        assert result[0]["required_gold"] == ["u1"]
        assert result[0]["supporting_gold"] == ["u2"]

    def test_unresolved_anchor_produces_empty_gold(self):
        queries = [{"id": "q1", "required_anchor_ids": ["ga_missing"]}]
        resolutions = {
            "ga_missing": AnchorResolution("ga_missing", "v1", [], "unresolved", "none"),
        }
        result = build_resolved_gold_sets(queries, resolutions)
        assert result[0]["required_gold"] == []


# ---------------------------------------------------------------------------
# resolution_summary tests
# ---------------------------------------------------------------------------

class TestResolutionSummary:
    def test_all_resolved(self):
        resolutions = {
            "a": AnchorResolution("a", "v1", ["u1"], "exact", "cached"),
            "b": AnchorResolution("b", "v1", ["u2"], "approximate", "quote"),
        }
        s = resolution_summary(resolutions)
        assert s["all_resolved"]
        assert s["total_anchors"] == 2
        assert s["by_status"] == {"exact": 1, "approximate": 1}

    def test_unresolved_reported(self):
        resolutions = {
            "a": AnchorResolution("a", "v1", ["u1"], "exact", "cached"),
            "b": AnchorResolution("b", "v1", [], "unresolved", "none"),
        }
        s = resolution_summary(resolutions)
        assert not s["all_resolved"]
        assert s["unresolved_anchors"] == ["b"]
