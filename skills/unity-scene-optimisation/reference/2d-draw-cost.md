# 2D draw cost and fill: every sprite pixel is blended, including the empty ones

> Part of the `unity-scene-optimisation` skill. Enter from a GPU frame time well above the CPU
> times, or from a frame time that follows the resolution. Sprites are transparent geometry:
> nothing is rejected by depth, so a pixel covered by five layers is shaded and blended five
> times, and the transparent corners of a sprite cost the same as its middle.

## The cheapest test

No profiler counter reports overdraw. Two tests stand in for it.

**Is the frame fill-bound?** Halve the render scale for one window:

```csharp
var urp = (UniversalRenderPipelineAsset)GraphicsSettings.currentRenderPipeline;
urp.renderScale = 0.5f;         // a quarter of the pixels; put it back to 1 afterwards
```

Frame time falling by half or more says the GPU is paying per pixel, and this file applies.
Frame time unchanged says the cost is per draw or per object: `reference/batching.md`. Where
the platform reports it, `gpuFrameTime` in the same window says so directly — `unity-profiling`
→ `reference/frame-windows.md`.

**Where is it?** Window → Analysis → Rendering Debugger → Rendering → Overdraw Mode, set to
`Transparent` or `All`; Max Overdraw Count sets the scale. Screenshot the situation. Under the
2D Renderer confirm the mode draws on your version; if it does not, disable sorting layers one
at a time and take a window for each.

## Sprite meshes: tight or full rect

| Mesh Type | Geometry | Fill | Use for |
|---|---|---|---|
| `SpriteMeshType.Tight` | An outline around the opaque pixels | The outline's area | Characters, props, anything with empty margins |
| `SpriteMeshType.FullRect` | Two triangles | The whole rectangle | Tiles, opaque panels, sprites drawn Tiled or Sliced, shader effects that need the rect's UVs |

A runner sprite in a 256 × 256 frame that covers a third of it draws three times the pixels on
a full rect. Twenty of them overlapping in the side run's crowd is the frame.

- Tight costs vertices. That is the right trade until sprites are tiny: below 32 × 32 px Unity
  uses a quad regardless.
- The setting is per texture, in the importer: `TextureImporterSettings.spriteMeshType`.
  Editing the outline itself is `unity-2d-sprites` → `reference/sprite-geometry.md`.
- `resources/Editor/SceneCostAudit.cs` reports `twoD.quadSprites`: sprite renderers whose
  sprite is two triangles. Many of them on character art is the finding.

## Layers that cover the screen

Each full-screen layer is one more blend per pixel. A side-run backdrop of sky, far skyline,
near skyline, rooftops and haze is five before a single actor is drawn.

- **Make the bottom layer opaque.** A sky on an opaque material, drawn first, is written once
  with no blend.
- **Merge layers that move together.** Two parallax layers with the same factor are one
  texture — `unity-2d-rendering` → `reference/parallax.md`.
- **Do not stack what is hidden.** A layer entirely behind an opaque foreground strip can be
  cut to the part that shows.
- **Full-screen effects are layers too**: a vignette sprite, a darkening quad at alpha 0.
  Disable the renderer when its alpha is 0. Post-processing volume cost is `unity-render-urp` §3.

## Batches: consecutive, same texture, same material

Two sprites share a draw only when they are next to each other in sorted order and use one
material and one texture.

| Break | Fix | Owner |
|---|---|---|
| Sprites on different textures interleaved in the sort | One atlas for everything that sorts together | `unity-sprite-atlas` |
| Sorting layers or orders that alternate two materials | Put the two materials on separate layers or orders | `unity-2d-rendering` → `reference/sort-order.md` |
| A `MaterialPropertyBlock` or `renderer.material` per sprite | Tint with `SpriteRenderer.color` | `unity-2d-rendering` → `reference/masks-and-materials.md` |
| A `SpriteMask` around each item | One mask for the area | `unity-2d-rendering` → `reference/masks-and-materials.md` |
| Lit and unlit sprites alternating | Group them by layer | `unity-2d-rendering` → `reference/lights-2d.md` |

A Y-sorted depot interleaves by nature: actors, shelves and pickups alternate by row. One atlas
for the Y-sorted layer is what makes that layer one batch.

Read the breaks in the Frame Debugger: each event names why it could not join the one before.

## Tilemap renderer mode

| `TilemapRenderer.Mode` | Draws | Cost |
|---|---|---|
| `Chunk` | Blocks of tiles as one mesh each | Lowest. One draw per chunk per texture: tiles from two textures split every chunk |
| `SRPBatch` | Chunks the SRP Batcher can batch | For a large flat map on a scriptable pipeline |
| `Individual` | Every tile sorted on its own | One sprite's worth of work per tile; needed only where actors walk behind tall tiles |

- Pack a tilemap's tiles into one atlas, or `Chunk` mode draws once per source texture.
- Keep the floor on `Chunk` and move only the tall tiles to a second Tilemap in `Individual` —
  the split is `unity-2d-rendering` → `reference/sort-order.md`.
- The audit prints `twoD.tilemapModes`. `Individual` on a floor the size of the yard is the
  finding.

## 2D lights

Under the 2D Renderer each blend style in use is a screen-sized light texture, and each light
is drawn into it: a scene of forty small lights is forty more fills of their area. Shrink the
lights' radius to what they light, cut the blend styles in use, and lower the lighting Render
Scale on the 2D Renderer asset. The model and the debugger for it are `unity-2d-rendering` →
`reference/lights-2d.md`.

## Particle fill

Particles are the densest overdraw a scene has: many large, soft, overlapping quads, often
near the camera.

- **Size on screen is the cost, not the count.** Ten dust quads filling the screen cost more
  than five hundred sparks. Set `ParticleSystemRenderer.maxParticleSize` — a share of the
  viewport, `0.5` by default — to `0.1` for anything that can drift past the camera.
- **Cut the texture's empty border.** A soft puff with half its quad at alpha 0 pays for the
  whole quad; crop the texture to the puff.
- **Fewer, more opaque particles** read the same as many faint ones and blend less often.
- **Short lifetimes and a cap**: Max Particles on the main module is the hard bound on fill.
- **Debris and sparks can be opaque or alpha-clipped**, which lets depth reject them in 3D.
- **Pickup bursts in the lane run** are pooled and prewarmed; a burst that instantiates its
  system on the hit is a spike on the CPU side, measured with a work counter — `unity-profiling`
  → `reference/work-counters.md`.

## UI on top

A canvas is more transparent layers. A full-screen panel at alpha 0 still fills the screen:
disable its `Canvas` or `CanvasRenderer`, never just fade it. Building screens that do not
stack is `unity-ui-ugui`.

## The same rule in 3D

Transparent meshes — glass in the gate room, foliage cards — sort back to front and overdraw
exactly like sprites. Use alpha clipping on an opaque material wherever a hard edge is
acceptable; opaque geometry is drawn front to back and rejected by depth.

## Read it again

Fill does not show in the render counters, so compare the frame time itself, with the instrument
that has a GPU — `unity-profiling` → `reference/compare.md`:

```bash
python3 scripts/compare_windows.py base.jsonl cand.jsonl --label ledge-drop --stat p95 \
    --counters "Render/Draw Calls Count,Render/SetPass Calls Count,Render/Batches Count"
```

The frame-time rows are always in the table; the counters listed are the batching half of this
file. Take both sides at the same resolution with vsync off — a frame pinned at 16.67 ms hides
a fill saving completely. For a mobile target the window that counts is on the device:
`unity-device-testing`.
