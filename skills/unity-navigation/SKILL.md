---
name: unity-navigation
description: >-
  NavMesh pathfinding: baking, NavMeshAgent movement, obstacles, links, click-to-move and patrols.
---

# unity-navigation — walkable surfaces, and the agent that owns the transform

## Symptom → where to look

| Symptom | Go to |
|---|---|
| The agent does not move at all | §2 |
| It moves but slides instead of walking / fights the animation | §3 |
| It walks through a wall, or ignores an obstacle | [`reference/obstacles-links-baking.md`](reference/obstacles-links-baking.md) §4 |
| It stutters or overshoots at corners | §3 |
| It reaches *near* the target and stops short | §2 `pathPending` |
| It cannot cross a gap, stairs, a ledge | [`reference/obstacles-links-baking.md`](reference/obstacles-links-baking.md) §5 links |
| Agents avoid an area they should prefer, or vice versa | [`reference/obstacles-links-baking.md`](reference/obstacles-links-baking.md) §5 areas and costs |
| NavMesh baking at runtime; a generated or streamed level | [`reference/obstacles-links-baking.md`](reference/obstacles-links-baking.md) §6 |
| It will not enter a doorway or cross a narrow ledge | [`reference/obstacles-links-baking.md`](reference/obstacles-links-baking.md) §6 — voxel size, before anything else |
| Generate Links produced no links at all | [`reference/obstacles-links-baking.md`](reference/obstacles-links-baking.md) §6 — the agent type's Drop Height / Jump Distance |
| Carving obstacles are costing frames | [`reference/obstacles-links-baking.md`](reference/obstacles-links-baking.md) §4, then §6 tile size |
| Click-to-move, a patrol route, a chase — a working agent script rather than an explanation; also corner speed, locomotion, runtime bake | [`reference/recipes.md`](reference/recipes.md) |
| `agent.target` or `NavMesh.Bake()` will not compile | [`reference/agent-api.md`](reference/agent-api.md) |
| Click-to-move in a 2D (XY) top-down game | [`reference/recipes.md`](reference/recipes.md) §9 |

> **Two things own the transform and only one can win.** A `NavMeshAgent` writes
> `transform.position` every frame; so does root motion, and so does any movement script you
> wrote. Nearly every "the agent slides", "it teleports back", "it fights the animation" report
> is that conflict, not a baking problem. Decide the owner first — §3.

**The split is real and it is the first compile error.**

| Types | Namespace | Assembly | Ships with |
|---|---|---|---|
| `NavMeshAgent`, `NavMesh`, `NavMeshObstacle`, `NavMeshPath` | `UnityEngine.AI` | `UnityEngine.AIModule` | **the engine** |
| `NavMeshSurface`, `NavMeshLink`, `NavMeshModifier`, `NavMeshModifierVolume` | `Unity.AI.Navigation` | `Unity.AI.Navigation` | **`com.unity.ai.navigation`** |

There is no `UnityEngine.AI.NavMeshSurface`. So an agent compiles in a project with no navigation
package, and the surface that would give it something to walk on does not. Check before writing
against the package: `System.Type.GetType("Unity.AI.Navigation.NavMeshSurface, Unity.AI.Navigation")`
returns null without it. Installing the package headlessly: `unity-new-project` →
`reference/package-bootstrap.md`.

## 1. Inspect before you add anything

A project that already has navigation has already made these decisions, and adding a second
`NavMeshSurface` or a second agent type is how you get two disagreeing NavMeshes.

Check, in this order: existing `NavMeshSurface` components and what each collects; the agent
types defined in Navigation settings; whether anything bakes at runtime. Then ask what you still
do not know — **agent radius, height, step height and max slope are properties of the character,
not defaults**, and baking with the wrong ones produces a mesh that is subtly too generous.

## 2. The agent moves, or it does not

> **Two layers steer, and they fail differently.** A\* over the baked polygons picks the *route*;
> RVO local avoidance picks the *next step*. A wrong route is §5–§6, a crowd that shoves or stalls
> is §4 — both in [`reference/obstacles-links-baking.md`](reference/obstacles-links-baking.md).

```csharp
agent.destination = target.position;   // or agent.SetDestination(pos), which returns
                                       // whether the request was accepted
```

**Check the path, not the position.**

```csharp
if (agent.pathStatus == NavMeshPathStatus.PathComplete)      { /* reachable */ }
else if (agent.pathStatus == NavMeshPathStatus.PathPartial)  { /* only partway */ }
else                                                          { /* PathInvalid */ }
```

`PathPartial` is the one that masquerades as a bug: the agent walks confidently to a point that
is not the target and stops. It means the destination is off the NavMesh or behind a gap with
no link.

> **`NavMesh.CalculatePath` returns `true` for a partial path.** On two deliberately
> disconnected islands it gives `returned=True status=PathPartial corners=2`. Only a target that
> maps to no NavMesh position at all gives `returned=False status=PathInvalid corners=0`.
> **Checking the bool is not checking the path** — a great deal of "it walks to the wrong place"
> code is a correct-looking `if (CalculatePath(...))`. All three cases:
> [`reference/agent-api.md`](reference/agent-api.md) §1.

> **`remainingDistance` is meaningless while a path is being calculated.** Guard it, or arrival
> fires on frame one because the value is still `Infinity` — or never fires because it is zero.

```csharp
if (!agent.pathPending && agent.remainingDistance < 0.5f) { Arrived(); }
```

**Not moving at all**, in order: the agent is not on the NavMesh (`agent.isOnNavMesh` is false —
it was spawned above or beside it); `agent.isStopped` is true; the destination is unreachable
(check `pathStatus`); nothing was baked; or the agent's radius/height exceed the gap it is being
asked to enter, so the mesh has no surface there.

**Getting onto the NavMesh:** `NavMesh.SamplePosition` finds the nearest valid point, and
`agent.Warp(pos)` is how you teleport. **Do not assign `transform.position` to move an agent** —
it desyncs from the NavMesh and the agent snaps back or stops responding.

> **`SamplePosition`'s `maxDistance` is a 3D radius, not a ground-plane one.** A query
> at `(0, 50, 0)` directly above a baked surface with `maxDistance = 2` returns **false**. An
> object spawned above the level — dropped in, or at a prefab's authored height — is not "near"
> the NavMesh: a large share of "the agent will not move". Sample from roughly ground height, or
> pass a `maxDistance` that spans the drop. The sampled point sits slightly **above** the surface
> (e.g. `y = 0.08` on a plane at `y = 0`), so comparing it to the ground's exact height fails.

> **`agent.isOnNavMesh` is `false` outside play mode.** An agent placed directly on a
> freshly baked surface in the Editor, not playing, reports `isOnNavMesh=False` with
> `enabled=True`. It is a runtime state — **do not use it as a headless diagnostic**, or you will
> conclude the bake is broken when it is not. As with `Physics.Simulate()`: the query is real,
> the context is not.

`agent.isStopped = true` pauses but keeps the path; `agent.ResetPath()` discards it. They are
different intentions and using the wrong one is why an agent "resumes" to the wrong place.

Names that do not exist, `[Obsolete]` members that still compile, `Move` versus `Warp`, and the
`velocity` / `desiredVelocity` / `speed` split: [`reference/agent-api.md`](reference/agent-api.md)
§2.

## 3. Who owns the transform

| Setup | `updatePosition` | `updateRotation` | Animation |
|---|---|---|---|
| **Agent drives, animation follows** (default, simplest) | true | true | Feed `agent.velocity.magnitude` into the locomotion blend tree |
| **Animation drives, agent advises** (root motion) | **false** | true | Read `agent.desiredVelocity`, drive the Animator, then write `agent.nextPosition = transform.position` each frame |

The second is what removes foot sliding, and it is also where people get stuck: if you disable
`updatePosition` and never write back `nextPosition`, the agent's internal position never
advances and pathing silently stops working while the character keeps animating. Rotation stays
with the agent in both rows — leave `updateRotation` true unless your own code writes
`transform.rotation`, or the character stops turning altogether.

Feed the blend tree from **`agent.velocity`** (actual, post-avoidance); lean or turn from
**`agent.desiredVelocity`** (intended, pre-avoidance). Confusing them animates avoidance the
character is not performing.

Animator and blend-tree construction itself: `unity-rigged-character`.

**Corner stutter and overshoot** is steering, not baking: `angularSpeed` too low for the turn,
`acceleration` too high, or `stoppingDistance` at zero so the agent oscillates around the exact
point. Raising `stoppingDistance` above zero fixes more "jitter at the destination" reports than
anything else — **and zero is the default**, so this is the common case, not the unusual one.

`autoBraking` off makes an agent hold its speed through a waypoint — right for a patrol, wrong
for a single destination it is meant to stop at. Every default of a fresh agent, worth
knowing before you "tune" anything: [`reference/agent-api.md`](reference/agent-api.md) §3.

**The scripts themselves live in [`reference/recipes.md`](reference/recipes.md) §5:** both rows
above, runnable, with the blend tree root motion expects, head look-at, and (§4) a corner speed
limiter.

## 4–6. Obstacles, links and areas, baking → `reference/obstacles-links-baking.md`

§4 carve or avoid, and why a wall missing from the bake is walked through; §5 `NavMeshLink`,
areas and costs, modifiers and volumes; §6 `BuildNavMesh` / `UpdateNavMesh`, voxel size and the
runtime baker. Same numbering there.

## 7. Verify it

Assertions do not see a bad NavMesh. **Look at it**: the navigation overlay in the Scene view
shows the baked surface and the carves, and an agent's current path can be drawn from
`agent.path.corners`. Screenshot-driven verification is `unity-debug`.

Cheap runtime probes worth keeping while building: log `pathStatus` on every destination set,
and assert `agent.isOnNavMesh` on spawn — **in play mode only**, per §2.

**Baking is headless-friendly.** `NavMeshSurface.BuildNavMesh()` over a couple of primitive planes
completes in milliseconds from a batch-mode Editor and produces a live `navMeshData`, with
`NavMesh.SamplePosition` and `NavMesh.CalculatePath` answering correctly against it immediately
afterwards. So bake-and-query is a real automated test you can write, even though agent
*movement* is not — build the surface from `CollectObjects.Children`, bake, call
`NavMesh.CalculatePath`, and **assert on `path.status`, never on the bool**. The snippet:
[`reference/recipes.md`](reference/recipes.md) §6. Time the bake on your own scene (`reference/obstacles-links-baking.md` §6).

Driving the Editor to run it: `unity-debug` → `reference/editor-control.md`.

## Scope — what this skill does NOT do

Rigs, Avatars and Animator layers (`unity-rigged-character`), PhysX collision and triggers
(`unity-physics-3d`), 2D grid pathfinding (`unity-2d-grid`), and enemy decisions: patrol,
chase, perception, waves (`unity-game-ai`).
