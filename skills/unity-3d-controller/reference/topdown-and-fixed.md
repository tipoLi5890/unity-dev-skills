# Top-down, fixed cameras and the lane runner

> Part of the `unity-3d-controller` skill. Three 3D set-ups where the camera does not orbit:
> the depot seen from above (`resources/TopDownController3D.cs`), a room framed by fixed
> cameras (the same controller), and the lane run (`resources/LaneRunnerController.cs`), which
> has no stick at all.

## 1. Axes that do not turn

Under a camera that never rotates, "up on the stick" is a direction in the world, decided once:

| Camera | `view` | Stick up means |
|---|---|---|
| Straight overhead, north at the top of the screen | empty | World +Z |
| Overhead or isometric, yawed (45° is the usual) | the camera | The camera's heading, flattened — or its up vector when it looks straight down |
| Fixed cameras, one per room | the live camera | That camera's heading, **latched while the stick is held** |

**The latch.** With `holdAxesWhileHeld` on (the default) the axes are re-read from `view` only
when the stick is at rest. Without it, a cut from the gate room's east camera to its west one
reverses "forward" under a held stick: the runner turns round, walks back through the doorway,
the camera cuts back, and the doorway becomes a trap. With it, the runner keeps walking the way
it was going and the new axes apply from the next push.

On a camera cut, reassign `view` to the new output camera if the cameras are separate objects;
with Cinemachine the output camera is one object and `view` never changes.

Movement is otherwise the third-person rule: flatten, cross, clamp —
`reference/third-person.md`, section 1. There is no jump: the depot floor is level, `gravity`
(19.6) only handles a floor that ends, and a design that needs a jump under an overhead camera
uses `ThirdPersonController` with `view` set to the fixed camera.

## 2. Facing: aim first, movement second

Move and aim are separate inputs and the body follows the aim when there is one:

| `RunInput` | The body faces |
|---|---|
| `hasAimPoint` (a pointer) | From the runner to `aimPoint`, flattened |
| `aim` non-zero (a stick) | `aim` on the same axes as the move |
| Neither | The move direction; at rest, whatever it last faced |

`Facing` is that direction as a unit vector, kept at rest, and it is the value to hand to a
weapon or an interaction check — not `transform.forward`, which lags it by the turn.

- **The pointer's ground point comes from a plane or a ray, in the input reader** — the plane
  at the height of what is aimed, not the floor.
  `unity-input` → `reference/pointer-and-aim.md` has the parallax rule and the code.
- **Closer than 0.2 units the direction to the pointer is noise**; the controller keeps the last
  facing instead of spinning on the spot.
- **`turnRate` 720 shows weight; 0 snaps.** A twin-stick depot wants the muzzle on the pointer
  now: fire along `Facing` and let the body catch up.
- **`faceAim` off** gives a character that always faces where it walks — an action-adventure
  under a fixed camera.

`Moving` is "the input asks for movement", for the Animator; `Velocity` is what the body did.

## 3. Click-to-move is a different owner

A click names a destination. Getting there round shelves is pathfinding, and the component that
does it also wants the transform. So click-to-move does not go through the motor: the
controller **releases** the transform and a `NavMeshAgent` takes it.

```csharp
void OnWorldClick(Vector3 point)                 // the reader has already rejected clicks on the UI
{
    if (topDown.Owns) topDown.Release();         // Move stops; the CharacterController is disabled
    agent.enabled = true;
    agent.Warp(transform.position);
    agent.SetDestination(point);
}

void Update()
{
    // Any stick input cancels the walk and takes the transform back.
    if (!topDown.Owns && input.Peek().move.sqrMagnitude > 0.04f)
    {
        agent.ResetPath();
        agent.enabled = false;
        topDown.Reclaim();
    }
}
```

| Detail | Why |
|---|---|
| Release before enabling the agent | An enabled agent and an enabled `CharacterController` on one object fight every frame; the character slides back |
| `Warp`, not `transform.position` | The agent has its own idea of where it is |
| `IMoveFacts3D` while released | The controller's `Velocity` is stale; point the Animator bridge's `mover` at a component that reports `agent.velocity` |
| A game that is only click-to-move | Has no `CharacterController` at all — `unity-navigation` → `reference/recipes.md` |

Telling a world click from a UI click, and reading the point:
`unity-input` → `reference/pointer-and-aim.md`. Baking, stopping distance, corner stutter: `unity-navigation`.

## 4. The lane runner

The lane run has no stick, no walls and no ground to find, so it has no motor. Position is a
formula of four numbers, and `LaneRunnerController` on a kinematic `Rigidbody` is the owner:

```
position = origin + forward · Distance + right · LaneOffset + up · height
```

| Number | Default | Rule |
|---|---|---|
| `lanes` · `laneWidth` | 3 · 1.3 | Lane `i` is at `(i − 1) × 1.3`: −1.3, 0, +1.3. The middle lane is 1 |
| `laneChangeTime` | 0.15 s | `LaneOffset` goes from the old centre to the new over this time, eased (`SmoothStep`) or linear, then is set to the centre exactly |
| `forwardSpeed` → `maxForwardSpeed` | 12 → 20 | `Speed = min(max, start + speedRamp × seconds run)` |
| `speedRamp` | 0.1 units/s per second | 80 s from 12 to 20 |
| `apexHeight` · `timeToApex` | 1.2 · 0.35 | `height = v0·t − g·t²/2` from the time in the air: the apex is the designed one at any step |

**The lane is the truth; the transform catches up.** `Lane` changes on the step the change
starts. Hazard logic that asks "which lane is the runner in" reads `Lane`; a check that needs
the body — is it still overlapping the old lane's hazard — uses the trigger, which is why the
runner carries a `Rigidbody`.

**A change is an edge, not a level.** The controller asks for a change when `move.x` crosses
`laneThreshold` (0.5) from rest. Holding does not repeat: a held key walks one lane. That makes
every device the same input:

| Device | Arrives as |
|---|---|
| Keyboard, D-pad | `move.x` at ±1 while held |
| Stick flick | `move.x` past 0.5, then back to rest |
| Swipe | A pulse on the virtual stick, 0.08 s — `unity-input` → `reference/touch-and-on-screen.md`, gestures as actions |
| Tap on the left or right half | The same pulse from two on-screen buttons |

The pulse has to outlast one fixed step (0.02 s), because the controller reads the level in
`FixedUpdate`.

**One change is remembered.** A request during a change is kept — the last one wins — and
starts on the step the current change ends. A double swipe therefore crosses two lanes in 0.3 s
without the second being lost, and a swipe back during a change returns the runner to the lane
it left. A request past the outer lane is counted in `Refused` (the bump sound) and moves
nothing.

**Hazard spacing follows from the change time.** A hazard has to be readable for
`laneChangeTime + 0.25 s` of reaction: at 12 units/s that is 4.8 units of sight, and at the
ramped 20 it is 8. Spawn distances scale with `Speed`, not with a constant —
`unity-gameplay` → `reference/level-metrics.md`, the lane section.

**Far from the origin.** Past a few thousand units positions lose precision and the runner
shimmers. Every 1000 units, shift the track and call `ShiftOrigin(delta)` with the same vector
in the same frame; `Distance` is unaffected, so the probe and the score do not see it.

**Jump.** `Launch` through `TryUse`, grounded only; the buffer on the input source lets a press
0.12 s before landing jump again on landing. A slide under a barrier is the same shape with a
collider height instead of a `height`.

## 5. Checks

| Check | Expect |
|---|---|
| `LaneRunner_Change_LandsOnTheLaneInTheConfiguredTime` | x = +1.3 within 0.01 after 0.15 s (to the step); no sample beyond 1.305; two lefts with the second asked mid-change end on −1.3; a third is refused |
| The same with `CONTROLLER3D_JOURNEY_BREAK=lane` | Red: 0.45 s is not 0.15 |
| Hold the right key | One lane, not two |
| Probe `lane` against `laneOffset` during a change | `lane` steps at the start; `laneOffset` follows over 0.15 s |
| Fixed cameras: hold the stick through a cut | The runner keeps its world direction |
| Overhead: probe `speed` on a diagonal | 5, not 7.07 |
