---
name: unity-physics-3d
description: >-
  3D PhysX bugs: OnTriggerEnter never fires, tunnelling, raycast misses, exploding ragdolls.
---

# unity-physics-3d — a triage ladder, not a list of things to try

> **Your prior knowledge about PhysX callbacks is unreliable, and the errors are silent.**
> Almost nothing in this domain throws. A collider that will never collide looks identical in the
> inspector to one that will. Work the ladder; do not reason from what "should" happen.

## Symptom → where to look

First match wins. **Stop at the first cause you confirm** and write the diagnosis; the rest of the
ladder is for when that check comes back clean.

| Symptom | Go to |
|---|---|
| `OnCollisionEnter` / `OnTriggerEnter` never fires | §1 |
| Objects pass through each other at speed; a fast object passes through a wall | §2 |
| A hit is reported before the two objects visibly touch | §2 — speculative contacts |
| `Physics.Raycast` misses something clearly in front of it | §3 |
| A click finds no UI, or a world ray keeps hitting the HUD | §3 — two raycasters, two worlds |
| `AddForce` seems to stop working once the object settles | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §4 — and it is **not** the sleep state |
| `OnTriggerStay` / `OnCollisionStay` ran for a while, then went quiet | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §4 — the body fell asleep |
| Everything frozen but raycasts still hit | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §4 |
| Ragdoll explodes on the first frame | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §5 |
| Collider is the wrong shape after import / imported geometry does not collide | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §5 |
| Objects come to rest with a visible gap between them | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §5 — contact offset |
| Things pass out through a concave mesh they should sit inside | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §5 — inverted normals |
| It collides in the editor and not in the build | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §6 |
| Collisions stopped after a respawn or a return to the pool | [`reference/sleep-shapes-build.md`](reference/sleep-shapes-build.md) §6 — per-instance ignore pairs |
| A sports ball must curve, bounce with spin, replay and be predicted exactly | [`reference/own-ball-physics.md`](reference/own-ball-physics.md): no PhysX for the ball |

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
- **Answer with what the ladder confirmed.** When the checks you can reach are exhausted without a
  confirmed cause, write the most likely diagnosis off the ladder, labelled unconfirmed, with the
  one check that would settle it.
- **End with the fix or the diagnosis.** Make the change yourself where you can reach it — a
  script, or the live scene over an Editor connection — otherwise hand over an explanation complete
  enough to apply without you. Ask only for information you cannot get yourself, and name it.

## 1. No callback fires

Work down. First match wins.

1. **At least one of the pair needs a `Rigidbody`.** Two static colliders never generate contacts.
2. **An unticked `Collider` and an inactive GameObject are both completely silent.** No warning,
   no error: the object is simply not in the physics scene, and the inspector looks correct
   because the checkbox is the only difference. Check `Collider.enabled` *and*
   `gameObject.activeInHierarchy` — `Collider` declares its own `enabled` rather than inheriting
   one from `Behaviour`, and `activeInHierarchy` is read-only, so a parent
   switched off two levels up reads as the child's own fault.
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

> **In Unity 6 the property is `Rigidbody.linearVelocity`.** `velocity` still exists and old code
> compiles; mixing the two in one file reads as a bug that is not there.

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

Write the mode out in full (`ContinuousDynamic`, `ContinuousSpeculative`): the bare word
"continuous" in a bug report has meant each of three modes.

> **For a bullet or any projectile, raise `Physics.SphereCast` as well** — sweeping rather than
> stepping removes tunnelling entirely, independently of the physics step:
> [`reference/queries.md`](reference/queries.md).
> A ball the rules own, swept in substeps by your own code: [`reference/own-ball-physics.md`](reference/own-ball-physics.md).

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

## 4–6. Sleep, shapes, editor versus build → `reference/sleep-shapes-build.md`

§4 a body that moved then stopped (sleep, `AddForce` that wakes it, `timeScale`); §5 colliders
that are not the shape they look — imported geometry, non-uniform scale, ragdoll overlap, contact
offset, inverted normals, compound bodies; §6 what differs in a build. Same numbering there.

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
`unity-android-release`. A `CharacterController` motor — ground, slopes, steps — is
`unity-3d-controller`. Hit and hurt layers and damage events are `unity-combat`. A ball the game
integrates itself (drag, spin, swept contact, a shot solver) is
[`reference/own-ball-physics.md`](reference/own-ball-physics.md).

2D physics — `Rigidbody2D`, `Collider2D`, `Physics2D` — is `unity-physics-2d`. DOTS / the Unity
Physics package (`com.unity.physics`) is **not** this skill's subject either: it gets a
best-effort answer in its own vocabulary — never a PhysX rule from this page under a DOTS name,
never "move the project onto PhysX":
[`reference/neighbour-stacks.md`](reference/neighbour-stacks.md).
