# Bodies and the simulation step

Part of the `unity-physics-2d` skill. SKILL.md §0, §1 and §4 state each rule in a line; this file
holds the body types, the step and the movement calls in full.

## Three body types, chosen by who owns the motion

`Rigidbody2D.bodyType` is `RigidbodyType2D.Dynamic`, `Kinematic` or `Static`. `isKinematic` is the
deprecated spelling; read and write `bodyType`.

| | Dynamic | Kinematic | Static |
|---|---|---|---|
| Moved by | Forces, gravity, velocity, contacts | `linearVelocity`, `MovePosition`, `angularVelocity` | Nothing |
| Gravity and `AddForce` | Applied | Ignored | Ignored |
| Pushed by contacts | Yes | No | No |
| Collides with | Everything | Dynamic only, until `useFullKinematicContacts` | Dynamic only |
| Courier-run use | A pushed pickup, debris, a runner driven by velocity | A sentry, a moving platform, a launch pad, a cast-driven runner | Rooftops, depot shelving, yard walls |

A collider with no `Rigidbody2D` on itself or a parent belongs to one hidden static body shared by
the scene. That is correct for geometry that never moves and wrong for anything that does: every
move rebuilds its shapes, and nothing riding it is carried: a static body has no velocity to
hand to a contact.

A collider attaches to the nearest `Rigidbody2D` up the hierarchy — read
`Collider2D.attachedRigidbody` rather than guessing. A second `Rigidbody2D` on a child cuts that
child out of the parent's body; the two then move independently and the parent's Transform drags
the child's pose against its own simulation. One body per moving thing.

## `simulated`

`Rigidbody2D.simulated = false` takes the body, every attached collider and every attached joint
out of the world in one write: no contacts, no callbacks, no query hits. It is the cheap way to
park a pooled sentry or pickup, and the reason a perfectly configured object can be silent — the
checkbox sits on the body, not on the collider the reader is looking at.

`Physics2D.simulationLayers` does the same to whole layers. Both are all bits set by default.

## Mass, gravity and damping

- `gravityScale` multiplies `Physics2D.gravity` (`(0, -9.81)`) per body. A top-down depot runner
  sets it to `0`; a platformer that integrates its own gravity sets it to `0` and writes velocity.
- `mass` is ignored while `useAutoMass` is on: the mass then comes from each collider's `density`
  and area. A crate that got heavier after its sprite was resized has auto mass on.
- `linearDamping` and `angularDamping` are the Unity 6 names; `drag` and `angularDrag` are
  deprecated spellings of the same values.
- `linearVelocity` is the Unity 6 name; `velocity` still compiles with a deprecation warning.
  `linearVelocityX` and `linearVelocityY` write one axis without reading the other.
- Friction and bounce come from a `PhysicsMaterial2D` on the collider, or on the body through
  `Rigidbody2D.sharedMaterial`. A runner that sticks to a wall while falling has friction against
  it: give the runner's collider a material with `friction = 0`, not the level's.

## Constraints

`Rigidbody2D.constraints` takes `RigidbodyConstraints2D.FreezePositionX`, `FreezePositionY`,
`FreezeRotation`, `FreezePosition` and `FreezeAll`. `freezeRotation` is the shortcut for the
rotation bit, and every character body sets it — an unfrozen box rolls off the first ledge it
clips. A constraint freezes the solver's output only: writing `position` or the Transform still
moves a frozen axis.

## The step

- `Time.fixedDeltaTime` is the step, `0.02` s unless the project set `Project Settings → Time →
  Fixed Timestep`. Halving it doubles the physics cost and changes how far a body travels per step.
- `Physics2D.simulationMode` picks who runs it:

| `SimulationMode2D` | The step runs | Use |
|---|---|---|
| `FixedUpdate` | After every `FixedUpdate`, at the fixed step | The default, and the one to keep |
| `Update` | After every `Update`, with the frame's delta time | Nothing that must behave the same at two frame rates |
| `Script` | Only when code calls `Physics2D.Simulate(step)` | Deterministic tests, replays, turn-based resolution |

- `Physics2D.Simulate(deltaTime)` advances the default physics scene one step. Own the step for a
  test, then give it back:

  ```csharp
  SimulationMode2D before = Physics2D.simulationMode;
  Physics2D.simulationMode = SimulationMode2D.Script;
  try
  {
      for (int i = 0; i < 50; i++) Physics2D.Simulate(Time.fixedDeltaTime);
  }
  finally { Physics2D.simulationMode = before; }
  ```

  `Physics2D.autoSimulation` is the obsolete switch for the same thing.
- `velocityIterations` (`8`) and `positionIterations` (`3`) are solver quality. A stack that
  sinks into itself wants more position iterations; a missed collision does not.
- `Physics2D.maxTranslationSpeed` (`100`) caps a body at that many units of travel **per step**,
  without a warning: 5,000 units/s at the default step. Check it in one line before trusting
  either number — give a body `linearVelocity = new Vector2(10000, 0)`, step once, read how far
  it went.
- `useSubStepping`, `maxSubStepCount` (`4`) and `minSubStepFPS` (`30`) split a long step into
  shorter ones when the frame rate drops. Off by default.

## Moving a body

| Call | On Dynamic | On Kinematic | Notes |
|---|---|---|---|
| `linearVelocity = v` | Moves, collides, is pushed back | Moves, is never stopped | Write in `FixedUpdate` |
| `AddForce(f)` | Accelerates over the step | Ignored | `ForceMode2D.Impulse` for a jump or a launch |
| `MovePosition(p)` | Travels to `p` during the next step, stopped by what its collision-detection mode catches: `Discrete` still tunnels on a long step | Travels to `p` during the next step, stopped by nothing; riders are carried | Interpolation stays correct |
| `position = p` | The body teleports at once; the Transform follows at the next step | Same | No sweep; queries see the new pose at once; breaks interpolation for a frame |
| `transform.position = p` | Teleports, synchronised at the next step or by `Physics2D.SyncTransforms()` | Same | The body's velocity is unchanged |

A moving platform is Kinematic and uses `MovePosition` or a velocity so that the contact solver
knows it is moving; a platform moved by its Transform has no velocity, and a Dynamic body
standing on it is left behind. After a `MovePosition` step the platform's `linearVelocity` reads
back as it was before the call — zero for a platform that only ever uses `MovePosition` — so a
script that wants the platform's speed computes it from the two positions.

## Interpolation

The step runs fewer times than the frame at 120 fps and more times at 30. A body drawn at its last
stepped pose therefore moves in bursts.

- `RigidbodyInterpolation2D.Interpolate` draws between the last two stepped poses: one step of
  latency, smooth. Use it on the runner and on anything the camera follows.
- `RigidbodyInterpolation2D.Extrapolate` predicts ahead from velocity: no latency, overshoot on
  every sudden stop.
- `None` on everything else — interpolation costs per body per frame.

With interpolation on, `transform.position` in `Update` is the drawn pose and
`Rigidbody2D.position` is the simulated one. Gameplay in `FixedUpdate` reads the body; a camera in
`LateUpdate` reads the Transform. Writing the Transform of an interpolated body cancels the
interpolation for that step.

## Sleeping

A body sleeps after `Physics2D.timeToSleep` (`0.5` s) below both `Physics2D.linearSleepTolerance`
(`0.01`) and `Physics2D.angularSleepTolerance` (`2`). Asleep, it is skipped by the solver and its
`Stay` callbacks stop; `Enter` and `Exit` are unaffected.

- `Rigidbody2D.sleepMode` is `RigidbodySleepMode2D.StartAwake`, `StartAsleep` or `NeverSleep`.
  `NeverSleep` on one body keeps a damage zone ticking; on every body it removes the saving that
  sleep exists for.
- `IsSleeping()`, `IsAwake()`, `Sleep()` and `WakeUp()` read and force the state. A new contact, a
  force or a non-zero velocity wakes the body.
- Check before diagnosing: log `IsSleeping()` on the frame the callback stops. `False` moves the
  fault to the trigger's layers or to `Collider2D.callbackLayers`.

## `Rigidbody2D.Slide`

Unity 6 carries a move-and-slide call on the body, present with the same signature in 6000.3 and
6000.4:

```csharp
Rigidbody2D.SlideResults r = body.Slide(velocity, Time.fixedDeltaTime, movement);
```

`Rigidbody2D.SlideMovement` configures it:

| Field | Meaning |
|---|---|
| `maxIterations` | How many slide bounces one call may resolve |
| `surfaceSlideAngle` | A hit on a surface shallower than this slides; steeper stops |
| `gravity`, `gravitySlipAngle` | Gravity applied by the call, and the slope above which it slips |
| `surfaceUp` | The reference direction for those angles |
| `surfaceAnchor` | Direction and distance probed to stay attached to a surface while moving down a slope |
| `layerMask`, `useLayerMask`, `SetLayerMask(mask)` | What the slide collides with |
| `selectedCollider` | Use one attached collider instead of all |
| `useAttachedTriggers` | Whether trigger colliders on the body take part in detection |
| `useSimulationMove` | Move with `MovePosition` during the step instead of instantly |
| `useNoMove` | Compute the result and move nothing |
| `startPosition`, `useStartPosition`, `SetStartPosition(p)` | Slide from a position other than the body's |

`Rigidbody2D.SlideResults` returns `position`, `remainingVelocity`, `iterationsUsed`, `slideHit`
and `surfaceHit` — the last two are `RaycastHit2D`, so `surfaceHit.collider != null` is the ground
answer and `surfaceHit.normal` is the slope.

`new Rigidbody2D.SlideMovement()` is not neutral: `gravity` is `(0, -9.81)`, `surfaceAnchor` is
`(0, -1)`, both angles are `90`, `maxIterations` is `3` and `useSimulationMove` is `false`. Left
alone, one call from rest applies its own gravity and snaps the body onto any surface within one
unit below it. Set `gravity` and `surfaceAnchor` on purpose.

`Slide` is a query plus a move: it obeys the rules in
`reference/queries-2d.md`, ignores one-way effectors as every query does, and
suits a Kinematic body. Whether a character uses it, a cast-and-velocity motor or a dynamic body is
a movement-model decision — `unity-2d-controller` → `reference/model-choice.md`.
