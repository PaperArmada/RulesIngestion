"""Tests for mention extraction module."""
import json
import pytest
from unittest.mock import MagicMock

from enrichment.mentions import Mention, MentionType, extract_mentions
from enrichment.vocabulary_loader import (
    extract_role_mentions,
    load_vocabulary_from_graph,
    load_mention_type_mappings,
    DEFAULT_MENTION_TYPE_MAPPINGS,
)
from enrichment.clause_units import ClauseUnit


class TestMentionModel:
    """Test Mention dataclass."""
    
    def test_mention_to_dict(self):
        """Mention should serialize to dict."""
        mention = Mention(
            mention_id="clause_1::mention_0",
            surface="DC 15",
            normalized="dc:15",
            mention_type=MentionType.NUMERIC_TERM,
            clause_id="clause_1",
            span_offsets=(10, 15),
        )
        d = mention.to_dict()
        assert d["surface"] == "DC 15"
        assert d["mention_type"] == "numeric_term"
        assert d["span_offsets"] == [10, 15]
    
    def test_mention_default_values(self):
        """Mention should have correct default values."""
        mention = Mention(
            mention_id="test::mention_0",
            surface="test",
            normalized="test",
            mention_type=MentionType.UNKNOWN,
            clause_id="test",
            span_offsets=(0, 4),
        )
        assert mention.confidence == 1.0
        assert mention.extraction_method == "regex"


class TestMentionExtraction:
    """Test mention extraction patterns."""
    
    def _make_clause(self, text: str, clause_id: str = "test::clause_0") -> ClauseUnit:
        return ClauseUnit(
            clause_id=clause_id,
            text=text,
            parent_chunk_id="test",
            order_in_chunk=0,
            char_offsets=(0, len(text)),
            page=1,
        )
    
    # Level mentions
    def test_level_numeric(self):
        """'Level 9' should extract as level mention."""
        clause = self._make_clause("At Level 9, you gain this feat.")
        mentions = extract_mentions(clause)
        level_mentions = [m for m in mentions if m.mention_type == MentionType.LEVEL]
        assert len(level_mentions) == 1
        assert level_mentions[0].normalized == "level:9"
        
    def test_nth_level_spell(self):
        """'5th-level spell' should extract level."""
        clause = self._make_clause("Cast a 5th-level spell.")
        mentions = extract_mentions(clause)
        level_mentions = [m for m in mentions if m.mention_type == MentionType.LEVEL]
        assert len(level_mentions) == 1
        assert level_mentions[0].normalized == "level:5"
        
    def test_at_nth_level(self):
        """'at 3rd level' should extract level."""
        clause = self._make_clause("You gain this ability at 3rd level.")
        mentions = extract_mentions(clause)
        level_mentions = [m for m in mentions if m.mention_type == MentionType.LEVEL]
        assert len(level_mentions) == 1
        assert level_mentions[0].normalized == "level:3"
    
    def test_multiple_level_formats(self):
        """Different level formats should all extract."""
        clause = self._make_clause("At Level 5, cast a 3rd-level spell at 7th level.")
        mentions = extract_mentions(clause)
        level_mentions = [m for m in mentions if m.mention_type == MentionType.LEVEL]
        assert len(level_mentions) == 3
    
    # Trait mentions
    def test_action_icon(self):
        """Action icons should extract as traits."""
        clause = self._make_clause("Strike [two-actions] Make a melee attack.")
        mentions = extract_mentions(clause)
        trait_mentions = [m for m in mentions if m.mention_type == MentionType.TRAIT]
        assert len(trait_mentions) == 1
        assert trait_mentions[0].surface == "[two-actions]"
        
    def test_reaction_trait(self):
        """Reaction should extract."""
        clause = self._make_clause("Sidestep [reaction] When a creature misses.")
        mentions = extract_mentions(clause)
        trait_mentions = [m for m in mentions if m.mention_type == MentionType.TRAIT]
        assert len(trait_mentions) == 1
        assert "reaction" in trait_mentions[0].normalized
    
    def test_one_action(self):
        """One-action should extract."""
        clause = self._make_clause("Strike [one-action] Attack a target.")
        mentions = extract_mentions(clause)
        trait_mentions = [m for m in mentions if m.mention_type == MentionType.TRAIT]
        assert len(trait_mentions) == 1
        assert "one-action" in trait_mentions[0].normalized
    
    def test_three_actions(self):
        """Three-actions should extract."""
        clause = self._make_clause("Meteor Swarm [three-actions] Rain fire.")
        mentions = extract_mentions(clause)
        trait_mentions = [m for m in mentions if m.mention_type == MentionType.TRAIT]
        assert len(trait_mentions) == 1
        assert "three-actions" in trait_mentions[0].normalized
    
    # Numeric terms
    def test_dc_extraction(self):
        """DC values should extract."""
        clause = self._make_clause("Make a DC 15 Reflex save.")
        mentions = extract_mentions(clause)
        dc_mentions = [m for m in mentions if m.mention_type == MentionType.NUMERIC_TERM]
        assert len(dc_mentions) == 1
        assert dc_mentions[0].normalized == "dc:15"
        
    def test_multiple_numeric_terms(self):
        """Multiple DC/CR/AC values in one clause."""
        clause = self._make_clause("DC 20 against AC 18 for CR 5 creatures.")
        mentions = extract_mentions(clause)
        numeric = [m for m in mentions if m.mention_type == MentionType.NUMERIC_TERM]
        assert len(numeric) == 3
    
    def test_ac_extraction(self):
        """AC values should extract."""
        clause = self._make_clause("The creature has AC 18.")
        mentions = extract_mentions(clause)
        ac_mentions = [m for m in mentions if m.mention_type == MentionType.NUMERIC_TERM]
        assert len(ac_mentions) == 1
        assert ac_mentions[0].normalized == "ac:18"
    
    # Outcome mentions
    def test_success_outcomes(self):
        """Success/failure outcomes should extract."""
        clause = self._make_clause("On a critical success, deal double damage. On failure, nothing happens.")
        mentions = extract_mentions(clause)
        outcomes = [m for m in mentions if m.mention_type == MentionType.OUTCOME]
        assert len(outcomes) == 2
        
    def test_critical_failure(self):
        """Critical failure should extract."""
        clause = self._make_clause("Critical Failure: You fall prone.")
        mentions = extract_mentions(clause)
        outcomes = [m for m in mentions if m.mention_type == MentionType.OUTCOME]
        assert len(outcomes) == 1
        assert "critical_failure" in outcomes[0].normalized.lower()
    
    def test_all_four_outcomes(self):
        """All four degree-of-success outcomes should extract."""
        clause = self._make_clause("Critical Success: Extra. Success: Normal. Failure: Miss. Critical Failure: Worse.")
        mentions = extract_mentions(clause)
        outcomes = [m for m in mentions if m.mention_type == MentionType.OUTCOME]
        assert len(outcomes) == 4
    
    # Condition mentions
    def test_condition_extraction(self):
        """Conditions should extract."""
        clause = self._make_clause("The target is stunned 1 and prone.")
        mentions = extract_mentions(clause)
        conditions = [m for m in mentions if m.mention_type == MentionType.CONDITION]
        assert len(conditions) == 2
        normalized = {m.normalized for m in conditions}
        assert "condition:stunned" in normalized
        assert "condition:prone" in normalized
        
    def test_flat_footed(self):
        """Hyphenated conditions should extract."""
        clause = self._make_clause("You are flat-footed to that creature.")
        mentions = extract_mentions(clause)
        conditions = [m for m in mentions if m.mention_type == MentionType.CONDITION]
        assert len(conditions) == 1
        assert "flat_footed" in conditions[0].normalized or "flat-footed" in conditions[0].normalized
    
    def test_frightened_condition(self):
        """Frightened should extract."""
        clause = self._make_clause("The creature becomes frightened 2.")
        mentions = extract_mentions(clause)
        conditions = [m for m in mentions if m.mention_type == MentionType.CONDITION]
        assert len(conditions) == 1
        assert "frightened" in conditions[0].normalized
    
    def test_invisible_hidden(self):
        """Stealth conditions should extract."""
        clause = self._make_clause("You become invisible and hidden from enemies.")
        mentions = extract_mentions(clause)
        conditions = [m for m in mentions if m.mention_type == MentionType.CONDITION]
        assert len(conditions) == 2
    
    # Entity type mentions
    def test_creature_entity(self):
        """Creature mentions should extract."""
        clause = self._make_clause("When a creature misses you with an attack.")
        mentions = extract_mentions(clause)
        entities = [m for m in mentions if m.mention_type == MentionType.ENTITY_TYPE]
        assert len(entities) == 1
        assert "creature" in entities[0].normalized
        
    def test_object_entity(self):
        """Object mentions should extract."""
        clause = self._make_clause("Target an object within 30 feet.")
        mentions = extract_mentions(clause)
        entities = [m for m in mentions if m.mention_type == MentionType.ENTITY_TYPE]
        # Both "Target" and "object" are entity types
        assert len(entities) == 2
        normalized = {m.normalized for m in entities}
        assert "entity:object" in normalized
        assert "entity:target" in normalized
    
    def test_ally_enemy_entities(self):
        """Ally and enemy should extract as entity types."""
        clause = self._make_clause("Allies gain a bonus. Enemies take damage.")
        mentions = extract_mentions(clause)
        entities = [m for m in mentions if m.mention_type == MentionType.ENTITY_TYPE]
        assert len(entities) == 2
    
    # Span correctness
    def test_span_offsets_correct(self):
        """Span offsets should allow extraction from clause text."""
        clause = self._make_clause("Make a DC 15 save.")
        mentions = extract_mentions(clause)
        for mention in mentions:
            start, end = mention.span_offsets
            assert clause.text[start:end] == mention.surface
    
    def test_span_offsets_multiple(self):
        """All spans should be extractable from original text."""
        clause = self._make_clause("On failure, you are prone and stunned.")
        mentions = extract_mentions(clause)
        for mention in mentions:
            start, end = mention.span_offsets
            assert clause.text[start:end] == mention.surface
    
    # Deduplication
    def test_no_duplicate_spans(self):
        """Overlapping matches should deduplicate."""
        clause = self._make_clause("Prone creature is prone.")
        mentions = extract_mentions(clause)
        # Should have 2 prone mentions (two occurrences) + 1 creature
        condition_count = sum(1 for m in mentions if m.mention_type == MentionType.CONDITION)
        assert condition_count == 2  # Two separate "prone" occurrences
    
    # Determinism
    def test_deterministic_extraction(self):
        """Same clause should produce identical mentions."""
        clause = self._make_clause("Level 5 Solarian with DC 15 check.")
        m1 = extract_mentions(clause)
        m2 = extract_mentions(clause)
        assert [m.to_dict() for m in m1] == [m.to_dict() for m in m2]
    
    # Empty/edge cases
    def test_empty_clause(self):
        """Empty clause should return empty list."""
        clause = self._make_clause("")
        mentions = extract_mentions(clause)
        assert mentions == []
        
    def test_whitespace_only_clause(self):
        """Whitespace-only clause should return empty list."""
        clause = self._make_clause("   \n\t  ")
        mentions = extract_mentions(clause)
        assert mentions == []
        
    def test_no_matches(self):
        """Clause with no patterns should return empty list."""
        clause = self._make_clause("This is plain narrative text.")
        mentions = extract_mentions(clause)
        # May have some entity mentions but no specific game terms
        assert isinstance(mentions, list)


class TestRoleMentions:
    """Test role-specific vocabulary extraction."""
    
    # Test vocabulary - loaded from graph in production
    TEST_ROLE_VOCABULARY = {"lashunta", "solarian", "human", "android"}
    
    def _make_clause(self, text: str) -> ClauseUnit:
        return ClauseUnit(
            clause_id="test::clause_0",
            text=text,
            parent_chunk_id="test",
            order_in_chunk=0,
            char_offsets=(0, len(text)),
            page=1,
        )
    
    def test_ancestry_extraction(self):
        """Ancestry names should extract as roles."""
        clause = self._make_clause("A Lashunta character gains telepathy.")
        mentions = extract_role_mentions(clause, self.TEST_ROLE_VOCABULARY)
        assert len(mentions) == 1
        assert mentions[0].normalized == "role:lashunta"
        
    def test_class_extraction(self):
        """Class names should extract as roles."""
        clause = self._make_clause("As a Solarian, you channel stellar forces.")
        mentions = extract_role_mentions(clause, self.TEST_ROLE_VOCABULARY)
        assert len(mentions) == 1
        assert mentions[0].normalized == "role:solarian"
        
    def test_multiple_roles(self):
        """Multiple roles in one clause should all extract."""
        clause = self._make_clause("A Lashunta Solarian can combine telepathy with photon mode.")
        mentions = extract_role_mentions(clause, self.TEST_ROLE_VOCABULARY)
        assert len(mentions) == 2
        normalized = {m.normalized for m in mentions}
        assert "role:lashunta" in normalized
        assert "role:solarian" in normalized
        
    def test_case_insensitive(self):
        """Role matching should be case insensitive."""
        clause = self._make_clause("SOLARIAN and solarian and Solarian")
        mentions = extract_role_mentions(clause, self.TEST_ROLE_VOCABULARY)
        assert len(mentions) == 3
        
    def test_word_boundary_respected(self):
        """Partial matches should not extract."""
        clause = self._make_clause("The humanoid creature attacks.")
        mentions = extract_role_mentions(clause, self.TEST_ROLE_VOCABULARY)
        # "human" should not match inside "humanoid"
        role_mentions = [m for m in mentions if "human" in m.normalized]
        assert len(role_mentions) == 0
    
    def test_vocabulary_extraction_method(self):
        """Role mentions should have vocabulary extraction method."""
        clause = self._make_clause("A Lashunta gains telepathy.")
        mentions = extract_role_mentions(clause, self.TEST_ROLE_VOCABULARY)
        assert len(mentions) == 1
        assert mentions[0].extraction_method == "vocabulary"


class TestVocabularyLoading:
    """Test config-driven vocabulary loading."""
    
    def test_load_from_graph_with_default_mapping(self, tmp_path):
        """Vocabulary should load from graph nodes using default mapping."""
        # Create minimal graph
        graph = {
            "nodes": [
                {"type": "Ancestry", "name": "Lashunta", "normalized_name": "lashunta"},
                {"type": "Class", "name": "Solarian", "normalized_name": "solarian"},
                {"type": "Feat", "name": "Guarded Thoughts", "normalized_name": "guarded thoughts"},
                {"type": "Condition", "name": "Stunned", "normalized_name": "stunned"},
            ]
        }
        graph_path = tmp_path / "test.graph.json"
        with open(graph_path, "w") as f:
            json.dump(graph, f)
        
        # Uses default mapping (ancestry, class -> role; feat -> mechanic; condition -> condition)
        vocabularies = load_vocabulary_from_graph(graph_path)
        
        assert "lashunta" in vocabularies["role"]
        assert "solarian" in vocabularies["role"]
        assert "guarded thoughts" in vocabularies["mechanic"]
        assert "stunned" in vocabularies["condition"]
    
    def test_load_from_graph_with_custom_mapping(self, tmp_path):
        """Custom mapping should be respected."""
        # Graph with D&D 5e style entity types
        graph = {
            "nodes": [
                {"type": "Race", "name": "Elf", "normalized_name": "elf"},
                {"type": "Class", "name": "Fighter", "normalized_name": "fighter"},
            ]
        }
        graph_path = tmp_path / "dnd.graph.json"
        with open(graph_path, "w") as f:
            json.dump(graph, f)
        
        # Custom mapping that includes "race"
        custom_mapping = {
            "role": {"race", "class"},
            "mechanic": {"feat", "spell"},
        }
        
        vocabularies = load_vocabulary_from_graph(graph_path, custom_mapping)
        
        assert "elf" in vocabularies["role"]  # "race" mapped to "role"
        assert "fighter" in vocabularies["role"]
    
    def test_load_mention_type_mappings_from_config(self):
        """Mappings should load from config if present."""
        # Mock config with custom mappings
        config = MagicMock()
        config.deterministic_rules = {
            "mention_type_mappings": {
                "role": ["warrior", "wizard", "thief", "cleric"],  # DCC-style
                "mechanic": ["deed", "spell", "skill"],
            }
        }
        
        mappings = load_mention_type_mappings(config=config)
        
        assert "warrior" in mappings["role"]
        assert "deed" in mappings["mechanic"]
    
    def test_load_mention_type_mappings_fallback_to_default(self):
        """Without config, should use default cross-system mapping."""
        mappings = load_mention_type_mappings(config=None)
        
        # Should have default keys
        assert "role" in mappings
        assert "mechanic" in mappings
        assert "condition" in mappings
        
        # Should include cross-system entity types
        assert "ancestry" in mappings["role"]  # SF2e, PF2e
        assert "race" in mappings["role"]      # D&D 5e
        assert "class" in mappings["role"]     # Universal
    
    def test_empty_graph_returns_empty_vocabularies(self, tmp_path):
        """Empty graph should return empty vocabulary sets."""
        graph = {"nodes": []}
        graph_path = tmp_path / "empty.graph.json"
        with open(graph_path, "w") as f:
            json.dump(graph, f)
        
        vocabularies = load_vocabulary_from_graph(graph_path)
        
        assert vocabularies["role"] == set()
        assert vocabularies["mechanic"] == set()
    
    def test_graph_with_missing_names(self, tmp_path):
        """Nodes without names should be skipped."""
        graph = {
            "nodes": [
                {"type": "Ancestry", "name": "Lashunta", "normalized_name": "lashunta"},
                {"type": "Ancestry"},  # No name
                {"type": "Class", "name": "", "normalized_name": ""},  # Empty name
            ]
        }
        graph_path = tmp_path / "partial.graph.json"
        with open(graph_path, "w") as f:
            json.dump(graph, f)
        
        vocabularies = load_vocabulary_from_graph(graph_path)
        
        assert "lashunta" in vocabularies["role"]
        assert "" not in vocabularies["role"]
        assert len(vocabularies["role"]) == 1


class TestMentionIntegration:
    """Integration tests with real clause data."""
    
    @pytest.fixture
    def sample_clauses(self):
        """Load real clauses from PlayerCore."""
        from enrichment.clause_units import extract_clause_units
        from enrichment.chunks import EnrichedChunk
        
        path = "Rules/StarFinder2e/PlayerCore/outputs/runs/latest/enriched/merged.enriched.json"
        try:
            with open(path) as f:
                data = json.load(f)
        except FileNotFoundError:
            pytest.skip("PlayerCore data not available")
            
        clauses = []
        for chunk_dict in data.get("chunks", [])[:50]:
            chunk = EnrichedChunk(**chunk_dict)
            clauses.extend(extract_clause_units(chunk))
        return clauses
    
    def test_real_clauses_produce_mentions(self, sample_clauses):
        """Real clauses should produce some mentions."""
        all_mentions = []
        for clause in sample_clauses:
            all_mentions.extend(extract_mentions(clause))
        assert len(all_mentions) > 0
        
    def test_mention_types_distributed(self, sample_clauses):
        """Multiple mention types should appear in real data."""
        all_mentions = []
        for clause in sample_clauses:
            all_mentions.extend(extract_mentions(clause))
        
        types_found = {m.mention_type for m in all_mentions}
        # Should find at least 3 different types
        assert len(types_found) >= 3


class TestNormalization:
    """Test mention normalization."""
    
    def _make_clause(self, text: str) -> ClauseUnit:
        return ClauseUnit(
            clause_id="test::clause_0",
            text=text,
            parent_chunk_id="test",
            order_in_chunk=0,
            char_offsets=(0, len(text)),
            page=1,
        )
    
    def test_level_normalization(self):
        """Levels should normalize to level:N format."""
        clause = self._make_clause("At Level 9, gain a feat.")
        mentions = extract_mentions(clause)
        level_mentions = [m for m in mentions if m.mention_type == MentionType.LEVEL]
        assert level_mentions[0].normalized == "level:9"
    
    def test_dc_normalization(self):
        """DC values should normalize to dc:N format."""
        clause = self._make_clause("Make a DC 15 save.")
        mentions = extract_mentions(clause)
        dc_mentions = [m for m in mentions if m.mention_type == MentionType.NUMERIC_TERM]
        assert dc_mentions[0].normalized == "dc:15"
    
    def test_condition_normalization(self):
        """Conditions should normalize to condition:name format."""
        clause = self._make_clause("You are stunned.")
        mentions = extract_mentions(clause)
        cond_mentions = [m for m in mentions if m.mention_type == MentionType.CONDITION]
        assert cond_mentions[0].normalized == "condition:stunned"
    
    def test_outcome_normalization(self):
        """Outcomes should normalize with underscores."""
        clause = self._make_clause("On a critical failure, take damage.")
        mentions = extract_mentions(clause)
        outcome_mentions = [m for m in mentions if m.mention_type == MentionType.OUTCOME]
        assert outcome_mentions[0].normalized == "outcome:critical_failure"
    
    def test_trait_normalization(self):
        """Traits should normalize to trait:name format."""
        clause = self._make_clause("Strike [reaction] Counter attack.")
        mentions = extract_mentions(clause)
        trait_mentions = [m for m in mentions if m.mention_type == MentionType.TRAIT]
        assert trait_mentions[0].normalized == "trait:reaction"
