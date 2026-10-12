# 3D — third-person, first-person, fixed or overhead camera, lane runner

> Part of the `unity-gameplay` skill. Four types that share a physics vocabulary and differ in
> where the camera sits, which decides what "forward" means to the stick. Worked settings: the
> **gate room** — walk to the switch, the gate opens — and the **lane run**, three lanes 1.3
> units apart with the middle lane numbered 1.

## The constraints

| Constraint | Third-person | First-person | Fixed or overhead camera | Lane runner (one-thumb casual) |
|---|---|---|---|---|
| View · projection | Behind the character · perspective | Through its eyes · perspective | From above at a fixed pitch · perspective with a narrow FOV, or orthographic | Behind and above, fixed · perspective |
| Movement model | Free; stick is relative to the **camera** | Free; stick is relative to the **body** | Free in world axes, or click-to-move | Lane index plus forward speed |
| Transform owner | `CharacterController`, or a dynamic `Rigidbody` | `CharacterController` | `CharacterController`, or a `NavMeshAgent` for click-to-move | The run controller itself, on a kinematic `Rigidbody` |
| Facing | Turns towards the move direction | Yaw on the body, pitch on the camera only | Towards movement, or towards the aim point on the ground | Fixed forward |
| Camera | Orbits; collides with the world | Is the head | Does not rotate; frames the room or follows at a fixed offset | Fixed offset; widens with speed |
| Level unit | Kit module (2 or 4 units) | Kit module | Room | Lane width × chunk length |
| Animation | Full body, always visible | Arms at most; world sees a full body only in multiplayer | Full body, small on screen — silhouettes matter more than detail | Run cycle, lane lean, jump, hit |

Underneath all four: **exactly one component writes the character's position.** A
`CharacterController` with a non-kinematic `Rigidbody`, a `NavMeshAgent` with a
`CharacterController`, root motion with a script that also calls `Move` — each is two owners,
and the symptom is always jitter or a character that slides back to where it was.

| Choose | When |
|---|---|
| `CharacterController` | A person on foot. Steps, slopes and walls are handled; it pushes nothing and is pushed by nothing unless code says so |
| Dynamic `Rigidbody` | The character must be shoved, carried and knocked about by other bodies, and you will write grounding yourself |
| `NavMeshAgent` | Destinations, not directions: click-to-move, followers — `unity-navigation` |
| Root motion | The animation is the authority on distance travelled — `unity-animation` → `reference/root-motion.md` |

## Numbers to decide first

| Number | Gate-room start | Decides |
|---|---|---|
| Scale | 1 unit = 1 metre; the runner is 1.8 tall | Whether physics, lighting and imported models agree |
| Capsule | height 1.8, radius 0.4, skin width 0.04, step offset 0.3, slope limit 45° | Doors, corridors, stairs — `reference/level-metrics.md` §5 |
| Speeds | walk 2, run 5, sprint 7 units/s; 0.15 s to reach, 0.1 s to stop | Room sizes: a 10-unit room is 2 s across at a run |
| Turn rate (third-person) | 720°/s | Whether a reversal is a snap or an arc |
| Jump | apex 1.2 in 0.35 s → gravity 19.6, jump velocity 6.86 | What can be vaulted; project gravity stays at 9.81 for props |
| Third-person camera | distance 4, pivot 1.5 above the feet, vertical FOV 50, pitch −30° to 70° | Corridor width (at least the distance), ceiling height |
| First-person camera | eye height 1.6, vertical FOV 60 (about 91° horizontal at 16:9), pitch ±85°, near clip 0.1 | Sense of speed and of scale; a near clip above the capsule radius sees through walls |
| Overhead camera | pitch 55°, distance 14, vertical FOV 35 | How much of the room fits; a narrow FOV keeps verticals near parallel |
| Lane run | 3 lanes × 1.3, lane change 0.15 s, forward 12 units/s, camera pitch 21° at distance 8 | Hazard spacing — `reference/level-metrics.md`, last section |
| Look sensitivity | pointer: degrees per count, no `deltaTime`; stick: degrees per second, with `deltaTime` | Whether aim changes with frame rate |

## Build order for the 3C prototype

1. **Greybox to scale.** Cubes or ProBuilder shapes snapped to 1 unit, on a `World` layer: a
   room, a door at 1.2 × 2.2, a 0.3 step, a 30° ramp, a 1-unit ledge, and a 1.8-unit capsule
   left standing in it as a ruler. No art.
2. **Controls.** A struct with `move`, `look`, `jumpPressed`, `sprintHeld` — `unity-input`.
3. **Character.** The motor below. Register with
   `GameProbe.SetPlayerVelocity(() => transform, () => _controller.velocity);` and
   `GameProbe.Register("grounded", () => _controller.isGrounded);`
4. **Journey 1 — the walk.** Enter the gate-room situation; drive up the step, up the ramp, and
   into a wall. Assert the runner is never inside `World`
   (`JourneyAsserts.NeverInside`), that `grounded` stays true on the ramp, and that speed never
   exceeds the designed run speed.
5. **Journey 2 — the jump.** `scripts/jump_report.py --grounded-key grounded --apex …`.
6. **Camera.** `unity-camera` → `reference/follow-3d.md`. Journey 3: the camera never ends a
   frame on the far side of a wall, and its position does not jitter against the character.
7. **Animation.** Feed the controller's facts to the Animator — `unity-animation` →
   `reference/parameter-contract.md`.

### The motor, in essentials

```csharp
// GateRoomMotor.cs — third-person, camera-relative. Drop on the runner beside a
// CharacterController; assign the camera transform. No Rigidbody on this object.
using UnityEngine;

[RequireComponent(typeof(CharacterController))]
public class GateRoomMotor : MonoBehaviour
{
    public Transform view;                       // the camera; its yaw defines "forward"
    public float runSpeed = 5f, accel = 33f, turnRate = 720f;
    public float gravity = 19.6f, jumpVelocity = 6.86f;
    public Vector2 MoveInput;                    // set every frame from the input struct

    CharacterController _controller;
    Vector3 _planar; float _vertical; bool _jumpQueued;

    void Awake() => _controller = GetComponent<CharacterController>();
    public void PressJump() => _jumpQueued = true;

    void Update()
    {
        float dt = Time.deltaTime;
        Vector3 forward = Vector3.ProjectOnPlane(view.forward, Vector3.up).normalized;
        Vector3 right = Vector3.Cross(Vector3.up, forward);
        Vector3 wish = Vector3.ClampMagnitude(forward * MoveInput.y + right * MoveInput.x, 1f) * runSpeed;
        _planar = Vector3.MoveTowards(_planar, wish, accel * dt);

        if (_controller.isGrounded)
        {
            // Not zero: isGrounded is only true on a frame where Move pressed into the floor.
            _vertical = _jumpQueued ? jumpVelocity : -2f;
        }
        else _vertical -= gravity * dt;
        _jumpQueued = false;

        // One Move per frame. A second call overwrites isGrounded with its own result.
        _controller.Move((_planar + Vector3.up * _vertical) * dt);

        if (_planar.sqrMagnitude > 0.01f)
            transform.rotation = Quaternion.RotateTowards(transform.rotation,
                Quaternion.LookRotation(_planar), turnRate * dt);
    }
}
```

- **First-person** replaces the last block and the basis: `forward` and `right` are the body's
  own; yaw is `transform.Rotate(0f, look.x, 0f)`; pitch is accumulated, clamped to ±85° and
  written to the camera's local rotation only.
- **Overhead** replaces the basis with world axes (or the camera's yaw, fixed once per room) and
  aims at the ground: `new Plane(Vector3.up, transform.position).Raycast(ray, out float enter)`
  on `Camera.ScreenPointToRay`, then face `ray.GetPoint(enter)`.
- **Lane run** has no stick: `targetX = (lane − 1) × 1.3`, `x` moves towards it at
  `1.3 / 0.15` units/s, `z` advances at forward speed. A swipe changes `lane` by one, clamped to
  0…2; a swipe during a change is buffered, one deep.
- **A `CharacterController` moves on the frame**, so its jump is integrated with a variable
  `dt` and the apex wanders by a few percent with frame rate. If the reach table has to hold
  exactly, step the vertical motion on a fixed accumulator, or check the journey at 30 and at
  120 frames per second.

## Traps

- **`isGrounded` flickers on flat ground** when the vertical velocity is zero: `Move` did not
  press down, so it reports false. Hold a small downward velocity while grounded.
- **Teleporting a `CharacterController` by `transform.position`** is undone by its next `Move`.
  Disable the controller, set the position, enable it — respawns and situations both need this.
- **`OnCollisionEnter` on a `CharacterController`** never fires; it raises
  `OnControllerColliderHit` — `unity-physics-3d`.
- **A `Rigidbody` character moved in `Update`**, or by `transform.position`, tunnels and
  jitters. Read input on the frame, write `linearVelocity` in `FixedUpdate`, set Interpolate,
  freeze rotation on X and Z.
- **Camera-relative input while the camera cuts.** On a fixed-camera cut, "forward" flips under
  a held stick and the character reverses. Keep the previous basis until the stick returns to
  centre.
- **Mouse look multiplied by `deltaTime`** makes sensitivity depend on frame rate; the pointer
  delta is already per-frame. Stick look is a rate and does need it.
- **The first-person body in its own camera.** Put the body mesh on a layer the first-person
  camera does not render — `unity-3d-models` → `reference/culling-and-layers.md`.
- **The camera through the wall.** A third-person boom needs collision and a corridor at least
  as wide as the boom is long — `unity-camera` → `reference/follow-3d.md`.
- **Models imported at the wrong scale** make every number above wrong at once. Stand the
  1.8-unit capsule next to the character before tuning anything — `unity-3d-models`.
- **Overhead: `NavMeshAgent` and `CharacterController` on one object** are two owners. For
  click-to-move let the agent own position — `unity-navigation` → `reference/recipes.md`.
- **Lane run: hazards as triggers with no `Rigidbody` on either side** never fire. The runner
  carries a kinematic one — `unity-physics-3d`.
- **Lane run: thousands of units from the origin**, positions lose precision and the runner
  shimmers. Recentre runner and track together every 1000 units, in one frame, and offset the
  probe's reported distance so journeys do not see the jump.
- **Tuning on a 144 Hz monitor for a 30 fps phone.** Run the journeys at the shipping frame rate
  (`Application.targetFrameRate`) — `unity-device-testing` for the device itself.

## Where each need is answered

| Need | Answer |
|---|---|
| Move, look, jump actions; the input struct; a scripted driver | `unity-input` → `reference/reading-input.md` |
| Mouse and stick look, aim at a ground point | `unity-input` → `reference/pointer-and-aim.md` |
| Swipes and on-screen sticks | `unity-input` → `reference/touch-and-on-screen.md` |
| Orbit, first-person, overhead and fixed rigs; boom collision | `unity-camera` → `reference/follow-3d.md` |
| Camera jitter against the character | `unity-camera` → `reference/update-order-and-jitter.md` |
| Cinemachine class names for the installed major | `unity-camera` → `reference/version-and-names.md` |
| Animator parameters fed from the motor | `unity-animation` → `reference/parameter-contract.md` |
| Locomotion blend trees | `unity-animation` → `reference/blend-trees.md` |
| Root motion | `unity-animation` → `reference/root-motion.md` |
| Foot IK | `unity-animation` → `reference/ik-and-rigging.md` |
| A rigged, animated character in the project | `unity-rigged-character` |
| Hit boxes and colliders on a rig | `unity-rigged-character` → `reference/gameplay-rig.md` |
| Click-to-move, patrols, agents | `unity-navigation` → `reference/recipes.md` |
| Raycasts, ground checks, triggers that do not fire | `unity-physics-3d` → `reference/queries.md` |
| Importing and budgeting models | `unity-3d-models` |
| Post-processing on a frame budget | `unity-render-urp` |
| Journeys; the never-inside invariant | `unity-play-harness` → `reference/journeys.md` |
| Jump, step, door and corridor numbers | `reference/level-metrics.md` |
| The motor and its three variants; greybox scale | this file |
| The switch and the gate | this file: the switch is a trigger volume plus a "use" input; the runner asks the nearest interactable in front of it within 2 units (`Physics.OverlapSphere`, then the smallest angle to forward), the switch sets one flag, the gate reads the flag. Expose the flag to the probe |
| The sentry | patrol and chase on a `NavMeshAgent` — `unity-navigation` → `reference/recipes.md` §3; sight is range, then angle, then one `Physics.Linecast` against `World` |
| HUD placement around the vanishing point | `unity-game-ui` → `reference/hud-placement.md` |
| Frame time on the target device | `unity-profiling` |
