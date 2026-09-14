# Locking the look before the first line of code

> Part of the `unity-game-brief` skill. This file decides **what gets locked, how many rounds it
> takes, and what "accepted" means**. Generating the images, the art bible and the anchor is
> `codex-visual`; that skill generates, this section decides.

Code written before the look is settled encodes a guess about scale, contrast and camera, and the
guess is load-bearing: lane spacing, type size, hazard silhouette size and camera pitch all appear
in gameplay constants. Changing them after a week of work is not a re-skin, it is a re-tune.

So: **an image the human has said yes to comes before the first gameplay constant.** Not an art
pipeline, not a full style guide — five decisions.

---

## The five decisions, and no more

| Decision | What locking it means | What it stops later |
|---|---|---|
| **Palette roles** (≤5) | Each colour has exactly one meaning: the thing the player reacts to, the ground it moves over, the destination, the danger, the neutral. Never two meanings for one colour. | A hazard and a pickup that read the same at speed |
| **Reactive-vs-ground contrast** | A ratio, not an adjective. Default floor **3:1** between anything the player reacts to and whatever is directly behind it. | A build that is only readable on the machine it was authored on |
| **Three silhouettes** | The three shapes from the brief's three moments, recognisable in black on white at the size they ship. | Art that works in the mockup and vanishes in motion |
| **Camera** | Distance, pitch, and the aspect it is framed for, as numbers. | Every layout number being wrong at once |
| **Anchor image** | One file, one path, referenced from the brief. Everything later is compared to it. | Style drift with nothing to point at |

Anything else — final resolution, animation counts, tile sets, UI chrome, the art bible's full
schema — is not a day-one decision and belongs to `codex-visual` and to the asset skills.

**The contrast number belongs in the brief**, because at 2–3 m from a propped-up tablet it is the
difference between a game and a blur. The measurement and the type sizes that follow from it are
`unity-game-ui`.

---

## The iteration budget, and the rule that stops it

Style exploration has no natural end, so it gets a budget before it starts:

```
2-3 distinct boards  ->  the human picks one  ->  at most 2 correction rounds  ->  LOCKED
```

- **2–3 boards, deliberately different.** Three variations on one idea is one board shown three
  times; it tells you nothing and costs three generations.
- **The human picks.** Not "which do you prefer" alongside a recommendation the agent argues for —
  present them flat, one line each on what differs.
- **At most two corrections.** If the third round is needed, the *brief* is wrong, not the image:
  go back and ask what the picture is supposed to make the player feel in the "during" moment.
- **Locked means locked for the first version.** A locked direction is allowed to be wrong; it is
  not allowed to be re-opened while the first interaction is being built. Re-opening it is a
  decision with a date, recorded as one.

---

## How to give correction feedback

Free-form notes on an image produce a different image, not a closer one. One sentence, one axis:

> **keep [what works], change [one axis], toward [the other end], not all the way.**

Worked, from the courier run:

- "Keep the three-lane read and the gate glow; change the hazard value, toward darker against the
  lane, not all the way to black."
- "Keep the palette; change the camera pitch, toward lower so the next row sits higher in frame,
  about halfway."
- "Keep the runner silhouette; change its size, toward larger so it survives at 2–3 m, one step."

Three things make a correction cheap: it names what survives (so the next round does not lose it),
it moves **one** axis (so the result is attributable), and it gives a distance ("halfway", "one
step") rather than a destination.

**Never write correction feedback as a list of five adjectives.** The result is a new direction
that nobody chose, and the two-round budget is gone.

---

## Accepting a direction — five checks, in this order

Run these against the candidate *before* asking for the yes, and report the failures rather than
the opinion:

1. **Silhouette test.** The three shapes in solid black at shipping size. Still tellable apart?
   A hazard that becomes a pickup at 24 px is a gameplay bug drawn in advance.
2. **Distance test.** View the board at the brief's distance — 2–3 m for the propped-up tablet — or
   scale it down by the equivalent factor. Whatever the player must react to has to survive it.
3. **Contrast check.** Sample the reactive colour against the ground colour behind it; check the
   ratio against the floor in the brief. A number, not a glance.
4. **Aspect check.** Reframe to the brief's aspect. Art that is composed for a square and shipped
   at 16:10 loses whichever edge carried the information.
5. **Motion sanity.** The player's eye is on the runner; the thing they must react to enters from
   the far edge. Is it distinguishable *before* it is reacted to, or only once it is close?

Then ask for the yes, in one message, with the board attached and the five results listed. A yes
given against these five is a yes that survives; a yes given to "do you like this?" is not.

---

## Where it is recorded

Two files, and they say different things:

- **`GAME_BRIEF.md` — "Visual direction (locked)"**: the five decisions, as values. This is what the
  gameplay constants are derived from, and it is short on purpose.
- **`ART_DIRECTION.md`** — the art bible: style preamble, palette hexes, formats, folder layout,
  anchor path, version and changelog. Its schema and every generation mechanic are `codex-visual`.

The brief points at the anchor path; it does not duplicate the bible. When the bible's version
bumps, the brief's line is checked against it — that check is one `grep` and it catches the case
where the art moved on and the gameplay constants did not.

**If there is no `ART_DIRECTION.md` yet and the art is hand-made or bought**, the five decisions
still get written into the brief. They are decisions about the game, not about the pipeline.
