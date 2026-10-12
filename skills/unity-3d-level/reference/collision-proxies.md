# Collision proxies — the mesh you see is not the mesh you hit

> Part of the `unity-3d-level` skill. Why level collision is authored separately from the
> render mesh, which shape each piece gets, the `Collision` child that holds it, the layer
> scheme every query relies on, the few cases a `MeshCollider` is right, and what the NavMesh
> bake should collect. Worked setting: the **depot** kit in the gate room.

The render mesh is shaped for the eye: trims, bevels, bolts, a doorframe with a 3 cm lip. The
collision is shaped for a capsule sliding along it at 5 units a second. Use one mesh for both
and the runner snags on the lip, the camera boom jitters on the bolts, and every query pays for
triangles nobody can stand on.

## 1. Which shape

| The piece | Proxy | Note |
|---|---|---|
| Wall, floor, ceiling, crate, pillar | One `BoxCollider` | Flat faces flush with the greybox block it replaced |
| Door wall, window wall | Three boxes: two jambs and a lintel | The opening stays exactly the sheet's door — `reference/greybox.md` |
| Post, pipe, tree trunk, railing upright | `CapsuleCollider` along its length | A capsule against a capsule never snags |
| Stairs | **A ramp**: one box tilted to the stair's pitch | The runner glides instead of juddering up each riser; keep the pitch at or under the sheet's ramp angle |
| L, T and U shapes | Several boxes on the one `Collision` child | A compound of primitives is still cheaper and more predictable than a hull |
| An irregular solid: a boulder, a wrecked crate, a prop that can be pushed | Convex `MeshCollider` | PhysX builds a hull of at most 255 faces; concave detail is filled in |
| Large static ground that is not flat: a cave floor, a curved ramp, a sculpted road | Non-convex `MeshCollider` on a **collision mesh** authored for it | §3 |
| Trim, cables, signs, anything under 0.1 across or above head height | None | A collider nobody can reach is only cost |
| Hazard pad, spawn, sentry post | None on the solid layer | Gameplay volumes are triggers on their own layer |

When in doubt, the proxy is the greybox block the art replaced. The room was proven with those
shapes; the art has not changed where the runner can stand.

## 2. The `Collision` child

```
Kit_Depot_WallDoor_2x3        root, scale (1,1,1), no collider
├── Model                     MeshRenderer; layer Default; NO collider
└── Collision                 layer World; no renderer
    ├── (BoxCollider)         left jamb
    ├── (BoxCollider)         right jamb
    └── (BoxCollider)         lintel
```

- Axis-aligned primitives are components on `Collision` itself. A tilted or rotated one — the
  stair ramp — is a child of `Collision` with its own rotation, because a `BoxCollider` has a
  centre and a size and no rotation.
- `Collision` and everything under it keep scale `(1, 1, 1)`; size goes in the collider.
- Moving the root moves both children together. A piece that moves at runtime — the gate —
  carries a kinematic `Rigidbody` on the **root**, so its colliders are moved by the physics
  engine and not re-inserted every frame.
- The imported model keeps "Generate Colliders" off in its import settings. That option puts a
  `MeshCollider` on every mesh of the model.

`resources/Editor/CollisionProxyBuilder.cs` creates the child from the render meshes' bounds:

| Menu (`Tools/Unity Dev/3D Level/…`) | Adds |
|---|---|
| Add Box Proxy | One `BoxCollider` around all render meshes |
| Add Capsule Proxy | One `CapsuleCollider` along the longest axis, as wide as the wider of the other two |
| Add Convex Proxies | One convex `MeshCollider` per render mesh, each on a child that copies the mesh's pose |

Each command prints what it would add and waits. It never removes a collider that is already
there — the plan lists them, to be deleted once the proxy has been checked — and it refuses to
run without the `World` layer. Run it on the prefab, not on an instance in a scene: there the
child would be an added-object override (`reference/prefab-architecture.md` §3). A box from
bounds is a starting point; a door wall still needs splitting into three by hand.

```csharp
string plan = CollisionProxyBuilder.Plan(Selection.gameObjects, ProxyShape.Box);
GameObject child = CollisionProxyBuilder.Build(Selection.activeGameObject, ProxyShape.Box);
```

## 3. When a `MeshCollider` is right

Only for **static, large** geometry whose shape cannot be said in a few primitives, and then
on a mesh made for the job:

- Author a collision mesh beside the render mesh: the same silhouette at a tenth of the
  triangles, no bevels, no holes smaller than the capsule. Export it as its own object and
  assign it to the `MeshCollider` on the `Collision` child; it has no renderer.
- Non-convex is for things that never move. On a dynamic `Rigidbody` it is ignored, and two
  non-convex colliders never collide with each other.
- Convex is for things that move, and for cheap irregular statics.
- Keep it under 500 triangles per piece; `KitAudit` reports `dense-mesh-collider` above that.
- Check it in a player build, not only in the Editor: `unity-physics-3d` →
  `reference/editor-vs-build.md`.

The rest of the four silent rules of `MeshCollider` — contact on the hull, flipped normals —
are `unity-physics-3d` §5.

## 4. The layer scheme

One layer per *role in a query*, decided before the first room and never by default.

| Layer | Holds | Collides with |
|---|---|---|
| `World` | Every static solid: greybox blocks, `Collision` children, terrain | `Runner`, `Sentry`, `Prop` |
| `Runner` | The player's body | `World`, `Sentry`, `Prop`, `Trigger` |
| `Sentry` | Enemy bodies | `World`, `Runner`, `Prop` |
| `Prop` | Dynamic bodies: crates, pickups that can be knocked | `World`, `Runner`, `Sentry`, `Prop` |
| `Trigger` | Gameplay volumes: hazard pads, the switch's reach, room bounds | `Runner` only |
| Default | Render meshes with no collider | — |

Set the pairs in Project Settings ▸ Physics ▸ Layer Collision Matrix; untick everything not
in the table. Then every query names its layer:

| Query | Mask |
|---|---|
| Ground check, step and slope tests | `World` |
| Camera boom, line of sight, a sentry's vision ray | `World` |
| "Is there room to stand up / spawn here" | `World` + `Prop` |
| What the runner can use | The interactables' own layer, never `World` |
| `JourneyAsserts.NeverInside` | `World` |

```csharp
static readonly int World = LayerMask.GetMask("World");
bool blocked = Physics.Linecast(eye, target, World, QueryTriggerInteraction.Ignore);
```

A cast with no mask hits everything, including the caster's own collider and every trigger.
The symptoms and the probe for a query that misses are `unity-physics-3d` →
`reference/queries.md`.

## 5. What the NavMesh bake collects

The sentry must be able to walk exactly what the runner can stand on. So the bake reads the
same proxies:

```csharp
surface.useGeometry = NavMeshCollectGeometry.PhysicsColliders;   // not render meshes
surface.layerMask = LayerMask.GetMask("World");                  // not props, not triggers
surface.BuildNavMesh();
```

- Collected from **render meshes**, the NavMesh climbs onto trims, treats a table as floor and
  bakes a hole round every decorative crate.
- Collected from **colliders on `World`**, it is the greybox's walkable surface, from the day
  the greybox exists.
- A proxy that should block movement but not be walked on — a railing's top — takes a
  `NavMeshModifier` with `ignoreFromBuild`, or an area override.
- Re-bake after replacing blocks with proxies; a ramp proxy over stairs is what lets the bake
  climb them without a height mesh.

Voxel size, agent radius, runtime baking and links are `unity-navigation` →
`reference/recipes.md` §6–§7.

## 6. Verify it

1. **See it.** Window ▸ Analysis ▸ Physics Debugger draws every collider by type; a kit piece
   showing a dense mesh where a box should be is visible at a glance.
2. **Audit it.** `KitAudit.Audit(folder)` reports `missing-collider` and `dense-mesh-collider`
   per prefab — `reference/modular-kit.md` §7.
3. **Walk it.** Re-run the walk journey of `reference/greybox.md` §6 on the art-dressed room.
   The asserts do not change: arrival, never inside `World`, grounded on the ramp. A journey
   that passed on the greybox and fails on the art has found a proxy that differs from its block.
4. **Count it.** A room's collider count should fall, not rise, when art replaces greybox:
   one box per wall either way, and none on the dressing.

## Traps

- **"Generate Colliders" on the model import.** Every mesh of every piece gets a `MeshCollider`
  on the render layer. Turn it off; build proxies.
- **A collider on `Model` and another on `Collision`.** The runner collides with both; the
  render-mesh one snags. The builder's plan lists what is already there.
- **Proxies left on Default.** The ground check misses them, or the query mask is widened to
  Default and now hits the dressing too.
- **A stair proxy steeper than the slope limit.** The stairs look climbable and are a wall.
  Measure the pitch: `atan(rise / run)`, at or under the sheet's ramp row.
- **Scaling the `Collision` child to fit.** A sphere or capsule under non-uniform scale is not
  the shape drawn — `unity-physics-3d` §5. Set the collider's own size.
- **Moving a static collider every frame.** A gate that slides open by `transform.position`
  with no `Rigidbody` is re-inserted into the scene each frame and pushes nothing. Give the
  root a kinematic body and use `MovePosition`.
- **Proxies thinner than a fast body's step.** A 0.02 wall is tunnelled at speed —
  `unity-physics-3d` §2. Keep solid proxies at wall thickness, 0.2.

## Where each need is answered

| Need | Answer |
|---|---|
| The blocks the proxies replace; the layer the greybox uses | `reference/greybox.md` |
| The prefab shape the `Collision` child lives in | `reference/prefab-architecture.md` |
| Terrain's own collider, holes | `reference/terrain.md` |
| Callbacks that never fire, tunnelling, scaled colliders | `unity-physics-3d` |
| Casts, masks and triggers in a query | `unity-physics-3d` → `reference/queries.md` |
| The capsule that walks the proxies | `unity-3d-controller` → `reference/grounding-and-slopes.md` |
| Camera collision against `World` | `unity-camera` → `reference/follow-3d.md` |
| Bake settings, links, runtime baking | `unity-navigation` → `reference/recipes.md` |
| Colliders and hit boxes on a character rig | `unity-rigged-character` → `reference/gameplay-rig.md` |
| Occluders and static flags on the same pieces | `unity-scene-optimisation` → `reference/occlusion.md` |
