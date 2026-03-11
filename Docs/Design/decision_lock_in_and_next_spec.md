# Decision Lock-In + Next Implementation Spec (Stages A/B / Retrieval Lab)

**Status:** Historical decision memo kept for rationale. The canonical current
baseline is documented in [v1/](v1/) and current workflow docs; this note is not
normative for the stabilized Mark III surface.

## Context

Stage A extraction is high-fidelity (minimal prose/structure loss). Benchmark results show the system is in “crack-finding” mode: refactor parity is proven, and the most meaningful improvements come from **candidate shaping / compositional retrieval support**, not from tuning retrieval knobs.

Clause-family projection variants demonstrate a strong compositional lift (especially on T2) but can introduce T1 regressions depending on parameterization. The current “sidecar” edge mechanism fires and adds candidates, but adds **zero gold** because it links sibling neighbors rather than true dependency pairs.

**Update (post-run):** Dual-list fusion (Index_U + Index_F, quota interleave) is now the **PHB default baseline** for this stage. It delivered 0 T1 regressions, higher T1 MRR, and doubled T2 Full-set@10; see § Findings and baseline update.

---

## One decision to lock in

1) **Keep canonical EvidenceUnits as the admissible evidence layer.**  
   EvidenceUnits remain the authoritative, immutable substrate for grounding and citation.

2) **Keep `sym_w1_m4` as the “safe projection” if you need a single default.**  
   `sym_w1_m4` provides conservative local context expansion while minimizing T1 regressions.

3) **Implement A1.2 dual-list fusion as the production path (now PHB default baseline).**  
   Retrieve from both:
   - the **canonical EvidenceUnit** index (precision / first-hit protection)
   - the **clause-family projection** index (coverage / composition)

   This aligns with the real use-cases:
   - T1 = precision, first hit
   - T2 = multi-unit composition, coverage

   Dual-list fusion prevents the predictable “signal dilution” regressions introduced by more aggressive clause-family windows, while preserving most of the T2 and full-set gains.

4) **Replace B1 neighbor edges with dependency-oriented pairing edges:**  
   The current sidecar is structurally reasonable but not dependency-oriented. Replace it with:
   - **delta → base pairing**
   - **exception → base pairing**

   These pairing edges are deterministic (lexical marker + local structural adjacency), and they target the kind of “retrieve these together” behavior required for compositional queries.

---

## Minimal spec: A1.2 Dual-list fusion

### Inputs
- `Index_U`: canonical EvidenceUnits (admissible)
- `Index_F`: clause-family projection (retrieval-only), recommended starting shape:
  - `sym_w3_m6` for coverage, but used through fusion rather than as a replacement

### Retrieval
Given query `q`:
- Retrieve `U = topK(Index_U, q, Ku)`
- Retrieve `F = topK(Index_F, q, Kf)`

Recommended starting values:
- `Ku = 12`
- `Kf = 12`
- Final candidate cap `Kfinal = 10`

### Dedupe rules
- EvidenceUnit hits are keyed by canonical `unit_id`.
- Clause-family hits map to their anchor `unit_id`.
- If both lists contain the same `unit_id`, keep the EvidenceUnit version as the “primary” candidate record and attach a metadata note that the family also matched.

### Merge policy (quota interleave)
Construct the final list `C` with a deterministic quota schedule:

1) **Protect precision (T1):**  
   Add up to `Qu` unit-hits first (in rank order):
   - `Qu = 6`

2) **Add coverage (T2):**  
   Interleave family hits until `Kfinal` is reached:
   - Add one from `F`, then one from remaining `U`, repeating
   - Skip any candidate whose `unit_id` is already present

3) **Backfill:**  
   If `C` still < `Kfinal`, fill from remaining `F`, then remaining `U` (in order), with dedupe.

### Optional “pinning” guardrail (deterministic)
If the top EvidenceUnit hit is very strong, keep it pinned:
- If `U[0].rank <= 3` (i.e., it exists), do not allow any family hit to appear above it in `C`.

This is purely a merge-order constraint, not a learned re-rank.

### Required metadata for auditability
Every candidate in `C` must carry:
- `source_list`: `unit` | `family` | `both`
- `family_params` if applicable (e.g., `sym_w3_m6`)
- `merge_reason`: `quota_unit` | `quota_family` | `backfill`
- `dedupe_of`: if candidate was skipped due to duplicate

---

## Minimal spec: dependency-oriented pairing edges (replace B1)

### Goal
Enable deterministic “retrieve these together” behavior without semantic inference and without LLM.

### Edge type 1: delta → base pairing

**Trigger (delta markers):**
- lexical patterns such as:
  - “increase by”
  - “at 5th/10th/15th/20th level”
  - “additional”
  - “instead of”
  - “bonus equals”
  - “in addition”

**Resolution (base target):**
- Within same `document_id`
- Prefer same `structural_path` (heading ancestry)
- Prefer same page; if none found, allow previous page within same structural_path
- Choose the nearest preceding unit that is **not** itself delta-marked

**Edge:**
- `unit_id(delta) -> unit_id(base)`

### Edge type 2: exception → base pairing

**Trigger (exception markers):**
- lexical patterns such as:
  - “except”
  - “unless”
  - “however”
  - “despite”
  - “but”

**Resolution (base target):**
- Within same `document_id`
- Same `structural_path`
- Nearest preceding unit that is not exception-marked

**Edge:**
- `unit_id(exception) -> unit_id(base)`

### Retrieval-time expansion policy (bounded)
When a candidate `u` is retrieved:
- If `u` has paired targets, union them into the candidate pool
- If `u` is a paired target of other units, union those sources as well (optional symmetric expansion)

Caps:
- At most 1 base per delta unit
- At most 1 base per exception unit
- At most `Emax = 6` paired adds per query

Tag expansions:
- `expanded_by = delta_base_pair` or `exception_base_pair`

---

## Recommended next run order (lowest noise)

1) ~~Baseline vs Dual-list fusion (with `sym_w3_m6` as Index_F)~~ **Done.**
2) ~~Add pairing edges expansion on top of fusion~~ **Done.**
3) Evaluate: T1 regression count, T2 Hit@10 and Full-set@10, overall MRR — **see Findings below.**

---

## Findings and baseline update (post-run)

**Run:** Baseline (phb_hybrid) vs Dual-list fusion (sym_w3_m6) vs Dual-list + pairing.  
**Comparison:** `out/retrieval_lab/stage_a_and_b/COMPARISON_BASELINE_DUAL_LIST_PAIRING.md`

### Result summary

| Experiment          | MRR    | T1 MRR | T1 regressions | T2 Hit@10 | T2 Full-set@10 |
|---------------------|--------|--------|----------------|-----------|-----------------|
| Baseline (hybrid)   | 0.4898 | 0.6400 | —              | 0.6667    | 0.0909          |
| Dual-list fusion    | 0.4912 | 0.6700 | **0**          | 0.6667    | **0.1818**      |
| Dual-list + pairing | 0.4912 | 0.6700 | **0**          | 0.6667    | **0.1818**      |

Dual-list fusion did exactly what we wanted: it **protected T1 completely** (0 regressions), **improved T1 ordering** (MRR 0.64 → 0.67), and **doubled T2 Full-set@10** (0.0909 → 0.1818) while keeping overall MRR flat-to-slightly-up (0.4898 → 0.4912). That’s a Pareto improvement on the things we care about.

### Baseline policy

**Dual-list fusion is now the PHB default retrieval policy for this stage.**  
Consume clause-family through **fusion** (Index_U + Index_F, quota interleave), not replacement. The earlier sweep showed “aggressive family-only” can win on T2 but introduces regressions; fusion captures the gain without the cost.

### What the numbers imply

- **T2 Hit@10 flat, Full-set@10 doubled:** We were already finding “some gold” in top-10 for most T2 queries; we weren’t finding the **complete set** of required evidence. So the gain is on **compositional coverage**, not “better retrieval of the first relevant clause.” Full-set@10 (or a GoldCoverage@10-style metric) is the right primary KPI for T2 going forward; Hit@10 is too coarse once you’re consistently getting some gold.
- **Pairing edges not moving metrics:** In this eval slice pairing didn’t show up — either triggers didn’t fire much, the expansion cap kept adds out of top-10, or the affected queries were already solved by fusion. That’s “not exercised / not needed here,” not evidence pairing is wrong. Pairing may still matter for broader corpora or for the “ongoing damage/unconscious” class when the relevant rule isn’t in the same page/heading neighborhood where families help.

### Interpretation check

T2 Full-set@10: 0.0909 → 0.1818 is 1/11 → 2/11 for 11 grounded T2 queries. Real gain.

### Next steps (minimal, high signal)

**A) Promote dual-list fusion as the PHB default.**  
Use dual-list fusion (sym_w3_m6, Qu=6, Kfinal=10) as the baseline config for PHB retrieval experiments. **Done as policy; config default in lab to follow.**

**B) Instrument pairing.**  
Metrics alone won’t show whether pairing is working. For the pairing run, log per query:

- number of pairing triggers fired
- number of candidates added by pairing
- whether any added candidate was gold
- whether any added candidate entered top-10
- whether pairing caused dedupe interactions (added a unit already present via family)

If “pairing fired 0 times” → refine triggers.  
If “pairing fired, added units, but never gold” → resolution is wrong (like the earlier sidecar).  
If “pairing added gold but not top-10” → adjust cap or integrate pairing earlier in candidate assembly.

**C) Treat Full-set@10 as primary T2 metric.**  
Use Full-set@10 (or GoldCoverage@10) as the main T2 KPI; keep Hit@10 as secondary.

### Discussion: pairing as bonus recall vs composition guarantee

Do we want pairing edges to be:

1. **Purely “bonus recall”** — only add candidates to the pool; no rank guarantee.
2. **A “composition guarantee”** — ensure base+delta / base+exception **co-appear** whenever one appears (e.g. apply pairing after retrieval but before final top-10 truncation, with a rule that paired units are inserted immediately after the triggering candidate, deterministic, capped).

Option (2) would make pairing visible in reported metrics more often. Open for next iteration.

---

## Notes

- EvidenceUnits remain pristine and admissible throughout.
- Clause-family projection remains retrieval-only and auditable.
- Pairing edges are deterministic, local, and dependency-oriented — addressing the known failure of the current “neighbor” sidecar.

