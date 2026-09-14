# The simulation / presentation split

> Part of the `unity-game-brief` skill. The proposal says the split exists; this file is what it
> costs and what it buys, plus a skeleton in `resources/` that compiles as-is. Assembly definition
> mechanics, folder layout and module boundaries in general are `unity-new-project` §5.

Two assemblies:

```
Game.Sim           rules, seeded generation, state     "noEngineReferences": true
Game.Presentation  scene, clock, input, logging        references Game.Sim
```

One type crosses: `RunState`. The presenter reads it, the tests assert on it, a probe prints it.
That is the whole contract, and it is the reason the look can change without re-tuning the game.

---

## What `noEngineReferences` takes away

It is not a style setting. The assembly genuinely cannot see UnityEngine, so these stop existing:

| Gone | Use instead |
|---|---|
| `Vector2` / `Vector3` / `Quaternion` | Plain floats, or your own small struct. A lane index and a distance beat a `Vector3` anyway |
| `Mathf` | `System.Math` — note it takes and returns `double` for most functions, so cast at the call |
| `Random` | `System.Random`, seeded explicitly. This is a feature: the seed is now visible |
| `Time` | The `dt` passed into `Tick` |
| `Debug.Log` | Return values, and `TestContext.WriteLine` in tests. Nothing in here should be logging |
| `JsonUtility`, `ScriptableObject`, `MonoBehaviour`, coroutines | A hand-written writer for state; configuration passed into the constructor |

`JsonUtility` living on the wrong side of the boundary is the one that surprises people, because
serialization is exactly what a rules assembly wants to do. Decide it knowingly: either hand-write a
small writer inside the assembly (30 lines for a state object this size) or let the presentation
layer serialize.

**`Unity.Mathematics` is available without the engine**, as a package assembly — `float3`,
`math.*`, and a deterministic `Random` struct. Adding it costs a package dependency in a place whose
selling point was having none, and it makes the assembly untestable outside Unity. Take it when the
game is genuinely vector-heavy; the courier run, which is a lane index and a distance, does not need
it. Confirm the reference name on your version before adding it to the asmdef.

---

## Commands in, state out, dt in

Three doors, and nothing else:

```csharp
sim.Enqueue(RunCommand.Launch);   // commands in — from input, a test, or a situation
sim.Tick(dt);                     // time in — a fixed dt, supplied by whoever owns the clock
RunState state = sim.State;       // state out — read-only by convention, the only type that crosses
```

Two rules keep it that way:

- **Commands are named intents, not device events.** `LaneLeft`, not `KeyCode.A` and not
  `leftStick.x < -0.5f`. The three physical buttons, a keyboard stand-in, a test and a replay all
  produce the same three commands, which is what makes any of them drivable.
- **The presenter never writes into state.** Not "just this one field". The first write is the end
  of "the same seed gives the same run", and it is undetectable afterwards because the write looks
  local and correct.

---

## Picking the tick

`Tick(dt)` advances by exactly `dt` and reads nothing else, so determinism is entirely a question of
what the caller passes. Two workable choices:

**Fixed accumulator in `Update` (what `resources/Presentation/RunPresenter.cs` does).** The presenter
accumulates `Time.deltaTime` and calls `Tick(TickSeconds)` as many times as fit, capped so a stalled
frame cannot spiral. The simulation sees a constant dt forever; frame rate changes nothing.

**`FixedUpdate`.** Free fixed stepping, at the cost of the simulation now living on the physics
clock: `Time.fixedDeltaTime` is a project setting other people change, and a physics-heavy frame
moves it around. Fine when the game already runs on physics; unnecessary coupling when it does not.

Either way, **cap the catch-up**. Without a cap, one long frame (a domain reload, a breakpoint, a
window drag) produces hundreds of ticks in one frame, and what the player sees is the run teleporting
to its end.

---

## Two things the presenter is allowed to invent

The split is not "the presenter does nothing". It owns everything that is *about the drawing*:

- **Smoothing.** The drawn runner glides toward its lane centre; the simulation's lane changed
  instantly. The glide is presentation and may be tuned freely — it does not change the run.
- **Edge detection for logs.** Comparing this frame's phase to the last one and logging the change
  is the presenter's job. `[RUN] phase=AtGate lane=1 dist=120.00` is a presentation artefact, and
  the simulation stays silent.

What it is not allowed to invent: anything the outcome depends on. If the presenter decides
something, a test cannot reach it.

---

## The tests come free

`resources/Tests/` runs in EditMode, opens no scene, and instantiates nothing. That is the payoff:
the invariants are checked in about a second, on every compile, with no Editor window and no
graphics device — an EditMode suite is the cheapest instrument this project has, and the split is
what makes the game's rules reachable by it.

How to actually run it from a terminal, what the exit code means, and how to prove the run happened
rather than trusting a stale results file: `unity-debug` → `reference/cli-harness.md`.

**Confirm on your version:** the test assembly in `resources/Tests/Game.Sim.Tests.asmdef` is
Editor-only, `noEngineReferences: true`, with `nunit.framework.dll` as its only precompiled
reference. If the Test Runner does not list the tests after a recompile, add `UnityEngine.TestRunner`
and `UnityEditor.TestRunner` to its `references` and drop `noEngineReferences` — the tests
themselves do not change.

---

## The probe hook

One line makes the simulation readable from outside without giving anything write access:

```csharp
// In the presenter, not the simulation — the simulation still knows nothing about Unity.
GameProbe.SetState(() => _sim.State.Phase.ToString());
GameProbe.Register("run", () => _sim.State.Signature());
```

`RunState.Signature()` already exists for the determinism test, so the probe costs nothing new. What
a probe is, what keys it carries, how a situation boots straight into a moment and how a journey
test samples it: `unity-play-harness`.

---

## The files, and where they go

| From `resources/` | To | Why |
|---|---|---|
| `Sim/Game.Sim.asmdef` | `Assets/Scripts/Sim/` | `noEngineReferences`, not auto-referenced |
| `Sim/RunSimulation.cs` | `Assets/Scripts/Sim/` | Phases, commands, config, state, tick |
| `Sim/TrackGen.cs` | `Assets/Scripts/Sim/` | Seeded generation; INV-5 as a function |
| `Presentation/Game.Presentation.asmdef` | `Assets/Scripts/Presentation/` | References `Game.Sim` |
| `Presentation/RunPresenter.cs` | `Assets/Scripts/Presentation/` | Clock, spawning, mapping, the three entry points |
| `Presentation/RunLegacyInput.cs` | `Assets/Scripts/Presentation/` | Keyboard stand-in for the three buttons |
| `Tests/Game.Sim.Tests.asmdef` | `Assets/Tests/EditMode/` | Editor-only, NUnit |
| `Tests/RunSimulationTests.cs` | `Assets/Tests/EditMode/` | One test per invariant, each printing its number |

```bash
SKILL=<path-to>/skills/unity-game-brief
mkdir -p Assets/Scripts/Sim Assets/Scripts/Presentation Assets/Tests/EditMode
cp "$SKILL"/resources/Sim/* Assets/Scripts/Sim/
cp "$SKILL"/resources/Presentation/* Assets/Scripts/Presentation/
cp "$SKILL"/resources/Tests/* Assets/Tests/EditMode/
```

Then rename the assemblies and the namespace to the project's own, and replace the courier rules
with the game's. **The skeleton is a shape, not content** — the useful part is the boundary, the
three doors and one test per invariant; the lanes and the gate are there so the shape has something
in it to read.
