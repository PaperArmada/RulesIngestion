"""Tests for mention_type_inference module."""
import pytest
from enrichment.mention_type_inference import (
    infer_mention_type_mappings,
    get_entity_type_to_mention_type,
    singularize,
    TAG_TO_MENTION_TYPE,
)


class TestSingularize:
    """Test singularization of entity type names."""
    
    def test_classes_to_class(self):
        assert singularize("classes") == "class"
    
    def test_ancestries_to_ancestry(self):
        assert singularize("ancestries") == "ancestry"
    
    def test_feats_to_feat(self):
        assert singularize("feats") == "feat"
    
    def test_spells_to_spell(self):
        assert singularize("spells") == "spell"
    
    def test_conditions_to_condition(self):
        assert singularize("conditions") == "condition"
    
    def test_species_stays_species(self):
        """Species is already singular."""
        assert singularize("species") == "species"
    
    def test_already_singular(self):
        assert singularize("feat") == "feat"
        assert singularize("class") == "class"
    
    def test_case_insensitive(self):
        assert singularize("CLASSES") == "class"
        assert singularize("Ancestries") == "ancestry"


class TestInferMentionTypeMappings:
    """Test inference from chunk metadata."""
    
    def test_infer_from_tags(self):
        """Tags should map to mention types."""
        chunks = [
            {"tags": ["ancestries", "feats"]},
            {"tags": ["classes", "spells"]},
            {"tags": ["conditions"]},
        ]
        
        mappings = infer_mention_type_mappings(chunks, merge_with_defaults=False)
        
        assert "ancestry" in mappings["role"]
        assert "class" in mappings["role"]
        assert "feat" in mappings["mechanic"]
        assert "spell" in mappings["mechanic"]
        assert "condition" in mappings["condition"]
    
    def test_infer_from_content_kind(self):
        """Content kind should also contribute to mappings."""
        chunks = [
            {"content_kind": "feat", "tags": []},
            {"content_kind": "spell", "tags": []},
        ]
        
        mappings = infer_mention_type_mappings(chunks, merge_with_defaults=False)
        
        assert "feat" in mappings["mechanic"]
        assert "spell" in mappings["mechanic"]
    
    def test_empty_chunks(self):
        """Empty chunks should return empty mappings (without defaults)."""
        mappings = infer_mention_type_mappings([], merge_with_defaults=False)
        assert mappings == {}
    
    def test_merge_with_defaults(self):
        """Default entity types should be merged when requested."""
        chunks = [{"tags": ["ancestries"]}]
        
        mappings = infer_mention_type_mappings(chunks, merge_with_defaults=True)
        
        # Should have ancestry from chunks AND archetype from defaults
        assert "ancestry" in mappings["role"]
        assert "archetype" in mappings["role"]
        assert "background" in mappings["role"]
    
    def test_handles_dict_format(self):
        """Should handle both dict with 'chunks' key and list of chunks."""
        data = {"chunks": [{"tags": ["feats"]}]}
        
        mappings = infer_mention_type_mappings(data, merge_with_defaults=False)
        
        assert "feat" in mappings["mechanic"]
    
    def test_handles_unknown_tags(self):
        """Unknown tags should not cause errors."""
        chunks = [
            {"tags": ["ancestries", "combat", "unknown_tag"]},
        ]
        
        mappings = infer_mention_type_mappings(chunks, merge_with_defaults=False)
        
        assert "ancestry" in mappings["role"]
        # Unknown tags should not appear in mappings
        assert "combat" not in mappings.get("role", set())
        assert "combat" not in mappings.get("mechanic", set())
    
    def test_normalization(self):
        """Tags should be normalized to singular, lowercase."""
        chunks = [
            {"tags": ["ANCESTRIES", "Classes", "FEATS"]},
        ]
        
        mappings = infer_mention_type_mappings(chunks, merge_with_defaults=False)
        
        # All should be singular, lowercase
        assert "ancestry" in mappings["role"]
        assert "class" in mappings["role"]
        assert "feat" in mappings["mechanic"]
        # Plurals should not be present
        assert "ancestries" not in mappings.get("role", set())


class TestGetEntityTypeToMentionType:
    """Test inverted mapping lookup."""
    
    def test_invert_mapping(self):
        """Should invert mention_type -> entity_types to entity_type -> mention_type."""
        mappings = {
            "role": {"ancestry", "class"},
            "mechanic": {"feat", "spell"},
        }
        
        inverted = get_entity_type_to_mention_type(mappings)
        
        assert inverted["ancestry"] == "role"
        assert inverted["class"] == "role"
        assert inverted["feat"] == "mechanic"
        assert inverted["spell"] == "mechanic"
    
    def test_empty_mappings(self):
        """Empty mappings should return empty dict."""
        assert get_entity_type_to_mention_type({}) == {}


class TestSeedVocabulary:
    """Validate the seed vocabulary coverage."""
    
    def test_role_types_covered(self):
        """Common role-related entity types should be covered."""
        role_types = ["ancestry", "ancestries", "class", "classes", "race", "races",
                      "archetype", "background", "heritage", "subclass"]
        
        for et in role_types:
            assert et in TAG_TO_MENTION_TYPE, f"{et} not in seed vocabulary"
            assert TAG_TO_MENTION_TYPE[et] == "role"
    
    def test_mechanic_types_covered(self):
        """Common mechanic-related entity types should be covered."""
        mechanic_types = ["feat", "feats", "spell", "spells", "ability", "abilities",
                         "action", "actions", "skill", "skills", "item", "equipment"]
        
        for et in mechanic_types:
            assert et in TAG_TO_MENTION_TYPE, f"{et} not in seed vocabulary"
            assert TAG_TO_MENTION_TYPE[et] == "mechanic"
    
    def test_condition_types_covered(self):
        """Common condition-related entity types should be covered."""
        condition_types = ["condition", "conditions", "status"]
        
        for et in condition_types:
            assert et in TAG_TO_MENTION_TYPE, f"{et} not in seed vocabulary"
            assert TAG_TO_MENTION_TYPE[et] == "condition"


class TestIntegrationWithRealData:
    """Integration tests with actual enriched data."""
    
    @pytest.fixture
    def playercore_path(self):
        from pathlib import Path
        path = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json")
        if not path.exists():
            pytest.skip("PlayerCore data not available")
        return path
    
    def test_infer_from_playercore(self, playercore_path):
        """Should successfully infer mappings from real PlayerCore data."""
        from enrichment.mention_type_inference import infer_mention_type_mappings_from_file
        
        mappings = infer_mention_type_mappings_from_file(playercore_path, merge_with_defaults=False)
        
        # Should have discovered key entity types
        assert "ancestry" in mappings.get("role", set())
        assert "class" in mappings.get("role", set())
        assert "feat" in mappings.get("mechanic", set())
        assert "spell" in mappings.get("mechanic", set())
        assert "condition" in mappings.get("condition", set())
    
    def test_execution_is_fast(self, playercore_path):
        """Inference should complete quickly (< 2 seconds)."""
        import time
        from enrichment.mention_type_inference import infer_mention_type_mappings_from_file
        
        start = time.time()
        mappings = infer_mention_type_mappings_from_file(playercore_path)
        elapsed = time.time() - start
        
        assert elapsed < 2.0, f"Inference took {elapsed:.2f}s, expected < 2s"
