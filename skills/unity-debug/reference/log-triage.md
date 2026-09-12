# Instrumenting and reading the log

The editor can stay open the whole time. `Debug.Log` output goes to Editor.log at runtime, and
stopping play flushes it.

```bash
LOG=~/Library/Logs/Unity/Editor.log        # Editor-prev.log = previous session
grep -n "\[RUN\]" "$LOG" | tail -80
grep -nE "error CS|Exception|NullReference" "$LOG" | tail -20
```

When a human is in the loop: **focus Unity (it recompiles) → Play → do the action → stop → "done".**
Scripts only recompile when the window regains focus or on `Ctrl/Cmd+R`; CLI runs always compile
fresh.

---

## Tagged trace logs

Use a **unique grep prefix** so one `grep` isolates your trace from Unity's noise.

- **Lifecycle transitions**, once each: `Awake`, `Start`, state changes, scene setup.
- **Per-frame dumps, THROTTLED**, or the log floods:

```csharp
private int _f;
void FixedUpdate() {
    if (++_f % 20 == 0)   // ~0.4 s at 50 Hz
        Debug.Log($"[RUN] f#{_f} state={GameManager.Instance?.State} playing={IsPlaying()} " +
                  $"tScale={Time.timeScale} pos={rb.position} vel={rb.linearVelocity} " +
                  $"grounded={isGrounded} lane={currentLane} " +
                  $"players={GameObject.FindGameObjectsWithTag(\"Player\").Length} last={_last}");
}
```

- **Collisions**, so phantom hits are visible:

```csharp
void OnCollisionEnter(Collision c) { _last = $"COLLIDE {c.gameObject.name} [{c.gameObject.tag}]"; }
void OnTriggerEnter(Collider o)    { _last = $"TRIGGER {o.name} [{o.tag}]"; }
```

These fields answer 90% of runtime questions: state-machine state, paused flag, `Time.timeScale`,
`rb.position`, `rb.linearVelocity`, `rb.isKinematic`, `rb.constraints`, grounded, **count of tagged
duplicates**, and the last collision. Unity 6 uses `rb.linearVelocity`, not `.velocity`.

**Also log the numbers a test asserts on.** A test that prints
`[BOX] world width=0.50 laneSpacing=1.30` tells you *why* it passed, and keeps telling you after
the next change — a bare green tick does not.

`resources/DevDebug.cs` is a project-agnostic drop-in that does all of the above plus an on-screen
panel. Copy it into `Assets/`, attach it, **delete it when finished.**

---

## Symptom → cause

| What the log shows | Likely cause |
|---|---|
| `pos` never changes, `vel≈0`, state=Playing | Something zeroing velocity — a collider in the path, or code |
| `pos` moves on X but not Z | Invisible wall on the blocked axis (overlapping collider / duplicate body) |
| state=`MainMenu`/`GameOver`, `playing=False` | Never started, or instant game-over |
| `tScale=0` | Paused; `FixedUpdate` will not run |
| `players x2` | Duplicate prefab instance — often overlapping and jamming physics |
| `last=` shows a hit you did not expect | Phantom collider — see `unity-gotchas.md` |
| `kinematic=True` unexpectedly | Body will not respond to velocity |
| `error CS####` | Compile error — scripts are running stale. Fix first |
| `NullReferenceException` | Read the stack; a serialized ref or singleton is null |

The winning move is usually: find the **last good line** against the **first bad line**, and read
`last=` on the frame the state flips.

---

## On device there is no Editor.log

```bash
adb logcat -s Unity                                        # Debug.Log + Unity native errors
adb logcat -c && adb logcat -s Unity AndroidRuntime DEBUG  # clean run incl. Java/native crashes
```

| Works in editor, dies on device | First suspect |
|---|---|
| `DllNotFoundException` / instant startup crash | ABI mismatch — plugin lacks arm64-v8a (`unity-android-release`) |
| `NullReferenceException` only in the built player | Managed stripping removed a reflection target — `link.xml` |
| Feature silently does nothing | Runtime permission never granted — check the MERGED manifest |
