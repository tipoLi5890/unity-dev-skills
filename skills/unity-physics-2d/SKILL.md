---
name: unity-physics-2d
description: >-
  Diagnose 2D physics in Unity when Box2D disagrees with what the scene looks
  like: a symptom-routed triage ladder in Box2D's own vocabulary, a two-sided
  debug probe and a read-only scene audit. Load for: "OnCollisionEnter2D never
  fires", "OnTriggerEnter2D never fires", "the bullet goes through the tilemap
  wall", "the ground check hits the player itself", "the character snags on
  tile edges", "the one-way platform blocks from below", "OnTriggerStay2D
  stops after a moment", a Rigidbody2D that jitters, or a tilemap that falls
  when a composite collider is added. The player's own movement code is
  unity-2d-controller; a tile's collider type is unity-tilemap; PhysX is
  unity-physics-3d.
---

# unity-physics-2d — Box2D answers in its own vocabulary

> **A PhysX rule renamed with a 2D suffix is usually wrong.** A kinematic `Rigidbody2D` moves
> under its velocity, a ray that starts inside a collider hits it, sleep is a timer, there are two
> collision-detection modes, and Z separates nothing. Almost nothing here throws. Work the
> ladder; do not translate what the 3D engine would do.

## Symptom → where to look

First match wins. **Stop at the first cause you confirm** and write the diagnosis.

| Symptom | Go to |
|---|---|
| `OnCollisionEnter2D` / `OnTriggerEnter2D` never fires | §1 |
| A kinematic sentry walks through walls and reports nothing | §1 — full kinematic contacts |
| A bullet or a fast runner passes through a wall | §2 |
| A fast body skips a pickup or a hazard trigger | §2 — triggers are not swept |
| A ground check reports the caster itself, or a cast misses what is in its path | §3 |
| A click through the camera finds no 2D collider | §3 — a 3D ray against 2D shapes |
| `OnTriggerStay2D` / `OnCollisionStay2D` ran, then went quiet | §4 — the body fell asleep |
| The runner stutters while the camera follows | §4 |
| The tilemap falls out of the scene on Play | §5 — the composite's body |
| The runner snags on flat ground or on tile seams | §5 |
| A body ends up inside a wall and stays there | §5 — outlines are hollow |
| The one-way platform blocks from below, or grips at the sides | §6 |
| Works in the editor, not in the build | §7 |
| Collisions changed after a respawn or a return to the pool | §7 — per-instance ignore pairs |

## 0. Before diagnosing

Connect to the Editor rather than reading files — `unity-debug` → `reference/editor-control.md`.

- **Name the stack.** `Rigidbody2D`, `Collider2D`, `Physics2D` and messages ending in `2D` are
  this ladder; `Rigidbody` and `Physics` are `unity-physics-3d`; `UnityEngine.LowLevelPhysics2D`
  (`PhysicsWorld`, `PhysicsBody`) is a third vocabulary. The stacks never see each other, and a
  message from the wrong one is silent.
- **Two matrices.** `Project Settings → Physics 2D → Layer Collision Matrix` is not the 3D one.
- **Read `Physics2D.simulationMode`.** In `SimulationMode2D.Script` nothing moves until code calls
  `Physics2D.Simulate`; a test that set it and never restored it freezes every later scene.
- **A query sees the pose of the last step.** After writing a Transform, call
  `Physics2D.SyncTransforms()` once before querying. `Physics2D.autoSyncTransforms` is deprecated.
- **Never judge callbacks from `Physics2D.Simulate()` outside play mode**: scripts without
  `[ExecuteAlways]` receive no messages. Queries do work there, after a sync.
- **Restore any Project Setting you change**, and answer with what the ladder confirmed — or the
  most likely cause, labelled unconfirmed, with the one check that would settle it.

Body types, the step and `Physics2D.Simulate`:
[`reference/bodies-and-simulation.md`](reference/bodies-and-simulation.md).

## 1. No callback fires

Work down. First match wins.

1. **One of the pair needs a `Rigidbody2D` that is not `Static`.** A collider with no body is on
   the hidden static body; static × static never makes a contact.
2. **`Rigidbody2D.simulated == false` removes the body, its colliders and its joints**: no
   callbacks, no query hits, and the inspector looks right. So does a disabled collider, an
   inactive parent, or a layer missing from `Physics2D.simulationLayers`.
3. **Kinematic × Kinematic and Kinematic × Static make no collision contact** until the kinematic
   body sets `useFullKinematicContacts = true`. With it the body gets `OnCollisionEnter2D` and
   contact points and is still not pushed.
4. **Trigger versus collision.** If either collider `isTrigger`, the pair gets `OnTrigger*2D` and
   never `OnCollision*2D`.
5. **The layer pair.** `a.CanContact(b)` answers for the matrix and every layer override at once;
   `Physics2D.GetIgnoreCollision(a, b)` for a per-instance ignore. Contact with no message is
   `Collider2D.callbackLayers`.
6. **The script sits on the collider's GameObject or the `Rigidbody2D`'s**, with the exact
   signature: `OnCollisionEnter2D(Collision2D)`, `OnTriggerEnter2D(Collider2D)`.
7. **A child merged into a `CompositeCollider2D` loses its own `isTrigger` and material**; the
   composite's apply.

| Pair | `OnCollisionEnter2D` (no trigger) | `OnTriggerEnter2D` (a trigger in the pair) |
|---|---|---|
| Dynamic × anything | Yes | Yes |
| Kinematic × Kinematic or Static | Only with `useFullKinematicContacts` | Yes |
| Static × Static, or no body on either side | Never | Never |

Layer schemes, overrides and the ignore calls:
[`reference/layers-and-matrix.md`](reference/layers-and-matrix.md).

## 2. Tunnelling

| `Rigidbody2D.collisionDetectionMode` | Sweeps against |
|---|---|
| `CollisionDetectionMode2D.Discrete` | Nothing — the body is tested where each step lands |
| `CollisionDetectionMode2D.Continuous` | Every non-trigger collider in its path |

Two modes, not four. With no speculative mode, a hit reported before two shapes touch is a
collider larger than its sprite.

- **Set `Continuous` on the fast body**, not on the wall; reserve it for the runner and for
  projectiles.
- **`Continuous` does nothing for a Kinematic body and nothing for triggers.** At 40 units/s a
  body covers 0.8 units per 0.02 s step and steps over a thinner pickup trigger.
- **The fix that always holds is a cast.** Sweep the step's movement with `Physics2D.CircleCast`
  or `Rigidbody2D.Cast` and stop at the first hit:
  [`reference/queries-2d.md`](reference/queries-2d.md).

## 3. A cast or overlap misses, or hits itself

- **A ray that starts inside a collider hits that collider** at `fraction` 0 with the normal
  pointing back along the ray: `Physics2D.queriesStartInColliders` is `true`. A ground ray from
  the runner's centre returns the runner. Use `Collider2D.Cast` or `Rigidbody2D.Cast`, which
  ignore the caster, or mask its layer out. Leave the global alone.
- **A shape cast that starts overlapping reports it at distance 0**, with a normal that
  describes no surface; with the global off it skips that collider, as a ray does.
- **Triggers are hit by default — by the overloads that take a layer mask.**
  `Physics2D.queriesHitTriggers` is `true`, but an overload taking a `ContactFilter2D` also
  needs `filter.useTriggers`, which is `false` in `new ContactFilter2D()`: one overload finds
  the pickup, the other does not.
- **The Z range.** `minDepth` / `maxDepth` compare the collider's Transform Z. Collisions ignore
  Z, so a wall at Z 5 stops the runner and a depth-filtered cast misses it.
- **A camera ray is 3D.** `Physics2D.GetRayIntersection(ray)` takes it; under an orthographic
  camera `Physics2D.OverlapPoint(camera.ScreenToWorldPoint(p))` is enough.
- **One-way platforms do not exist for queries.** A ground cast from below a platform hits it;
  the caller filters by normal and height.

Every query, the list overloads, the filter fields and the start-inside table:
[`reference/queries-2d.md`](reference/queries-2d.md).

## 4. It moved, then it stopped — or it jitters

- **Sleep is a timer.** A body slower than `Physics2D.linearSleepTolerance` (`0.01`) for
  `Physics2D.timeToSleep` (`0.5` s) sleeps, and `OnCollisionStay2D` / `OnTriggerStay2D` stop. For
  a zone that must tick while something rests in it, set `sleepMode =
  RigidbodySleepMode2D.NeverSleep` on the one body, or count `Enter` and `Exit`. `AddForce` wakes
  a sleeping body: a force that seems swallowed is too small, on a Kinematic body or a frozen axis.
- **A Kinematic `Rigidbody2D` moves under `linearVelocity`.** Gravity and forces are ignored;
  velocity is not. A sentry that drifts after its patrol still has one.
- **`MovePosition` is one step of velocity, a position write is a teleport.** `MovePosition`
  travels during the next step: a rider is carried, and a Dynamic body stops at a wall as §2
  allows. `Rigidbody2D.position` and `transform.position` jump, with no velocity for a rider to
  inherit. Move platforms and sentries as Kinematic bodies, in `FixedUpdate`.
- **A moving collider with no `Rigidbody2D` is rebuilt on the static body at every move** and
  carries nothing: the rider is left behind. Give it a Kinematic body.
- **Jitter is two clocks.** The step runs at `Time.fixedDeltaTime` (`0.02`), the frame does not.
  Set `interpolation = RigidbodyInterpolation2D.Interpolate` on any body the camera follows and
  put the camera on one clock — `unity-camera` → `reference/update-order-and-jitter.md`. An
  Animator or a script writing the body's own Transform each frame fights the step: animate a
  child that holds the sprite.
- **`Time.timeScale == 0`** stops the step; queries keep answering.

Each of these in full, with `Rigidbody2D.Slide`:
[`reference/bodies-and-simulation.md`](reference/bodies-and-simulation.md).

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
[`reference/tilemap-colliders.md`](reference/tilemap-colliders.md).

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
[`reference/effectors-and-joints.md`](reference/effectors-and-joints.md).

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
  [`reference/layers-and-matrix.md`](reference/layers-and-matrix.md).

## The probe

`resources/CollisionDebugger2D.cs` — attach to **both** suspected objects, drag each one's
collider into the other's `other` field, read the console, remove it when done.

| Console | Diagnosis |
|---|---|
| Neither object logs `[Setup]` | The script is not on the objects you think it is |
| `[Setup]` reports `collider none`, `enabled False`, `simulated False` or `shapes 0` | §1 step 2, §5 |
| `[Pair]` reports `canContact False` or `ignored True` | §1 step 5 |
| `[Setup]` from both, `[Pair]` clean, no `[Collision]` / `[Trigger]` | §1 steps 1, 3, 4 |
| `[3D Collision]` appears | 3D components in a 2D scene |

`resources/Editor/Physics2DAudit.cs` reads the open scene, changes nothing and prints one JSON
object — `Tools/Unity Dev/Physics 2D/Audit Open Scene`, or `Physics2DAudit.Audit()` from an eval.
It lists colliders that move with no body, layers that touch nothing, unmerged composite
children, triggers with no body, tilemap colliders with no composite and colliders with no shapes.

## Scope — what this skill does NOT do

The player's own movement — ground check design, slopes, jump numbers, top-down and grid
motors — is `unity-2d-controller`. Painting tiles and a tile's collider type are
`unity-tilemap`; level layout and runtime tile data are `unity-2d-level`; cell occupancy and grid
pathfinding are `unity-2d-grid`. Sprite physics outlines are `unity-2d-sprites`; draw order is
`unity-2d-rendering`. A camera that stutters is `unity-camera`; pixel snapping is
`unity-2d-pixel-perfect`. Asserting that a recorded run never entered geometry is
`unity-play-harness`. PhysX — `Rigidbody`, `Physics.Raycast`, `CharacterController` — is
`unity-physics-3d`. Hit and hurt layers are `unity-combat`; pickup and switch triggers are
`unity-interaction`.
