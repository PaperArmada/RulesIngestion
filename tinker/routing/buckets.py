"""Canonical retrieval-mode buckets.

Each bucket has:
- a short id (snake_case) used as a label
- a human-readable name
- a one- or two-sentence definition the classifier prompt injects verbatim
- 3 few-shot examples (query, optional rationale)

The taxonomy is derived from the conversation behind Docs/Design/VISION-Intent-Routed-Retrieval.md:
keyword search (entity-anchored), paraphrase (concept-anchored), HyDE
(intent-bearing distributed), and the four "extension" modes (enumeration,
structural, cross-reference, example-based).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Bucket:
    id: str
    name: str
    definition: str
    examples: tuple[str, ...]
    anti_examples: tuple[tuple[str, str], ...] = ()  # (query, why NOT this bucket)


BUCKETS: tuple[Bucket, ...] = (
    Bucket(
        id="entity_anchored_single",
        name="Entity-anchored, single-target",
        definition=(
            "The query names a specific corpus entity (a spell, action, "
            "feature, condition, class, etc.) by its corpus name, and one "
            "passage contains the full answer. Lexical-match territory: "
            "BM25 alone or hybrid retrieval is likely sufficient."
        ),
        examples=(
            "What does the Healing spell do?",
            "How many hit points does a Cleric have at first level?",
            "What is the Armor Class of a Goblin?",
        ),
    ),
    Bucket(
        id="entity_anchored_composite",
        name="Entity-anchored, composite",
        definition=(
            "The query names two or more specific entities and asks how "
            "they interact. The answer requires composing evidence from "
            "multiple separate passages, but each passage is itself "
            "individually retrievable by name."
        ),
        examples=(
            "Can a Magic-User cast Fireball while wearing armor?",
            "How does the Paladin's Detect Evil work against a Vampire?",
            "If a Thief uses Backstab against a Sleeping creature, what bonuses apply?",
        ),
    ),
    Bucket(
        id="concept_anchored",
        name="Concept-anchored (paraphrase)",
        definition=(
            "The query uses different words from the corpus but the "
            "question shape mirrors the answer shape (a definition asks "
            "for a definition). Dense semantic embeddings bridge the "
            "vocabulary gap. No HyDE needed."
        ),
        examples=(
            "How do I figure out who acts first in a fight?",
            "What's the rule for picking up an object during combat?",
            "How is a character's chance to hit determined?",
        ),
    ),
    Bucket(
        id="intent_bearing_distributed",
        name="Intent-bearing, distributed evidence",
        definition=(
            "The query expresses an intent or goal whose answer requires "
            "assembling evidence from multiple corpus passages, and the "
            "question shape does NOT match the answer shape. The user "
            "would not know to search for the corpus's terms. HyDE-with-"
            "shape-prior territory: generate a hypothetical answer-shaped "
            "artifact and use that to retrieve."
        ),
        examples=(
            "I want to build a character that's good at stealth and trickery — what should I pick?",
            "How do I move away from someone in melee without getting hit?",
            "What's the best way to deal with a group of undead?",
        ),
    ),
    Bucket(
        id="enumeration",
        name="Enumeration / set completion",
        definition=(
            "The query asks for the COMPLETE set of items matching a "
            "predicate (all spells of a level, all magic items of a kind, "
            "every class feature). Not a top-K retrieval; needs typed-"
            "metadata filtering. Top-K dense / BM25 will under-recall."
        ),
        examples=(
            "List every first-level Magic-User spell.",
            "What magic items grant a bonus to AC?",
            "Show me all class features that interact with poison.",
        ),
    ),
    Bucket(
        id="structural",
        name="Structural navigation",
        definition=(
            "The query asks the system to OPEN, JUMP TO, or DISPLAY a "
            "specific section of the document (a chapter, an appendix, "
            "the introduction, the index). The user wants the table-of-"
            "contents to drive the answer, not the content. Questions "
            "ABOUT what happens in some game procedure (combat sequence, "
            "character creation steps, turn structure) are NOT structural "
            "— those are concept_anchored or intent_bearing_distributed "
            "depending on how the evidence is distributed."
        ),
        examples=(
            "Take me to the combat chapter.",
            "What does the introduction say?",
            "Show me Appendix B.",
        ),
        anti_examples=(
            (
                "How does initiative work and what is the basic combat sequence?",
                "Asks about a game PROCEDURE (combat sequence), not a document "
                "section. This is intent_bearing_distributed or concept_anchored.",
            ),
            (
                "What are the steps to create a character?",
                "Asks about a game PROCEDURE (character creation), not navigating "
                "the document. Likely intent_bearing_distributed.",
            ),
            (
                "What are the roles at the table?",
                "Asks about GAME ROLES (players, GM), not a document section. "
                "This is concept_anchored or entity_anchored_single.",
            ),
        ),
    ),
    Bucket(
        id="cross_reference",
        name="Cross-reference traversal",
        definition=(
            "The query asks what other rules reference a named rule, or "
            "what rules a given rule depends on. This is a graph hop over "
            "the corpus's reference structure, not a content match."
        ),
        examples=(
            "What rules reference Saving Throws?",
            "Where else is the Turn Undead ability mentioned?",
            "What other class features depend on Charisma?",
        ),
    ),
    Bucket(
        id="example_based",
        name="Example-based (more like this)",
        definition=(
            "The query points at a known passage and asks for similar "
            "passages. The interaction shape is 'find more of this kind' "
            "rather than 'find something that answers a question'."
        ),
        examples=(
            "Find me other spells like Fireball.",
            "Show me actions that work like Cleave.",
            "What other magic items behave like a Wand of Wonder?",
        ),
    ),
)


BUCKET_IDS: tuple[str, ...] = tuple(b.id for b in BUCKETS)
BUCKET_BY_ID: dict[str, Bucket] = {b.id: b for b in BUCKETS}


def render_bucket_descriptions(buckets: Iterable[Bucket] = BUCKETS) -> str:
    """Markdown-ish block of bucket id, name, definition, examples.

    Used as the classifier prompt's bucket reference. Stable ordering so
    deterministic prompts are reproducible.
    """
    parts: list[str] = []
    for b in buckets:
        parts.append(f"Bucket: {b.id}")
        parts.append(f"Name: {b.name}")
        parts.append(f"Definition: {b.definition}")
        parts.append("Examples:")
        for ex in b.examples:
            parts.append(f"  - {ex}")
        if b.anti_examples:
            parts.append("Anti-examples (do NOT use this bucket for these):")
            for q, why in b.anti_examples:
                parts.append(f"  - \"{q}\"")
                parts.append(f"    Why not: {why}")
        parts.append("")
    return "\n".join(parts).strip()
