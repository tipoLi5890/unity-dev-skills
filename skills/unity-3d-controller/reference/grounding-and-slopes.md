# Grounding, slopes, steps and platforms

> Part of the `unity-3d-controller` skill. What `resources/CharacterMotor3D.cs` does between
> being handed a velocity and reporting `Grounded`, and why each part is there. Gate-room body
> throughout: height 1.8, radius 0.4, skin width 0.04, step offset 0.3, slope limit 45°.

## 1. `isGrounded` describes one `Move`

`CharacterController.isGrounded` is true when the **last call to `Move` collided below the
capsule**. It is a fact about a call, not about the character:

| Situation | `isGrounded` | Why |
|---|---|---|
| Standing still, vertical velocity 0 | false | `Move` did not press down, so nothing was hit below |
| Walking down a 20° ramp at 5 units/s | flickers | The level move leaves the surface; only some frames touch it again |
| A second `Move` in the same frame (a platform nudge, a knock-back) | whatever that one hit | The flag belongs to the latest call |
| The frame after a `transform.position` teleport | stale | No `Move` has run at the new place |

The usual patch — hold `-2` of vertical velocity while grounded — fixes the first row, half
fixes the second, and adds a downward pull that has to be remembered everywhere a jump or a
launch is written.

The motor does not read the flag. After every `Move` it asks the level directly.

## 2. The ground cast

```
origin   the centre of the capsule's lower sphere
shape    a sphere 0.9 × the capsule's radius       (narrower, so a wall beside the runner is not "under" it)
dir      world down
reach    groundTolerance (0.05) when airborne · snapDistance (0.3) when it was grounded
mask     'ground' — the level's layers, without the runner's own
```

Three details make the answer usable:

- **The surface normal, not the contact normal.** A sphere that meets the corner of a step
  reports a normal tilted away from the corner, often past the slope limit, and a motor that
  trusts it slides the runner off every kerb. The motor casts one ray down onto the collider it
  hit, a centimetre beyond the contact point, and takes that face's normal.
- **Gap, corrected for the slope.** On a surface with normal `n`, a sphere reaches contact after
  `rest / n.y` of travel, not `rest`. Without the division, a runner standing on a 30° ramp reads
  as hovering 1.2 cm above it and is pulled down every frame.
- **Never while rising.** A cast on the first frame of a jump finds the floor the runner has
  only just left, reports grounded, and the rules cancel the jump.

`Grounded` is true when that cast finds a surface no steeper than `slopeLimit` within reach.
`GroundNormal`, `GroundAngle`, `Ground` (the collider) and `Platform` come from the same hit.

Check it is the motor's state the rest of the game reads:

```bash
grep -rn 'isGrounded' Assets/Scripts        # expected: nothing outside a comment
```

## 3. Slopes

`slopeLimit` is read from the `CharacterController`; there is one number, not two.

| Ground angle | The motor | The capsule itself |
|---|---|---|
| At or under `slopeLimit` | Grounded. Horizontal velocity is turned along the surface and keeps its magnitude | Would climb at `speed × cos(angle)` and leave the surface going down |
| Over `slopeLimit` | `OnSteep`: not grounded, and the uphill part of the input is removed | Refuses most climbs, but a step offset lets it creep up in small steps |

**Along the surface at the asked speed.** A level move into a 30° ramp is slid along it by the
capsule and loses 13% of its speed; the same move at the top of a down-ramp leaves the ground,
falls, lands, and repeats — the stair-stepping descent. Projecting the wish onto the ground
plane and restoring its length gives 5 units/s uphill, downhill and level, and the downhill move
points into the ramp.

**Sticking going down.** Projection covers a steady slope. A crest, the top of a ramp and a
flight of stairs still leave the feet in the air for a frame. A runner that was grounded and is
not rising looks `snapDistance` below itself; ground found there is ground, and the capsule is
moved down onto it. Keep `snapDistance` at or under `stepOffset`: larger, and walking off a
low wall teleports the runner to the floor.

**Sliding off what is too steep.** Nothing special: `OnSteep` is not grounded, so the rules keep
applying gravity, and the capsule's own collide-and-slide turns the fall into travel down the
surface. Coyote time still allows one jump for 0.1 s after leaving walkable ground and no
longer, which is what stops a jump-spam climb of a 60° face.

**Not sliding on what is walkable.** A grounded runner at rest is handed a zero velocity, and
zero is what the motor moves by. There is no resting gravity to leak down a ramp. The journey
holds the runner on the 30° ramp for 0.5 s and allows 0.02 units of drift.

**A physics material does nothing here.** Friction and bounce belong to the solver; a
`CharacterController` is not in it.

## 4. Steps

`stepOffset` lets the capsule rise over a ledge during a sideways move. Four interactions:

- **`skinWidth`.** The capsule rests a skin above the floor (0.04) and stops a skin short of
  walls. Keep skin near 10% of the radius: thinner and the capsule snags on seams between
  boxes; thicker and it hovers visibly. The motor writes `stepOffset + skinWidth` to the
  component, so a ledge of exactly `stepOffset` is cleared with a skin to spare and is not the
  one height that depends on rounding. Ledges between 0.3 and 0.34 are then walkable too: build
  walls at twice the step offset or more, never just above it.
- **The jump.** With the step offset left on in the air, a jump that clips the side of a ledge
  is lifted onto it: the runner climbs 0.3 more than the apex says, and only when the frame
  timing allows. The motor writes the offset to the capsule while grounded and `0` while
  airborne or rising. The motor's field is the number to tune; a value typed on the
  `CharacterController` is overwritten.
- **The capsule's round foot.** A lip lower than the radius meets the lower hemisphere, not the
  side, and the hemisphere does not ride it: with a step offset of 0 a 0.3 lip is a wall. The
  offset alone decides what is climbed. `CONTROLLER3D_JOURNEY_BREAK=step` (step offset 0) turns
  `ThirdPerson_LowStep_IsClimbed` red; run it after any change to the motor's step handling.
- **`stepOffset` against the jump apex.** A step offset near the apex (1.2) makes the jump
  pointless: keep it at a quarter of the apex or less.

Stairs are a ramp to the collider and steps to the eye: put one sloped box over a flight
(`unity-3d-level` → `reference/collision-proxies.md`) and the capsule neither bobs nor asks
anything of the step offset.

## 5. Moving and turning platforms

A `CharacterController` is not carried by what it stands on. `resources/MovingPlatform3D.cs`
is a kinematic `Rigidbody` moved with `MovePosition` that publishes `PointVelocity(worldPoint)`
— its travel plus its turn about its pivot — and the motor adds the velocity of the point under
the feet to each `Move`, and the platform's yaw to the runner's.

| Detail | Why |
|---|---|
| Velocity, not "parent the runner to the platform" | A parented `CharacterController` is moved by the transform and then moved back by its own `Move`; scale and rotation of the parent distort the capsule |
| The platform has Interpolate | Its collider moves on the physics clock, the runner on the frame. Interpolation draws the platform between steps so the pair look locked |
| Up to two fixed steps of the platform's vertical travel is not treated as a gap | The same clock difference; closing it every frame pins the runner to a pose that moves 50 times a second |
| On leaving, the rider keeps the platform's velocity (`PlatformLaunch`), upward part only | A jump off a moving platform carries its momentum; one off a descending lift is not shortened |
| The rules assign the jump, the launch is added | A lift going up at 2 units/s gives a higher jump; that is the design, and the reach table for that room includes it |

Check on the target frame rate: ride the lift down at a frame rate above the physics rate. A
rider that steps while the platform glides needs a shorter `Time.fixedDeltaTime`, not a
different carry.

A platform that moves **into** a standing runner is not solved by any of this: the capsule is
overlapped and recovers on its next `Move`, sideways or upwards, whichever is shorter. Crushers
and closing gates are hazards with their own trigger volume, not platforms.

## 6. Walls, ceilings and other bodies

- `OnCeiling` is set when `Move` collided above; the rules zero upward velocity so the runner
  does not hang under a ledge for the rest of the rise.
- `HitSide` is set on a sideways collision. The rules keep asking for their velocity: the
  capsule slides along the wall, which is what a player expects.
- `pushSpeed` above 0 gives a dynamic body the runner walks into that speed along the push
  direction, from `OnControllerColliderHit`. It is a velocity, not a force: a heavy crate and a
  light one move alike. Per-crate weight is a multiplier you read from the crate.
- `minMoveDistance` is set to 0 in `Awake`. The component's default (0.001) discards any move
  shorter than a millimetre, and at 240 frames per second a slow walk is shorter than that.

## 7. Checks

| Check | Expect |
|---|---|
| `ThirdPerson_Ramp_IsClimbedGroundedAndHeld` | 0 airborne frames, more than 2 units climbed, less than 0.02 slid |
| The same with `CONTROLLER3D_JOURNEY_BREAK=slope` | Red: a 30° ramp under a 10° limit is a wall |
| `ThirdPerson_LowStep_IsClimbed`, `ThirdPerson_TallStep_IsRefused` | Feet at 0.34 on the 0.3 step; z short of the 0.6 step's face |
| The same with `=tallstep` | Red: a 0.7 offset walks up a 0.6 wall |
| Probe key `groundAngle` while crossing a kerb | 0 before, on and after the kerb — a spike is the contact normal leaking through |
| `Physics.SyncTransforms()` after moving level geometry from script in the same frame | Casts see the new pose; without it they see the old one |

Layers, masks and why a cast misses what is in front of it:
`unity-physics-3d` → `reference/queries.md`.
