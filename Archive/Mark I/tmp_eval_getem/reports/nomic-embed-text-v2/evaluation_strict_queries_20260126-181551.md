# RulesLawyer Evaluation Report: nomic-embed-text-v2 (run 2026-01-25_19-16-02)

## Summary

### Run
| Metric | Value |
| --- | --- |
| Ruleset ID | `None` |
| Chunk source | `enriched` |
| Chunk count | `23248` |
| Query count | `1` |
| Evaluated queries | `1` |
| Embeddings reused | `True` |

Embedding reuse reason: `store_cache`

### Strict Gold Metrics
| Metric | Value |
| --- | --- |
| Coverage | `1.0000` |
| MRR | `0.0000` |
| hit@1 | `0.0000` |
| hit@3 | `0.0000` |
| hit@5 | `0.0000` |
| hit@10 | `0.0000` |

### Cross-Book Contamination
| Metric | Value |
| --- | --- |
| contamination@1 | `1.0000` |
| contamination@3 | `1.0000` |
| contamination@5 | `1.0000` |
| contamination@10 | `1.0000` |

## Timings (ms)
| Metric | Value |
| --- | --- |
| Embedding (chunks) | `0` |
| Embedding (queries) | `95` |
| Embedding (answers) | `0` |
| Evaluation (strict) | `36` |
| Evaluation (expanded) | `0` |
| Total | `12490` |

### Timing Estimates (ms)
| Metric | Value |
| --- | --- |
| Evaluation (strict) | `60` |
| Evaluation (expanded) | `None` |
| Total | `155` |

## Document IDs
`merged`

## Metrics Legend (Why Each Metric Matters)
- Gold: the expected source chunk(s) for a query. Metrics that refer to gold measure whether retrieval surfaced the authoritative evidence.
- Coverage: fraction of evaluated queries whose gold chunk appears in top-k. This is the primary signal that retrieval is *traceable* to a source chunk.
- MRR: mean reciprocal rank of the first gold hit; higher means the correct chunk is found earlier, which reduces noise in the LLM context window.
- hit@k: share of queries where gold appears within top-k. This reflects how often the LLM can be fed a correct supporting chunk without additional reasoning.
- Candidate fraction (TOC traversal): fraction of chunks eligible after structural gating. Lower is better if coverage holds; it proves structure constrains retrieval safely.
- Missing scope count: queries whose expected chunk has no TOC scope. High values indicate broken section paths and weaken determinism.
- Routing Δ: chapter routing metric minus baseline; negative means routing loses reachable gold. We expect Δ to be >= 0 when routing is healthy.
- Contamination@k: cross-book hits in top-k (lower is better). Non-zero values break traceability and show leakage across books.
- Reachability: fraction of gold preserved through routing stages. This ensures structural gates do not discard correct evidence.

## Vocabulary (Traceable Retrieval)
- Structural eligibility: the set of chunks allowed by deterministic structure (TOC, sections, edges). This defines what is *allowed* to be retrieved.
- Ranking: ordering chunks *within* the eligible set using hybrid signals (dense embeddings + sparse metadata). This decides what is *most relevant*.
- Gold: the expected source chunk(s) for a query, derived from ground-truth annotations or deterministic routing targets.
- Strict gold: only the exact expected chunk IDs are correct. This is the strongest traceability target.
- Expanded gold: strict gold plus graph-expanded equivalents. Used to validate that deterministic edges preserve correctness.
- Baseline: retrieval without routing constraints. Used as the control for structural gating experiments.
- Chapter routing: limit candidate chunks to top-n chapters. A soft structural gate that should preserve reachability.
- TOC traversal: section-based structural gating. A strict gate used to prove deterministic scope narrowing.
- Graph boost: score bonus for graph neighbors. A soft signal layered *after* eligibility to improve ranking without violating scope.

## Query Details
### Query 0

**Text:** For the envoy's Get 'Em directive in Starfinder 2e, does the "Increase the damage by 1 at 5th, 10th, 15th, and 20th levels" clause apply to both the initial Strike when you Lead by Example and the subsequent damage, or only to the subsequent Strikes?

- Expected found: `True`
- Expected rank: `20189`

#### Expected chunk IDs
```json
[
  "sf2e-playercore-PZO22001-HC-Player-Core-000::/page/0/Text/5"
]
```

| Rank | Chunk ID | Score | Preview |
| --- | --- | --- | --- |
| 1 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-174-181::/page/1/Text/20` | 0.674359 | You gain the Lead by Example benefit for your Get 'Em! directive, except you and your allies get a +2 status bonus to damage on both the initial and subsequent Strikes. |
| 2 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113::/page/6/Text/15` | 0.639872 | **Lead by Example** If you used two actions, Strike the target. You gain a status bonus to the damage roll equal to your Charisma modifier. Regardless of whether the Strike hits, you and your allie |
| 3 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113::/page/14/Text/18` | 0.549260 | You follow-up your issued directive with an understood order by attacking a notable foe. Make a Strike. If the Strike hits, the target is affected by a 1-action Get 'Em. |
| 4 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/10/Text/12` | 0.538576 | Strength for melee Strikes and Dexterity for ranged Strikes). You also add any item bonus from the weapon and any other permanent bonuses or penalties. You also need to calculate how much damage ea |
| 5 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113::/page/10/Text/40` | 0.538066 | **Lead by Example** If you used two actions, Strike a target with a nonlethal attack. On a success, you gain a status bonus to damage equal to your Charisma modifier. On a critical success, an ally |
| 6 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/2/Text/25` | 0.536952 | **Strike** (page 410) actions have the attack trait and allow you to attack with a weapon you're wielding or an unarmed attack (such as a tail). If you're using a melee weapon or unarmed attack, yo |
| 7 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113::/page/2/Text/21` | 0.536688 | This section specifies the levels at which your character can increase their proficiency rank in a skill. At 3rd level and every 2 levels thereafter, most classes grant a skill increase, though env |
| 8 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-174-181::/page/1/Text/30` | 0.534990 | You gain the envoy directives class feature (see page 104), but do not gain the Lead by Example benefits of the Get 'Em! envoy directive. You become trained in Deception, Diplomacy, or Intimidation |
| 9 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/10/Text/11` | 0.525130 | Next to where you've written your character's melee and ranged weapons, calculate the modifier to Strike with each weapon and how much damage that Strike deals. The modifier for a Strike is equal t |
| 10 | `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113::/page/6/Text/26` | 0.511573 | **Lead by Example** If you used two actions, Strike the target to focus their attention on you. The target takes a –1 circumstance penalty on attacks made against other creatures until the start of |
