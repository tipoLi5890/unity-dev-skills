# The damage contract — one struct, one interface, one receiver

> Part of the `unity-combat` skill. Every source of harm in the game — a swing, a shot, spikes,
> a crusher — builds the same struct and hands it to the same interface. The attack decides who
> is offered the hit; the receiver decides whether it lands; nobody else changes health.

## 1. `DamageInfo`

`resources/DamageInfo.cs`. A struct, filled on the stack and passed with `in`:

| Field | Type | Set by the attack to | Read by |
|---|---|---|---|
| `amount` | `int` | Hearts or hit points; 1 for the runner's swing | The receiver |
| `source` | `GameObject` | The attacker's root, not the hitbox child; `null` for a hazard | Score, aggro, the kill feed |
| `team` | `int` | `CombatTeam.Neutral` 0, `Runner` 1, `Sentry` 2 | The friendly-fire rule |
| `point` | `Vector3` | Contact position in the world | Sparks, damage numbers |
| `direction` | `Vector3` | Unit vector, attacker towards target; z is 0 in 2D | Knock-back, the hurt animation's side |
| `knockback` | `float` | Launch speed, units/s; 8 for a swing, 4 for a shot | The receiver's controller |
| `stun` | `float` | Seconds without control; 0.15 | The receiver's controller |
| `tags` | `DamageTags` | `Melee`, `Projectile`, `Hazard`, `Heavy`, `IgnoreInvincibility` | Receiver rules and presentation |
| `swingId` | `int` | The hitbox's swing counter; 0 for a shot or a hazard | Logs and journeys |

- **A struct, because a hit is a value.** A class is an allocation per hit and invites a receiver
  to keep the reference and read it after the attacker has reused it.
- **Whole numbers for health.** A float health reaches `0.0000001` and a sentry survives a hit
  that should have killed it. Scale up (100 points) when fractions are wanted.
- **`direction` and `knockback` are separate** so a receiver can scale the speed (a heavy sentry
  takes half) without renormalising.
- **Add a field when a second system needs it, not before.** Element, critical flag and armour
  penetration belong here the day a receiver reads them.

## 2. `IDamageable`

```csharp
public interface IDamageable
{
    int Team { get; }
    bool IsAlive { get; }
    bool TakeDamage(in DamageInfo info);   // true when it was applied
}
```

- **The attack finds it from the collider**: `hurtbox.GetComponentInParent<IDamageable>()`. The
  hurtboxes are children, the receiver is on the root, and that walk is what makes two hurtboxes
  one target.
- **`TakeDamage` returns whether it landed.** The attack needs it: a shot that was refused still
  stops, a swing that was refused plays no impact sound, and a journey counts landed hits.
- **Anything can implement it.** A crate that breaks, a gate switch that is struck, a shield
  that absorbs and forwards the rest to the `Health` behind it.
- **The walk is short and runs only while a window is open.** Do not cache receivers in a
  dictionary keyed by collider until a profiler names it.

## 3. `Health`

`resources/Health.cs`, on the root of whatever can be hit.

| Member | Meaning |
|---|---|
| `team`, `max`, `invincibleSeconds` | Serialised: 1, 3, 0.6 |
| `Current`, `IsAlive`, `Invincible`, `InvincibleRemaining` | State |
| `DamageEvents`, `RefusedEvents`, `LastHit` | What a journey and a log read |
| `TakeDamage(in info)` | The only way health goes down |
| `Heal(n)`, `GrantInvincibility(s)`, `Revive()` | The only other writers |
| `Damaged`, `Died`, `Refused` | Events |

`TakeDamage` refuses, in this order, and a refusal changes nothing:

1. Not alive, or `amount <= 0`.
2. Same team — `CombatTeam.CanDamage(attacker, target)` is false.
3. Invincible, unless the hit carries `DamageTags.IgnoreInvincibility`. This one raises
   `Refused` and counts in `RefusedEvents`.

Then: subtract and clamp at 0, count the event, start the invincibility timer, raise `Damaged`,
and raise `Died` when `Current` reached 0. **State is written before any event is raised**, so a
handler that reads `Current` or `IsAlive` sees the result of the hit it is told about.

## 4. Events are for listeners, not for rules

`Damaged` is raised exactly once per hit that lands, `Died` exactly once per life. What may hang
on them:

| Handler | Belongs on the event |
|---|---|
| The character's own controller applying the push and the stun | Yes — it is the owner of that body reacting to its own health |
| Flash, blink, particles, sound, camera shake, the health bar | Yes — presentation |
| Score, a dropped pickup, the wave counter, opening the gate when the last sentry falls | **No** |

The last row is gameplay that must run exactly once, and an event cannot promise that for its
listeners: a pooled sentry that subscribes in `OnEnable` and never unsubscribes pays out twice on
its second life, and a listener destroyed with its scene pays out nothing. Put those in the
state transition the game owns:

```csharp
// SentryBrain. The transition is the single place the consequences live.
void OnDied(DamageInfo info)
{
    if (_state == SentryState.Down) return;      // the transition is entered once
    _state = SentryState.Down;
    hitbox.Close();
    _run.SentryDown(this, info.source);          // score, drop, wave count — one call
}
```

- **Subscribe in `OnEnable`, unsubscribe in `OnDisable`**, always in pairs.
- **A handler never calls `TakeDamage` on the same receiver.** Thorns, reflect and chain damage
  are queued and applied on the next fixed step, or one hit recurses into a second event.
- **A handler that throws stops the handlers after it.** Keep them to one line that forwards.

## 5. Teams

Three numbers cover the courier run: `Neutral` 0, `Runner` 1, `Sentry` 2.

```csharp
public static bool CanDamage(int attackerTeam, int targetTeam)
    => attackerTeam == Neutral || targetTeam == Neutral || attackerTeam != targetTeam;
```

- **Neutral damages everybody and is damaged by everybody**: spikes hurt the runner and the
  sentry alike; a crate breaks for either.
- **The team is checked twice on purpose.** The hitbox passes teammates over so they never enter
  its hit list or stop a shot; the receiver refuses them so a hand-built `DamageInfo` cannot get
  round the rule.
- **A team is a number on the receiver, not a layer.** A layer per team multiplies the matrix by
  the number of teams and still cannot express a hazard. Layers say what kind of collider this
  is; teams say whose side it is on.
- **Changing sides is assigning `team`** — a sentry turned by a pickup, a shot reflected back
  (relaunch it with the reflector's team and owner).

## 6. Death is a state

`Health` never calls `Destroy` and never switches anything off. At 0 it stops accepting damage
and raises `Died` once.

- **`Destroy` in a damage handler removes the object while its other handlers still run**, kills
  the death animation and the sound, and leaves every hit list and AI target pointing at a
  destroyed component.
- **The sequence belongs to the character's state machine**: `Down` → hurtboxes off (or leave
  them: `IsAlive` is false, so every attack passes over) → the clip plays out → return to the
  pool. `unity-game-ai` → `reference/state-machine.md` owns the sentry's states.
- **`Revive()` when the pool hands the object out again.** `OnEnable` does not reset health on
  purpose: a sentry deactivated by room streaming keeps its hearts.
- **Shots and hitboxes pass over the dead.** A corpse that still stops shots is a hurtbox whose
  receiver is not answering `IsAlive`.

## 7. Checks

| Check | How |
|---|---|
| One event per swing | `templates/CombatJourneyTest.cs`; `GameProbe.Count("damageEvents", () => health.DamageEvents)` |
| `Died` raised once per life | Count it in a handler, kill the sentry with a swing whose `oncePerSwing` is off, assert 1 |
| No leaked subscription | Take a sentry from the pool three times, kill it each time, assert the score rose by three kills |
| Refusals are counted, not silent | `RefusedEvents` rises when a hit arrives inside invincibility |
