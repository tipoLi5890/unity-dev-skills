# Rule tile patterns — the neighbour tables, and two errors in the ones in circulation

A `TilingRule` is a set of assertions about the eight cells around a tile. Write them as a
one-line pattern and the whole rule set fits on a page. This file is the lookup: the symbols, the
cell-to-`Vector3Int` map, the rectangular tables, and what hexagonal changes.

## Symbols

| Symbol | Rule value | What it asserts |
|---|---|---|
| `.` | `Neighbor.This` | That cell holds this same rule tile |
| `X` | *(nothing)* | Don't-care. **Not a constant** — the cell is don't-care because its position was never added to the neighbour lists |
| `*` | — | The tile itself. Always skipped |

`Neighbor.NotThis` has no symbol here because these tables never use it. It asserts the opposite
— that the cell does *not* hold this tile — and it belongs in hand-written rules, not in a set
generated from art.

Pattern layout is rows top to bottom, cells left to right, ` / ` between rows:

```
T T T / L * R / B B B
```

## Cell index to grid offset

```
index 0 1 2      offset  (-1, 1, 0)  ( 0, 1, 0)  ( 1, 1, 0)
index 3 * 5              (-1, 0, 0)      —       ( 1, 0, 0)
index 6 7 8              (-1,-1, 0)  ( 0,-1, 0)  ( 1,-1, 0)
```

| Index | Cell | `Vector3Int` |
|---|---|---|
| 0 | top-left | `(-1, 1, 0)` |
| 1 | top | `(0, 1, 0)` |
| 2 | top-right | `(1, 1, 0)` |
| 3 | left | `(-1, 0, 0)` |
| 4 | centre | *skipped* |
| 5 | right | `(1, 0, 0)` |
| 6 | bottom-left | `(-1, -1, 0)` |
| 7 | bottom | `(0, -1, 0)` |
| 8 | bottom-right | `(1, -1, 0)` |

Y increases upwards, as everywhere else in Unity. The pattern string reads downwards, so index 0
is `y = +1` — that inversion is the single most common transcription bug when a pattern table is
retyped by hand.

## Two errors in the table as it circulates

The rectangular set is genuinely **47 rules**, and 47 is not a convention — it falls out of the
connection rule. Any subset of the four edges may be required, and a corner may be required only
when both of its adjacent edges already are: 1 + 4 + 8 + 2 + 16 + 16 = 47 distinct neighbour
configurations. Enumerated from that rule and compared cell by cell against the table as it
circulates, two rows are wrong:

- **One pattern is mistyped, and the typo swallows a real configuration.** The row usually named
  for an inverse L pointing up carries `X . X / . * . / . . X`, which is the all-four-edges-plus-SW
  row again, and states its `This` count as 5. Its three siblings each assert three edges
  plus the one corner between two of them, so this row must be N, S, W plus SW:
  `X . X / . * X / . . X`, four neighbours. Copy the typo and a sprite that genuinely analyses to
  N/S/W-plus-SW is rejected as an unknown configuration, the tile comes out one rule short, and
  that edge paints the default sprite — which is exactly what "one of my tiles was ignored" looks
  like from the outside.
- **Three of the stated `This` counts are one too low**: `. . X / . * X / X . X`,
  `X . X / X * . / X . .` and `X . . / X * . / X . X` each require four neighbours, not three.
  Harmless if the count is computed from the pattern; wrong order if a human sorts by the column.

The table below is regenerated from the patterns, so both are already fixed. It is sorted by
`This` count descending, which is also the order the rules must appear in
(`SKILL.md` §6). The last two columns are derived from the pattern — edges are the four
orthogonal cells, corners the four diagonal ones — and they are the fastest way to match a
pattern to a piece of art by eye.

## Fixed rules — 47 distinct configurations

| `This` | Pattern | Required edges | Required corners |
|---:|---|---|---|
| 8 | `. . . / . * . / . . .` | N E S W | NW NE SE SW |
| 7 | `. . . / . * . / . . X` | N E S W | NW NE SW |
| 7 | `. . . / . * . / X . .` | N E S W | NW NE SE |
| 7 | `. . X / . * . / . . .` | N E S W | NW SE SW |
| 7 | `X . . / . * . / . . .` | N E S W | NE SE SW |
| 6 | `. . . / . * . / X . X` | N E S W | NW NE |
| 6 | `. . X / . * . / . . X` | N E S W | NW SW |
| 6 | `. . X / . * . / X . .` | N E S W | NW SE |
| 6 | `X . . / . * . / . . X` | N E S W | NE SW |
| 6 | `X . . / . * . / X . .` | N E S W | NE SE |
| 6 | `X . X / . * . / . . .` | N E S W | SE SW |
| 5 | `. . . / . * . / X X X` | N E W | NW NE |
| 5 | `. . X / . * . / X . X` | N E S W | NW |
| 5 | `. . X / . * X / . . X` | N S W | NW SW |
| 5 | `X . . / . * . / X . X` | N E S W | NE |
| 5 | `X . . / X * . / X . .` | N E S | NE SE |
| 5 | `X . X / . * . / . . X` | N E S W | SW |
| 5 | `X . X / . * . / X . .` | N E S W | SE |
| 5 | `X X X / . * . / . . .` | E S W | SE SW |
| 4 | `. . X / . * . / X X X` | N E W | NW |
| 4 | `. . X / . * X / X . X` | N S W | NW |
| 4 | `X . . / . * . / X X X` | N E W | NE |
| 4 | `X . . / X * . / X . X` | N E S | NE |
| 4 | `X . X / . * . / X . X` | N E S W | — |
| 4 | `X . X / . * X / . . X` | N S W | SW |
| 4 | `X . X / X * . / X . .` | N E S | SE |
| 4 | `X X X / . * . / . . X` | E S W | SW |
| 4 | `X X X / . * . / X . .` | E S W | SE |
| 3 | `. . X / . * X / X X X` | N W | NW |
| 3 | `X . . / X * . / X X X` | N E | NE |
| 3 | `X . X / . * . / X X X` | N E W | — |
| 3 | `X . X / . * X / X . X` | N S W | — |
| 3 | `X . X / X * . / X . X` | N E S | — |
| 3 | `X X X / . * . / X . X` | E S W | — |
| 3 | `X X X / . * X / . . X` | S W | SW |
| 3 | `X X X / X * . / X . .` | E S | SE |
| 2 | `X . X / . * X / X X X` | N W | — |
| 2 | `X . X / X * . / X X X` | N E | — |
| 2 | `X . X / X * X / X . X` | N S | — |
| 2 | `X X X / . * . / X X X` | E W | — |
| 2 | `X X X / . * X / X . X` | S W | — |
| 2 | `X X X / X * . / X . X` | E S | — |
| 1 | `X . X / X * X / X X X` | N | — |
| 1 | `X X X / . * X / X X X` | W | — |
| 1 | `X X X / X * . / X X X` | E | — |
| 1 | `X X X / X * X / X . X` | S | — |
| 0 | `X X X / X * X / X X X` | — | — |


The bottom row is the catch-all: zero assertions, matches anything, and therefore must be last.
Its sprite is also the natural choice for the tile's default sprite.

## Rotated rules — 15 configurations covering the same ground

When the art is symmetric enough to be reused at 90° increments, set `Transform` to `Rotated`
and one rule covers up to four orientations. The set collapses from 47 rules to 15, and 15 sprites
instead of 47:

| `This` | Pattern | Transform | Required edges | Required corners |
|---:|---|---|---|---|
| 8 | `. . . / . * . / . . .` | Fixed | N E S W | NW NE SE SW |
| 7 | `X . . / . * . / . . .` | Rotated | N E S W | NE SE SW |
| 6 | `X . . / . * . / . . X` | Rotated | N E S W | NE SW |
| 6 | `X . X / . * . / . . .` | Rotated | N E S W | SE SW |
| 5 | `X . X / . * . / . . X` | Rotated | N E S W | SW |
| 5 | `X X X / . * . / . . .` | Rotated | E S W | SE SW |
| 4 | `X . X / . * . / X . X` | Fixed | N E S W | — |
| 4 | `X X X / . * . / . . X` | Rotated | E S W | SW |
| 4 | `X X X / . * . / X . .` | Rotated | E S W | SE |
| 3 | `X X X / . * . / X . X` | Rotated | E S W | — |
| 3 | `X X X / X * . / X . .` | Rotated | E S | SE |
| 2 | `X X X / . * . / X X X` | Rotated | E W | — |
| 2 | `X X X / X * . / X . X` | Rotated | E S | — |
| 1 | `X X X / . * X / X X X` | Rotated | W | — |
| 0 | `X X X / X * X / X X X` | Fixed | — | — |

Rotating these 15 patterns through 90° increments regenerates the fixed table exactly — all 47
configurations, no more and no fewer. That
identity is the cheapest audit there is on a retyped fixed table: if the rotations produce a
pattern the table does not hold, the table lost a row. Three rules stay `Fixed` because they are
already rotationally symmetric and marking them `Rotated` would only add duplicate match attempts.

**The trade is art, not code.** A rotated rule reuses one sprite at four orientations, which
shows immediately if the art has directional lighting, a baked drop shadow, or text. Rotate the
sprite in an image viewer and look at it before committing to the 15-rule set.

## Hexagonal

`HexagonalRuleTile` works on six neighbours rather than eight, so none of the tables above
transfer. The directions, for a pointy-top layout:

| Direction | Offset from `(x, y, 0)` |
|---|---|
| North-west | `(-1, 1, 0)` |
| North | `(0, 1, 0)` |
| East | `(1, 0, 0)` |
| West | `(-1, 0, 0)` |
| South-west | `(-1, -1, 0)` |
| South | `(0, -1, 0)` |

**Confirm this list against the installed `com.unity.2d.tilemap.extras` before relying on it.** It
is **not centrally symmetric**: `(-1, 1, 0)` is present while `(1, -1, 0)` is not. That is what
offset hex coordinates look like, where a neighbour's offset depends on the row's parity — but a
transposed pair here produces tiles that connect in one direction only, so check rather than
assume.

A full hexagonal set uses `Fixed` and `MirrorX` transforms; `Rotated` does not apply, because
rotating a hex by 90° does not land on the grid. Enumerate the rules from the installed package
rather than carrying a count over from the rectangular set.

## Isometric

`IsometricRuleTile` keeps the eight-neighbour 3 × 3 neighbourhood — the grid is rectangular in
cell space and only the rendering is skewed — so the fixed and rotated tables above apply
unchanged. What differs is which pattern the art corresponds to: a sprite whose visual top-right
edge is solid sits at cell index 2, not index 1. Match by cell offset, not by how the sprite
looks on screen.
