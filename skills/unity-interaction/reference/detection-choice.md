# Detection — chosen by perspective, scored the same way everywhere

> Part of the `unity-interaction` skill. `resources/Interactor2D.cs` and
> `resources/Interactor3D.cs`: five ways to answer "what is in reach", which one each camera
> wants, and the scoring and hysteresis that turn the answer into one stable target. The calls
> themselves — overloads, filters, what a query does when it starts inside a collider — are
> `unity-physics-3d` → `reference/queries.md` and `unity-physics-2d` → `reference/queries-2d.md`.

## 1. The table

The player selects with whatever the camera lets them point with. Pick the row by that, not by
whether the project is 2D or 3D.

| Perspective | The player points with | Detection | Component and mode |
|---|---|---|---|
| Side view | The body: standing at it | A trigger collider on the runner and a list of what is inside | `Interactor2D`, `TriggerList` |
| Top-down, free movement | The body, and the way it faces | The same list, plus a cone on the facing when two things sit close | `Interactor2D`, `TriggerList` or `Overlap` with `Facing` assigned |
| Third person, overhead 3D | The body's forward; the camera is elsewhere | A sphere on a tick, a cone on the body's forward, one line of sight | `Interactor3D`, `Overlap` |
| First person | The centre of the screen | One ray from the camera | `Interactor3D`, `Ray` |
| Cells | The cell in front | A lookup in the board, no physics | Neither — §6 |
| Pointer: hotspots | The cursor | A hit under the pointer | Neither — `reference/point-and-click.md` |

Two wrong pairings account for most complaints:

- **A screen-centre ray in third person.** The ray leaves the camera, passes the runner's
  shoulder and selects things the runner is nowhere near, or the back of the runner's own head.
- **An overlap sphere in first person.** The player is looking straight at one switch and the
  prompt names the one beside their elbow.

## 2. Each detection, with its numbers

### Trigger list — side view and top-down

A trigger `CircleCollider2D` on the runner, radius equal to the reach (1.5 to 2 units), on the
runner's own body. `OnTriggerEnter2D` adds, `OnTriggerExit2D` removes, the scan scores the list.

- **One side of the pair has a `Rigidbody2D`**, or neither callback fires. The runner has one.
- **The sensor is the reach.** `range` is not applied a second time in this mode; it only
  normalises the distance score.
- **The list is pruned on every scan.** A pickup returned to its pool while inside the sensor
  is removed by its `enabled` and `activeInHierarchy`, not by waiting for an exit.
- **The sensor is a trigger on the runner, so everything else that reacts to triggers now sees
  the runner sooner.** A touch pickup must ignore trigger colliders or it is collected at reach
  distance — `reference/pickups.md` §1.
- **No kept margin.** A runner standing exactly on the rim can see the prompt blink. If it
  does, switch the mode to `Overlap`, which keeps the target out to `range × 1.15`.

### Overlap on a tick — third person, overhead

`Physics.OverlapSphereNonAlloc` from 1 unit above the feet (`originHeight`), radius
`range × keepRangeFactor` = 2.3, every 0.1 s (`scanInterval`), into a fixed array of 16.

- **A tick, not every frame.** Ten scans a second is beyond what a walking player can perceive
  and a tenth of the cost. Call `Rescan()` after a teleport. After building or moving colliders
  from code, call `Physics.SyncTransforms()` first: until the next simulation step the query
  still sees them where they were created, and the first scan can select a switch across the room.
- **Distance is to the collider's bounds, not to its pivot.** A gate 4 units wide is in reach
  at its near face. The component uses `Collider.bounds.ClosestPoint`; `Collider.ClosestPoint`
  rejects a non-convex `MeshCollider`.
- **The cone is on the body's forward, flattened to the ground plane:** 60° either side
  (`halfAngle`). Standing on top of the target, within 0.05 units, the angle is taken as 0 —
  there is no direction to be wrong about.
- **Line of sight is one `Physics.Linecast`** from eye height (1.6) to the target's `Anchor`
  against `blockers`. A hit on the target's own collider counts as sight: a gate is both the
  wall and the thing being used.
- **`QueryTriggerInteraction.Collide` on the overlap, `Ignore` on the line of sight** — passed
  on every call. A switch is often a trigger; a wall never is.

### Ray from the view — first person

One `Physics.Raycast` from the camera's position along its forward, length 2.3, against
`interactable | blockers`, first hit only.

- **First hit only.** If the first thing the ray meets is a wall, nothing is selected. A
  `RaycastAll` that skips the wall is how a switch gets used through it.
- **The runner's own layer is in neither mask.** The camera sits inside the capsule.
- **`rayRadius` 0.1 turns it into a sphere cast** for small targets and for a gamepad, where
  holding a crosshair on a 0.2-unit switch is work. Above 0.25 it starts selecting round corners.
- **Reach is measured from the camera**, so a first-person reach of 2 is shorter at the feet
  than a third-person 2. Stand at a table and check the far edge is selectable.
- **Trigger volumes that are not interactables stay off both masks**, or the first hit is an
  invisible zone and the switch behind it never selects.

### Overlap circle — 2D without a sensor

`Physics2D.OverlapCircle(origin, radius, filter, list)` with `useTriggers = true` on the filter,
and one `Physics2D.Linecast` against `blockers` when the depot's shelving must hide a switch.
Use the list overloads: the `…NonAlloc` names are deprecated, and the list is reused with no
allocation once it has capacity.

## 3. Scoring — distance, angle, priority

Every candidate inside the thresholds gets one number; the highest is the target.

```
score = (1 − distance / (range × 1.15))                  near           0 … 1
      + 0.5 × (1 − angle / (halfAngle + 10°))            in front       0 … 0.5, only with a cone
      + 2 × Priority                                     by design
      − 1 when CanInteract is false                      spent, locked, busy
      + 0.15 when it is the current target               hysteresis
```

| Term | Field | Effect |
|---|---|---|
| Near | — | Weight 1. The base of every selection |
| In front | `angleWeight` 0.5 | A switch dead ahead at 1.8 units beats one at the edge of the cone at 1.2 |
| Priority | `priorityWeight` 2 | One step outranks anything geometry can say (geometry tops out at 1.5). For a parcel lying on a gate's threshold |
| Unavailable | `unavailablePenalty` 1 | A spent switch stays selectable — so "Locked" can be shown — but loses to anything usable beside it |
| Current | `switchMargin` 0.15 | §4 |

Raise `Priority` only where two interactables overlap by design. If it is doing the work in
ordinary rooms, the objects are too close together: 1 unit apart is the least that lets a
player choose by walking.

## 4. Hysteresis — why the prompt does not flicker

Two separate thresholds, both in favour of the target already held:

| Threshold | Enter | Keep |
|---|---|---|
| Range | `range` — 2 | `range × keepRangeFactor` — 2.3 |
| Cone | `halfAngle` — 60° | `halfAngle + keepAngleMargin` — 70° |
| Score | highest | holds until a challenger wins by `switchMargin` — 0.15 |

Without them, a runner standing between two switches — or on the rim of one — sees the prompt
swap on every animation sway, and a press lands on whichever was selected that step. With
`switchMargin` 0.15 and a reach of 2, the challenger has to be about 0.35 units nearer; that is
a step the player took, not noise.

`TargetChanges` counts selections. Register it and the flicker becomes a number:

```csharp
GameProbe.Count("targetChanges", () => interactor.TargetChanges);
```

`Selection_HoldsBetweenTwoEqualSwitches` in the journey shifts the runner 0.1 units back and
forth between two mirrored switches and asserts the count does not move.

## 5. Layers

| Layer | In `interactable` | In `blockers` |
|---|---|---|
| `Interactable` — switches, interact pickups, hotspots | yes | no |
| `World` / `Obstacles` — walls, shelving | no | yes |
| `Gate` — a gate that is itself used | yes | yes |
| `Runner` | no | no |
| `Pickup` — touch pickups | no | no |
| Trigger zones that are not interactables | no | no |

- A dedicated `Interactable` layer keeps the overlap from returning every wall in the room.
- Queries take a mask and ignore the collision matrix; trigger **callbacks** obey it. The
  trigger list therefore needs the `Runner × Interactable` pair enabled in the 2D matrix —
  `unity-physics-2d` → `reference/layers-and-matrix.md` — and a 3D pressure plate needs its
  pair in the 3D matrix, which `unity-physics-3d` §1 walks through.
- Resolve layer names once and fail loudly on −1: `LayerMask.NameToLayer("Interactable")`.

## 6. Cells — no physics at all

On a board the runner's reach is the cell it faces, and what stands there is a lookup:

```csharp
// The sorting yard: the runner's cell and facing index come from the board, not the transform.
Vector3Int ahead = GridCoords.Neighbour(shape, runnerCell, facing);
int id = occupancy.OccupantAt(ahead);
IInteractable target = id == GridOccupancy.Nobody ? null : yard.InteractableOf(id);
if (target != null && input.TryUse(RunButton.Interact)) target.Interact(runner);
```

The contract is unchanged — one target, one press, the interactable decides — and the
interactor is those four lines in the turn handler. An overlap at the cell centre reads the
transform, which is wrong for half of every step. Neighbour indices on rectangular and
hexagonal boards: `unity-2d-grid` → `reference/neighbours-and-range.md`.

## Checks

- Stand between two switches and sway: `targetChanges` stays put. Set `switchMargin` to 0 and
  it climbs — that is the flicker.
- Stand with a wall between the runner and a switch 1 unit away: nothing is selected. Empty
  `blockers` and it is — that is the switch used through the wall.
- Face away from a switch at 1 unit in third person: nothing is selected. `halfAngle` 180 and
  it is.
- A query that finds nothing at all: fire it once with `Physics.AllLayers` and once with the
  production mask — `unity-physics-3d` → `reference/queries.md`.
- In first person, look at a switch through the gap under a shelf: the prompt names the
  switch only if the ray reaches it first.
