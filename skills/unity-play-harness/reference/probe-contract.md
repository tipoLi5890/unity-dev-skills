# The probe contract: one line the agent can read

> Part of the `unity-play-harness` skill. What the line contains, where the values come from on
> Unity 6, and the four ways to read it. `resources/GameProbe.cs` is the file; copy it into a
> Runtime assembly with the game.

A probe is not instrumentation. Instrumentation is temporary and gets deleted; this is a
**contract** the game keeps so that every other tool in the skill — situations, journeys,
complaint-to-test — has something to read. One line, one object, always the same keys.

## The keys

| Key | Type | Source on Unity 6 |
|---|---|---|
| `schema` | int | `GameProbe.Schema`. Bump it when a key changes meaning, never when one is added |
| `frame` | int | `Time.frameCount` |
| `t` · `ut` · `dt` | float | `Time.time` · `Time.unscaledTime` · `Time.deltaTime` |
| `timeScale` | float | `Time.timeScale` — a 0 here explains most "it froze" reports before anything else is read |
| `scene` | string | `SceneManager.GetActiveScene().name` |
| `situation` | string | Set by `Situations.Enter`; `null` when the game booted normally |
| `state` | string | The game's own state machine, through `SetState(() => _run.Phase.ToString())` |
| `cam` | string | `Camera.main != null ? Camera.main.name : null` — a `null` here is why the screenshot is black |
| `pos` · `vel` | `[x,y,z]` | `transform.position` · `Rigidbody.linearVelocity` (Unity 6 name; it was `velocity` before) |
| `speed` | float | `vel.magnitude` |
| `ready{}` | object | Every readiness member, each re-evaluated this frame |
| `allReady` | bool | Every member true **and** at least one member registered |
| `counts{}` | object | Named ints: spawned hazards, pooled pickups, live agents |
| `custom{}` | object | Game-specific values: lane index, distance to the gate, LOD level |
| `batch` · `playing` | bool | `Application.isBatchMode` · `Application.isPlaying` |

Two hooks put anything else in there, and both take a delegate rather than a value:

```csharp
GameProbe.Ready("laneCollider", () => _lane != null && _lane.Collider != null);
GameProbe.Register("gateDist", () => Vector3.Distance(_runner.position, _gate.position));
GameProbe.Count("hazards", () => _hazards.Count);
GameProbe.SetState(() => _run.Phase.ToString());
GameProbe.SetPlayer(() => _runner, () => _runnerBody);
```

**A delegate cannot go stale; a bool can.** The failure this design exists to prevent is a
readiness flag set true during a load that was later cancelled, which then reads ready forever.
Re-evaluating the predicate on every snapshot makes that impossible.

**`allReady` means every member the probe currently holds** — the ones the game registered at
startup plus the ones the current situation added. So only register members that are genuinely
required for play; an optional subsystem in the set makes `allReady` false forever and every
journey that waits on it times out. A single situation's own requirement is
`SituationHandle.IsReady`, which asks only about that situation's members.

**`state` comes from the game's state machine, not from a copy.** If the probe holds its own
enum, the day the two disagree is the day the probe starts lying — and it will be the day
something is broken, because that is when the paths diverge.

## Why the JSON is hand-written

`JsonUtility` does not serialise dictionaries, and `ready{}`, `counts{}` and `custom{}` are all
dictionaries with names the game chooses at runtime. The writer in `GameProbe.cs` is ~40 lines,
formats every float `F3` under `CultureInfo.InvariantCulture` — a machine on a comma-decimal
locale otherwise emits `9,800` and every downstream parser breaks — and escapes strings. No
package, no `Newtonsoft`, nothing to add to the manifest.

## Four ways to read it

**1 · A live Editor** — sub-second, no recompile, no domain reload. This is the one to reach for
while iterating.

```bash
unity command eval 'return GameProbe.Json();' --format json
```

Three things to know, all of which cost a round if you learn them the hard way:

- **There is no `using` directive in `eval`** — it compiles a statement block. `GameProbe` is in
  the global namespace precisely so this call has nothing to qualify.
- **The return value lands at `data.result.result`**, inside an envelope whose outer `success`
  only means the command reached the Editor. → `unity-debug` → `reference/editor-control.md`
- **Outside Play mode the call must not throw.** `GameProbe.Json()` answers
  `{"schema":1,"playing":false}` — a fact, not an exception, so a polling loop keeps polling
  instead of dying while the Editor enters Play mode.

**2 · A project command** — `resources/Editor/ProbeCommands.cs` registers `probe`,
`probe_ready`, `situation_list` and `situation_enter`, gated on `HAS_UNITY_PIPELINE` so a
project without the CLI package still compiles. After adding it: `unity command recompile` →
poll `unity command recompile_status` → `unity list` to confirm what registered.

```bash
unity command probe                       # the same line, no eval quoting
unity command probe_ready                 # allReady + missing[], for a wait loop
```

**3 · The log** — any run at all, including one a human drove and a build on a device:

```bash
grep '\[PROBE\]' Editor.log | tail -5
# [PROBE] frame=412 t=6.833 scene=Run situation=approach-gate state=Approach
#         pos=[0.000,1.200,-12.000] speed=9.800 ready=3/4 missing=laneCollider
```

Attach `GameProbeReporter` to a boot object. It logs every 30 frames plus one line the frame
readiness completes, and it disables itself when `Debug.isDebugBuild` is false — so a release
player carries the probe and prints nothing.

**4 · Inside a test** — `GameProbe.Snapshot()` returns the object, no parsing:

```csharp
ProbeSnapshot s = GameProbe.Snapshot();
Assert.IsTrue(s.allReady, "missing: " + string.Join(",", GameProbe.MissingReady()));
Assert.Less(s.speed, 12f, "entry speed at gateDist=" + s.Number("gateDist"));
```

## From the shell

`scripts/probe.py` wraps path 1 and unwraps both envelope levels for you:

```bash
python3 scripts/probe.py --project-path .                    # pretty-print the snapshot
python3 scripts/probe.py --key state                         # just that key, for a shell test
python3 scripts/probe.py --watch 0.5                         # one line per poll
python3 scripts/probe.py --wait-ready --timeout 20           # exit 1 listing the missing members
```

`--wait-ready` is the piece that replaces a `sleep` in a shell script: it polls until `allReady`
or until the timeout, and on failure prints the member names rather than "timed out".

## What it costs, and what ships

One snapshot evaluates a handful of delegates and builds a ~300-byte string. `Camera.main` is a
tag lookup and the most expensive part of it; sampling every frame for a 20-second journey is
fine, sampling every frame of a shipped game is not the intent.

Decide these three deliberately:

- **`GameProbe` and `Situations` ship.** They are small, they carry no gameplay, and they are the
  reason the next complaint can be turned into a test. Stripping them costs more than they weigh.
- **`GameProbeReporter` is gated** on `Debug.isDebugBuild || Application.isEditor`, so the logging
  — not the probe — is what a release build loses.
- **`ProbeCommands.cs` is Editor-only** by assembly, so it cannot reach a player build at all.

Confirm on your version, three things:

- **`Rigidbody.linearVelocity` is the name your Editor resolves** — it is the Unity 6 spelling.
- **`Camera.main` returns the camera you mean** when more than one is tagged `MainCamera`; `cam`
  in the line is how you find out that it does not.
- **Whether `sceneUnloaded` for the outgoing scene raises before the incoming scene's `Awake`.**
  `GameProbe.ResetOnSceneUnload` is off by default because the other order wipes the
  registrations `Awake` just made. Turn it on only after checking, and only where each scene
  registers its own hooks. A persistent boot object wants it off either way; the unconditional
  reset before the first scene of every session is what keeps a stale registry out of the run.
