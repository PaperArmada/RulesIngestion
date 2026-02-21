# Swords & Wizardry Revised: Benchmark Design (Bottom-Up)

**Date:** 2026-02-15  
**Intent:** Create a new retrieval benchmark from the bottom up, applying gold curation philosophy from the start. The PD version is being abandoned; we use the **Revised** rulebook as the sole corpus. Questions translate from our existing set but target **novel pages and chunks** in Revised—we define what we’re looking for by reading the material first, then building gold.

---

## 1) Philosophy (from gold curation handoff)

- **Read before retrieve:** Open the material, inspect pages and structural paths, decide what answers we need, then define gold.
- **Path-based gold from the start:** Use `gold_locations` (page + structural_path) as canonical; no legacy `gold_unit_ids` that break when the corpus changes.
- **Required vs supporting:** Distinguish must-have chunks from helpful context; document rationale.
- **Expert Referee answers:** Detailed, S&W-only, cite slots/rounds/caveats where relevant.

---

## 1.5) Discovery flexibility and question taxonomy

### Flexibility: be prepared to split

We **discover** as we go. The benchmark is not fixed:

- **Split questions:** A broad question ("How do experience points work?") may become two: one for XP sources and one for advancement tables. Or we find that a single question conflates lookup and reasoning—split them.
- **Split gold:** Gold for one question may belong to two distinct lookups; split the question so each has focused gold. Conversely, two questions may share supporting gold; that's fine.
- **Evolve during curation:** As we read the material and curate, we add, merge, or split. Use `_split_from` or `_gold_note` to track lineage.

Schema addition: optional `_split_from: "sw_rev_q07"` when a question was derived from another.

### Question types: lookup, atomic rules, reasoning

We're modeling how a **user** looks things up and how an **agentic system** helps: retrieving atomic rules and reasoning over them to support Referee decisions.

| Type | What we're testing | Example |
|------|--------------------|---------|
| **Lookup** | User finds a specific fact in the book. | "What does 'T' mean on the Turn Undead table?" |
| **Atomic rule construction** | System gathers discrete rule fragments that together answer a question. Multiple chunks, each an atomic unit. | "What rules govern when a magic-user can re-prepare spells?" → retrieve prep phase, combat sequence, damage-interruption rule. |
| **Reasoning / Referee decision** | System retrieves atomic rules, then reasons over them to propose a ruling. Rules may be silent or ambiguous; answer requires judgment. | "The fighter took 3 hp damage during the surprise round. When does she get initiative?" → rules + inference about sequencing. |

Design questions accordingly: some are pure lookup, some require composition of atoms, some require reasoning beyond the text. Gold for reasoning questions still points at the atomic rules that *inform* the decision—not the decision itself, which lives in the answer.

### Answer quality: taste

Answers are not search-result dumps. They should read like a **thoughtful Referee** who has consulted the rules and is making a call:

- **Cite** the relevant atomic rules (what the book says).
- **Reason** over them: how they apply, where they're silent, what edge cases arise.
- **Decide** when appropriate: "Given X and Y, the Referee would typically…" or "The rules don't specify; the Referee is free to…"

Good taste means: precise where the rules are precise, appropriately hedged where they're not, and phrased for someone at the table—not for a search engine. The answer models the kind of response we want the agentic system to produce.

---

## 2) Process

### Phase A: Read the material (before any retrieval)

1. **Run substrate inspection:**
   ```bash
   uv run python scripts/inspect_substrate_for_benchmark.py --corpus sw --output evals/retrieval/SwordsandWizardy/substrate_index.md
   ```
2. **Produce:** Page index, structural paths per page, chunk summaries. Use this to decide what topics the Revised book actually covers.
3. **Decide:** Which questions we can answer from Revised; which need rewriting or dropping.

### Phase B: Map questions to Revised

As we read the material, assign **question_type** and be willing to **split** (see §1.5).

| Old ID | Question theme | Type | Revised fit | Action |
|--------|----------------|------|-------------|--------|
| sw_q01 | Referee discretion when rules don't cover | reasoning | ✓ | Keep; may split into lookup (where does it say?) + reasoning (how to apply?) |
| sw_q02a | Treasure division (Splitting the Take) | lookup | ✓ | Keep |
| sw_q02b | Treasure tables mandatory? | lookup | ✓ | Keep |
| sw_q02c | Treasure value vs XP | atomic_rules | ✓ | Keep |
| sw_q03 | Class ability formula (White Box) | lookup | ✓ | Rewrite for Revised only |
| sw_q04 | Magic-user spell prep, re-prepare | atomic_rules | ✓ | Keep; may split prep vs damage-interruption |
| sw_q05 | Turn Undead: T vs number | lookup | ✓ | Keep |
| sw_q06 | First-level cleric spells? | lookup | ✓ | Keep |
| sw_q07 | XP and level advancement | atomic_rules | ✓ | Consider split: XP sources vs advancement tables vs referee adjustment |
| sw_q08 | Race, class, ability bonuses | atomic_rules | ✓ | Keep |
| sw_q09 | Can humans dual-class? | reasoning | ✓ | Keep; rules are silent → Referee decision |
| sw_q10 | Minimum ability scores? | lookup | ✓ | Rewrite S&W-only |
| sw_q11 | Starting spells for magic-users | atomic_rules | ✓ | Rewrite S&W-only |
| sw_q12 | Thief skills / saving throws | ⚠ | Check Revised for thief |
| sw_q13 | Combat sequence | atomic_rules | ✓ | Rewrite S&W-only |
| sw_q14 | 0 hp and healing | atomic_rules | ✓ | Rewrite S&W-only; consider reasoning variant |
| sw_q15 | Firing into melee | lookup | ✓ | Rewrite S&W-only |
| sw_q16–25 | S&W Light, Complete, external | — | ✗ | Drop |

**Questions to discover:** As we curate, add reasoning questions that require composing atomic rules and making a Referee call. E.g.: "The magic-user declares she's preparing a spell. Before she finishes, an orc hits her. She had already cast one spell this round. What happens?" — gold = damage-during-prep rule + combat sequence; answer = reasoned ruling.

### Phase C: Define gold from the book

For each question we keep or rewrite:

1. **Identify target pages** from the substrate index (or PDF).
2. **Discover structural_path** for those pages: run the same pipeline as experiments (min_chars=100, merge_max_chars=2000).
3. **Build `gold_locations`** with placeholder keys; no hardcoded chunk IDs.
4. **Set `required_gold`** / **`supporting_gold`** with rationale.
5. **Split if needed:** If one question spans two distinct lookups or mixes lookup and reasoning, split and give each focused gold.

### Phase C′: Curate answers with taste

When writing or revising **answer** text:

- **Lookup:** State the fact clearly; cite where it appears. No hedging if the rule is explicit.
- **Atomic rules:** List the relevant rules and how they fit together. Avoid dumping; synthesize.
- **Reasoning:** Lead with the rules, then the inference. "The book says X and Y. It doesn't say Z. A Referee would typically…" or "The rules leave this to the Referee; common approaches include…"

Taste = appropriate precision, appropriate hedging, language for the table not the index.

### Phase D: Run resolution and persist

```bash
uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml
```

Resolution runs at experiment time; optionally persist resolved IDs back to the benchmark file.

---

## 3) Schema (per query)

- **id:** e.g. `sw_rev_q01`
- **tier:** T1 (core rules) | T2 (detail) | T3 (edge)
- **question_type:** Optional. `lookup` | `atomic_rules` | `reasoning` — see §1.5.
- **question:** Natural-language question answerable from Revised only.
- **answer:** Thoughtful Referee–style; cite atomic rules, reason over them, decide when appropriate. See §1.5 (taste).
- **expected_answer_summary:** One-line for embedding/display.
- **source_page:** Comma-separated 1-based pages for display.
- **gold_unit_ids:** Placeholder keys (e.g. `sw_rev_q01_p39`) or resolved after run.
- **gold_locations:** Map key → `{ "page": <0-based>, "structural_path": ["Heading Name"] }`.
- **required_gold** / **supporting_gold:** Subset of gold_locations keys.
- **required_gold_rationale:** Optional map key → reason.
- **_gold_note:** Optional curation note.
- **_split_from:** Optional. ID of question this was split from (for discovery tracking).

---

## 4) Files

| File | Purpose |
|------|---------|
| `swords_wizardry_benchmark.json` | Legacy benchmark (mixed sources; some legacy IDs). |
| `swords_wizardry_revised_benchmark.json` | **New** benchmark: Revised-only, path-based gold from start. |
| `substrate_index.md` | Output of inspect script: pages, paths, chunks (when substrate exists). |
| `scripts/inspect_substrate_for_benchmark.py` | Read material; produce index before retrieval. |

---

## 5) Config

- **Experiment config:** `retrieval_lab/experiments/hybrid/swords_wizardry_revised_hybrid.yaml`
- **Run:** `uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/hybrid/swords_wizardry_revised_hybrid.yaml`

## 6) Next steps

1. Ensure substrate `out/Swords&Wizardry` exists (Revised rulebook, stageB evidence units).
2. Run `inspect_substrate_for_benchmark.py` to generate `substrate_index.md`:
   ```bash
   uv run python scripts/inspect_substrate_for_benchmark.py --corpus sw --output evals/retrieval/SwordsandWizardy/substrate_index.md
   ```
3. Review substrate index; confirm question mapping and fix any placeholder `gold_locations` (especially sw_rev_q03, sw_rev_q10–sw_rev_q14).
4. Run experiment; verify resolution and metrics.
