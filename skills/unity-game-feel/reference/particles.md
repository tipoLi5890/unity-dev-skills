# Particles — bursts from script, one emitter per effect, and when VFX Graph is the answer

> Part of the `unity-game-feel` skill. A burst-style `ParticleSystem` built from a preset; two
> ways to fire it (a shared emitter moved to the event, or pooled one-shot instances); stop
> actions, simulation space, sorting in 2D, the clock; and the short list of reasons to reach
> for VFX Graph.

## 1. A burst is punctuation

A feedback particle effect is a burst: one emission at 0 s, no rate over time, lifetimes under
0.5 s, counts under 24. A burst that lingers or loops is scenery, and scenery belongs to the
level, not to the event.

`resources/Editor/ParticlePresetBuilder.cs` builds one from four presets. Each menu command
reports what it would create and waits for confirmation:

```
Tools/Unity Dev/Feel/Build Particle Preset/Hit Spark      12, cone 35°, streaks, 0.15–0.30 s
Tools/Unity Dev/Feel/Build Particle Preset/Pickup Pop      6, sphere, 0.20–0.35 s
Tools/Unity Dev/Feel/Build Particle Preset/Land Dust       8, hemisphere, 0.25–0.45 s, rises slightly
Tools/Unity Dev/Feel/Build Particle Preset/Launch Burst   20, cone 20°, streaks, 0.20–0.40 s
```

Every preset: looping off, duration 1 s, World simulation space, Hierarchy scaling, size and
alpha over lifetime 1 → 0, shadows off, drag through Limit Velocity over Lifetime (dampen 0, so
only drag applies), `maxParticles` four bursts' worth. The material is the active pipeline's
`RenderPipelineAsset.defaultParticleMaterial` — URP's `Particles/Unlit` — so the prefab is never
magenta; with no pipeline asset it is the built-in `Default-ParticleSystem.mat`.

From a script or a test, call `ParticlePresetBuilder.Plan(preset, folder, pooled)`, show the
text, then `Build(...)`. `Build` does not ask.

## 2. Two ways to fire it

| Way | Prefab shape | How the event fires it | Use when |
|---|---|---|---|
| **Shared emitter** (the menu's shape) | Play On Awake off, stop action None | One instance in the scene; the `Feedback` row moves it to the event and calls `Emit(count)` | The default. No instantiate, no pool, one draw for every burst of that effect |
| **Pooled instances** — `Build(preset, folder, true)` | Play On Awake on, stop action Disable | A pool hands out an instance at the event; enabling it plays; it switches itself off when done | The effect must follow a moving object, carry its own light or sound, or be a hierarchy of several systems |

The shared emitter works because World simulation space leaves particles where they were born
when the emitter moves on. Twelve sparks at the gate and six at a pickup two lanes over are one
system emitting twice.

```csharp
emitter.transform.SetPositionAndRotation(point, Quaternion.LookRotation(normal));
emitter.Emit(12);
```

`Emit` ignores the burst list and Play On Awake; it uses the start settings of the main module.
To vary one burst — a bigger hit, a tinted pickup — use `ParticleSystem.EmitParams`:

```csharp
var p = new ParticleSystem.EmitParams { startColor = laneColour, applyShapeToPosition = true };
emitter.Emit(p, 6);
```

For pooled instances, pooling is `unity-scene-flow` → `reference/pooling.md`. What release must
reset on a particle object: `Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear)` before
it goes back, so a reused instance does not show the tail of its last use at the new place; and
any `TrailRenderer` on it cleared (`reference/trails.md`).

## 3. Stop actions

`main.stopAction` is what happens when the system and every particle in it have finished:

| Stop action | Effect | Use |
|---|---|---|
| `None` | Nothing | A shared emitter that lives for the scene |
| `Disable` | `SetActive(false)` on the GameObject | A pooled instance: the pool sees it inactive and takes it back |
| `Destroy` | Destroys the GameObject | A rare one-off that is not worth pooling; an instantiate and a destroy per use |
| `Callback` | Sends `OnParticleSystemStopped` to scripts on the object | Returning to a pool that does not poll `activeSelf` |

A stop action fires only on a system that is not looping. A looping system never finishes.

## 4. Simulation space and scale

| Space | Particles after birth | Use for |
|---|---|---|
| `World` | Stay where they were born | Every burst: sparks, dust, pickups. Required for a shared emitter |
| `Local` | Move with the emitter | A glow attached to the runner, a jet on the launch pad |
| `Custom` | Move with `customSimulationSpace` | Effects inside a moving platform or a lift, which must ride along |

`scalingMode` Hierarchy scales the effect with its parents; `Shape` scales only the emitter's
shape; `Local` ignores the parents' scale. Hierarchy is the preset's choice so a scaled-down 2D
scene scales its effects with it.

## 5. The clock

Particles run on scaled time. In a hit stop at 0.05 the sparks of the hit freeze in mid-air for
80 ms and then fly, and the spray hangs on the impact. When that is wrong
(a UI burst, a pause-menu effect), set `main.useUnscaledTime = true` on that system.

## 6. Sorting in 2D

A particle system is a renderer, and it sorts by the keys every 2D renderer sorts by —
sorting layer, order in layer, then distance — set on its `ParticleSystemRenderer`:

```csharp
var r = emitter.GetComponent<ParticleSystemRenderer>();
r.sortingLayerName = "Effects";
r.sortingOrder = 10;
```

Put feedback effects on their own sorting layer above characters. In a Y-sorted top-down depot,
a dust puff at the runner's feet belongs on the character layer instead, with a `SortingGroup`
on the runner or a sort point set so it sorts with what it touches. The priority order and the
group rules: `unity-2d-rendering` → `reference/sort-order.md`. In 2D, also set the renderer
alignment to View and keep the emitter's z at the plane of the characters, or a perspective
camera's distance sort reorders it.

## 7. Cost

A burst of 12 that lives 0.3 s is nothing; the costs that show up are overdraw (large soft
particles stacked over the camera — dust clouds, smoke) and the count of systems updating at
once. When a profiling capture names particles, the scene-side fixes — fewer, smaller, opaque
where possible, culling — are in `unity-scene-optimisation` → `reference/2d-draw-cost.md` and `unity-scene-optimisation`
→ `reference/batching.md`. Cap `main.maxParticles` per system: at the cap a stream of hits stops
adding particles until old ones die (`ringBufferMode` `Disabled`, the default), instead of
growing.

## 8. When VFX Graph is the answer

The `ParticleSystem` simulates on the CPU, one system at a time; VFX Graph
(`com.unity.visualeffectgraph`) simulates on the GPU through compute shaders.

| Choose VFX Graph when | Stay with ParticleSystem when |
|---|---|
| Thousands to millions of particles in one effect — a swarm, a dense storm, debris fields | Bursts of tens, which is every feedback row in this skill |
| The target hardware has compute shaders: desktop and console, recent high-end phones | The game ships to low-end mobile or to WebGL. Check `SystemInfo.supportsComputeShaders` on the slowest supported device |
| The effect reads the depth buffer or a signed distance field to collide | Particles must collide with physics colliders and fire callbacks (`OnParticleCollision`) |
| Artists author it in a graph and the gameplay only sends events | Gameplay emits from script with per-burst parameters, as `Feedback` does |

A VFX Graph effect is fired with `VisualEffect.SendEvent("OnPlay")` and positioned through
exposed properties; the `Feedback` row's particle channel would call that in place of `Emit`. It
does not run without compute support, so a mobile game with a VFX Graph effect needs a
`ParticleSystem` fallback for the devices without it. Two versions of every effect is the
reason to stay with `ParticleSystem` throughout.
