---
name: unity-2d-rendering
description: >-
  Draw order and 2D lighting in Unity 6: the four sorting keys in priority
  order, SortingGroup, Y-sort for top-down, isometric and hex scenes, Light2D,
  shadow casters, normal maps, sprite masks and parallax layers. Load for:
  "this sprite draws behind that one", "Order in Layer does nothing", "moving
  it in z changes nothing", "the player walks behind a wall it stands in front
  of", "the Light 2D does nothing", "everything went black when I added a
  light", "the normal map does nothing", "the sprite mask hides the wrong
  things", "parallax background". Pixel snapping is unity-2d-pixel-perfect;
  post-processing is unity-render-urp; tile palettes are unity-tilemap; camera
  rigs are unity-camera.
---

# unity-2d-rendering — draw order is four keys in a fixed priority, and z is the last of them

> **Moving a sprite in z is almost never the fix.** Two overlapping renderers are compared on
> sorting layer, then Order in Layer, then render queue, then distance along the sort axis. The
> first key that differs decides and the rest are never read. World z is only what "distance"
> happens to mean under the default sort mode — and under a custom axis it means nothing.
>
> **The first `Light2D` you add turns everything it does not light black.** With no light in
> the scene, lit sprites draw at full colour; with one, every pixel outside its shape and every
> sorting layer it does not target receives darkness. Both halves of this skill are the same question: which asset is the renderer
> actually reading?

## Symptom → where to look

First match wins. Stop at the first cause the audit or the frame confirms.

| Symptom | Go to |
|---|---|
| A sprite draws behind one it should be in front of | §1 |
| Changing z or Order in Layer makes no difference | §1 — an earlier key already decided |
| Two sprites flicker or swap as the camera moves | §1 — a tie on all four keys |
| A character's hat, weapon or carried item sorts apart from its body | §2 |
| Something appears between the parts of a character | §2 |
| Seen from above, the runner's head goes behind a shelf it stands in front of | §3 |
| Isometric or hex pieces draw inside out against the board | §3 |
| The sort axis is set under Project Settings and nothing changed | §0, then §3 |
| The runner cannot walk behind a tall tile, or is always behind the whole Tilemap | §4 |
| Particles or a world canvas draw under the sprites | §4 |
| The Light 2D does nothing | §5 |
| Everything went black after adding one light | §5 — no Global light |
| One sorting layer stays dark, or stays bright, under a light | §5 — target sorting layers |
| No shadow, or a wall that shades itself black | §6 |
| The normal map does nothing | §6 |
| A sprite mask hides nothing, or hides sprites it should leave alone | §7 |
| Tinting or flashing one sprite multiplied the draw calls | §7 |
| Background layers shudder, slide after a respawn, or run out in a long level | §8 |

## 0. Before diagnosing

Work on a live Editor, not on files — `unity-debug` → `reference/editor-control.md`. Two
reports come first, because every later section depends on what they say.

1. **`Renderer2DSetup.Report()`** — the pipeline asset in force for the current quality level,
   its renderer list, which renderer is the default, and the sort mode and axis on each 2D
   Renderer. Three outcomes:
   - `pipeline` is `built-in`: there is no `Light2D`, and the sort axis lives on the camera
     and under Project Settings → Graphics.
   - URP with `renderer2DInForce` false: sprites sort by the camera's own axis and lights do
     nothing. The create command in the same file adds a 2D Renderer after reporting.
   - URP with a 2D Renderer in force: the renderer asset's Transparency Sort Mode and Axis are
     the only ones read. A value under Project Settings or on the camera is ignored.
   A URP asset can sit in the project and be assigned nowhere: `unity-render-urp` →
   `reference/resolve-active-pipeline.md`.
2. **`SortingAudit.Json()`** — every renderer in the open scenes with its four keys, its
   `SortingGroup`, its sort point, whether its material is lit, and the pairs that tie.

Then two rules for how the turn ends:

- **Answer from the frame.** The Frame Debugger (Window → Analysis → Frame Debugger) shows the
  order things were drawn in; a later event is on top. Where the audit and the frame disagree,
  the frame is right.
- **Change the key that decided, and only that one.** Raising Order in Layer on an object whose
  sorting layer already lost changes nothing and leaves a wrong number behind for the next
  person. Record and restore any setting changed while probing.

## 1. The four keys

| # | Key | Set on | Decides |
|---|---|---|---|
| 1 | Sorting layer | Renderer; order from the list in Tags and Layers | Higher in the list draws first |
| 2 | Order in Layer | Renderer, −32768 to 32767 | Higher draws later, on top |
| 3 | Render queue | Material | Higher draws later. Both default sprite shaders are 3000 |
| 4 | Distance along the sort axis | The renderer's sort point and the sort mode | Further draws first |

- **Compare in order.** Find the two renderers in the audit and read `layerValue`, `order`,
  `queue`, `distance`. The first difference is the whole explanation.
- **A tie on all four has no defined order** and can swap from frame to frame. The audit's
  `ties` array lists every overlapping pair. Fix a tie with a key, never with a hope that
  hierarchy order holds.
- **`SortingLayer.id` is not an order.** Compare `SortingLayer.GetLayerValueFromID(id)`. A
  misspelt `sortingLayerName` lands on Default without an error.
- **z is key 4 only**, and only under `Default`, `Orthographic` or `Perspective`. Under
  `CustomAxis` with `(0, 1, 0)` z is ignored completely.
- **Key 3 behaves differently outside the 2D Renderer.** The 2D Renderer sorts every queue in
  one back-to-front list per batch of layers. The Built-in pipeline and URP's Universal
  Renderer draw opaque-queue materials in an earlier pass with depth writing: an opaque
  `MeshRenderer` there ignores keys 1 and 2 against sprites and hides them by z.

Each key in full, the three places a sort axis can live, and the fix per deciding key:
[`reference/sort-order.md`](reference/sort-order.md).

## 2. SortingGroup — a character is one thing

A `SortingGroup` on a root makes everything below it sort as one unit against the outside,
using the group's own layer and order and the root's position. Inside, the children order
themselves with their own keys.

- A multi-sprite or skeletal character gets one group on its root. Parts are ordered inside
  with Order in Layer: body 0, satchel 1, cap 2.
- Nothing outside can be drawn between two members. To put a pickup between body and cap, make
  it a child inside the group.
- A child's Order in Layer cannot lift it over an outside object; raise the group's.
- `sortAtRoot` on a nested group takes it out of its parent.

What a group costs and what it isolates: [`reference/sort-order.md`](reference/sort-order.md).

## 3. Sorting from above

Depth in a top-down, isometric or hex view is key 4 with a custom axis. Four settings, and it
fails if any one is missing:

1. Sort mode `CustomAxis`, axis `(0, 1, 0)` — on the asset §0 named.
2. Pivot at the feet on every sprite that takes part — `unity-2d-sprites` for setting pivots.
3. `SpriteRenderer.spriteSortPoint = SpriteSortPoint.Pivot`. The default is `Center`, which
   swaps a tall shelf and the runner half a shelf late.
4. One sorting layer **and** one Order in Layer for everything that Y-sorts. Keys 1 and 2 beat
   the axis.

Isometric Z as Y starts from `(0, 1, -0.26)`. A board with rows is often better served by an
Order in Layer per row than by the axis. Layer table, split tall objects, the isometric and hex
cases, and the row formula: [`reference/y-sort.md`](reference/y-sort.md).

## 4. Tilemaps, particles and UI

- **`TilemapRenderer.mode`.** `Chunk` sorts the map as chunks: the runner is in front of all
  of it or behind all of it. `Individual` sorts each tile at its own position against other
  renderers on the same layer and order — required for tall tiles the runner walks behind,
  and it gives up chunk batching. Keep floors on `Chunk`, put tall tiles on a second Tilemap.
- **`TilemapRenderer.sortOrder`** is the corner the renderer starts from among its own tiles.
- **A particle system** is one unit with its own Sorting Layer and Order in Layer.
- **A Screen Space – Overlay canvas** draws after the scene and takes no part. Camera and World
  Space canvases sort with sprites by `Canvas.sortingLayerID` and `sortingOrder`.

Values and checks: [`reference/sort-order.md`](reference/sort-order.md).

## 5. The light does nothing

Three conditions, all required. First failure wins.

1. **The 2D Renderer is in force** — `renderer2DInForce` in the §0 report.
2. **The sprite's material is lit** — `lit` in the audit. `Sprite-Unlit-Default` and the
   Built-in `Sprites/Default` never react.
3. **The light targets the sprite's sorting layer.** A light targets the layers that existed
   when it was created; a layer added later is missing from lights in prefabs and unopened
   scenes.

And the inversion: **no `Light2D` at all means full colour; one `Light2D` means everything it
does not reach is black.** Make the first light in a scene a Global light on every layer.

Light types and defaults, blend styles, the cost per light, and why lights that skip a layer
in the middle of the stack multiply the light textures:
[`reference/lights-2d.md`](reference/lights-2d.md).

## 6. Shadows and normal maps

Each needs a setting on the light **and** a piece on the sprite.

- **Shadow:** the light has shadows enabled and is not Global; the object has a
  `ShadowCaster2D`; both target the layer the shadow falls on. `CastShadow` leaves the caster
  itself lit; `CastAndSelfShadow` darkens it. A Tilemap casts through its composite collider.
- **Normal map:** the sprite carries a secondary texture named `_NormalMap` — `unity-2d-sprites`
  → `reference/data-provider.md` — and the light's Normal Maps quality is `Fast` or
  `Accurate`. The default is `Disabled`, and the property is read-only from script.
- **Mask map:** `_MaskTex` on the sprite plus a blend style that reads a mask channel.

[`reference/shadows-and-normals.md`](reference/shadows-and-normals.md).

## 7. Masks, materials and batches

- A `SpriteMask` reaches only renderers whose `maskInteraction` is not `None` — the default is
  `None`. Narrow it with a custom range in sorting-layer and order units, or by placing it
  inside a `SortingGroup`.
- Tint with `SpriteRenderer.color`: it is vertex colour and keeps the batch. A
  `MaterialPropertyBlock` or `renderer.material` takes the renderer out of it.
- Two sprites batch only when consecutive in sorted order with the same material and texture.
  Y-sorted scenes interleave textures constantly; one atlas for the Y-sorted layer restores it.

[`reference/masks-and-materials.md`](reference/masks-and-materials.md).

## 8. Parallax

One factor per layer — `0` moves with the world, `1` is locked to the camera — applied
**after** the camera's final position for the frame. A layer placed before the camera trails
by a frame and shudders on every acceleration. `resources/ParallaxLayer.cs` runs after the
Cinemachine Brain, wraps endlessly for a runner, snaps to the pixel grid, and has `Snap()` for
cuts and respawns. Camera timing itself is `unity-camera` → `reference/update-order-and-jitter.md`.

[`reference/parallax.md`](reference/parallax.md).

## The tools

| File | Does |
|---|---|
| `resources/Editor/SortingAudit.cs` | Read-only. Every renderer's four keys, group, sort point, lit or unlit, and tied pairs, as JSON. `SortingAudit.Json()` |
| `resources/Editor/Renderer2DSetup.cs` | `Report()` the pipeline, renderers and sort axis. Creates a 2D Renderer or sets its axis after reporting the plan and waiting for confirmation |
| `resources/ParallaxLayer.cs` | One parallax layer: factor, wrap, pixel snap, `Snap()` |

Menu root: Tools → Unity Dev → 2D Rendering.

## Scope — what this skill does NOT do

Pixel-art filtering, the pixel-perfect camera and seams between tiles are
`unity-2d-pixel-perfect`. Post-processing Volumes, bloom on lit sprites and renderer features
are `unity-render-urp`; moving a Built-in project onto URP is `unity-urp-migration`. Sprite
pivots, slicing and secondary textures are `unity-2d-sprites`; packing is `unity-sprite-atlas`.
Tile palettes, their own sort setting and rule tiles are `unity-tilemap`; which Tilemap goes on
which sorting layer is `unity-2d-level` → `reference/layer-stack.md`. Skeletal sprite meshes
and bones are `unity-2d-animation`. Colliders, including the Tilemap collider a shadow caster
reads, are `unity-physics-2d`. Camera follow, confiners and shake are `unity-camera`. Draw
calls and frame time as numbers are `unity-profiling`.
