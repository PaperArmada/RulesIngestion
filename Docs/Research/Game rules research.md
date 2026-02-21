# Universal Rules of Table‑Top Role‑Playing Games

## Key Findings from the Literature

The literature on game studies, design frameworks and formal languages for games reveals recurring concepts that are helpful for building a rules taxonomy. Below are the most consequential findings, each grounded in a credible source.

1. **Definitions of “game” converge on systems, players, rules and outcomes.** Classical definitions by Parlett, Abt, Callois, Suits, Crawford, Costikyan and Salen & Zimmerman emphasise that a game is a voluntary, rule‑governed activity involving players in a conflict or challenge, usually outside ordinary life, with quantifiable outcomes or goals[\[1\]](https://computerscience.chemeketa.edu/cis125greader/WhatIsAGame/AGame.html). These definitions cite properties such as a limiting context (rules), decision‑making, uncertain outcomes, inefficiency via “unnecessary obstacles,” interaction, conflict and endogenous meaning[\[2\]](https://computerscience.chemeketa.edu/cis125greader/WhatIsAGame/AGame.html#:~:text=Here%20are%20some%20definitions%20from,various%20sources).

2. **Game rules define the allowable actions and interactions and are not always fixed.** The Game Ontology Project (GOP) notes that rules “define what can or can’t be done,” regulate game development and determine the basic interactions. Some games (such as Fluxx) intentionally change their rules during play[\[3\]](https://gameontology.com/index.php/Rules#:~:text=The%20rules%20and%20constraints%20of,%28Looney%201998).

3. **Gameplay rules and gameworld rules are distinguished.** GOP separates **gameplay rules**, which describe abstract conventions such as health points or lives, from **gameworld rules**, which arise from the environment (board spaces, physics, time). Gameworld rules often define spatial restrictions or simulated physics[\[4\]](https://gameontology.com/index.php/Gameworld_Rules#:~:text=In%20non,the%20game%2C%20the%20gameworld%20rules).

4. **The Mechanics–Dynamics–Aesthetics (MDA) framework divides games into three layers.** Mechanics are the “data representation and algorithms” of game rules; dynamics are the run‑time behaviour produced by player inputs; and aesthetics are the emotions evoked by play. This layered view helps separate core procedures from emergent play experience.

5. **Game design patterns can be catalogued as recurring solutions.** Holopainen & Björk describe patterns such as resource management and progression loops as tools for creative design and communication across disciplines[\[5\]](https://www.gents.it/FILES/ebooks/Game_Design_Patterns.pdf). Patterns are not canonical but highlight common structures and problems.

6. **Formal languages for games treat rules as programs.** Game Description Language (GDL) represents games via logic predicates like role, init, legal, next, terminal, and goal that specify players, initial state, legal moves, state transitions, termination and win conditions【912727920492451†L129-L199】. GDL‑II adds keywords for incomplete information (sees) and randomness (random)[\[6\]](https://en.wikipedia.org/wiki/Game_Description_Language#:~:text=Rules%20that%20describe%20the%20conditions,are%20no%20more%20blank%20spaces). Regular Boardgames (RBG) extends this idea using regular languages to efficiently encode complex deterministic games and emphasises expressiveness, efficiency and naturalness[\[7\]](https://arxiv.org/abs/1706.02462#:~:text=,large%20chess%20variants%2C%20go%2C%20international).

7. **Video‑game‑oriented languages emphasise human readability and support non‑determinism.** The Video Game Description Language (VGDL) aims to represent 2‑D arcade‑style games; it advocates human‑readability, expressiveness and support for non‑determinism and simultaneous actions[\[8\]](https://drops.dagstuhl.de/storage/02dagstuhl-follow-ups/dfu-vol006/DFU.Vol6.12191.85/DFU.Vol6.12191.85.pdf). PyVGDL builds on this with an ontology of sprites, interactions and termination conditions[\[9\]](https://www.idsia.ch/~schaul/publications/pyvgdl.pdf#:~:text=blocks%2C%20and%20the%20interaction%20effects,range%20of%20learning%20scenarios%2C%20we).

8. **The game loop pattern describes the engine’s execution cycle.** In game programming, the **game loop** decouples time progression from user input. It runs continuously, processing input, updating the game state and rendering the result on each “tick” or frame[\[10\]](https://gameprogrammingpatterns.com/game-loop.html#:~:text=This%20is%20the%20first%20key,The%20loop%20always%20keeps%20spinning). This pattern informs how compiled rules might be executed: evaluate legal moves, request inputs/randomisation, update state, then proceed to the next frame.

9. **TTRPG rulebooks emphasise the Game Master’s (GM’s) authority and adjudication.** The Dungeons & Dragons 3.5 e *Dungeon Master’s Guide* states that the Dungeon Master is the **final arbiter** of rules and can overrule the written text to maintain consistency[\[11\]](https://dtdnd.neocities.org/books/dm/DungeonMastersGuide.pdf#:~:text=in%20charge,that%20when%20a%20situation%20comes). Pathfinder 2e likewise notes that the GM runs each session, sets scenes and has final say on how the world and rules function[\[12\]](https://pf2.d20pfsrd.com/rules/game-mastering/#:~:text=Game%20Mastering), even while encouraging collaboration[\[13\]](https://pf2.d20pfsrd.com/rules/game-mastering/#:~:text=As%20Game%20Master%2C%20you%20have,and%20how%20nonplayer%20characters%20act).

10. **Core resolution mechanics revolve around checks, attacks and saves.** In D\&D 5 e, the three main rolls are the **ability check**, **attack roll** and **saving throw**[\[14\]](https://www.5esrd.com/using-ability-scores/#:~:text=,personality). An ability check uses a d20 plus a relevant ability modifier to overcome a Difficulty Class; the GM decides when to call for checks and sets the DC[\[15\]](https://5thsrd.org/rules/abilities/ability_checks/#:~:text=An%20ability%20check%20tests%20a,the%20dice%20determine%20the%20results). Attack rolls compare a d20 + modifiers against a target’s Armor Class to determine hits and misses; a natural 20 is an automatic hit (critical) and a natural 1 is an automatic miss[\[16\]](https://www.dandwiki.com/wiki/5e_SRD:Attack_Rolls#:~:text=When%20you%20make%20an%20attack%2C,is%20in%20its%20stat%20block). Saving throws require the player to roll a d20 and add a specified ability modifier, often to avoid a harmful effect[\[17\]](https://www.5esrd.com/using-ability-scores/#:~:text=,personality).

11. **Alternative systems use different resolution structures.** **Fate Core** reduces all skill rolls to four actions—**overcome**, **create advantage**, **attack** and **defend**—and prescribes outcomes (succeed, succeed at cost, failure) based on comparison with an opposition number[\[18\]](https://fate-srd.com/fate-core/four-actions#:~:text=When%20you%20make%20a%20skill,an%20advantage%2C%20attack%2C%20or%20defend). **Blades in the Dark** uses an **action roll** triggered by challenging actions; players state their goal, choose an action rating, then the GM sets **position** (controlled/risky/desperate) and **effect** before rolling dice[\[19\]](https://bladesinthedark.com/action-roll#:~:text=Action%20Roll). The result (critical, success, partial, failure) determines both progress and consequences[\[20\]](https://bladesinthedark.com/action-roll#:~:text=6,Judge%20the%20Result). Blades also employs **progress clocks** to track obstacles or dangers over time[\[21\]](https://bladesinthedark.com/progress-clocks#:~:text=,the%20approach%20of%20impending%20trouble).

12. **Powered by the Apocalypse (PbtA) games classify moves by who triggers them.** Vincent Baker differentiates **action moves** (player chooses the move), **check moves** (player acts but the GM decides whether the move triggers) and **save moves** (GM interrupts to make the move)[\[22\]](https://lumpley.games/2020/07/12/powered-by-the-apocalypse-part-5/#:~:text=Let%E2%80%99s%20say%20that%20exert%20themself,advance%2C%20or%20might%20not%20even). Moves may be triggered by fictional conditions, or non‑fictional prompts such as session start[\[23\]](https://lumpley.games/2020/07/12/powered-by-the-apocalypse-part-5/#:~:text=The%20second%20angle%20I%20want,event%20or%20a%20nonfictional%20one).

13. **Resolution forms in role‑playing theory vary by uncertainty source.** GNS theory identifies **fortune** (chance), **karma** (fixed values) and **drama** (narrative fiat) as resolution modes[\[24\]](https://en.wikipedia.org/wiki/GNS_theory#:~:text=GNS%20theory%20is%20an%20informal,engagement%3A%20Gamism%2C%20Narrativism%20and%20Simulation). Tabletop games often combine modes: D\&D relies on fortune via dice; Fate uses fate points for narrative influence; PbtA includes drama through GM moves.

14. **Rulebooks emphasise segmentation of time and sequences.** D\&D divides combat into rounds and turns; abilities such as **initiative** determine order. Fate uses **exchanges** and **turns**; Blades in the Dark segments play into **scores** and **downtime**, with clocks for long‑term projects[\[25\]](https://bladesinthedark.com/progress-clocks#:~:text=,the%20approach%20of%20impending%20trouble).

15. **Game ontologies and formal languages suggest representing rules as declarative expressions over state transitions.** GDL, RBG and VGDL encode **roles**, **initial states**, **legal moves**, **next states**, **termination** and **goal conditions**【912727920492451†L129-L199】. These correspond directly to the phases of a deterministic engine loop.

## Proposed Two‑Layer Taxonomy for TTRPG Rule Compilation

The taxonomy is organised in two layers to bridge the human‑readable structure of rulebooks (layer 1) and the compiler‑facing primitives needed to execute rules as code (layer 2). Each node lists typical section headings in TTRPG rulebooks, common synonyms, and hidden locations where information may be found.

### Layer 1: Human‑Facing Concepts

| Concept | Typical Sections / Synonyms | State Implications | Procedural Implications | Failure Modes |
| :---- | :---- | :---- | :---- | :---- |
| **Roles & Authority** | *“Game Master,” “Dungeon Master,” “Referee,” “MC,” “Keeper,” “Judge,” “Player Responsibilities”*; synonyms: GM, DM, MC, Referee. | Tracks which agent (player vs GM) has authority to narrate outcomes and set DCs. | Determines who calls for rolls, adjudicates rules, and resolves disputes. | Rules may be split between GM section and player section; authority guidelines often appear in introductions or sidebars; PbtA moves may hide GM responsibilities in play advice. |
| **Entities & Attributes** | *“Characters,” “Creatures,” “NPCs,” “Statistics,” “Attributes,” “Abilities,” “Skills,” “Aspects,” “Playbooks”*. | Defines data structures: ability scores, skills, hit points, stress, fate points, clocks, items, spells. | Provides methods to modify attributes (increase level, apply damage, recover stress), check prerequisites, create characters or monsters. | Rules may be scattered across character creation, monster manuals and equipment sections; some systems (e.g., PbtA) embed character moves in playbook lists. |
| **Actions & Moves** | *“Actions,” “Moves,” “Skill Checks,” “Tests,” “Challenges,” “Ability Checks,” “Tasks,” “Combat Actions,” “Maneuvers,” “Rolls”*; synonyms: act, attempt, check, test, move. | Determines what triggers a procedure; whether the state changes; may include action categories (attack, defend, cast, social, exploration). | Specifies how to resolve actions: choose appropriate rule (e.g., ability check, four Fate actions, Blades action rating); compute modifiers; roll dice; interpret result; update state. | Hidden in different chapters (combat, skill section, magic); sometimes only examples show how to perform an action; alternative names (e.g., “make a roll,” “act under fire”). |
| **Resolution & Outcomes** | *“Attack Rolls,” “Saving Throws,” “Skill Resolution,” “Success & Failure,” “Consequences,” “Resistance Rolls,” “Hit/Miss,” “Critical,” “Degrees of Success”*. | Encodes uncertain outcomes; may involve randomisers (d20, d6 dice pool, Fate dice), deterministic comparisons (fixed thresholds), or drama (GM decision). Tracks ongoing conditions like harm, stress, advantage. | Describes procedures: roll dice, add modifiers, compare to DC or effect scale, apply damage or consequences; update progress clocks or success ladders. | Sometimes found in rules summary or core mechanics section; details may be hidden in spells or combat examples; PbtA moves each list their own outcome tables; GM may need to infer consequences. |
| **Time & Turn Structure** | *“Turn Order,” “Rounds,” “Initiative,” “Phases,” “Exchanges,” “Scenes,” “Episodes,” “Sessions,” “Downtime,” “Clocks”*. | Tracks order of actions and progression; variables include initiative order, round number, scene progression, clock segments. | Procedures to update time: at start/end of round apply effects; check durations; update clocks; call for downtime or recovery phases. | Rules for segments may reside in combat chapter or GM section; some systems treat narrative time flexibly (PbtA scenes) while others are strict; retrieving them requires cross‑referencing. |
| **Resources & Progression** | *“Hit Points,” “Stress,” “Mana/Energy,” “Experience Points,” “Leveling,” “Advancement,” “Clocks,” “Fate Points,” “Luck,” “Coin & Stash.”* | Models consumable or accumulative resources; defines character progression (level, rank, playbook advancement) and resource caps. | Procedures: how resources are gained (XP awards, treasure), spent (casting spells, invoking aspects, pushing yourself), recovered (rest, downtime), and converted (level‑up benefits). | Often spread across equipment, reward, and advancement chapters; some resources (fate points, stress) explained in separate sections; PbtA improvements appear in end‑of‑session moves. |
| **State Transitions & Effects** | *“Conditions,” “Status Effects,” “Damage & Healing,” “Consequences & Harm,” “Clocks,” “Scene Effects,” “Environmental Hazards.”* | Defines discrete states (poisoned, stunned, on fire) and continuous measures (HP, stress segments). | Procedures to apply state transitions after resolution: mark or clear conditions; tick progress clocks; set timers; cascade triggers (e.g., hitting zero HP causes death saving throws). | Effects may be hidden in spells, items, or monster abilities; retrieving them requires scanning multiple sources; interplay between conditions sometimes appears only in GM advice. |
| **Exceptions & Overrides** | *“House Rules,” “Rule Zero,” “Exceptions,” “Feat/Spell Overrides,” “GM Fiat,” “Edge Cases.”* | Rules that modify or supersede default behaviour (e.g., a feat allows rerolls, a spell changes movement rules). | The engine must apply these with higher priority than general rules; may require rule precedence or conditional checks. | Exceptional rules often appear as character options, feats, spells or sidebars; rulebooks may remind that the GM can override any rule[\[11\]](https://dtdnd.neocities.org/books/dm/DungeonMastersGuide.pdf#:~:text=in%20charge,that%20when%20a%20situation%20comes). |
| **Narrative Authority & Fictional Positioning** | *“Storytelling,” “Describing Outcomes,” “Fiction First,” “Position & Effect,” “Move Triggers,” “Describe the Scene.”* | Tracks which narrative elements are established (locations, NPC intents, threats) and who can introduce new facts. | Procedures: in PbtA, moves trigger when fictional conditions occur; in Blades, the GM sets position and effect based on fiction[\[26\]](https://bladesinthedark.com/action-roll#:~:text=1,Goal); actions may be invalid if fiction doesn’t justify them. | Often in GM chapters or design essays; sometimes overlooked by players; retrieving this requires reading examples and advice sections. |

### Layer 2: Compiler‑Facing Primitives

The compiler needs more granular primitives to translate the human‑facing concepts into executable code.

1. **Entities/components:** data structures representing players, characters, NPCs, items, clocks, areas and resources (HP, stress, XP). Each component has attributes and may contain sub‑components (e.g., skills within characters).

2. **Procedures/steps:** algorithmic procedures for each action or rule (e.g., ability check, attack roll, Blades action roll). Each procedure defines input variables, conditions, randomiser usage and state updates.

3. **Inputs:** player choices (declaring an action, selecting a target, spending resources), GM choices (setting DC, position, effect, offering Devil’s Bargain), and random inputs (dice rolls, card draws). For deterministic rules such as karma‑based resolution, inputs may be fixed values.

4. **Outputs:** state patches indicating modifications (HP changes, resource expenditure, condition flags, clock segments ticked). Outputs also include narrative messages for display.

5. **Rule priorities and override patterns:** a system for deciding which rule applies when multiple rules conflict. For example, a spell description overrides the generic movement rule; GM fiat (Rule Zero) overrides all[\[11\]](https://dtdnd.neocities.org/books/dm/DungeonMastersGuide.pdf#:~:text=in%20charge,that%20when%20a%20situation%20comes). This layer may include a priority queue or predicate logic similar to GDL’s rule evaluation order【912727920492451†L129-L199】.

### Synonyms & Hidden Locations

For each concept, several synonyms appear across rulebooks: *GM/DM/MC*, *skill check/test* (D\&D), *move* (PbtA), *action rating* (Blades), *saving throw* vs **defense** (Fate uses “defend”), *scene* vs *round*, *stress* vs *strain/fatigue*, etc. Important rules may be hidden in appendices, sidebars or narrative advice; for example, the D\&D *Dungeon Master’s Guide* emphasises Rule Zero (GM is final arbiter) in an aside[\[11\]](https://dtdnd.neocities.org/books/dm/DungeonMastersGuide.pdf#:~:text=in%20charge,that%20when%20a%20situation%20comes), and PbtA move triggers are described in blog articles[\[22\]](https://lumpley.games/2020/07/12/powered-by-the-apocalypse-part-5/#:~:text=Let%E2%80%99s%20say%20that%20exert%20themself,advance%2C%20or%20might%20not%20even) rather than the basic rules.

## Retrieval Seed Questions by Taxonomy Concept

For each concept, practitioners ask informal questions that map to specific rule sections. Below are 2–5 natural‑language seed questions per concept; these can be used to evaluate retrieval systems across different rulesets.

### Roles & Authority

1. **“Who makes the final decision when there’s a disagreement about the rules?”** (GM authority)

2. **“What does the MC do during play?”** (PbtA; MC responsibilities and moves)

3. **“Can players add details to the world, or is that the GM’s job?”** (narrative authority)

4. **“When can I call for a roll, and when can the GM decide automatically?”** (call for checks)

5. **“Does this game have a rule zero?”** (override)  
   *Typical sections:* introductions, GM chapter, sidebars about “running the game”.  
   *Failure modes:* hidden in advice essays or blogs; players may not know the GM can say no.

### Entities & Attributes

1. **“How do I create a character and choose my abilities?”** (character creation)

2. **“How much damage can I take before I’m incapacitated?”** (hit points/stress)

3. **“Where do I find my skills or aspects?”**

4. **“What do these attributes mean in play?”**

5. **“How do I track progress on a project or clock?”** (Blades clocks)  
   *Typical sections:* character creation chapter, playbook pages, monsters section, gear and resources.  
   *Failure modes:* attributes may be split across chapters (e.g., skills vs abilities vs spells).

### Actions & Moves

1. **“How do I attack an enemy?”**

2. **“What happens when I try something risky?”** (skill checks)

3. **“Which action category should I use: overcome, create advantage, attack, or defend?”** (Fate)

4. **“What triggers a move in this game?”** (PbtA triggers)

5. **“When do I make an action roll and how do I choose the action rating?”** (Blades)  
   *Typical sections:* core mechanics chapter, “actions in combat”, “skills”, PbtA move lists.  
   *Failure modes:* action categories may be implicit; triggers may be described in examples rather than rules.

### Resolution & Outcomes

1. **“How do I resolve an attack roll and what counts as a hit?”** (D\&D attack roll)

2. **“What happens when I tie or miss a skill check?”**

3. **“How do critical successes or failures work?”**

4. **“How are consequences handled when I succeed with complications?”** (Blades, PbtA partials)

5. **“What dice or modifiers do I add for this kind of action?”**  
   *Typical sections:* attack rules, saving throws, skill resolution tables, outcome summaries.  
   *Failure modes:* partial successes and consequences may be scattered across examples; critical rules may be hidden in sidebars.

### Time & Turn Structure

1. **“Who acts first in combat and how is initiative determined?”**

2. **“How long is a round and what can I do on my turn?”**

3. **“What is a scene or exchange, and when does it end?”** (Fate, PbtA)

4. **“How do progress clocks tick down over time?”** (Blades)

5. **“What happens during downtime between sessions?”**  
   *Typical sections:* combat chapter, initiative rules, chapters on time and movement, downtime and clocks.  
   *Failure modes:* some games treat narrative time flexibly; segmentation rules may appear in GM advice or specific modules.

### Resources & Progression

1. **“How do I gain experience and level up?”**

2. **“What are fate points/stress/doom and how do I spend them?”**

3. **“How do I heal damage or recover stress?”**

4. **“What rewards do we get after a session or score?”** (loot, coin, stash)

5. **“How many segments are in this clock and what happens when it fills?”**  
   *Typical sections:* advancement chapter, gear and treasure, resource rules, downtime.  
   *Failure modes:* resource rules may be distributed across multiple chapters; some advancement options may appear in class descriptions or playbooks.

### State Transitions & Effects

1. **“What conditions can affect my character (poisoned, stunned, broken) and what do they do?”**

2. **“How do I apply damage and when do I die?”** (death saves)

3. **“How do I remove a status effect?”**

4. **“When do I tick a progress clock or consequence track?”**

5. **“What happens when a spell changes the environment (e.g., slow or sleep)?”**  
   *Typical sections:* conditions list, damage & healing, consequences and resistance sections, spells or abilities.  
   *Failure modes:* state effects may be in appendices; interplay of conditions may be referenced only in GM guidance.

### Exceptions & Overrides

1. **“Does this feat/spell/edge override the normal rule for this action?”**

2. **“Can the GM veto a rule in favour of the story?”** (Rule Zero)

3. **“Are there house rules that replace or modify core mechanics?”**

4. **“How do conflicting rules interact—does specific trump general?”**  
   *Typical sections:* feats/spells/class features, optional rules, GM advice.  
   *Failure modes:* exceptions are often in disparate lists; rule precedence may not be explicitly spelled out.

### Narrative Authority & Fictional Positioning

1. **“Do I need to describe my character’s action before rolling?”**

2. **“Can I make up details about the world, or does the GM decide everything?”**

3. **“What triggers this move—fictional circumstances or a command like ‘start of session’?”** (PbtA triggers)

4. **“How do I determine position and effect based on the fiction?”** (Blades)  
   *Typical sections:* game philosophy, PbtA MC moves, Blades “position & effect” guidelines, examples of play.  
   *Failure modes:* narrative rules may be found in blog posts or supplemental essays rather than the core rulebook.

## Universal Benchmark Core Questions

To support cross‑system rule retrieval and evaluation, a minimal benchmark of general questions should be included for every ruleset. Each question is accompanied by paraphrases to address terminology drift, notes on the expected rulebook section, and whether the question is primarily player‑facing or GM‑facing.

| Core Question | Paraphrase 1 | Paraphrase 2 | Typical Section(s) | Player/GM |
| :---- | :---- | :---- | :---- | :---- |
| **How do I perform an action and determine success?** | “What do I roll to try something risky?” | “How are tests or checks resolved?” | Core mechanics, skill or move list, action resolution rules[\[15\]](https://5thsrd.org/rules/abilities/ability_checks/#:~:text=An%20ability%20check%20tests%20a,the%20dice%20determine%20the%20results) | Player & GM |
| **How are attack rolls resolved and what counts as a hit?** | “What die do I roll to strike an enemy?” | “How do I know if my attack lands?” | Combat chapter or attack rules[\[16\]](https://www.dandwiki.com/wiki/5e_SRD:Attack_Rolls#:~:text=When%20you%20make%20an%20attack%2C,is%20in%20its%20stat%20block) | Player |
| **What happens when I fail, tie or succeed with complications?** | “What are partial successes or mixed results?” | “What are the consequences of a 4/5 result?” | Outcome tables, consequences and harm sections[\[20\]](https://bladesinthedark.com/action-roll#:~:text=6,Judge%20the%20Result) | GM & Player |
| **How are turn order and timing handled?** | “How is initiative determined and who acts first?” | “What is a round, scene or exchange?” | Combat/time chapter, initiative rules[\[17\]](https://www.5esrd.com/using-ability-scores/#:~:text=,personality) | Player & GM |
| **What resources track my character’s condition and progress?** | “How many hit points/stress segments do I have?” | “How do I advance or level up?” | Character creation, advancement, stress or damage rules[\[21\]](https://bladesinthedark.com/progress-clocks#:~:text=,the%20approach%20of%20impending%20trouble) | Player |
| **Who has authority to call for rolls or decide outcomes?** | “Does the GM decide when to roll?” | “Can players initiate checks or moves?” | GM chapter, rule zero/authority sidebars[\[11\]](https://dtdnd.neocities.org/books/dm/DungeonMastersGuide.pdf#:~:text=in%20charge,that%20when%20a%20situation%20comes) | GM |
| **How do I handle special abilities or exceptions that modify the rules?** | “Does this spell override normal movement rules?” | “Do feats or playbook moves change how actions work?” | Spells/feats/class features/playbooks | Player & GM |
| **What happens when a character reaches zero health or suffers a severe consequence?** | “How do death saving throws work?” | “What are trauma or burnout rules?” | Damage & healing, consequences & trauma sections | Player & GM |
| **How do we track ongoing challenges or long‑term projects?** | “What are progress clocks and how do they fill?” | “How do I measure progress toward my goal?” | Clocks, long‑term projects, quests or downtime rules[\[25\]](https://bladesinthedark.com/progress-clocks#:~:text=,the%20approach%20of%20impending%20trouble) | Player & GM |
| **When and how can players influence the narrative (e.g., spending points or invoking aspects)?** | “What can I spend a fate point on?” | “Can I describe something into existence with a move?” | Fate points, narrative currencies, PbtA moves, MC advice | Player |

## Mapping Taxonomy Concepts to a Deterministic Engine Loop

The deterministic engine loop described by the game programming pattern provides a blueprint for executing compiled TTRPG rules. Each cycle of the loop corresponds to phases that evaluate rules, solicit inputs, update state, and progress time[\[10\]](https://gameprogrammingpatterns.com/game-loop.html#:~:text=This%20is%20the%20first%20key,The%20loop%20always%20keeps%20spinning). The taxonomy concepts map onto this loop as follows:

1. **Evaluate Rules (processInput & update):**  
   *The system checks current state and identifies which rules are relevant.*  
   – **Roles & Authority** determine who can propose actions and call for rolls.  
   – **Actions & Moves** provide a catalogue of possible procedures triggered by player declarations or fictional events.  
   – **Exceptions & Overrides** adjust rule priority (e.g., a specific spell effect supersedes a general rule).  
   – **Narrative Authority & Fictional Positioning** ensure that moves are only triggered when fictional prerequisites are met[\[22\]](https://lumpley.games/2020/07/12/powered-by-the-apocalypse-part-5/#:~:text=Let%E2%80%99s%20say%20that%20exert%20themself,advance%2C%20or%20might%20not%20even).

2. **Request Choice/Randomisation (processInput):**  
   *The engine asks for player inputs or random values.*  
   – **Entities & Attributes** supply relevant modifiers (e.g., ability scores, skills).  
   – **Actions & Moves** specify what dice or randomisers to use (d20, dice pool, Fudge dice) or when to use deterministic comparisons.  
   – **Resources & Progression** and **Narrative Authority** may require players to spend points (fate points, stress) or accept Devil’s Bargains[\[27\]](https://bladesinthedark.com/action-roll#:~:text=5).

3. **Commit Transition (update):**  
   *The engine applies the rule’s outcome to the state.*  
   – **Resolution & Outcomes** determine success, partial success or failure, apply damage or consequences, tick clocks, update positional states and trigger follow‑on effects[\[20\]](https://bladesinthedark.com/action-roll#:~:text=6,Judge%20the%20Result).  
   – **State Transitions & Effects** encode changes to conditions, clocks and resources.  
   – **Progression & Resources** update XP and advancement.  
   – **Exceptions & Overrides** may change the usual transition (e.g., resistance rolls reduce harm).

4. **Next Frame/Tick (render & loop):**  
   *The loop advances time and prepares for the next input.*  
   – **Time & Turn Structure** controls progression through rounds, scenes or turns; updates initiative order and durations.  
   – **Narrative Authority** determines who describes the outcome and sets the next scene (GM or players).  
   – **Resources & Progression** may refresh (e.g., regain stress during downtime) or degrade (e.g., tick clocks).  
   – The loop repeats until a termination condition is met (end of session, mission success/failure) as specified in rules or GM guidance.

By aligning TTRPG rules with this engine loop, compilers can transform PDF rulebooks into declarative models (similar to GDL or RBG) where rules become state transition functions triggered by inputs. The universal benchmark questions above help ensure that retrieval systems surface the necessary rules for each phase.

---

[\[1\]](https://computerscience.chemeketa.edu/cis125greader/WhatIsAGame/AGame.html) [\[2\]](https://computerscience.chemeketa.edu/cis125greader/WhatIsAGame/AGame.html#:~:text=Here%20are%20some%20definitions%20from,various%20sources) 3.1. Defining “Game” — CIS125G Reader

[https://computerscience.chemeketa.edu/cis125greader/WhatIsAGame/AGame.html](https://computerscience.chemeketa.edu/cis125greader/WhatIsAGame/AGame.html)

[\[3\]](https://gameontology.com/index.php/Rules#:~:text=The%20rules%20and%20constraints%20of,%28Looney%201998) Rules \- gameontology

[https://gameontology.com/index.php/Rules](https://gameontology.com/index.php/Rules)

[\[4\]](https://gameontology.com/index.php/Gameworld_Rules#:~:text=In%20non,the%20game%2C%20the%20gameworld%20rules) Gameworld Rules \- gameontology

[https://gameontology.com/index.php/Gameworld\_Rules](https://gameontology.com/index.php/Gameworld_Rules)

[\[5\]](https://www.gents.it/FILES/ebooks/Game_Design_Patterns.pdf) Game Design Patterns / Jussi Holopainen, Staffan Björk, Bernd Kreimeier

[https://www.gents.it/FILES/ebooks/Game\_Design\_Patterns.pdf](https://www.gents.it/FILES/ebooks/Game_Design_Patterns.pdf)

[\[6\]](https://en.wikipedia.org/wiki/Game_Description_Language#:~:text=Rules%20that%20describe%20the%20conditions,are%20no%20more%20blank%20spaces) Game Description Language \- Wikipedia

[https://en.wikipedia.org/wiki/Game\_Description\_Language](https://en.wikipedia.org/wiki/Game_Description_Language)

[\[7\]](https://arxiv.org/abs/1706.02462#:~:text=,large%20chess%20variants%2C%20go%2C%20international) \[1706.02462\] Regular Boardgames

[https://arxiv.org/abs/1706.02462](https://arxiv.org/abs/1706.02462)

[\[8\]](https://drops.dagstuhl.de/storage/02dagstuhl-follow-ups/dfu-vol006/DFU.Vol6.12191.85/DFU.Vol6.12191.85.pdf) DFU.Vol6.12191.85.pdf

[https://drops.dagstuhl.de/storage/02dagstuhl-follow-ups/dfu-vol006/DFU.Vol6.12191.85/DFU.Vol6.12191.85.pdf](https://drops.dagstuhl.de/storage/02dagstuhl-follow-ups/dfu-vol006/DFU.Vol6.12191.85/DFU.Vol6.12191.85.pdf)

[\[9\]](https://www.idsia.ch/~schaul/publications/pyvgdl.pdf#:~:text=blocks%2C%20and%20the%20interaction%20effects,range%20of%20learning%20scenarios%2C%20we) pyvgdl.pdf

[https://www.idsia.ch/\~schaul/publications/pyvgdl.pdf](https://www.idsia.ch/~schaul/publications/pyvgdl.pdf)

[\[10\]](https://gameprogrammingpatterns.com/game-loop.html#:~:text=This%20is%20the%20first%20key,The%20loop%20always%20keeps%20spinning) Game Loop · Sequencing Patterns · Game Programming Patterns

[https://gameprogrammingpatterns.com/game-loop.html](https://gameprogrammingpatterns.com/game-loop.html)

[\[11\]](https://dtdnd.neocities.org/books/dm/DungeonMastersGuide.pdf#:~:text=in%20charge,that%20when%20a%20situation%20comes) Dungeon Master's Guide Core Rulebook II v.3.5

[https://dtdnd.neocities.org/books/dm/DungeonMastersGuide.pdf](https://dtdnd.neocities.org/books/dm/DungeonMastersGuide.pdf)

[\[12\]](https://pf2.d20pfsrd.com/rules/game-mastering/#:~:text=Game%20Mastering) [\[13\]](https://pf2.d20pfsrd.com/rules/game-mastering/#:~:text=As%20Game%20Master%2C%20you%20have,and%20how%20nonplayer%20characters%20act) Game Mastering – PF2 SRD

[https://pf2.d20pfsrd.com/rules/game-mastering/](https://pf2.d20pfsrd.com/rules/game-mastering/)

[\[14\]](https://www.5esrd.com/using-ability-scores/#:~:text=,personality) [\[17\]](https://www.5esrd.com/using-ability-scores/#:~:text=,personality) Ability Scores – 5th Edition SRD

[https://www.5esrd.com/using-ability-scores/](https://www.5esrd.com/using-ability-scores/)

[\[15\]](https://5thsrd.org/rules/abilities/ability_checks/#:~:text=An%20ability%20check%20tests%20a,the%20dice%20determine%20the%20results)  Ability Checks \- 5th Edition SRD 

[https://5thsrd.org/rules/abilities/ability\_checks/](https://5thsrd.org/rules/abilities/ability_checks/)

[\[16\]](https://www.dandwiki.com/wiki/5e_SRD:Attack_Rolls#:~:text=When%20you%20make%20an%20attack%2C,is%20in%20its%20stat%20block) 5e SRD:Attack Rolls \- D\&D Wiki

[https://www.dandwiki.com/wiki/5e\_SRD:Attack\_Rolls](https://www.dandwiki.com/wiki/5e_SRD:Attack_Rolls)

[\[18\]](https://fate-srd.com/fate-core/four-actions#:~:text=When%20you%20make%20a%20skill,an%20advantage%2C%20attack%2C%20or%20defend) Four Actions • Fate Core

[https://fate-srd.com/fate-core/four-actions](https://fate-srd.com/fate-core/four-actions)

[\[19\]](https://bladesinthedark.com/action-roll#:~:text=Action%20Roll) [\[20\]](https://bladesinthedark.com/action-roll#:~:text=6,Judge%20the%20Result) [\[26\]](https://bladesinthedark.com/action-roll#:~:text=1,Goal) [\[27\]](https://bladesinthedark.com/action-roll#:~:text=5) Action Roll | Blades in the Dark RPG

[https://bladesinthedark.com/action-roll](https://bladesinthedark.com/action-roll)

[\[21\]](https://bladesinthedark.com/progress-clocks#:~:text=,the%20approach%20of%20impending%20trouble) [\[25\]](https://bladesinthedark.com/progress-clocks#:~:text=,the%20approach%20of%20impending%20trouble) Progress Clocks | Blades in the Dark RPG

[https://bladesinthedark.com/progress-clocks](https://bladesinthedark.com/progress-clocks)

[\[22\]](https://lumpley.games/2020/07/12/powered-by-the-apocalypse-part-5/#:~:text=Let%E2%80%99s%20say%20that%20exert%20themself,advance%2C%20or%20might%20not%20even) [\[23\]](https://lumpley.games/2020/07/12/powered-by-the-apocalypse-part-5/#:~:text=The%20second%20angle%20I%20want,event%20or%20a%20nonfictional%20one) Powered by the Apocalypse, part 5 – lumpley games

[https://lumpley.games/2020/07/12/powered-by-the-apocalypse-part-5/](https://lumpley.games/2020/07/12/powered-by-the-apocalypse-part-5/)

[\[24\]](https://en.wikipedia.org/wiki/GNS_theory#:~:text=GNS%20theory%20is%20an%20informal,engagement%3A%20Gamism%2C%20Narrativism%20and%20Simulation) GNS theory \- Wikipedia

[https://en.wikipedia.org/wiki/GNS\_theory](https://en.wikipedia.org/wiki/GNS_theory)