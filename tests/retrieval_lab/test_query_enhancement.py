"""Tests for query enhancement: profile, enhancer, cache, determinism."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from retrieval_lab.query_enhancement.cache import QueryEnhancementCache, _compute_cache_key
from retrieval_lab.query_enhancement.enhancer import enhance_queries
from retrieval_lab.query_enhancement.profile import (
    AllowedVocab,
    CacheConfig,
    DecompositionConfig,
    DriftGuardConfig,
    LLMRewriteConfig,
    NormalizationConfig,
    PoliciesConfig,
    QueryExpansionProfile,
    SynonymSet,
    TermBooster,
    load_profile,
    normalize_query,
    validate_profile,
)


def _make_profile(**overrides) -> QueryExpansionProfile:
    defaults = dict(
        profile_id="test_v1_qe_001",
        corpus_id="test_corpus",
        corpus_hash="abc123",
        profile_version="0.1.0",
        synonym_sets=[
            SynonymSet(name="gm_terms", canonical="referee", variants=["gm", "dm", "judge"]),
            SynonymSet(name="save_terms", canonical="saving throw", variants=["save", "resist"]),
        ],
    )
    defaults.update(overrides)
    return QueryExpansionProfile(**defaults)


# --- Profile tests ---


class TestProfile:
    def test_hash_stability(self):
        """Same profile content produces same hash across calls."""
        p1 = _make_profile()
        p2 = _make_profile()
        assert p1.compute_hash() == p2.compute_hash()

    def test_hash_changes_on_content_change(self):
        p1 = _make_profile(profile_version="0.1.0")
        p2 = _make_profile(profile_version="0.2.0")
        assert p1.compute_hash() != p2.compute_hash()

    def test_to_dict_roundtrip(self):
        p = _make_profile()
        d = p.to_dict()
        assert d["profile_id"] == "test_v1_qe_001"
        assert len(d["synonym_sets"]) == 2
        assert d["synonym_sets"][0]["canonical"] == "referee"
        assert d["normalization"]["lowercase"] is True

    def test_load_profile_from_json(self, tmp_path: Path):
        p = _make_profile()
        path = tmp_path / "profile.json"
        path.write_text(json.dumps(p.to_dict(), indent=2))

        loaded = load_profile(path)
        assert loaded.profile_id == p.profile_id
        assert loaded.corpus_id == p.corpus_id
        assert len(loaded.synonym_sets) == 2
        assert loaded.synonym_sets[0].canonical == "referee"
        assert loaded.compute_hash() == p.compute_hash()

    def test_load_profile_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_profile("/nonexistent/profile.json")

    def test_validate_valid(self):
        p = _make_profile()
        errors = validate_profile(p)
        assert errors == []

    def test_validate_missing_profile_id(self):
        p = _make_profile(profile_id="")
        errors = validate_profile(p)
        assert any("profile_id" in e for e in errors)

    def test_validate_missing_corpus_id(self):
        p = _make_profile(corpus_id="")
        errors = validate_profile(p)
        assert any("corpus_id" in e for e in errors)

    def test_validate_llm_requires_model_id(self):
        p = _make_profile()
        p.llm_rewrite = LLMRewriteConfig(enabled=True, model_id="")
        errors = validate_profile(p)
        assert any("model_id" in e for e in errors)

    def test_validate_llm_temperature_must_be_zero(self):
        p = _make_profile()
        p.llm_rewrite = LLMRewriteConfig(enabled=True, model_id="gpt-4o", temperature=0.5)
        errors = validate_profile(p)
        assert any("temperature" in e for e in errors)


# --- Normalization tests ---


class TestNormalization:
    def test_lowercase(self):
        p = _make_profile()
        assert normalize_query("How Does INITIATIVE Work?", p) == "how does initiative work?"

    def test_dice_normalization(self):
        p = _make_profile()
        assert "d20" in normalize_query("roll a d 20", p)
        assert "2d6" in normalize_query("roll 2 d 6 damage", p)

    def test_unicode_nfkc(self):
        p = _make_profile()
        result = normalize_query("ﬁre", p)
        assert "fi" in result

    def test_strip_punct(self):
        p = _make_profile()
        p.normalization.strip_punct = True
        result = normalize_query("What's the AC?", p)
        assert "'" not in result
        assert "?" not in result

    def test_no_lowercase(self):
        p = _make_profile()
        p.normalization.lowercase = False
        result = normalize_query("HOW", p)
        assert result == "HOW"


# --- Cache tests ---


class TestCache:
    def test_miss_then_hit(self, tmp_path: Path):
        cache = QueryEnhancementCache(tmp_path / "cache")
        params = dict(
            corpus_id="c1", corpus_hash="h1", profile_hash="p1",
            query_norm="test query", mode="dict",
        )
        assert cache.get(**params) is None

        expansions = [{"q": "test", "source": "original", "intent": "", "notes": ""}]
        cache.put(**params, expansions=expansions)

        result = cache.get(**params)
        assert result is not None
        assert len(result) == 1
        assert result[0]["q"] == "test"

    def test_different_keys_no_collision(self, tmp_path: Path):
        cache = QueryEnhancementCache(tmp_path / "cache")
        cache.put(
            corpus_id="c1", corpus_hash="h1", profile_hash="p1",
            query_norm="query a", mode="dict",
            expansions=[{"q": "a"}],
        )
        cache.put(
            corpus_id="c1", corpus_hash="h1", profile_hash="p1",
            query_norm="query b", mode="dict",
            expansions=[{"q": "b"}],
        )
        a = cache.get(corpus_id="c1", corpus_hash="h1", profile_hash="p1", query_norm="query a", mode="dict")
        b = cache.get(corpus_id="c1", corpus_hash="h1", profile_hash="p1", query_norm="query b", mode="dict")
        assert a[0]["q"] == "a"
        assert b[0]["q"] == "b"

    def test_disabled_cache(self, tmp_path: Path):
        cache = QueryEnhancementCache(tmp_path / "cache", enabled=False)
        cache.put(
            corpus_id="c1", corpus_hash="h1", profile_hash="p1",
            query_norm="test", mode="dict",
            expansions=[{"q": "test"}],
        )
        assert cache.get(corpus_id="c1", corpus_hash="h1", profile_hash="p1", query_norm="test", mode="dict") is None

    def test_cache_key_determinism(self):
        k1 = _compute_cache_key("c", "h", "p", "q", "dict")
        k2 = _compute_cache_key("c", "h", "p", "q", "dict")
        assert k1 == k2

    def test_cache_key_differs_on_mode(self):
        k1 = _compute_cache_key("c", "h", "p", "q", "dict")
        k2 = _compute_cache_key("c", "h", "p", "q", "llm")
        assert k1 != k2


# --- Enhancer tests ---


class TestEnhancer:
    def test_mode_none_passthrough(self):
        p = _make_profile()
        result = enhance_queries(["how does initiative work?"], p, mode="none")
        assert len(result) == 1
        assert len(result[0]) == 1
        assert result[0][0]["source"] == "original"

    def test_dict_expansion_finds_synonyms(self):
        p = _make_profile()
        result = enhance_queries(["what does the referee decide?"], p, mode="dict")
        assert len(result) == 1
        group = result[0]
        assert group[0]["source"] == "original"
        variant_texts = [e["q"].lower() for e in group if e["source"] == "dict"]
        assert any("gm" in v or "dm" in v or "judge" in v for v in variant_texts)

    def test_dict_expansion_no_match(self):
        p = _make_profile()
        result = enhance_queries(["how does combat work?"], p, mode="dict")
        assert len(result) == 1
        assert len(result[0]) == 1
        assert result[0][0]["source"] == "original"

    def test_dict_expansion_deduplicates(self):
        p = _make_profile()
        result = enhance_queries(["the referee makes a saving throw"], p, mode="dict")
        group = result[0]
        q_texts_lower = [e["q"].strip().lower() for e in group]
        assert len(q_texts_lower) == len(set(q_texts_lower))

    def test_dict_expansion_respects_max(self):
        p = _make_profile()
        p.policies.max_expanded_queries = 2
        result = enhance_queries(["the referee makes a saving throw"], p, mode="dict")
        group = result[0]
        assert len(group) <= 3  # original + max 2 expansions

    def test_include_original_true(self):
        p = _make_profile()
        p.policies.include_original = True
        result = enhance_queries(["the referee decides"], p, mode="dict")
        assert result[0][0]["source"] == "original"

    def test_invalid_mode_raises(self):
        p = _make_profile()
        with pytest.raises(ValueError, match="Invalid enhancement mode"):
            enhance_queries(["test"], p, mode="bogus")

    def test_with_cache(self, tmp_path: Path):
        p = _make_profile()
        cache = QueryEnhancementCache(tmp_path / "cache")
        q = ["what does the referee decide?"]

        r1 = enhance_queries(q, p, mode="dict", cache=cache)
        r2 = enhance_queries(q, p, mode="dict", cache=cache)

        assert len(r1[0]) == len(r2[0])
        for a, b in zip(r1[0], r2[0]):
            assert a["q"] == b["q"]
            assert a["source"] == b["source"]

    def test_multiple_queries(self):
        p = _make_profile()
        result = enhance_queries(
            ["the referee decides", "make a saving throw"],
            p, mode="dict",
        )
        assert len(result) == 2
        assert all(len(group) >= 1 for group in result)


# --- Drift guard tests ---


class TestDriftGuard:
    def test_lexical_overlap_passes(self):
        from retrieval_lab.query_enhancement.enhancer import _passes_drift_guard
        p = _make_profile()
        p.policies.drift_guard.enabled = True
        p.policies.drift_guard.method = "lexical_overlap"
        p.policies.drift_guard.threshold = 0.2
        assert _passes_drift_guard("how does initiative work in combat", "how does initiative work", p) is True

    def test_lexical_overlap_rejects_drift(self):
        from retrieval_lab.query_enhancement.enhancer import _passes_drift_guard
        p = _make_profile()
        p.policies.drift_guard.enabled = True
        p.policies.drift_guard.method = "lexical_overlap"
        p.policies.drift_guard.threshold = 0.5
        assert _passes_drift_guard("completely unrelated banana topic", "how does initiative work", p) is False

    def test_disabled_guard_passes_everything(self):
        from retrieval_lab.query_enhancement.enhancer import _passes_drift_guard
        p = _make_profile()
        p.policies.drift_guard.enabled = False
        assert _passes_drift_guard("totally unrelated", "original query", p) is True


# --- LLM response parsing tests ---


class TestLLMResponseParsing:
    def test_parse_valid_response(self):
        from retrieval_lab.query_enhancement.enhancer import _parse_llm_response
        p = _make_profile()
        raw = '{"queries": [{"q": "alternative query", "intent": "facet:combat", "used_terms": ["initiative"], "notes": ""}]}'
        result = _parse_llm_response(raw, "original", p)
        assert len(result) == 1
        assert result[0]["q"] == "alternative query"
        assert result[0]["source"] == "llm"
        assert result[0]["intent"] == "facet:combat"

    def test_parse_invalid_json(self):
        from retrieval_lab.query_enhancement.enhancer import _parse_llm_response
        p = _make_profile()
        result = _parse_llm_response("not json at all", "original", p)
        assert result == []

    def test_parse_empty_queries(self):
        from retrieval_lab.query_enhancement.enhancer import _parse_llm_response
        p = _make_profile()
        result = _parse_llm_response('{"queries": []}', "original", p)
        assert result == []

    def test_parse_skips_oversized_query(self):
        from retrieval_lab.query_enhancement.enhancer import _parse_llm_response
        p = _make_profile()
        raw = '{"queries": [{"q": "' + "x" * 250 + '", "intent": "test"}]}'
        result = _parse_llm_response(raw, "original", p)
        assert len(result) == 0

    def test_parse_sorts_by_intent_then_q(self):
        from retrieval_lab.query_enhancement.enhancer import _parse_llm_response
        p = _make_profile()
        raw = '{"queries": [{"q": "beta", "intent": "z"}, {"q": "alpha", "intent": "a"}]}'
        result = _parse_llm_response(raw, "original", p)
        assert result[0]["intent"] == "a"
        assert result[1]["intent"] == "z"

    def test_drift_guard_filters_in_parse(self):
        from retrieval_lab.query_enhancement.enhancer import _parse_llm_response
        p = _make_profile()
        p.policies.drift_guard.enabled = True
        p.policies.drift_guard.method = "lexical_overlap"
        p.policies.drift_guard.threshold = 0.8
        raw = '{"queries": [{"q": "completely unrelated banana fish", "intent": "test"}]}'
        result = _parse_llm_response(raw, "how does initiative work", p)
        assert len(result) == 0


# --- Attribution metrics tests ---


class TestAttribution:
    def test_expansion_contribution(self):
        from retrieval_lab.query_enhancement.attribution import compute_enhancement_attribution
        ranked = [["a", "b", "gold1"], ["c", "d"]]
        baseline = [["a", "b"], ["c", "d"]]
        queries = [{"gold_unit_ids": ["gold1"]}, {"gold_unit_ids": ["gold2"]}]
        result = compute_enhancement_attribution(ranked, baseline, queries)
        assert result["gold_from_expansion"] == 1
        assert result["expansion_contribution_pct"] > 0

    def test_no_baseline(self):
        from retrieval_lab.query_enhancement.attribution import compute_enhancement_attribution
        ranked = [["a", "gold1"]]
        queries = [{"gold_unit_ids": ["gold1"]}]
        result = compute_enhancement_attribution(ranked, None, queries)
        assert result["gold_from_original_only"] == 1
        assert result["candidate_inflation_median"] is None

    def test_candidate_inflation(self):
        from retrieval_lab.query_enhancement.attribution import compute_enhancement_attribution
        ranked = [["a", "b", "c", "d"]]
        baseline = [["a", "b"]]
        queries = [{"gold_unit_ids": []}]
        result = compute_enhancement_attribution(ranked, baseline, queries)
        assert result["candidate_inflation_median"] == 2.0


# --- Multi-query fusion tests ---


class TestOnlyAddFusion:
    def test_only_add_locks_baseline_prefix_and_appends_novel(self):
        from retrieval_lab.query_enhancement.multi_query import fuse_only_add

        baseline_ranked = [["b1", "b2", "b3"]]
        baseline_scores = [[3.0, 2.0, 1.0]]
        variants = [[["b2", "v1", "v2"], ["v2", "v3"]]]

        fused_ids, fused_scores, debug = fuse_only_add(
            baseline_ranked_lists=baseline_ranked,
            baseline_score_lists=baseline_scores,
            variant_ranked_lists=variants,
            baseline_keep_n=2,
            admission_cutoff=4,
            append_score_band=1e-6,
        )

        assert fused_ids[0][:2] == ["b1", "b2"]
        assert fused_ids[0] == ["b1", "b2", "v1", "v2"]
        assert len(fused_scores[0]) == len(fused_ids[0])
        assert all(cid in set(fused_ids[0]) for cid in ["b1", "b2"])
        assert debug[0]["regression_guard_passed"] is True

        # Appended items must be below the baseline band.
        assert fused_scores[0][2] < min(fused_scores[0][:2])



# --- Decomposition tests ---


class TestDecomposition:
    def test_disabled_returns_empty(self):
        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=False)
        result = enhance_queries(["combat and spells and movement"], p, mode="decompose")
        assert len(result) == 1
        assert len(result[0]) == 1
        assert result[0][0]["source"] == "original"

    def test_should_decompose_long_query(self):
        from retrieval_lab.query_enhancement.enhancer import _should_decompose
        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="multi_hop_only")
        long_q = "how does " + " ".join(["word"] * 20)
        assert _should_decompose(long_q, p) is True

    def test_should_decompose_conjunction(self):
        from retrieval_lab.query_enhancement.enhancer import _should_decompose
        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="multi_hop_only")
        assert _should_decompose("how does initiative work and what actions can I take", p) is True

    def test_should_decompose_never(self):
        from retrieval_lab.query_enhancement.enhancer import _should_decompose
        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="never")
        assert _should_decompose("combat and spells", p) is False

    def test_should_decompose_always(self):
        from retrieval_lab.query_enhancement.enhancer import _should_decompose
        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="always")
        assert _should_decompose("simple query", p) is True

    def test_decompose_mode_integration(self):
        from retrieval_lab.query_enhancement import enhancer

        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="always")
        original = enhancer.decompose_query
        enhancer.decompose_query = lambda query, profile: [
            {"q": "initiative timing", "source": "decompose", "intent": "initiative", "notes": "test"},
            {"q": "combat action options", "source": "decompose", "intent": "actions", "notes": "test"},
        ]
        try:
            result = enhance_queries(
                ["how does initiative work and what actions can I take during combat"],
                p,
                mode="decompose",
            )
        finally:
            enhancer.decompose_query = original

        assert len(result) == 1
        group = result[0]
        assert group[0]["source"] == "original"
        decompose_entries = [e for e in group if e["source"] == "decompose"]
        assert len(decompose_entries) == 2

    def test_decompose_mode_is_not_capped_by_max_expanded_queries(self):
        from retrieval_lab.query_enhancement import enhancer

        p = _make_profile()
        p.policies.max_expanded_queries = 1
        p.decomposition = DecompositionConfig(enabled=True, when="always")
        original = enhancer.decompose_query
        enhancer.decompose_query = lambda query, profile: [
            {"q": "query one", "source": "decompose", "intent": "one", "notes": "test"},
            {"q": "query two", "source": "decompose", "intent": "two", "notes": "test"},
            {"q": "query three", "source": "decompose", "intent": "three", "notes": "test"},
        ]
        try:
            result = enhance_queries(["complex question"], p, mode="decompose")
        finally:
            enhancer.decompose_query = original

        assert len(result[0]) == 4  # original + all decomposition queries

    def test_multi_facet_template_triggers(self):
        from retrieval_lab.query_enhancement.enhancer import _should_decompose
        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="multi_hop_only")
        assert _should_decompose("how do combat spells interact with movement", p) is True


class TestResponsesDecomposition:
    def test_parse_decomposition_response(self):
        from retrieval_lab.query_enhancement.decomposition import parse_decomposition_response

        raw = json.dumps(
            {
                "retrieval_queries": [
                    {
                        "query": "pathfinder persistent damage recovery",
                        "must_include_terms": ["persistent damage"],
                    },
                    {
                        "query": "pathfinder flat check persistent damage",
                        "must_include_terms": ["flat check"],
                    },
                ]
            }
        )
        result = parse_decomposition_response(raw, original_query="pathfinder persistent damage flat check recovery")
        assert len(result) == 2
        assert result[0]["source"] == "decompose"
        assert result[0]["must_include_terms"] == ["persistent damage"]

    def test_parse_decomposition_response_rejects_out_of_query_terms(self):
        from retrieval_lab.query_enhancement.decomposition import parse_decomposition_response

        raw = json.dumps(
            {
                "retrieval_queries": [
                    {
                        "query": "persistent damage recovery",
                        "must_include_terms": ["persistent damage"],
                    },
                    {
                        "query": "persistent damage healing check",
                        "must_include_terms": ["healing"],
                    },
                ]
            }
        )
        result = parse_decomposition_response(raw, original_query="persistent damage recovery check")
        assert len(result) == 1
        assert result[0]["q"] == "persistent damage recovery"

    def test_decomposition_cache_signature_is_stable(self):
        from retrieval_lab.query_enhancement.decomposition import decomposition_cache_signature

        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="always")
        sig1 = decomposition_cache_signature(p)
        sig2 = decomposition_cache_signature(p)
        assert sig1 == sig2

    def test_decompose_query_uses_responses_api_schema(self):
        from retrieval_lab.query_enhancement import decomposition as module
        import sys
        import types

        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="always", model_id="gpt-5-mini")

        class _FakeResponse:
            output_text = ""
            output_parsed = {
                "retrieval_queries": [
                    {"query": "initiative work", "must_include_terms": ["initiative"]}
                ]
            }

        class _FakeResponses:
            def __init__(self):
                self.last_kwargs = None

            def create(self, **kwargs):
                self.last_kwargs = kwargs
                return _FakeResponse()

        fake_responses = _FakeResponses()

        class _FakeClient:
            def __init__(self):
                self.responses = fake_responses

        original_openai = sys.modules.get("openai")
        try:
            fake_module = types.SimpleNamespace(OpenAI=lambda: _FakeClient())
            sys.modules["openai"] = fake_module
            result = module.decompose_query("how does initiative work?", p)
        finally:
            if original_openai is None:
                sys.modules.pop("openai", None)
            else:
                sys.modules["openai"] = original_openai

        assert len(result) == 1
        assert fake_responses.last_kwargs["text"]["format"]["type"] == "json_schema"
        assert "temperature" not in fake_responses.last_kwargs

    def test_decompose_query_omits_temperature_for_gpt5_codex(self):
        from retrieval_lab.query_enhancement import decomposition as module
        import sys
        import types

        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="always", model_id="gpt-5.3-codex")

        class _FakeResponse:
            output_text = ""
            output_parsed = {
                "retrieval_queries": [
                    {"query": "initiative work", "must_include_terms": ["initiative"]}
                ]
            }

        class _FakeResponses:
            def __init__(self):
                self.last_kwargs = None

            def create(self, **kwargs):
                self.last_kwargs = kwargs
                return _FakeResponse()

        fake_responses = _FakeResponses()

        class _FakeClient:
            def __init__(self):
                self.responses = fake_responses

        original_openai = sys.modules.get("openai")
        try:
            fake_module = types.SimpleNamespace(OpenAI=lambda: _FakeClient())
            sys.modules["openai"] = fake_module
            result = module.decompose_query("how does initiative work?", p)
        finally:
            if original_openai is None:
                sys.modules.pop("openai", None)
            else:
                sys.modules["openai"] = original_openai

        assert len(result) == 1
        assert "temperature" not in fake_responses.last_kwargs

# --- Replay determinism tests ---


class TestReplayDeterminism:
    """Verify identical inputs produce identical outputs across multiple runs."""

    def test_dict_expansion_determinism(self):
        p = _make_profile()
        q = ["what does the referee decide about saving throws?"]
        r1 = enhance_queries(q, p, mode="dict")
        r2 = enhance_queries(q, p, mode="dict")
        assert len(r1[0]) == len(r2[0])
        for a, b in zip(r1[0], r2[0]):
            assert a["q"] == b["q"]
            assert a["source"] == b["source"]
            assert a["intent"] == b["intent"]

    def test_normalization_determinism(self):
        p = _make_profile()
        q = "How does Initiative   work with  d 20 rolls?"
        r1 = normalize_query(q, p)
        r2 = normalize_query(q, p)
        assert r1 == r2

    def test_cache_produces_identical_results(self, tmp_path: Path):
        p = _make_profile()
        cache = QueryEnhancementCache(tmp_path / "cache")
        q = ["the referee makes a saving throw"]
        r1 = enhance_queries(q, p, mode="dict", cache=cache)
        r2 = enhance_queries(q, p, mode="dict", cache=cache)
        r3 = enhance_queries(q, p, mode="dict", cache=cache)
        for a, b, c in zip(r1[0], r2[0], r3[0]):
            assert a["q"] == b["q"] == c["q"]

    def test_profile_hash_determinism(self):
        p1 = _make_profile()
        p2 = _make_profile()
        h1a = p1.compute_hash()
        h1b = p1.compute_hash()
        h2 = p2.compute_hash()
        assert h1a == h1b
        assert h1a == h2

    def test_decomposition_cache_signature_determinism(self):
        from retrieval_lab.query_enhancement.decomposition import decomposition_cache_signature

        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="always")
        r1 = decomposition_cache_signature(p)
        r2 = decomposition_cache_signature(p)
        assert r1 == r2


# --- Profile linting tests ---


class TestProfileLinting:
    def test_lint_version_required(self):
        p = _make_profile(profile_version="")
        errors = validate_profile(p)
        assert errors == []  # version empty is allowed but hash changes

    def test_lint_synonym_set_missing_canonical(self):
        p = _make_profile()
        p.synonym_sets = [SynonymSet(name="bad", canonical="", variants=["a"])]
        errors = validate_profile(p)
        assert any("canonical" in e for e in errors)

    def test_lint_synonym_set_empty_variants(self):
        p = _make_profile()
        p.synonym_sets = [SynonymSet(name="bad", canonical="ok", variants=[])]
        errors = validate_profile(p)
        assert any("variants" in e for e in errors)

    def test_lint_invalid_decomposition_when(self):
        p = _make_profile()
        p.decomposition = DecompositionConfig(enabled=True, when="invalid")
        errors = validate_profile(p)
        assert any("decomposition.when" in e for e in errors)

    def test_lint_invalid_stopword_policy(self):
        p = _make_profile()
        p.normalization.stopword_policy = "aggressive"
        errors = validate_profile(p)
        assert any("stopword_policy" in e for e in errors)


# --- CLI override tests ---


class TestCLIOverrides:
    def test_enhancement_mode_override(self):
        from argparse import Namespace
        from retrieval_lab.orchestration.cli import apply_cli_overrides
        from retrieval_lab.config import ExperimentConfig

        data = {
            "experiment_name": "test",
            "substrate_path": ".",
            "document_id": "test",
            "query_batches": [],
            "models": ["bm25"],
            "retrieval_mode": "bm25",
        }
        cfg = ExperimentConfig.from_dict(data)
        args = Namespace(
            experiment_name=None, substrate=None, batches=None, models=None,
            top_k="10", rrf_k=None, seed=None, output=None,
            mongo_uri=None, substrate_version=None, trust_remote_code=False,
            baseline_metrics=None, enhancement_mode="dict", enhancement_profile=None,
            merge_chunks=None, merge_max_chars=None, min_chars=None,
        )
        apply_cli_overrides(cfg, args)
        assert cfg.query_enhancement.enabled is True
        assert cfg.query_enhancement.mode == "dict"

    def test_enhancement_profile_override(self):
        from argparse import Namespace
        from retrieval_lab.orchestration.cli import apply_cli_overrides
        from retrieval_lab.config import ExperimentConfig

        data = {
            "experiment_name": "test",
            "substrate_path": ".",
            "document_id": "test",
            "query_batches": [],
            "models": ["bm25"],
            "retrieval_mode": "bm25",
        }
        cfg = ExperimentConfig.from_dict(data)
        args = Namespace(
            experiment_name=None, substrate=None, batches=None, models=None,
            top_k="10", rrf_k=None, seed=None, output=None,
            mongo_uri=None, substrate_version=None, trust_remote_code=False,
            baseline_metrics=None, enhancement_mode=None,
            enhancement_profile="/tmp/profile.json",
            merge_chunks=None, merge_max_chars=None, min_chars=None,
        )
        apply_cli_overrides(cfg, args)
        assert cfg.query_enhancement.enabled is True
        assert cfg.query_enhancement.profile_path == "/tmp/profile.json"


# --- Config integration tests ---


class TestConfigIntegration:
    def test_parse_query_enhancement_from_dict(self):
        from retrieval_lab.config import ExperimentConfig

        data = {
            "experiment_name": "test",
            "substrate_path": ".",
            "document_id": "test",
            "query_batches": [],
            "models": ["bm25"],
            "retrieval_mode": "bm25",
            "query_enhancement": {
                "enabled": False,
                "profile_path": "",
                "mode": "dict",
            },
        }
        cfg = ExperimentConfig.from_dict(data)
        assert cfg.query_enhancement.mode == "dict"
        assert cfg.query_enhancement.enabled is False

    def test_default_query_enhancement(self):
        from retrieval_lab.config import ExperimentConfig

        data = {
            "experiment_name": "test",
            "substrate_path": ".",
            "document_id": "test",
            "query_batches": [],
            "models": ["bm25"],
            "retrieval_mode": "bm25",
        }
        cfg = ExperimentConfig.from_dict(data)
        assert cfg.query_enhancement.enabled is False
        assert cfg.query_enhancement.mode == "none"

    def test_read_query_enhancement_config(self):
        from retrieval_lab.config import ExperimentConfig
        from retrieval_lab.orchestration.config_access import read_query_enhancement_config

        data = {
            "experiment_name": "test",
            "substrate_path": ".",
            "document_id": "test",
            "query_batches": [],
            "models": [],
            "retrieval_mode": "bm25",
            "query_enhancement": {"enabled": True, "profile_path": "/tmp/p.json", "mode": "llm+dict"},
        }
        cfg = ExperimentConfig.from_dict(data)
        qe = read_query_enhancement_config(cfg)
        assert qe.enabled is True
        assert qe.mode == "llm+dict"
        assert qe.profile_path == "/tmp/p.json"
        assert qe.fusion_mode == "only_add"
        assert qe.only_add.baseline_keep_n == 20
        assert qe.only_add.variant_k_per_query == 20
        assert qe.only_add.admission_cutoff == 50
        assert qe.only_add.prefix_lock_n == 20
        assert qe.only_add.tail_rerank == "none"
        assert qe.only_add.tail_rerank_window == 50
