# Board HUD — the turn-order strip and the range legend

> Part of the `unity-game-ui` skill. The two pieces of HUD a turn-based board game needs that a
> real-time game does not. The rules and the data come from `unity-2d-grid` (`TurnQueue`, and
> the highlight Tilemap: `unity-2d-grid` → `reference/picking.md`); this file is how they read
> on screen. Build them in whichever UI system `SKILL.md` §0 picked.

## The turn-order strip

It answers one question at a glance: who acts now, and who acts next.

- **One edge, one direction.** Top edge on a landscape screen, reading from the anchor end: the
  current actor at the anchor, the next ones after it. Never reorder the cells in place while the
  player reads it; on `Advance()` the strip shifts by one cell.
- **Fixed cell size**, sized from the type scale for the viewing distance
  ([`type-scale.md`](type-scale.md)), and a fixed count: the current actor plus the next N, read
  with `TurnQueue.Peek(0..N)`. A strip that grows with the cast pushes the board around.
- **The current actor is marked twice**: a larger cell and a frame, not colour alone
  ([`colour-and-contrast.md`](colour-and-contrast.md) §5). Side (runner team or sentries) is a
  shape or a badge, with colour as the second cue.
- **The round boundary is visible** when `Peek` wraps into the next round: a divider, not a gap that
  looks like a missing actor.
- **Hovering a cell in the strip highlights that unit on the board**, and hovering a unit on the
  board highlights its cell in the strip. The link is what makes the strip useful in a crowd.
- **It reads state; it never owns it.** Rebuild it from `TurnQueue` on `RoundStarted` and after each
  `Advance()`, `Remove()` or `SetInitiative()`, so an undo cannot leave it out of step.

## The range legend

Range overlays on the board (move, attack, a sentry's sight) need a key the first time a player
sees them and stay out of the way after that.

- **One corner, away from the strip and the action menu**
  ([`hud-placement.md`](hud-placement.md)). A small swatch per overlay with a one-word label: Move,
  Attack, Sight.
- **The swatch is the tile.** Draw it with the same sprite and colour the highlight Tilemap uses, so
  a palette change cannot desynchronise the key from the board.
- **Overlays differ by more than hue**: a fill for move, an outline or hatch for attack, a dotted
  edge for sight. Two overlays on one cell must both stay readable; check that pair on screen.
- **Contrast against the board, not a blank panel**: measure the overlay colours against the
  ground tiles they sit on ([`colour-and-contrast.md`](colour-and-contrast.md) §6).
- **Show only the overlays on screen now.** The legend lists what the board currently shows and
  hides when nothing is highlighted.

## Checking it

Screenshot a turn with the most units the level holds and the densest overlay (move and attack
together), at the smallest target screen. The strip should name the current actor without
squinting, and every coloured cell on the board should have its row in the legend.
