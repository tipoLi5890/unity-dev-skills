# Ladder steps 5–7: shapes, one-way platforms, editor versus build

Moved out of SKILL.md, which keeps steps 0–4 of the triage ladder; numbering continues it. First match wins here too.

## 5. Shapes that are not what they look like

- **Adding a `CompositeCollider2D` adds a `Rigidbody2D`, and it is Dynamic.** The level falls on
  Play. Set the body to `Static`.
- **A child joins the composite only with `compositeOperation` set** — `Merge` for level
  geometry; `usedByComposite` is the deprecated spelling. At `None` the seams stay.
- **`GeometryType.Outlines` is edges: no interior.** A body teleported inside is not pushed out,
  `OverlapPoint` inside finds nothing, and two outline composites never collide with each other.
  `Polygons` is solid and costs more shapes. Static level: `Outlines`. Anything that moves, or
  must answer "is this point inside": `Polygons`.
- **A `TilemapCollider2D` alone is one shape per tile.** A box sliding over the row catches the
  shared corner of two neighbours and stops dead on flat ground — the ghost-vertex snag. Merge
  into a composite; an `EdgeCollider2D` has `useAdjacentStartPoint` / `useAdjacentEndPoint` for
  the same reason.
- **`Collider2D.errorState` names a collider with no shapes**: `NoShapes` or `RemovedShapes`
  when the geometry is too small or its vertices too close. The inspector shows nothing. A body
  rotated about X or Y flattens its shapes the same way.
- **A `PolygonCollider2D` copies the sprite's physics outline once, when it is added** —
  `unity-2d-sprites` → `reference/sprite-geometry.md`.

Tile collider types, composite set-up, runtime `SetTile` and one-way tiles:
[`reference/tilemap-colliders.md`](tilemap-colliders.md).

## 6. Effectors and one-way platforms

1. **The collider must set `usedByEffector`**, or the `PlatformEffector2D` beside it does
   nothing. Under a composite the flag belongs on the `CompositeCollider2D`.
2. **`useOneWay` is on and `surfaceArc` is narrower than 180**: about `170`. At 180 the side
   faces count as top and the runner hangs on the platform's edge.
3. **The pass direction is the effector's local up** plus `rotationalOffset`: a platform rotated
   180° passes the wrong way.
4. **`useColliderMask` replaces the layer matrix for this collider**: a layer missing from the
   effector's `colliderMask` falls through.
5. **A runner made of two colliders is held half way** until `useOneWayGrouping` is on.
6. **Dropping through is a per-pair ignore**: `Physics2D.IgnoreCollision(runner, platform)` for
   0.25 s, then restore. Disabling the platform drops every sentry standing on it.

Area, point and buoyancy effectors want a trigger collider; a surface effector a solid one.
Effectors and the five joints worth knowing:
[`reference/effectors-and-joints.md`](effectors-and-joints.md).

## 7. Editor yes, build no

- **`SimulationMode2D.Update` ties the step to the frame rate**, and so do forces written in
  `Update`: the Editor at 300 fps and a phone at 60 integrate different jumps. Keep `FixedUpdate`
  and set `Fixed Timestep` on purpose.
- **A layer name resolving to `-1` is a layer that is not defined**, in the Editor too:
  `LayerMask.GetMask` returns 0 for it and that filter finds nothing. Assert at startup.
- **IL2CPP stripped a MonoBehaviour that is only added from code** — `[Preserve]` or `link.xml`,
  `unity-android-release` → `reference/size-and-stripping.md`.
- **`Physics2D.IgnoreCollision` binds two collider instances.** A pooled bullet still ignores the
  shooter that first fired it; set it on use and clear it on return.
  `Physics2D.IgnoreLayerCollision` is global until changed back; that rule belongs in the matrix:
  [`reference/layers-and-matrix.md`](layers-and-matrix.md).
