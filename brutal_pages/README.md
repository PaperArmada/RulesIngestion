# Canonical markdown representations — brutal pages

Each `.md` file in this directory is a **canonical markdown representation** of one brutal-page PDF, derived purely from the extraction pipeline output.

## Source

- **Input:** `RulesIngestion/out/brutal_pages/<stem>/marker_stream.json`
- **Order:** Reading order of the marker stream (block_ordinal order on the page).
- **Conventions:**
  - `SectionHeader` → `## Heading`
  - `Text` → paragraph
  - `ListItem` → `- item`

## Contents

| Stem                                                    | Description (see Docs/BRUTAL-PAGES-20.md)          |
| ------------------------------------------------------- | -------------------------------------------------- |
| BrutalPage1–21                                          | 21 brutal pages (Alien Core, DnD PHB, Player Core) |
| DnD5eForms, DnD5eTable\*, DnD5eTable-multi              | S5/S6 D&D 5e tables and forms                      |
| FateCoreCheatSheet, FateCoreForms, FateCoreSingleColumn | S6/S7 Fate Core forms and control                  |
| Starfinder2eTable\*, Starfinder2eTables-multi           | S5 Starfinder 2e tables                            |
| Swords&WizardryCharacterSheet                           | S6 character sheet                                 |

## Regenerating

From repo root:

```bash
uv run python scripts/build_brutal_canonical_md.py
```

Outputs are written here; one `.md` per stem that has `marker_stream.json` in `out/brutal_pages/<stem>/`.
