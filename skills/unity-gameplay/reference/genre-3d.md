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

1. **Greybox to scale.** Blocks snapped to 1 unit, on a `World` layer: a room, a door at
   1.2 × 2.2, a 0.3 step, a 30° ramp, a 1-unit ledge, and a 1.8-unit capsule left standing in
   it as a ruler. No art. The metrics sheet and the builder that makes the room from it:
   `unity-3d-level` → `reference/greybox.md` (`resources/Editor/GreyboxBuilder.cs`).
2. **Controls.** A struct with `move`, `look`, `jumpPressed`, `sprintHeld` — `unity-input`.
3. **Character.** The controller for the column, from `unity-3d-controller` (below). Register
   it with the probe, where `run` is the `ThirdPersonController` and `chest` an empty child at
   the capsule's centre:

   ```csharp
   GameProbe.SetPlayerVelocity(() => chest, () => run.Velocity);   // the centre, not the feet
   GameProbe.Register("grounded", () => run.Grounded);             // the motor's, never isGrounded
   GameProbe.SetState(() => run.State);                            // Grounded · Rising · Falling
   ```

4. **Journey 1 — the walk.** Drive up the step, up the ramp, and into a wall. Assert the runner
   is never inside `World` (`JourneyAsserts.NeverInside`), that `grounded` stays true on the
   ramp, and that speed never exceeds the designed run speed. Ready-made on a box room:
   `unity-3d-controller` → `templates/Controller3DJourneyTest.cs`
   (`ThirdPerson_Ramp_IsClimbedGroundedAndHeld`, the two step tests); on the real greybox:
   `unity-3d-level` → `templates/GreyboxJourneyTest.cs`.
5. **Journey 2 — the jump.** `ThirdPerson_Jump_ReachesTheConfiguredApex` in the same template,
   then `scripts/jump_report.py --grounded-key grounded --apex …` on the timeline it writes.
6. **Camera.** `unity-camera` → `reference/follow-3d.md`. Journey 3: the camera never ends a
   frame on the far side of a wall, and its position does not jitter against the character.
7. **Animation.** Feed the controller's facts to the Animator through the bridge —
   `unity-3d-controller` → `reference/animator-bridge.md`, on the contract in
   `unity-animation` → `reference/parameter-contract.md`.

### The controller, by column

The motor, its four controllers and their journeys are `unity-3d-controller`. Pick the file by
column:

- **Third-person** → `unity-3d-controller` → `reference/third-person.md`
  (`ThirdPersonController.cs` on `CharacterMotor3D.cs`).
- **First-person** → `unity-3d-controller` → `reference/first-person.md`
  (`FirstPersonController.cs`).
- **Fixed or overhead camera, lane run** → `unity-3d-controller` →
  `reference/topdown-and-fixed.md` (`TopDownController3D.cs`, `LaneRunnerController.cs`).
- **Which component owns the transform**, and the pairs that fight → `unity-3d-controller` →
  `reference/model-choice.md`.

## Traps

- **`isGrounded` flickers on flat ground.** Read ground from the motor's cast —
  `unity-3d-controller` → `reference/grounding-and-slopes.md`.
- **Teleporting a `CharacterController` by `transform.position`** is undone by its next `Move`;
  respawns and situations teleport through the motor — `unity-3d-controller` →
  `reference/model-choice.md`.
- **`OnCollisionEnter` on a `CharacterController`** never fires; it raises
  `OnControllerColliderHit` — `unity-physics-3d`.
- **A `Rigidbody` character moved in `Update`**, or by `transform.position`, tunnels and
  jitters — `unity-3d-controller` → `reference/model-choice.md`.
- **Camera-relative input while the camera cuts** reverses the character under a held stick —
  `unity-3d-controller` → `reference/topdown-and-fixed.md`.
- **Mouse look multiplied by `deltaTime`** makes sensitivity depend on frame rate —
  `unity-3d-controller` → `reference/first-person.md`.
- **The first-person body in its own camera** — `unity-3d-controller` →
  `reference/first-person.md`.
- **The camera through the wall.** A third-person boom needs collision and a corridor at least
  as wide as the boom is long — `unity-camera` → `reference/follow-3d.md`.
- **Models imported at the wrong scale** make every number above wrong at once. Stand the
  1.8-unit capsule next to the character before tuning anything — `unity-3d-level` →
  `reference/greybox.md`, and `unity-3d-models` for the import.
- **Overhead: `NavMeshAgent` and `CharacterController` on one object** are two owners —
  `unity-3d-controller` → `reference/model-choice.md`, then `unity-navigation` →
  `reference/recipes.md`.
- **Lane run: hazards as triggers with no `Rigidbody` on either side** never fire. The runner
  carries a kinematic one — `unity-physics-3d`.
- **Lane run: thousands of units from the origin**, the runner shimmers — `unity-3d-controller`
  → `reference/topdown-and-fixed.md`.
- **Tuning on a 144 Hz monitor for a 30 fps phone.** A `CharacterController` moves on the frame,
  so its apex depends on the frame rate unless the motor integrates for it —
  `unity-3d-controller` → `reference/jump-and-air.md`. Run the journeys at the shipping frame
  rate (`Application.targetFrameRate`) — `unity-device-testing` for the device itself.

## Where each need is answered

| Need | Answer |
|---|---|
| Move, look, jump actions; the input struct; a scripted driver | `unity-input` → `reference/reading-input.md` |
| Mouse and stick look, aim at a ground point | `unity-input` → `reference/pointer-and-aim.md` |
| Swipes and on-screen sticks | `unity-input` → `reference/touch-and-on-screen.md` |
| Orbit, first-person, overhead and fixed rigs; boom collision | `unity-camera` → `reference/follow-3d.md` |
| Camera jitter against the character | `unity-camera` → `reference/update-order-and-jitter.md` |
| Cinemachine class names for the installed major | `unity-camera` → `reference/version-and-names.md` |
| Who owns the transform; two owners | `unity-3d-controller` → `reference/model-choice.md` |
| Third-person controller: camera-relative stick, turn rate, lock-on | `unity-3d-controller` → `reference/third-person.md` |
| First-person controller: yaw on the body, pitch on the head, crouch | `unity-3d-controller` → `reference/first-person.md` |
| Fixed or overhead camera controller, pointer aim, the lane runner | `unity-3d-controller` → `reference/topdown-and-fixed.md` |
| Grounding, slopes, steps, moving platforms | `unity-3d-controller` → `reference/grounding-and-slopes.md` |
| Jump from apex and time, coyote time, buffer, frame-rate independence | `unity-3d-controller` → `reference/jump-and-air.md` |
| The Animator bridge from the controller | `unity-3d-controller` → `reference/animator-bridge.md` |
| The parameter contract the bridge follows | `unity-animation` → `reference/parameter-contract.md` |
| Locomotion blend trees | `unity-animation` → `reference/blend-trees.md` |
| Root motion | `unity-animation` → `reference/root-motion.md` |
| Foot IK | `unity-animation` → `reference/ik-and-rigging.md` |
| A rigged, animated character in the project | `unity-rigged-character` |
| Hit boxes and colliders on a rig | `unity-rigged-character` → `reference/gameplay-rig.md` |
| Click-to-move, agents, a NavMesh baked for the gate room | `unity-navigation` → `reference/recipes.md` |
| Raycasts, ground checks, triggers that do not fire | `unity-physics-3d` → `reference/queries.md` |
| Importing and budgeting models | `unity-3d-models` |
| Post-processing on a frame budget | `unity-render-urp` |
| Journeys; the never-inside invariant | `unity-play-harness` → `reference/journeys.md` |
| Jump, step, door and corridor numbers | `reference/level-metrics.md` |
| Greybox from a metrics sheet; the walk journey | `unity-3d-level` → `reference/greybox.md` |
| Modular kit: grid, pivots, gaps between pieces | `unity-3d-level` → `reference/modular-kit.md` |
| Prefabs, variants, overrides; a room as a prefab or a scene | `unity-3d-level` → `reference/prefab-architecture.md` |
| Collision proxies, stairs as a ramp, the layer scheme | `unity-3d-level` → `reference/collision-proxies.md` |
| Terrain, holes, a prop scatter | `unity-3d-level` → `reference/terrain.md` |
| Splines, the lane on a curve, roads, decals | `unity-3d-level` → `reference/splines-and-decals.md` |
| Light modes: realtime, mixed, baked | `unity-lighting` → `reference/light-modes.md` |
| Baking the gate room and reading the bake back | `unity-lighting` → `reference/bake-setup.md` |
| Light probes, probe volumes, reflection probes | `unity-lighting` → `reference/probes.md` |
| Ambient light, the sun source, fog; a scene that looks unlit | `unity-lighting` → `reference/environment.md` |
| Shadows: distance, cascades, what each artefact means | `unity-lighting` → `reference/shadows.md` |
| Lighting on a phone | `unity-lighting` → `reference/mobile-subset.md` |
| LOD on kit pieces and props | `unity-scene-optimisation` → `reference/lod.md` |
| Occlusion culling | `unity-scene-optimisation` → `reference/occlusion.md` |
| Batching: SRP Batcher, instancing, static | `unity-scene-optimisation` → `reference/batching.md` |
| Per-layer culling distances | `unity-scene-optimisation` → `reference/culling-distances.md` |
| Texture memory and mipmap streaming | `unity-scene-optimisation` → `reference/texture-streaming.md` |
| Which interactable is selected: overlap on a tick in third person, a ray from the view in first person | `unity-interaction` → `reference/detection-choice.md` |
| The switch and the gate: a switch owns a bool, the gate a state machine and its collider | `unity-interaction` → `reference/doors-and-switches.md` (`resources/GateSwitch.cs`, `templates/InteractionJourneyTest.cs`) |
| The use prompt, its glyph and hold ring | `unity-interaction` → `reference/prompts.md` |
| Pickups counted once | `unity-interaction` → `reference/pickups.md` |
| One swing, one damage event; hit and hurt layers | `unity-combat` → `reference/attack-windows.md`, then `unity-combat` → `reference/hit-and-hurt-layers.md` |
| The sweep a blade or a fist makes, every step | `unity-combat` → `reference/melee-queries.md` |
| Shots that stop at a thin wall; invincibility and knock-back through the controller | `unity-combat` → `reference/projectiles.md`, then `unity-combat` → `reference/iframes-and-knockback.md` |
| The sentry: patrol, sight, chase, return | `unity-game-ai` → `reference/patrol-and-chase.md` (`resources/SentryBrain.cs` moved by `resources/NavMeshAgentMover.cs`) |
| Sight as range, angle and one cast against `World`, on a budget | `unity-game-ai` → `reference/perception.md` |
| A sentry with more than three states: a state machine or a tree | `unity-game-ai` → `reference/state-machine.md`, then `unity-game-ai` → `reference/behaviour-tree.md` |
| Waves and hidden spawn points | `unity-game-ai` → `reference/spawners-and-waves.md` |
| The Boot scene; rooms loaded additively; a loading screen | `unity-scene-flow` → `reference/bootstrap.md`, then `unity-scene-flow` → `reference/additive-scenes.md` |
| Pause, and what stops with it | `unity-scene-flow` → `reference/game-state-and-pause.md` |
| The save file; checkpoints and a respawn through the motor | `unity-scene-flow` → `reference/save-format.md`, then `unity-scene-flow` → `reference/checkpoints.md` |
| Lane run: hazards and pickups from a pool | `unity-scene-flow` → `reference/pooling.md` |
| A hit: hit stop, flash on a lit material, sparks, sound | `unity-game-feel` → `reference/feedback-stack.md`, then `unity-game-feel` → `reference/flash-and-squash.md` |
| Impact particles; VFX Graph or not | `unity-game-feel` → `reference/particles.md` |
| Footsteps and the gate's sound as named events, placed in 3D | `unity-game-feel` → `reference/sfx-events.md` |
| Rumble on a pad | `unity-game-feel` → `reference/haptics.md` |
| HUD placement around the vanishing point | `unity-game-ui` → `reference/hud-placement.md` |
| Frame time on the target device | `unity-profiling` |
