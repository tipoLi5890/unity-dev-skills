---
name: unity-sprite-atlas
description: >-
  Author, configure and ship Unity Sprite Atlases from script — the V2 editor
  and runtime split, packing and platform settings, build-time generation, and
  delivery. Load for: sprites that should share a draw call, an atlas asset
  that never produces a texture, "sprite atlas packing is disabled", shipping
  atlases in the player versus loading them through Addressables, a
  half-resolution variant, an Editor script that will not compile against
  SpriteAtlas or a cast on a platform format, atlases that go stale unless
  somebody clicks a menu item, or a layout the built-in packer will not
  produce. Atlas work rewrites assets and forces reimports, so this skill
  reports before it changes anything.
---

# unity-sprite-atlas — an atlas can look finished and pack nothing

> **`SpritePackerMode.Disabled` is the zero value of the enum.** So a project where nobody ever
> opened that setting has packing off, and an atlas authored there saves, imports, appears in the
> Project window and lists its sprites — while producing no packed texture at all. Nothing in the
> workflow errors. Everything else in this skill is wasted effort until
> `EditorSettings.spritePackerMode` is set **and read back**.

> **Report, then wait.** Generating atlases writes new assets, rewrites importer settings and
> forces reimports across the art folder. Survey what exists, state which atlases you would create
> or reconfigure and with what values, and wait for confirmation before applying. Connecting to a
> live Editor: `unity-debug` → `reference/editor-control.md`.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Atlas asset exists, no texture is ever produced, sprites still load one by one | §1 |
| The Inspector says atlas packing is disabled | §1 |
| Editor script will not compile: `SpriteAtlas` has no `Add`, `GetPackables`, `SetTextureSettings` | §2 |
| `new SpriteAtlas()` rejected, or a loaded `SpriteAtlas` will not take settings | §2 |
| Importer settings assigned and nothing changed on disk | §3 — the struct copy, then `SaveAndReimport()` |
| `format = (int)TextureImporterFormat.…` does not compile | §3, `reference/common-errors.md` |
| A mobile format was assigned and the platform will not take it (PVRTC) | §3, `reference/common-errors.md` |
| `PackAtlases` rejects the array you hand it | `reference/common-errors.md` |
| An atlas search picks up assets from `Packages/` | `reference/common-errors.md` |
| Atlases go stale unless somebody remembers to click a menu item | §4 |
| The atlas shipped inside the player and you wanted it downloadable | §5 |
| `GetSprite` returns null on an atlas the game loaded itself | §5 — the callback registered too late |
| `SetMasterAtlasPath` does not exist | §6 |
| A lower-resolution build needs half-size art from the same sources | §6 |
| The packer will not produce the layout the tooling downstream expects | §7 |

## 1. Turn packing on, then prove it took

The full enum:

```
Disabled, BuildTimeOnly, AlwaysOn, BuildTimeOnlyAtlas, AlwaysOnAtlas,
SpriteAtlasV2, SpriteAtlasV2Build
```

`Disabled` is `0`; the four values after it belong to the V1 packer. New work uses one of the two V2
values: write `SpriteAtlasV2` unless the project has a stated reason to defer packing to build.

Read it before writing it. Assigning this property rewrites the tracked file
`ProjectSettings/EditorSettings.asset`, so a survey pass only reads:

```csharp
return UnityEditor.EditorSettings.spritePackerMode.ToString();   // survey: read only
```

```csharp
var before = UnityEditor.EditorSettings.spritePackerMode;        // fix: only if it is not V2 yet
if (before != UnityEditor.SpritePackerMode.SpriteAtlasV2 &&
    before != UnityEditor.SpritePackerMode.SpriteAtlasV2Build)
    UnityEditor.EditorSettings.spritePackerMode = UnityEditor.SpritePackerMode.SpriteAtlasV2;
return $"{before} -> {UnityEditor.EditorSettings.spritePackerMode}";
```

> **A write you did not read back proves nothing.** Report both values — the one that was there and
> the one that came back — not the value you assigned. If the read fails, say the mode is unknown
> rather than assuming the write landed — the failure this section exists for is a silent no-op.

A project may already carry `SpriteAtlasV2` (integer `5`) — you cannot tell a configured project
from an unconfigured one without looking, and the unconfigured one quietly breaks.

Do not hand-edit `ProjectSettings/EditorSettings.asset` or an atlas `.meta`: the setting is one
property assignment away, and the file format is not a contract.

## 2. Editor and runtime are two disjoint APIs

V2 splits atlas authoring from atlas use across the Editor/runtime boundary, enforced by which type
carries which member — not by an error message that explains itself. Both halves ship in the Editor
install (`UnityEditor.CoreModule` and `UnityEngine.CoreModule`): there is no package to add.

| Job | Type | Namespace | Instance surface |
|---|---|---|---|
| Author content | `SpriteAtlasAsset` | `UnityEditor.U2D` | `Add`, `Remove`, `SetIsVariant`, `isVariant`, `SetMasterAtlas`, `GetMasterAtlas`, `SetScriptablePacker`, plus static `Save` / `Load` |
| Configure it | `SpriteAtlasImporter` | `UnityEditor.U2D` | `variantScale`, `includeInBuild`, `packingSettings`, `textureSettings`, `GetPlatformSettings`, `SetPlatformSettings` (an `AssetImporter`, so `SaveAndReimport()` too) |
| Preview packing | `SpriteAtlasUtility` | `UnityEditor.U2D` | `PackAllAtlases`, `PackAtlases`, `CleanupAtlasPacking` |
| Read packed sprites | `SpriteAtlas` | `UnityEngine.U2D` | `spriteCount`, `tag`, `isVariant`, `GetSprite`, `GetSprites`, `CanBindTo` — **that is all of it** |
| Supply an atlas on demand | `SpriteAtlasManager` | `UnityEngine.U2D` | `atlasRequested`, `atlasRegistered`, `CreateSpriteAtlas` |

Four members people reach for on `SpriteAtlasAsset` are **absent**:
`RemoveAt`, `GetPacker`, `GetPackables`, `SetMasterAtlasPath`. Of the seventeen methods it does
declare, **nine carry `[Obsolete]`** — the whole settings surface, which moved to the importer — and
six of those messages name importer methods that do not exist; use the importer's four properties.
Both enumerations and the mapping: `reference/v2-api.md`.

> **`GetPackables()` is not a method on `SpriteAtlas`.** It is an extension method in
> `UnityEditor.U2D.SpriteAtlasExtensions`, so `atlas.GetPackables()` compiles in Editor code with
> `using UnityEditor.U2D;` and nowhere else. Its fourteen siblings there are the V1
> authoring path — they compile, and they do not build a V2 atlas. Full list: `reference/v2-api.md`.

## 3. Create, save, import, configure, reimport

The order is load-bearing: the asset has to exist on disk and be imported before an importer
exists to configure, so authoring and configuration are two passes.

```csharp
var asset = new UnityEditor.U2D.SpriteAtlasAsset();
asset.Add(sprites);                                              // UnityEngine.Object[]
UnityEditor.U2D.SpriteAtlasAsset.Save(asset, path);
UnityEditor.AssetDatabase.ImportAsset(path);                     // now an importer exists

var importer = UnityEditor.AssetImporter.GetAtPath(path) as UnityEditor.U2D.SpriteAtlasImporter;
if (importer == null) throw new System.Exception($"no SpriteAtlasImporter at {path}");

var tex = importer.textureSettings;      // struct copy — edit the local
tex.filterMode      = UnityEngine.FilterMode.Bilinear;
tex.generateMipMaps = false;
importer.textureSettings = tex;          // …and assign it back, or nothing happened

var pack = importer.packingSettings;
pack.padding             = 4;
pack.enableAlphaDilation = true;
importer.packingSettings = pack;

importer.includeInBuild = true;
importer.SaveAndReimport();              // nothing persists without this
```

- **`textureSettings` and `packingSettings` are struct properties** — take a local, edit it,
  assign it back, as above. Members, with `maxTextureSize` read-only: `reference/v2-api.md`.
- **`TextureImporterPlatformSettings.format` is a property typed `TextureImporterFormat`**, not
  an `int` field — delete the cast, never widen it: `reference/common-errors.md` §1.
- **Pack only sprites under `Assets/`** — package and built-in textures are read-only imports
  nothing downstream can reimport, so filter on the path: `reference/common-errors.md` §5.
- **The file extension is `.spriteatlasv2`**, per the package documentation — confirm it on the
  first asset you create.

## 4. Generate on build, not from a menu

An atlas whose contents are decided by a folder or a naming rule should be regenerated by the
build, through `IPreprocessBuildWithReport`. A `[MenuItem]` generator is one extra way to ship a
stale atlas: it is correct exactly until somebody adds art and builds without clicking.

`resources/AtlasBuildGenerator.cs` is the runnable shape: it corrects the packer mode only when it
is not already a V2 value, rebuilds one atlas per rule, configures the importer, and optionally
registers the results with Addressables — adapt its rules, not its scaffolding. The one build that
writes the mode rewrites the tracked `ProjectSettings/EditorSettings.asset`; commit the new value
rather than reverting it.

Reserve a menu entry for a human choosing the layout — a hand-tuned arrangement, or an
Editor preview while authoring — under `Tools/Unity Dev/…`, clear of a project's own menus.
`SpriteAtlasUtility.PackAtlases` and `PackAllAtlases` pack for preview: wrap either in
`try/finally` and call `CleanupAtlasPacking()` in the `finally`, so a cancelled or thrown pack does
not leave temporary state behind.

## 5. Delivery: inside the player, or late-bound

One importer flag decides this; the rest follows from it.

| Content | `includeInBuild` | What else is needed |
|---|---|---|
| Core UI, the first scene, anything always on screen | `true` | Nothing |
| Level packs, cosmetics, per-locale art, seasonal content | `false` | Addressables entries, a content build, and a runtime supplier |

Setting `includeInBuild = false` without the other three pieces — a prebuild step creating the
Addressables entries, a postprocess step building the content, and a runtime component answering
`SpriteAtlasManager.atlasRequested` — produces a build whose sprites resolve to nothing: the atlas
is excluded exactly as asked and nobody delivers it. Setup and the Addressables API surface:
`reference/addressables-delivery.md`.

> **The supplier has to be listening before the first sprite resolves.** `atlasRequested` fires
> once per tag, so a component that subscribes in `Start`, or lives in the second scene, leaves the
> first scene's sprites blank for the session. Subscribe in `Awake` on an object that survives the
> load, and unsubscribe in `OnDestroy`.

## 6. Variants

A variant is a second atlas reusing a master's packables at another scale — usually a
reduced-resolution build from the same source art.

```csharp
var master = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.U2D.SpriteAtlas>(masterPath);
var variant = new UnityEditor.U2D.SpriteAtlasAsset();
variant.SetIsVariant(true);
variant.Add(UnityEditor.U2D.SpriteAtlasExtensions.GetPackables(master));  // §2's extension
variant.SetMasterAtlas(master);           // takes the runtime SpriteAtlas
UnityEditor.U2D.SpriteAtlasAsset.Save(variant, variantPath);
UnityEditor.AssetDatabase.ImportAsset(variantPath);

var importer = UnityEditor.AssetImporter.GetAtPath(variantPath)
             as UnityEditor.U2D.SpriteAtlasImporter;
importer.variantScale   = 0.5f;           // on the importer, not the asset
importer.includeInBuild = true;
importer.SaveAndReimport();
```

Two signatures decide whether this compiles: `SetMasterAtlas` takes a
**`UnityEngine.U2D.SpriteAtlas`**, so a path string or a `SpriteAtlasAsset` is rejected; and there
is **no `SetMasterAtlasPath`** to fall back on. Scale lives on the importer because
`SpriteAtlasAsset.SetVariantScale` is one of the nine methods carrying `[Obsolete]`.

Add the master's packables, not sprites you collected earlier: a variant listing a different set
from its master is not a variant of it, and the mismatch shows up as missing sprites, not an error.

## 7. Custom packing

`ScriptablePacker` is a `ScriptableObject` with one abstract member, `Pack` (**public**), and one
virtual member, `Fit` (**protected** — an override cannot widen access, so `public override bool
Fit` will not compile). Attach an instance with `SpriteAtlasAsset.SetScriptablePacker`, which takes
a `ScriptablePacker`, not a plain `Object`.

Its input and output types are **nested inside `ScriptablePacker`** — `PackerData`, `SpriteData`,
`SpritePack`, `TextureData` and `PackTransform` are all `ScriptablePacker.<Name>`, not free types
in `UnityEditor.U2D`; a mis-qualified reference is the usual reason a packer will not compile.
Field lists, two of them easy to get wrong from memory: `reference/v2-api.md`.

Write to `sprite.output` and write the struct back into the array — `NativeArray<T>` hands out
copies. Never dispose the arrays inside `PackerData`; the importer owns them.

> **`Pack` returning `true` is the only report anyone downstream gets**, so check the output before
> returning it: `resources/PackerValidation.cs` rejects a negative position, an unopened page and
> an overlap, and says what landed on each page.

Three layouts: `resources/ScriptablePackerExample.cs` (a fixed grid),
`resources/MultiPagePacker.cs` (shelves, spilling onto a new page) and
`resources/SizeOptimizedPacker.cs` (one page, tallest first). Padding is yours to apply — whatever
`Pack` writes is the final position.

## Scope — what this skill does NOT do

Slicing a sheet, sprite rects, pivots, 9-slice borders and outlines are `unity-2d-sprites` — this
skill starts from sprites that already exist and only decides how they are packed and delivered.

Point filtering, mipmap and upscaling decisions for pixel art belong to `unity-2d-pixel-perfect`;
this skill sets `filterMode` and `generateMipMaps` to whatever you ask, with no opinion on which
suits an art style.

Download size and texture budget for a shipping build are `unity-web-release` and
`unity-android-release` — atlas format and max size are one input to those, not the whole answer.
Addressables as a content-delivery strategy (groups, catalogues, remote hosting, updates) is
larger than §5, which covers only the three pieces an atlas needs.

Generating the artwork itself is outside this library.

## Reference

- [`reference/v2-api.md`](reference/v2-api.md) — every class and member as enumerated, absent and
  obsolete ones included.
- [`reference/common-errors.md`](reference/common-errors.md) — the six costliest failures, each
  with the check that settles it.
- [`reference/addressables-delivery.md`](reference/addressables-delivery.md) — late binding end to
  end.
- `resources/`: `AtlasBuildGenerator.cs` (build-time generation, both delivery modes),
  `AtlasContentBuild.cs` (the content build that pairs with it), `AtlasSupplier.cs` (the runtime
  supplier), `ScriptablePackerExample.cs` (a grid packer and the shape of a custom one),
  `MultiPagePacker.cs`, `SizeOptimizedPacker.cs` (two more layouts) and `PackerValidation.cs`
  (a packer checking its own output).
