# The probe scene: make a device run readable

A device run is only as good as what the app says about itself. The probe is a **dev-only scene**
in a host project (never shipped) with one `MonoBehaviour` that exercises the feature under test
through its **public API** and reports in a shape a script can assert on.
`templates/DeviceProbe.cs` is the skeleton.

## The line contract

One tag, three kinds of line, all through `Debug.Log` so they reach logcat and the iOS console
alike:

```
[Probe] state Stopped -> Starting (running=False)     # every state change, old -> new
[Probe] connected pad-1 (Acme Pad fw=1.2 paired=True)       # every external event, with its payload
[Probe] diag fps=60 latencyMs=18 packets=120 dropped=0 count=2               # once a second, k=v
[Probe] error DeviceUnavailableException: …           # every error, type first
```

| Rule | Why |
|---|---|
| **A fixed tag in square brackets** | `grep -E '\[Probe\] state A -> B'` is the whole assertion language |
| **`old -> new` on transitions** | A step asserts the *edge*, not the level — "is Running" also matches a run that never left it |
| **`k=v` pairs on the diag line, stable key order** | Parsed with one regex; diffable between devices and builds |
| **Once a second, not once a frame** | A 60 Hz log floods the ring buffer and evicts the line you wait on |
| **Everything the screen shows is also logged** | iOS has no screenshot; Android's is a round trip. The screen is for the human, the log is for the driver |
| **Log the build identity first** | SDK/package version, `Application.version`, platform — so a stale install is visible in line one |
| **Log every file you write with its full path** | The driver pulls exactly those |

## What goes on screen

The same head line (state · running · rate · the two numbers that matter), the last error, and the
last ~20 log lines, in a font sized from the screen (`Screen.height / 36`). Large, high-contrast,
no layout — a human glances at it from arm's length while holding a cable. Runtime IMGUI details
are in `unity-game-ui`.

`Screen.sleepTimeout = SleepTimeout.NeverSleep` in `Start()` — a test that pauses for a human must
not lose the screen while waiting.

## Modes are buttons, and buttons log

When a run compares configurations (controller A vs B, low vs high quality, route A vs B), put **one large
button per axis** at the bottom of the screen. On Android the driver taps it by coordinate; on iOS
the human does. Either way the handler's first act is a log line:

```csharp
Log("mode -> " + next);      // the driver waits on this, not on the tap
```

A mode switch **tears the old pipeline down completely and builds a new one** (dispose, recreate,
restart), so each mode is measured from a clean start and a leak between modes shows up as a
failure rather than as a skewed number.

## Sequences beat conversations

For N configurations, do not ask the human to press N buttons. Add one button that runs the whole
sequence unattended and logs a `DONE` line:

```
for each config:  log "step <name> requested …"
                  create → start → log "running actual=<negotiated values>"
                  settle 2 s → record 10 s → stop → write file → log "wrote <path>"
                  compute summary → log "result name=… k=v …"
finally:          log "sequence DONE dir=<path>"
```

Wrap each step in `try/catch` that logs `step <name> FAILED <Type>: <message>` and **continues** —
one unsupported configuration must not cost the other results. Log what was *requested* and what
was *actually negotiated* side by side; the difference is usually the finding.

## Reaching inside without changing the product

The probe lives in `Assembly-CSharp`; the SDK's internals are not visible to it, and adding a
public member for a test is the wrong trade. Two acceptable reaches:

- **Reflection onto one private field**, to subscribe to a raw stream the facade does not expose:
  `typeof(Facade).GetField("_inner", NonPublic | Instance)`. Guard for null; it is a dev scene.
- **`[assembly: InternalsVisibleTo]`** for an editor/test assembly — not for the probe scene.

Hook lazily from the once-a-second tick (the inner object may not exist until the first start), and
**expect the first one or two diag lines to read zero** — no window is full yet.

## One analyser for every configuration

If the run measures a signal, compute the numbers **in the probe, with one code path for every
mode and both platforms**, and log them. Two different measurement paths cannot be compared, and a
number produced on the device survives a lost file. Keep raw dumps (CSV, JSON) as the second source
for offline analysis.

## Cleanup

The probe is dev-only: a scene outside the shipped build list, a build method of its own
(`-executeMethod …BuildProbe`), and the artifact under an ignored `Builds/`. Headless builds rewrite
`ProjectSettings.asset` (bundle id, signing team) — read that diff before committing it.
