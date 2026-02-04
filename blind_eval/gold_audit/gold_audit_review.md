# Gold chunk audit – review

For each block: confirm the chunk is a **good** gold (supports the answer).

- **keep** – Chunk clearly supports the answer; use full text as target_text or a tight substring.
- **trim** – Only part of the chunk is gold; set target_text to that portion.
- **expand** – Chunk is relevant but too narrow; ideal gold would include adjacent context (e.g. header + body). Note in reviewer_notes.
- **drop** – Irrelevant or wrong; will not appear in gold reference.

After review, set `evaluation_status` and `target_text` in `gold_audit.json` (or re-export from this workflow).

---

## blind_001_01

**Question:** What abilities can cancel out Vent Gas when a Barathu uses it?

**Expected answer summary:** Gust of Wind can blow away the gas cloud. Dispel Magic could counter it if it's magical. Alternative senses (scent, precise senses) can detect through concealment.

### Gold chunk 1 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/9/Text/12`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 9 · **Path:** `/page/9/Text/12`

**Chunk text:**

```
You vent gas to propel yourself forward. All squares in a  5-foot emanation become filled with gas. All creatures in  the gas become concealed, and all creatures outside the gas  become concealed to creatures within it. This gas disperses at  the beginning of your next turn.
```

**Status:** keep · **Notes:** Vent Gas: describes gas/emanation; supports what can affect it (wind, dispel). · **target_text:** (optional substring)

### Gold chunk 2 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-330-363::/page/6/Text/2`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-330-363` · **Page:** 6 · **Path:** `/page/6/Text/2`

**Chunk text:**

```
**GUST OF WIND **[two-actions] **SPELL 1**

**AIR** **CONCENTRATE** **MANIPULATE**

**Traditions** arcane, primal

**Area** 60-foot line

**Defense** Fortitude; **Duration** until the start of your next turn A violent wind issues forth from your palm, blowing from the  point where you are when you Cast the Spell to the line's  opposite end. The wind extinguishes small non-magical fires,  disperses fog and mist, blows objects of light Bulk or less  around, and pushes larger objects. Large or smaller creatures  in the area must attempt a Fortitude save. Large or smaller  creatures that later move into the gust must attempt the save  on entering.
```

**Status:** keep · **Notes:** Gust of Wind: 'disperses fog and mist' directly answers. · **target_text:** (optional substring)

### Gold chunk 3 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-294-329::/page/7/Text/7`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-294-329` · **Page:** 7 · **Path:** `/page/7/Text/7`

**Chunk text:**

```
Some spells, such as *dispel magic*, can be used to eliminate  the effects of other spells. At least one creature, object, or  manifestation of the spell you are trying to counteract must  be within range of the spell that you are using. You attempt  a counteract check (page 423) using your Charisma (or other  spellcasting attribute modifier) and your proficiency bonus  for spell attack rolls.
```

**Status:** keep · **Notes:** dispel magic: can eliminate effects of other spells. · **target_text:** (optional substring)

## blind_001_02

**Question:** Suggest some complimentary feats for a Level 9 Lashunta Solarian

**Expected answer summary:** Lashunta feats: Guarded Thoughts (mental protection), Psychic Mastery (enhanced telepathy). Solarian feats at level 9 from class table. Synergies with telepathy + melee combat style.

### Gold chunk 4 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073::/page/1/Text/12`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073` · **Page:** 1 · **Path:** `/page/1/Text/12`

**Chunk text:**

```
Damayas tend to be tall and graceful with delicate features and  are traditionally pushed toward artistic or intellectual pursuits  and political occupations. Korashas are shorter, more muscular,  and gravitate toward military service, manual labor, and wartime  leadership. Regardless of heritage, all lashuntas have short  forehead antennae that focus their telepathy, with colorful  bumps and facial markings unique to each individual. Lashuntas  produce pheromones that subtly broadcast their moods in ways  that other ancestries might find alluring or unnerving.
```

**Status:** keep · **Notes:** Lashunta flavor: telepathy/synergy context for feats. · **target_text:** (optional substring)

### Gold chunk 5 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073::/page/3/SectionHeader/24`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073` · **Page:** 3 · **Path:** `/page/3/SectionHeader/24`

**Chunk text:**

```
**GUARDED THOUGHTS** **FEAT 9**
```

**Status:** expand · **Notes:** GUARDED THOUGHTS: header only; ideal gold includes feat body. · **target_text:** (optional substring)

### Gold chunk 6 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073::/page/3/SectionHeader/28`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073` · **Page:** 3 · **Path:** `/page/3/SectionHeader/28`

**Chunk text:**

```
**PSYCHIC MASTERY** **FEAT 9**
```

**Status:** expand · **Notes:** PSYCHIC MASTERY: header only; ideal gold includes feat body. · **target_text:** (optional substring)

### Gold chunk 7 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149::/page/2/Table/2`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149` · **Page:** 2 · **Path:** `/page/2/Table/2`

**Chunk text:**

```
Your LevelClass Features1Ancestry and background, attribute boosts,
initial proficiencies, stellar attunement, solar
manifestations, solarian feat2Skill feat, solarian feat3General feat, skill increase, stellar resilience4Skill feat, solarian feat5Ancestry feat, attribute boosts, skill increase,
solar weapon expertise6Skill feat, solarian feat7General feat, skill increase, stellar senses,
weapon specialization8Skill feat, solarian feat9Ancestry feat, skill increase, solarian
expertise, stellar partition10Attribute boosts, skill feat, solarian feat11Armor expertise, general feat, skill increase12Skill feat, solarian feat13Ancestry feat, skill increase, solarian weapon
mastery14Skill feat, solarian feat15Attribute boosts, general feat, gravitas,
greater weapon specialization, skill increase16Skill feat, solarian feat17Ancestry feat, armor mastery, skill increase,
solarian mastery18Skill feat, solarian feat19General feat, skill increase, stellar paragon20Attribute boosts, skill feat, solarian feat
```

**Status:** keep · **Notes:** Solarian table: level 9 row shows solarian expertise, stellar partition. · **target_text:** (optional substring)

### Gold chunk 8 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149::/page/3/Text/8`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149` · **Page:** 3 · **Path:** `/page/3/Text/8`

**Chunk text:**

```
Through sheer will, you call forth a tangible weapon forged  from the essence of stars. This weapon is an extension of  yourself, and you can change its form with meditation. When  manifesting your weapon, it appears in a free hand of your  choice. If it has the free-hand trait, it can manifest in any  hand. Your solar weapon is a martial melee weapon. It deals  1d8 of your choice of bludgeoning, piercing, or slashing  damage with the attuned and solarian traits.
```

**Status:** keep · **Notes:** Solar weapon: melee weapon/synergy for build. · **target_text:** (optional substring)

## blind_001_03

**Question:** Can I use Redirect Current to power up a console?

**Expected answer summary:** Redirect Current is triggered by taking electricity damage and redirects it. To power devices, you'd need a different ability like the one that lets you 'use to power technological devices'.

### Gold chunk 9 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/16/Text/17`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 16 · **Path:** `/page/16/Text/17`

**Chunk text:**

```
**Redirect Current** [reaction] (electricity) **Frequency** once per hour;  **Trigger** You take electricity damage, and your electricity  resistance doesn't reduce this damage to 0; **Effect** After  being shocked, you seize the electricity coursing through  your body and redirect it at another creature within 30  feet. That creature can't have already taken damage  from the effect that damaged you. That creature takes  electricity damage equal to the amount of Hit Points you  lost from the triggering electricity damage (basic Reflex  save using your class DC or spell DC, whichever is higher).
```

**Status:** keep · **Notes:** Redirect Current: trigger = electricity damage, redirect at creature; no powering devices. · **target_text:** (optional substring)

### Gold chunk 10 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/16/Text/20`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 16 · **Path:** `/page/16/Text/20`

**Chunk text:**

```
Your body produces an overabundance of electrical energy,  which you can emit as a blast of lightning or use to power  technological devices. You can cast the *electric arc* cantrip as  a divine innate spell at will. A cantrip is heightened to a spell  rank equal to half your level rounded up.
```

**Status:** keep · **Notes:** 'use to power technological devices' directly answers alternative. · **target_text:** (optional substring)

### Gold chunk 11 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/16/Text/34`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 16 · **Path:** `/page/16/Text/34`

**Chunk text:**

```
Your ability to control and empower technological devices
```

**Status:** trim · **Notes:** Fragment; ideal gold includes full ability name + sentence. · **target_text:** (optional substring)

## blind_001_04

**Question:** Can I use Side Step to hit something that is inanimate or maybe a robot?

**Expected answer summary:** Sidestep triggers when 'a creature misses you'. Robots are creatures (with tech trait) so YES. Inanimate objects are NOT creatures, so NO. The answer depends on whether it's a creature-robot or an inanimate hazard.

### Gold chunk 12 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113::/page/13/SectionHeader/37`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113` · **Page:** 13 · **Path:** `/page/13/SectionHeader/37`

**Chunk text:**

```
**SIDESTEP **[reaction] **FEAT 8**
```

**Status:** expand · **Notes:** SIDESTEP: header only; need trigger/body for creature vs inanimate. · **target_text:** (optional substring)

### Gold chunk 13 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113::/page/12/Text/44`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113` · **Page:** 12 · **Path:** `/page/12/Text/44`

**Chunk text:**

```
**Trigger** A creature misses you with a melee Strike.
```

**Status:** keep · **Notes:** Trigger 'a creature misses you'—direct answer. · **target_text:** (optional substring)

### Gold chunk 14 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-232-249::/page/4/Text/20`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-232-249` · **Page:** 4 · **Path:** `/page/4/Text/20`

**Chunk text:**

```
Inanimate objects and hazards are immune to bleed, death effects, disease, healing, mental effects, nonlethal attacks, poison, spirit, vitality, void, as well as the doomed, drained, fatigued, paralyzed, sickened, and unconscious conditions. Conscious, thinking items are not immune to mental effects. Many objects are immune to other conditions, at the GM's discretion. For instance, a sword can't move, so it can't take a penalty to its Speed, but a spinning blade trap might be affected.
```

**Status:** keep · **Notes:** Inanimate objects/hazards not creatures; supports Sidestep answer. · **target_text:** (optional substring)

### Gold chunk 15 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/Text/9`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/Text/9`

**Chunk text:**

```
You were created to fight other synthetic creatures. When  you roll a critical hit against a creature with the tech trait, the  target becomes glitching 1.
```

**Status:** drop · **Notes:** Wrong topic (Android glitching vs tech trait, not Sidestep/creature). · **target_text:** (optional substring)

## blind_001_05

**Question:** I don't really understand perception?

**Expected answer summary:** Perception measures awareness of your environment. Check = d20 + Wis + proficiency + bonuses/penalties. Used for noticing things (Seek), social situations (Sense Motive), and initiative in encounters. Perception DC = 10 + total modifier.

### Gold chunk 16 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/8/SectionHeader/21`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 8 · **Path:** `/page/8/SectionHeader/21`

**Chunk text:**

```
PERCEPTION
```

**Status:** expand · **Notes:** PERCEPTION: section header only. · **target_text:** (optional substring)

### Gold chunk 17 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/8/Text/22`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 8 · **Path:** `/page/8/Text/22`

**Chunk text:**

```
Perception measures your ability to be aware of your  environment. Every creature has Perception, which works  with and is limited by a creature's senses. (Details on senses  and detecting things begin on page 424.) Whenever you need  to attempt a check based on your awareness, you'll attempt  a Perception check. Your Perception uses your Wisdom  modifier, so you'll use the following formula when attempting  a Perception check.
```

**Status:** keep · **Notes:** Perception measures awareness; core definition. · **target_text:** (optional substring)

### Gold chunk 18 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/8/Text/23`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 8 · **Path:** `/page/8/Text/23`

**Chunk text:**

```
**Perception check result = d20 roll + Wisdom modifier + ** **proficiency bonus + other bonuses + penalties**
```

**Status:** keep · **Notes:** Formula: d20 + Wis + proficiency + bonuses. · **target_text:** (optional substring)

### Gold chunk 19 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/9/Text/1`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 9 · **Path:** `/page/9/Text/1`

**Chunk text:**

```
Nearly all creatures are at least trained in Perception,  so you will almost always add a proficiency bonus to your  Perception modifier. You might add a circumstance bonus  for advantageous situations or environments and typically  get status bonuses from spells or other magical effects.  Items can also grant you a bonus to Perception, typically  in a certain situation. For instance, the retinal reflectors  augmentation grants a +1 item bonus to Perception checks  to Seek.
```

**Status:** keep · **Notes:** Proficiency/bonuses paragraph. · **target_text:** (optional substring)

### Gold chunk 20 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/9/Text/3`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 9 · **Path:** `/page/9/Text/3`

**Chunk text:**

```
Many abilities are compared to your **Perception DC** to  determine whether they succeed. As with any DC based on  a modifier, your Perception DC is 10 + your total Perception  modifier.
```

**Status:** keep · **Notes:** Perception DC = 10 + modifier. · **target_text:** (optional substring)

### Gold chunk 21 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/9/Text/5`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 9 · **Path:** `/page/9/Text/5`

**Chunk text:**

```
Often, you'll roll a Perception check to determine your order  in initiative. When you do this, instead of comparing the  result against a DC, the GM will put the results for everyone  in the encounter in order. The creature with the highest result  acts first, the creature with the second-highest result goes  second, and so on. Sometimes you may be called on to roll  a skill check for initiative instead, but you'll compare results  just as if you had rolled Perception. The full rules for initiative  are found in the rules for encounter mode on page 427.
```

**Status:** keep · **Notes:** Perception for initiative. · **target_text:** (optional substring)

## blind_001_06

**Question:** I need help deciding between Covering Fire or I'll be back as my 6th level feat I'm playing an Android

**Expected answer summary:** Covering Fire: Ranged Strike (1 action) or Area/Auto-Fire (2 actions) to suppress target and give ally -2 penalty protection. Active team support. I'll Be Back: Free action 1/day when you wake from unconscious - Stand and draw weapon immediately. Recovery insurance. Choice depends on playstyle: team support (Covering Fire) vs personal resilience (I'll Be Back).

### Gold chunk 22 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161::/page/7/SectionHeader/5`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161` · **Page:** 7 · **Path:** `/page/7/SectionHeader/5`

**Chunk text:**

```
**COVERING FIRE **[one-action]** OR **[two-actions] **FEAT 6**
```

**Status:** expand · **Notes:** Covering Fire: header only. · **target_text:** (optional substring)

### Gold chunk 23 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161::/page/7/Text/8`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161` · **Page:** 7 · **Path:** `/page/7/Text/8`

**Chunk text:**

```
You make a well placed shot or unleash a hail of fire to cover  your allies. Make a ranged Strike against a target and select  one ally within range of the same attack. If your Strike hits  your target, you deal no damage, but the targeted creature  becomes suppressed and takes a –2 circumstance penalty  on attacks made against your ally until the end of your next  turn.
```

**Status:** keep · **Notes:** Covering Fire: Strike, suppress, -2 penalty to attacks vs ally. · **target_text:** (optional substring)

### Gold chunk 24 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161::/page/7/Text/9`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161` · **Page:** 7 · **Path:** `/page/7/Text/9`

**Chunk text:**

```
You can use Covering Fire as a 2-action activity to Area  Fire or Auto-Fire instead of making a ranged Strike, affecting  targets that fail their save.
```

**Status:** keep · **Notes:** 2-action Area Fire / Auto-Fire option. · **target_text:** (optional substring)

### Gold chunk 25 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161::/page/7/SectionHeader/15`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161` · **Page:** 7 · **Path:** `/page/7/SectionHeader/15`

**Chunk text:**

```
**I'LL BE BACK **[free-action] **FEAT 6**
```

**Status:** expand · **Notes:** I'll Be Back: header only. · **target_text:** (optional substring)

### Gold chunk 26 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161::/page/7/Text/18`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161` · **Page:** 7 · **Path:** `/page/7/Text/18`

**Chunk text:**

```
**Frequency** once per day
```

**Status:** trim · **Notes:** Frequency only; need trigger + effect for full answer. · **target_text:** (optional substring)

### Gold chunk 27 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161::/page/7/Text/19`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161` · **Page:** 7 · **Path:** `/page/7/Text/19`

**Chunk text:**

```
**Trigger** You regain consciousness after being unconscious. Even when you're downed, you get right back into the thick
```

**Status:** trim · **Notes:** Trigger fragment (mid-sentence). · **target_text:** (optional substring)

### Gold chunk 28 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161::/page/7/Text/20`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-150-161` · **Page:** 7 · **Path:** `/page/7/Text/20`

**Chunk text:**

```
of things once recovered. You Stand and Interact to draw a  weapon or grab an unattended weapon.
```

**Status:** trim · **Notes:** Effect fragment (continuation). · **target_text:** (optional substring)

## blind_001_07

**Question:** Can a character with only the Solar Nimbus feat use Nimbus Surge when an enemy within reach leaves a square during a move action?

**Expected answer summary:** Yes. Nimbus Surge triggers when a creature within reach 'leaves a square during a move action it's using'. Solar Nimbus feat grants Nimbus Surge reaction but without attunement benefits (no graviton/photon bonuses).

### Gold chunk 29 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149::/page/3/SectionHeader/1`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149` · **Page:** 3 · **Path:** `/page/3/SectionHeader/1`

**Chunk text:**

```
**NIMBUS SURGE **[reaction]
```

**Status:** expand · **Notes:** Nimbus Surge: header only. · **target_text:** (optional substring)

### Gold chunk 30 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149::/page/3/Text/3`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149` · **Page:** 3 · **Path:** `/page/3/Text/3`

**Chunk text:**

```
**Trigger** A creature within your reach uses a manipulate action  or a move action, makes a ranged attack, or leaves a square  during a move action it's using.
```

**Status:** keep · **Notes:** Trigger includes 'leaves a square during a move action'. · **target_text:** (optional substring)

### Gold chunk 31 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149::/page/3/Text/4`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149` · **Page:** 3 · **Path:** `/page/3/Text/4`

**Chunk text:**

```
Your nimbus surges with energy, forcing an opening in your foe's  defenses. Make a melee Strike against the triggering creature.  This Strike doesn't count toward your multiple attack penalty,  and your multiple attack penalty doesn't apply to this Strike.
```

**Status:** keep · **Notes:** Effect: Strike, doesn't count toward MAP. · **target_text:** (optional substring)

### Gold chunk 32 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-174-181::/page/4/SectionHeader/42`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-174-181` · **Page:** 4 · **Path:** `/page/4/SectionHeader/42`

**Chunk text:**

```
**SOLAR NIMBUS** **FEAT 6**
```

**Status:** expand · **Notes:** Solar Nimbus: header only. · **target_text:** (optional substring)

### Gold chunk 33 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-174-181::/page/4/Text/46`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-174-181` · **Page:** 4 · **Path:** `/page/4/Text/46`

**Chunk text:**

```
You gain the Nimbus Surge reaction (page 141), but do not  gain any additional benefits based on your attunement.
```

**Status:** keep · **Notes:** Grants Nimbus Surge without attunement benefits. · **target_text:** (optional substring)

## blind_001_08

**Question:** Do Androids with Revivification Protocol need to make recovery checks?

**Expected answer summary:** No. Revivification Protocol triggers 'when you are about to attempt a recovery check'. Instead of rolling, you auto-revive to 1 HP and lose dying/unconscious. The ability replaces the recovery check.

### Gold chunk 34 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/SectionHeader/37`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/SectionHeader/37`

**Chunk text:**

```
**REVIVIFICATION PROTOCOL **[free-action] **FEAT 13**
```

**Status:** expand · **Notes:** Revivification Protocol: header only. · **target_text:** (optional substring)

### Gold chunk 35 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/Text/41`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/Text/41`

**Chunk text:**

```
**Trigger** You have the dying condition and are about to  attempt a recovery check.
```

**Status:** keep · **Notes:** Trigger: about to attempt recovery check—replaces check. · **target_text:** (optional substring)

### Gold chunk 36 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/Text/42`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/Text/42`

**Chunk text:**

```
Your nanites are programmed to automatically revive you.  You are restored to 1 Hit Point, lose the dying and unconscious  conditions, and can act normally on this turn. You gain or  increase the wounded condition as normal when losing the  dying condition in this way.
```

**Status:** keep · **Notes:** Effect: restored to 1 HP, lose dying/unconscious. · **target_text:** (optional substring)

### Gold chunk 37 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/15/SectionHeader/3`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 15 · **Path:** `/page/15/SectionHeader/3`

**Chunk text:**

```
RECOVERY CHECKS
```

**Status:** expand · **Notes:** RECOVERY CHECKS: section header. · **target_text:** (optional substring)

### Gold chunk 38 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/15/Text/4`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 15 · **Path:** `/page/15/Text/4`

**Chunk text:**

```
While you're dying, attempt a recovery check at the start  of each of your turns. This is a flat check with a DC equal  to 10 + your current dying value to see if you get better  or worse.
```

**Status:** keep · **Notes:** Recovery check at start of turn; context for 'replaces'. · **target_text:** (optional substring)

## blind_001_09

**Question:** Can a Shirren use Undying more than once per day?

**Expected answer summary:** Need to check if Undying has a frequency limit. The feat text says 'You have died once before' suggesting narrative limitation, but no explicit 'once per day' frequency listed. May be unlimited use.

### Gold chunk 39 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/13/SectionHeader/46`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 13 · **Path:** `/page/13/SectionHeader/46`

**Chunk text:**

```
**UNDYING **[reaction] **FEAT 17**
```

**Status:** expand · **Notes:** Undying: header only. · **target_text:** (optional substring)

### Gold chunk 40 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/13/Text/50`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 13 · **Path:** `/page/13/Text/50`

**Chunk text:**

```
**Trigger** You have the dying condition and are about to  attempt a recovery check.
```

**Status:** keep · **Notes:** Trigger: about to attempt recovery check. · **target_text:** (optional substring)

### Gold chunk 41 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/13/Text/51`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 13 · **Path:** `/page/13/Text/51`

**Chunk text:**

```
You have died once before and have no intention of dying  ever again; your soul stubbornly resuscitates your body  when you would otherwise perish. You are restored to 1  Hit Point, lose the dying and unconscious conditions, and  can act normally on this turn. You increase your wounded  condition as normal.
```

**Status:** keep · **Notes:** Effect: no frequency in text; supports 'may be unlimited'. · **target_text:** (optional substring)

## blind_001_10

**Question:** What's the difference between Android Revivification Protocol and Shirren Undying?

**Expected answer summary:** Both restore to 1 HP and remove dying/unconscious. Revivification Protocol (Android, Feat 13): Triggers before recovery check, replaces it. Undying (Shirren, Feat 17): Triggers when you would otherwise perish. Both increase wounded. Key difference: trigger timing (before check vs at death) and level requirement (13 vs 17).

### Gold chunk 42 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/SectionHeader/37`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/SectionHeader/37`

**Chunk text:**

```
**REVIVIFICATION PROTOCOL **[free-action] **FEAT 13**
```

**Status:** keep · **Notes:** Revivification (Android): one of two feats compared. · **target_text:** (optional substring)

### Gold chunk 43 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/Text/41`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/Text/41`

**Chunk text:**

```
**Trigger** You have the dying condition and are about to  attempt a recovery check.
```

**Status:** keep · **Notes:** Trigger: before recovery check. · **target_text:** (optional substring)

### Gold chunk 44 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/Text/42`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/Text/42`

**Chunk text:**

```
Your nanites are programmed to automatically revive you.  You are restored to 1 Hit Point, lose the dying and unconscious  conditions, and can act normally on this turn. You gain or  increase the wounded condition as normal when losing the  dying condition in this way.
```

**Status:** keep · **Notes:** Android effect text. · **target_text:** (optional substring)

### Gold chunk 45 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/13/SectionHeader/46`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 13 · **Path:** `/page/13/SectionHeader/46`

**Chunk text:**

```
**UNDYING **[reaction] **FEAT 17**
```

**Status:** keep · **Notes:** Undying (Shirren): second feat. · **target_text:** (optional substring)

### Gold chunk 46 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/13/Text/50`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 13 · **Path:** `/page/13/Text/50`

**Chunk text:**

```
**Trigger** You have the dying condition and are about to  attempt a recovery check.
```

**Status:** keep · **Notes:** Trigger: same structure. · **target_text:** (optional substring)

### Gold chunk 47 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/13/Text/51`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 13 · **Path:** `/page/13/Text/51`

**Chunk text:**

```
You have died once before and have no intention of dying  ever again; your soul stubbornly resuscitates your body  when you would otherwise perish. You are restored to 1  Hit Point, lose the dying and unconscious conditions, and  can act normally on this turn. You increase your wounded  condition as normal.
```

**Status:** keep · **Notes:** Shirren effect text. · **target_text:** (optional substring)

## batch_002_01

**Question:** What penalties do I have while prone?

**Expected answer summary:** Prone: You're off-guard (-2 circumstance penalty to AC) and take -2 circumstance penalty to attack rolls. Limited to Crawl and Stand move actions. Standing ends prone.

### Gold chunk 48 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/13/Text/96`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 13 · **Path:** `/page/13/Text/96`

**Chunk text:**

```
**Prone:** You're lying on the ground and easier to attack.
```

**Status:** trim · **Notes:** Prone one-liner; need full condition text for penalties. · **target_text:** (optional substring)

### Gold chunk 49 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/15/Text/6`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 15 · **Path:** `/page/15/Text/6`

**Chunk text:**

```
You're lying on the ground. You are off-guard and take a –2  circumstance penalty to attack rolls. The only move actions  you can use while you're prone are Crawl and Stand. Standing  up ends the prone condition. You can Take Cover while prone  to hunker down and gain greater cover against ranged attacks,  even if you don't have an object to get behind, which grants  you a +4 circumstance bonus to AC against ranged attacks (but  you remain off-guard).
```

**Status:** keep · **Notes:** Prone full: off-guard, -2 attack, Crawl/Stand only. · **target_text:** (optional substring)

## batch_002_02

**Question:** Can I use Stealth to Hide while I'm prone?

**Expected answer summary:** Yes. Hide requires cover/greater cover or concealment. Prone doesn't prevent Hide. Prone only limits you to Crawl and Stand for movement actions, not other actions.

### Gold chunk 50 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209::/page/25/Text/9`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209` · **Page:** 25 · **Path:** `/page/25/Text/9`

**Chunk text:**

```
You huddle behind cover or greater cover or deeper into  concealment to become hidden, rather than observed.  The GM rolls your Stealth check in secret and compares  the result to the Perception DC of each creature you're  observed by but that you have cover or greater cover  against or are concealed from. You get a +2 circumstance  bonus to your check if you have standard cover (or +4  from greater cover).
```

**Status:** keep · **Notes:** Hide: cover/concealment required. · **target_text:** (optional substring)

### Gold chunk 51 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/15/Text/6`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 15 · **Path:** `/page/15/Text/6`

**Chunk text:**

```
You're lying on the ground. You are off-guard and take a –2  circumstance penalty to attack rolls. The only move actions  you can use while you're prone are Crawl and Stand. Standing  up ends the prone condition. You can Take Cover while prone  to hunker down and gain greater cover against ranged attacks,  even if you don't have an object to get behind, which grants  you a +4 circumstance bonus to AC against ranged attacks (but  you remain off-guard).
```

**Status:** keep · **Notes:** Prone limits only move actions; doesn't prevent Hide. · **target_text:** (optional substring)

## batch_002_03

**Question:** What changes when I gain the wounded condition?

**Expected answer summary:** Wounded increases your dying value when you gain dying condition. If you gain dying while wounded, increase dying by your wounded value. Wounded ends when restored to full HP and rest 10 minutes, or via Treat Wounds.

### Gold chunk 52 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/17/Text/23`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 17 · **Path:** `/page/17/Text/23`

**Chunk text:**

```
and don't already have the wounded condition, you become  wounded 1. If you already have the wounded condition  when you lose the dying condition, your wounded condition  value increases by 1. If you gain the dying condition while  wounded, increase your dying condition value by your  wounded value.
```

**Status:** trim · **Notes:** Wounded mid-paragraph; expand for full wounded definition. · **target_text:** (optional substring)

### Gold chunk 53 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/17/Text/24`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 17 · **Path:** `/page/17/Text/24`

**Chunk text:**

```
The wounded condition ends if someone successfully  restores Hit Points to you using Treat Wounds, or if you  are restored to full Hit Points by any means and rest for 10  minutes.
```

**Status:** keep · **Notes:** Wounded ends: Treat Wounds or full HP + 10 min rest. · **target_text:** (optional substring)

## batch_002_04

**Question:** If I'm dying and taking persistent damage, what happens during my turn?

**Expected answer summary:** Start of turn: attempt recovery check (dying). End of turn: take persistent damage. If persistent damage keeps you at/below 0 HP, increase dying by 1. Dangerous: dying recovery happens first, then persistent damage can undo recovery.

### Gold chunk 54 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/12/Text/25`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 12 · **Path:** `/page/12/Text/25`

**Chunk text:**

```
You're bleeding out or otherwise at death's door. While you  have this condition, you're unconscious. Dying always includes  a value, and if it ever reaches dying 4, you die. When you're  dying, you must attempt a recovery check (page 403) at the  start of your turn each round to determine whether you get  better or worse. Your dying condition increases by 1 if you  take damage while dying, or by 2 if you take damage from an  enemy's critical hit or a critical failure on your save.
```

**Status:** keep · **Notes:** Dying: recovery at start; damage increases dying. · **target_text:** (optional substring)

### Gold chunk 55 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/4/ListItem/20`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 4 · **Path:** `/page/4/ListItem/20`

**Chunk text:**

```
If you have a persistent damage condition, you take the  damage at this point. After you take the damage, you can  attempt the flat check to end the persistent damage. You  then attempt any saving throws for ongoing afflictions.  Many other conditions change at the end of your turn,  such as the frightened condition decreasing in severity.  These take place after you've taken any persistent  damage, attempted flat checks to end the persistent  damage, and attempted saves against any afflictions.
```

**Status:** keep · **Notes:** End of turn: persistent damage at this point. · **target_text:** (optional substring)

### Gold chunk 56 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/15/Text/2`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 15 · **Path:** `/page/15/Text/2`

**Chunk text:**

```
You're taking damage from an ongoing effect, such as from  being lit on fire. This appears as "X persistent [type] damage,"  where "X" is the amount of damage dealt and "[type]" is the  damage type. Like normal damage, it can be doubled or halved  based on the results of an attack roll or saving throw. Instead  of taking persistent damage immediately, you take it at the end  of each of your turns as long as you have the condition, rolling  any damage dice anew each time. After you take persistent  damage, roll a DC 15 flat check to see if you recover from the  persistent damage. If you succeed, the condition ends.
```

**Status:** keep · **Notes:** Persistent damage at end of each turn. · **target_text:** (optional substring)

### Gold chunk 57 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/15/Text/4`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 15 · **Path:** `/page/15/Text/4`

**Chunk text:**

```
While you're dying, attempt a recovery check at the start  of each of your turns. This is a flat check with a DC equal  to 10 + your current dying value to see if you get better  or worse.
```

**Status:** keep · **Notes:** Recovery check at start of turn. · **target_text:** (optional substring)

## batch_002_05

**Question:** Does the concealed condition stack with cover?

**Expected answer summary:** They don't 'stack' additively. Concealed imposes DC 5 flat check before attack roll. Cover gives +2 AC/Reflex bonus (standard) or +4 (greater). Both can apply - attacker must pass flat check AND beat higher AC.

### Gold chunk 58 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/2/Text/6`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 2 · **Path:** `/page/2/Text/6`

**Chunk text:**

```
A concealed creature is in mist, within dim light, or amid  something else that obscures sight but isn't a physical  barrier. When you target a creature that's concealed  from you, you must attempt a DC 5 flat check before  you roll to determine your effect. If you fail, you don't  affect the target. The concealed condition doesn't change  which of the main categories of detection apply. A  creature in a light fog bank is still observed even though  it's concealed.
```

**Status:** keep · **Notes:** Concealed: DC 5 flat check before affecting target. · **target_text:** (optional substring)

### Gold chunk 59 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/11/Text/17`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 11 · **Path:** `/page/11/Text/17`

**Chunk text:**

```
You're difficult for one or more creatures to see due to thick  fog or some other obscuring feature. You can be concealed  to some creatures but not others. While concealed, you can  still be observed, but you're tougher to target. A creature  that you're concealed from must succeed at a DC 5 flat  check when targeting you with an attack, spell, or other  effect. If the check fails, you aren't affected. Area effects  aren't subject to this flat check.
```

**Status:** keep · **Notes:** Concealed condition text. · **target_text:** (optional substring)

### Gold chunk 60 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/10/Text/9`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 10 · **Path:** `/page/10/Text/9`

**Chunk text:**

```
When you're behind an obstacle that could block weapons,  guard you against explosions, and make you harder to detect,  you're behind cover. Standard cover gives you a +2 circumstance  bonus to AC, to Reflex saves against area effects, and to Stealth  checks to Hide, Sneak, or otherwise avoid detection. You can  increase this to greater cover using the Take Cover basic action  (page 410), increasing the circumstance bonus to +4. If cover is  especially light, typically when it's provided by a creature, you  have lesser cover, which grants a +1 circumstance bonus to AC.  A creature with standard cover or greater cover can attempt to  use Stealth to Hide, but lesser cover isn't sufficient.
```

**Status:** keep · **Notes:** Cover: +2/+4 circumstance bonus to AC, Reflex. · **target_text:** (optional substring)

### Gold chunk 61 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/10/Table/10`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 10 · **Path:** `/page/10/Table/10`

**Chunk text:**

```
Type of CoverBonusCan HideLesser+1 to ACNoStandard+2 to AC, Reflex,
StealthYesGreater+4 to AC, Reflex,
StealthYes
```

**Status:** keep · **Notes:** Cover table: bonus summary. · **target_text:** (optional substring)

## batch_002_06

**Question:** What penalties apply while blinded?

**Expected answer summary:** Blinded: Can't see. All terrain is difficult. Auto-fail Perception checks requiring vision. -4 status penalty to Perception if vision is your only precise sense. Immune to visual effects. You're off-guard. Overrides dazzled.

### Gold chunk 62 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/11/Text/10`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 11 · **Path:** `/page/11/Text/10`

**Chunk text:**

```
You can't see. All normal terrain is difficult terrain to you.  You can't detect anything using vision. You automatically  critically fail Perception checks that require you to be able  to see, and if vision is your only precise sense, you take a –4  status penalty to Perception checks. You're immune to visual  effects. Blinded overrides dazzled.
```

**Status:** keep · **Notes:** Blinded: full penalties (difficult terrain, auto-fail vision, -4, off-guard). · **target_text:** (optional substring)

## batch_002_07

**Question:** If I'm reduced to 0 HP by nonlethal damage, do I gain the dying condition?

**Expected answer summary:** No. Nonlethal damage that reduces you to 0 HP knocks you unconscious but you don't gain dying. You remain unconscious with 0 HP instead. Different state transition than lethal damage.

### Gold chunk 63 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/12/ListItem/10`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 12 · **Path:** `/page/12/ListItem/10`

**Chunk text:**

```
You gain the dying 1 condition. If the effect that  knocked you out was a critical success from the  attacker or the result of your critical failure, you  gain the dying 2 condition instead. If you have the  wounded condition, increase these values by your  wounded value. If the damage came from a nonlethal  attack or effect, you don't gain the dying condition you're instead unconscious with 0 Hit Points.
```

**Status:** keep · **Notes:** Nonlethal: don't gain dying condition, unconscious with 0 HP. · **target_text:** (optional substring)

### Gold chunk 64 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405::/page/14/Text/17`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-388-405` · **Page:** 14 · **Path:** `/page/14/Text/17`

**Chunk text:**

```
Creatures can't be reduced to fewer than 0  Hit Points. When most creatures reach  0 Hit Points, they die and are removed  from play unless the attack was  nonlethal, in which case they're instead  knocked out for a significant amount of  time (usually 10 minutes or more). When  undead and constructs reach 0 Hit Points,  they're destroyed.
```

**Status:** keep · **Notes:** 0 HP: nonlethal knocks out, no dying. · **target_text:** (optional substring)

### Gold chunk 65 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-250-267::/page/6/Text/17`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-250-267` · **Page:** 6 · **Path:** `/page/6/Text/17`

**Chunk text:**

```
**Nonlethal:** Attacks with this weapon are nonlethal (page  399) and are used to knock creatures unconscious instead of  kill them. You can use a nonlethal weapon to make a lethal  attack with a –2 circumstance penalty.
```

**Status:** keep · **Notes:** Nonlethal trait context. · **target_text:** (optional substring)

## batch_002_08

**Question:** Can I crawl while prone and does it provoke?

**Expected answer summary:** Yes, Crawl is available while prone (moves 5 feet, requires Speed 10+). Crawl has the move trait, so it triggers reactions that respond to move actions (like Attack of Opportunity).

### Gold chunk 66 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/2/Text/17`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 2 · **Path:** `/page/2/Text/17`

**Chunk text:**

```
**Requirements** You're prone, and your Speed is at least 10 feet. You move 5 feet by crawling and continue to stay prone.
```

**Status:** keep · **Notes:** Crawl: requirements, 5 feet, stay prone. · **target_text:** (optional substring)

### Gold chunk 67 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/15/Text/6`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 15 · **Path:** `/page/15/Text/6`

**Chunk text:**

```
You're lying on the ground. You are off-guard and take a –2  circumstance penalty to attack rolls. The only move actions  you can use while you're prone are Crawl and Stand. Standing  up ends the prone condition. You can Take Cover while prone  to hunker down and gain greater cover against ranged attacks,  even if you don't have an object to get behind, which grants  you a +4 circumstance bonus to AC against ranged attacks (but  you remain off-guard).
```

**Status:** keep · **Notes:** Prone: only Crawl and Stand for move actions. · **target_text:** (optional substring)

## batch_003_01

**Question:** Does the off-guard condition from flanking apply only while the creature is flanked, or does it persist after the flanking ally moves away?

**Expected answer summary:** Off-guard from flanking is situational: the creature is off-guard to melee attacks from creatures that are flanking it. It applies only while flanked; when the ally moves away the creature is no longer flanked so the penalty ends.

### Gold chunk 68 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/11/Text/7`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 11 · **Path:** `/page/11/Text/7`

**Chunk text:**

```
When you and an ally are flanking a foe, it has a harder time  defending against you. A creature is off-guard (taking a –2  circumstance penalty to AC) to melee attacks from creatures  that are flanking it.
```

**Status:** keep · **Notes:** Flanking: off-guard to melee from flanking creatures only (situational). · **target_text:** (optional substring)

## batch_003_02

**Question:** Is the 'until the end of your next turn' effect from an ability applied once when you use it, or every time the trigger is met?

**Expected answer summary:** Frequency limits how often you can use the ability; Trigger says when a reaction/free action can be used. 'Until the end of your next turn' is duration of the effect once you use the ability—it's one effect per use, not re-applied every time the trigger fires.

### Gold chunk 69 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/2/Text/14`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029` · **Page:** 2 · **Path:** `/page/2/Text/14`

**Chunk text:**

```
**Frequency** The limit on how often you can use the ability. **Trigger** Reactions and some free actions have triggers that  must be met before they can be used.
```

**Status:** keep · **Notes:** Frequency and Trigger definitions. · **target_text:** (optional substring)

### Gold chunk 70 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/2/Text/19`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029` · **Page:** 2 · **Path:** `/page/2/Text/19`

**Chunk text:**

```
**Name** [one-action] (traits) **Frequency** how often it can be used;  **Trigger** when a reaction or free action can be  used; **Requirements** some actions require specific  circumstances, listed here; **Effect** this section explains  how the ability changes the world.
```

**Status:** keep · **Notes:** Ability block: Effect is duration of one use. · **target_text:** (optional substring)

## batch_003_03

**Question:** Does the Aid action apply to allies, enemies, or only the ally you choose?

**Expected answer summary:** Aid applies only to an ally. Requirements: the ally is willing to accept your aid, and you've prepared to help. You try to help your ally with a task—target is explicitly an ally.

### Gold chunk 71 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/2/Text/9`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 2 · **Path:** `/page/2/Text/9`

**Chunk text:**

```
**Requirements** The ally is willing to accept your aid, and you've  prepared to help (see below).
```

**Status:** keep · **Notes:** Aid: requirements ally willing. · **target_text:** (optional substring)

### Gold chunk 72 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/2/Text/10`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 2 · **Path:** `/page/2/Text/10`

**Chunk text:**

```
You try to help your ally with a task. To use this reaction, you  must first prepare to help, usually by using an action during  your turn. You must explain to the GM exactly how you're trying  to help, and they determine whether you can Aid your ally.
```

**Status:** keep · **Notes:** Aid: help your ally with a task. · **target_text:** (optional substring)

## batch_003_04

**Question:** When you have both a reaction and a free action with the same trigger, can you use both or only one?

**Expected answer summary:** You can use only one action in response to a given trigger. If you had a reaction and a free action that both had the same trigger, you would choose one to use.

### Gold chunk 73 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/1/Text/1`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 1 · **Path:** `/page/1/Text/1`

**Chunk text:**

```
free actions limit when you can use those actions. You can use  only one action in response to a given trigger. For example, if  you had a reaction and a free action that both had a trigger  of "your turn begins," you could use either of them at the  start of your turn—but not both. If two triggers are similar,  but not identical, the GM determines whether you can use  one action in response to each or whether they're effectively  the same thing. Usually, this decision will be based on what's  happening in the narrative.
```

**Status:** keep · **Notes:** One action per trigger (reaction or free action). · **target_text:** (optional substring)

## batch_003_05

**Question:** Does Enhanced Nanite Surge replace the base Nanite Surge frequency or add to it?

**Expected answer summary:** Enhanced Nanite Surge (feat) lets you use Nanite Surge with a frequency of once per 10 minutes, rather than once per hour. It replaces the frequency for that use, not adds an extra use.

### Gold chunk 74 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/4/SectionHeader/25`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 4 · **Path:** `/page/4/SectionHeader/25`

**Chunk text:**

```
**NANITE SURGE **[reaction] **FEAT 1**
```

**Status:** expand · **Notes:** Nanite Surge base: header; need Enhanced Nanite Surge for replace vs add. · **target_text:** (optional substring)

### Gold chunk 75 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/Text/36`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/Text/36`

**Chunk text:**

```
body's efficiency more often. You can use Nanite Surge with a  frequency of once per 10 minutes, rather than once per hour.
```

**Status:** keep · **Notes:** Enhanced: use Nanite Surge once per 10 min rather than once per hour (replaces). · **target_text:** (optional substring)

## batch_003_06

**Question:** What exact condition must be true to use your one reaction per round?

**Expected answer summary:** You get one reaction per round. You can use it only when its specific trigger is fulfilled. So the condition is: (1) you haven't used your reaction yet this round, and (2) the trigger for that reaction has occurred.

### Gold chunk 76 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/1/Text/12`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029` · **Page:** 1 · **Path:** `/page/1/Text/12`

**Chunk text:**

```
Reactions use this symbol: [reaction]. These actions can be used even  when it's not your turn. You only get one reaction per encounter  round, and you can use it only when its specific trigger is  fulfilled. Often, the trigger is another creature's action.
```

**Status:** keep · **Notes:** One reaction per round, use only when trigger fulfilled. · **target_text:** (optional substring)

### Gold chunk 77 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464::/page/10/Text/25`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464` · **Page:** 10 · **Path:** `/page/10/Text/25`

**Chunk text:**

```
**reaction** ([reaction]) An action you can use even if it's not your turn.  You can use 1 reaction per round. 15, **406** reactions in encounters 428–429
```

**Status:** keep · **Notes:** reaction glossary: 1 per round. · **target_text:** (optional substring)

## batch_003_07

**Question:** Can you use more than one reaction in response to the same trigger?

**Expected answer summary:** No. You can use only one action in response to a given trigger. So even if multiple reactions could fire on the same trigger, you choose one.

### Gold chunk 78 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/1/Text/1`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 1 · **Path:** `/page/1/Text/1`

**Chunk text:**

```
free actions limit when you can use those actions. You can use  only one action in response to a given trigger. For example, if  you had a reaction and a free action that both had a trigger  of "your turn begins," you could use either of them at the  start of your turn—but not both. If two triggers are similar,  but not identical, the GM determines whether you can use  one action in response to each or whether they're effectively  the same thing. Usually, this decision will be based on what's  happening in the narrative.
```

**Status:** keep · **Notes:** Same rule: one action per trigger. · **target_text:** (optional substring)

## batch_003_08

**Question:** What does 'reaction' mean in Starfinder rules terms?

**Expected answer summary:** Reaction ([reaction]): an action you can use even when it's not your turn. You get one reaction per round, and you can use it only when its specific trigger is fulfilled.

### Gold chunk 79 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/1/Text/12`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029` · **Page:** 1 · **Path:** `/page/1/Text/12`

**Chunk text:**

```
Reactions use this symbol: [reaction]. These actions can be used even  when it's not your turn. You only get one reaction per encounter  round, and you can use it only when its specific trigger is  fulfilled. Often, the trigger is another creature's action.
```

**Status:** keep · **Notes:** Reactions: not your turn, one per round, trigger. · **target_text:** (optional substring)

### Gold chunk 80 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464::/page/10/Text/25`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464` · **Page:** 10 · **Path:** `/page/10/Text/25`

**Chunk text:**

```
**reaction** ([reaction]) An action you can use even if it's not your turn.  You can use 1 reaction per round. 15, **406** reactions in encounters 428–429
```

**Status:** keep · **Notes:** reaction glossary. · **target_text:** (optional substring)

## batch_003_09

**Question:** Where does the book tell you to look for the complete definition of a bolded term?

**Expected answer summary:** New concepts are presented in bold. The complete game rules are defined in later chapters, and the Glossary and Index in the back of the book will help you find the specific rules you need.

### Gold chunk 81 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-001-013::/page/5/Text/19`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-001-013` · **Page:** 5 · **Path:** `/page/5/Text/19`

**Chunk text:**

```
Before creating your first character or adventure, you should  understand a number of basic concepts used in the game.  New concepts are presented in bold to make them easy to  find, but this chapter is only an introduction to the basics of  play. The complete game rules are defined in later chapters,  and the Glossary and Index in the back of this book will help  you find the specific rules you need.
```

**Status:** keep · **Notes:** Bold terms; Glossary and Index for full rules. · **target_text:** (optional substring)

## batch_003_10

**Question:** When in your turn does the dying recovery check happen?

**Expected answer summary:** Many things happen at the start of your turn. When you're dying, you must attempt a recovery check at the start of your turn each round. So the dying recovery check happens at the start of your turn.

### Gold chunk 82 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/3/Text/21`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 3 · **Path:** `/page/3/Text/21`

**Chunk text:**

```
Many things happen automatically at the start of your turn it's a common point for tracking the passage of time for  effects that last multiple rounds. At the start of each of your  turns, take these steps in any order you choose.
```

**Status:** keep · **Notes:** Many things at start of turn. · **target_text:** (optional substring)

### Gold chunk 83 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/12/Text/25`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 12 · **Path:** `/page/12/Text/25`

**Chunk text:**

```
You're bleeding out or otherwise at death's door. While you  have this condition, you're unconscious. Dying always includes  a value, and if it ever reaches dying 4, you die. When you're  dying, you must attempt a recovery check (page 403) at the  start of your turn each round to determine whether you get  better or worse. Your dying condition increases by 1 if you  take damage while dying, or by 2 if you take damage from an  enemy's critical hit or a critical failure on your save.
```

**Status:** keep · **Notes:** Dying: recovery check at start of turn each round. · **target_text:** (optional substring)

## batch_003_11

**Question:** Does a free action with a trigger use up your one reaction per round?

**Expected answer summary:** No. Free actions with triggers can be used at any time, but they don't use up your 1 reaction per round. Reactions use your one reaction per round; free actions do not.

### Gold chunk 84 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464::/page/5/Text/43`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464` · **Page:** 5 · **Path:** `/page/5/Text/43`

**Chunk text:**

```
**free action** ([free-action]) An action you can use without spending one  of your actions. Free actions with triggers can be used at  any time, but they don't use up your 1 reaction per round.  15, **406**
```

**Status:** keep · **Notes:** Free actions with triggers don't use up your 1 reaction per round. · **target_text:** (optional substring)

### Gold chunk 85 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464::/page/10/Text/25`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464` · **Page:** 10 · **Path:** `/page/10/Text/25`

**Chunk text:**

```
**reaction** ([reaction]) An action you can use even if it's not your turn.  You can use 1 reaction per round. 15, **406** reactions in encounters 428–429
```

**Status:** keep · **Notes:** reaction uses 1 per round (contrast). · **target_text:** (optional substring)

## batch_003_12

**Question:** Can you use a reaction when it's not your turn?

**Expected answer summary:** Yes. Reactions can be used even when it's not your turn. You only get one per round and only when the trigger is fulfilled.

### Gold chunk 86 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/1/Text/12`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029` · **Page:** 1 · **Path:** `/page/1/Text/12`

**Chunk text:**

```
Reactions use this symbol: [reaction]. These actions can be used even  when it's not your turn. You only get one reaction per encounter  round, and you can use it only when its specific trigger is  fulfilled. Often, the trigger is another creature's action.
```

**Status:** keep · **Notes:** Reactions can be used when it's not your turn. · **target_text:** (optional substring)

## batch_003_13

**Question:** If the book gives an example of having both a reaction and a free action with the same trigger, does that example change the rule or just illustrate it?

**Expected answer summary:** It illustrates the rule. The rule states you can use only one action in response to a given trigger. The example ('if you had a reaction and a free action that both had a trigger of...') is clarifying that you choose one—it doesn't add or change the rule.

### Gold chunk 87 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/1/Text/1`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 1 · **Path:** `/page/1/Text/1`

**Chunk text:**

```
free actions limit when you can use those actions. You can use  only one action in response to a given trigger. For example, if  you had a reaction and a free action that both had a trigger  of "your turn begins," you could use either of them at the  start of your turn—but not both. If two triggers are similar,  but not identical, the GM determines whether you can use  one action in response to each or whether they're effectively  the same thing. Usually, this decision will be based on what's  happening in the narrative.
```

**Status:** keep · **Notes:** Example illustrates rule (choose one, not both). · **target_text:** (optional substring)

## batch_003_14

**Question:** If the text is ambiguous, where does the book say to look?

**Expected answer summary:** The introduction says the complete game rules are in later chapters and the Glossary and Index in the back will help you find the specific rules you need. So for ambiguity, look to later chapters and the Glossary & Index.

### Gold chunk 88 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-001-013::/page/5/Text/19`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-001-013` · **Page:** 5 · **Path:** `/page/5/Text/19`

**Chunk text:**

```
Before creating your first character or adventure, you should  understand a number of basic concepts used in the game.  New concepts are presented in bold to make them easy to  find, but this chapter is only an introduction to the basics of  play. The complete game rules are defined in later chapters,  and the Glossary and Index in the back of this book will help  you find the specific rules you need.
```

**Status:** keep · **Notes:** Glossary and Index for specific rules (same chunk as 81). · **target_text:** (optional substring)

## batch_004_01

**Question:** When in my turn does the dying recovery check happen—start or end?

**Expected answer summary:** At the start of your turn each round when you're dying, you must attempt a recovery check. Many things happen at the start of your turn; the dying check is one of them.

### Gold chunk 89 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/12/Text/25`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 12 · **Path:** `/page/12/Text/25`

**Chunk text:**

```
You're bleeding out or otherwise at death's door. While you  have this condition, you're unconscious. Dying always includes  a value, and if it ever reaches dying 4, you die. When you're  dying, you must attempt a recovery check (page 403) at the  start of your turn each round to determine whether you get  better or worse. Your dying condition increases by 1 if you  take damage while dying, or by 2 if you take damage from an  enemy's critical hit or a critical failure on your save.
```

**Status:** keep · **Notes:** Dying recovery at start of turn. · **target_text:** (optional substring)

### Gold chunk 90 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/3/Text/21`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 3 · **Path:** `/page/3/Text/21`

**Chunk text:**

```
Many things happen automatically at the start of your turn it's a common point for tracking the passage of time for  effects that last multiple rounds. At the start of each of your  turns, take these steps in any order you choose.
```

**Status:** keep · **Notes:** Start of turn steps. · **target_text:** (optional substring)

## batch_004_02

**Question:** When do I take persistent damage—start or end of my turn?

**Expected answer summary:** You take persistent damage at the end of each of your turns (not immediately when you get it). After you take the damage you can attempt the flat check to end it.

### Gold chunk 91 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/15/Text/2`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 15 · **Path:** `/page/15/Text/2`

**Chunk text:**

```
You're taking damage from an ongoing effect, such as from  being lit on fire. This appears as "X persistent [type] damage,"  where "X" is the amount of damage dealt and "[type]" is the  damage type. Like normal damage, it can be doubled or halved  based on the results of an attack roll or saving throw. Instead  of taking persistent damage immediately, you take it at the end  of each of your turns as long as you have the condition, rolling  any damage dice anew each time. After you take persistent  damage, roll a DC 15 flat check to see if you recover from the  persistent damage. If you succeed, the condition ends.
```

**Status:** keep · **Notes:** Persistent damage at end of turn. · **target_text:** (optional substring)

### Gold chunk 92 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/4/ListItem/20`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 4 · **Path:** `/page/4/ListItem/20`

**Chunk text:**

```
If you have a persistent damage condition, you take the  damage at this point. After you take the damage, you can  attempt the flat check to end the persistent damage. You  then attempt any saving throws for ongoing afflictions.  Many other conditions change at the end of your turn,  such as the frightened condition decreasing in severity.  These take place after you've taken any persistent  damage, attempted flat checks to end the persistent  damage, and attempted saves against any afflictions.
```

**Status:** keep · **Notes:** ListItem: persistent damage at this point. · **target_text:** (optional substring)

## batch_004_03

**Question:** If I have a reaction that triggers on 'you are about to attempt a recovery check', does it happen before or after the recovery check roll?

**Expected answer summary:** Trigger says 'about to attempt' so the reaction resolves before the check. You use the reaction when the trigger is met, then you attempt the recovery check.

### Gold chunk 93 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/Text/41`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/Text/41`

**Chunk text:**

```
**Trigger** You have the dying condition and are about to  attempt a recovery check.
```

**Status:** keep · **Notes:** 'About to attempt' = reaction resolves before the check. · **target_text:** (optional substring)

### Gold chunk 94 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/12/Text/25`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 12 · **Path:** `/page/12/Text/25`

**Chunk text:**

```
You're bleeding out or otherwise at death's door. While you  have this condition, you're unconscious. Dying always includes  a value, and if it ever reaches dying 4, you die. When you're  dying, you must attempt a recovery check (page 403) at the  start of your turn each round to determine whether you get  better or worse. Your dying condition increases by 1 if you  take damage while dying, or by 2 if you take damage from an  enemy's critical hit or a critical failure on your save.
```

**Status:** keep · **Notes:** Dying: attempt recovery at start of turn. · **target_text:** (optional substring)

## batch_004_04

**Question:** For Graviton-Attuned Stride, can I move immediately before or after my attacks, or only one?

**Expected answer summary:** You can Stride up to half your speed once as a free action immediately before or after making your attacks. So you choose: either before or after, once.

### Gold chunk 95 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149::/page/10/Text/50`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-138-149` · **Page:** 10 · **Path:** `/page/10/Text/50`

**Chunk text:**

```
**Graviton-Attuned** You can Stride up to half your speed once  as a free action immediately before or after making your  attacks.
```

**Status:** keep · **Notes:** Graviton-Attuned Stride: before or after attacks, once. · **target_text:** (optional substring)

## batch_004_05

**Question:** When a reaction says you Grapple the 'triggering creature', does that mean the creature that triggered the reaction?

**Expected answer summary:** Yes. 'The triggering creature' is the creature that triggered the reaction (e.g. the one who critically failed the melee Strike against you). You attempt to Grapple that creature.

### Gold chunk 96 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073::/page/15/Text/45`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073` · **Page:** 15 · **Path:** `/page/15/Text/45`

**Chunk text:**

```
**Trigger** A creature critically fails a melee Strike against you. **Requirements** The triggering creature is within your reach,  you have at least one free active hand, and your target is  no more than one size larger than you.
```

**Status:** keep · **Notes:** 'Triggering creature' = creature that triggered the reaction. · **target_text:** (optional substring)

### Gold chunk 97 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073::/page/15/Text/46`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-058-073` · **Page:** 15 · **Path:** `/page/15/Text/46`

**Chunk text:**

```
You seize the opportunity to give your foe a big hug to help  them feel better or calm down. You attempt an Athletics  check to Grapple the triggering creature.
```

**Status:** keep · **Notes:** Grapple the triggering creature. · **target_text:** (optional substring)

## batch_004_06

**Question:** Does the multiple attack penalty reset at the start or end of my turn?

**Expected answer summary:** The multiple attack penalty starts at -5 on the second attack and increases for each additional attack. It lasts until the end of your turn, so it resets at the end of your turn (before your next turn).

### Gold chunk 98 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-001-013::/page/8/Text/8`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-001-013` · **Page:** 8 · **Path:** `/page/8/Text/8`

**Chunk text:**

```
You can use more than one Strike action on your turn, but  each additional attack after the first becomes less accurate.  This is reflected by a **multiple attack penalty** that starts at  –5 on the second attack, but increases to –10 on the third.  There are many ways to reduce this penalty, and it resets at  the end of your turn.
```

**Status:** keep · **Notes:** MAP resets at end of your turn. · **target_text:** (optional substring)

## batch_005_01

**Question:** What restrictions apply when I choose a target for an effect—can I target undetected creatures or only those that match certain criteria?

**Expected answer summary:** Targeting can be difficult or impossible if the creature is undetected by you or doesn't match restrictions on who you can target. Some effects require specific targets.

### Gold chunk 99 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-001-013::/page/4/Text/17`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-001-013` · **Page:** 4 · **Path:** `/page/4/Text/17`

**Chunk text:**

```
Everyone involved in a Starfinder game is a player, including  the Game Master, but for the sake of simplicity, "player"  usually refers to participants other than the GM. Before  the game begins, players invent a history and personality  for their characters, using the rules to determine their  characters' statistics, abilities, strengths, and weaknesses.  The GM might limit the options available to the players during  character creation, but these restrictions should be discussed  ahead of time so everyone can create interesting heroes. In  general, the only limits to character concepts are the players'  imaginations and the GM's guidelines.
```

**Status:** drop · **Notes:** Wrong chunk (character creation); targeting/undetected not here. · **target_text:** (optional substring)

## batch_005_02

**Question:** When I'm grabbed, what am I prevented from doing?

**Expected answer summary:** Grabbed restricts movement and may prevent or limit other actions; the condition text states what you cannot do while grabbed.

### Gold chunk 100 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209::/page/12/Text/19`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209` · **Page:** 12 · **Path:** `/page/12/Text/19`

**Chunk text:**

```
You attempt to grab a creature or object with your free hand.  Attempt an Athletics check against the target's Fortitude  DC. You can Grapple a target you already have grabbed or  restrained without having a hand free.
```

**Status:** trim · **Notes:** Grapple action text; grabbed condition restrictions would be in condition block. · **target_text:** (optional substring)

### Gold chunk 101 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209::/page/12/Text/21`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209` · **Page:** 12 · **Path:** `/page/12/Text/21`

**Chunk text:**

```
**Success** Your target is grabbed until the end of your next turn  unless you move or your target Escapes.
```

**Status:** keep · **Notes:** Success: target is grabbed. · **target_text:** (optional substring)

### Gold chunk 102 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209::/page/12/Text/22`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209` · **Page:** 12 · **Path:** `/page/12/Text/22`

**Chunk text:**

```
**Failure** You fail to grab your target. If you already had the target  grabbed or restrained using a Grapple, those conditions on  the target end.
```

**Status:** keep · **Notes:** Failure: conditions end. · **target_text:** (optional substring)

## batch_005_03

**Question:** If an ability says 'Frequency once per round', can I use it more than once in the same round by any means?

**Expected answer summary:** Frequency once per round means you can use the ability only once per round; the limit is per round, not per turn.

### Gold chunk 103 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091::/page/7/Text/24`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-074-091` · **Page:** 7 · **Path:** `/page/7/Text/24`

**Chunk text:**

```
**Frequency** once per round
```

**Status:** keep · **Notes:** Frequency once per round: direct. · **target_text:** (optional substring)

### Gold chunk 104 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/15/Text/20`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029` · **Page:** 15 · **Path:** `/page/15/Text/20`

**Chunk text:**

```
modifier, recalculate their maximum Hit  Points using their new Constitution modifier  (typically, this adds 1 Hit Point per level). If  an attribute boost increases your character's  Intelligence modifier, they become trained in an  additional skill and language. Some feats grant  a benefit based on your level, such as Toughness,  and these benefits are adjusted whenever you gain  a level as well.
```

**Status:** drop · **Notes:** Irrelevant (level/attribute boost text). · **target_text:** (optional substring)

## batch_005_04

**Question:** Can an illusion created by a spell affect the physical world or cause damage beyond what the spell says?

**Expected answer summary:** The illusion can cause damage by making the target believe the attacks are real, but it cannot otherwise directly affect the physical world.

### Gold chunk 105 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-364-387::/page/11/Text/33`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-364-387` · **Page:** 11 · **Path:** `/page/11/Text/33`

**Chunk text:**

```
You create an advanced, martial, or simple weapon out  of elemental energy that materializes in the hands of a  bonded creature. Select an elemental trait for the created  weapon: air, earth, fire, metal, water, or wood. The weapon  is tactical grade and comes fully charged and loaded  with basic ammunition. It cannot be made of any special  materials.
```

**Status:** drop · **Notes:** Elemental weapon, not illusion spell. · **target_text:** (optional substring)

## batch_005_05

**Question:** When a creature is swallowed by its own shadow (spell failure), can it act or perceive the outside world?

**Expected answer summary:** The target is invisible and paralyzed, cannot experience or interact with the outside world, and cannot take actions until the effect ends.

### Gold chunk 106 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-364-387::/page/13/Text/9`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-364-387` · **Page:** 13 · **Path:** `/page/13/Text/9`

**Chunk text:**

```
**Failure** The target is swallowed by its own shadow until the  beginning of your next turn. The target is invisible and  paralyzed, cannot experience or interact with the outside  world, and cannot be targeted by any attacks or other  effects.
```

**Status:** keep · **Notes:** Shadow failure: invisible, paralyzed, cannot experience or interact. · **target_text:** (optional substring)

## batch_005_06

**Question:** Are there restrictions on who I can target with the Aid action or similar ally-only effects?

**Expected answer summary:** Aid and similar effects target an ally; restrictions on who can be targeted (e.g. willing ally) are stated in the effect.

### Gold chunk 107 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113::/page/11/Text/12`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-098-113` · **Page:** 11 · **Path:** `/page/11/Text/12`

**Chunk text:**

```
When the target you directed your allies to take down falls  unconscious or is destroyed, you quickly direct them at another  target. You use Get 'Em! against a new target following all the  normal targeting restrictions for Get 'Em! You don't count as  leading by example against this new target.
```

**Status:** drop · **Notes:** Get 'Em targeting, not Aid. · **target_text:** (optional substring)

### Gold chunk 108 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423::/page/2/Text/9`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-406-423` · **Page:** 2 · **Path:** `/page/2/Text/9`

**Chunk text:**

```
**Requirements** The ally is willing to accept your aid, and you've  prepared to help (see below).
```

**Status:** keep · **Notes:** Aid: ally willing, prepared to help. · **target_text:** (optional substring)

## batch_005_07

**Question:** Does Sure Footing let me ignore the movement restriction from being grabbed?

**Expected answer summary:** Sure Footing can counteract clumsy, grabbed, paralyzed, or related conditions—so it can remove or mitigate the grabbed condition's restrictions.

### Gold chunk 109 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/5/ListItem/58`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 5 · **Path:** `/page/5/ListItem/58`

**Chunk text:**

```
You're immune to the grabbed, prone, and restrained  conditions.
```

**Status:** keep · **Notes:** Sure Footing: immune to grabbed (among others). · **target_text:** (optional substring)

### Gold chunk 110 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057::/page/8/Text/24`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-040-057` · **Page:** 8 · **Path:** `/page/8/Text/24`

**Chunk text:**

```
**Piercing Spikes** [reaction] **Trigger** You become grabbed by a  creature; **Effect** You twist and thrash your body around,  dealing 1d4 plus your Strength modifier piercing damage  to the triggering creature. This damage increases by 1d4  at 5th level and every four levels thereafter.
```

**Status:** drop · **Notes:** Piercing Spikes reaction when grabbed, not Sure Footing. · **target_text:** (optional substring)

## batch_006_01

**Question:** Why would I look at several conditions together instead of one at a time?

**Expected answer summary:** Some conditions exist relative to one another or share a similar theme. It can be useful to look at these conditions together to understand how they interact.

### Gold chunk 111 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/12/Text/2`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 12 · **Path:** `/page/12/Text/2`

**Chunk text:**

```
Some conditions exist relative to one another or share  a similar theme. It can be useful to look at these  conditions together to understand how they interact.
```

**Status:** keep · **Notes:** Conditions together: relative/similar theme, understand interaction. · **target_text:** (optional substring)

## batch_006_02

**Question:** What is an archetype in character-building terms?

**Expected answer summary:** An archetype is a special additional theme for your character that you can choose using your class feats.

### Gold chunk 112 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464::/page/1/Text/6`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-442-464` · **Page:** 1 · **Path:** `/page/1/Text/6`

**Chunk text:**

```
**archetype** A special additional theme for your character that  you can choose using your class feats. 174–181
```

**Status:** keep · **Notes:** archetype: special theme, choose using class feats. · **target_text:** (optional substring)

## batch_006_03

**Question:** Do spells always have visible or sensory effects when cast?

**Expected answer summary:** Spellcasting creates obvious sensory manifestations (lights, sounds, smells). Nearly all spells manifest a spell signature—a colorful, global indicator.

### Gold chunk 113 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-294-329::/page/4/Text/4`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-294-329` · **Page:** 4 · **Path:** `/page/4/Text/4`

**Chunk text:**

```
Spellcasting creates obvious sensory manifestations, such  as bright lights, crackling sounds, and sharp smells from the  gathering magic. Nearly all spells manifest a spell signature—a  colorful, glowing ring of magical runes or circuitry that  appears in midair, typically around your hands, though what  kind of spellcaster you are can affect this—witchwarpers'  signatures often look like ripples or winkles in reality,  and a mystic's might be inspired by their connection. How  spellcasting looks can vary from one spellcasting tradition or  class to another, or even from person to person. You have  a great deal of freedom in flavoring your character's magic  however you wish!
```

**Status:** keep · **Notes:** Spellcasting: obvious sensory manifestations, spell signature. · **target_text:** (optional substring)

## batch_006_04

**Question:** How do conditions that share a theme relate to each other?

**Expected answer summary:** Some conditions exist relative to one another or share a similar theme; looking at them together helps understand how they interact.

### Gold chunk 114 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209::/page/1/Text/6`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-182-209` · **Page:** 1 · **Path:** `/page/1/Text/6`

**Chunk text:**

```
A character's acumen in skills can come from all sorts of  training, from piloting starships to researching a topic on  an infosphere to rehearsing a performing art. When you  create your character and as they advance in level, you  have flexibility as to which skills they become better at  and when. Some classes benefit more from improving  certain skills—such as the envoy's focus on their leadership  skill—but for most classes, you can choose whichever  skills make the most sense for your character's theme  and backstory at 1st level, then use their adventure and  downtime experiences to inform how their skills should  improve as your character levels up.
```

**Status:** drop · **Notes:** Skills/character building, not conditions. · **target_text:** (optional substring)

### Gold chunk 115 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441::/page/12/Text/2`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-424-441` · **Page:** 12 · **Path:** `/page/12/Text/2`

**Chunk text:**

```
Some conditions exist relative to one another or share  a similar theme. It can be useful to look at these  conditions together to understand how they interact.
```

**Status:** keep · **Notes:** Conditions relative/similar theme, look together. · **target_text:** (optional substring)

## batch_006_05

**Question:** What is the purpose of the Frequency and Trigger entries on an ability block?

**Expected answer summary:** Frequency limits how often you can use the ability; Trigger describes when a reaction or free action can be used. Together they define when and how often the ability is available.

### Gold chunk 116 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-030-039::/page/5/Text/1`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-030-039` · **Page:** 5 · **Path:** `/page/5/Text/1`

**Chunk text:**

```
Technology and scientific knowledge flourish across the galaxy, but these advancements can't  solve every problem or answer all existential questions. Many turn to religion to understand their  place in the cosmos. Some people worship an ancestral deity, while others follow the teachings of  a pantheon, find purpose in a nondeific belief like the Green Faith, or practice a philosophy like the  Cycle. Faith is often important to mystics, who sometimes draw on their connection to the divine  for their abilities, and solarians, who find power through understanding the cosmic cycle. Note that  countless more deities, religions, and philosophies exist in the many worlds of the multiverse than  those detailed below.
```

**Status:** drop · **Notes:** Religion/deities, wrong chunk. · **target_text:** (optional substring)

### Gold chunk 117 – `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029::/page/2/Text/14`

- **Document:** `sf2e-playercore-PZO22001-Starfinder-Player-Core-014-029` · **Page:** 2 · **Path:** `/page/2/Text/14`

**Chunk text:**

```
**Frequency** The limit on how often you can use the ability. **Trigger** Reactions and some free actions have triggers that  must be met before they can be used.
```

**Status:** keep · **Notes:** Frequency = limit; Trigger = when reaction/free action can be used. · **target_text:** (optional substring)
