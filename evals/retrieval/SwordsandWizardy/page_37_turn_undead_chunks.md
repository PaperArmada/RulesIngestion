# Page 37 (Turn Undead) — Chunk construction and retrieval

Full page 37 is relevant for sw_q05. Desired grouping:

- **[0,1,2]** — One chunk: intro + “roll ≥ number” + “D” = destroyed (single piece of information).
- **[3,4]** — One chunk: table caption + table (single piece of information).
- **[5]** — Turn Undead (Variant), distinct.
- **[6]** — Chaotic Clerics and the Undead, distinct.

How this is achieved depends on **min_chars** and **merge** behaviour.

## Table-with-caption merge (substrate_loader)

When merging by heading, if adding a **table** unit would exceed `max_chars` and the **last** unit in the current buffer is a short caption (≤ 100 chars), the merge flushes the buffer *without* that last unit and then merges the caption with the table. So we get [0,1,2] and [3,4] instead of [0,1,2,3] and [4].

## Raw evidence units (stageB)

| Order | unit_id (short) | structural_path | Content | len |
|-------|------------------|-----------------|---------|-----|
| 0 | 3c818d5a | Turning the Undead | Intro: roll 3d6, consult table | 199 |
| 1 | 251df129 | Turning the Undead | If roll ≥ number → turned, flee 3d6 rounds | 178 |
| 2 | fd308a05 | Turning the Undead | **"D" = destroyed automatically** | **105** |
| 3 | d67c4bb0 | Turning the Undead | "Turning Undead Table" header | 21 |
| 4 | f250a29e | Turning the Undead | Turn Undead table (HTML) | 1988 |
| 5 | 3788c850 | **Turn Undead (Variant)** | Referees may count as 1st level spell | **95** |
| 6 | c330a976 | Chaotic Clerics and the Undead | "D" for Chaotic = servitude | 699 |

## Merge behaviour

- Merge is by **(page, structural_path)**. So there are **3 merge groups** on the page:
  1. **Turning the Undead** → units 0,1,2,3,4 (same path)
  2. **Turn Undead (Variant)** → unit 5
  3. **Chaotic Clerics and the Undead** → unit 6

- Units under the same path are concatenated until **merge_max_chars** (2000). So "Turning the Undead" splits into (prose chunk) + (table chunk).

## With min_chars = 100 (current S&W config)

- **Filtered out** (len &lt; 100): units 3 (21), 5 (95).
- **In corpus**: 0, 1, 2, 4, 6 → folded then merged. Unit 2 (105) **“D” = destroyed** is retained; **Turn Undead (Variant)** (95 chars) is still dropped.
- Chunk IDs and boundaries differ from min_chars=150; run-time gold resolution uses the current pipeline so benchmark gold stays correct.

## With min_chars = 150 (legacy)

- **Filtered out** (len &lt; 150): units 2 (105), 3 (21), 5 (95).
- So the **"D" = destroyed** explanation and the **Turn Undead (Variant)** paragraph were **not in the corpus**.
- **In corpus**: 0, 1, 4, 6 → 3 chunks (prose 0+1, table 4, Chaotic 6).

## With min_chars = 20 and table-with-caption merge

- All units 0–6 pass. Merge gives the **desired** grouping:
  1. `78994bd0...` — [0,1,2]: intro + number rule + **"D" = destroyed**.
  2. `63c627fc...` — [3,4]: table caption + table (one chunk).
  3. `3788c850...` — [5]: Turn Undead (Variant).
  4. `c330a976...` — [6]: Chaotic Clerics and the Undead.

So with **min_chars=20** and the table-with-caption merge, the full page is in the corpus as **4 chunks** with the desired boundaries. Note: min_chars=20 changes merged chunk IDs elsewhere in the document; re-resolve other benchmark gold if you switch.

## Summary

- **They do not all end up merged into one chunk**: different headings (Turning the Undead vs Variant vs Chaotic) and the 2000-char cap force at least 3–4 chunks.
- **With min_chars=100** (current S&W config): “D” = destroyed (105 chars) is in the corpus; Turn Undead (Variant) (95 chars) is still below threshold. Gold is resolved at run time from `gold_locations`.
- **To have the full page as gold** (including the 95-char Variant): set min_chars=20 and use the table-with-caption merge. Then set sw_q05 gold to the **4** chunk IDs: `78994bd0...`, `63c627fc...`, `3788c850...`, `c330a976...`.
