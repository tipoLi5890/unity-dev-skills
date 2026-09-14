# ARCHITECTURE_PROPOSAL.md

<!-- Copy to the project root. This is the agent's proposal, derived line by line from
     GAME_BRIEF.md — every decision below must name the constraint that forced it. A decision
     with no constraint behind it is a preference and belongs in the open question at the
     bottom, or nowhere. Method: the skill's reference/architecture-proposal.md. -->

**Derived from:** GAME_BRIEF.md <!-- revision or date --> · **Status:** PROPOSED <!-- PROPOSED | ACCEPTED -->

## Constraints → decisions

<!-- Four columns, and the third is the one that makes this document worth reading: naming what
     the decision rules OUT is how a reader can disagree with it cheaply. "Routed to" is the
     skill or file that owns the detail, so this page stays a derivation and not a manual. -->

| Constraint (from the brief) | Forced decision | Rules out | Routed to |
|---|---|---|---|
| | | | |
| | | | |
| | | | |

## Layers

<!-- One row per assembly. Keep it to four or fewer on day one; a fifth is easier to add later
     than a wrong boundary is to move. -->

| Assembly | Owns | May reference | Engine references |
|---|---|---|---|
| | | | |
| | | | |

## What talks to what

<!-- At most six arrows, each "A --<what> --> B". If it needs a seventh, a layer is doing two
     jobs. Name the payload on every arrow: an arrow whose payload you cannot name is a
     dependency nobody has designed. -->

```
```

## Swappable

<!-- For each part that is expected to change: what it is, what would replace it, and the ONE
     type that crosses the boundary. If more than one type crosses, it is not swappable yet —
     say so here rather than discovering it during the swap. -->

| Part | Replaced by | The one type that crosses |
|---|---|---|
| | | |

## Deliberately NOT done

<!-- Things a reader would expect and will not find, each with the reason. This is not the
     brief's "not in the first version" list (that is about content); this is about structure:
     no networking layer, no save system, no scene per level, no physics on the player. -->

-
-

## First interaction

<!-- One sentence naming what will be playable, plus the Done list: what must be true before a
     human is asked to play it, and the command that proves each item. -->

**What:**

| Done when | Proved by |
|---|---|
| | |
| | |

## One open question

<!-- Exactly one, and it must be a real fork the human has to decide — not "does this look
     right". State the two branches and the default you will build if nobody answers, so the
     absence of an answer does not block the work. -->

**Question:**

**Default if unanswered:**
