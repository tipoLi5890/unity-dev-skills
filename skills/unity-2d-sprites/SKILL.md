---
name: unity-2d-sprites
description: >-
  Slice sprite sheets, set pivots and 9-slice from script, and turn frames
  into an AnimationClip.
---

# unity-2d-sprites — the metadata is inside the importer, not in a file

> **Sprite rects, pivots, borders and outlines are not stored anywhere you can edit.** They live
> in importer data reached through `ISpriteEditorDataProvider`. There is no file to patch, and
> **hand-editing the `.meta` corrupts it** — the capability checks in §2 exist precisely because
> the importer's contract is not enforced by the type system.

## Start here — symptom → where to look

| Symptom | Go to |
|---|---|
| No live Editor, or no `eval` | [Getting there](#getting-there) — needs a live Editor (`unity-debug`) |
| Sheet imported as a single sprite | §1 — `spriteImportMode` |
| "Slice this sprite sheet" (grid, automatic, isometric); cut a sheet into frames | §3 |
| Irregular frames, or a grid with padding between cells | §3 — `resources/Editor/AutomaticSliceSheet.cs` |
| "Set the pivot on every frame"; frames right, pivots wrong | §3 pivots |
| "Set up 9-slice on this panel"; a UI panel stretches its corners | §3 borders |
| Slicing "worked" but the names are `sprite_0` | §3 naming |
| Collider shape does not match the art | §4 outlines |
| The script throws about capabilities | §2 — do not bypass it |
| Loading a sprite **by filename** returns null, texture looks fine | §1 — `Multiple` with no rects |
| Editor script will not compile, or cannot see `ISpriteEditorDataProvider`: the types "do not exist" | §0 — the asmdef reference |
| New art in the folder never shows up in the game | §5 — the passes ran in the wrong order |
| Import settings skip files that were already there | §5 — a postprocessor only fires on import |
| A stretched effect sprite stops short of its target | `reference/sprite-geometry.md` §1 |
| "Turn these frames into an animation" (an `AnimationClip`) | §7 — the clip, then the controller |
| The character bobs or jumps between frames; an idle shimmers | §7 — the frames, not pivots |
| The clip plays and nothing moves | §7 — the curve is bound to the wrong `path` |

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

**Grid** (fixed cell; count cells from the texture size), **Automatic** (islands; merges touching
frames, splits detached parts) or **Isometric** (diamond cells), against the real size from
`ITextureDataProvider`. **Pivots** are normalised, set with `SpriteAlignment.Custom` (never `9`):
`(0.5, 0)` for a character's feet. **Borders** are `Vector4(left, bottom, right, top)` in pixels —
9-slice reads them; stretched corners mean a zero border. **Name during the slice** (`sprite_0` is
unusable), update the name↔fileID map on 2021.2+, and **reuse existing rects when re-slicing**.
In `Single` mode add a whole-texture rect named after the file stem. Each rule with its code:
`reference/slicing-and-scripts.md` §3.

## 4. Outlines

The render outline and the collider outline are **two providers, not one setting**, and the
tessellation that suits one wastes the other: a physics outline cut as finely as a render outline
is an expensive `PolygonCollider2D` for no gameplay benefit. Both, the `0`–`1` detail range and the
other providers: `reference/data-provider.md` §1.

## 5. Style rules for generated scripts

Standalone snippets only (no `AssetPostprocessor`, no `MenuItem` for a one-off job; a committed
project postprocessor is fine and **only fires on import**); enums cast, never magic numbers;
verify by reading back through a fresh provider (§6). In a project pipeline the metadata pass
finishes before any generator writes `Sprite` references, and either pass can exit 0 having wired
nothing. The rules, the ordering and which script in `resources/` does what:
`reference/slicing-and-scripts.md` §5.

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
`AnimationClipSettings.loopTime` lands only through `SetAnimationClipSettings`. **A bob or a jump
between frames is fixed in the frames** (`codex-visual`), not in sixteen pivots; every
rect takes ONE pivot, the sidecar's `pivot_norm`. **An idle that boils** plays one frame,
moved in code. **Slice, `Apply()`, `SaveAndReimport()`, then build the clip** (§5), or the curve is
full of nulls. The whole path is `reference/sprite-animation.md`; `resources/Editor/SheetToAnimationClip.cs`
runs it; `resources/Tests/SpriteFramesAudit.cs` re-measures the frames.

## Scope — what this skill does NOT do

**Frame animation is in** — a clip whose keyframes swap one sprite for the next is sprite metadata
one step further on (§7). **Rig animation is out**, and the line is the deformer: a skeleton that
bends the art, blend trees, masked layers, Avatars and root motion belong to
`unity-rigged-character`, the 3D character pipeline. **2D bones, skinning weights, PSB rigs and
Sprite Library** are `unity-2d-animation`.

Also out: 2D physics (`unity-physics-2d`) and generating the
artwork (`codex-visual`, which produces the equal-canvas frames §7 consumes and the previews Unity
will not play). **Sprite atlas packing** and the memory it buys → `unity-sprite-atlas`; **tilemap
authoring** — palettes, Rule Tiles, autotiling from the rects sliced here → `unity-tilemap`;
**pixel-art filtering and camera snapping** → `unity-2d-pixel-perfect`.
