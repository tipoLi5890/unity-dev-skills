# Free movement from above — speed, stopping and aim as numbers

> Part of the `unity-2d-controller` skill. `resources/TopDownMotor2D.cs`, line by line: how many
> directions, why a diagonal is not faster, what acceleration and stopping feel like as numbers,
> how the runner slides along shelving, where aim comes from, and the two extras a fixed-screen
> shooter needs. Worked setting: the **depot** — aisles between shelving, a pickup carried to the
> gate, a sentry with a vision cone.

## 1. The body

Dynamic, Gravity Scale 0, Linear Damping 0, rotation frozen, Collision Detection Continuous,
Interpolate. The motor's `Awake` sets all but the last. The collider is a `CircleCollider2D` at
the **feet**, radius 0.3 for a 1-unit tile, carrying a `PhysicsMaterial2D` with friction 0 and
`frictionCombine` `Minimum`.

| Choice | Why |
|---|---|
| Dynamic, not kinematic | With no gravity there is no ground to decide, and the solver's push-out is the wall slide. A kinematic body written by velocity walks through shelving — the break switch in `templates/TopDownJourneyTest.cs` shows it |
| Gravity Scale 0 on the body | Project gravity at zero takes it from every prop that should fall, and hides the decision in a settings file |
| Damping 0 | Stopping is `decel`. With damping as well, two numbers in two places decide one feel |
| A circle at the feet | A box round the sprite makes a 1-tile aisle impassable and catches every corner; a circle rolls round them |
| Friction 0 | With friction, pushing diagonally into a shelf slows the slide along it |

## 2. How many directions

`directions` on the motor:

| Value | The wish vector is | Use for |
|---|---|---|
| `Analogue` | The stick, magnitude clamped to 1 | Twin-stick shooters; anything played on a stick |
| `EightWay` | Snapped to the nearest 45°, stick magnitude kept | Action-adventure with eight sprite directions |
| `FourWay` | The dominant axis only | Maze and tile-authored levels moved through freely |

Four-way with two keys held needs a tie rule, and "the dominant axis" has none for a keyboard:
(1, 1) is a tie. The motor gives x the tie. For last-pressed-wins, track which axis became
non-zero most recently in the input reader and zero the other before it reaches the struct —
the rule belongs to input, not to the motor.

## 3. The diagonal

A keyboard sends (1, 1) for up and right together: magnitude 1.41, 41% faster than a cardinal.

- **Clamp the magnitude; do not normalise.** `Vector2.ClampMagnitude(move, 1)` leaves a
  half-pushed stick at half speed. `move.normalized` makes any deflection full speed and turns
  an analogue stick into a switch.
- The input funnel clamps (`RunInputSource.SetMove`), and the motor clamps again. The motor's
  clamp is not redundant: it is the one that still holds when a different source feeds it.
- The journey asserts it twice — top speed on a diagonal equals top speed on a cardinal within
  2%, and no sample anywhere exceeds `speed × 1.02`.

## 4. Acceleration and stopping

Velocity moves towards `wish × speed` at `accel` while the stick is deflected and at `decel`
when it is not:

```
time to top speed   = speed / accel        5 / 62.5 = 0.08 s
time to stop        = speed / decel        5 / 100  = 0.05 s
stopping distance   = speed² / (2·decel)   25 / 200 = 0.125 units
```

| Feel | Time to top speed | Time to stop |
|---|---|---|
| Instant, arcade | 0 (assign the velocity) | 0 |
| Responsive, with weight — the default | 0.08 s | 0.05 s |
| Heavy | 0.15 s | 0.12 s |
| Ice | 0.4 s and up | 1 s and up |

Past 0.15 s to top speed players report input lag. Stopping faster than starting is the usual
shape: a late stop costs the player a hit, a late start costs nothing. A reversal runs at
`accel` and takes `2·speed/accel` (0.16 s).

**Friction as a number** means `decel`, not a physics material and not Linear Damping. Damping
is exponential — velocity loses a fraction per second, so the stop has a long tail — and it also
fights `accel`, lowering top speed below `speed`. If a surface should be slippery, lower
`decel` (and `accel`) while the runner stands on it: a trigger on the ice writes the two
numbers and restores them on exit.

## 5. Sliding along walls

Nothing to write: the motor asks for a velocity into the shelf every step, the solver removes
the part along the contact normal, and the part along the wall remains. Pushing diagonally into
a wall therefore travels at `speed × cos 45°` = 3.5 units/s along it. That is the expected
number; a game that wants full speed along a wall projects the wish onto the wall tangent
first, using the contact normal from `Rigidbody2D.GetContacts`.

What breaks it:

| Symptom | Cause |
|---|---|
| Sticks instead of sliding | Friction on the runner's collider, or a level material combined by `Maximum` |
| Snags on the seam between two shelf tiles | Per-tile colliders — `unity-physics-2d` → `reference/tilemap-colliders.md` |
| Jitters in a corner | A box collider; or `MovePosition` and velocity both written |
| Passes through thin shelving at speed | Collision Detection `Discrete`; the motor sets `Continuous` |
| Bounces off | Bounciness above 0 on either material |

## 6. Aim is not movement

A twin-stick runner moves on one input and faces on another. The struct already carries both:
`move`, and `aim` — a unit direction, or zero when nothing is aiming. The motor exposes `Aim`
(the aim while there is one, the move direction otherwise) and, with `faceAim` on, `Facing`
follows it.

- **Aim reaches gameplay as a direction on the play plane, whichever device made it.** Stick or
  pointer, the reader resolves it; the motor and the weapon never see a screen position —
  `unity-input` → `reference/pointer-and-aim.md`.
- **Zero means "keep the last one".** A released stick springs through centre; a controller
  that faces `aim` when it is zero snaps to the right on every release.
- **Fire along `Aim`, not along `Facing`,** when `snapFacing` is on: the sprite has four
  directions, the weapon has 360.
- **Smooth the camera, never the aim.** A camera that leads towards the pointer moves the
  pointer's world position every frame — `unity-camera` → `reference/follow-2d.md`.
- With `faceAim` off (action-adventure), `Facing` is the last move direction, snapped to four,
  and holds through a stop. The current facing wins a near tie, so a diagonal does not flicker
  between two sprite sets.

## 7. Fixed screen: the clamp

A shooter that does not scroll keeps the runner inside the view. Assign `clampTo` (an
orthographic camera) and `clampMargin` (at least the collider radius): after its velocity is
set, the motor clamps the body's position to the view rectangle shrunk by the margin and zeroes
only the outward component of velocity, so the runner slides along the screen edge like a wall.

| Alternative | Trade |
|---|---|
| Four `EdgeCollider2D` walls built from the camera rectangle at start | The solver does the work, and bullets can be made to collide with them or not by layer. Rebuild them when the aspect changes |
| The clamp | No colliders to maintain; follows a camera that changes size. The runner's body is teleported the last fraction of a unit, which is invisible at these speeds |

The clamp reads `orthographicSize` and `aspect`, so it is right on any screen shape. In a
vertical shooter with a pillar-boxed play field, clamp to the field's own rectangle instead of
the camera's.

Bullets in a fixed-screen shooter do not use this motor or any body: move each by
`velocity × dt`, test the segment from the old position to the new with `Physics2D.Linecast`,
and return it to the pool on a hit or on leaving the view. Pool size is rate × lifetime ×
shooters.

## 8. Knock-back

`Push(velocity, stunSeconds)` replaces the velocity and ignores the stick for the stun. During
the stun the push decays at half of `decel`; afterwards the ordinary stop takes over.

```csharp
// On the hazard's trigger. Away from the hazard, 8 units/s, 0.15 s without control.
Vector2 away = ((Vector2)runner.position - (Vector2)transform.position).normalized;
motor.Push(away * 8f, 0.15f);
```

- Distance travelled during the stun is about `v·t − ¼·decel·t²`: 8 units/s for 0.15 s goes
  0.6 units (0.56 at a 0.02 step, where 0.15 s is eight steps), and the stop after it adds
  almost nothing. Size a hazard's surroundings to that — a push into a second hazard is a
  combo the player cannot answer.
- The push goes through the motor because the motor is the one writer. `AddForce` beside a
  motor that assigns velocity lasts one step.
- Pair it with invulnerability in the game's own state (0.6 s), or the runner is pushed back
  into the same trigger.

## 9. Checks

| Check | How |
|---|---|
| Diagonal, wall slide, stopping distance | `templates/TopDownJourneyTest.cs`, three tests; `TOPDOWN_JOURNEY_BREAK=kinematic` and `=ice` turn two of them red |
| A 1-tile aisle is passable | Drive the depot aisle situation along it; assert progress and `NeverInside2D` |
| Top speed is `speed` | `GameProbe.SetPlayerVelocity`, then read `speed` from the probe at steady state. Lower means damping; higher means a second writer |
| Facing holds at rest | `GameProbe.Register("faceX", () => motor.Facing.x)` and the same for y; release the stick; neither may change |

## Where each need is answered

| Need | Answer |
|---|---|
| Stick dead zones, pointer to world, the aim threshold | `unity-input` → `reference/pointer-and-aim.md` |
| On-screen sticks | `unity-input` → `reference/touch-and-on-screen.md` |
| Layers for runner, shelving, pickups, bullets | `unity-physics-2d` → `reference/layers-and-matrix.md` |
| Merged tilemap colliders | `unity-physics-2d` → `reference/tilemap-colliders.md` |
| Walking behind shelving: draw order | `unity-2d-rendering` → `reference/y-sort.md` |
| Direction sprites from `Facing` | `reference/facing-and-animator-bridge.md` |
| Moving by the cell instead | `reference/grid-step.md` |
