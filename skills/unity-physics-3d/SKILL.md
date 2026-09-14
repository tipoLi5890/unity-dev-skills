---
name: unity-physics-3d
description: >-
  Diagnose 3D PhysX collisions and triggers in Unity when the physics
  disagrees with what the scene looks like: a symptom-routed triage ladder
  plus a two-sided debug probe, first match wins, and the answer is a
  diagnosis. Load for: "OnCollisionEnter never fires", "OnTriggerEnter never
  fires", objects passing through each other at speed, a raycast that misses
  something in front of it, a ragdoll that explodes on activation, AddForce
  doing nothing after the body has come to rest, colliders the wrong shape
  after import, or "it collides in the editor and not in the build".
  Pathfinding is unity-navigation; 2D physics and DOTS Physics get an answer
  in their own vocabulary, never a PhysX rule.
---

# unity-physics-3d — a triage ladder, not a list of things to try

> **Your prior knowledge about PhysX callbacks is unreliable, and the errors are silent.**
> Almost nothing in this domain throws. A collider that will never collide looks identical in the
> inspector to one that will. Work the ladder; do not reason from what "should" happen.

## Symptom → where to look

First match wins. **Stop at the first cause you confirm** — do not run the whole ladder. A matched
row is the answer, not a lead: write the diagnosis and stop calling tools.

| Symptom | Go to |
|---|---|
| `OnCollisionEnter` / `OnTriggerEnter` never fires | §1 |
| Fast object passes through a wall | §2 |
| A hit is reported before the two objects visibly touch | §2 — speculative contacts |
| `Physics.Raycast` misses something clearly in front of it | §3 |
| A click finds no UI, or a world ray keeps hitting the HUD | §3 — two raycasters, two worlds |
| `AddForce` seems to stop working once the object settles | §4 — and it is **not** the sleep state |
| `OnTriggerStay` / `OnCollisionStay` ran for a while, then went quiet | §4 — the body fell asleep |
| Everything frozen but raycasts still hit | §4 |
| Ragdoll explodes on the first frame | §5 |
| Collider is the wrong shape / imported geometry does not collide | §5 |
| Objects come to rest with a visible gap between them | §5 — contact offset |
| Things pass out through a concave mesh they should sit inside | §5 — inverted normals |
| Works in the editor, not in the build | §6 |
| Collisions stopped after a respawn or a return to the pool | §6 — per-instance ignore pairs |

## 0. Before diagnosing

Connect to the Editor rather than reading files — `unity-debug` → `reference/editor-control.md`.
Three rules specific to physics, then two about how the turn ends:

- **Never verify with `Physics.Simulate()` outside play mode.** Editor-mode simulation does not
  dispatch MonoBehaviour callbacks, so a working setup reports as broken. It is a guaranteed false
  negative and it will send you down the wrong branch.
- **Geometry queries DO work outside play mode — but only after a sync.** `Physics.autoSyncTransforms`
  is **`false`** by default, so a collider you just created or moved is not where PhysX thinks it
  is, and every raycast against it returns false. Call `Physics.SyncTransforms()` once before
  querying, or you will diagnose a perfectly good collider as broken — the call, and where it
  goes: [`reference/queries.md`](reference/queries.md).
- **Record the original value of any Project Setting you change** (Queries Hit Triggers, the
  Layer Collision Matrix, Contact Offset) and restore it. A diagnosis that leaves the project
  altered is not a diagnosis.
- **Five tool calls, then answer.** After five of any kind, stop calling and write the most likely
  diagnosis off the ladder, labelled unconfirmed, with the one check that would settle it. Tool
  output alone is the one outcome worth nothing, however much of it there is.
- **Never close by asking permission.** "Would you like me to proceed?", "Should I continue?",
  "Do you want me to investigate further?", "I will do X — continue?" are one move, and it costs a
  round trip to say nothing. Make the change yourself where you can reach it — a script, or the
  live scene over an Editor connection — otherwise hand over an explanation complete enough to
  apply without you. Ask only for information you cannot get yourself, and name it.

## 1. No callback fires

Work down. First match wins.

1. **At least one of the pair needs a `Rigidbody`.** Two static colliders never generate contacts.
2. **An unticked `Collider` and an inactive GameObject are both completely silent.** No warning,
   no error: the object is simply not in the physics scene, and the inspector looks correct
   because the checkbox is the only difference. Check `Collider.enabled` *and*
   `gameObject.activeInHierarchy` — `Collider` declares its own `enabled` rather than inheriting
   one from `Behaviour`, and `activeInHierarchy` is read-only, so a parent
   switched off two levels up reads as the child's own fault. This is the cheapest step on the
   ladder and the one most often skipped.
3. **Layer Collision Matrix** — `Project Settings → Physics`. An unchecked pair is silent.
4. **Trigger vs collision.** If either collider `isTrigger`, you get `OnTrigger*` and **never**
   `OnCollision*`.
5. **`OnCollision*` and `OnTrigger*` must be on a GameObject that has a collider** — not on a
   parent that merely contains one.
6. **`CharacterController` never raises `OnCollisionEnter`** → `OnControllerColliderHit`. Do not
   add a `Rigidbody` to "fix" it; the two movement models are mutually exclusive.
7. **A 3D scene with `OnCollisionEnter2D`** in it. `resources/CollisionDebugger.cs` catches this
   specifically.

> **Two kinematic triggers DO fire `OnTriggerEnter`.** The Trigger matrix is not the Collision
> matrix. Kinematic × kinematic produces no `OnCollisionEnter`, which is where the belief comes
> from — but kinematic-trigger × kinematic-trigger produces `OnTriggerEnter` normally.

> **A kinematic body must be moved with `MovePosition()` or by writing `transform.position`.**
> Assigning velocity is ignored without warning, the body does not move, and the broadphase
> never updates — which then reads as "collisions stopped working".

> **In Unity 6 the property is `Rigidbody.linearVelocity`.** `velocity` still exists (both are
> present and read-write), so old code compiles — but new code and anything you paste
> from a Unity 6 sample will use `linearVelocity`, and mixing the two in one file reads as a
> bug that is not there.

## 2. Tunnelling

| `collisionDetectionMode` | Sweeps against |
|---|---|
| `Discrete` | Nothing — default; fast objects pass through |
| `Continuous` | **Static colliders only** — silently falls back to Discrete against dynamic bodies |
| `Continuous Dynamic` | Static + other Continuous Dynamic bodies (expensive) |
| `Continuous Speculative` | Everything, cheaper than CCD, occasional ghost contact |

Choose by what the fast thing hits, not by how fast it is.

- **Against static geometry** — thin floors, walls, terrain — `Continuous Speculative` is the
  one to reach for. `Continuous` is also correct there, but it degrades to `Discrete` the moment
  the counterpart is a dynamic body, and it does that without saying so.
- **Against another moving body**, accuracy belongs to `Continuous Dynamic`. Speculative contacts
  are *predictions*: the solver widens the contact distance and resolves against where the body
  is about to be, and a prediction that does not come true surfaces as a **ghost contact** — a
  callback with the objects visibly apart, a bullet scoring early, a shivering stack. When "it
  hits before it touches" meets `Continuous Speculative`, the mode *is* the finding; do not hunt
  for an oversized collider.

Write the mode out in full every time. The enum is
`CollisionDetectionMode = Discrete, Continuous, ContinuousDynamic, ContinuousSpeculative` —
three distinct continuous behaviours, and the bare word "continuous" in a bug report has meant
each of them.

> **For a bullet or any projectile, raise `Physics.SphereCast` as well** — sweeping rather than
> stepping removes tunnelling entirely, independently of the physics step:
> [`reference/queries.md`](reference/queries.md).

## 3. Raycast misses

- **An origin inside the target collider returns false** — backface culling; Queries Hit Backfaces
  rescues only a `MeshCollider`.
- **Triggers are hit by default.** `Physics.queriesHitTriggers` is `true` and `UseGlobal` defers
  to it — pass `Ignore` or `Collide` explicitly, never rely on a default.
- **Check the mask you passed is the mask you meant** — A/B it against
  `Physics.DefaultRaycastLayers`, which excludes `Ignore Raycast`; `Physics.AllLayers` does not.
- **A disabled `Collider` or an inactive GameObject is invisible to queries too.**
  `Physics.OverlapSphere` asks what PhysX actually has at a position.
- **`GraphicRaycaster` finds UI, `Physics.Raycast` finds colliders**, never each other's
  (`unity-ui-ugui`).
- **After writing `transform.position`, queries see the old position** until
  `Physics.SyncTransforms()` — once, never every frame.

Each rule in full — the primitive-versus-mesh split, the three trigger results, the A/B probe, the
screen-point call and the `MovePosition` alternative:
[`reference/queries.md`](reference/queries.md).

## 4. It moved, then it stopped

- **The Rigidbody fell asleep.** Below `Physics.sleepThreshold` (**default `0.005`**)
  the body deactivates and `OnCollisionStay` / `OnTriggerStay` stop firing.
  `Rigidbody.sleepThreshold` also exists per body, and **`0` stops that body sleeping at all** —
  affordable for one object under test, expensive as a habit. `Project Settings → Physics → Sleep
  Threshold` does the same to every resting body in the game.

> **`AddForce` is NOT ignored on a sleeping body — it wakes it.** In a PlayMode test, a body put
> to sleep with `Sleep()` and then given a force of **0.001** reports `IsSleeping() == false` on
> the very next line. There is no magnitude below which the force is swallowed. **`WakeUp()`
> before `AddForce` is unnecessary.**
>
> So when someone reports *"AddForce stops working once it settles"*, the sleep state is not the
> explanation — do not assert a sleep mechanism, and do not chase one. Check instead, in order: the
> force is simply too small to be visible (force `0.001` produces a velocity of `0.00002` — awake,
> and going nowhere); it is being applied in `Update` rather than `FixedUpdate`, so most calls are
> discarded; the body turned `isKinematic`; or `constraints` froze the axis.
- **`Time.timeScale == 0`.** Diagnostic tell: raycasts still hit while nothing moves — that is
  timeScale, not the physics setup ([`reference/queries.md`](reference/queries.md)).

## 5. Shapes that are not what they look like

- **Non-uniform parent scale breaks a `SphereCollider`, and not in the way you would guess.**
  PhysX has no ellipsoid, so the sphere takes the **largest** axis. Under a `(1, 3, 1)` parent the
  mesh renders `(1, 3, 1)` and the collider's bounds are **`(3, 3, 3)`** — a sphere three times
  too wide in X and Z, colliding with things that are visibly nowhere near it. A `BoxCollider`
  under the same parent reads `(1, 3, 1)`, matching the mesh: **boxes are fine.** Apply scale in
  the DCC tool so the model imports at `(1,1,1)`.
- **`Transform.SetParent(t)` preserves world scale**, silently rewriting the child's
  `localScale` to compensate. Reparenting a collider under a scaled object therefore changes its
  local numbers without changing how it looks — and `SetParent(t, false)` is the overload that
  keeps local values.
- **A child `Rigidbody` cuts the compound body.** A parent Rigidbody governs colliders beneath it
  only until another Rigidbody appears.
- **MeshCollider, four silent rules:** a non-convex MeshCollider on a dynamic Rigidbody is
  ignored; two non-convex MeshColliders never collide with each other; a convex collider's
  contacts are on the hull, so concave shapes are wrong by design; and **flipped normals invert
  the contact direction**, so a ball that should rest inside a bowl or a pipe is pushed *out*
  through the shell instead. That last one reads as leaking geometry, not as a normals problem.
  Fix the winding in the DCC tool; enabling **Convex** also sidesteps it, because the hull is
  rebuilt from the vertices and the original winding stops mattering.
- **Ragdoll explosion = colliders overlapping in the start pose.** One frame of depenetration
  becomes velocity. **Shrink the colliders.** Joint limits, projection, mass ratios and Enable
  Collision are the standard misdiagnoses. Confirm with `Window > Analysis > Physics Debugger`.
  **`Rigidbody.detectCollisions = false` in `Start()`, back on a frame later, is a holding
  measure and is reported as one** — it postpones the spike while the colliders are re-fitted;
  the overlap returns with the collisions.
- **A visible gap when objects rest is Contact Offset.** `Physics.defaultContactOffset` is
  **`0.01`** by default. **Never set it to 0** — PhysX requires a positive value and 0 is unstable.
  Inset the visual mesh instead.

## 6. Editor yes, build no

- IL2CPP stripped the `MonoBehaviour` — `[Preserve]` or `link.xml`
  (`unity-android-release` → `reference/size-and-stripping.md`).
- **A layer name resolving to `-1` is not a build problem** — it means the layer is not defined at
  all, and `1 << -1` is not the mask you meant.
- **The first frames of a player are not the first Editor frames**, and **Fixed Timestep is a
  per-platform decision** a project that never set it inherits.
- **`Physics.IgnoreCollision` binds to collider *instances*** and is lost on a respawn or a return
  to the pool; **`Physics.IgnoreLayerCollision` is global and persists across scenes.**

Each of those three in full — where layer names actually ship and the startup assertion, the
one-frame delay and owning the step with `SimulationMode.Script`, and which of the two ignore
calls to reach for:
[`reference/editor-vs-build.md`](reference/editor-vs-build.md).

## The probe

`resources/CollisionDebugger.cs` — attach to **both** suspected objects, read the console, remove
it when done.

| Console | Diagnosis |
|---|---|
| Neither object logs `[Setup]` | The script is not on the objects you think it is |
| `[Setup]` from both, no `[Collision]` / `[Trigger]` | §1 steps 1, 3, 4 |
| `[Setup]` reports `collider none` or `enabled False` | §1 step 2 — the collider is not in the scene |
| Only one side logs anything | The other object is not the one colliding |
| `[2D Collision]` appears | 2D components in a 3D scene |

## Scope — what this skill does NOT do

Pathfinding, NavMesh baking and agent steering are `unity-navigation` — a collider that was
absent at bake time still collides here and is still not pathed around there. Canvas hit-testing
and the EventSystem are `unity-ui-ugui`. Stripping and `link.xml` are
`unity-android-release`.

2D physics and DOTS / the Unity Physics package (`com.unity.physics`) are **not** this skill's
subject. Both get a best-effort answer in their own vocabulary — never a PhysX rule from this page
under a 2D or DOTS name, never "move the project onto PhysX":
[`reference/neighbour-stacks.md`](reference/neighbour-stacks.md).
