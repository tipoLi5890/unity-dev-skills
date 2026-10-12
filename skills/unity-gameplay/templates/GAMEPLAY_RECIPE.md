# Gameplay recipe — <game name>

<!-- One page, kept beside GAME_BRIEF.md. It records which constraints this game has, the
     numbers that follow from them, and which skill answers each need. Fill it top to bottom:
     each block is derived from the one above. When a constraint changes, change it here first
     and then re-pick every row it touches. Delete these comments as each block is filled. -->

## Perspective

<!-- From the brief's perspective and movement block, or from
     `python3 scripts/fingerprint.py . --indent 2` on an existing project. State constraints,
     not a genre name. -->

| | |
|---|---|
| Dimension | <!-- 2D · 3D --> |
| Projection | <!-- orthographic: size, pixels per unit · perspective: vertical FOV, distance, pitch --> |
| View | <!-- side · top-down · isometric · behind the character · through its eyes · fixed --> |
| Camera behaviour | <!-- follows with dead zone · confined per room · fixed · orbits · fixed offset --> |
| Device and input | <!-- gamepad, keyboard and mouse, touch; one-thumb or two --> |
| Aspect range | <!-- e.g. 16:9 only · 9:16 to 9:21 --> |

## Movement model

| | |
|---|---|
| Model | <!-- free · lane · cell --> |
| Transform owner | <!-- kinematic motor · dynamic body · CharacterController · NavMeshAgent · root motion · the cell map. Exactly one. --> |
| Step | <!-- fixed step for simulation (0.02) · frame, for a CharacterController --> |
| Level unit | <!-- tile 1 × 1 · cell and layout · kit module 2 m · lane 1.3 × chunk 40 --> |
| Facing | <!-- move direction snapped to 4 · aim direction · body yaw · fixed --> |
| Genre file used | <!-- reference/genre-….md, and the column in it --> |

## The numbers

<!-- Decide the visible numbers; derive the rest with
     `python3 scripts/level_metrics.py …`; fill the "In the game" column from
     `python3 scripts/jump_report.py …`. Leave out rows the movement model has no use for. -->

| Number | Designed | In the game | Source |
|---|---|---|---|
| Body: width × height | | | |
| Top speed · time to reach · time to stop | | | |
| Apex height · time to apex | | | |
| Gravity · jump velocity (derived) | | | `level_metrics.py` |
| Fall multiplier · max fall speed | | | |
| Coyote time · jump buffer | | | |
| Apex on the fixed step | | | `level_metrics.py` → `derived.apex` |
| Air time on level ground | | | `jump_report.py` |
| Step offset · slope limit | | | |
| Lane: count × spacing · change time · forward speed | | | |
| Cell: size · step time · range per move or turn | | | |

### Reach — what a level may contain

<!-- Paste the `reach` rows from level_metrics.py, in level units. "Usable" is the main-path
     maximum; between usable and widest is a deliberate challenge only. -->

| Landing relative to take-off | Widest gap | Usable gap |
|---|---|---|
| | | |

| Clearance | Minimum |
|---|---|
| Door / opening width | |
| Corridor width | |
| Landing platform length | |
| Ceiling for a full jump | |
| Minimum hazard sight distance (lane) | |

The command that reproduces this block:

```bash
python3 scripts/level_metrics.py --apex … --time-to-apex … --run-speed … --fall-multiplier …
```

## Who answers each need

<!-- One row per need this game has. Name the skill and the file; where no skill owns the need,
     name the genre file section that carries the method. Remove rows that do not apply, and
     keep one alternative where a cell offers two. -->

| Need | Answered by | Status |
|---|---|---|
| Brief and invariants | `unity-game-brief` | |
| Project and packages | `unity-new-project` | |
| Input: actions, the struct gameplay reads | `unity-input` | |
| Touch controls | `unity-input` | |
| Player motor | <!-- 2D: `unity-2d-controller` · 3D: `unity-3d-controller` → reference/third-person.md, reference/first-person.md or reference/topdown-and-fixed.md --> | |
| Bodies, colliders, layer matrix | <!-- `unity-physics-2d` · `unity-physics-3d` --> | |
| Camera rig | `unity-camera` | |
| Animator parameters and states | `unity-animation` | |
| Animator bridge from the motor | <!-- 2D: `unity-2d-controller` → reference/facing-and-animator-bridge.md · 3D: `unity-3d-controller` → reference/animator-bridge.md --> | |
| Character art into the project | <!-- frames: `unity-2d-sprites` · bones on a sprite: `unity-2d-animation` · 3D: `unity-rigged-character` --> | |
| Draw order, 2D lights, parallax | <!-- `unity-2d-rendering` --> | |
| Level geometry and level data | <!-- 2D: `unity-tilemap` for palettes, `unity-2d-level` for the level · 3D: `unity-3d-level` → reference/greybox.md, reference/modular-kit.md --> | |
| Cells, range, turns | <!-- `unity-2d-grid` --> | |
| Pathing for opponents | <!-- cells: `unity-2d-grid` → reference/pathfinding.md · NavMesh: `unity-navigation` --> | |
| Pickups, switches, hazards | <!-- genre file --> | |
| 3D lighting: modes, bake, probes, shadows | <!-- `unity-lighting` → reference/light-modes.md --> | |
| HUD and menus | `unity-game-ui` | |
| Probe, situations, journeys | `unity-play-harness` | |
| Frame budget | `unity-profiling` | |
| Scene cost: LOD, occlusion, batching | <!-- `unity-scene-optimisation` → reference/lod.md, reference/occlusion.md --> | |

## The checks this recipe is held to

<!-- One line each, runnable. These are the exit condition of the 3C prototype stage
     (reference/pipeline-stages.md) and they stay in the project for good. -->

| Check | Command | Passes when |
|---|---|---|
| Level numbers inside reach | `python3 scripts/level_metrics.py … --gap … --height …` | exit 0 |
| The jump is the designed jump | `python3 scripts/jump_report.py <timeline> --grounded-key grounded --apex … --air-time …` | exit 0 |
| Controls journey | | `violations=0`, samples > 0 |
| Character journey | <!-- 3D: `-testFilter Controller3DJourney` (`unity-3d-controller` → templates/Controller3DJourneyTest.cs) --> | `violations=0`, samples > 0 |
| Camera journey | | `violations=0`, samples > 0 |

## Changes

<!-- When a constraint or a number changes after levels exist: the date-free reason, what
     changed, and which checks were re-run over which levels. -->

| What changed | Why | Checks re-run |
|---|---|---|
| | | |
