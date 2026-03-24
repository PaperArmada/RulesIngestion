DnD 5e Rules on Occupying the Same Space

This note summarises official and community‑documented rules for creatures occupying the same space in Dungeons & Dragons 5th Edition (2014) and notes changes previewed for the 2024 Player’s Handbook. It focuses on rules that determine when creatures can move through or end their movement in another creature’s space.

Basic PHB/Basic Rules (2014 SRD)

The System Reference Document (SRD) replicates the core rules of the 2014 Player’s Handbook and establishes three key principles:

Move through a friendly creature: You can move through a non‑hostile creature’s space, but the space counts as difficult terrain. Moving through an ally’s square costs an extra 5 feet of movement.

Move through a hostile creature: You may only move through a hostile creature’s space if it is at least two sizes larger or smaller than you. Otherwise you cannot pass through it.

Cannot end your move in another creature’s space: Whether the creature is friendly or hostile, you cannot willingly end your move in its space. If you attempt to stop there, you must keep moving until you occupy an unoccupied space.

These rules mean that, under normal circumstances, two creatures of similar size cannot occupy the same square at the end of a turn. They can briefly pass through each other’s spaces during movement, but one creature’s space is considered difficult terrain for the other.

Variant: Grid‑Based Creature Space (DMG p. 251)

When using an optional tactical grid, the Dungeon Master’s Guide includes a variant table stating that:

One Small or Medium creature occupies a single 5‑foot square.

Up to four Tiny creatures can fit into the same 5‑foot square.

Larger creatures occupy multiple squares (Large = 2×2 squares, Huge = 3×3 squares, Gargantuan = 4×4 squares).

This is a tactical convenience guideline rather than a core rule, and it still assumes only one creature fights effectively in its space. It acknowledges that additional tiny creatures can physically fit into the area but does not override the general rule that you cannot willingly end your move in another creature’s square.

Racial/Creature Abilities that Bypass the Rule

Several abilities and creature traits explicitly allow moving through (and sometimes occupying) other creatures’ spaces.

Halfling Nimbleness

Halflings have a racial trait called Nimbleness allowing them to “move through the space of any creature that is of a size larger than yours”. They still cannot end their movement in that space.

Incorporeal Movement & Ethereal Forms

Some undead or spectral creatures and spells grant the ability to move through creatures and objects. For example:

Swarm of Quippers (and other swarms): the Swarm trait states that “the swarm can occupy another creature’s space and vice versa, and the swarm can move through any opening large enough for a Tiny quipper”. Swarms represent many tiny creatures acting as a single entity and are exempt from the normal occupancy rules.

Greater Ghost / Incorporeal Movement: certain monsters such as the ghost have Incorporeal Movement, which lets them move through creatures and objects as if they were difficult terrain; if they end their turn inside an object they take force damage. This allows them to share a space temporarily.

Stygian Shade (Third‑party SRD): the Ghostly Flesh trait allows the character to become spectral; during this transformation they can “move through creatures and solid objects as if they were difficult terrain”, but if they end their turn inside an object they take 1d10 force damage.

These abilities treat other creatures’ spaces as difficult terrain and impose penalties if the creature remains inside an object or another creature. They illustrate that exceptions exist but always include consequences or limitations.

Tiny creatures and squeezing rules

The rules section on Squeezing into a Smaller Space states that a creature may squeeze into a space large enough for a creature one size smaller. While squeezing, movement costs extra and attacks and Dexterity saves are at disadvantage. This allows multiple creatures to crowd into a limited area (e.g., several halflings squeezing into a 10‑foot corridor), but does not override the restriction on ending movement in another creature’s space.

2024 Player’s Handbook Preview: Stacking Allies

Previews of the 2024 Player’s Handbook indicate that allied creatures may stack in the same square by going prone. The Gaming Nexus summary notes that under the 2014 PHB you could move through a non‑hostile creature’s space but could not end your turn there. In the 2024 rules, you can end your turn in an ally’s space by becoming prone, with the prone creature lying under the standing ally. Moving through an ally’s space also no longer counts as difficult terrain. This change has not yet taken effect in the 2014 rules but shows how the designers intend to relax the restriction for friendly stacking.

Example Situations

Normal creatures (Medium or Small): A fighter cannot end its movement on top of a wizard unless the 2024 stacking rule (prone) is used. Even if the fighter moves through the wizard’s space, the rules require it to finish in an unoccupied space.

Halfling moving past a Human: A halfling can move through a human’s space (Nimbleness trait), but the space is still difficult terrain and the halfling cannot stop there.

Tiny familiars: Up to four Tiny creatures can fit into one 5‑foot square under the DMG variant rule. However, if combat uses the basic rules rather than a tactical grid, the DM may adjudicate how many tiny creatures can cluster in a space.

Swarms and incorporeal creatures: A swarm of quippers can occupy the same space as another creature, and a ghost can move through a creature’s space as if it were difficult terrain. These are explicit exceptions.

Deriving a Generic Occupancy Constraint

From the above evidence, a generic rule for a grid‑based engine might be formulated as follows:

Default constraint: Only one non‑spectral creature of Small or larger size may end its turn in a 5‑foot cell. Creatures may move through another creature’s cell if the other creature is non‑hostile (or at least two sizes difference if hostile), but the space counts as difficult terrain. Halflings and other creatures with similar traits may also move through larger creatures’ spaces.

Exceptions:
• Creatures or forms with traits like Nimbleness, Swarm, Incorporeal Movement, Etherealness or Ghostly Flesh can move through other creatures’ spaces (difficult terrain) and may briefly share them.
• Under the DMG tactical grid variant, up to four Tiny creatures may occupy a single 5‑foot cell.
• The 2024 PHB allows an ally to end its turn in your space by going prone.

This default constraint combined with enumerated exceptions provides a solid basis for constructing a runtime “placement prohibition” rule for a single‑cell engine. It enforces that two solid, non‑exceptional entities cannot occupy the same space, while allowing explicit exceptions (swarms, incorporeal creatures, Tiny stacking, 2024 prone stacking) to override the prohibition.
