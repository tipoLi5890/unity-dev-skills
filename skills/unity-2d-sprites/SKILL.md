---
name: unity-2d-sprites
description: >-
  Edit Unity sprite metadata from script — slice a sheet (grid, automatic,
  isometric), set pivots, 9-slice borders, names and outlines, and turn frames
  into a playable AnimationClip. Load for "slice this sprite sheet", "set the
  pivot on every frame", "set up 9-slice on this panel", "the sheet imported as
  one sprite", "turn these frames into an animation", "the character bobs", a
  sprite loaded by filename returns null, new art never reaches the game,
  import settings skip files already imported, an Editor script cannot see
  ISpriteEditorDataProvider, or a stretched effect sprite stops short. Needs a
  live Editor (unity-debug). Packing is unity-sprite-atlas; tilemaps are
  unity-tilemap.
---

# unity-2d-sprites — the metadata is inside the importer, not in a file

> **Sprite rects, pivots, borders and outlines are not stored anywhere you can edit.** They live
> in importer data reached through `ISpriteEditorDataProvider`. There is no file to patch, and
> **hand-editing the `.meta` corrupts it** — the capability checks in §2 exist precisely because
> the importer's contract is not enforced by the type system.

## 0. The API is in a package, and a 3D project does not have it

> **`ISpriteEditorDataProvider` and everything around it ship in `com.unity.2d.sprite`.** Without
> it the types do not exist and the code **does not compile** — the first thing that happens on a 3D
> project, where the error names a missing assembly reference rather than a missing package.

Check first. Adding it is a project change — `unity-new-project` →
`reference/package-bootstrap.md`, or the Editor's own `package_add` command, which **refuses
without `confirm=true`**:

```bash
unity command eval 'return UnityEditor.PackageManager.PackageInfo.FindForAssetPath(
  "Packages/com.unity.2d.sprite/package.json") != null;'
unity command package_add -- --identifier com.unity.2d.sprite --confirm true
unity command package_status          # poll until "completed"
```

> **The package being present is not enough for code that lives in your own asmdef.** `eval` sees
> these types with nothing declared; an Editor script inside an assembly definition does not until
> **`"Unity.2D.Sprite.Editor"`** is in that asmdef's `references`, and the plain *type or namespace
> not found* sends people to re-add a package that is already there.
> `reference/import-pipeline.md` §1.

## Getting there

This skill needs a **live Editor with `eval`** — `unity-debug` → `reference/editor-control.md`
covers installing `com.unity.pipeline`, confirming the Editor is reachable, and telling a
genuinely absent Editor apart from one wedged in Safe Mode. Two things it cannot know:

- **You need `eval` specifically.** Its presence depends on the Pipeline package version, not
  the CLI version: `unity command --format json --query eval`. Some versions also register
  `eval_file`; **check before reaching for it, it is frequently absent.**
- **An unreachable Editor is a stop, not a cue to improvise.** Every fallback risks corrupting
  importer data.

`eval` compiles a statement block, so `using` directives are rejected (`CS0210`) and every snippet
here is fully qualified; saved as a `.cs` file, add the usings back. `unity command` defaults to a
30-second timeout; a large atlas needs `--timeout`. **The namespaces are not where you would
guess** — `SpriteRect` and `SpriteNameFileIdPair` sit in `UnityEditor`, `GUID` is
`UnityEngine.GUID` — so use the table in `reference/data-provider.md` §1, not reasoning.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Sheet imported as a single sprite | §1 — `spriteImportMode` |
| Need to cut a sheet into frames | §3 |
| Irregular frames, or a grid with padding between cells | §3 — `resources/AutomaticSliceSheet.cs` |
| Frames are right, pivots are wrong | §3 pivots |
| A UI panel stretches its corners | §3 borders |
| Slicing "worked" but the names are `sprite_0` | §3 naming |
| Collider shape does not match the art | §4 outlines |
| The script throws about capabilities | §2 — do not bypass it |
| Loading a sprite **by filename** returns null, texture looks fine | §1 — `Multiple` with no rects |
| Editor script will not compile: the sprite types "do not exist" | §0 — the asmdef reference |
| New art in the folder never shows up in the game | §5 — the passes ran in the wrong order |
| Import settings skip files that were already there | §5 — a postprocessor only fires on import |
| A stretched effect sprite stops short of its target | `reference/sprite-geometry.md` §1 |
| Turn these frames into an animation | §7 — the clip, then the controller |
| The animation plays but the character bobs | §7 — one ground line, not sixteen pivots |
| The clip plays and nothing moves | §7 — the curve is bound to the wrong `path` |

## 1. The importer must be a Sprite, in Multiple mode, first

> **A plain PNG does not import as a sprite at all.** A freshly imported `.png` in a 3D
> project reports `spriteImportMode = None` — not `Single`. Setting `spriteImportMode` alone on
> a texture whose `textureType` is still `Default` does not give you sprite data. Set **both**:

```csharp
var ti = (UnityEditor.TextureImporter)UnityEditor.AssetImporter.GetAtPath(path);
ti.textureType      = UnityEditor.TextureImporterType.Sprite;      // easy to omit; nothing works without it
ti.spriteImportMode = UnityEditor.SpriteImportMode.Multiple;
ti.SaveAndReimport();
```

Re-fetch the importer after `SaveAndReimport()` before asserting on it. Flipping an already-sliced
sheet to `Single` and back to `Multiple` is **non-destructive** — the rects and their names survive
the round trip — so do not panic-rebuild a slice because the mode was toggled.

> **`Multiple` is a promise to slice — a texture left in it with no rects publishes no sprite at
> all.** In `Single` mode the importer publishes one `Sprite` sub-asset **named after the file** —
> the name `Resources.Load`, Addressables and every by-name lookup depend on; an unsliced
> `Multiple` texture publishes none, and lookups return `null` while it looks normal (a test fails
> with `sprite '<filename>' not found`). Never set `Multiple` "to be safe", never *preserve* the
> mode a texture already had: derive it from a rule you can state, and slice in the same run that
> sets it. `reference/import-pipeline.md` §4.

Check `pixelsPerUnit` before computing world units: it is per-asset, and the default is rarely
what a project uses.

## 2. The capability gate — never bypass it

> **The check that fires first is not the capability gate — it is a null data provider.**
> `GetSpriteEditorDataProviderFromObject` returns **`null`** for an asset with no sprite
> data (a `.cs` file, any non-texture), and `InitSpriteEditorDataProvider()` on that is the
> `NullReferenceException` most scripts hit. **Null-check the provider before anything else.**

The capability gate is the *second* check. `TextureImporter` reports **every capability `true`**
— including in `Single` mode — so on a plain PNG the gate never fires. `PSBImporter` and custom
importers are where it does, and **an unsupported edit there is not rejected, it is accepted and
corrupts the data.** Keep the gate: four lines against silent data loss on the one importer
that needed it. Then `SetSpriteRects`, `Apply()` and `SaveAndReimport()` —
nothing persists without the last. The sequence in code, the `EEditCapability` members and which
edit needs which: `reference/data-provider.md` §2.

## 3. Slicing, pivots, borders, names

The three slicing shapes and what actually decides them:

- **Grid** — fixed cell size, optional padding and offset, for a sheet authored on a grid.
  Compute the cell count from the texture size; do not assume 16 columns.
- **Automatic** — islands of non-transparent pixels, for irregular sheets; wrong where adjacent
  frames touch (they merge into one rect) or a frame has a detached element (it splits in two).
- **Isometric** — diamond cells for iso tilesets, where a grid slice cuts through neighbours.

Slice against the real dimensions from `ITextureDataProvider`: the **importer's reported size can
differ from the file's** once max-size and compression apply.

**Pivots** are normalised `(0,0)`–`(1,1)` within each rect. Use the enum and cast it; never the
raw number:

```csharp
r.alignment = UnityEngine.SpriteAlignment.Custom;   // not 9
r.pivot     = new UnityEngine.Vector2(0.5f, 0f);    // bottom-centre: feet on the ground
```

`(0.5, 0)` is the one that matters for characters — a centre pivot sinks a character into the
floor by half its height. The pivot goes wherever the sprite is anchored while it moves; other
anchors and the transparent-margin check are in `reference/sprite-geometry.md`.

**Borders** are `Vector4(left, bottom, right, top)` in pixels, and they are what 9-slice reads.
A UI panel whose corners stretch has a zero border, not a scaling bug.

**Names are the API surface of a sheet.** `Resources.Load`, Addressables and every animation
clip reference sprites by name, so `sprite_0 … sprite_37` is a sheet nobody can use. Name during
the slice, not after.

> **On Unity 2021.2+, adding or removing sprites also requires updating the name↔fileID map**
> (`SetNameFileIdPairs`), or existing references silently rebind to the wrong sprite —
> `reference/data-provider.md` §3.

**Re-slicing is not slicing.** A fresh `SpriteRect` with a fresh `GUID.Generate()` for a name that
already exists throws away the identity everything serialised against — reuse the existing rect and
replace only its `rect`, pivot and border. Where names are not stable the merge is geometric, in one
of three modes: `reference/data-provider.md` §3.

In `Single` mode there may be no rect to write to: for a pivot or a border, add one covering the
whole texture, **named after the file stem** — the asset's API surface (§1).

## 4. Outlines

The render outline and the collider outline are **two providers, not one setting**, and the
tessellation that suits one wastes the other: a physics outline cut as finely as a render outline
is an expensive `PolygonCollider2D` for no gameplay benefit. Both, the `0`–`1` detail range and the
other providers: `reference/data-provider.md` §1.

## 5. Style rules for generated scripts

- **Standalone snippets only.** No `AssetPostprocessor`, no `MenuItem`: a postprocessor keeps
  running against every future import, invisibly. **This rule is about scripts you write to do one
  job once.** A committed, project-owned import postprocessor is a good shape — a human decided it
  should exist forever — and `reference/import-pipeline.md` §2 covers it: it **only fires on
  import**, and it takes `Single` vs `Multiple` from one helper shared with the slicer.
- **Enums cast to their numeric type, never magic numbers.** `(int)SpriteAlignment.Center`, not
  `1`. The numbering is not stable across versions and a raw number is unreadable at review.
- **Verify afterwards** — read the rects back through a fresh provider (§6, and
  `reference/data-provider.md` §2); skip the reimport and the in-memory change evaporates.

**Ordering, when this is a project pipeline rather than one edit:** the metadata pass (reimport →
mode → pivots, borders, slices) finishes before any generator writes `Sprite` references into
ScriptableObjects, prefabs or catalogues — they capture references *at generation time*, so the
other order serialises `null` with no error. Each pass is a separate headless invocation and
**either can exit 0 having wired nothing**: assert on the artifacts, not the exit code.
`reference/import-pipeline.md` §5.

Scripts — adapt rather than rewrite. The slicers `resources/SliceSheet.cs` (grid),
`resources/AutomaticSliceSheet.cs` (islands, or a padded grid) and
`resources/IsometricSliceSheet.cs` run the checks above; `resources/SpriteToPng.cs` (pixels out)
and `resources/SheetToAnimationClip.cs` (§7) open no provider at all. What each adds is in
`reference/data-provider.md` §4.
Run the §6 acceptance test (and the four reads in `reference/sprite-animation.md` §7 for a clip)
before reporting any of them done.
Project-scale pipeline: `reference/import-pipeline.md`; margins, motion-driven pivots, stretched
borders: `reference/sprite-geometry.md`.

## 6. The acceptance test: named sprites, not rects

**Real `Sprite` sub-assets, addressable by name, are the acceptance test.** Rects are not sprites
until `Apply()` + `SaveAndReimport()` succeed, so never report a slice done because
`GetSpriteRects()` returned the right count. Worked example: a 128×64 sheet cut on a 32 px grid
(4×2) reads back through a **fresh** provider as eight rects — `cell_000`…`cell_007`, top-left
reading order (`0,32` … `96,0`), `pivot=(0.5, 0)`, `alignment=Custom` — with eight
`SpriteNameFileIdPair`s persisted, and it passes only when the asset holds eight `Sprite`s:

```csharp
int n = 0;
foreach (var o in UnityEditor.AssetDatabase.LoadAllAssetsAtPath(path))
    if (o is UnityEngine.Sprite) n++;
return n;                                  // must equal the frame count you asked for
```

## 7. Frames into a clip

> **Unity cannot play a GIF.** A preview is a review artifact; the game plays an `AnimationClip`
> with an object-reference curve on `m_Sprite` and an `AnimatorController` whose default state is it.

Four facts decide whether it works: **`m_Sprite`** on both `SpriteRenderer` and
`UnityEngine.UI.Image`; `binding.path` relative to the `Animator`'s GameObject (wrong, and the clip
plays while nothing moves); a new clip's **`frameRate = 60`**, so set it;
`AnimationClipSettings.loopTime` lands only through `SetAnimationClipSettings`. **A bob is a pivot
problem, and it is fixed in the frames.** Register them to one ground line, then give every rect one
bottom-centre pivot. **Slice, `Apply()`, `SaveAndReimport()`, then build the clip** (§5), or the
curve is full of nulls. The whole path — `frames.json`, `length == N / fps`, one-shots, the
controller, UI `Image`, the acceptance reads — is `reference/sprite-animation.md`;
`resources/SheetToAnimationClip.cs` runs it.

## Scope — what this skill does NOT do

**Frame animation is in** — a clip whose keyframes swap one sprite for the next is sprite metadata
one step further on (§7). **Rig animation is out**, and the line is the deformer: a skeleton that
bends the art, blend trees, masked layers, Avatars and root motion belong to
`unity-rigged-character`, the 3D character pipeline. **2D bones stay out of the family
altogether** — bone hierarchies and skinning weights over a sprite live in `com.unity.2d.animation`
(a dependency of `com.unity.feature.2d`), which nobody here covers.
Say so; the sprite-metadata API cannot reach any of it.

Also out: 2D physics behaviour (`unity-physics-3d` covers 3D and says so) and generating the
artwork (`codex-visual`, which produces the equal-canvas frames §7 consumes and the previews Unity
will not play). **Sprite atlas packing** and the memory it buys → `unity-sprite-atlas`; **tilemap
authoring** — palettes, Rule Tiles, autotiling from the rects sliced here → `unity-tilemap`;
**pixel-art filtering and camera snapping** → `unity-2d-pixel-perfect`.
