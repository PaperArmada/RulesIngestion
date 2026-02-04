# Handoff: RulesIngestion Config Generation Improvements
**Date:** 2026-01-24  
**Type:** Refactor / Technical Debt  
**Last Updated:** 2026-01-24 09:20  

---

## 🚨 CURRENT STATE

### What's Working ✅
- RulesIngestion repo is now committed and structured; core pipeline sources + tests are tracked.
- Config generation currently uses `RulesetProfile` built from headings + block type distribution.
- Example configs show evolution drift (GMCore `v1` → `v8` → `v15`) with real-world noise issues.

### What's NOT Working ❌
- Configs can be generated from noisy slices (glossary/ads/legal), producing weak drift anchors and placeholder tags.
- Profile signature is based on raw headings, so noise dominates `doc_signature` and drift behavior.
- The generator/validator has no quality gate; it always attempts generation, even if profile is low-signal.

### Suspected Causes
1. `build_ruleset_profile` collects **all** `SectionHeader` strings without filtering noise.
2. Sample selection is the first N blocks, which biases toward early/late slices depending on run order.
3. `detect_structure_drift` requires both headings + distribution changes, which can miss drift or overfit a noisy sample.

### Debug Steps for Next Session
1. Review GMCore config evolution to spot noise drift anchors:
   - `RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/configs/sf2e-gmcore/v1.config.json`
   - `RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/configs/sf2e-gmcore/v8.config.json`
   - `RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/configs/sf2e-gmcore/v15.config.json`
2. Inspect `RulesetProfile` creation and drift logic to identify insertion points for filtering/sampling:
   - `RulesIngestion/config_profile.py` (see below)
3. Review generator retry/diagnostics structure:
   - `RulesIngestion/config_generator.py` (see below)

---

## Quick Pickup

### Commands
```bash
cd /media/drakosfire/Projects/DungeonOverMind/RulesIngestion
```

### Key Files
```
RulesIngestion/config_profile.py
  - build_ruleset_profile() L50-L82 (heading capture + sampling)
  - compute_doc_signature() L37-L47 (uses raw headings + block distribution)
  - detect_structure_drift() L85-L89 (requires both heading + distribution changes)

RulesIngestion/config_generator.py
  - generate_ruleset_config_with_retries() L31-L50 (no quality gate; retries validation only)
  - generate_ruleset_config_with_diagnostics() L60-L91 (diagnostics payload built here)

RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/configs/sf2e-gmcore/
  - v1.config.json (baseline)
  - v8.config.json (core-heavy headings, richer block distribution)
  - v15.config.json (noise headings: glossary/ads/legal)
```

---

## Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Baseline analysis of config evolution and generator gaps |
| Phase 2 | 🔄 In Progress | Design changes for profile filtering, sampling, and quality gates |
| Phase 3 | ⬜ Not Started | Implement + validate against GMCore configs |

---

## Proposed Improvements (No Code Yet)

### 1) Improve Profile Quality (Pre-LLM)
- **Filter noise headings** before building `heading_hierarchy` (glossary/ads/legal/publisher notices).
- **Split headings** into `core` vs `noise` buckets.
- **Sampling strategy**: take samples from early/mid/late *core* sections, not first N blocks.
- **Doc signature** should use *filtered* headings so drift anchors are stable.

### 2) Add Quality Gate Before Prompt Generation
Gate examples:
- Core heading count below threshold → skip generation, log diagnostics.
- Noise headings > core headings → reject or resample.
- No `SectionHeader` in distribution → reject.

### 3) Make Prompt Self-Policing
Rules to enforce:
- Forbid placeholder tags/aliases (e.g., `important_tag_1`).
- Require **traceability** for each alias/tag/override (heading + sample snippet).
- Enforce minimum counts; if unmet, return empty lists + `config_notes: insufficient signal`.

### 4) Automatic Slice Selection Loop
- If profile fails gate, **sample a different range** (early/mid core).
- Avoid known glossary/index/ads ranges via metadata.

### 5) Strengthen Drift Detection
- Consider drift levels:
  - **Low drift:** headings changed
  - **High drift:** headings + distribution changed
- Auto-regenerate on high drift; log and accept on low drift.

### 6) Post-LLM Validation
Reject configs with:
- Placeholder tags/aliases
- Drift headings from noise set
- Missing minimum counts

---

## Files Modified This Session (RulesIngestion repo)

### Created
- `RulesIngestion/Docs/rules_ingestion_architecture.md` — architecture overview
- `RulesIngestion/Docs/rules_ingestion_cleanup_plan.md` — cleanup plan

### Removed
- `RulesIngestion/docling_pipeline.py` (Docling removed)
- Docling/Paddle handoffs and reports (see git history)

### Moved/Archived
- `RulesIngestion/Rules/StarFinder2e/PlayerCore/archives/early-experiments-2026-01-24/` — early experiment outputs

### Dependencies
- Removed `docling`, `paddleocr`, `paddlepaddle-gpu` from `pyproject.toml`
- Regenerated `uv.lock`

---

## Context

Goal is to **update config generation** so it reliably produces high-signal configs without manual filtering or selection. GMCore config evolution reveals that noise headings and skewed slices degrade drift anchors and prompt outputs. Current profile/generator flow lacks filtering, sampling strategy, quality gates, and post-LLM validation.

---

## References

- **Config profile + drift logic:** `RulesIngestion/config_profile.py`
- **Config generator + diagnostics:** `RulesIngestion/config_generator.py`
- **GMCore config sequence:** `RulesIngestion/Rules/StarFinder2e/GMCore/outputs/runs/2026-01-23_23-47-32/configs/sf2e-gmcore/`
