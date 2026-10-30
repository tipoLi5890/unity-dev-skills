# Rule tiles: empty, autotiled, and ordered

Moved out of SKILL.md, which keeps the working contract and §1–§3 (packages, creating a palette, the layout's three numbers); numbering continues it.

## 4. An empty rule tile, when there is no art yet

Three types, one per grid shape: `RuleTile` (rectangular), `HexagonalRuleTile`,
`IsometricRuleTile`. Pick by the grid the tiles will be painted into, not by the shape of the
source sprites.

> **A blank rule still needs its sprite slot.** Give every rule's sprite array exactly one
> `null` entry rather than a zero-length array. A rule with no slot is not "waiting for art" —
> the Inspector has nowhere to drop art into it, so the tile paints nothing at that
> configuration.

Two constants, and the absence of one:

| Value | Meaning | When to use it |
|---|---|---|
| `Neighbor.This` | The neighbouring cell must hold this same rule tile | The normal case — it is what "these tiles connect" means |
| `Neighbor.NotThis` | The neighbouring cell must **not** hold this rule tile | Only when asked for. It is a positive assertion about emptiness, and it makes two rule tiles refuse to sit beside each other |
| *(position absent)* | Don't-care | Not a constant. A cell is don't-care by being left out of the neighbour lists entirely |

Filling the rules by hand is the slow path. Retype the pattern tables — fixed, the 15-rule rotated
set for symmetric art, hexagonal — from `reference/rule-tile-patterns.md`, not from a table you
found: the fixed set is **47** configurations, and the version in circulation mistypes one into a
duplicate of another, costing a real rule, and understates three `This` counts by one.

## 5. Autotile from sprites you already have

The fast path when the art exists: a terrain sprite already says where its edges are — a top-edge
tile is solid along the bottom and empty along the top — so let it declare its rule. Per sprite:

1. **Segment it into a 3 × 3 grid** and take the majority colour of the centre cell.
2. **Score the eight surrounding cells** against that colour. A cell whose matching-pixel share
   meets the threshold is `.`; otherwise `X`.
3. **Emit one line**: `T T T / L * R / B B B`, rows top to bottom, cells left to right, `*` the
   centre. `.` becomes a `This` neighbour, `X` becomes don't-care, `*` is skipped.

Two knobs, and they interact:

| Knob | Values | Effect |
|---|---|---|
| Match threshold | 0.5 / 0.75 / 0.9 | Share of a cell's pixels that must match the centre colour. 0.5 for art with mixed regions, 0.75 as the working default, 0.9 only for flat-colour tiles |
| Colour tolerance | per-channel RGB distance | How close counts as "the same colour". Tight for a limited palette, loose for gradients and dithering |

> **Raise the threshold before you loosen the tolerance.** A loose tolerance makes every cell
> match and every sprite reports the fully-surrounded pattern; that failure looks like "the
> analysis did nothing" rather than like a bad number.

The algorithm, the Y flip and the texture readability requirement:
`reference/sprite-3x3-analysis.md`; code:
[`resources/SpriteGridAnalysis.cs`](../resources/SpriteGridAnalysis.cs).

## 6. Order, dedup, and the sprite that catches everything else

Rules are evaluated top down and **the first match wins**, so the list order is the behaviour.
Four decisions turn a bag of patterns into a rule tile that paints correctly:

- **Discard patterns outside the known set.** A noisy sprite — a decoration, a half-transparent
  overlay, an off-palette variant — becomes a rule that fires on real geometry. Keep only the
  known configurations; bypassing that is an explicit request, never a default.
- **Deduplicate, first sprite wins.** Variants of one edge analyse to the same pattern, and a
  second rule with an identical neighbour set can never fire.
- **Sort by `This` count, descending.** The most constrained rule is tested first: an eight-`This`
  "fully surrounded" rule below a zero-`This` rule never runs, and the tile paints one sprite.
- **The default sprite is the least specific rule's sprite** — after sorting, the last one: what
  paints when nothing matched, so the most generic art in the set, not the first in the folder.

One sprite per rule; multi-sprite output means animation, a different feature.
[`resources/RuleTileFromSprites.cs`](../resources/RuleTileFromSprites.cs) does analysis → filter →
dedup → sort → apply; [`resources/Editor/RuleTileGeneratorWindow.cs`](../resources/Editor/RuleTileGeneratorWindow.cs)
wraps it in an Editor window (`Tools/Unity Dev/Rule Tile from Sprites`).
