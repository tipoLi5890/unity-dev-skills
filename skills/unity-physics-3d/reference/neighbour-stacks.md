# Neighbouring physics stacks: 2D and DOTS

Two neighbouring physics stacks are **not** the subject of `unity-physics-3d`. Never restate a
PhysX rule from SKILL.md under a 2D or DOTS name, and never propose that the fix is to move the
project onto PhysX.

**2D physics** is `unity-physics-2d`: `Rigidbody2D`, `Collider2D`, the `2D` callbacks, `Physics2D`
queries and the separate layer matrix under `Project Settings → Physics 2D` have their own ladder
there, in Box2D's vocabulary. One report belongs to both skills — a `2D` suffix in a PhysX scene,
or a missing one in a Box2D scene, is silent in both directions; `resources/CollisionDebugger.cs`
flags it. Past that signature check, hand over.

**DOTS / the Unity Physics package (`com.unity.physics`).** Outside the primary scope; best effort,
to be confirmed against the package documentation. There are no MonoBehaviour messages at all. A
body is an entity carrying `PhysicsCollider`, `PhysicsVelocity` and `PhysicsMass`; contacts arrive
as jobs — `ICollisionEventsJob` and `ITriggerEventsJob` scheduled against the `SimulationSingleton`
in a system that runs after the physics step — and whether a body collides, only reports, or is
skipped is `CollisionResponsePolicy` on its collider, not an `isTrigger` checkbox. Havok Physics is
a drop-in backend behind the same components. `Rigidbody`, `AddForce`, `WakeUp` and
`Physics.Raycast` do not exist in that world; the query entry point is the `CollisionWorld`.
Package docs: <https://docs.unity3d.com/Packages/com.unity.physics@latest>
