---
name: unity-scene-optimisation
description: >-
  Cut draw calls, triangles and texture memory: batching, LOD, occlusion, cull distances.
---

# unity-scene-optimisation — optimise the counter that moved, not the one you remember

> **Every lever here moves one counter and leaves the others alone.** The SRP Batcher lowers
> SetPass calls and not draw calls. A `LODGroup` lowers triangles and does nothing for a frame
> that is waiting on fill. Baked occlusion culling returns nothing in an open lane. A change
> made from habit lands on a counter that was never the problem. Each rung below starts from a
> number `unity-profiling` reports and ends with the same number read again.

## Symptom → where to look

Read the row off a window you already have. First match wins.

| The window says | Go to |
|---|---|
| "Draw calls are too high, what do I change"; the SRP Batcher is not batching; GPU instancing does nothing | §1 — batching |
| Draw calls rose after a tint, a flash or a per-object colour was added | §1 — a property block left the batch |
| "Set up LODs for this prop"; triangles high looking down the lane, lower looking at the floor | §2 — LOD |
| Low-tier trees or props missing after an FBX import; a fixed camera never switches level | §2 — `reference/lod.md`, the importer's `LODGroup` |
| Triangles high at every distance | `unity-3d-models` → `reference/import-and-decimate.md` |
| It still draws the room behind the wall; occlusion culling does nothing | §3 — occlusion |
| Draw calls climb with view distance, and what is added is a few pixels tall; small props pop in | [`reference/distance-texture-fill.md`](reference/distance-texture-fill.md) §4 — culling distances |
| A second camera doubled every render counter | [`reference/distance-texture-fill.md`](reference/distance-texture-fill.md) §4 — the culling mask |
| Texture memory over budget, or textures soft after streaming was turned on | [`reference/distance-texture-fill.md`](reference/distance-texture-fill.md) §5 |
| "Is it overdraw?" GPU frame time far above the CPU times; frame time follows the resolution | [`reference/distance-texture-fill.md`](reference/distance-texture-fill.md) §6 — fill |
| A 2D scene with more draw calls than sprites on screen warrant | [`reference/distance-texture-fill.md`](reference/distance-texture-fill.md) §6 — sort order and atlases |
| Shadow caster count high | `unity-lighting` → `reference/shadows.md` |
| Allocation per frame, a spike on spawn, discarded work | `unity-profiling` → `reference/where-the-time-goes.md` |

## 0. Before changing anything

1. **Hold a baseline.** Three windows of the named situation, saved before the first edit —
   `unity-profiling` → `reference/compare.md`.
2. **Confirm the counter exists on this build.** A name that is not exposed reads zero —
   `unity-profiling` → `reference/counters.md`. Under `-batchmode -nographics` every render
   counter is zero: this skill needs a window from an instrument with a graphics device.
3. **Read the scene's census.** `resources/Editor/SceneCostAudit.cs` prints one JSON object for
   the open scene and changes nothing: `Tools/Unity Dev/Scene Optimisation/Audit Open Scene`, or
   `SceneCostAudit.Audit()` from an eval. It says where a counter comes from.
4. **Run the rung's cheapest test.** Each section names one global switch that shows, in one
   window and with nothing authored, whether its lever can move the counter at all. Put the
   switch back afterwards.
5. **Make one change, take the same three windows, compare.**

```bash
python3 scripts/compare_windows.py base.jsonl cand.jsonl --label approach-gate \
    --counters "Render/*,Memory/Texture Memory,Memory/Mesh Memory"
```

That script is `unity-profiling` → `scripts/compare_windows.py`. Read the whole table: a lever
that lowers its own counter and raises another has moved the cost, not removed it.

## 1. Draw calls and SetPass calls — batching

**Cheapest test:** turn the SRP Batcher off on the URP Asset for one window. SetPass calls
jumping says it was carrying the scene and the remaining cost is elsewhere; no change says the
scene's renderers are not on it.

A draw takes the first path that accepts it:

| Path | Lowers | Needs | Frame Debugger event |
|---|---|---|---|
| GPU Resident Drawer | Draw calls | Forward+, a `MeshRenderer`, no property block | `Hybrid Batch Group` |
| Static batching | Draw calls | Batching Static; pays in mesh memory | `Static Batch` |
| SRP Batcher | SetPass calls | A compatible shader, no property block | `SRP Batch` |
| GPU instancing | Draw calls | The SRP Batcher not taking the renderer | `Draw Mesh (instanced)` |
| Dynamic batching | Draw calls | Meshes under 300 vertices; leave it off | `Draw Dynamic` |

- **Read the path in the Frame Debugger, never infer it.** The event name is the path, and the
  event's details say why a draw could not join the one before.
- **One `MaterialPropertyBlock` takes a renderer out of the SRP Batcher and the resident
  drawer.** For a state many objects share — every armed hazard — swap to a second shared
  material. The audit's `propertyBlocks.paths` lists the renderers, in play mode.
- **Enabling GPU instancing on a URP Lit material changes nothing**: the SRP Batcher took it.
- **The SRP Batcher batches by shader variant, not by material.** A kit whose materials differ
  in keywords is several batches; give them the same maps.
- **Static batching copies every instance's vertices.** Never use it for a repeated kit piece.

Every path's requirements, the resident drawer's settings and material consolidation:
[`reference/batching.md`](reference/batching.md).

## 2. Triangles at distance — LOD

**Cheapest test:** halve `QualitySettings.lodBias` for one window. No change in the triangle
median means the scene has no levels to fall back to: the audit's `lod.groupTriangleShare` is
the share of triangles under a `LODGroup`, and `lod.heaviestWithout` the ten meshes to start on.

- **Heights are a share of the screen**, not distances: the first hand-over at 0.5, each later
  one at 0.4 of the one before, culled below 0.01. At 60° a 2 m crate swaps at 3.5 m and 8.7 m
  and is culled at 173 m.
- **`resources/Editor/LodGroupBuilder.cs`** builds the group from children named `_LOD0` …
  `_LODn`; it reports levels, triangles and heights and waits for confirmation.
- **A level earns its place when it halves the triangles.** The last level is a different
  object: one material, no shadow casting.
- **The collider never needs a LOD.** One collider on the root; none on the level children.
- **A fixed camera picks the level by quality tier**, not screen height, and the FBX importer's
  automatic `LODGroup` (from `_LODn` names) has to be removed at prefab build.
- **Mesh LOD** is the import-time alternative for dense single-material meshes: no extra
  renderers, no culling.
- **`lodBias` and `maximumLODLevel` are per quality tier**: 0.6 and 1 on the low tier, 1.0 and
  0 on medium, 2.0 and 0 on desktop.

Making the lower meshes is `unity-3d-models` → `reference/import-and-decimate.md`. The distance
formula, cross-fade and the two mechanisms compared: [`reference/lod.md`](reference/lod.md).

## 3. Drawn but hidden — occlusion

**Cheapest test:** with the runner facing the wall, deactivate the rooms that cannot be seen and
take one window. That is the most occlusion culling can return. If the counters barely move,
stop.

- **It works in the gate room and not in the lane.** Occlusion needs large solid things between
  the camera and most of the scene; an open strip or a depot seen from above has none.
- **Baked:** flag walls and floors Occluder Static, every static renderer Occludee Static, then
  bake. `resources/Editor/OcclusionBake.cs` reports the flagged counts and settings, waits,
  bakes, and reads the data size back. Zero occluders is refused.
- **Smallest Occluder (default 5 m) is also the cell size.** Lower it only when a wall that
  should hide the next room does not; 2 for the gate room.
- **The gate is an `OcclusionPortal`**, opened and closed by the switch. A moving thing is
  never a baked occluder.
- **The bake goes stale.** After a static wall moves, the old data culls by the old layout:
  props vanish in plain view. Re-bake on every layout change.
- **GPU occlusion culling** needs no bake, for renderers on the GPU Resident Drawer. URP skips
  it on Qualcomm GPUs: take the window on the device.

Accept a culling change only with a second window looking through the doorway, where the
counters must not have fallen. [`reference/occlusion.md`](reference/occlusion.md).

## 4–6. Distance, texture memory, fill → `reference/distance-texture-fill.md`

§4 per-layer cull distances and a second camera's culling mask; §5 texture size and mipmap
streaming; §6 overdraw, fill and 2D draw cost. Same numbering there.

## The tools

| File | Does |
|---|---|
| `resources/Editor/SceneCostAudit.cs` | Read-only, one JSON object: triangles by layer, materials and shaders, property blocks, static-flag and LOD coverage by triangle share, shadow-casting lights, large textures that do not stream, camera culling, sprite and tilemap modes |
| `resources/Editor/LodGroupBuilder.cs` | `Plan(root)` reports, `Build(root)` writes a `LODGroup` from `_LOD0` … `_LODn` children |
| `resources/Editor/OcclusionBake.cs` | `Plan()` reports flagged renderers and settings; `Bake(…)` bakes and returns the data size |

Menu root: Tools → Unity Dev → Scene Optimisation. Editor folder, no package. SRP Batcher
compatibility is not readable from public script API: read it on the shader's inspector.

## The report

```
Situation  approach-gate seed=7 · editor-windowed · 90 frames, 30 warm-up, 3 windows each
Counter    Render/Triangles Count median 1.84 M looking down the lane
Test       lodBias 1.0 → 0.5: 1.84 M → 1.79 M (no LODGroup under 81% of the triangles)
Change     LODGroup on LaneBarrier, 3 levels 0.5 / 0.2 / cull 0.01 — 240 instances
Result     triangles 1.84 M → 0.61 M (-66.8%) · draw calls 412 → 418 · ft_p95 12.9 → 9.4 ms
Open       cross-fade off: the swap at 8.7 m pops; device window not taken
```

The counter, the test that showed the lever was real, one change, the counter again, what was
not covered.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Taking the window, listing counters, the before/after table itself | `unity-profiling` |
| Decimating a mesh, glTF import, a model's triangle budget | `unity-3d-models` |
| Shadow distance, cascades, which lights cast, baking light | `unity-lighting` |
| Modular kits, trim sheets, collision proxies | `unity-3d-level` |
| Post-processing cost, renderer features, URP not active | `unity-render-urp` |
| Packing sprites into an atlas | `unity-sprite-atlas` |
| Sorting layers, 2D lights, sprite masks · sprite outlines | `unity-2d-rendering` · `unity-2d-sprites` |
| A canvas that rebuilds every frame | `unity-game-ui` · `unity-ui-ugui` |
| Build size and stripping · a window on the phone | `unity-android-release` · `unity-web-release` · `unity-device-testing` |
| Deciding the frame and memory budget | `unity-game-brief` |
