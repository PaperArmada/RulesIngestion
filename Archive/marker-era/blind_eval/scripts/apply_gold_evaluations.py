#!/usr/bin/env python3
"""
Apply systematic gold chunk evaluations to gold_audit.json.
Each item gets evaluation_status (keep|trim|expand|drop) and reviewer_notes.
Run from repo root: uv run python blind_eval/scripts/apply_gold_evaluations.py
"""

from __future__ import annotations

import json
from pathlib import Path

# (evaluation_status, reviewer_notes) for each gold_items index 0..116
EVALUATIONS: list[tuple[str, str | None]] = [
    ("keep", "Vent Gas: describes gas/emanation; supports what can affect it (wind, dispel)."),
    ("keep", "Gust of Wind: 'disperses fog and mist' directly answers."),
    ("keep", "dispel magic: can eliminate effects of other spells."),
    ("keep", "Lashunta flavor: telepathy/synergy context for feats."),
    ("expand", "GUARDED THOUGHTS: header only; ideal gold includes feat body."),
    ("expand", "PSYCHIC MASTERY: header only; ideal gold includes feat body."),
    ("keep", "Solarian table: level 9 row shows solarian expertise, stellar partition."),
    ("keep", "Solar weapon: melee weapon/synergy for build."),
    ("keep", "Redirect Current: trigger = electricity damage, redirect at creature; no powering devices."),
    ("keep", "'use to power technological devices' directly answers alternative."),
    ("trim", "Fragment; ideal gold includes full ability name + sentence."),
    ("expand", "SIDESTEP: header only; need trigger/body for creature vs inanimate."),
    ("keep", "Trigger 'a creature misses you'—direct answer."),
    ("keep", "Inanimate objects/hazards not creatures; supports Sidestep answer."),
    ("drop", "Wrong topic (Android glitching vs tech trait, not Sidestep/creature)."),
    ("expand", "PERCEPTION: section header only."),
    ("keep", "Perception measures awareness; core definition."),
    ("keep", "Formula: d20 + Wis + proficiency + bonuses."),
    ("keep", "Proficiency/bonuses paragraph."),
    ("keep", "Perception DC = 10 + modifier."),
    ("keep", "Perception for initiative."),
    ("expand", "Covering Fire: header only."),
    ("keep", "Covering Fire: Strike, suppress, -2 penalty to attacks vs ally."),
    ("keep", "2-action Area Fire / Auto-Fire option."),
    ("expand", "I'll Be Back: header only."),
    ("trim", "Frequency only; need trigger + effect for full answer."),
    ("trim", "Trigger fragment (mid-sentence)."),
    ("trim", "Effect fragment (continuation)."),
    ("expand", "Nimbus Surge: header only."),
    ("keep", "Trigger includes 'leaves a square during a move action'."),
    ("keep", "Effect: Strike, doesn't count toward MAP."),
    ("expand", "Solar Nimbus: header only."),
    ("keep", "Grants Nimbus Surge without attunement benefits."),
    ("expand", "Revivification Protocol: header only."),
    ("keep", "Trigger: about to attempt recovery check—replaces check."),
    ("keep", "Effect: restored to 1 HP, lose dying/unconscious."),
    ("expand", "RECOVERY CHECKS: section header."),
    ("keep", "Recovery check at start of turn; context for 'replaces'."),
    ("expand", "Undying: header only."),
    ("keep", "Trigger: about to attempt recovery check."),
    ("keep", "Effect: no frequency in text; supports 'may be unlimited'."),
    ("keep", "Revivification (Android): one of two feats compared."),
    ("keep", "Trigger: before recovery check."),
    ("keep", "Android effect text."),
    ("keep", "Undying (Shirren): second feat."),
    ("keep", "Trigger: same structure."),
    ("keep", "Shirren effect text."),
    ("trim", "Prone one-liner; need full condition text for penalties."),
    ("keep", "Prone full: off-guard, -2 attack, Crawl/Stand only."),
    ("keep", "Hide: cover/concealment required."),
    ("keep", "Prone limits only move actions; doesn't prevent Hide."),
    ("trim", "Wounded mid-paragraph; expand for full wounded definition."),
    ("keep", "Wounded ends: Treat Wounds or full HP + 10 min rest."),
    ("keep", "Dying: recovery at start; damage increases dying."),
    ("keep", "End of turn: persistent damage at this point."),
    ("keep", "Persistent damage at end of each turn."),
    ("keep", "Recovery check at start of turn."),
    ("keep", "Concealed: DC 5 flat check before affecting target."),
    ("keep", "Concealed condition text."),
    ("keep", "Cover: +2/+4 circumstance bonus to AC, Reflex."),
    ("keep", "Cover table: bonus summary."),
    ("keep", "Blinded: full penalties (difficult terrain, auto-fail vision, -4, off-guard)."),
    ("keep", "Nonlethal: don't gain dying condition, unconscious with 0 HP."),
    ("keep", "0 HP: nonlethal knocks out, no dying."),
    ("keep", "Nonlethal trait context."),
    ("keep", "Crawl: requirements, 5 feet, stay prone."),
    ("keep", "Prone: only Crawl and Stand for move actions."),
    ("keep", "Flanking: off-guard to melee from flanking creatures only (situational)."),
    ("keep", "Frequency and Trigger definitions."),
    ("keep", "Ability block: Effect is duration of one use."),
    ("keep", "Aid: requirements ally willing."),
    ("keep", "Aid: help your ally with a task."),
    ("keep", "One action per trigger (reaction or free action)."),
    ("expand", "Nanite Surge base: header; need Enhanced Nanite Surge for replace vs add."),
    ("keep", "Enhanced: use Nanite Surge once per 10 min rather than once per hour (replaces)."),
    ("keep", "One reaction per round, use only when trigger fulfilled."),
    ("keep", "reaction glossary: 1 per round."),
    ("keep", "Same rule: one action per trigger."),
    ("keep", "Reactions: not your turn, one per round, trigger."),
    ("keep", "reaction glossary."),
    ("keep", "Bold terms; Glossary and Index for full rules."),
    ("keep", "Many things at start of turn."),
    ("keep", "Dying: recovery check at start of turn each round."),
    ("keep", "Free actions with triggers don't use up your 1 reaction per round."),
    ("keep", "reaction uses 1 per round (contrast)."),
    ("keep", "Reactions can be used when it's not your turn."),
    ("keep", "Example illustrates rule (choose one, not both)."),
    ("keep", "Glossary and Index for specific rules (same chunk as 81)."),
    ("keep", "Dying recovery at start of turn."),
    ("keep", "Start of turn steps."),
    ("keep", "Persistent damage at end of turn."),
    ("keep", "ListItem: persistent damage at this point."),
    ("keep", "'About to attempt' = reaction resolves before the check."),
    ("keep", "Dying: attempt recovery at start of turn."),
    ("keep", "Graviton-Attuned Stride: before or after attacks, once."),
    ("keep", "'Triggering creature' = creature that triggered the reaction."),
    ("keep", "Grapple the triggering creature."),
    ("keep", "MAP resets at end of your turn."),
    ("drop", "Wrong chunk (character creation); targeting/undetected not here."),
    ("trim", "Grapple action text; grabbed condition restrictions would be in condition block."),
    ("keep", "Success: target is grabbed."),
    ("keep", "Failure: conditions end."),
    ("keep", "Frequency once per round: direct."),
    ("drop", "Irrelevant (level/attribute boost text)."),
    ("drop", "Elemental weapon, not illusion spell."),
    ("keep", "Shadow failure: invisible, paralyzed, cannot experience or interact."),
    ("drop", "Get 'Em targeting, not Aid."),
    ("keep", "Aid: ally willing, prepared to help."),
    ("keep", "Sure Footing: immune to grabbed (among others)."),
    ("drop", "Piercing Spikes reaction when grabbed, not Sure Footing."),
    ("keep", "Conditions together: relative/similar theme, understand interaction."),
    ("keep", "archetype: special theme, choose using class feats."),
    ("keep", "Spellcasting: obvious sensory manifestations, spell signature."),
    ("drop", "Skills/character building, not conditions."),
    ("keep", "Conditions relative/similar theme, look together."),
    ("drop", "Religion/deities, wrong chunk."),
    ("keep", "Frequency = limit; Trigger = when reaction/free action can be used."),
]


def main() -> None:
    audit_path = Path("blind_eval/gold_audit/gold_audit.json")
    if not audit_path.exists():
        raise SystemExit(f"Not found: {audit_path}")
    with open(audit_path, encoding="utf-8") as f:
        audit = json.load(f)
    items = audit.get("gold_items", [])
    if len(items) != len(EVALUATIONS):
        raise SystemExit(f"Expected {len(EVALUATIONS)} items, got {len(items)}")
    for i, (status, notes) in enumerate(EVALUATIONS):
        items[i]["evaluation_status"] = status
        items[i]["reviewer_notes"] = notes
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    counts = {}
    for s, _ in EVALUATIONS:
        counts[s] = counts.get(s, 0) + 1
    print(f"Updated {audit_path}: keep={counts.get('keep',0)} trim={counts.get('trim',0)} expand={counts.get('expand',0)} drop={counts.get('drop',0)}")


if __name__ == "__main__":
    main()
