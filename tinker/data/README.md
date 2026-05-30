# tinker/data — preserved artifacts

Durable backups of resource-costly generated artifacts that otherwise live only
under the gitignored `out/tinker/`.

- `swcr_glossary_llm.json` — high-recall LLM-extracted glossary for SWCR (811
  terms + definitions, 32 acronyms), built by `tinker/scripts/build_llm_glossary.py`
  via Gemini over 715 units (M9). ~20 min / a few hundred API calls to produce.
  Replaces the M1 130-term regex glossary; failing-concept coverage went 1/8 → 6/8.
  Used as the proper HyDE shape-prior bridge (M9) and the re-seed source for the
  M8 cross-reference graph.
