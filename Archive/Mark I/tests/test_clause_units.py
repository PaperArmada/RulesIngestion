"""Tests for ClauseUnit extraction from enriched chunks."""

import pytest
from enrichment.clause_units import ClauseUnit, extract_clause_units
from enrichment.chunks import EnrichedChunk


class TestClauseUnitModel:
    """Test ClauseUnit dataclass structure."""

    def test_clause_unit_to_dict(self):
        """ClauseUnit should serialize to dictionary."""
        clause = ClauseUnit(
            clause_id="chunk-1::clause_0",
            text="The warrior attacks.",
            parent_chunk_id="chunk-1",
            order_in_chunk=0,
            char_offsets=(0, 20),
            page=1,
            section_path=["Combat"],
        )
        result = clause.to_dict()
        assert result["clause_id"] == "chunk-1::clause_0"
        assert result["text"] == "The warrior attacks."
        assert result["parent_chunk_id"] == "chunk-1"
        assert result["order_in_chunk"] == 0
        assert result["char_offsets"] == [0, 20]
        assert result["page"] == 1
        assert result["section_path"] == ["Combat"]


class TestClauseUnitExtraction:
    """Test clause extraction from chunks."""

    def _make_chunk(self, chunk_id: str, text: str, page: int = 1, **kwargs) -> EnrichedChunk:
        """Helper to create test chunks with minimal boilerplate."""
        return EnrichedChunk(
            id=chunk_id,
            block_type=kwargs.get("block_type", "Text"),
            text=text,
            page=page,
            section_path=kwargs.get("section_path", []),
            bbox=kwargs.get("bbox", []),
            section_hierarchy=kwargs.get("section_hierarchy", {}),
            content_kind=kwargs.get("content_kind", "narrative"),
            is_rule_bearing=kwargs.get("is_rule_bearing", False),
            tags=kwargs.get("tags", []),
            traits=kwargs.get("traits", []),
        )

    def test_simple_two_sentences(self):
        """Two sentences should produce two clauses."""
        chunk = self._make_chunk(
            "test-chunk-1",
            "The warrior attacks. The wizard casts a spell.",
            section_path=["Combat"],
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 2
        assert clauses[0].text == "The warrior attacks."
        assert clauses[1].text == "The wizard casts a spell."

    def test_offsets_are_correct(self):
        """Char offsets should allow reconstruction."""
        chunk = self._make_chunk(
            "test-chunk-2",
            "First sentence. Second sentence.",
        )
        clauses = extract_clause_units(chunk)
        for clause in clauses:
            start, end = clause.char_offsets
            assert chunk.text[start:end] == clause.text

    def test_dice_notation_not_split(self):
        """Dice notation should not cause false splits."""
        chunk = self._make_chunk(
            "test-chunk-3",
            "Deal 1d6 + 5 damage. The target is prone.",
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 2
        assert "1d6 + 5" in clauses[0].text

    def test_dc_not_split(self):
        """DC notation should not cause false splits."""
        chunk = self._make_chunk(
            "test-chunk-4",
            "Make a DC 15 Fortitude save. On a success, you resist the effect.",
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 2
        assert "DC 15" in clauses[0].text

    def test_cr_not_split(self):
        """CR notation should not cause false splits."""
        chunk = self._make_chunk(
            "test-chunk-5",
            "This creature is CR 5. It has multiple abilities.",
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 2
        assert "CR 5" in clauses[0].text

    def test_numbered_list_preserved(self):
        """Numbered lists should not falsely split on period."""
        chunk = self._make_chunk(
            "test-chunk-6",
            "Requirements: 1. Be trained in Athletics. 2. Have a free hand.",
        )
        clauses = extract_clause_units(chunk)
        # Should produce clauses, but not split on "1." or "2." alone
        # The entire requirement text should be preserved
        all_text = " ".join(c.text for c in clauses)
        assert "1." in all_text
        assert "2." in all_text

    def test_clause_ids_unique(self):
        """Each clause should have a unique ID."""
        chunk = self._make_chunk(
            "test-chunk-7",
            "One sentence here. Two sentences here. Three sentences here.",
        )
        clauses = extract_clause_units(chunk)
        ids = [c.clause_id for c in clauses]
        assert len(ids) == len(set(ids))

    def test_clause_ids_follow_pattern(self):
        """Clause IDs should follow {chunk_id}::clause_{order} pattern."""
        chunk = self._make_chunk(
            "test-chunk-8",
            "The warrior attacks the dragon. The wizard casts a powerful spell.",
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 2
        assert clauses[0].clause_id == "test-chunk-8::clause_0"
        assert clauses[1].clause_id == "test-chunk-8::clause_1"

    def test_parent_chunk_linked(self):
        """All clauses should link to parent chunk."""
        chunk = self._make_chunk(
            "test-chunk-9",
            "First. Second.",
        )
        clauses = extract_clause_units(chunk)
        assert all(c.parent_chunk_id == "test-chunk-9" for c in clauses)

    def test_minimum_length_filter(self):
        """Very short fragments should be merged or filtered."""
        chunk = self._make_chunk(
            "test-chunk-10",
            "OK. This is a proper sentence with more content here.",
        )
        clauses = extract_clause_units(chunk)
        # "OK." alone is too short (<20 chars), should be merged with next
        assert all(len(c.text) >= 20 for c in clauses)

    def test_empty_chunk_returns_empty(self):
        """Empty chunk text should return empty list."""
        chunk = self._make_chunk(
            "test-chunk-11",
            "",
        )
        clauses = extract_clause_units(chunk)
        assert clauses == []

    def test_whitespace_only_returns_empty(self):
        """Whitespace-only chunk should return empty list."""
        chunk = self._make_chunk(
            "test-chunk-12",
            "   \n\t  ",
        )
        clauses = extract_clause_units(chunk)
        assert clauses == []

    def test_section_path_inherited(self):
        """Clauses should inherit section_path from parent."""
        chunk = self._make_chunk(
            "test-chunk-13",
            "First statement here. Second statement here.",
            page=5,
            section_path=["Magic", "Spellcasting"],
        )
        clauses = extract_clause_units(chunk)
        assert clauses[0].section_path == ["Magic", "Spellcasting"]
        assert clauses[0].page == 5
        assert clauses[1].section_path == ["Magic", "Spellcasting"]
        assert clauses[1].page == 5

    def test_order_in_chunk_sequential(self):
        """Order should be sequential starting at 0."""
        chunk = self._make_chunk(
            "test-chunk-14",
            "First clause text. Second clause text. Third clause text.",
        )
        clauses = extract_clause_units(chunk)
        orders = [c.order_in_chunk for c in clauses]
        assert orders == list(range(len(clauses)))

    def test_exclamation_mark_splits(self):
        """Exclamation marks should cause sentence splits."""
        chunk = self._make_chunk(
            "test-chunk-15",
            "Beware the dragon! It breathes fire.",
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 2
        assert clauses[0].text == "Beware the dragon!"
        assert clauses[1].text == "It breathes fire."

    def test_question_mark_splits(self):
        """Question marks should cause sentence splits."""
        chunk = self._make_chunk(
            "test-chunk-16",
            "What is the DC? The DC is determined by the spell.",
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 2

    def test_abbreviations_not_split(self):
        """Common abbreviations should not cause false splits."""
        chunk = self._make_chunk(
            "test-chunk-17",
            "The range is 30 ft. and affects all creatures in the area.",
        )
        clauses = extract_clause_units(chunk)
        # "ft." should not split - this is a single sentence
        assert len(clauses) == 1
        assert "30 ft." in clauses[0].text

    def test_single_long_sentence(self):
        """A single long sentence should produce one clause."""
        long_sentence = "The wizard carefully prepares their most powerful spell while the warrior stands guard and the rogue scouts ahead for any signs of danger"
        chunk = self._make_chunk(
            "test-chunk-18",
            long_sentence + ".",
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 1
        assert clauses[0].text == long_sentence + "."

    def test_action_icon_preserved(self):
        """Action icons like [one-action] should be preserved."""
        chunk = self._make_chunk(
            "test-chunk-19",
            "[one-action] Strike at a creature. [two-actions] Cast a spell.",
        )
        clauses = extract_clause_units(chunk)
        assert any("[one-action]" in c.text for c in clauses)
        assert any("[two-actions]" in c.text for c in clauses)

    def test_level_notation_not_split(self):
        """Level notations like 'Level 5' should not split falsely."""
        chunk = self._make_chunk(
            "test-chunk-20",
            "At Level 5, you gain this ability. It allows you to move faster.",
        )
        clauses = extract_clause_units(chunk)
        assert len(clauses) == 2
        # Both sentences should be properly formed

    def test_deterministic_output(self):
        """Same input should always produce same output."""
        chunk = self._make_chunk(
            "test-chunk-21",
            "First sentence here. Second sentence here. Third sentence here.",
        )
        result1 = extract_clause_units(chunk)
        result2 = extract_clause_units(chunk)
        
        assert len(result1) == len(result2)
        for c1, c2 in zip(result1, result2):
            assert c1.clause_id == c2.clause_id
            assert c1.text == c2.text
            assert c1.char_offsets == c2.char_offsets


class TestClauseUnitIntegration:
    """Test clause extraction on real enriched outputs."""

    @pytest.fixture
    def sample_enriched_chunks(self):
        """Load real enriched chunks from PlayerCore outputs."""
        import json
        from pathlib import Path

        # Try multiple possible paths
        possible_paths = [
            Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json"),
            Path("Rules/StarFinder2e/PlayerCore/outputs/runs/latest/enriched/merged.enriched.json"),
        ]

        for path in possible_paths:
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                return data.get("chunks", [])

        pytest.skip("No PlayerCore enriched data found")

    def _chunk_from_dict(self, chunk_dict: dict) -> EnrichedChunk:
        """Create EnrichedChunk from dict, filtering out extra fields."""
        # Get only the fields that EnrichedChunk accepts
        valid_fields = {
            "id", "block_type", "text", "page", "bbox", "section_hierarchy",
            "content_kind", "is_rule_bearing", "tags", "traits", "spell_rank",
            "traditions", "spell_stats", "section_path"
        }
        filtered = {k: v for k, v in chunk_dict.items() if k in valid_fields}
        return EnrichedChunk(**filtered)

    def test_real_chunks_produce_clauses(self, sample_enriched_chunks):
        """Real chunks should produce at least one clause."""
        chunks_tested = 0
        for chunk_dict in sample_enriched_chunks[:20]:
            if not chunk_dict.get("text", "").strip():
                continue
            chunk = self._chunk_from_dict(chunk_dict)
            clauses = extract_clause_units(chunk)
            if clauses:  # Non-empty text should produce clauses
                chunks_tested += 1
                assert len(clauses) >= 1

        assert chunks_tested > 0, "No chunks with text were found"

    def test_real_chunk_offsets_valid(self, sample_enriched_chunks):
        """Offsets should be valid for real chunks."""
        for chunk_dict in sample_enriched_chunks[:20]:
            if not chunk_dict.get("text", "").strip():
                continue
            chunk = self._chunk_from_dict(chunk_dict)
            clauses = extract_clause_units(chunk)
            for clause in clauses:
                start, end = clause.char_offsets
                assert 0 <= start < end <= len(chunk.text), (
                    f"Invalid offsets ({start}, {end}) for chunk of length {len(chunk.text)}"
                )

    def test_rule_bearing_chunks_have_clauses(self, sample_enriched_chunks):
        """Rule-bearing chunks should produce clauses."""
        rule_bearing = [c for c in sample_enriched_chunks if c.get("is_rule_bearing")]
        if not rule_bearing:
            pytest.skip("No rule-bearing chunks found")

        for chunk_dict in rule_bearing[:10]:
            chunk = self._chunk_from_dict(chunk_dict)
            clauses = extract_clause_units(chunk)
            # Rule-bearing chunks should have actual content
            if len(chunk.text.strip()) >= 20:
                assert len(clauses) >= 1, f"Rule-bearing chunk produced no clauses: {chunk.text[:50]}..."
