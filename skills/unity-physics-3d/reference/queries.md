# Raycasts and queries: the rules behind §3, in full

Part of the `unity-physics-3d` skill. SKILL.md §3 states each rule in a line; this file holds it in
full, with the values and the A/B probe.

- **Outside play mode a query needs a sync first.** `Physics.autoSyncTransforms` is **`false`** by
  default, so a collider created or moved this frame is not yet where PhysX believes it is and
  every ray against it returns `false` — which reads as a broken collider. One call before the
  first query is the whole fix:

  ```csharp
  // without the sync, every one of these returns false
  UnityEngine.Physics.SyncTransforms();
  UnityEngine.Physics.Raycast(origin, dir, out hit, 100f);
  ```
- **Origin inside the target collider returns false** (backface culling).
  **`Queries Hit Backfaces` only rescues a `MeshCollider`.** From inside a `BoxCollider`,
  the raycast stays `false` whether the flag is on or off; from inside a non-convex `MeshCollider`
  it flips `false → true`. For a primitive collider the only fix is to move the origin outside the
  bounds.
- **Triggers are hit by default, not ignored.** `Physics.queriesHitTriggers` is **`true`**,
  and the default `QueryTriggerInteraction.UseGlobal` defers to it — so an unqualified
  `Physics.Raycast` **does** hit a trigger. A project can flip that global, which is why the
  reliable move is to **pass the flag explicitly** (`Ignore` or `Collide`) rather than rely on
  either default. Against a trigger: `UseGlobal → true`, `Ignore → false`, `Collide → true`.
- **`maxDistance` defaults to infinity but the layer mask does not default to everything** if you
  passed one — check the mask you passed is the mask you meant.
- **Prove a suspected mask miss with an A/B, not by reading the mask.** Fire the same ray twice:
  once with `Physics.DefaultRaycastLayers`, once with `LayerMask.GetMask("TheLayer")`. Hit on the
  first and miss on the second means the layer is not in the production mask. `DefaultRaycastLayers`
  is **not** everything, which is the trap in that probe — it is `-5`, every layer
  *except* layer 2, `Ignore Raycast`, while `Physics.AllLayers` is `-1`. A target parked on
  `Ignore Raycast` therefore misses the "hit everything" half too, which reads as a broken ray path
  rather than the layer choice it is; `Physics.AllLayers` is the mask that really includes it.
- **A disabled `Collider` or an inactive GameObject is invisible to a query as well**, with the same
  silence as SKILL.md §1 step 2 — the call just returns `false`. `Physics.OverlapSphere` (three
  overloads) is the cheap way to ask what PhysX actually has at a position: an empty result
  says the collider is not in the scene at all, a non-empty one moves the fault to the ray, the mask
  or the origin. It is also how you find the collider that is enclosing an origin, per the backface
  rule above.
- **`GraphicRaycaster` and `Physics.Raycast` search disjoint worlds.** A `GraphicRaycaster` walks
  its `Canvas` and returns UI `Graphic`s; `Physics.Raycast` queries the PhysX scene and returns
  `Collider`s. Neither ever finds the other's objects, so "the click does nothing" splits on which
  of the two the code called — and a **World Space** Canvas does not blur the line, it is still UI
  and still reached through the EventSystem (`unity-ui-ugui`).
  `UnityEngine.UI.GraphicRaycaster` derives from `UnityEngine.EventSystems.BaseRaycaster`, with
  nothing from the physics module in its ancestry. To hit a world collider from a screen point, the
  call is `Physics.Raycast(Camera.main.ScreenPointToRay(screenPos), out hit)`.
- **Queries keep answering while the game is frozen.** `Raycast` and `OverlapSphere` read collider
  geometry directly, so they are unaffected by `Time.timeScale == 0` — which makes them the tell
  for it: rays hit, nothing moves, and the physics setup is innocent.
- **A projectile is better swept than stepped.** `Physics.SphereCast` along the frame's trajectory,
  taking the first hit, removes tunnelling entirely and does not care what the physics step is —
  where a projectile "fixed" by halving the timestep is still tunnelling, just at a higher speed.
  The cast is a query, so it also answers outside play mode once transforms are synced.
- **After writing `transform.position`, the same frame's queries still see the old position** until
  `Physics.SyncTransforms()`. Call it once, deliberately — **never every frame**. A physics-driven
  object should be using `Rigidbody.MovePosition` instead.
