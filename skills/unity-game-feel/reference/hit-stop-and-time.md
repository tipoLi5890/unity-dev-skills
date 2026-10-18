# Hit stop, slow motion and the clock — one owner of `Time.timeScale`

> Part of the `unity-game-feel` skill. Hit stop as a global time dip and as a per-object freeze,
> why the dip written at the call site breaks, the request-queue owner in `resources/HitStop.cs`,
> slow motion, pause beside both, and which code must run on unscaled time.

## 1. Two ways to stop a hit

| Kind | What freezes | Use it for | Cost |
|---|---|---|---|
| Global dip — `Time.timeScale` to 0.05 for 60–120 ms | Everything on scaled time: physics, animators, particles, scaled timers | A hit the player gave or took; the fail | Everything stops, including things far from the hit; one owner is mandatory |
| Per-object freeze — the attacker's and the victim's animators and bodies only | Two characters | A crowd fight where the rest of the world must keep moving; a networked game, where time cannot stop | More code: each frozen thing needs its state saved and put back |

Start with the global dip. It reads strongest and it is one call. Move to per-object freezes
when a playtest shows the world stopping for a hit nobody was looking at.

Numbers: 50–80 ms for a light hit, 100–120 ms for a heavy one, never above 150 ms (it reads as a
hang). Scale 0.05, not 0: a deltaTime of exactly zero is a divide-by-zero in somebody's code, and
0.05 is indistinguishable from a freeze for 100 ms.

> **When not to stop at all.** In a game where the player times the next input against an object
> in flight (a returned ball, a falling note), any freeze or slow motion during play moves that
> object off the beat they are reading, and a simulation clock that ignores `timeScale` makes the
> picture and the clock disagree. A tennis game kept the rally at full speed and spent its impact
> on flashes, rings, speed lines and a 4 cm camera dip instead:
> `reference/sports-readability.md` §3.

## 2. Why the call-site version breaks

The version everybody writes first, on the thing that was hit:

```csharp
IEnumerator Stop(float seconds)          // on the sentry — wrong in three ways
{
    float before = Time.timeScale;
    Time.timeScale = 0.05f;
    yield return new WaitForSecondsRealtime(seconds);
    Time.timeScale = before;
}
```

1. **Two overlap.** The second reads `before` while the first is live and stores 0.05. The
   first ends and restores 1 — ending the second early — then the second ends and restores 0.05.
   Time stays at 5 % for good.
2. **The requester dies.** The hit that froze the game is the hit that destroys the
   sentry. The coroutine dies with it; the restore never runs.
3. **It begins inside slow motion or a pause.** It restores whatever it read, which may be a
   pause another system is about to lift, or a slow-motion value that system is about to
   change.

`templates/FeelJourneyTest.cs` runs this exact coroutine under `FEEL_JOURNEY_BREAK=restore`,
and the overlap and destroyed-requester tests go red.

## 3. One owner with a request queue

`resources/HitStop.cs` is the only code that writes `Time.timeScale`. A request is a value — an
end time on the unscaled clock and a scale — in a list the owner holds:

```csharp
HitStop.Request(0.08f);           // a hit: 80 ms at the default 0.05
HitStop.Request(0.6f, 0.3f);      // slow motion: 600 ms at 30 %
HitStop.SetBase(0f);              // pause; SetBase(1f) resumes
HitStop.Clear();                  // drop every request and put the base back now
```

| Rule | Why |
|---|---|
| The lowest scale among live requests applies | Two hits do not multiply into 0.0025 |
| Time comes back when the **last** request ends | Overlap ends with the later stop, not the earlier |
| It comes back to the **base**, the value before the first request | A stop inside slow motion returns to the slow motion |
| Nothing of the requester is kept | A destroyed requester cannot take the restore with it |
| The timer reads `Time.unscaledTime` | A timer on scaled time would never finish the stop it is timing |
| `OnDisable`, `OnDestroy` and `OnApplicationQuit` restore | Leaving play mode mid-stop does not leave the Editor at 5 % |
| `[DefaultExecutionOrder(-10000)]` | The scale is settled before any gameplay `Update` reads `deltaTime` |

Serialised limits and their defaults:

| Field | Default | Meaning |
|---|---|---|
| `defaultScale` | 0.05 | Scale for a request that names none |
| `maxSeconds` | 1 | Longest single request |
| `maxContinuousSeconds` | 0.25 | Longest run of overlapping freezes (scale under 0.2), from the first. A stream of hits freezes a quarter of a second, not the sum |
| `cooldownSeconds` | 0.05 | Freezes are refused this long after one ends, so a stream of hits is not a stream of freezes |

`Accepted` and `Refused` count requests; put them on the probe. A `Refused` that climbs during a
fight is the budget working; one that climbs at rest is a system asking every frame.

`HitStop.Enabled = false` refuses every request: the global switch for a debugging session. The
reduce-motion setting works one level up — `Feedback` skips the time channel.

**Something else that writes `timeScale`** is noticed, not fought: the owner compares the value
with the one it last wrote, logs `[HITSTOP] Time.timeScale was written outside HitStop`, and
adopts the foreign value as its base. Find the writer:

```bash
grep -rn "timeScale *=" Assets --include='*.cs'     # every hit that is not HitStop.cs is a second owner
```

## 4. Pause beside a hit stop

Pause is a game phase owned by the state machine in the boot scene (`unity-scene-flow` →
`reference/game-state-and-pause.md`). Its `GameState` can write `timeScale` itself
(`ownsTimeScale`, on by default). Two writers again — and the failure is concrete: a stop is live
at 0.05, the player pauses, `GameState` stores 0.05 as the value to resume to and sets 0; the
stop's unscaled timer runs out during the pause; resume writes 0.05 back and nothing ever
restores it.

Wire one owner:

```csharp
// In the boot scene, where GameState is built. GameState never writes timeScale; HitStop does.
gameState.ownsTimeScale = false;
gameState.Changed += (from, to) => HitStop.SetBase(to == GamePhase.Paused ? 0f : 1f);
```

With the base at 0 the lowest scale is 0 whatever is live, so the pause holds. A stop's timer is
unscaled and keeps running through the pause: a stop that straddles a pause is spent when play
resumes. That is right — replaying 80 ms of freeze after a menu closes reads as a stutter.

A slow-motion field is the same call with a different base: `SetBase(0.5f)` on entering,
`SetBase(1f)` on leaving. Hit stops inside it dip under 0.5 and come back to 0.5.

## 5. Per-object freeze

When the world must keep moving, freeze the two characters instead:

```csharp
// On the sentry and the runner. Saves what it changes and puts exactly that back.
public sealed class LocalFreeze : MonoBehaviour
{
    [SerializeField] Animator animator;
    [SerializeField] Rigidbody body;
    float _speed; Vector3 _velocity; bool _kinematic, _frozen; float _until;

    public void Freeze(float seconds)
    {
        if (!_frozen)
        {
            _speed = animator != null ? animator.speed : 1f;
            if (body != null) { _velocity = body.linearVelocity; _kinematic = body.isKinematic; }
            if (animator != null) animator.speed = 0f;
            if (body != null) body.isKinematic = true;     // a kinematic body ignores gravity and contacts
            _frozen = true;
        }
        _until = Mathf.Max(_until, Time.unscaledTime + seconds);    // overlap extends, never shortens
    }

    void Update() { if (_frozen && Time.unscaledTime >= _until) Thaw(); }
    void OnDisable() { if (_frozen) Thaw(); }                       // a pooled sentry comes back clean

    void Thaw()
    {
        _frozen = false;
        if (animator != null) animator.speed = _speed;
        if (body != null) { body.isKinematic = _kinematic; if (!_kinematic) body.linearVelocity = _velocity; }
    }
}
```

The 2D form swaps `Rigidbody` for `Rigidbody2D` and `isKinematic` for `bodyType`
(`RigidbodyType2D.Kinematic`, then the saved type back). A controller that moves the body itself
(a kinematic motor) also needs its own `Frozen` flag that skips `Move` — the motor is the owner
of the transform, and only it can stop itself.

The same capture-once rule as the flash applies: save the state when the freeze starts from rest,
never when one is already holding, or the second freeze saves the frozen state as "the original".

## 6. What must not run on scaled time

| System | Clock | Why |
|---|---|---|
| The hit stop's own timer | `Time.unscaledTime` | Otherwise it never ends |
| Flash duration (`RendererFlash.unscaledTime` on) | Unscaled | The flash ends on time inside the stop it accompanies |
| The squash that comes with a hit (`Tween`, `unscaled` true) | Unscaled | It is seen through the stop, not after it |
| Sound cooldowns and voice ends (`SfxPlayer`) | Unscaled | Audio runs in real time; a scaled cooldown never expires in a stop |
| Haptic durations | Unscaled | Motors run in real time; a scaled timer leaves them on through a pause |
| Camera shake | Cinemachine's impulse manager reads scaled time unless `IgnoreTimeScale` is set — `unity-camera` → `reference/shake-and-blends.md` | A shake started by a hit should play through the stop |
| UI animation, menus, the pause screen | Unscaled; `Animator.updateMode = AnimatorUpdateMode.UnscaledTime` for animated UI | The pause screen must animate at `timeScale` 0 |

And what must stay scaled: gameplay timers (invincibility, cooldowns, coyote time, the attack
window), physics, AI ticks, spawners. They are the game, and the game is what stopped. Combat's
invincibility counts on the fixed clock for exactly this reason (`unity-combat` →
`reference/iframes-and-knockback.md`).

`Time.fixedDeltaTime` is not scaled by `timeScale` — fewer fixed steps run, each the same length.
In slow motion at 0.3 a 50 Hz simulation steps 15 times a second, and interpolation on the
bodies is what keeps the motion smooth. For a long slow-motion shot, lower `fixedDeltaTime` in
proportion and put it back after; for a 100 ms stop, leave it.

## 7. Measuring it

Every probe sample carries `timeScale`, so the dip is a column in the journey's timeline:

```bash
python3 - "$JOURNEY_OUT/gate-room-hit/timeline.jsonl" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if '"timeScale"' in l]
dip = [r for r in rows if r.get("timeScale", 1) < 1]
print("samples", len(rows), "dipped", len(dip),
      "from", dip[0]["ut"] if dip else None, "to", dip[-1]["ut"] if dip else None)
EOF
```

The dip's length in unscaled seconds is the number a person tunes against; the journey asserts
only that time is back inside the window plus one frame.
