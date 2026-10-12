# Texture memory: size first, streaming second

> Part of the `unity-scene-optimisation` skill. Enter from `Render/Used Textures Bytes` or
> `Memory/Texture Memory` above the budget. Mipmap streaming decides which mip levels are
> resident; it cannot make a texture that is four times too large cheap, and it does nothing at
> all for a texture without mipmaps.

## The cheapest test

```csharp
QualitySettings.globalTextureMipmapLimit = 1;      // every mipmapped texture loads at half size
```

One window with it at 1, one at 0, same situation. The difference is what halving every texture
would return, and a screenshot of each says what it would cost. If the screenshots match, the
textures are larger than the screen can show and import size is the fix. Put it back to 0.

## Lever 1 — import size and compression

Bytes for one 2048 × 2048 texture, with its mip chain:

| Format | Bits per texel | Resident |
|---|---|---|
| RGBA32, uncompressed | 32 | 21.3 MB |
| BC7 · ASTC 4×4 | 8 | 5.3 MB |
| DXT1 · ETC2 RGB | 4 | 2.7 MB |
| ASTC 6×6 | 3.56 | 2.4 MB |
| ASTC 8×8 | 2 | 1.3 MB |

Halving the size divides every row by four. Three rules cover most of a scene:

- **Size by texels on screen.** A crate 1 m wide that never fills more than 400 px needs 512,
  not 2048. Start generated props at 512 — `unity-3d-models` →
  `reference/performance-budget.md`.
- **Compress per platform, never "None".** ASTC 6×6 on Android and iOS, BC7 or DXT on desktop.
  An uncompressed UI atlas is the commonest single entry in a texture memory report.
- **Turn Read/Write off.** A readable texture keeps a second copy in system memory.

```csharp
var importer = (TextureImporter)AssetImporter.GetAtPath(path);
TextureImporterPlatformSettings android = importer.GetPlatformTextureSettings("Android");
android.overridden = true;
android.maxTextureSize = 1024;
android.format = TextureImporterFormat.ASTC_6x6;
importer.SetPlatformTextureSettings(android);
importer.SaveAndReimport();                         // rewrites the import: report the list first
```

`resources/Editor/SceneCostAudit.cs` lists, under `textures.largeNotStreaming`, every texture
the open scene's materials and sprites reference whose longer side is 2048 or more and which
does not stream — the first candidates for a smaller import. What a platform's build finally
carries is read from the build, not the importer: `unity-android-release` →
`reference/size-and-stripping.md`, `unity-web-release` → `reference/settings-and-verification.md`.

## Lever 2 — mipmap streaming

With streaming on, Unity loads for each texture only the mip levels the cameras need, within a
memory budget.

**Three switches, all required:**

| Switch | Where | From script |
|---|---|---|
| Texture Mipmap Streaming, per quality level | Project Settings → Quality | `QualitySettings.streamingMipmapsActive` |
| Stream Mipmap Levels, per texture | Texture import settings | `TextureImporter.streamingMipmaps` |
| Mipmaps generated | Texture import settings | `TextureImporter.mipmapEnabled` |

**The quality-level settings:**

| Setting | Default | Meaning |
|---|---|---|
| `streamingMipmapsMemoryBudget` | 512 MB | The total for **all** textures, streaming or not |
| `streamingMipmapsMaxLevelReduction` | 2 | How many top levels a texture may lose to fit the budget |
| `streamingMipmapsAddAllCameras` | true | Every camera drives streaming. Off: only cameras with a `StreamingController` |
| `streamingMipmapsRenderersPerFrame` | 512 | Renderers examined per frame; lower spreads the CPU cost |
| `streamingMipmapsMaxFileIORequests` | 1024 | Concurrent mip loads |

**The budget includes what cannot stream.** If the non-streaming textures alone — UI, sprites,
anything without mipmaps or without the per-texture flag — exceed the budget, every streaming
texture is pushed down by the full level reduction and the whole scene goes soft. Read
`Texture.nonStreamingTextureMemory` first and set the budget above it.

**What does not stream:** textures without mipmaps, render textures, and anything whose import
flag is off. Sprites and UI usually have no mipmaps, so
streaming does nothing for a 2D game: size and atlas them instead — `unity-sprite-atlas`.

**In the Editor** streaming runs only when Project Settings → Editor → Texture Streaming
Settings → Enable Mipmap Streaming In Play Mode is on. Check it before trusting an editor window;
the numbers that matter come from a development player.

## Reading what was loaded

All static, all bytes, from `UnityEngine.Texture`:

| Property | Says |
|---|---|
| `totalTextureMemory` | Everything at full resolution: the cost with streaming off |
| `desiredTextureMemory` | What the cameras want with no budget |
| `targetTextureMemory` | What streaming is aiming for after the budget and the level reduction |
| `currentTextureMemory` | What is resident now |
| `nonStreamingTextureMemory` | The part streaming cannot touch |
| `streamingTextureCount` · `nonStreamingTextureCount` | How many of each |
| `streamingTexturePendingLoadCount` | Loads still queued; non-zero for long means IO is the limit |

```csharp
const float MB = 1024f * 1024f;
Debug.Log($"[TEX] total={Texture.totalTextureMemory / MB:0} desired={Texture.desiredTextureMemory / MB:0} " +
          $"target={Texture.targetTextureMemory / MB:0} current={Texture.currentTextureMemory / MB:0} " +
          $"fixed={Texture.nonStreamingTextureMemory / MB:0} budget={QualitySettings.streamingMipmapsMemoryBudget:0} " +
          $"streaming={Texture.streamingTextureCount} pending={Texture.streamingTexturePendingLoadCount}");
```

| The line says | Meaning | Do |
|---|---|---|
| `desired` ≈ `total` | The camera needs nearly everything at full size | Streaming saves nothing here; reduce import sizes |
| `desired` well under `budget` | Nothing is being held back | Fine, or lower the budget to what the tier has |
| `target` under `desired` | The budget is cutting levels the camera wants | Expect softness; raise the budget or shrink the fixed part |
| `fixed` over `budget` | Everything streaming is at its lowest allowed level | Fix the non-streaming textures |
| `streaming` is 0 | No texture has the import flag | Set it on the scene's large textures |

Per texture: `Texture2D.loadedMipmapLevel` against `desiredMipmapLevel` (0 is full size), and
`requestedMipmapLevel` to force one with `ClearRequestedMipmapLevel()` to release it. The
Rendering Debugger's Mipmap Streaming panel colours the scene by the same values.

## Camera cuts

A cut to a place the camera has not seen shows low mips for a few frames. Preload before it:

```csharp
var controller = gateCamera.GetComponent<StreamingController>();    // on the camera about to go live
controller.SetPreloading(2f, true, runnerCamera);     // up to 2 s, then enable this camera and disable that one
// or poll controller.IsPreloading() and cut when it turns false
```

`streamingMipmapBias` on the same component shifts the chosen level for that camera: `1` for a
minimap camera that never needs full size.

## Per tier

| Tier | `globalTextureMipmapLimit` | Streaming | Budget |
|---|---|---|---|
| Low — older phones | 1 | On | 256 MB |
| Medium | 0 | On | 512 MB |
| High — desktop | 0 | Off, or on at 1024 MB | — |

`PlayerSettings.mipStripping` removes from the build the top levels that no quality level of
the target can ever load, so a mobile build with the limit at 1 on every tier also ships
smaller. A stripped level cannot be restored at runtime by raising the limit.

## Read it again

Texture memory is a level, so compare the median — `unity-profiling` → `reference/compare.md`:

```bash
python3 scripts/compare_windows.py base.jsonl cand.jsonl --label depot-aisle \
    --counters "Render/Used Textures Bytes,Memory/Texture Memory,Memory/Total Used Memory" --stat median
```

Attach one screenshot per side from the same camera pose. Memory down with a soft floor texture
is a trade to report, not a win. And take the window after the camera has stood still for a
second: streaming is still loading during the first frames of a situation.

## Traps

- **A new texture streams only after its import flag is set**; generated and downloaded assets
  arrive with it off. Set it in an `AssetPostprocessor` for the folders that hold level art.
- **Lightmaps have their own switch**: Lightmap Streaming in Player Settings, per platform.
- **`Texture.streamingTextureForceLoadAll = true` is a test switch.** Left on, streaming is off.
- **A player build on Android must compress with LZ4 or LZ4HC for streaming to load mips on
  demand.** Confirm the build's compression before reading a device window.
