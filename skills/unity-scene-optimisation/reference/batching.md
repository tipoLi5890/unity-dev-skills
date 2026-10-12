# Batching: which path drew it, and what pushed it off that path

> Part of the `unity-scene-optimisation` skill. Enter from `Render/SetPass Calls Count`,
> `Render/Draw Calls Count` and `Render/Batches Count` high while triangles are ordinary. Five
> mechanisms can draw a mesh, each moves a different counter, and turning on a second one often
> switches off the first.

## Which counter each one moves

| Path | Lowers | Does not lower | Frame Debugger event |
|---|---|---|---|
| SRP Batcher | SetPass calls — the state changes between draws | Draw calls | `SRP Batch` |
| GPU Resident Drawer | Draw calls and CPU culling time | Triangles | `Hybrid Batch Group` |
| GPU instancing | Draw calls, for one mesh and one material | SetPass calls already low | `Draw Mesh (instanced)` |
| Static batching | Draw calls, for static meshes sharing a material | Memory — it raises it | `Static Batch` |
| Dynamic batching | Draw calls, for tiny meshes | CPU — it pays per frame | `Draw Dynamic` |
| None | — | — | `Draw Mesh` |

A report that says "batching improved" names the counter. With the SRP Batcher on, a draw-call
count of 400 over 12 SetPass calls is a batched scene.

## The order they are tried

For a renderer in a URP scene:

1. **GPU Resident Drawer**, when it is on and the renderer qualifies. It takes the renderer out
   of the ordinary path altogether.
2. **Static batching**, when the object is Batching Static and the player setting is on. A
   static-batched renderer is never GPU-instanced.
3. **SRP Batcher**, when the shader is compatible and the renderer carries no
   `MaterialPropertyBlock`. It also draws static batches.
4. **GPU instancing**, only when the SRP Batcher did not take the renderer and the material has
   `enableInstancing`.
5. **Dynamic batching**, when enabled on the URP Asset and the mesh is small enough.

So enabling GPU instancing on a URP Lit material changes nothing: the SRP Batcher already took
it. And one `MaterialPropertyBlock` drops a renderer from step 3 to step 4 or to a plain draw.

## Read the path, do not infer it

Window → Analysis → Frame Debugger, in play mode, with the situation on screen.

- The event list names the path for every draw, with the strings in the table above.
- Select an event: the details give its shader, keywords and, where a draw could not join the
  one before it, a line saying why — a different keyword set, a property block, a different
  material.
- Count events by name before and after. That count is the explanation for the counter.

`resources/Editor/SceneCostAudit.cs` gives the scene-side census without a frame:
`srpBatcher`, `staticBatching`, `dynamicBatching`, `materials.distinct`, `materials.byShader`,
`materials.instancingEnabled`, `propertyBlocks.renderers` with their paths, and
`staticFlags.batching`. Run it in play mode: property blocks are set by running scripts.

## SRP Batcher

On by default: the URP Asset's SRP Batcher toggle, `UniversalRenderPipelineAsset.useSRPBatcher`,
mirrored at runtime in `GraphicsSettings.useScriptableRenderPipelineBatching`. Toggling that
one flag for a window is the cheapest test of how much it carries.

It batches consecutive draws that use the **same shader variant** — not the same material. Two
hundred materials on URP Lit with the same keywords are one batch; two materials whose keyword
sets differ (one with a normal map, one without) are two.

**Compatibility is a property of the shader**: every material property declared in one
`CBUFFER_START(UnityPerMaterial)` block. URP's own shaders and Shader Graph output are
compatible; a hand-written shader with a loose `float4 _Tint;` is not. It is not readable from
public script API. Read it on the shader asset's inspector, which states `SRP Batcher:
compatible` or names the property that broke it, or per draw in the Frame Debugger.

**What takes a renderer out of it:**

| Cause | Fix |
|---|---|
| `renderer.SetPropertyBlock(block)` | For a state many objects share — every armed hazard — swap to a second shared material. Clear a temporary block with `SetPropertyBlock(null)` |
| `renderer.material` | It clones the material: one more material per object, and one to destroy. Use `sharedMaterial` |
| An incompatible shader | Move its properties into `UnityPerMaterial` |
| Different keywords across a kit | Give every kit material the same maps so the variant is one |
| Particles, lines, trails | Not handled; they batch among themselves by material |

`Renderer.HasPropertyBlock()` answers for one renderer at runtime.

## GPU Resident Drawer

URP hands qualifying mesh renderers to a `BatchRendererGroup`, which culls and submits them in
instanced groups. It is the path that lowers draw calls for a level built from repeated kit
pieces, with nothing authored per object.

**Project requirements**, each of which disables it with a console line beginning
`GPUResidentDrawer`:

| Requirement | Where |
|---|---|
| `gpuResidentDrawerMode` is `InstancedDrawing` | URP Asset → Rendering → GPU Resident Drawer |
| Every renderer in the asset's list is a Universal Renderer on Forward+ or Deferred+ | Universal Renderer Data → Rendering Path |
| BatchRendererGroup Variants is Keep All | Project Settings → Graphics. Otherwise the instancing variants are stripped from the player |
| A graphics API with compute shaders and raw buffers | Player Settings → Graphics APIs. Take the window on the target device to confirm |

**Per renderer**: a `MeshRenderer` with a shader that has the instancing variants — URP Lit,
Unlit and Shader Graph do — and no `MaterialPropertyBlock`. Skinned meshes, particles and
sprites stay on the ordinary path.

**With it on:**

- Turn Static Batching off in Player Settings; the URP Asset inspector says so when both are on.
- `smallMeshScreenPercentage` (0–20, default 0) culls drawer-owned renderers below that share of
  the screen. Members of a `LODGroup` ignore it and use the group's own cull height.
- GPU occlusion culling becomes available — `reference/occlusion.md`.

```csharp
var urp = (UniversalRenderPipelineAsset)GraphicsSettings.currentRenderPipeline;
bool supported = urp.IsGPUResidentDrawerSupportedBySRP(out string reason, out LogType severity);
bool keepAll = EditorGraphicsSettings.batchRendererGroupShaderStrippingMode
               == BatchRendererGroupStrippingMode.KeepAll;         // read-only; set it in Graphics settings
```

Read it back in the Frame Debugger (`Hybrid Batch Group` events replace the `SRP Batch` ones for
the kit) and in `Render/Draw Calls Count`.

## GPU instancing

For one mesh drawn many times with per-instance values, or with no GameObject at all.

- `Material.enableInstancing = true`, and a shader the SRP Batcher does not take — in practice,
  a renderer with a `MaterialPropertyBlock` whose properties the shader declares as instanced.
- For hundreds of identical things with no behaviour — lane markers, debris —
  `Graphics.RenderMeshInstanced(new RenderParams(material), mesh, 0, matrices)`: no
  GameObjects, and no culling unless the caller does it. Read the draws it became in the Frame
  Debugger.

## Static batching

Marks: `StaticEditorFlags.BatchingStatic` on the object and Static Batching in Player Settings
(`PlayerSettings.GetStaticBatchingForPlatform`).

The cost is memory. Each batched object's vertices are copied into a combined mesh in world
space: forty copies of a 2,000-vertex shelf are 80,000 vertices in memory and in the build,
where instancing stores 2,000. A batch holds at most 64,000 vertices. Use it for unique static
geometry that shares a material — the gate room's walls — and never for a repeated kit piece.

`Renderer.isPartOfStaticBatch` reads the result in play mode. `StaticBatchingUtility.Combine`
does the same for objects placed at runtime, at the same memory cost.

## Dynamic batching

`UniversalRenderPipelineAsset.supportsDynamicBatching`, off by default. It merges meshes of up
to 300 vertices on the CPU every frame. On current hardware the merge costs more than the draws
it saves. Leave it off; reach for the resident drawer or instancing.

## Fewer materials, fewer variants

When the path is right and SetPass calls are still high, the scene has too many shader variants
or the draws are interleaved.

- **One material per kit.** A trim sheet or an atlas lets every wall, floor and prop of a kit
  share a material — `unity-3d-level` → `reference/modular-kit.md`. `materials.distinct` against
  `materials.shaders` in the audit shows the spread.
- **One keyword set per shader.** A kit where half the materials lack a normal map is two
  variants. Assign a flat normal map to the rest.
- **Transparent objects sort back to front and cannot be reordered** to group by material.
  Every transparent material between two others is a break. Make cut-outs alpha-clipped opaque.
- **Sprites** follow their own rule — consecutive in sort order with one texture —
  `reference/2d-draw-cost.md`.
- **UI** is a separate batcher: a canvas that rebuilds every frame is `unity-game-ui`.

## Read it again

Three windows a side — `unity-profiling` → `reference/compare.md`:

```bash
python3 scripts/compare_windows.py base.jsonl cand.jsonl --label gate-room \
    --counters "Render/SetPass Calls Count,Render/Draw Calls Count,Render/Batches Count,Memory/Mesh Memory,Internal/Render Thread"
```

`Memory/Mesh Memory` is in the list on purpose: static batching buys its draw calls with it.
`Internal/Render Thread` is the time the change was for; fewer draw calls with the same render
thread time means the frame was not waiting on them.
