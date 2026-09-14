---
name: unity-3d-models
description: >-
  Bring 3D model files into a Unity game — import, optimise and wire them into
  prefabs. Built for AI image-to-3D output (Tripo / Hunyuan3D / Meshy / Rodin,
  usually `.glb`), works for any GLB/GLTF/FBX. Load when the user has a 3D
  model to add, wants a 2.5D sprite to become a real mesh, 3D assets make the
  game lag or stutter, a model "shows in Scene, invisible in Game", or distant
  textures shimmer. AI meshes are photogrammetry-dense and must be decimated
  first (gltf-transform CLI); Unity needs glTFast for GLB. Static props only:
  rigged, animated characters are `unity-rigged-character`, because glTFast
  cannot produce an Avatar.
---

# unity-3d-models — import, optimize & wire 3D models into a Unity game

**Scope:** static props (coins, obstacles, environment). **A rigged, animated
character is a different pipeline** — glTFast cannot produce an Avatar, so
characters must come in as FBX. See `unity-rigged-character`.

Two hard truths this skill exists for:

1. **Unity 6 can't import `.glb` natively** — you need the **glTFast** package.
2. **AI image-to-3D output is unusable raw.** Straight off Tripo/Hunyuan/Meshy, a
   mesh is photogrammetry-dense: routinely **~1,000,000+ triangles and 40 MB each**. A
   runner prop should be a few thousand tris. Pooled ×N, raw models will crawl
   the game. **Always inspect and decimate before using.**

## The pipeline, in order

| Step | What decides it | Read |
|---|---|---|
| 1 · Inspect | How dense is it really? AI image-to-3D output is routinely 1M+ triangles and 40 MB | `reference/import-and-decimate.md` |
| 2 · Decimate + shrink textures | This is the whole win. `gltf-transform simplify` before Unity ever sees the file | `reference/import-and-decimate.md` |
| 3 · Stage + import | Unity 6 has **no native GLB importer** — glTFast, and it is a UPM dependency you must add | `reference/import-and-decimate.md` |
| 4 · Wire into a prefab | An Editor script, so it is re-runnable and layer-aware | `reference/import-and-decimate.md` |
| 5 · It's invisible in Game view | Almost always layer/culling, not the mesh | `reference/culling-and-layers.md` |
| 6 · It looks cheap at distance | Filtering defaults, not model quality | `reference/texture-filtering.md` |
| 7 · It runs badly | Measure it first (`unity-profiling`), then budget and the order to attack it in | `reference/performance-budget.md` |

## Load what the situation needs

| The situation | Read |
|---|---|
| A model file to bring in; it's huge; decimation; glTFast setup | `reference/import-and-decimate.md` |
| "Shows in Scene, invisible in Game"; culling masks; layers | `reference/culling-and-layers.md` |
| Distant surfaces shimmer or look blurry; aniso; MSAA | `reference/texture-filtering.md` |
| The game lags/stutters with 3D assets; triangle budget; draw calls | `reference/performance-budget.md` |
| Numbers for the lag before touching a mesh: triangle and draw-call counters, a before/after window | skill `unity-profiling` |
| Textures and meshes are bloating memory or the build | skill `unity-android-release` → `reference/size-and-stripping.md` |
| A **rigged, animated character** rather than a prop | skill `unity-rigged-character` |
| 2D sprite sheets, slicing, pivots, 9-slice borders | skill `unity-2d-sprites` |
| Verifying any of it visually | skill `unity-debug` |

## Scope — what this skill does NOT do

Static props only. Characters take the FBX route because glTFast cannot produce an Avatar —
`unity-rigged-character`. Driving the Editor is `unity-cli` and `unity-debug`; build-wide
stripping is `unity-android-release` and `unity-web-release`.

## Two rules that decide everything else

> **Decimate before Unity sees the file.** AI image-to-3D output is photogrammetry-dense.
> Importing first and optimising later means every downstream asset — prefabs, colliders,
> lightmap UVs — is rebuilt from the wrong mesh.

> **Read/Write Enabled off on every mesh and texture nothing reads back.** It keeps a second,
> CPU-side copy resident for the asset's lifetime. Combine with **Strip Unused Mesh
> Components** — details in `unity-android-release` → `reference/size-and-stripping.md`.
>
> `isReadable` defaults to **`false`** on both `TextureImporter` and `ModelImporter`.
> So this is a *keep it off* rule, not a *turn it off* one — the cost appears when
> someone enables it for one script and never reverts it. Audit rather than assume.

**Anisotropic filtering defaults to `1`** — an imported texture reads `anisoLevel = 1`,
`mipmapEnabled = true`, `filterMode = Bilinear`. That combination is what makes a ground plane
shimmer into mush at grazing angles, and it is the default on every texture in the project.
→ `reference/texture-filtering.md`

For textures loaded at runtime through Addressables or AssetBundles — and only those — **KTX2 /
Basis Universal** ships one file that transcodes to the device's best GPU format (ASTC on
mobile, BC7 on desktop, ETC2 on older Android). Encode offline with `toktx`: `--genmipmap`,
`--assign_oetf linear` for normal/mask/data maps, and `--lower_left_maps_to_s0t0` to match
Unity's UV origin. ETC1S for albedo (small), UASTC for normals and UI (quality). Confirm the
project can transcode KTX2 at runtime — Unity reads it through the KTX for Unity package
(`com.unity.cloud.ktx`) — before encoding a whole texture set. Textures that
go **into the player build do not need this** — Unity already picks a format at build time.
