---
name: unity-combat
description: >-
  Make one swing one damage event, in 2D and 3D: a damage struct and a
  receiver with teams, invincibility and death as a state; hit and hurt
  layers; query hitboxes that own a swing id and a hit list, opened by
  animation windows; knock-back through the motor; cast-per-step projectiles;
  bullet patterns as data. Load for: "the enemy takes damage twice from one
  swing", "the sword hits every frame", "my attack does not hit the enemy",
  "spikes drain all my health", "the shot goes straight through the
  sentry", "knockback pushes it into the wall", "add health and damage".
  Flash, shake and hit pause are unity-game-feel; what an enemy decides is
  unity-game-ai; doors and pickups are unity-interaction.
---

# unity-combat — one swing is one damage event, and the engine will not enforce it for you

> **`OnTriggerEnter` counts collider pairs, not attacks.** A sword that crosses a sentry with a
> head and a torso hurtbox raises it twice; a target that steps out and back in raises it again;
> `OnTriggerStay` raises it every step. Nothing in PhysX or Box2D knows what a swing is. So the
> trigger is demoted to a question — what is in this volume now — and the **attack** keeps the
> list of who it has already hit.

Every hit in the game takes the same path, and each stage has one job:

```
window ────────► hitbox ─────────────► DamageInfo ──► IDamageable ───────► events
Open() / Close()  swing id + hit list   a struct       Health: team,        Damaged, Died
from the Animator query per fixed step  on the stack   invincibility,       presentation and
or a game timer   who, once per swing                  death as a state     the controller's push
```

| Stage | File | Decides | Never decides |
|---|---|---|---|
| Window | the game's attacking state, or `unity-animation`'s window behaviour | When the active frames start and end | Who is hit |
| Attack | `resources/Hitbox3D.cs`, `Hitbox2D.cs`, `Projectile3D.cs`, `Projectile2D.cs` | Who is offered the hit, once per swing | Whether it lands |
| Message | `resources/DamageInfo.cs` | Nothing — it carries amount, source, team, point, direction, knock-back, stun, tags, swing id | — |
| Receiver | `resources/Health.cs` | Whether it lands: alive, other team, not invincible | Movement, effects, destruction |

## Symptom → where to look

First match wins. Stop at the first cause you confirm.

| Symptom | Go to |
|---|---|
| One swing takes two hearts, or the count rises with the number of colliders | §1 |
| The target loses health on every step the weapon touches it | §1 |
| The hit never lands: the swing passes through and nothing is reported | §2 |
| It lands on the attacker, on a teammate, or through a wall | §2 |
| The window stays open after the attack was interrupted | §3 |
| The runner loses every heart at once on a hazard, or is hit again while flying back | §4 |
| A fast shot passes through the sentry or a thin wall | §5 |
| Knock-back leaves the target inside a wall, or it does not move at all | §6 |
| Hits land and nothing shows: no flash, no pause, no sound | `unity-game-feel` |

## 0. Set up the path

1. **Three layers beyond the level's own**: `Body` (what the solver pushes), `Hurtbox` (where a
   character can be hit), `Hitbox` (trigger hitboxes only). `Hurtbox` collides with nothing in
   the matrix: a query reads its mask, not the matrix. The matrices for 3D and 2D:
   `reference/hit-and-hurt-layers.md`.
2. **The receiver goes on the root**, hurtboxes on its children: `Health` on the sentry, a
   trigger `BoxCollider` on the torso bone and a `SphereCollider` on the head, both on
   `Hurtbox`. Size them from constants, never from the renderer — `unity-rigged-character` →
   `reference/gameplay-rig.md`.
3. **The hitbox is an empty child with `Hitbox3D`** (or `Hitbox2D`), `hurtMask` = `Hurtbox`,
   `team` set. No collider, no body.
4. **Open and close it from the window**, and from the game's own state on interruption:

```csharp
// Beside the Animator. AttackWindowBehaviour sits on the attack state, open 0.25, close 0.55.
public sealed class StrikeWindow : MonoBehaviour, IAttackWindowReceiver
{
    public Hitbox3D hitbox;
    public void OnWindowOpen(string id)                    { if (id == "strike") hitbox.Open(); }
    public void OnWindowClose(string id, bool interrupted) { if (id == "strike") hitbox.Close(); }
}
```

5. **The controller listens for the hit** and moves itself; presentation listens to the same
   event and moves nothing:

```csharp
health.Damaged += info => motor.Push(info.KnockbackVelocity, info.stun);   // the one writer
health.Died    += info => state = RunState.Down;                           // a state, not Destroy
```

6. **Register what a journey reads**: `GameProbe.Count("damageEvents", () => health.DamageEvents)`,
   `GameProbe.Count("swings", () => hitbox.SwingId)`, `GameProbe.Register("hitboxOpen", () => hitbox.IsOpen)`.

## 1. The hit lands twice, or once per step

Count before changing anything: log `hitbox.SwingId`, `hitbox.ContactsThisSwing` and the
target's `DamageEvents` when the window closes. A 0.2 s window over two hurtboxes reads about
`contacts=20 events=1`; `events` equal to `contacts` means nothing is deduplicating.

1. **Damage is dealt from `OnTriggerEnter` / `OnTriggerStay` on the weapon.** Enter fires per
   collider pair and again on every re-entry; Stay fires every step. Move the damage call out of
   the callback and into a hitbox with a hit list.
2. **The hit list is keyed by collider, not by receiver.** Two hurtboxes are two keys. Resolve
   `collider.GetComponentInParent<IDamageable>()` first and list that.
3. **The list is never cleared, or cleared on the wrong edge.** It is cleared in `Open()`, and
   only there. Cleared in `Close()` it is empty for a re-entrant open; cleared per step it is no
   list.
4. **Two windows are open.** An AnimationEvent pair whose closing event was skipped leaves the
   first swing live under the second. `Open()` here ends a swing that is still open; the cause
   is §3.
5. **Two hitbox components answer one window** — one on the prefab and one on its variant, or a
   trigger collider left on the weapon beside the query. Search the hierarchy for both.
6. **Invincibility hides it.** A runner with 0.6 s of invincibility takes one hit from a broken
   attack; the sentry, which has none, takes ten. Test the attack against a target whose
   `invincibleSeconds` is 0.

A move that is meant to hit three times is three windows, each a new swing id — never one window
with the rule switched off. The contract and the list: `reference/attack-windows.md`.

## 2. The hit never lands

Work down. First match wins.

1. **The window never opened.** Read `hitboxOpen` in the probe while the attack plays. Closed
   throughout: the state has no window behaviour, the receiver is not beside the Animator, or
   the Animator is culled off screen — `unity-animation` → `reference/events-and-windows.md`.
2. **The query leaves triggers out.** Hurtboxes are triggers. In 3D pass
   `QueryTriggerInteraction.Collide`; never rely on `Physics.queriesHitTriggers`. In 2D a
   `new ContactFilter2D()` has `useTriggers == false` — set it. Both files here do.
3. **`ContactsThisSwing` is 0 with the gizmo over the target.** `hurtMask` lacks the `Hurtbox`
   layer; the hurtbox objects are not on it — a child does not inherit its parent's layer; or
   `owner` is wrong. Left empty it is `transform.root`: a whole level object, when characters
   are parented under one, and every collider under the owner is skipped.
4. **`ContactsThisSwing` is above 0 and `HitsThisSwing` is 0.** In order: no `IDamageable` on
   any parent; same `team`; `blockMask` has a solid between owner and target (or the floor, when
   `originOffset` is at the feet); the receiver refused — dead, or invincible.
5. **The pose is stale.** A collider moved by a bone, a motor or a teleport reaches PhysX at the
   next physics step. After a respawn or a teleport call `Physics.SyncTransforms()` once.
6. **The volume is somewhere else.** Select the hitbox: its gizmo is the box that is queried, in
   world units, ignoring scale. A sprite flipped by negative scale does not mirror a 2D query;
   move the child.
7. **A fast, short swing stepped over the target.** Leave `sweep` on:
   `reference/melee-queries.md`.

Queries that miss for physics reasons: `unity-physics-3d` → `reference/queries.md`,
`unity-physics-2d` → `reference/queries-2d.md`.

## 3. The window outlives the attack

- **An AnimationEvent at 55% never fires when the state is left at 40%.** Open and close from a
  StateMachineBehaviour, which always closes — `unity-animation` →
  `reference/events-and-windows.md`.
- **The game closes too.** On hurt, stun, death, a cancelled attack or a return to the pool the
  attacking state calls `hitbox.Close()` itself. `Close()` is safe to call twice.
- **A window shorter than a fixed step still queries once**: `Close()` runs the query when no
  step has.

## 4. Damage every step, and being hit while already hit

- **Invincibility is a timer on the receiver**, started by a hit that lands: 0.6 s for the
  runner, 0 for a sentry meant to be hit in a combo. It is game state on the fixed clock; the
  blink is presentation — `unity-game-feel` → `reference/flash-and-squash.md`.
- **A hazard is an attack with a period.** Spikes deal 1 on contact and again every 1.0 s while
  the runner stays; they do not call `TakeDamage` from `OnTriggerStay`.
- **A kill plane sets `DamageTags.IgnoreInvincibility`.** Nothing else does.
- **Stun is shorter than invincibility** (0.15 s against 0.6 s), or the runner regains control
  with no time to leave.

Timers, hazards, stun and control lock: `reference/iframes-and-knockback.md`.

## 5. Projectiles pass through

A shot at 30 units/s moves 0.6 units per 0.02 s step. Anything thinner is stepped over, and
continuous detection does not help: triggers are not swept, and in 2D neither is a kinematic body.

- **The shot is a cast, not a body.** Each fixed step, cast its radius along `speed × dt`; move
  to the hit or to the end. `Projectile3D` and `Projectile2D` have no collider and no body.
- **The mask is `Hurtbox` plus the solid layers.** Without the solids it flies through walls;
  without `Hurtbox` it hits bodies, which are the wrong shape.
- **It ignores its owner and its team**, by hierarchy and by number, not by a layer per team.
- **Pool it.** Pool size = fire rate × lifetime × shooters — `unity-scene-flow` →
  `reference/pooling.md`.

Homing, patterns as data and the fixed-screen budget: `reference/projectiles.md`.

## 6. Knock-back through a wall

- **Knock-back is a velocity handed to whatever moves the character**, never a position write.
  `transform.position += push` and `Rigidbody.position` skip collision; `CharacterController.Move`,
  a motor's `Push` and a dynamic body's `linearVelocity` do not.
- **One writer.** `AddForce` beside a motor that assigns velocity lasts one step — route the
  push through the motor: `unity-2d-controller` → `reference/topdown-free.md`,
  `unity-3d-controller` → `reference/model-choice.md`.
- **Direction comes from the `DamageInfo`**, attacker's chest to the hurtbox, flattened onto the
  floor in 3D. From `transform.forward` of the target it sends a runner hit in the back towards
  the sentry.
- **Size the room to the push.** 8 units/s decaying at 50 units/s² travels 0.72 units at a
  0.02 s step.

## 7. Prove it

`templates/CombatJourneyTest.cs` builds a gate room from colliders, drives the runner through
`ScriptedRunInput`, and reads the probe:

| Test | Asserts |
|---|---|
| `Swing_OverTwoHurtboxes_IsOneDamageEvent` | Contacts ≥ 4, damage events exactly 1, and at no sample more events than swings |
| `SecondSwing_IsASecondDamageEvent` | Two presses, two events, swing ids 1 and 2 |
| `HitDuringInvincibility_IsNoDamageEvent` | A swing 0.2 s after a hit touches the runner and is refused; after 0.6 s the next lands; the runner was pushed and `JourneyAsserts.NeverInside` reports nothing |
| `FastShot_IsStoppedByAThinWall` | A 60 units/s shot stops at a 0.1-unit wall; no sample is past it; the sentry behind is untouched |

`COMBAT_JOURNEY_BREAK=hitlist`, `=iframes` and `=cast` each turn at least one test red. Run each once: a
gate nobody has seen fail proves nothing. Journeys and the probe: `unity-play-harness` →
`reference/journeys.md`.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Hit flash, hit pause, screen shake, particles, impact sounds | `unity-game-feel` |
| When a sentry attacks, what it sees, patrols, waves | `unity-game-ai` |
| Doors, switches, pickups, prompts | `unity-interaction` |
| Authoring the window on a state; clips, events, override controllers | `unity-animation` |
| Moving the character; how a motor applies a push | `unity-2d-controller`, `unity-3d-controller` |
| A callback or a query that fails for physics reasons | `unity-physics-3d`, `unity-physics-2d` |
| Pools, saving health between scenes, pause | `unity-scene-flow` |
| Health bars and damage numbers | `unity-game-ui` |
| The attack button, aim direction | `unity-input` |
| Cell-based attacks, range and turn order on a board | `unity-2d-grid` |
| Recorders, the probe contract | `unity-play-harness` |
| Damage over a network; who is authoritative | `unity-multiplayer` |
