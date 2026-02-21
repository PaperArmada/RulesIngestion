# Manual Curation Workflow: Retrieval Benchmark (PDF-Driven)

This workflow builds a high-quality retrieval benchmark **without substrate/corpus access** by iterating question-by-question using **user-pasted PDF excerpts** (verbatim text + printed page numbers + headings).

The result is a benchmark JSON that starts as an outline (draft Q/A) and is progressively upgraded to **cited**, with `gold_locations` + `required_gold` grounded in the book’s visible structure.

---

## Goals

- **Build the benchmark structure first** (IDs, tiers, question types, draft answers).
- **Keep “atomic” questions system-agnostic** so they can be reused across rulesets.
- **Manually cite** each question using pasted PDF excerpts:
  - tighten answers to what’s explicitly supported
  - fill `source_page`, `gold_locations`, `required_gold`, and rationales

---

## Constraints and conventions

- **No substrate access assumed.** Gold is curated from the PDF excerpts you paste.
- **Page numbers**
  - Use **printed page numbers** everywhere the human sees them:
    - `source_page`: comma-separated printed page numbers (string)
    - `gold_locations.*.page`: printed page numbers (number)
  - If/when substrate is available later, run a resolver/mapping step to align any 0-based vs 1-based discrepancies.
- **Structural paths**
  - `gold_locations.*.structural_path` must match the **exact heading(s)** visible on those pages.
  - Prefer 1–3 heading segments (e.g., `["How to Play", "TIME"]`) that uniquely identify the section.
- **Avoid corpus-name bias in queries**
  - Do **not** include the system name in `question` text (the benchmark file already selects the corpus).
  - Answers become system-specific once cited.

---

## Benchmark shape (per query)

Minimum recommended fields (existing repo schema):

- **`id`**: stable string ID (e.g., `sw_rev_u03_time_progression_model`)
- **`tier`**: `T1` (core) | `T2` (detail) | `T3` (edge)
- **`question_type`**: `lookup` | `atomic_rules` | `reasoning`
- **`question`**: system-agnostic question text (natural table language)
- **`answer`**: Referee-style answer; must match cited text; hedge only where rules are silent
- **`expected_answer_summary`**: one crisp line
- **`source_page`**: `"33, 35"` (printed pages)
- **`gold_locations`**: map key → `{ page, structural_path }`
- **`required_gold`**: list of gold keys that *must* be retrieved to answer correctly
- **`supporting_gold`**: helpful context (optional)
- **`required_gold_rationale`**: map key → why it’s required
- **`_status`**: `draft_needs_citations` → `cited` (optional helper)
- **`_mode`**: typically `"single_cite"`

Gold keys should be stable and readable, e.g.:

- `sw_rev_u03_p33_time_turns_rounds`
- `sw_rev_u04_p35_declare_spells_limits`

---

## Phase A: Create an outline benchmark (no citations yet)

### 1) Start with a universal “atomic” set (always include)

These are designed to appear in most TTRPG core texts and map to an engine loop (evaluate → choose → commit → next frame):

- **Roles & authority**: who decides what?
- **Uncertainty resolution**: default dice/cards procedure; how to read results
- **Time progression model**: turns/rounds/scenes; what advances time
- **What a player can do**: action options and limits (especially in combat)
- **What must be tracked**: authoritative state + where it’s recorded

Write these questions **system-agnostic**.

### 2) Add system-specific questions (still without citations)

Add a compact set that exercises the same primitives in that ruleset:

- combat sequencing nuances
- spell preparation/interruption timing
- XP/treasure rules
- specific tables with symbols
- “rules are guidelines / when in doubt” authority statements (if present)
- exploration cadence (turns, wandering checks, light duration)

### 3) Draft answers (explicitly marked as drafts)

Use a consistent draft marker so it’s obvious what still needs evidence:

- `answer`: start with `DRAFT (needs manual citations): ...`
- `_status`: `draft_needs_citations`

---

## Phase B: Manual citation loop (one question at a time)

For each benchmark entry:

### 1) Present the current entry

Show: `id`, `tier`, `question`, `answer`, `source_page`, and any current `gold_locations/required_gold`.

### 2) Ask for evidence (verbatim and minimal)

Request:

- **Exact quoted text** (copy/paste from PDF)
- **Printed page number(s)**
- **Exact section heading(s)** on those pages

Copy/paste prompts:

- “Please paste the exact paragraph(s) that answer this, plus page number(s) and the heading text on that page.”
- “Which sentences in the current answer are explicitly stated vs inferred? Let’s mark the inferred ones or remove them.”
- “If you were a player at the table, how would you ask this in one sentence?”

### 3) Claim-check the draft answer

For each sentence in `answer`:

- If it is **explicitly supported**, keep it (ideally with the same wording).
- If it is **not supported**:
  - delete it, or
  - rewrite it as **table practice** / **Referee judgment**, clearly labeled (not “the rules say”).

### 4) Rewrite question if needed

- If the query mixes two lookups (or lookup + reasoning), **split** into separate benchmark items.
- Prefer a single explicit question that a real player would ask.

### 5) Fill citations and gold

Update:

- `source_page`: printed pages, comma-separated
- `gold_locations`:
  - one entry per cited chunk location
  - `structural_path` matches visible headings exactly
- `required_gold` vs `supporting_gold`
- `required_gold_rationale` for anything non-obvious
- `_status`: set to `cited`

---

## Anchor guidance (S&W Revised specific)

When curating **Swords & Wizardry Revised**, treat **p73 “Referee Guide”** as *required gold* only when the answer depends on:

- “rules are guidelines”
- “there is not a rule for everything”
- “when in doubt, make a ruling”
- general Referee authority and adjudication

Do **not** force p73 into pure lookup questions unless it materially supports the answer.

---

## Output quality bar (what “done” looks like)

An entry is “done” when:

- `answer` contains **only** supported claims (with explicit hedging where rules are silent)
- `source_page` and `gold_locations.*.page` match **printed** page numbers
- `gold_locations.*.structural_path` matches **visible** headings
- `required_gold` includes the minimum chunks needed to answer correctly
- `expected_answer_summary` is a single crisp line

