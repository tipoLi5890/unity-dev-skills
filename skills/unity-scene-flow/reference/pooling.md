# Pooling — reuse is cheap, a dirty instance is the bug

> Part of the `unity-scene-flow` skill. `resources/PickupObjectPool.cs` is the file: a component in the
> Boot scene wrapping `UnityEngine.Pool.ObjectPool<T>`. Worked setting: the **lane run** and the
> **gate room** — pickups collected, and the same objects set out again after a respawn.

## 1. When a pool earns its place

`Instantiate` and `Destroy` cost time on the frame they run and leave garbage for the collector.
A pool trades that for memory held all the time and for one new class of bug: an instance that
comes back carrying its last life.

| Pool it | Do not |
|---|---|
| Spawned many times a minute during play: pickups, projectiles, hit effects, floating numbers | One per level: the gate, the runner, a sentry that never respawns |
| Short-lived: back within seconds | Lives as long as the level — let the scene own it |
| Uniform: every instance resets the same way | Carries unique authored state |

Size it from the game's numbers, not by feel: **spawn rate × lifetime × sources**, plus a
quarter. Eight pickups visible per stretch and three stretches loaded is 24, so `maxSize` 32.

## 2. `ObjectPool<T>`

```csharp
using UnityEngine.Pool;

var pool = new ObjectPool<PooledPickup>(
    createFunc:      Create,        // the pool is empty and something was asked for
    actionOnGet:     OnGet,         // an instance is leaving: activate it
    actionOnRelease: OnRelease,     // an instance is back: clean it and deactivate it
    actionOnDestroy: OnDestroyItem, // an instance came back to a full pool: destroy it
    collectionCheck: true,
    defaultCapacity: 16,
    maxSize:         64);
```

| Parameter | Default | What it really is |
|---|---|---|
| `createFunc` | — (required) | Called from `Get` only when no idle instance exists. Counting its calls is the measurement (§6) |
| `actionOnGet` | none | Runs on every `Get`, new instance or reused |
| `actionOnRelease` | none | Runs on every `Release`, **before** the pool decides whether it has room |
| `actionOnDestroy` | none | Runs for an instance released beyond `maxSize`, and for every idle one on `Clear` or `Dispose` |
| `collectionCheck` | `true` | Throws when an instance already in the pool is released again — **in the Editor only**. A player performs no check |
| `defaultCapacity` | 10 | Starting size of the internal stack. **Creates nothing**: instances are made one `Get` at a time |
| `maxSize` | 10000 | The most *idle* instances kept. It is not a cap on how many can be out at once |

| Member | Returns |
|---|---|
| `Get()` · `Release(item)` | An instance out · the instance back |
| `CountAll` | Created and not destroyed: out plus idle |
| `CountActive` · `CountInactive` | Out · idle |
| `Clear()` · `Dispose()` | Destroy every idle instance through `actionOnDestroy` |

Three consequences the names hide:

- **`defaultCapacity` is not a prewarm.** A level whose first eight pickups appear at once pays
  eight `Instantiate` calls on that frame. Prewarm behind the loading screen: get N, release N.
  `PickupObjectPool.Prewarm(count)` does it; the serialised `prewarm` field does it in `Start`.
- **`maxSize` does not stop a burst.** Sixty-five out at once from a pool of 64 creates the
  sixty-fifth; on release, the one that finds the pool full is destroyed. A hard cap is the
  caller's rule: refuse the spawn, or recycle the oldest.
- **The double-release check is not there in a build.** Releasing twice puts one instance in the
  stack twice, and two later `Get` calls hand the same object to two owners — one pickup that
  teleports between two places. `PickupObjectPool.Despawn` checks `InUse` itself and counts
  `DoubleReleases` instead of relying on the pool.

## 3. Using `PickupObjectPool`

```csharp
// Boot scene: PickupObjectPool on a child of the Boot root, prefab assigned, then provided once.
Bootstrap.WhenReady(boot => boot.Services.Provide(pool));

// A level, from Start onwards:
PickupObjectPool pool = Bootstrap.Get<PickupObjectPool>();
PooledPickup pickup = pool.Spawn(new Vector3(1.3f, 0.5f, 24f), id: "pickup-lane2-24");

// The pickup, when the runner reaches it:
save.SetFlag(pickup.Id, 1);        // the fact first
pickup.Release();                  // then the object; a second call does nothing
```

| Member | Meaning |
|---|---|
| `Spawn(position, id)` | An instance, active, at the position, carrying the id its spawn data gave it |
| `Despawn(pickup)` / `pickup.Release()` | Back to the pool; ignored when it is already back |
| `DespawnAll()` | Everything that is out — the first step of a respawn (`reference/checkpoints.md`) |
| `Prewarm(count)` | Create that many now |
| `Configure(factory, capacity, max)` | Build instances in code when there is no prefab — what the journey does |
| `CountAll`, `CountActive`, `CountInactive` | The pool's own numbers |
| `Created`, `Destroyed`, `DoubleReleases` | Calls to create, instances lost to a full pool, releases ignored |

**The pool lives in Boot and instances are parented under it.** A pooled instance parented to a
level object is in the level's scene and is destroyed with it, leaving the pool holding a dead
reference that it hands out on the next `Get`. An instance that must follow something sets its
position each frame, or is re-parented and put back in `OnRelease`.

## 4. Resetting state on release

An instance comes back with everything its last use did to it. The reset is the pool's whole
correctness, and it is split in two by who knows what:

| Reset by the pool, in `OnRelease` | Reset by the instance, in its own `OnEnable` |
|---|---|
| Parent, back under the pool | Health, timers, "already collected" latches |
| Scale, back to the prefab's | Animator: `Rebind()` and `Update(0f)`, unless `keepAnimatorStateOnDisable` is wanted |
| A non-kinematic body's `linearVelocity` and `angularVelocity` | `TrailRenderer.Clear()` — a trail otherwise draws a streak from the old place to the new |
| The id of the use that ended | `ParticleSystem.Clear()` then `Play()` |
| Active state, off | Subscriptions made in `OnEnable`, removed in `OnDisable` |

Checklist for a new pooled type — each line is a bug seen as "the second one behaves oddly":

- A coroutine started in the last life is still scheduled. Deactivation stops coroutines on that
  object; ones started on *another* object for it are not stopped.
- A collected flag set to true and never cleared: the reused pickup cannot be collected.
- A material property changed with `renderer.material` — that instance now has its own material
  for good. Use a property block, and clear it.
- An event the instance subscribed to on Get and did not leave on Release fires on an idle
  object.
- A reference to the thing that spawned it: a projectile that remembers its first shooter.

Write it as `OnEnable`/`OnDisable` on the instance where possible. Those run for a pooled and a
non-pooled instance alike, so the prefab also works dropped straight into a scene.

## 5. Pooled objects and physics callbacks

Deactivating an object removes it from the simulation; activating it puts it back. Four things
follow:

- **Do not rely on `OnTriggerExit` for an object deactivated inside a trigger.** Whether an exit
  is raised differs between the engines (in 2D it follows `Physics2D.callbacksOnDisable`), and a
  counter of "things in the zone" incremented on enter and decremented on exit drifts by one per
  pickup collected inside it when none comes. Track the set and prune inactive members, or
  decrement from the release.
- **A release from inside a physics callback is safe; a second callback on the same step is
  not rare.** A pickup overlapping two of the runner's colliders reports twice. The `InUse`
  guard makes the second release a no-op — and the *score* needs its own guard, in the handler.
- **Teleporting a reused body.** Set the position before activating, or the body is simulated
  for one step where it last died. `Spawn` positions first; a body with interpolation on also
  needs its `position` assigned, not only the transform.
- **`Physics.IgnoreCollision` is forgotten** when an object is deactivated and re-enabled, so a
  reused projectile hits the shooter it was told to ignore. Re-apply it on every Get — the
  reason, and the layer-wide alternative, are in `unity-physics-3d` →
  `reference/editor-vs-build.md`.

## 6. Measuring whether the pool helps

A pool that is too small, or that is bypassed, looks exactly like a working one. Three numbers
say which:

| Number | Healthy | Means when not |
|---|---|---|
| `Created` during play, after the prewarm | Flat | Rising: the pool is too small, or instances are never released |
| `Destroyed` | 0 | Above 0: bursts exceed `maxSize`, and the pool is paying `Destroy` after all |
| `CountActive` at a quiet moment | Back to its baseline | Climbing: a leak — something is spawned and never released |

Register them where the game wires its probe, and they are in every journey's timeline:

```csharp
GameProbe.Count("poolAll", () => pool.CountAll);
GameProbe.Count("poolActive", () => pool.CountActive);
GameProbe.Count("poolCreated", () => pool.Created);
```

Then decide with a before and after, not with the counters alone: scheduled, completed and
discarded work per spawn, and the frame-time window around the third pickup, are in
`unity-profiling` → `reference/work-counters.md`. If `Created` was already flat and the hitch is
still there, the cost was never `Instantiate`.

The journey's check is identity: after the level is replaced, the three pickups set out again
are the same three objects, `Created` is still 3 and each has `Uses == 2`.
`SCENEFLOW_JOURNEY_BREAK=pool` sets `maxSize` to 1, two of the three are destroyed on release,
and the test turns red.

Projectiles pooled the same way → `unity-combat` → `reference/projectiles.md`; waves that draw
on a pool → `unity-game-ai` → `reference/spawners-and-waves.md`.
