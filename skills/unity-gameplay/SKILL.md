---
name: unity-gameplay
description: >-
  START HERE for any gameplay request: make a platformer, runner, top-down or
  tactics game, add a player. Reads 2D or 3D and the view, routes each system;
  level metrics, stages.
---

# unity-gameplay — a genre is a set of constraints, and the constraints pick the skills

> **A genre name decides nothing you can build from.** "Platformer" does not say who owns the
> transform, what the level unit is, or which clock the camera reads. Six constraints do, and two
> games with the same label and a different transform owner share no controller code — while two
> with different labels and the same six share almost all of it.

## Request → where to go

| The request | Go to |
|---|---|
| "make a platformer", "build a top-down shooter", "which skills for a tactics game" | §0, then the genre file it names |
| "add a player character" | §0, then the controller row in *Load what the situation needs* |
| "how wide can the gap be", "the jump cannot reach the ledge" | *Discipline* (numbers before levels) and `reference/level-metrics.md` |
| "what do we build first", "is the prototype done" | `reference/pipeline-stages.md` |
| The idea, the brief, the look, a preview before code | `unity-game-brief` |
| Controls · camera · Animator work | `unity-input` · `unity-camera` · `unity-animation` |
| Any other system a game needs | *Load what the situation needs* |

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
| A timed press graded in milliseconds, "swing timing", a cue ring, tennis, badminton, a rally against bots | 3D · broadcast view · characters move themselves | `reference/genre-timing-sports.md` |

**No explicit signal — fingerprint the project.** One command, read-only, no Unity needed:

```bash
python3 scripts/fingerprint.py /path/to/project --indent 2
```

Read the result as a whole, not key by key — packages are not a signal, physics outranks
renderers, 3D physics under an orthographic camera is 2.5D, and the Cinemachine major changes the
class names. A sample result, how each verdict is derived and the same checks as `find`/`grep`:
`reference/perspective-fingerprint.md`.

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
| Racket and bat games: the clip library bounds the simulation, contact decided by the sim, timing invariants, balance grid | `reference/genre-timing-sports.md` |
| A simulation on its own thread: absolute clock, triple-buffered snapshot, render tick, JIT warmup, sim-lag smoke gate, rules tests with no Editor | `reference/sim-host-and-clock.md` |
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
| 3D character: who owns the transform, third-person, first-person, overhead and lane controllers, the Animator bridge | `unity-3d-controller` |
| 3D levels: greybox to metrics, modular kits, prefabs, collision proxies, terrain, splines | `unity-3d-level` |
| 3D light modes, bakes, probes, shadows, environment, the mobile subset | `unity-lighting` |
| Switches, gates, pickups, the use prompt, point-and-click hotspots | `unity-interaction` |
| Damage events, hit and hurt boxes, attack windows, invincibility, projectiles | `unity-combat` |
| The sentry: perception, patrol and chase, pathing in 2D, waves, enemy turns on a board | `unity-game-ai` |
| The Boot scene, additive loading, pause, the save file, checkpoints, pools | `unity-scene-flow` |
| Feedback per event: hit stop, flash and squash, particles, trails, sound events, rumble | `unity-game-feel` |
| LOD, occlusion, batching, culling distances, texture streaming | `unity-scene-optimisation` |
| Situations, journeys, timelines; a feel report with no number in it | `unity-play-harness` |
| The brief, its perspective and movement block, simulation/presentation split | `unity-game-brief` |
| Project creation, which packages, version pinning | `unity-new-project` |
| Tile Palettes, rule tiles, grid layouts | `unity-tilemap` |
| Slicing sheets, pivots, clips from frames | `unity-2d-sprites` |
| Pixel art that shimmers or blurs | `unity-2d-pixel-perfect` |
| A collision or trigger that does not fire, in 3D · in 2D | `unity-physics-3d` · `unity-physics-2d` |
| NavMesh baking, agents, click-to-move | `unity-navigation` |
| A rigged, animated character from source art, stage by stage · its Unity import | `game-character-pipeline` · `unity-rigged-character` |
| HUD and menus · frame time and counters | `unity-game-ui` · `unity-profiling` |
| URP renderer, post-processing, the look of the frame | `unity-render-urp` |
| Music, sound import settings, mixers | `unity-audio` |
| Packing sprites into atlases, draw calls from sprites | `unity-sprite-atlas` |
| Trusting a test run, reading logs, screenshots | `unity-debug` |

### Given inline here

Every genre file ends on a table naming the skill that owns each need. What no skill owns is
carried here:

| Need | Where the method is |
|---|---|
| Door, corridor, step and ceiling numbers from the body | `reference/level-metrics.md` §5 |
| Playfield fit, bullets as one array of structs, the launch gesture | `reference/genre-2d-fixed-screen.md` |
| A sim thread with a clock every thread can read; pause-aware timestamp conversion | `resources/SimHost.cs`, `resources/SimClock.cs` — pure C# in a plain assembly with no engine references, which the presentation references |

---

## Discipline

- **Name the transform owner before writing movement code.** A kinematic motor, a dynamic body, a
  `CharacterController`, a `NavMeshAgent`, root motion or the cell map: one of them writes
  position and the others read it. Two writers produce jitter no camera setting removes.
- **Numbers before levels.** Decide apex height, time to apex and run speed; derive gravity and
  jump velocity from them; then let `scripts/level_metrics.py` say how wide a gap may be. A level
  built first fixes the jump by accident (`--gap 5 --height 1` exits 1 when a number is outside
  reach; the commands are in `reference/level-metrics.md`).
- **Measure the jump the game performs, not the one the constants describe.** A fixed step moves
  the apex by `v0 · dt / 2`; drag, a clamped fall speed or a second writer move it further —
  `scripts/jump_report.py` reads it off a journey's `timeline.jsonl`.
- **Gameplay reads a struct, never a device.** A gamepad, a touch overlay and a journey's
  scripted driver all fill the same struct, which is what makes the controller testable.
- **Simulate on the fixed step, present on the frame.** Input is sampled on the frame and consumed
  on the step; the camera reads after both. Most jitter is one of the three in the wrong place.
- **A heavy or timing-graded sim gets its own thread and an absolute clock.** Draw one tick
  behind the clock and never clamp that to the snapshot; warm the code paths up before the clock
  starts: `reference/sim-host-and-clock.md`.
- **Measure what the clips can do before setting speeds and reach.** A simulation that ran at
  7 m/s against a 2.7 m/s run loop, with contact points 25 to 65 cm from where the clips put the
  racket, spent its whole motion pass bridging the gap: `reference/genre-timing-sports.md` §0.
- **3C on greybox first.** Character, camera and controls each pass one journey on untextured
  boxes before any art is imported.
- **A genre file is a starting set of constraints.** Change one and re-pick the rows it touched.

## Scope — what this skill does NOT do

Every row of *Load what the situation needs* that names another skill is that skill's work, not
this one's: deciding what the game is (`unity-game-brief`), creating the project
(`unity-new-project`), input, camera, Animator, controllers, levels, physics, draw order, light,
interaction, combat, AI, scene flow, feel, journeys (`unity-play-harness`) and trusting a test run
(`unity-debug`).

What is left is what no single-system skill can hold: **deciding which constraints this game
has, and so which skills to open** — plus the level numbers that follow from the controller and
the check that ends each stage.
