# Where HUD belongs in a 3D game's frame

Placement is not taste. The camera decides which parts of the frame carry information the player
must act on, and HUD goes everywhere else.

## Find the vanishing point and leave it alone

In a forward-running 3D game, **everything the player must react to arrives at the vanishing
point**: the gate, the sentry, every hazard, smallest and furthest and earliest. A panel parked
there hides each one for the whole time it is still avoidable.

A conventional three-part top bar — score / timer / hearts — puts its centre panel exactly on that
point. It looks balanced, and it covers the gate posts.

**Leave the centre of the horizon empty and say so in the code**, or someone will "fix" the
asymmetry later:

```csharp
// NOTHING goes in the top centre. That point is the track's vanishing point: the gate, the
// sentry and every hazard arrive there, smallest and furthest, and a panel parked on it hides
// them for the whole time they are still avoidable. Score and hearts stay at the EDGES, over the
// roadside, where they cost nothing.
```

The edges are free: they show sky, roadside, scenery — nothing actionable. That is where readouts go.

## Map the frame before placing anything

Take a real screenshot of the busiest moment and write down the bands:

```
0 – 12%    gate, sentry, distant hazards     ← never cover
12 – 38%   empty road                         ← the one free band mid-frame
38 – 75%   the player character
75 – 100%  near-field ground                  ← free; the thumbs live here
```

Prompts belong in the free mid-band; controls and status belong at the bottom. Anything that must
cross something should cross **the runner's own legs**, never a hazard, a pickup, or the gate.

## Corners for thumbs, centre-bottom for status

In landscape the bottom corners are where thumbs rest, so lane controls go bottom-left and the
action button bottom-right. Never a centred row of three: it sits directly over the lane the player
is running down, which is the one part of the road that has to stay readable.

That leaves the **bottom centre** free, and it is the best place for a status readout — near-field
ground, nothing to occlude, and it completes a row the eye already reads as one band:

```
[←][→]  ·······  [⏱ 28]  ·······  [↑]
```

## Swap the slot, do not empty it — unless emptying it is the point

A bar that loses a section mid-game reads as a fault. Swap its contents instead. **But** if the
slot sits on something the player needs to see, emptying it is correct and the asymmetry is the
lesser cost. Decide from what is behind the panel, not from the shape of the bar.

## When the mode changes, change the controls

The run's control layout is a *lane-changing* scheme. The launch is a *direction-chosen* one. Reusing
the layout — and worse, reusing the up-arrow glyph that meant "jump" for the previous thirty
seconds — silently changes what a symbol means at the one moment the player cannot take it back.

Give the new mode its own row, centred, mirroring the choice: `←  ●  →`. The visible
reconfiguration is a feature: it announces that the controls mean something different now.

## Do not read a 2D layout without checking the 3D scale

"The gate looks tiny" is a camera problem, not a UI one. Work it out:

- A 6 m gate drawn at 4.2 world units puts the scale at `6 ÷ 4.2 ≈ 1.43` m per unit, so the
  gate is the **right** size — derive yours the same way before calling a size wrong. The problem
  is that the phase begins 26 units out, where the gate covers 8% of the screen width.
- Halving the approach helps; the bigger lever is the camera. A racing broadcast cuts to a closer
  angle at the finish line. Blending — never cutting — pitch 21°→12°, distance 8→7, look-ahead 3→3.4
  turns a distant object into the whole frame, with the runner still in it.

Blend the framing over ~0.5 s so the player never loses their bearings, and check the arithmetic in
`layout-math.md` before running it — a look-ahead chosen by eye puts the camera in front of the
player, and the character leaves the frame entirely.
