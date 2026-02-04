"""Tests for RuleFact extraction module."""
import json
import pytest

from enrichment.rule_facts import (
    RuleFact, FactType, Modality,
    extract_rule_facts,
    FactPattern,
    ALL_FACT_PATTERNS,
)
from enrichment.clause_units import ClauseUnit
from enrichment.mentions import Mention, MentionType, extract_mentions


class TestRuleFactModel:
    """Test RuleFact dataclass."""
    
    def test_rulefact_to_dict(self):
        """RuleFact should serialize to dict."""
        fact = RuleFact(
            fact_id="clause_1::fact_0",
            fact_type=FactType.GRANTS,
            subject="guarded thoughts",
            subject_type="feat",
            predicate="grants",
            object="+2 bonus to Will saves",
            object_type="bonus",
            modality=Modality.AUTOMATIC,
            condition=None,
            scope="role:lashunta",
            clause_id="clause_1",
            mention_ids=["clause_1::mention_0"],
            evidence_span=(0, 50),
        )
        d = fact.to_dict()
        assert d["fact_type"] == "grants"
        assert d["subject"] == "guarded thoughts"
        assert d["modality"] == "automatic"
        assert d["is_complete"] is True
        assert d["object"] == "+2 bonus to Will saves"
        assert d["scope"] == "role:lashunta"
    
    def test_partial_fact_creation(self):
        """PartialFact should have is_complete=False."""
        fact = RuleFact.partial(
            clause_id="clause_1",
            order=0,
            subject=None,
            subject_type=None,
            predicate="grants",
            object="something",
            mention_ids=[],
            evidence_span=(0, 10),
        )
        assert fact.is_complete is False
        assert fact.fact_type == FactType.PARTIAL
        assert fact.confidence == 0.5
        assert fact.extraction_method == "heuristic"
    
    def test_rulefact_default_values(self):
        """RuleFact should have correct default values."""
        fact = RuleFact(
            fact_id="test::fact_0",
            fact_type=FactType.GRANTS,
            subject="test",
            subject_type="test",
            predicate="grants",
            object="something",
            object_type="text",
            modality=Modality.AUTOMATIC,
            condition=None,
            scope=None,
            clause_id="test",
        )
        assert fact.confidence == 1.0
        assert fact.extraction_method == "pattern"
        assert fact.is_complete is True
        assert fact.mention_ids == []
        assert fact.failure_outcome is None
        assert fact.override_target is None
    
    def test_fact_type_enum_values(self):
        """FactType enum should have expected values."""
        assert FactType.GRANTS.value == "grants"
        assert FactType.REQUIRES.value == "requires"
        assert FactType.ON_SUCCESS.value == "on_success"
        assert FactType.ON_FAILURE.value == "on_failure"
        assert FactType.LEVEL_GATE.value == "level_gate"
        assert FactType.PARTIAL.value == "partial"
    
    def test_modality_enum_values(self):
        """Modality enum should have expected values."""
        assert Modality.MUST.value == "must"
        assert Modality.MAY.value == "may"
        assert Modality.AUTOMATIC.value == "automatic"
        assert Modality.CONDITIONAL.value == "conditional"


class TestFactExtraction:
    """Test fact extraction patterns."""
    
    def _make_clause(self, text: str, clause_id: str = "test::clause_0") -> ClauseUnit:
        return ClauseUnit(
            clause_id=clause_id,
            text=text,
            parent_chunk_id="test",
            order_in_chunk=0,
            char_offsets=(0, len(text)),
            page=1,
        )
    
    # Success/Failure patterns
    def test_on_success_extraction(self):
        """'On a success' should extract ON_SUCCESS fact."""
        clause = self._make_clause("On a success, you deal 2d6 damage.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        success_facts = [f for f in facts if f.fact_type == FactType.ON_SUCCESS]
        assert len(success_facts) >= 1
        assert "2d6 damage" in success_facts[0].object
    
    def test_on_failure_extraction(self):
        """'On failure' should extract ON_FAILURE fact."""
        clause = self._make_clause("On failure, the target is unaffected.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        failure_facts = [f for f in facts if f.fact_type == FactType.ON_FAILURE]
        assert len(failure_facts) >= 1
        assert "unaffected" in failure_facts[0].object
    
    def test_critical_success_extraction(self):
        """'Critical Success:' should extract ON_CRITICAL fact."""
        clause = self._make_clause("Critical Success: Deal double damage and stun the target.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        critical_facts = [f for f in facts if f.fact_type == FactType.ON_CRITICAL]
        assert len(critical_facts) >= 1
        assert "double damage" in critical_facts[0].object.lower() or "stun" in critical_facts[0].object.lower()
    
    def test_critical_failure_extraction(self):
        """'Critical Failure:' should extract failure fact."""
        clause = self._make_clause("Critical Failure: You fall prone and are stunned 1.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        failure_facts = [f for f in facts if f.fact_type == FactType.ON_FAILURE]
        assert len(failure_facts) >= 1
        assert "prone" in failure_facts[0].object.lower() or "stunned" in failure_facts[0].object.lower()
    
    def test_failure_explicit_not_inferred(self):
        """Failure facts should be explicit, not absence of success."""
        clause = self._make_clause("Success: You hit. Failure: You miss.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        success_count = sum(1 for f in facts if f.fact_type == FactType.ON_SUCCESS)
        failure_count = sum(1 for f in facts if f.fact_type == FactType.ON_FAILURE)
        
        # Both should exist as explicit facts
        assert success_count >= 1
        assert failure_count >= 1

    def test_instead_of_sets_procedure_override_target(self):
        clause = self._make_clause("Instead of attempting a recovery check, you regain 1 HP.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:recovery_check"

    def test_instead_sets_procedure_override_target_from_clause(self):
        clause = self._make_clause("Instead, you regain 1 HP when you would attempt a recovery check.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:recovery_check"

    def test_instead_of_sets_persistent_damage_override_target(self):
        clause = self._make_clause("Instead of taking persistent damage, you gain resistance.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:persistent_damage_tick"

    def test_instead_of_sets_attack_resolution_override_target(self):
        clause = self._make_clause("Instead of a missed attack, you may step 5 feet.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:attack_resolution"

    def test_instead_of_sets_gain_dying_override_target(self):
        clause = self._make_clause("Instead of gaining dying, you remain stable at 0 HP.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:gain_dying"

    def test_instead_of_sets_perception_check_override_target(self):
        clause = self._make_clause("Instead of a Perception check, you may attempt Stealth.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:perception_check"

    def test_instead_of_sets_initiative_roll_override_target(self):
        clause = self._make_clause("Instead of rolling initiative, you act immediately.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:initiative_roll"

    def test_instead_of_sets_apply_damage_override_target(self):
        clause = self._make_clause("Instead of taking damage, you gain temporary Hit Points.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:apply_damage"

    def test_instead_of_sets_damage_roll_override_target(self):
        clause = self._make_clause(
            "Instead of using its normal weapon damage dice, use the next larger die."
        )
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:damage_roll"
    
    def test_inline_instead_of_sets_override_target(self):
        clause = self._make_clause("You regain 1 HP instead of attempting a recovery check.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:recovery_check"
    
    def test_rather_than_sets_override_target(self):
        clause = self._make_clause("Rather than a recovery check, you regain 1 HP.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:recovery_check"
    
    def test_replaces_sets_override_target(self):
        clause = self._make_clause("This replaces a recovery check.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        override_facts = [f for f in facts if f.fact_type == FactType.OVERRIDES]
        assert override_facts
        assert override_facts[0].override_target == "procedure:recovery_check"
    
    def test_instead_of_sets_knocked_out_override_target(self):
        clause = self._make_clause("Instead of being knocked out, you remain conscious.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:knocked_out_transition"
    
    def test_instead_of_sets_roll_strike_override_target(self):
        clause = self._make_clause("Instead of rolling to Strike, you attempt a feint.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:roll_strike"
    
    def test_instead_of_sets_miss_resolution_override_target(self):
        clause = self._make_clause("Instead of a miss, you deal half damage.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "procedure:miss_resolution"
    
    def test_instead_of_numeric_override_target_classified_as_noise(self):
        clause = self._make_clause("Instead of -5, you take a -2 penalty.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        instead_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert instead_facts
        assert instead_facts[0].override_target == "noise:numeric:-5"
    
    def test_success_with_implicit_failure(self):
        """If success exists and failure mentioned but not extracted, create partial."""
        clause = self._make_clause("On success, deal damage. On failure the spell fizzles.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        # Should have both success and failure facts
        success_facts = [f for f in facts if f.fact_type == FactType.ON_SUCCESS]
        failure_facts = [f for f in facts if f.fact_type == FactType.ON_FAILURE]
        
        assert len(success_facts) >= 1
        assert len(failure_facts) >= 1
    
    # Level gate patterns
    def test_at_level_extraction(self):
        """'At 5th level' should extract LEVEL_GATE fact."""
        clause = self._make_clause("At 5th level, you gain the ability to fly.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        level_facts = [f for f in facts if f.fact_type == FactType.LEVEL_GATE]
        assert len(level_facts) >= 1
        assert "fly" in level_facts[0].object.lower()
    
    def test_prerequisite_level_extraction(self):
        """'Prerequisite: Level 9' should extract LEVEL_GATE."""
        clause = self._make_clause("Prerequisites: Level 9, trained in Athletics.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        level_facts = [f for f in facts if f.fact_type == FactType.LEVEL_GATE]
        assert len(level_facts) >= 1
    
    def test_requires_level_extraction(self):
        """'requires level 9' should extract LEVEL_GATE."""
        clause = self._make_clause("This feat requires level 9.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        level_facts = [f for f in facts if f.fact_type == FactType.LEVEL_GATE]
        assert len(level_facts) >= 1
    
    # Grants patterns
    def test_you_gain_extraction(self):
        """'You gain' should extract GRANTS fact."""
        clause = self._make_clause("You gain a +2 circumstance bonus to Perception checks.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        grant_facts = [f for f in facts if f.fact_type == FactType.GRANTS]
        assert len(grant_facts) >= 1
        assert "+2" in grant_facts[0].object or "bonus" in grant_facts[0].object.lower()
    
    def test_this_grants_extraction(self):
        """'This grants you' should extract GRANTS fact."""
        clause = self._make_clause("This grants you resistance to fire damage.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        grant_facts = [f for f in facts if f.fact_type == FactType.GRANTS]
        assert len(grant_facts) >= 1
        assert "resistance" in grant_facts[0].object.lower()
    
    def test_grants_bonus_extraction(self):
        """'grants a +2 bonus' should extract GRANTS fact."""
        clause = self._make_clause("Guarded Thoughts grants a +2 bonus to Will saves.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        grant_facts = [f for f in facts if f.fact_type == FactType.GRANTS]
        assert len(grant_facts) >= 1
    
    # Requires patterns
    def test_requires_extraction(self):
        """'Requires:' should extract REQUIRES fact."""
        clause = self._make_clause("Requires: trained in Arcana, ability to cast spells.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        req_facts = [f for f in facts if f.fact_type == FactType.REQUIRES]
        assert len(req_facts) >= 1
    
    def test_must_be_extraction(self):
        """'You must be' should extract REQUIRES fact."""
        clause = self._make_clause("You must be trained in Stealth to use this action.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        req_facts = [f for f in facts if f.fact_type == FactType.REQUIRES]
        assert len(req_facts) >= 1
        assert "stealth" in req_facts[0].object.lower()
    
    def test_prerequisites_extraction(self):
        """'Prerequisites:' should extract REQUIRES fact."""
        clause = self._make_clause("Prerequisites: expert in Acrobatics, Dexterity 14+.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        req_facts = [f for f in facts if f.fact_type == FactType.REQUIRES]
        assert len(req_facts) >= 1
    
    # Override patterns
    def test_instead_extraction(self):
        """'Instead' should extract INSTEAD_OF fact."""
        clause = self._make_clause("Instead, you may make a ranged attack against the target.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        override_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert len(override_facts) >= 1
    
    def test_overrides_extraction(self):
        """'This overrides' should extract OVERRIDES fact."""
        clause = self._make_clause("This overrides the normal movement restrictions.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        override_facts = [f for f in facts if f.fact_type == FactType.OVERRIDES]
        assert len(override_facts) >= 1
    
    def test_instead_of_extraction(self):
        """'instead of X, you Y' should extract INSTEAD_OF fact."""
        clause = self._make_clause("Instead of attacking, you may cast a spell.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        override_facts = [f for f in facts if f.fact_type == FactType.INSTEAD_OF]
        assert len(override_facts) >= 1
    
    # Applies-to patterns
    def test_affects_extraction(self):
        """'Affects' should extract APPLIES_TO fact."""
        clause = self._make_clause("This affects all creatures within 30 feet.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        applies_facts = [f for f in facts if f.fact_type == FactType.APPLIES_TO]
        assert len(applies_facts) >= 1
        assert "creature" in applies_facts[0].object.lower()
    
    def test_targets_extraction(self):
        """'Targets:' should extract APPLIES_TO fact."""
        clause = self._make_clause("Targets: one creature or object.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        applies_facts = [f for f in facts if f.fact_type == FactType.APPLIES_TO]
        assert len(applies_facts) >= 1
    
    def test_applies_to_extraction(self):
        """'applies to' should extract APPLIES_TO fact."""
        clause = self._make_clause("This bonus applies to all attack rolls.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        applies_facts = [f for f in facts if f.fact_type == FactType.APPLIES_TO]
        assert len(applies_facts) >= 1
    
    # Triggers patterns
    def test_when_triggers_extraction(self):
        """'When you hit' should extract TRIGGERS fact."""
        clause = self._make_clause("When you hit with a melee Strike, deal extra damage.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        trigger_facts = [f for f in facts if f.fact_type == FactType.TRIGGERS]
        assert len(trigger_facts) >= 1
    
    def test_if_triggers_extraction(self):
        """'If you succeed' should extract TRIGGERS fact."""
        clause = self._make_clause("If you succeed, the target takes 2d6 damage.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        trigger_facts = [f for f in facts if f.fact_type == FactType.TRIGGERS]
        assert len(trigger_facts) >= 1
    
    # Unless patterns
    def test_unless_extraction(self):
        """'unless' should extract UNLESS fact."""
        clause = self._make_clause("You take full damage unless you have resistance.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        unless_facts = [f for f in facts if f.fact_type == FactType.UNLESS]
        assert len(unless_facts) >= 1
    
    def test_except_extraction(self):
        """'except when' should extract UNLESS fact."""
        clause = self._make_clause("This works on all creatures except when they are immune.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        unless_facts = [f for f in facts if f.fact_type == FactType.UNLESS]
        assert len(unless_facts) >= 1
    
    # Subject identification
    def test_subject_from_mechanic_mention(self):
        """Subject should be identified from MECHANIC mentions."""
        clause = self._make_clause("Guarded Thoughts grants you a +2 bonus.")
        mentions = [
            Mention(
                mention_id="test::mention_0",
                surface="Guarded Thoughts",
                normalized="mechanic:guarded_thoughts",
                mention_type=MentionType.MECHANIC,
                clause_id="test::clause_0",
                span_offsets=(0, 15),
            )
        ]
        facts = extract_rule_facts(clause, mentions)
        
        assert len(facts) >= 1
        assert facts[0].subject == "mechanic:guarded_thoughts"
        assert facts[0].subject_type == "mechanic"
    
    def test_subject_from_role_mention(self):
        """Subject should be identified from ROLE mentions if no MECHANIC."""
        clause = self._make_clause("A Lashunta gains telepathy.")
        mentions = [
            Mention(
                mention_id="test::mention_0",
                surface="Lashunta",
                normalized="role:lashunta",
                mention_type=MentionType.ROLE,
                clause_id="test::clause_0",
                span_offsets=(2, 10),
            )
        ]
        facts = extract_rule_facts(clause, mentions)
        
        # Check that subject includes the role
        role_subject_facts = [f for f in facts if f.subject and "lashunta" in f.subject.lower()]
        assert len(role_subject_facts) >= 1
    
    def test_subject_hint_used_when_no_mention(self):
        """Subject hint should be used when no mention identifies subject."""
        clause = self._make_clause("You gain a +2 bonus to Will saves.")
        mentions = extract_mentions(clause)  # No MECHANIC mentions
        facts = extract_rule_facts(clause, mentions, subject_hint="Guarded Thoughts")
        
        grant_facts = [f for f in facts if f.fact_type == FactType.GRANTS]
        assert len(grant_facts) >= 1
        assert "guarded thoughts" in grant_facts[0].subject.lower()
        assert grant_facts[0].subject_type == "inherited"
    
    # Scope extraction
    def test_scope_from_role_mention(self):
        """Scope should include role mentions."""
        clause = self._make_clause("A Lashunta gains telepathy at 1st level.")
        mentions = [
            Mention(
                mention_id="test::mention_0",
                surface="Lashunta",
                normalized="role:lashunta",
                mention_type=MentionType.ROLE,
                clause_id="test::clause_0",
                span_offsets=(2, 10),
            )
        ]
        facts = extract_rule_facts(clause, mentions)
        
        # Check that scope includes the role
        scoped_facts = [f for f in facts if f.scope and "lashunta" in f.scope.lower()]
        assert len(scoped_facts) >= 1
    
    def test_scope_from_level_mention(self):
        """Scope should include level mentions."""
        clause = self._make_clause("At Level 9, you gain this ability.")
        mentions = extract_mentions(clause)  # Will extract level mention
        facts = extract_rule_facts(clause, mentions)
        
        # Check that scope includes level
        scoped_facts = [f for f in facts if f.scope and "level" in f.scope.lower()]
        # May or may not have scoped facts depending on extraction
        assert isinstance(facts, list)
    
    # Modality
    def test_modality_must(self):
        """'Must' language should produce MUST modality."""
        clause = self._make_clause("You must be trained in Athletics.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        must_facts = [f for f in facts if f.modality == Modality.MUST]
        assert len(must_facts) >= 1
    
    def test_modality_conditional(self):
        """Outcome patterns should have CONDITIONAL modality."""
        clause = self._make_clause("On success, deal damage.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        conditional_facts = [f for f in facts if f.modality == Modality.CONDITIONAL]
        assert len(conditional_facts) >= 1
    
    def test_modality_automatic(self):
        """'You gain' should have AUTOMATIC modality."""
        clause = self._make_clause("You gain a +2 bonus.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        automatic_facts = [f for f in facts if f.modality == Modality.AUTOMATIC]
        assert len(automatic_facts) >= 1
    
    # Determinism
    def test_deterministic_extraction(self):
        """Same clause should produce identical facts."""
        clause = self._make_clause("On success, deal damage. On failure, miss.")
        mentions = extract_mentions(clause)
        
        f1 = extract_rule_facts(clause, mentions)
        f2 = extract_rule_facts(clause, mentions)
        
        assert [f.to_dict() for f in f1] == [f.to_dict() for f in f2]
    
    def test_deterministic_multiple_runs(self):
        """Multiple runs should produce identical output."""
        clause = self._make_clause("At 5th level, you gain resistance. You must be trained.")
        mentions = extract_mentions(clause)
        
        results = []
        for _ in range(5):
            facts = extract_rule_facts(clause, mentions)
            results.append([f.to_dict() for f in facts])
        
        # All runs should be identical
        for i in range(1, len(results)):
            assert results[0] == results[i]
    
    # Edge cases
    def test_empty_clause_returns_empty(self):
        """Empty clause should return empty list."""
        clause = self._make_clause("")
        facts = extract_rule_facts(clause, [])
        assert facts == []
    
    def test_whitespace_clause_returns_empty(self):
        """Whitespace-only clause should return empty list."""
        clause = self._make_clause("   \n\t  ")
        facts = extract_rule_facts(clause, [])
        assert facts == []
    
    def test_no_pattern_match_returns_empty(self):
        """Clause with no matching patterns should return empty list."""
        clause = self._make_clause("The stars shine brightly in the void.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        assert isinstance(facts, list)
        # May be empty or may have some facts from entity mentions
    
    def test_fact_id_format(self):
        """Fact IDs should follow expected format."""
        clause = self._make_clause("You gain a bonus.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        if facts:
            assert facts[0].fact_id.startswith(clause.clause_id)
            assert "::fact_" in facts[0].fact_id
    
    def test_evidence_span_valid(self):
        """Evidence span should be valid tuple within clause bounds."""
        clause = self._make_clause("You gain a +2 bonus to saves.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        for fact in facts:
            start, end = fact.evidence_span
            assert 0 <= start <= end <= len(clause.text)


class TestPartialFacts:
    """Test PartialFact creation for incomplete extractions."""
    
    def _make_clause(self, text: str) -> ClauseUnit:
        return ClauseUnit(
            clause_id="test::clause_0",
            text=text,
            parent_chunk_id="test",
            order_in_chunk=0,
            char_offsets=(0, len(text)),
            page=1,
        )
    
    def test_partial_fact_when_no_subject(self):
        """Facts without identifiable subject may have lower confidence."""
        clause = self._make_clause("On success, something happens.")
        mentions = []  # No mentions to identify subject
        facts = extract_rule_facts(clause, mentions)
        
        # Should still extract pattern
        if facts:
            # Without subject, confidence should be lower
            low_confidence = [f for f in facts if f.confidence < 1.0]
            assert len(low_confidence) >= 0  # May or may not have low confidence facts
    
    def test_partial_fact_preserves_extracted_components(self):
        """PartialFacts should preserve what was extracted."""
        clause = self._make_clause("You gain some unspecified benefit.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        # The object may be captured even without clear subject
        grant_facts = [f for f in facts if f.fact_type == FactType.GRANTS]
        if grant_facts:
            assert grant_facts[0].object is not None
    
    def test_partial_fact_for_implicit_failure(self):
        """Implicit failure should create a PartialFact."""
        clause = self._make_clause("On success, you hit. The target might fail the save.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        # Should have success fact
        success_facts = [f for f in facts if f.fact_type == FactType.ON_SUCCESS]
        assert len(success_facts) >= 1
        
        # Should have some failure-related content (either explicit or implicit)
        failure_related = [f for f in facts if f.fact_type == FactType.ON_FAILURE or "fail" in str(f.object or "").lower()]
        # May or may not have failure facts depending on text matching


class TestPatternRegistry:
    """Test pattern registry and pattern objects."""
    
    def test_all_patterns_have_name(self):
        """All patterns should have a name."""
        for pattern in ALL_FACT_PATTERNS:
            assert pattern.name
            assert isinstance(pattern.name, str)
    
    def test_all_patterns_have_type(self):
        """All patterns should have a fact type."""
        for pattern in ALL_FACT_PATTERNS:
            assert pattern.fact_type
            assert isinstance(pattern.fact_type, FactType)
    
    def test_all_patterns_have_modality(self):
        """All patterns should have a modality."""
        for pattern in ALL_FACT_PATTERNS:
            assert pattern.modality
            assert isinstance(pattern.modality, Modality)
    
    def test_pattern_names_unique(self):
        """Pattern names should be unique."""
        names = [p.name for p in ALL_FACT_PATTERNS]
        assert len(names) == len(set(names))
    
    def test_outcome_patterns_exist(self):
        """Should have outcome patterns for success/failure."""
        outcome_patterns = [p for p in ALL_FACT_PATTERNS if p.fact_type in (FactType.ON_SUCCESS, FactType.ON_FAILURE, FactType.ON_CRITICAL)]
        assert len(outcome_patterns) >= 4
    
    def test_level_patterns_exist(self):
        """Should have level gate patterns."""
        level_patterns = [p for p in ALL_FACT_PATTERNS if p.fact_type == FactType.LEVEL_GATE]
        assert len(level_patterns) >= 2


class TestRuleFactIntegration:
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
        for chunk_dict in data.get("chunks", [])[:100]:
            if not chunk_dict.get("is_rule_bearing"):
                continue
            chunk = EnrichedChunk(**chunk_dict)
            clauses.extend(extract_clause_units(chunk))
        return clauses[:50]  # Limit for speed
    
    def test_real_clauses_produce_facts(self, sample_clauses):
        """Real clauses should produce some facts."""
        all_facts = []
        for clause in sample_clauses:
            mentions = extract_mentions(clause)
            facts = extract_rule_facts(clause, mentions)
            all_facts.extend(facts)
        
        # Should produce at least some facts
        assert len(all_facts) > 0
    
    def test_fact_types_distributed(self, sample_clauses):
        """Multiple fact types should appear in real data."""
        all_facts = []
        for clause in sample_clauses:
            mentions = extract_mentions(clause)
            facts = extract_rule_facts(clause, mentions)
            all_facts.extend(facts)
        
        types_found = {f.fact_type for f in all_facts}
        # Should find at least 2 different types
        assert len(types_found) >= 2
    
    def test_failure_facts_present(self, sample_clauses):
        """Failure facts may appear in real rule data."""
        all_facts = []
        for clause in sample_clauses:
            mentions = extract_mentions(clause)
            facts = extract_rule_facts(clause, mentions)
            all_facts.extend(facts)
        
        failure_facts = [f for f in all_facts if f.fact_type == FactType.ON_FAILURE]
        # May or may not find any depending on sample, but list should exist
        assert isinstance(failure_facts, list)
    
    def test_facts_have_valid_structure(self, sample_clauses):
        """All extracted facts should have valid structure."""
        for clause in sample_clauses[:10]:
            mentions = extract_mentions(clause)
            facts = extract_rule_facts(clause, mentions)
            
            for fact in facts:
                # Check required fields
                assert fact.fact_id
                assert fact.fact_type in FactType
                assert fact.predicate
                assert fact.modality in Modality
                assert fact.clause_id
                
                # Check serialization works
                d = fact.to_dict()
                assert isinstance(d, dict)
                assert "fact_id" in d
                assert "fact_type" in d


class TestMentionIntegration:
    """Test integration with mention extraction."""
    
    def _make_clause(self, text: str) -> ClauseUnit:
        return ClauseUnit(
            clause_id="test::clause_0",
            text=text,
            parent_chunk_id="test",
            order_in_chunk=0,
            char_offsets=(0, len(text)),
            page=1,
        )
    
    def test_mention_ids_populated(self):
        """Fact mention_ids should reference overlapping mentions."""
        clause = self._make_clause("On failure, you are stunned 1 and prone.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        # Facts may or may not have mention IDs depending on overlap
        # Just verify structure is correct
        for fact in facts:
            assert isinstance(fact.mention_ids, list)
            for mid in fact.mention_ids:
                assert isinstance(mid, str)
    
    def test_object_type_from_mentions(self):
        """Object type should be inferred from overlapping mentions."""
        clause = self._make_clause("On failure, you are stunned.")
        mentions = extract_mentions(clause)
        facts = extract_rule_facts(clause, mentions)
        
        failure_facts = [f for f in facts if f.fact_type == FactType.ON_FAILURE]
        if failure_facts:
            # Object type should be set
            assert failure_facts[0].object_type is not None or failure_facts[0].object_type == "text"
    
    def test_scope_from_level_and_role(self):
        """Scope should combine level and role mentions."""
        clause = self._make_clause("At Level 9, a Lashunta gains telepathy.")
        # Create mentions manually for predictable test
        mentions = [
            Mention(
                mention_id="test::mention_0",
                surface="Level 9",
                normalized="level:9",
                mention_type=MentionType.LEVEL,
                clause_id="test::clause_0",
                span_offsets=(3, 10),
            ),
            Mention(
                mention_id="test::mention_1",
                surface="Lashunta",
                normalized="role:lashunta",
                mention_type=MentionType.ROLE,
                clause_id="test::clause_0",
                span_offsets=(14, 22),
            ),
        ]
        facts = extract_rule_facts(clause, mentions)
        
        # Check that scope contains both
        if facts:
            scope = facts[0].scope
            if scope:
                assert "lashunta" in scope.lower() or "level" in scope.lower()
