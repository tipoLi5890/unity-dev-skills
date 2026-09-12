# Neighbouring physics stacks: 2D and DOTS

Two neighbouring physics stacks are **not** the subject of `unity-physics-3d`, and both get an
answer anyway — written in their own vocabulary. Never restate a PhysX rule from SKILL.md under a 2D
or DOTS name, and never propose that the fix is to move the project onto PhysX.

**2D physics.** Outside the primary scope; what follows is best effort, to be confirmed against
Unity's 2D physics manual. The body is `Rigidbody2D`, the shapes are `Collider2D` subclasses, the
callbacks are `OnCollisionEnter2D(Collision2D)` and `OnTriggerEnter2D(Collider2D)`, the queries are
static members of `Physics2D`, and the settings — including a separate layer collision matrix — sit
under `Project Settings → Physics 2D`. The most common report by far is a signature mismatch: a `2D`
suffix in a PhysX scene, or a missing one in a Box2D scene, is silent in both directions, and
`resources/CollisionDebugger.cs` flags it. Beyond the shape of the API, assume nothing transfers:
sleep thresholds, contact offset, the collision-detection modes and the trigger-query defaults are
Box2D's, with Box2D's values.
Manual: <https://docs.unity3d.com/Manual/Physics2DReference.html>

**DOTS / the Unity Physics package (`com.unity.physics`).** Outside the primary scope; best effort,
to be confirmed against the package documentation. There are no MonoBehaviour messages at all. A
body is an entity carrying `PhysicsCollider`, `PhysicsVelocity` and `PhysicsMass`; contacts arrive
as jobs — `ICollisionEventsJob` and `ITriggerEventsJob` scheduled against the `SimulationSingleton`
in a system that runs after the physics step — and whether a body collides, only reports, or is
skipped is `CollisionResponsePolicy` on its collider, not an `isTrigger` checkbox. Havok Physics is
a drop-in backend behind the same components. `Rigidbody`, `AddForce`, `WakeUp` and
`Physics.Raycast` do not exist in that world; the query entry point is the `CollisionWorld`.
Package docs: <https://docs.unity3d.com/Packages/com.unity.physics@latest>
