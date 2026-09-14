# A hexagonal rule set — 38 configurations, unverified

> Part of the `unity-tilemap` skill. `reference/rule-tile-patterns.md` holds the rectangular
> tables, the symbols and the six hexagonal neighbour offsets; this file holds one full
> pointy-top set for `HexagonalRuleTile`, kept separate because its status is different from
> everything beside it.

> **Treat every row here as a starting draft, not as a table to retype.** The rectangular
> 47-rule table that circulates has two genuine errors in it — a mistyped pattern that swallows a
> real configuration, and three understated `This` counts — which is what
> `reference/rule-tile-patterns.md` exists to correct. Nothing equivalent has been done for this
> set. **Confirm it against the installed `com.unity.2d.tilemap.extras`** before a project depends
> on it: enumerate `HexagonalRuleTile`'s `TilingRule` members and its `Transform` enum on your
> version, paint a patch of every configuration, and look for a cell that paints the default
> sprite — that is what a missing or duplicated row looks like from the outside.

## Reading the table

Six neighbours, not eight. A row lists only the cells that must hold this same tile
(`Neighbor.This`); every cell it does not list is don't-care, which is a position left out of the
neighbour lists rather than a constant (`SKILL.md` §4). The offsets each name maps to are in
`reference/rule-tile-patterns.md` §Hexagonal — and that list is **not centrally symmetric**, so a
transposed pair produces tiles that connect one way only.

`Transform` is `Fixed` or `MirrorX`. A `MirrorX` rule is also tried with its neighbour set
mirrored, and its sprite drawn mirrored to match, so one sprite covers a left-hand and a
right-hand case. Mirroring is about the vertical axis, which on these six offsets swaps `E` with
`W`, `N` with `NW` and `S` with `SW` — that pairing is how to check a row's transform by hand, and
confirming the axis on your version is part of confirming the table. Two consequences: **art with directional lighting, a baked shadow or text cannot
be mirrored** — check the sprite mirrored in an image viewer before committing — and a rule whose
neighbour set is already mirror-symmetric gains nothing from `MirrorX` except a second match
attempt. `Rotated` has no place here: rotating a hex by 90° does not land on the grid.

**Order is behaviour.** Rules are evaluated top down and the first match wins, so keep the table's
order — most neighbours first, the empty configuration last — exactly as it stands, and give the
last row the tile's default sprite (`SKILL.md` §6).

## The set

| # | `This` | Neighbours required | Transform |
|---:|---:|---|---|
| 1 | 6 | NW N E W SW S | Fixed |
| 2 | 5 | NW E W SW S | MirrorX |
| 3 | 5 | NW N E W SW | MirrorX |
| 4 | 5 | NW N W SW S | MirrorX |
| 5 | 4 | E W SW S | Fixed |
| 6 | 4 | NW N E W | Fixed |
| 7 | 4 | NW N W SW | MirrorX |
| 8 | 4 | NW N W S | MirrorX |
| 9 | 4 | NW N SW S | Fixed |
| 10 | 4 | NW W SW S | MirrorX |
| 11 | 4 | NW E W SW | MirrorX |
| 12 | 4 | NW E W S | MirrorX |
| 13 | 4 | NW E SW S | MirrorX |
| 14 | 3 | NW N W | MirrorX |
| 15 | 3 | NW N S | MirrorX |
| 16 | 3 | NW W SW | MirrorX |
| 17 | 3 | NW W E | MirrorX |
| 18 | 3 | NW W S | MirrorX |
| 19 | 3 | NW SW S | MirrorX |
| 20 | 3 | NW E SW | MirrorX |
| 21 | 3 | N W SW | MirrorX |
| 22 | 3 | E W SW | MirrorX |
| 23 | 3 | W SW S | MirrorX |
| 24 | 2 | NW N | Fixed |
| 25 | 2 | NW W | Fixed |
| 26 | 2 | NW E | MirrorX |
| 27 | 2 | N E | Fixed |
| 28 | 2 | N SW | MirrorX |
| 29 | 2 | N S | MirrorX |
| 30 | 2 | E W | Fixed |
| 31 | 2 | E S | Fixed |
| 32 | 2 | W SW | Fixed |
| 33 | 2 | W S | MirrorX |
| 34 | 2 | SW S | Fixed |
| 35 | 1 | N | MirrorX |
| 36 | 1 | E | MirrorX |
| 37 | 1 | S | MirrorX |
| 38 | 0 | — | Fixed |

Row 38 asserts nothing, matches anything, and therefore must stay last; its sprite is also the
natural choice for the tile's default sprite.

## What the count does and does not tell you

Thirty-eight is the size of **this** set, not a number that falls out of the six-neighbour
geometry the way 47 falls out of the rectangular connection rule. Some rows are here because a
piece of art usually exists for them, not because the configuration is forced. So:

- A sheet that analyses to fewer distinct configurations is not missing rules — it is art with
  fewer cases, and adding empty rules to reach 38 gives you sprite slots nobody fills.
- A configuration this table does not list is not illegal. Add the row where the art calls for it,
  at the right place in the order rather than at the end.
- Count the rules on the asset after generating one and say the number in the report. A rule tile
  that was written with 38 rules and reads back with 37 lost one to a duplicate neighbour set, and
  a duplicate can never fire.

Generating the rules from art rather than retyping them is `SKILL.md` §5 — the 3 × 3 analysis in
`reference/sprite-3x3-analysis.md` is rectangular, so a hexagonal sheet needs the neighbour
sampling adjusted to these six directions before it says anything true.
