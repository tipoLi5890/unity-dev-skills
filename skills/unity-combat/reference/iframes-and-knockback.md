# Invincibility, knock-back, stun and hazards that tick

> Part of the `unity-combat` skill. What happens after a hit lands is three timers and one
> velocity, each with one owner: invincibility on the receiver, stun and the push on the
> controller, the blink in presentation. A hazard that drains every heart in a second is a
> missing timer; a target inside a wall is a push that skipped its owner.

## 1. Three timers, three owners

| Timer | Runner | Sentry | Owner | Started by |
|---|---|---|---|---|
| Invincibility | 0.6 s | 0 | `Health` | A hit that lands |
| Stun (no control) | 0.15 s | 0.3 s — `stun` 0.3 on the runner's hitbox | The controller | Its `Damaged` handler, from `DamageInfo.stun` |
| Push decay | to rest in 0.16 s | same | The motor | The same handler |
| Blink, flash | 0.6 s, 0.1 s | — , 0.1 s | Presentation | The same event, reading `InvincibleRemaining` |

- **Stun is shorter than invincibility.** The 0.45 s between them is the runner's time to leave
  with control restored. Equal, and the first controllable step is also the first hittable one.
- **All of them count game time on the fixed clock** (`Time.fixedTime`). A hit pause at
  `Time.timeScale` 0 stops them together, so a pause does not eat invincibility —
  `unity-game-feel` → `reference/hit-stop-and-time.md`.
- **A sentry has no invincibility** so the runner's combo connects. What protects it from a
  double hit is the attacker's hit list alone, which is why §1 of the skill tests against it.

## 2. Invincibility

It is a time on the receiver, compared on every `TakeDamage`:

```csharp
public bool Invincible => Time.fixedTime < _invincibleUntil;
// on a hit that lands:
if (invincibleSeconds > 0f) _invincibleUntil = Time.fixedTime + invincibleSeconds;
```

- **A refused hit changes nothing and restarts nothing.** Restarted by refused hits, a runner
  standing in spikes is invincible for ever.
- **Other sources extend the same timer**: `health.GrantInvincibility(0.2f)` for a dash,
  `1.5f` after a respawn. It takes the later of the two ends and never shortens.
- **Do not implement it by switching hurtboxes off.** Shots then pass through the runner and
  hit what is behind, nothing counts the refusal, and a hurtbox re-enabled inside a hazard is a
  new trigger pair with its own surprises.
- **Do not implement it by changing layers.** A layer swap is global state that a pooled object
  carries into its next life.
- **`DamageTags.IgnoreInvincibility`** is for the kill plane and the crusher. An attack that
  carries it by habit removes the mechanic.
- **The blink is not the state.** Presentation reads `health.Invincible`; nothing reads the
  renderer to learn whether the runner can be hit — `unity-game-feel` →
  `reference/flash-and-squash.md`.

## 3. Knock-back goes through whoever moves the character

The `DamageInfo` carries `direction` and `knockback`; `info.KnockbackVelocity` is their product.
The character's controller subscribes to its own `Health.Damaged` and hands that velocity to its
one writer:

| The character is moved by | The push is | Stops at walls because |
|---|---|---|
| `TopDownMotor2D` | `motor.Push(info.KnockbackVelocity, info.stun)` | The solver resolves the dynamic body |
| `PlatformerController2D` | `run.Push(info.KnockbackVelocity, info.stun)` | The motor casts the move |
| A `CharacterController` | Added to the velocity of the one `Move` per frame, then decayed | `Move` slides along colliders |
| A dynamic `Rigidbody` | `body.linearVelocity = push` — assigned, not `AddForce` | The solver, with continuous detection for a hard launch |
| A `NavMeshAgent` | `agent.isStopped = true`, then `agent.Move(push * dt)` each frame of the stun | `Move` is clamped to the navigation mesh |
| A cell mover | A step of one cell in the push direction, refused when the cell is taken | The cell map |

```csharp
// CharacterController: the push is one more term of the single Move.
void OnDamaged(DamageInfo info) { _push = info.KnockbackVelocity; _stun = info.stun; }

// in the motor's update, where Move already is
Vector3 wish = _stun > 0f ? Vector3.zero : _planar;
_controller.Move((wish + _push + Vector3.up * _vertical) * dt);
_push = Vector3.MoveTowards(_push, Vector3.zero, pushDecel * dt);     // pushDecel = 50
_stun -= dt;
```

- **Never `transform.position += …` and never `Rigidbody.position = …`.** Both are teleports:
  no sweep, no slide, and the next step starts inside the wall.
- **Assign the launch, do not add it.** Added to whatever the target was doing, the same hit
  throws a sentry that was walking towards the runner half as far as one walking away.
- **Distance is `v² / (2 · decel)`**: 8 units/s against 50 units/s² is 0.64 units (0.72 at a
  0.02 step, where the push moves before it decays). Fix it before
  the room is built; a push into a second hazard is a combo the player cannot answer.
- **Direction is attacker to target, flattened in 3D** (`Hitbox3D.planar`). A launch upwards is
  a separate number the controller adds on `DamageTags.Heavy`, through its own jump path.
- **Heavier targets scale the speed, not the direction**: `info.KnockbackVelocity * 0.5f` for a
  large sentry, `0` for a turret.
- **`Rigidbody.AddForce` beside a motor that assigns velocity lasts one step.** That is the
  usual "knock-back does nothing" — `unity-2d-controller` → `reference/topdown-free.md`,
  `unity-3d-controller` → `reference/model-choice.md`.
- **Root motion fights it.** An Animator applying root motion during the hurt clip is a second
  writer; switch `applyRootMotion` off for the hurt state or let the clip be the push and send
  none — `unity-animation` → `reference/root-motion.md`.

## 4. Stun and control lock

- **Stun is a state of the controller**: input is ignored, the push decays, the attack window is
  closed. Read it from the probe (`GameProbe.SetState`), not from the Animator.
- **Close the attacker's own window when it is hit.** The `Damaged` handler calls
  `hitbox.Close()` before it applies the push, or a runner knocked back mid-swing still hits.
- **Presses made during the stun expire by themselves** when they are older than the input
  buffer (0.12 s). A stun shorter than the buffer lets one through, which is what makes a
  mashed escape work; call `input.ClearPresses()` when the stun starts where that is not wanted.
- **Super-armour is a receiver rule.** A sentry in a heavy wind-up takes the damage and ignores
  `stun` unless the hit has `DamageTags.Heavy`.
- **What the sentry does when stunned is its state machine's** — `unity-game-ai` →
  `reference/state-machine.md`.

## 5. Hazards that tick

Spikes do not deal damage from `OnTriggerStay`: it runs every step, it stops when a body falls
asleep, and its rate changes with the fixed step. A hazard is an attack with a period — the same
query hitbox, held open and reopened on a timer:

```csharp
// On the spikes, beside a Hitbox3D with team = CombatTeam.Neutral, tags = Hazard,
// owner = this object, hurtMask = Hurtbox.
public sealed class HazardPulse : MonoBehaviour
{
    public Hitbox3D hitbox;
    public float interval = 1f;
    float _next;

    void OnEnable()  { hitbox.Open(); _next = Time.fixedTime + interval; }
    void OnDisable() { hitbox.Close(); }

    void FixedUpdate()
    {
        if (Time.fixedTime < _next) return;
        hitbox.Open();                       // a new swing: everybody still inside is offered it again
        _next += interval;
    }
}
```

| Rule | Value | Why |
|---|---|---|
| First hit | On contact | The window is always open, so the step that finds the runner hits |
| Repeat | Every 1.0 s while inside | Longer than the 0.6 s of invincibility, so the tick is never refused |
| Damage | 1 | — |
| Knock-back | 8 units/s, away from the hazard's centre | Carries the runner out of a small hazard in one hit |
| Team | `Neutral` | Sentries are hurt too; leave them out with `hurtMask` or the hitbox's `team` |

- **Set `owner` on a hazard's hitbox.** Left empty it is `transform.root`; a hazard parented
  under a level object then treats every character under that object as itself.
- **A period shorter than invincibility is decided by the invincibility.** Poison at 0.25 s
  against 0.6 s of invincibility ticks every 0.75 s. Damage over time that must tick at its own
  rate carries `IgnoreInvincibility` and no knock-back, and is applied by a status the receiver
  owns, not by a volume.
- **Contact damage from a sentry's body is the same shape**: a `Hitbox3D` the size of the body,
  team `Sentry`, reopened every 1.0 s, with the body layers still colliding so the runner cannot
  walk through.
- **A kill plane** is a `Neutral` hit with `amount = 999` and `IgnoreInvincibility`, or a direct
  transition to the fallen state. It does not `Destroy`.
- **In 2D** the same component with `Hitbox2D`.

## 6. Checks

| Check | How |
|---|---|
| A hit inside invincibility is refused, and the next one after it lands | `templates/CombatJourneyTest.cs`, third test; `COMBAT_JOURNEY_BREAK=iframes` turns it red |
| The push never ends inside a wall | Same test: `JourneyAsserts.NeverInside` over the samples; in 2D `JourneyInvariants2D.NeverInside2D` |
| Spikes take one heart per second, not three in a step | Stand the runner in them for 2.5 s of game time; assert `damageEvents` is 3 and never rises by more than 1 between two samples |
| Stun ends before invincibility | Register both as probe values; assert no sample has control restored and `Invincible` false within 0.3 s of a hit |
| Knock-back distance | Read the runner's position 0.3 s after the hit: 0.72 units from where it stood at a 0.02 step, within 0.1 |
