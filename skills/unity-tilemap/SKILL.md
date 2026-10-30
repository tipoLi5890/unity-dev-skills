---
name: unity-tilemap
description: >-
  Tile Palettes for rect, hex and iso grids, rule tiles, autotiling from a terrain sheet.
---

# unity-tilemap — two packages, and only one of them is already there

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Editor script will not compile: `RuleTile` "does not exist" | §1 — the second package |
| "Make me a Tile Palette" from a script | §2 |
| Palette exists but the Tile Palette window shows no cell sizing | §2 — the `GridPalette` sub-asset |
| Hex or isometric palette came out the wrong shape or cell proportions | §3 |
| Isometric tiles draw in front of tiles that are behind them | §3 — the sort axis |
| Want a blank rule tile to fill in by hand | [`reference/rule-tiles-and-autotile.md`](reference/rule-tiles-and-autotile.md) §4 |
| A rule shows an empty sprite slot and paints nothing | [`reference/rule-tiles-and-autotile.md`](reference/rule-tiles-and-autotile.md) §4 — the one `null` entry |
| "These tiles should connect as I paint them" — and they do not | [`reference/rule-tiles-and-autotile.md`](reference/rule-tiles-and-autotile.md) §5, then §6 — rule order |
| "Make these edge sprites auto-tile"; build a RuleTile from this terrain sheet | [`reference/rule-tiles-and-autotile.md`](reference/rule-tiles-and-autotile.md) §5 |
| A specific rule never fires although its pattern is present | [`reference/rule-tiles-and-autotile.md`](reference/rule-tiles-and-autotile.md) §6 — a less specific rule is above it |
| Gaps between painted tiles you did not author | Scope — `unity-2d-pixel-perfect` |
| Full pattern tables, neighbour coordinates | `reference/rule-tile-patterns.md` |
| A hexagonal set to start from, and why it is unverified | `reference/hexagonal-rule-set.md` |
| Cell sizing, swizzle and sort-mode values | `reference/palette-and-grid.md` |
| How a sprite becomes a pattern string | `reference/sprite-3x3-analysis.md` |

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
[`resources/Editor/CreatePaletteTemplate.cs`](resources/Editor/CreatePaletteTemplate.cs).

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

## 4–6. Rule tiles → `reference/rule-tiles-and-autotile.md`

§4 an empty rule tile to fill by hand when there is no art yet; §5 autotiling generated from
terrain sprites you already have; §6 rule order, dedup and the catch-all sprite. Same numbering
there.

## Scope — what this skill does NOT do

Cutting the tileset sheet into sprites in the first place — rects, pivots, names, 9-slice
borders — is `unity-2d-sprites`. This skill starts from sprites that already exist as sub-assets
of a texture.

Hairline gaps and bleeding between painted tiles, filtering, and camera-side blur are
`unity-2d-pixel-perfect`: they come from the sampler and the camera, not from the palette, and
no cell size fixes them. Packing the tiles into an atlas, and what that does to their edges, is
`unity-sprite-atlas`.

Assembling levels from data, layer stacks, runtime `SetTile`, rooms and external editors are
`unity-2d-level`. Cell coordinates, hexagonal and isometric maths and pathfinding are
`unity-2d-grid`. `TilemapCollider2D` and composites are `unity-physics-2d` — this skill only sets
a tile's collider type. Sorting and the scene-level sort axis are `unity-2d-rendering`.

## Reference

- [`reference/rule-tiles-and-autotile.md`](reference/rule-tiles-and-autotile.md) — §4–§6: empty, autotiled and ordered rule tiles.
- [`reference/palette-and-grid.md`](reference/palette-and-grid.md) — `CreateNewPalette` arguments,
  layouts, enums, verifying a palette.
- [`reference/rule-tile-patterns.md`](reference/rule-tile-patterns.md) — fixed and rotated tables,
  the cell-index-to-`Vector3Int` map, hexagonal directions.
- [`reference/hexagonal-rule-set.md`](reference/hexagonal-rule-set.md) — 38 pointy-top
  configurations with their transforms, marked unverified and how to confirm them.
- [`reference/sprite-3x3-analysis.md`](reference/sprite-3x3-analysis.md) — sprite to pattern, the
  Y flip, the two knobs, a bad run.
- Code: [`CreatePaletteTemplate.cs`](resources/Editor/CreatePaletteTemplate.cs) (four layouts, read-back
  check), [`SpriteGridAnalysis.cs`](resources/SpriteGridAnalysis.cs),
  [`RuleTileFromSprites.cs`](resources/RuleTileFromSprites.cs),
  [`RuleTileGeneratorWindow.cs`](resources/Editor/RuleTileGeneratorWindow.cs) (survey-then-generate).
