# Ladder steps 4–6: sleep and stopping, shapes, editor versus build

Moved out of SKILL.md, which keeps steps 0–3 of the triage ladder; numbering continues it. First match wins here too.

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
  timeScale, not the physics setup ([`reference/queries.md`](queries.md)).

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
  **`detectCollisions = false` in `Start()`, back on a frame later, is a holding measure and is
  reported as one**: the overlap returns with the collisions.
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
[`reference/editor-vs-build.md`](editor-vs-build.md).
