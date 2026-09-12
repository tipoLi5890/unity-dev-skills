---
name: unity-tilemap
description: >-
  Script Unity's 2D tilemap layer — Tile Palette assets for rectangular,
  hexagonal and isometric grids, empty rule tiles to fill in by hand, and
  autotiling generated from terrain sprites you already have. Load for "make me a
  Tile Palette", a palette that came out the wrong shape or sorts back to front,
  "these tiles should connect as I paint them", "build a RuleTile from this
  terrain sheet", a RuleTile whose rules fire in the wrong order or whose blank
  cells show nothing, or an Editor script that will not compile because RuleTile
  "does not exist". Creating palettes and tiles writes assets into the project, so
  this skill reports what it would create and waits for confirmation.
---

# unity-tilemap — two packages, and only one of them is already there

> **The grid half ships inside the Editor; the rule half does not.** `Tilemap`, `TileBase`,
> `Tile.ColliderType` and the palette utility all come from `com.unity.2d.tilemap`, which is
> **built into the Editor install**, even where the manifest names it. Every rule tile type comes
> from a second package, `com.unity.2d.tilemap.extras`; without it `RuleTile`,
> `UnityEngine.Tilemaps.RuleTile`, `HexagonalRuleTile` and `IsometricRuleTile` resolve to
> **nothing** across every loaded assembly. That is a compile error in an Editor script, not a null
> at runtime — and it is the first thing to check when "autotiling does not work".

## The working contract

> **Report, then wait.** A palette is a prefab plus a sub-asset; a rule tile is a
> `ScriptableObject` with a list nobody wants to re-author by hand. Both land in the project and
> in the diff. Say what you would create, where, and with which cell size and
> layout — then wait for confirmation before writing anything.

- Everything below needs a **live Editor** with `eval` (`unity-debug` →
  `reference/editor-control.md`), or an Editor script compiled into the project. `eval` compiles a
  statement block, so snippets here are fully qualified, with no `using` directives.
- **Read the result back from the asset, not from the return value.** `CreateNewPalette` returns
  the palette `GameObject`; whether the `GridPalette` sub-asset carrying the cell sizing was
  written alongside it is a separate question (§2).
- One palette per grid layout. The layout is baked into the prefab's `Grid` component — a
  rectangular palette does not become hexagonal by editing the tilemap it paints into.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Editor script will not compile: `RuleTile` "does not exist" | §1 — the second package |
| Need a Tile Palette from a script | §2 |
| Palette exists but the Tile Palette window shows no cell sizing | §2 — the `GridPalette` sub-asset |
| Hex or isometric palette has the wrong cell proportions | §3 |
| Isometric tiles draw in front of tiles that are behind them | §3 — the sort axis |
| Want a blank rule tile to fill in by hand | §4 |
| A rule shows an empty sprite slot and paints nothing | §4 — the one `null` entry |
| Painted tiles do not connect to each other | §5, then §6 — rule order |
| "Make these edge sprites auto-tile" | §5 |
| A specific rule never fires although its pattern is present | §6 — a less specific rule is above it |
| Gaps between painted tiles you did not author | Scope — `unity-2d-pixel-perfect` |
| Full pattern tables, neighbour coordinates | `reference/rule-tile-patterns.md` |
| Cell sizing, swizzle and sort-mode values | `reference/palette-and-grid.md` |
| How a sprite becomes a pattern string | `reference/sprite-3x3-analysis.md` |

## 1. Which package you are missing

| What you are reaching for | Package | State on a project that did not ask for it |
|---|---|---|
| `Tilemap`, `TileBase`, `Tile`, `Grid`, the palette utility | `com.unity.2d.tilemap` | Present. Reports `version 1.0.0, source = BuiltIn` — it lives in the Editor installation, and the package registry returns **404** for that id |
| `RuleTile`, `HexagonalRuleTile`, `IsometricRuleTile`, `RuleOverrideTile`, animated and weighted tiles | `com.unity.2d.tilemap.extras` | **Absent** until added; then read the version that resolved off `Packages/packages-lock.json` |

Check before writing any code that names a rule tile:

```bash
unity command eval 'var p = UnityEditor.PackageManager.PackageInfo.FindForAssetPath(
  "Packages/com.unity.2d.tilemap.extras/package.json"); return p == null ? "absent" : p.version;'
```

Adding it is a project change — `unity-new-project` → `reference/package-bootstrap.md`, or the
Editor's own `package_add`, which refuses without `confirm=true`. A rule tile type was never in the
built-in package, and the "missing assembly reference" wording sends people to the wrong manifest
line.

**The base types are where you would guess; the palette types are not.** `GridPalette` is
**`UnityEditor.GridPalette`** — not under `UnityEditor.Tilemaps` — so `using UnityEditor.Tilemaps;`
reaches the utility but not the `GridPalette.CellSizing` argument it demands, which costs an hour.
Two `using` lines, or fully qualify; every type's namespace and assembly is in
`reference/palette-and-grid.md`.

## 2. Creating a palette — one call, and it has two overloads

`GridPaletteUtility.CreateNewPalette` builds the palette prefab, its `Grid` component and its
sizing sub-asset in a single call, and it exists twice: six arguments (`folderPath`, `name`,
`layout`, `cellSizing`, `cellSize`, `swizzle`), and eight, adding `sortMode` and `sortAxis`. Both
signatures: [`reference/palette-and-grid.md`](reference/palette-and-grid.md).

> **The six-argument overload cannot express an isometric sort axis.** Sorting is the last two
> arguments only, so default to the eight-argument form: it degrades to the short one with
> `TransparencySortMode.Default` and any axis; the reverse is not available.

Pass the folder yourself: `CreateNewPaletteAtCurrentFolder` (five and seven arguments) reads it from
the Project window's selection, which a headless script does not want. `folderPath` is
project-relative (`Assets/Palettes`) and **must already exist** — creating a palette does not create
its directory.

**The sub-asset is the acceptance test.** `GridPalette` is a `ScriptableObject` carrying a single
public field, `cellSizing`, stored inside the palette asset; without it the Tile Palette window has
no sizing to show. Read the asset back, not the returned `GameObject`, and expect exactly one
`GridPalette` — the check, which also reads the `Grid` back, is in `reference/palette-and-grid.md`.
Run it the first time you create a palette in a project. Runnable code for all four layouts:
[`resources/CreatePaletteTemplate.cs`](resources/CreatePaletteTemplate.cs).

## 3. The layout decides three numbers

Four layouts exist and no more — `CellLayout` enumerates to exactly
`Rectangle, Hexagon, Isometric, IsometricZAsY`, and `CellSizing` to exactly `Automatic, Manual`.

| Layout | Cell sizing | Cell size | Sort mode / axis |
|---|---|---|---|
| `Rectangle` | `Automatic` | `(1, 1, 0)` | `Default` |
| `Hexagon` | `Manual` | `(0.8659766, 1, 1)` | `Default` |
| `Isometric` | `Manual` | `(1, 0.5, 1)` | `CustomAxis`, `(0, 0, 1)` |
| `IsometricZAsY` | `Manual` | `(1, 0.5, 1)` | `CustomAxis`, `(0, 0, 1)` |

- **`Automatic` ignores the cell size you pass** and takes it from the first sprite dropped into
  the palette — right only for a rectangular grid from a uniformly sliced sheet.
- The hexagonal width in circulation, `0.8659766`, sits 4.9 × 10⁻⁵ below √3⁄2 (`0.8660254`) —
  about two thousandths of a texel at 32 px per unit — so match what the project already uses.
- **Both isometric layouts need `CustomAxis` with `(0, 0, 1)`.** At `Default`, tiles further back
  draw over tiles in front. `IsometricZAsY` also lets a tile's Z push it along Y, faking height;
  the sort axis is the same.

Cell swizzle stays `XYZ` unless the project paints on a different plane. Every enum member, and
why each number is what it is: `reference/palette-and-grid.md`.

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
[`resources/SpriteGridAnalysis.cs`](resources/SpriteGridAnalysis.cs).

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
[`resources/RuleTileFromSprites.cs`](resources/RuleTileFromSprites.cs) does analysis → filter →
dedup → sort → apply; [`resources/RuleTileGeneratorWindow.cs`](resources/RuleTileGeneratorWindow.cs)
wraps it in an Editor window (`Tools/Unity Dev/Rule Tile from Sprites`).

## Scope — what this skill does NOT do

Cutting the tileset sheet into sprites in the first place — rects, pivots, names, 9-slice
borders — is `unity-2d-sprites`. This skill starts from sprites that already exist as sub-assets
of a texture.

Hairline gaps and bleeding between painted tiles, filtering, and camera-side blur are
`unity-2d-pixel-perfect`: they come from the sampler and the camera, not from the palette, and
no cell size fixes them. Packing the tiles into an atlas, and what that does to their edges, is
`unity-sprite-atlas`.

Level design itself — where the tiles go — is not a scripting problem. Neither is 2D physics on
a `TilemapCollider2D`: this skill only sets a tile's collider type and stops there.

## Reference

- [`reference/palette-and-grid.md`](reference/palette-and-grid.md) — `CreateNewPalette` arguments,
  layouts, enums, verifying a palette.
- [`reference/rule-tile-patterns.md`](reference/rule-tile-patterns.md) — fixed and rotated tables,
  the cell-index-to-`Vector3Int` map, hexagonal directions.
- [`reference/sprite-3x3-analysis.md`](reference/sprite-3x3-analysis.md) — sprite to pattern, the
  Y flip, the two knobs, a bad run.
- Code: [`CreatePaletteTemplate.cs`](resources/CreatePaletteTemplate.cs) (four layouts, read-back
  check), [`SpriteGridAnalysis.cs`](resources/SpriteGridAnalysis.cs),
  [`RuleTileFromSprites.cs`](resources/RuleTileFromSprites.cs),
  [`RuleTileGeneratorWindow.cs`](resources/RuleTileGeneratorWindow.cs) (survey-then-generate).
