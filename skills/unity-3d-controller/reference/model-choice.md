# Choosing the movement model — who writes the transform

> Part of the `unity-3d-controller` skill. Four components can own a 3D character's position.
> Each gives something for free and charges for something else, and any two of them on one
> object is the bug. Choose one per character, write it down, then write movement.

## 1. The four owners

| Owner | Who writes position | The engine does | You do |
|---|---|---|---|
| **`CharacterController`** — `resources/CharacterMotor3D.cs` | `CharacterController.Move`, once per frame, from `Update` | Sweeps the capsule, slides along walls, climbs steps up to `stepOffset`, refuses slopes over `slopeLimit` | Gravity, jump, ground state, sliding off steep ground, platform carry, pushing bodies |
| **Dynamic `Rigidbody`** | The solver, from the `linearVelocity` you assign every `FixedUpdate` | Resolves contacts, pushes the body out of walls, lets other bodies shove it | Grounding by cast, slope handling, friction set to zero, never also writing the transform |
| **Kinematic `Rigidbody` with your casts** — `resources/LaneRunnerController.cs` | `Rigidbody.MovePosition`, once per `FixedUpdate`, to a point you computed | Fires triggers, carries bodies resting on it, interpolates | Everything: nothing stops a kinematic body but your own casts |
| **`NavMeshAgent`** | The agent, towards a destination | Paths, steers, avoids other agents, stays on the mesh | Give destinations — `unity-navigation` → `reference/recipes.md` |

The built-in `CharacterController` component is part of the physics module and needs no
package. `com.unity.charactercontroller` is a different thing — an Entities (DOTS) character
package — and adding it to a GameObject project gives you nothing this skill uses. Check:

```bash
grep -n '"com.unity.charactercontroller"\|"com.unity.entities"' Packages/manifest.json
```

A hit for the first without a deliberate Entities project is a package to remove.

## 2. Which constraint picks which

| The game's constraint | Owner | Because |
|---|---|---|
| A person on foot in the gate room: steps, ramps, doors, a jump that lands on a designed apex | `CharacterController` | Steps and walls are solved; the jump is arithmetic you own; no contact or material can move the apex |
| The runner must be shoved, carried and knocked about by other bodies: crates that push back, a conveyor of physics props | Dynamic `Rigidbody` | Being pushed is free on a dynamic body and laborious on every other owner |
| The game owns the path: the lane run, a rail, a scripted traversal | Kinematic `Rigidbody` | There is no collision to resolve, only triggers to fire; a formula is the position |
| Destinations, not directions: click-to-move in the depot, followers, the sentry | `NavMeshAgent` | The path is the hard part and the agent has it |
| The stride must set the speed: a heavy third-person character whose feet may not slide | `CharacterController`, moved by the clip's delta | `unity-animation` → `reference/root-motion.md`, row 3; still one owner |

## 3. What each one costs

**`CharacterController`.**
- It moves on the frame. There is no interpolation and none is needed: the camera reads a pose
  written this frame. Set the Cinemachine Brain to update in `LateUpdate` —
  `unity-camera` → `reference/update-order-and-jitter.md`.
- It pushes nothing and is pushed by nothing. A crate it walks into stays put unless
  `OnControllerColliderHit` gives the crate a velocity (`pushSpeed` on the motor). A platform
  that moves into it passes into it until its next `Move` recovers the overlap.
- It never raises `OnCollisionEnter`. It raises `OnControllerColliderHit`, and trigger messages
  work as for any collider — `unity-physics-3d`.
- The capsule is always upright. No leaning, no prone, no gravity that is not world down.
- `isGrounded` describes the last `Move` and nothing else — `reference/grounding-and-slopes.md`.
- A write to `transform.position` while it is enabled is undone by the next `Move`. Teleport
  through `CharacterMotor3D.Teleport`, which disables it, writes, enables it.

**Dynamic `Rigidbody`.**
- Friction sticks the character to walls and slows it on slopes: put a physics material with
  zero friction and `Minimum` combine on the capsule.
- Velocity is assigned every `FixedUpdate`, keeping the body's own vertical component:
  `rb.linearVelocity = new Vector3(wish.x, rb.linearVelocity.y, wish.z)`. `AddForce` gives a
  character that accelerates like a crate.
- Freeze rotation on X and Z, set Interpolate, read input on the frame and move on the step.
- Grounding is yours: the same downward sphere cast as the motor, from `FixedUpdate`.
- The jump height varies with whatever contact lands on the take-off step. If the reach table
  has to hold, this is the wrong owner.

**Kinematic `Rigidbody`.**
- Nothing stops it. Walls are your casts, or the design has no walls — the lane run has lanes.
- It must be moved with `MovePosition` in `FixedUpdate` for triggers, carried bodies and
  interpolation to work; a `transform.position` write teleports it.
- It is the body that makes trigger volumes fire: a hazard that is a trigger with no `Rigidbody`
  on either side never raises `OnTriggerEnter`.

**`NavMeshAgent`.**
- It keeps the character on the baked mesh and nowhere else: no jump, no step that is not a link.
- `updatePosition` and `updateRotation` decide whether it writes the transform —
  `unity-navigation`, section 3.

## 4. Two owners: the pairs, the symptom, the grep

| Pair on one object | Symptom |
|---|---|
| `CharacterController` + non-kinematic `Rigidbody` | Jitter; the character sinks or is flung; gravity applied twice |
| `CharacterController` + enabled `NavMeshAgent` | The character slides back to where the agent thinks it is |
| `CharacterController.Move` + `Animator.applyRootMotion` | Runs at double speed, or snaps back each loop of the clip |
| A controller + a script that writes `transform.position` (a tween, a knock-back, a "snap to spawn") | Rubber-banding on the frames the second script runs |
| Two scripts that both call `Move` | `isGrounded` and `collisionFlags` describe whichever ran last |

```bash
# Every writer of a position under the character's scripts. One line per character is the goal.
grep -rnE '\.Move\(|MovePosition\(|linearVelocity\s*=|transform\.position\s*=|\.Translate\(|applyRootMotion\s*=\s*true|\.Warp\(|nextPosition\s*=' Assets/Scripts
```

Knock-back, launch pads and conveyors hand a velocity to the owner — `Push(velocity,
lockSeconds)` on the controllers here — and never move the body themselves.

## 5. Handing over

An owner can change during play — the depot's runner walks by stick, then by click — but the
change is a handover, never an overlap:

```csharp
// Stick to click: the agent takes the transform.
topDown.Release();                       // stops Move, disables the CharacterController
agent.enabled = true;
agent.Warp(transform.position);          // the agent starts where the body is
agent.SetDestination(point);

// Click to stick: the first stick input takes it back.
agent.ResetPath();
agent.enabled = false;
topDown.Reclaim();                       // enables the CharacterController and re-reads the ground
```

Order matters: disable the old owner before enabling the new one, in the same frame. The same
shape covers a ladder, a cutscene on a Timeline track and a mount: one script that knows both
owners and switches them.

## 6. Checks

- Select the character in play mode. Exactly one of `CharacterController`, non-kinematic
  `Rigidbody`, enabled `NavMeshAgent` is present and enabled.
- The grep above lists one writer for that character.
- `Animator.applyRootMotion` is off unless the mover has `OnAnimatorMove`.
- Disable the controller script in play mode: the character stops dead and stays. If it drifts,
  slides or sinks, something else is writing.
