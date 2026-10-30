# Rungs 4–6: culling distances, texture memory, overdraw and fill

Moved out of SKILL.md, which keeps rungs 0–3; numbering continues it. Each rung starts from a counter `unity-profiling` reports and ends with the same counter read again.

## 4. Too far to matter — culling distances

**Cheapest test:** halve `Camera.farClipPlane` for one window, then put it back — the fix is
per layer, because the far plane also removes the gate.

- **`Camera.layerCullDistances` takes exactly 32 floats**; 0 keeps the far plane for that
  layer. Small props at 45 m, medium at 90 m, the gate on the far plane.
- **Derive the distance from size**: an object under 8 px tall is not read. At 60° and 1080p
  that is 117 × its height.
- **`layerCullSpherical = true`** on any camera the player turns, or props pop at the screen
  edge.
- **A layer is shared with physics.** Put the renderer on a child with the culling layer and
  keep the collider on the root.
- **Under Cinemachine the far plane is on the rig's lens** — `unity-camera`.
- **Mask a second camera**, or a minimap draws the whole scene again.

[`reference/culling-distances.md`](culling-distances.md).

## 5. Texture memory

**Cheapest test:** `QualitySettings.globalTextureMipmapLimit = 1` for one window and one
screenshot. Matching screenshots mean the textures are larger than the screen can show.

- **Size and compression first.** A 2048 texture is 21.3 MB uncompressed and 2.4 MB in ASTC
  6×6; halving it divides by four. The audit lists `textures.largeNotStreaming`.
- **Streaming needs three switches**: the quality level's Texture Mipmap Streaming, the
  texture's Stream Mipmap Levels, and mipmaps.
- **The budget (512 MB) counts what cannot stream.** When UI and sprites alone exceed it, every
  streaming texture drops two levels and the scene goes soft.
- **Sprites and UI have no mipmaps**: streaming does nothing for a 2D game.
- **Read `Texture.desiredTextureMemory` against `targetTextureMemory`**, not the look.

What a build carries is `unity-android-release` → `reference/size-and-stripping.md` and
`unity-web-release` → `reference/settings-and-verification.md`. The settings, the readback line
and camera cuts: [`reference/texture-streaming.md`](texture-streaming.md).

## 6. Overdraw, fill and 2D draw cost

**Cheapest test:** set the URP Asset's `renderScale` to 0.5 for one window. Frame time falling
by half or more is fill; unchanged is draws, and §1 applies.

- **Every sprite pixel inside its mesh is blended, alpha 0 included.** Tight meshes for
  characters and props; full rect only for tiles and sliced panels.
- **Each screen-covering layer is one more blend per pixel.** Make the bottom layer opaque.
- **Sprites batch only when consecutive in sort order on one texture and material** —
  `unity-2d-rendering` → `reference/sort-order.md`, `unity-sprite-atlas`.
- **A Tilemap floor stays in Chunk mode**; Individual is one sprite's work per tile.
- **Particles cost by size on screen, not count.** Cap `ParticleSystemRenderer.maxParticleSize`
  at 0.1 and crop the texture's empty border.
- **A panel at alpha 0 still fills the screen.** Disable it.

Post-processing a mobile frame can afford is `unity-render-urp` §3.
[`reference/2d-draw-cost.md`](2d-draw-cost.md).
