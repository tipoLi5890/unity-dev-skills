# Sort order — the four keys, in full

> Part of the `unity-2d-rendering` skill. `SKILL.md` §1 states the rule in a table; this file
> holds each key with its values, what a `SortingGroup` isolates, where the sort axis lives in
> each pipeline, how a Tilemap, a particle system and a Canvas take part, and how to read the
> order off a real frame instead of reasoning about it.

## The comparison

Two renderers that overlap on screen are compared key by key. The first key that differs
decides; later keys are never consulted.

| # | Key | Where it is set | Script |
|---|---|---|---|
| 1 | Sorting layer | The renderer's Sorting Layer; order comes from the list in Project Settings → Tags and Layers, top of the list draws first | `Renderer.sortingLayerID`, `sortingLayerName` |
| 2 | Order in Layer | The renderer; higher draws later, so on top. Range −32768 to 32767 | `Renderer.sortingOrder` |
| 3 | Render queue | The material; higher draws later. Both sprite shaders sit at `Transparent` (3000) | `Material.renderQueue` |
| 4 | Distance along the sort axis | The renderer's sort point, measured the way the sort mode says; further draws first | — |

Two renderers equal on all four have **no defined order**. Nothing breaks the tie: not
hierarchy order, not creation order, not name. The pair can swap when a third object enters the
view or a batch is rebuilt, which is the flicker people describe as "z-fighting" in a 2D scene.
`resources/Editor/SortingAudit.cs` lists every such pair.

World z appears in exactly one place: key 4, and only while the sort mode measures along the
camera's forward axis. Moving a sprite in z cannot beat an Order in Layer, and under a custom
axis of `(0, 1, 0)` it does nothing at all.

### Key 1 — compare layer values, not ids

`SortingLayer.id` is a unique identifier and carries no order; two ids must not be compared.
The order is `SortingLayer.value`, or from an id:

```csharp
int a = SortingLayer.GetLayerValueFromID(runner.sortingLayerID);
int b = SortingLayer.GetLayerValueFromID(gate.sortingLayerID);   // lower draws first
```

`SortingLayer.NameToID` returns `0` — the Default layer — for a name that does not exist, so a
misspelt `sortingLayerName` puts the renderer on Default without an error. Read the name back
after assigning it.

### Key 4 — the sort point and the sort mode

The sort mode decides how distance is measured:

| `TransparencySortMode` | Distance |
|---|---|
| `Default` | `Orthographic` under an orthographic camera, `Perspective` under a perspective one |
| `Orthographic` | Depth along the camera's forward axis — world z for a 2D camera |
| `Perspective` | Straight-line distance from the camera position |
| `CustomAxis` | Position projected onto the axis; a larger projection is further back |

The sort point decides which position is measured. `SpriteRenderer.spriteSortPoint` is
`Center` by default — the centre of the sprite's bounds — and `Pivot` uses the sprite's pivot.
Every other renderer type has no such setting and is measured at its bounds centre. For
anything sorted by y, `Center` is wrong for every sprite taller than its neighbour:
`reference/y-sort.md`.

## Where the sort axis lives

Three places can hold a sort mode and axis, and each pipeline reads exactly one of them.

| Pipeline in force | Read from | Set it |
|---|---|---|
| URP, 2D Renderer | The 2D Renderer Data asset: Transparency Sort Mode, Transparency Sort Axis | Inspector, or `resources/Editor/Renderer2DSetup.cs` — the two fields have no public setter |
| Built-in | The camera: `Camera.transparencySortMode`, `transparencySortAxis`, seeded from Project Settings → Graphics → Camera Settings | Inspector, or `GraphicsSettings.transparencySortMode` / `transparencySortAxis` |
| URP, Universal Renderer | The camera's own pair | `Camera.transparencySortMode` and `transparencySortAxis` from script |

The 2D Renderer writes its asset's mode and axis into every draw pass, replacing whatever the
camera carries. A project that sets the axis under Project Settings → Graphics and then moves
to the 2D Renderer keeps a setting that nothing reads: the scene sorts by z again until the
axis is entered on the renderer asset. `Renderer2DSetup.Report()` prints all three places.

The other pipeline difference is key 3. The 2D Renderer draws each batch of sorting layers as
one back-to-front list across every render queue, so an opaque-queue material obeys Order in
Layer like a sprite. The Built-in pipeline and the Universal Renderer draw the opaque queues
(2500 and below) in an earlier pass with depth writing on: a `MeshRenderer` with an opaque
material there ignores keys 1 and 2 against sprites and hides them wherever it is nearer in z.
Give it a transparent-queue material, or accept that z is the control for that one object.

A material that writes depth changes the picture in any pipeline. `Sprite-Lit-Default` and
`Sprite-Unlit-Default` expose a ZWrite toggle that is off by default; with it on, a sprite
drawn earlier can still cut a hole in a later one that is further away in z.

## SortingGroup — one unit outside, its own order inside

A `SortingGroup` on a root makes the root and every renderer below it sort as **one unit**
against everything outside:

- Outside, the unit uses the group's own Sorting Layer and Order in Layer, and the group
  root's position for key 4. The children's own layers and orders are invisible from outside.
- Inside, the children are ordered among themselves by their own four keys.
- Nothing from outside can be drawn between two members. A pickup can never appear between
  the runner's body and the runner's satchel once both are in the runner's group.
- Groups nest. `SortingGroup.sortAtRoot` takes a nested group out of its parent and sorts it
  at the top level.

What it costs: the group cannot share a batch with sprites outside it that would otherwise have
been drawn in the middle of it, and a child cannot be lifted over an outside object by raising
its own Order in Layer — raise the group's. After changing group properties from script and
reading the order in the same frame, call `SortingGroup.UpdateAllSortingGroups()`.

Check which position the unit sorts at before relying on it: put the group root at the
character's feet, walk the character past a crate, and read the frame. If the swap happens at
the wrong moment the root is not where the feet are.

## Tilemap, particles and UI in the same order

**TilemapRenderer.** The renderer as a whole has a Sorting Layer and Order in Layer. What its
tiles do under key 4 depends on `TilemapRenderer.mode`:

| `Mode` | Tiles sort | Use for |
|---|---|---|
| `Chunk` | As chunks of the map. Another renderer is in front of a chunk or behind it, never between two of its tiles | Floors, backgrounds, anything nothing walks behind |
| `Individual` | Each tile separately, at its own position, against every other renderer on the same layer and order | Tall tiles the runner walks behind; isometric and hex boards with pieces on them |
| `SRPBatch` | In chunks the SRP Batcher can batch | A large flat map on a scriptable pipeline |

`TilemapRenderer.sortOrder` (`BottomLeft`, `BottomRight`, `TopLeft`, `TopRight`) is the
corner the renderer starts from when it orders its own tiles. For tiles that overlap the row
above them, start from a top corner so lower rows draw later. `Individual` gives up chunk
batching: keep it for the one Tilemap that needs it and leave the floor on `Chunk`.

After switching mode, put the runner half a cell behind a tall tile and read the frame — the
tile's sort position follows its sprite's pivot and the Tilemap's Tile Anchor, and a pivot at
the tile centre swaps half a cell late.

**ParticleSystemRenderer.** One system is one unit with a Sorting Layer and Order in Layer.
`sortMode` orders the particles inside it; `sortingFudge` biases the whole system's key 4,
lower values drawing it later. Prefer an explicit Order in Layer to a fudge value.

**Canvas.** A Screen Space – Overlay canvas is drawn after the whole scene and takes no part.
Screen Space – Camera and World Space canvases have `Canvas.sortingLayerID` and `sortingOrder`
and sort with the sprites; a Screen Space – Camera canvas sits at `planeDistance` for key 4.
A nested canvas keeps its parent's order until `overrideSorting` is on.

## Reading the order off a frame

Reason from the frame, not from the inspector.

1. **Frame Debugger** — Window → Analysis → Frame Debugger, Enable in play mode. Step through
   the draw events: a later event draws on top of an earlier one. Under the 2D Renderer the
   events are grouped by batches of sorting layers. Select the two renderers in question and
   note which event each belongs to; if they share one event they are batched and the order
   inside it is the order of the batch's quads.
2. **`resources/Editor/SortingAudit.cs`** — `SortingAudit.Json()` or Tools → Unity Dev → 2D Rendering →
   Audit Sorting. One JSON object:

   ```json
   {"pipeline":"Assets/Settings/UniversalRP.asset","rendererType":"Renderer2DData",
    "is2DRenderer":true,"sortMode":"CustomAxis","sortAxis":[0,1,0],"sortSource":"Renderer2DData",
    "renderers":[{"path":"Depot/Runner/Body","layer":"Actors","layerValue":2,"order":0,
                  "queue":3000,"distance":-1.5,"sortPoint":"GroupRoot","group":"Depot/Runner",
                  "lit":"lit"}],
    "ties":[{"a":"Depot/Pickup (3)","b":"Depot/Pickup (4)","layerValue":2,"order":0,"distance":-2}],
    "warnings":[]}
   ```

   Read `sortSource` first: it names the place the axis was taken from. Then find the two
   renderers and compare `layerValue`, `order`, `queue`, `distance` in that order — the first
   difference is the reason. An entry in `ties` is a pair whose bounds overlap and whose four
   keys are equal; each one is a flicker waiting for the right frame.

The audit measures a `SortingGroup` at its root and a Tilemap at its bounds centre, and assumes
a camera looking along +z. For a pair the audit and the frame disagree on, the frame wins.

## Fixes, by the key that decided

| The audit shows | Fix |
|---|---|
| Different `layerValue` | Move one renderer to the other's layer, or reorder the layer list. Do not reach for z |
| Same layer, different `order` | Set the order you meant. A character built from parts needs a `SortingGroup`, not a wider spread of orders |
| Different `queue` | Two materials with different queues on one layer: align the queues unless the difference is deliberate |
| Only `distance` differs, wrong way round | The sort point (`Center` where `Pivot` was meant), the pivot itself, or the axis: `reference/y-sort.md` |
| A tie | Give one of the pair a different Order in Layer, or a position that differs along the axis |
