# Attack windows — a swing id, a hit list, and two edges that always arrive in pairs

> Part of the `unity-combat` skill. An attack is three spans — wind-up, active, recovery — and
> only the active one can hurt. That span is a **window**: something opens it, something always
> closes it, and between the two edges the hitbox offers each target the hit once. The window
> says when; it never says who.

## 1. The contract

`resources/Hitbox3D.cs` and `resources/Hitbox2D.cs` expose the same surface:

| Member | Does |
|---|---|
| `int Open()` | Ends a swing still open, increments `SwingId`, empties the hit list, resets the per-swing counters, remembers the pose for the sweep. Returns the id |
| `void Close()` | Ends the swing. Queries once first when no fixed step ran while it was open. Safe when already closed |
| `IsOpen`, `SwingId` | State |
| `HitsThisSwing`, `ContactsThisSwing`, `TotalHits` | Accepted hits; colliders the queries returned, the owner's own left out; accepted hits over the component's life |
| `Landed` | Event: `(IDamageable target, DamageInfo info)` for a hit the receiver accepted |

Between the edges, on every fixed step, each collider the query returns goes through this, in
order, and the first rule that fails drops it:

1. It is not a child of `owner`.
2. Some parent implements `IDamageable`, and it is alive.
3. `CombatTeam.CanDamage(team, target.Team)`.
4. The target is not in this swing's hit list.
5. Nothing on `blockMask` lies between the owner's chest and the contact point.
6. The target is **added to the hit list** — and only then offered the `DamageInfo`.

Step 6 comes before the receiver answers on purpose: a target that refuses for invincibility has
had this swing's one chance. Listed after the answer instead, a runner whose timer runs out in
the middle of a long swing is hit by the tail of the attack it had already survived.

Step 5 comes before step 6 for the opposite reason: a target behind a pillar is not offered the
hit at all, so it can still be hit when the swing carries past the pillar.

## 2. The swing id

- **One per `Open()`**, never reused by that hitbox. It rides in `DamageInfo.swingId`.
- **It is how two events are told apart afterwards.** A log line `swing=7` twice on one sentry
  is a broken hit list; `swing=7` then `swing=8` is two attacks, and the question moves to why
  there were two windows.
- **The receiver does not dedupe on it.** Two hitboxes each start at 1, and the receiver would
  need a table per attacker. The attacker owns the list because the attacker knows what a swing
  is.
- **Register it**: `GameProbe.Count("swings", () => hitbox.SwingId)`. A journey then asserts
  `damageEvents <= swings` at every sample.

## 3. Windows from animation

The active frames are authored on the Animator state with `AttackWindowBehaviour`, which gives
one close for every open however the state is left — `unity-animation` →
`reference/events-and-windows.md`. The hitbox does not implement that interface itself: the
receiver has to sit beside the Animator, which is on the model child, and the hitbox sits on a
weapon bone or in front of the root. A forwarder joins them:

```csharp
// On the Animator's GameObject. Decides nothing: it turns a named window into two calls.
public sealed class StrikeWindow : MonoBehaviour, IAttackWindowReceiver
{
    public Hitbox3D strike;      // the runner's swing
    public Hitbox3D kick;        // a second volume, its own window id

    public void OnWindowOpen(string id)
    {
        if (id == "strike") strike.Open();
        else if (id == "kick") kick.Open();
    }

    public void OnWindowClose(string id, bool interrupted)
    {
        if (id == "strike") strike.Close();
        else if (id == "kick") kick.Close();
    }
}
```

| Number | Start | Why |
|---|---|---|
| Open | 0.25 of the state | The wind-up is what the defender reads |
| Close | 0.55 | The recovery is what the defender punishes |
| Active time at 0.5 s per swing | 0.15 s — seven fixed steps | Fewer than three steps and one long frame decides the hit |

- **Normalised time survives a retimed clip**; seconds do not. A design rule in seconds —
  "hittable for 0.2 s" — is a game timer started by `OnWindowOpen`.
- **A pair of AnimationEvents is not a window.** The closing event is skipped when the state is
  left before it, and the hitbox stays live through the hurt animation.
- **Under `AnimatorCullingMode.CullCompletely` the behaviour does not run off screen** and the
  window never opens. A sentry that attacks off screen uses `CullUpdateTransforms`, or a window
  in game time (§4).
- **The Animator updates in `Update`, the hitbox queries in `FixedUpdate`.** A window that opens
  and closes inside one frame may see no fixed step; `Close()` covers it with one query after
  `Physics.SyncTransforms()`.

## 4. Windows in game time

With no Animator — a frame-animated sprite, a sentry with no rig, a journey — the attacking
state owns the timer:

```csharp
// In the controller's fixed step. swingSeconds = 0.2, startup = 0.1.
if (_state == RunState.Attack)
{
    _t += Time.fixedDeltaTime;
    if (!_opened && _t >= startup) { hitbox.Open(); _opened = true; }
    if (_opened && _t >= startup + swingSeconds) { hitbox.Close(); Enter(RunState.Recover); }
}
```

For a sprite clip, pick the timer from the frames: at 12 frames per second, active frames 3 to 4
are `startup = 2 / 12`, `swingSeconds = 2 / 12`.

## 5. Closing on interruption

The behaviour closes when the state is left. The game closes as well, because the game knows
sooner and knows about cases the Animator never sees:

| The attacker | Who closes |
|---|---|
| Is hit and enters hurt | The controller's `Damaged` handler: `hitbox.Close()` before it applies the push |
| Dies | The death transition |
| Cancels into a dash or a jump | The state's exit |
| Is returned to a pool, or its room unloads | `OnDisable` — the hitbox drops the window without querying |
| Is paused | Nothing: at `Time.timeScale` 0 no fixed step runs and no query is made |

One exit function per state, called from every way out, is the whole discipline:

```csharp
void Exit(RunState state)
{
    if (state == RunState.Attack) hitbox.Close();     // harmless when already closed
}
```

Assert it from outside: `GameProbe.Register("hitboxOpen", () => hitbox.IsOpen)` and a journey
rule that it is never true while `state` is not the attacking one.

## 6. Moves that hit more than once

| Move | Shape |
|---|---|
| A three-hit combo on one button | Three states, each with its own window |
| One long clip that strikes twice — a slash out and a slash back | Two `AttackWindowBehaviour`s on the state, ids `strike` and `strike-2`, both forwarded to the same hitbox: each `Open()` is a new swing |
| A spin that keeps hurting while it turns | One hitbox, reopened on a timer: `Close(); Open();` every 0.25 s for as long as the state lasts |
| A beam held on a target | `oncePerSwing` off, with the target's own invincibility as the rate — the one use of that switch |
| A sweep that should hit each of several sentries once | One window: the list is per target, so every sentry in the arc is hit once |

- **Never one window with the list switched off to get "multi-hit".** The hit count then depends
  on how many hurtboxes the target has and on the step rate.
- **Damage per window may differ.** Set `hitbox.damage` and `hitbox.knockback` in
  `OnWindowOpen` from a table keyed by window id; the last hit of a combo carries
  `DamageTags.Heavy` and the launch.
- **Buffer the next press, do not chain windows.** The press made during recovery waits in the
  input buffer and is spent on the first step the state allows: `canAttack && input.TryUse(…)`
  — `unity-input` → `reference/reading-input.md`.

## 7. Checks

| Check | How |
|---|---|
| One open, one close, per attack | Log both edges with `SwingId`; interrupt the attack at 40% with a hit and read the close |
| The hit list holds | `templates/CombatJourneyTest.cs`, first test; `COMBAT_JOURNEY_BREAK=hitlist` turns it red |
| A second swing hits again | Second test: events 2, swing ids 1 and 2 |
| No window outside the attacking state | The journey rule in §5 |
| A hitch does not skip the window | Set `Time.captureDeltaTime = 0.25f` for one frame across the window in a test; the sentry still loses one heart |
