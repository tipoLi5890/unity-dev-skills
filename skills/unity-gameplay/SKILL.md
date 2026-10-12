---
name: unity-gameplay
description: >-
  START HERE for a gameplay request naming no perspective or movement model:
  fingerprints the project (2D or 3D, projection, view, movement model,
  Cinemachine major) and routes controls, camera, animation and verification to
  the skill owning each. Owns genre recipes written as constraints, level
  metrics derived from controller numbers, and production stages with exit
  checks. Load for: "make a platformer", "add a player character", "build a
  top-down shooter", "which skills for a tactics game", "how wide can the gap
  be", "the jump cannot reach the ledge", "is the prototype done". The brief
  is unity-game-brief; input, camera and Animator work are unity-input,
  unity-camera, unity-animation.
---

# unity-gameplay — a genre is a set of constraints, and the constraints pick the skills

> **A genre name decides nothing you can build from.** "Platformer" does not say who owns the
> transform, what the level unit is, or which clock the camera reads. Six constraints do, and two
> games with the same label and a different transform owner share no controller code — while two
> with different labels and the same six share almost all of it.

| Constraint | Values | What it picks |
|---|---|---|
| Dimension | 2D · 3D | The physics vocabulary, and every component name after it |
| Projection | orthographic (size, pixels per unit) · perspective (FOV, distance, pitch) | Camera rig, sorting, pixel snapping |
| View | side · top-down · isometric · behind the character · through its eyes · fixed | What "up" means to the stick, what occludes what |
| Movement model | free · lane · cell | Controller shape, level unit, what a journey asserts |
| Transform owner | kinematic motor · dynamic body · `CharacterController` · `NavMeshAgent` · root motion · the cell map | Who may write position — exactly one |
| Level unit | tile · cell · kit module · lane width | What every level number is a multiple of |

---

## 0. Which game is this? (route before you build)

Not every question needs routing. **Teaching questions — "what is coyote time", "kinematic or
dynamic for a platformer" — get answered directly.** Route only when the user wants gameplay
read, changed or built.

**Explicit signals win.** A named component, API or view is the answer:

| They mention | Perspective and movement model | Recipe |
|---|---|---|
| `Rigidbody2D`, a jump, platforms, "side-scroller", "runner seen from the side" | 2D · side · free, under gravity | `reference/genre-2d-side.md` |
| "seen from above", "8-direction", "twin-stick", zero gravity, Y-sorting | 2D · top-down · free | `reference/genre-2d-topdown.md` |
| `WorldToCell`, "turn-based", "tile puzzle", "hex", "isometric", "one tile per move" | 2D · cell | `reference/genre-2d-grid.md` |
| "the screen does not scroll", "bullet patterns", "click on the object", "one screen" | 2D · fixed screen | `reference/genre-2d-fixed-screen.md` |
| `CharacterController`, `Rigidbody`, `NavMeshAgent`, "third-person", "first-person", "lanes", meshes | 3D | `reference/genre-3d.md` |

**No explicit signal — fingerprint the project.** One command, read-only, no Unity needed:

```bash
python3 scripts/fingerprint.py /path/to/project --indent 2
```

```json
{"dimension":  {"value": "2d", "evidence": {"physics_2d": 41, "physics_3d": 0, "decided_by": "physics components"}},
 "projection": {"value": "orthographic", "evidence": {"orthographic_cameras": 2, "perspective_cameras": 0}},
 "view":       {"value": "side", "evidence": {"gravity_2d_y": -9.81, "platform_effectors": 6}},
 "movement_model": {"hints": [{"model": "dynamic-body-2d", "evidence": {"bodies": 9}}]},
 "packages":   {"cinemachine": {"version": "3.1.7", "major": 3}}}
```

Read the result as a whole, not key by key:

- **An installed package is not a signal.** Templates add the 2D feature set, Input System and
  Cinemachine to projects that use none of them. Components in scenes and prefabs are evidence.
- **Physics outranks renderers.** A 3D game has sprites in its HUD; a 2D game has a mesh or two.
  The body the player object carries is what a controller is written against.
- **3D physics under an orthographic camera is 2.5D**, not a contradiction: the controller follows
  the physics, the camera follows the projection.
- **The Cinemachine major changes the namespace and most class names.** Read it before writing
  a camera line; `unity-camera` starts from the same number.
- **Everything `unknown` means no evidence**: a new project, the wrong directory, or binary
  scenes (`notes` says which). Go to the ladder.

How each verdict is derived, and the same checks as `find`/`grep`: `reference/perspective-fingerprint.md`.

**Still ambiguous — the default ladder:**

1. Existing project → follow what the fingerprint found. Consistency beats preference.
2. The brief has a perspective and movement block → that block is the answer.
3. Sprite or pixel art is named → 2D. A rigged or modelled character is named → 3D.
4. One-thumb play on a phone, nothing else stated → fixed camera, lane or cell movement.
5. Still nothing → ask **one** question: "seen from the side, from above, or from behind the
   character?" The answer fixes view and, nearly always, dimension.

**Then hand off.** Fill `templates/GAMEPLAY_RECIPE.md` — the six constraints, the numbers, one
row per need — open the genre file named above and build in its order.

---

## Load what the situation needs

| The situation | Read |
|---|---|
| What the project already is; reading the fingerprint | `reference/perspective-fingerprint.md` |
| Platformer, exploration platformer with gated rooms, auto-runner | `reference/genre-2d-side.md` |
| Action-adventure from above, twin-stick shooter, RPG from above | `reference/genre-2d-topdown.md` |
| Tactics, tile puzzle, isometric or hexagonal boards | `reference/genre-2d-grid.md` |
| Scrolling shooter, point-and-click adventure, single-screen casual | `reference/genre-2d-fixed-screen.md` |
| Third-person, first-person, fixed or overhead camera in 3D, lane runner | `reference/genre-3d.md` |
| Jump height, gap, step, door and corridor sizes; "can the runner make this" | `reference/level-metrics.md` |
| What to build first; when a stage is finished | `reference/pipeline-stages.md` |
| Actions, a struct gameplay reads, touch, rebinding, pointer aim | `unity-input` |
| Follow, confiner, look-ahead, jitter, shake, Cinemachine names per major | `unity-camera` |
| Animator parameters, blend trees, sprite state graphs, events, IK, root motion | `unity-animation` |
| 2D character: platformer motor, motor seen from above, cell step, the Animator bridge | `unity-2d-controller` |
| 2D bodies, casts, tilemap colliders, one-way platforms, the 2D layer matrix | `unity-physics-2d` |
| 2D draw order, sorting by Y, 2D lights and shadows, parallax | `unity-2d-rendering` |
| 2D levels as data: layer stacks, runtime tiles, rooms, chunks, LDtk and Tiled | `unity-2d-level` |
| Cell coordinates, range, pathfinding, line of sight, occupancy, turns | `unity-2d-grid` |
| Bones and weights on a sprite, PSB rigs, Sprite Library | `unity-2d-animation` |
| Situations, journeys, timelines; a feel report with no number in it | `unity-play-harness` |
| The brief, its perspective and movement block, simulation/presentation split | `unity-game-brief` |
| Project creation, which packages, version pinning | `unity-new-project` |
| Tile Palettes, rule tiles, grid layouts | `unity-tilemap` |
| Slicing sheets, pivots, clips from frames | `unity-2d-sprites` |
| Pixel art that shimmers or blurs | `unity-2d-pixel-perfect` |
| A collision or trigger that does not fire, in 3D · in 2D | `unity-physics-3d` · `unity-physics-2d` |
| NavMesh agents, click-to-move, patrols | `unity-navigation` |
| Getting a rigged, animated character into the project | `unity-rigged-character` |
| HUD and menus · frame time and counters | `unity-game-ui` · `unity-profiling` |

### Given inline here

Every 2D genre file routes its motor, physics, draw order, level and cell needs to the six
skills above, by file. What no skill owns, the genre files carry as essential method — enough
for a 3C prototype that passes a journey:

| Need | Where the method is |
|---|---|
| The 3D motor: grounding, jump, slopes, its three variants | `reference/genre-3d.md`, "The motor, in essentials" and "Traps" |
| Greybox scale in 3D: capsule, door, corridor, step | `reference/level-metrics.md`, `reference/genre-3d.md` |
| Pickups, switches, hazards, a sentry that sees | the genre file for the view, its last table |
| Playfield fit, bullets as data, hotspot picking, the launch gesture | `reference/genre-2d-fixed-screen.md` |

---

## Discipline

- **Name the transform owner before writing movement code.** A kinematic motor, a dynamic body, a
  `CharacterController`, a `NavMeshAgent`, root motion or the cell map: one of them writes
  position and the others read it. Two writers produce jitter no camera setting removes.
- **Numbers before levels.** Decide apex height, time to apex and run speed; derive gravity and
  jump velocity from them; then let `scripts/level_metrics.py` say how wide a gap may be. A level
  built first fixes the jump by accident.

  ```bash
  python3 scripts/level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 \
      --fall-multiplier 1.5 --gap 5 --height 1      # exit 1 when a number is outside reach
  ```

- **Measure the jump the game performs, not the one the constants describe.** A fixed step moves
  the apex by `v0 · dt / 2`; drag, a clamped fall speed or a second writer move it further.

  ```bash
  python3 scripts/jump_report.py journeys/ledge-drop/timeline.jsonl \
      --grounded-key grounded --apex 2.85 --air-time 0.72
  ```

- **Gameplay reads a struct, never a device.** A gamepad, a touch overlay and a journey's
  scripted driver all fill the same struct, which is what makes the controller testable.
- **Simulate on the fixed step, present on the frame.** Input is sampled on the frame and consumed
  on the step; the camera reads after both. Most jitter is one of the three in the wrong place.
- **3C on greybox first.** Character, camera and controls each pass one journey on untextured
  boxes before any art is imported.
- **A genre file is a starting set of constraints.** Change one and re-pick the rows it touched.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Deciding what the game is: the brief, invariants, the look | `unity-game-brief` |
| Creating the project, choosing packages | `unity-new-project` |
| Action assets, reading input, touch controls, rebinding | `unity-input` |
| Camera rigs, confiners, jitter, shake | `unity-camera` |
| Animator graphs, events, IK, Timeline | `unity-animation` |
| Building the probe, situations and journeys the checks here rely on | `unity-play-harness` |
| The 2D motor, its scripts and its journey templates | `unity-2d-controller` |
| A collision or trigger that does not fire, in 3D · in 2D | `unity-physics-3d` · `unity-physics-2d` |
| Draw order, 2D lights, parallax | `unity-2d-rendering` |
| Level construction and level data in 2D | `unity-2d-level` |
| Cell maths, pathfinding, turn order | `unity-2d-grid` |
| Skeletal sprite art | `unity-2d-animation` |
| Trusting a test run, reading logs, screenshots | `unity-debug` |

What is left is what no single-system skill can hold: **deciding which constraints this game
has, and so which skills to open** — plus the level numbers that follow from the controller and
the check that ends each stage.
