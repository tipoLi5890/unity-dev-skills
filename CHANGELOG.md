# Changelog

Versions are the plugin's, in `.claude-plugin/plugin.json`.

## 0.22.0

Forty-seven skills. Six new ones are the 2D world: `unity-2d-controller`, `unity-physics-2d`,
`unity-2d-rendering`, `unity-2d-level`, `unity-2d-grid` and `unity-2d-animation`. `unity-gameplay`
routes its 2D recipes to them by file, and the neighbours that ended in a 2D dead end name an owner.


- **`unity-2d-controller` — a platformer character asks physics where the ground is.** A dynamic
  body left to the solver slides down slopes, sticks to walls and jumps a different height every
  time, so the character decides its own velocity and uses the engine only to ask what is in the
  way. Two halves never mix: `resources/PlatformerController2D.cs` holds the rules — coyote time,
  buffer, the short hop, dash, wall jump — and `resources/PlatformerMotor2D.cs` holds collision —
  ground, slopes, one-way platforms, the platform under the feet — joined by one `Move(velocity,
  dt)` call. `resources/MovingPlatform2D.cs` works out its own velocity for a rider,
  `resources/TopDownMotor2D.cs` is the dynamic body with gravity scale 0 for a game seen from above,
  `resources/GridStepMover.cs` commits a cell and tweens the transform after it, and
  `resources/AnimatorBridge2D.cs` is the one writer of the Animator, fed from whichever of the three
  is on the object. Apex height and time to apex are the tunables; gravity and jump velocity are
  derived, and the fixed step puts the apex at 2.85 for a designed 3.
  `templates/PlatformerJourneyTest.cs` asserts that apex, a press 0.08 s after the ledge honoured, a
  press at 0.16 s refused and a press 0.10 s before landing buffered; `PLATFORMER_JOURNEY_BREAK` set
  to `coyote`, `buffer` or `tap` turns one test red. `templates/TopDownJourneyTest.cs` covers
  diagonal speed, wall slide and stopping distance. Six reference files: the model choice, the
  platformer, jump maths, free top-down movement, the grid step, and facing with the Animator
  bridge.
- **`unity-physics-2d` — Box2D answers in its own vocabulary.** A PhysX rule renamed with a `2D`
  suffix is usually wrong: a kinematic `Rigidbody2D` moves under its velocity, a ray that starts
  inside a collider hits it, sleep is a timer, there are two collision-detection modes and z
  separates nothing. A symptom table routes to seven sections, first match wins: no callback fires,
  tunnelling, a cast that misses or hits itself, a body that stops or jitters, shapes that are not
  what they look like, effectors and one-way platforms, and editor yes, build no.
  `resources/CollisionDebugger2D.cs` is the two-sided probe, attached to both objects of a suspected
  pair and removed afterwards; `resources/Editor/Physics2DAudit.cs` prints the open scene's 2D
  physics set-up as one JSON object and changes nothing. Five reference files: bodies and
  simulation, layers and the matrix, queries, tilemap colliders, and effectors and joints.
- **`unity-2d-rendering` — draw order is four keys in a fixed priority, and z is the last of them.**
  Sorting layer, Order in Layer, render queue, then distance along the sort axis: the first key that
  differs decides and the rest are never read. The second half is the light — with no `Light2D` in
  the scene lit sprites draw at full colour, and the first one turns everything it does not reach
  black. `resources/Editor/Renderer2DSetup.cs` reports the pipeline asset in force, whether a 2D
  Renderer is the default and the sort mode and axis on it, which are the only ones read;
  `resources/Editor/SortingAudit.cs` lists every renderer in the open scenes with its four keys, its
  `SortingGroup`, whether its material is lit, and the pairs that tie. `resources/ParallaxLayer.cs`
  follows a fraction of the camera's travel with an optional wrap and pixel snap, and names no
  Cinemachine type. Six reference files: sort order, Y-sort, 2D lights, shadows and normals, masks
  and materials, and parallax.
- **`unity-2d-level` — a level is data with invariants, and the Tilemap is one renderer of it.**
  `resources/LevelData.cs` is the level — size, layers of tile ids, spawn, gate, pickups, entities
  with fields — and names no tile asset, prefab or scene. `scripts/level_validate.py` checks
  reachability from the file and three jump numbers without Unity and exits 1 naming what cannot be
  reached; `scripts/tiled_to_level.py` converts a Tiled map, flipping the rows once and decoding the
  flip flags. `resources/TilemapLevelLoader.cs` paints one `SetTilesBlock` per layer into six
  Tilemaps with fixed names, synchronises the colliders before it returns, and `Verify` counts the
  cells where the rendering differs from the data. `resources/Editor/TilemapLayerStackBuilder.cs`
  builds the stack for a side view or a top-down one and reports before it creates;
  `resources/RoomBounds.cs` is a room as a rectangle with one enter event, and
  `resources/ChunkStitcher.cs` appends chunks whose entry height equals the last exit height, in an
  order that is a pure function of the seed. `templates/sample-level.json` is a 40 × 12 side run and
  `templates/LEVEL_INVARIANTS.md` takes the level's rules, one id each. Seven reference files: the
  layer stack, level data, runtime tilemaps, rooms and chunks, external editors, SpriteShape, and
  procedural generation.
- **`unity-2d-grid` — the cell map is the truth and the transform is an animation of it.** A piece
  is in its new cell from the instant the rule says so and the sprite arrives later; no rule reads a
  transform, waits for a tween or asks a collider. Four files of plain C# with no `MonoBehaviour`:
  `resources/GridCoords.cs` for neighbours, distances, hexagonal offset, axial and cube conversion,
  rings and lines; `resources/GridPathfinder.cs` for A* and movement range by flood, with the
  heuristic picked from the neighbour rule; `resources/GridOccupancy.cs` for walls, one occupant per
  cell, push, reservation and revert; `resources/TurnQueue.cs` for initiative and the round.
  `resources/Tests/GridCoordsTests.cs` runs them in EditMode with no scene. Isometric is a drawing
  convention and hexagonal is a neighbour rule, so every lookup goes through `GridCoords.Neighbour`
  and the project's hexagonal layout is confirmed once on its own `Grid`. Six reference files:
  coordinates, neighbours and range, pathfinding, line of sight, occupancy and turns, and picking.
- **`unity-2d-animation` — a skeletal sprite is a mesh, and it costs like one.** Frame animation
  pays in texture memory and nothing per frame; a rig pays per vertex, per part, per frame, so the
  choice is made per character and counted before the art is drawn. The route is a `.psb` imported
  as a rig, then bones, geometry and weights in that order, then *Apply*.
  `resources/Editor/SkinningAudit.cs` returns one JSON object: unweighted vertices, weights that
  name a missing bone, a `SpriteSkin` that is not ready, and per character the skins, bone
  Transforms, vertices and triangles one instance deforms each frame.
  `resources/Editor/SpriteLibraryBuilder.cs` builds a `.spriteLib` from folders or sprite names and
  reports before it writes; `resources/SkinSwap.cs` changes a skin or one category of equipment at
  runtime and refreshes the resolvers. Five reference files: skeletal against frames, PSB to rig,
  bones and weights, the Sprite Library, and 2D IK.
- **`unity-gameplay` routes its 2D recipes.** The hub's routing table gains a row for each of the
  six, and the 2D genre files stop carrying the method in essentials. `reference/genre-2d-side.md`
  and `genre-2d-topdown.md` send the motor, jump maths and the Animator bridge to
  `unity-2d-controller`, bodies, casts, tilemap colliders and one-way platforms to
  `unity-physics-2d`, draw order, lights and, in the side run, parallax to `unity-2d-rendering`, and
  layer stacks, rooms, chunks and level files to `unity-2d-level`; `genre-2d-grid.md` keeps the rule
  set as one class and sends coordinates, range, paths, sight, occupancy and picking to
  `unity-2d-grid`; `genre-2d-fixed-screen.md` keeps playfield fit, bullets as data, hotspot picking
  and the launch gesture. `templates/GAMEPLAY_RECIPE.md` gains rows for bodies and the layer matrix,
  the Animator bridge, draw order, and cells, range and turns. What the hub still carries in
  essentials is the 3D motor, in `reference/genre-3d.md`.
- **Neighbours route to them.** Two dead ends in `unity-2d-sprites` close: 2D bones, skinning
  weights, PSB rigs and Sprite Library, which nothing covered, are `unity-2d-animation`, and 2D
  physics is `unity-physics-2d`. `unity-tilemap` sets a tile's collider type and hands the rest on:
  levels from data, layer stacks and runtime `SetTile` to `unity-2d-level`, cell maths and
  pathfinding to `unity-2d-grid`, `TilemapCollider2D` and composites to `unity-physics-2d`, sorting
  to `unity-2d-rendering`. `unity-physics-3d` drops its best-effort 2D answer —
  `reference/neighbour-stacks.md` keeps the one report both stacks share, a `2D` suffix in the wrong
  scene, and hands over. `unity-navigation` sends 2D pathfinding to `unity-2d-grid`; `unity-debug`,
  `unity-play-harness`, `unity-camera` and `unity-animation` name `unity-physics-2d` beside
  `unity-physics-3d` on their physics rows. `unity-animation` sends the 2D bridge to
  `unity-2d-controller` and bones on a sprite to `unity-2d-animation`, and `unity-rigged-character`
  adds the skeletal route to the same skill; `unity-camera` sends parallax and isometric sorting to
  `unity-2d-rendering` and room bounds to `unity-2d-level`; `unity-input` names
  `unity-2d-controller` as the consumer of its struct; `unity-2d-pixel-perfect` sends movement code,
  parallax and sorting out; and `unity-new-project` lists the six in its skill map and names them on
  its 2D package rows.
- **What this does not do.** No skill covers a 3D character controller, 3D level construction,
  lighting outside the 2D Renderer, scene-level optimisation, interaction, combat, AI behaviour,
  scene flow and saving, or game feel.

## 0.21.0

Forty-one skills. Four new ones cover the layer between a brief and a character that can be played:
`unity-gameplay` works out which game the project is and routes, and `unity-input`, `unity-camera`
and `unity-animation` are the 3C skills it routes to. `unity-play-harness` reads a 2D game as
readily as a 3D one, and the neighbours route to all four.

- **`unity-gameplay` — a genre is a set of constraints.** Six constraints replace the genre label:
  dimension, projection, view, movement model, transform owner and level unit.
  `scripts/fingerprint.py` reads them from a project without opening Unity — components in scenes
  and prefabs are the evidence, an installed package is not, and physics outranks renderers — and
  reports the Cinemachine major beside them; a five-step default ladder covers the project with no
  evidence and ends in one question. Five recipes follow the verdict: `reference/genre-2d-side.md`,
  `genre-2d-topdown.md`, `genre-2d-grid.md`, `genre-2d-fixed-screen.md` and `genre-3d.md`, each a
  starting set of constraints, filled into `templates/GAMEPLAY_RECIPE.md` with one row per need.
  `scripts/level_metrics.py` derives gravity and jump velocity from apex height, time to apex and
  run speed and exits 1 when a gap or a ledge is outside reach; `scripts/jump_report.py` measures
  apex and air time from a recorded timeline, because the jump the game performs is not the one the
  constants describe. `reference/pipeline-stages.md` gives each production stage an exit check.
- **`unity-input` — gameplay reads one struct, never a device.** A press happens on the render clock
  and gameplay runs on the physics clock, so `WasPressedThisFrame()` polled in `FixedUpdate` loses a
  jump on a fast frame and fires it twice on a slow one. `resources/RunInputReader.cs` reads the
  device in `Update` and latches each press with its time; gameplay spends it once from
  `FixedUpdate` through `TryUse`, which is also the input buffer. `resources/RunInput.cs` is the
  struct, with `StepRepeater` for a grid step under a held key; `resources/ScriptedRunInput.cs`
  drives the same funnel from a test; `resources/RebindStore.cs` saves overrides as JSON.
  `templates/RunActions.inputactions` has one map and three schemes — keyboard and mouse, gamepad,
  touch — and `resources/Editor/CreateRunActions.cs` builds it from script.
  `scripts/inputactions_lint.py` exits 1 on an action with no binding in some scheme, a composite
  missing a part or a binding to an action that is gone. `templates/InputJourneyTest.cs` sends ten
  taps at four fixed steps per frame and at one step per six frames and asserts as many launches as
  presses. Six reference files cover the asset, reading, touch and on-screen controls, pointer and
  stick aim, rebinding and devices, and the move off `UnityEngine.Input`.
- **`unity-camera` — a jittering camera is two clocks disagreeing.** The target moves on the physics
  step and the camera eases on the rendered frame; a table names the clock of every mover and five
  checks are worked in order, the first being a followed body with interpolation off. Cinemachine
  2.x and 3.x share a package id and almost no component names, an add with no version on Unity 6
  resolves 2.x, and everything shipped is written for 3.x — `reference/version-and-names.md` is the
  name table. Rigs: 2D side follow, runner, top down and isometric as one rig with four sets of
  numbers, a room confiner with its two caches, pixel-perfect follow, third-person orbit with
  deocclusion, over the shoulder, lock on, first person and fixed posts, then shake with a written
  budget and blends. `resources/Editor/CameraRigBuilder.cs` builds a 2D follow rig, a third-person
  rig and a fixed rig and reports before it creates; `resources/RoomConfinerSwitch.cs` is the
  one-camera room switch. `resources/CameraProbe.cs` puts `camViewport`, `camInBounds` and
  `camOffset` on the probe after the Brain has run, `templates/CameraJourneyTest.cs` records 600
  frames and asserts all three, and `scripts/camera_jitter.py` counts sign changes in the offset's
  frame-to-frame delta against a limit of 0.1. `CAMERA_JOURNEY_BREAK` set to `confiner` or `clocks`
  has to turn the journey red before a green run means anything.
- **`unity-animation` — the game's state is the truth, and the Animator renders it.** One contract
  for a 3D Humanoid and a 2D frame-clip character: one writer per parameter through a bridge that
  writes every parameter every frame, gameplay never reads the Animator, and only named moments
  cross back — an AnimationEvent, an attack window, a Timeline signal — each with a game-side
  fallback. Four Editor tools, each reporting before it writes: `AnimatorParamAudit.cs` lists every
  parameter with where the graph reads it and which scripts write it,
  `DirectionalBlendTreeBuilder.cs` builds a directional tree from clips named by direction,
  `SpriteStateGraphBuilder.cs` builds an idle, run, jump, fall and hurt controller from named clips,
  and `ClipEventWriter.cs` places an event by normalised time and reads the clip back.
  `resources/AttackWindowBehaviour.cs` opens and closes a window by normalised time and closes it on
  any exit, so a swing interrupted at 40% does not leave a hitbox on; `resources/FootIK.cs` plants
  Humanoid feet from two raycasts. `templates/AnimatorStateJourneyTest.cs` samples `animState`
  beside the game's `state` and fails when they disagree for more than three frames. Eight reference
  files: the parameter contract, blend trees, the sprite state graph, events and windows, override
  controllers, IK and rigging, Timeline, and root motion.
- **`unity-play-harness` reads a 2D game.** `GameProbe.SetPlayerVelocity` takes a delegate, so a
  `Rigidbody2D`, a `CharacterController`, a kinematic motor or a grid mover reports `vel` through
  the same key and shape as a `Rigidbody`. `GameProbe.cs` still names no 2D type and compiles with
  either physics module removed. The order is the delegate, then the `Rigidbody`, then the position
  delta — and the delta divides by unscaled time, so a journey that pins the step registers a
  delegate. `resources/JourneyInvariants2D.cs` adds `NeverInside2D`, the never-inside-solid-geometry
  rule on the x/y plane; triggers never count, and it is a separate file so a project without the 2D
  physics module compiles the rest. `templates/CourierSituations2D.cs` registers three situations —
  `ledge-drop` for a side run, `depot-aisle` for a top-down depot, `yard-step` for a sorting yard —
  with ready sets that name the 2D colliders and placements that write x and y only.
  `reference/journeys.md` says what each view is worth asserting. `templates/JourneyTest.cs` no
  longer deletes the journeys root, which took every other journey's timeline with it, and reads its
  directory from `JourneyRecorder.DefaultRoot()` or `$JOURNEY_OUT`.
- **Neighbours route to them.** `unity-new-project` gains the gameplay and 3C lines in its skill map
  and points its input funnel at `unity-input`; `reference/package-selection.md` corrects the 2D
  feature set's id from `com.unity.2d.feature` to `com.unity.feature.2d`, says a default Cinemachine
  add resolves 2.x on Unity 6 and makes 3.x the one deliberate pin, and names the owning skill on
  each package row; `reference/package-bootstrap.md` no longer says to delete the 2D packages
  outright — `2d.animation` and `psdimporter` stay when the art is skeletal, `spriteshape` for
  spline terrain, `aseprite` when that is the source format. `unity-game-brief` replaces its camera
  decision with perspective and movement, six lines written as constraints with numbers in
  `reference/visual-direction.md` and `templates/GAME_BRIEF.md`, and hands the choice of skills to
  `unity-gameplay`. `unity-2d-pixel-perfect` keeps the one Cinemachine rule and sends follow,
  confiners and blends to `unity-camera`. `unity-2d-sprites`, `unity-rigged-character` and
  `unity-navigation` send state graphs, events, attack windows and IK to `unity-animation`.
  `unity-play-harness` gains scope rows for `unity-gameplay` and `unity-input`. Two dead ends close:
  `unity-audio` names `comfyui-asset-generation` for generating music and SFX, and
  `unity-sprite-atlas` names `codex-visual` for generating artwork.
- **What this does not do.** No skill covers a 2D character controller, a 3D character controller,
  2D physics, level construction, lighting, interaction, combat, AI, scene flow or game feel. The
  genre files in `unity-gameplay` carry the essentials of a player motor, 2D physics set-up and cell
  movement — enough for a prototype that passes a journey, not a full treatment.

## 0.20.0

Thirty-seven skills. The new one, `blender-character-rig`, covers the character Mixamo cannot rig
— short limbs, a head as wide as the torso, long ears, a tail — from a generated GLB to an FBX
that has been read back by re-import. It works in a running Blender driven through its MCP
server: import, measure, place bones, compute weights, hang a prop on a hand, key an action,
render a preview, export, and compare what an import of the file holds against what went in.
Three neighbours gain the character branch that leads to it, and `unity-3d-models` routes to it.

- **Scripts that run from the skill, not pasted into a call.** Nine `bcr_*` modules over a shared
  `bcr_common.py` each expose `run(params) -> dict`. A short stub sent through the server's code
  tool puts `<skill>/scripts` on `sys.path`, reloads the module and assigns the return to
  `result`, so a call is a dozen lines of parameters and the logic is the shipped file. Every
  return has one shape: `ok`, `gates` (each with `name`, `value`, `limit`, `pass`), `created`,
  and the Blender version; `report_path` writes it as JSON. Two more scripts run on the host:
  `scripts/rig_gate.py` (stdlib only) and `scripts/frames_preview.py` (Pillow), both exit 0 / 1 /
  2 with one JSON object out.
- **Bones from measurement.** `bcr_import_prep` turns the GLB into one object with an identity
  transform, its origin between the feet, at a real height, welded by position — the worked
  20,000-triangle runner goes from 14,991 vertices to 9,994 and keeps every face, in 13 islands
  after the weld, because UVs live on face corners and a seam survives the weld. `bcr_survey` then reads
  the mesh: horizontal slices report how many separate runs of vertices each has (2 at the legs
  and the ears, 3 where the arms hang beside the body), and a box returns the centroid of the
  vertices inside it, which is how a hand, a foot and an ear tip get coordinates. `bcr_armature`
  takes the bone spec as data — head, tail, parent, `radius`, an optional `segment`, `mirror` for
  the `.R` twins — and stores it on the rig as `bcr_bones`. The worked skeleton is 22 bones.
- **Weights computed, not solved.** Automatic weights fail on a generated mesh: it is a double
  shell whose inner vertices are hidden from every bone, in several disconnected islands, so the
  solve stops or leaves vertices unweighted. `bcr_skin` needs no solve. Distance to each deform
  bone's segment is divided by that bone's radius and the nearest bone owns the vertex; it shares
  the vertex only with its own parent and children (`tau` 0.2), so an arm reaches the torso
  through the shoulder and never through the ribs; a chain named in `gradients` — ears, a tail —
  is weighted along its length so it bends as a curve; then four smoothing passes and a cut to
  four influences. The inner twin of a vertex gets the weights of the skin over it, because the
  rule only looks at where a vertex is. Nothing is deleted: the inner shell and the small islands
  stay, since the baked maps address them. It refuses a mesh whose object scale is not 1.
- **The extreme pose is the weight test.** Four numeric gates pass on weights that still look
  wrong, so the test is a picture: `bcr_pose` `apply` with an arm straight up, the other forward,
  the head turned, the spine bent, one ear folded and a leg lifted, one `bcr_preview` still, then
  `reset`. What the picture says is a table — a thin part torn into strips is hard nearest-bone
  weights and wants a gradient chain; a torso that follows a raised arm is an arm radius that is
  too large; a crease that reads as a fold wants a higher `tau` or more passes — and
  `dominant_vertices` names the bone whose radius is too small before the render does.
- **A prop on a hand bone.** `bcr_attach` measures the grip instead of taking it from the caller:
  the handle's axis is the centroid of a thin slice at the free end, the one place nothing but
  handle exists. A band further up that catches the head puts the axis beside the handle, and
  `handle_radius_ratio` shows it — about 0.3 where a handle is a few percent of the prop's length
  — so the gate is 0.15. Bone parenting attaches at the bone's tail and moves the prop by the
  bone's length; the module sets the parent, updates the view layer and assigns the wanted world
  matrix again, gated on a drift under 1e-4. `head_side` says which way the head sticks out, so
  the rotation that faces it forward is read rather than tried.
- **Poses in armature axes, and contact measured before a render.** A bone's own axes depend on
  its roll, so the same rotation means something different on every bone. `bcr_pose` takes steps
  in the armature's axes, applied in the order written — `[["Y", 40], ["X", -85]]` — and converts
  them with each bone's rest matrix. `key` writes an FK action from a frame table, keys a bone
  named in any frame in every frame, and gates that the action's slot is assigned, because an
  action without one drives nothing. `bcr_probe` then reads the striking edge in world space at
  chosen frames. A first pass that swings too far reads as the edge at floor height with
  `direction_z` near −1 at the contact frame: one read-only call shows it, by how much and which
  way, before any render; the target is then placed at the
  measured contact and gated with `within` 0.05 and `direction_z_min` −0.8.
- **Preview in chunks.** A render call has to return before the host's tool timeout, so
  `bcr_preview` renders a range a chunk at a time — twenty frames at 50% to start from — deletes
  a stale file in the range first, writes where `out_dir` says and restores the render path,
  resolution, format, camera and frame in a `finally`. `scripts/frames_preview.py` makes the GIF
  and a contact sheet of the key frames. Two things only the pictures show: a target standing
  between the camera and the character, and material slots that came out swapped.
- **The FBX round trip, and the clip-naming finding.** An export that returns `FINISHED` says a
  file was written. `bcr_fbx` snapshots the rig, exports, imports the file into a scene of its
  own and snapshots that; `scripts/rig_gate.py` compares the two on eight gates — bones, parents,
  bone positions within 0.001 m, vertex groups, the prop still on its bone, influences, scale,
  the action. The finding is in the exporter's all-actions switch. Off, the file carries one take
  with its frame numbers kept, and the take is named after the *scene*, not the action. On, every
  action in the .blend is written onto the armature — the one authored for the target object
  included — each named `<rig>|<action>` and re-based to start at 0. So the clip's name is a
  decision made before Unity: rename the scene, rename the clip in the importer, or keep one
  action per .blend and switch all-actions on. Two smaller ones: the importer's default
  `anim_offset` moves every key by one frame, so the read-back passes 0; and the baked take has
  an f-curve for every channel of every bone (229 against 30 authored for the worked rig), which
  is expected.
- **Session discipline.** The server is found by listing its tools, not by recalling them, and
  unreachable is not absent. New work goes in its own collection; what the user made is hidden,
  never deleted, and a camera, light or world is added beside theirs. Every non-additive change
  is reported with whether the file is saved, and nothing is saved unasked. A `bcr_*` call that
  raises removes what it had created, and calls are idempotent by name. With a non-English UI
  `nodes["Principled BSDF"]` raises `KeyError`, so nodes are found by `bl_idname`. A render tool
  given an output path may write into Blender's own temp directory: the path in its result is the
  authority. Seven references carry the depth — `reference/mcp-session.md`,
  `reference/scene-discipline.md`, `reference/import-and-survey.md`,
  `reference/armature-and-skinning.md`, `reference/prop-on-bone.md`,
  `reference/action-and-preview.md`, `reference/fbx-export.md`.
- **`codex-visual`** gains the source image for a character: a strict symmetric A-pose with the
  arms clear of the hips and a gap between the legs, chunky evenly thick limbs with mitten hands,
  thin parts drawn thick and the same in every view, no held prop — that is generated separately
  — and no shadow or ground. The four-view sheet is drawn from the approved three-quarter image
  and passes the same `--views` gate as a prop. One failure is caught only by eye: an ear whose
  inner colour faces the viewer in one side view and forward in the other, fixed by saying in the
  prompt that the inner ear always faces forward.
- **`comfyui-asset-generation`** gains the character row: the multi-view template at the close-up
  budget — 20,000 faces, a 768 remesh, a 2048 texture — gated by `inspect_glb.py --max-triangles
  20000 --texture-size 2048`. What comes back is upright, axis-aligned and unrigged, and the
  double shell that costs a prop half its triangles is, on a character, the reason automatic
  weights fail.
- **`unity-rigged-character`** opens on the choice of route. Standard humanoid proportions and
  stock clips go to Mixamo, as before; chibi proportions, short limbs, extra parts or a custom
  action go to `blender-character-rig`. The two differ on purpose — Mixamo wants a T-pose and
  stray shells removed, the Blender route takes an A-pose and keeps every island and the inner
  shell — and both end in the same FBX import.

What `blender-character-rig` does not do: IK, so the feet stay planted and the action is
single-handed where short arms do not meet; closed hands, so a handle passes through the palm;
facial animation; the Unity import, the Avatar and whether the Humanoid mapping accepts the
skeleton, which are `unity-rigged-character`'s to confirm in an Editor; and installing Blender,
its add-on or the MCP server, which stays the user's.

## 0.19.0

`comfyui-asset-generation` grows image-to-3D: one image or four views become a game-budget GLB on
a self-hosted ComfyUI, and the budget is set where the mesh is generated — not repaired after it.
The same release teaches its music to stay instrumental when it is a background bed, and gives
`codex-visual` a call that proves it produced a file and a gate on the image before a conversion.

- **Three API templates**, core nodes only: `templates/pixal3d_image_to_model_api.json` and
  `templates/trellis2_image_to_model_api.json` (one image → GLB) and
  `templates/pixal3d_multiview_to_model_api.json` (four views → GLB). The saved UI workflow picks
  its path with switch nodes; an API graph has nobody to flip them, so each switch is resolved
  statically into one template per path. Node ids are the UI workflow's, so a knob has the same
  address in both.
- **Six deliberate differences from the saved UI workflow**: 8000 faces instead of 700000, a 384
  remesh instead of 768, a 1024 texture instead of 4096, the normal bake tied to that texture size
  instead of a fixed 2048, occlusion `bias` 0.05 instead of 0.01, unwrap `padding` 4 instead of 1.
  The UI values make a ~65 MB showcase file; the defaults make a ~4 MB hero. The presets are named
  for the rows of `unity-3d-models`' triangle-budget table and sit inside them — pickup 2000,
  obstacle or environment prop 4000, hero 8000 — with a 20000-face close-up prop above the table.
- **Which path is the decision that matters.** Pixal3D from one image is pixel-aligned: highest
  fidelity, but the mesh takes the pose of the input view — a three-quarter view from above comes
  back tilted in world space, and a straight-on view comes back upright with invented depth (a
  pickup crate 2.5× too deep). Pixal3D multi-view is axis-aligned with true proportions on the
  four seen sides, a little darker than the input, and invents the top a level turnaround never
  shows — a lid emblem is lost. TRELLIS.2 gives an upright pose of its own at the lowest fidelity:
  small details smear, hue drifts. The pose is not an error to tune away: rotate in Unity, or
  take the multi-view path.
- **The one-scale finding.** The multi-view model wants the same scale in every view. Cropping
  each sheet panel to its own mask keeps one scale only when every view is height-limited; on an
  object wider than tall the front is fitted to its width and the side to its height, and a crate
  came back with its depth at 0.88 of the width instead of 0.56. `codex-visual` gains
  **`scripts/turnaround_to_views.py`**, which splits a one-row turnaround by content (panels are
  not equal width) and cuts all four views as squares of one side — which is why the multi-view
  template takes four prepared views and has no background-removal step.
- **The left/right finding.** Side views fed swapped do not break the geometry of a
  near-symmetric object; they show up as colour — orange turned yellow-green and bled across
  neighbouring panels. Re-seeding does not fix it; swapping nodes `802` and `804` does, and is the
  first move on any hue shift.
- **Face target and remesh resolution move together.** 5000 faces asked of a 768 remesh shredded
  the mesh: a thin part vanished, the silhouette collapsed and the bounding box shrank 12%. 4000
  from a 256 remesh and 2000 from 128 held both. Skipping the remesh breaks too — half the
  requested faces, shrunken bounds, three times the run time. A shrunken `extents` against a
  higher-budget run of the same input is the tell.
- **The double shell.** Every face has an opposite-facing twin a fraction of a percent of the
  bounding-box diagonal behind it, on both model paths, and no remesh option removes it
  (`sign_mode` sdf damages the mesh on top). It faces away from the viewer, so a budget of N
  triangles buys the visible detail of N/2 — and the GLB's material is exported double-sided, so
  the imported material is set to front faces only.
- **The occlusion finding.** At the UI workflow's `bias` 0.01, 6–24% of the outward-facing surface
  bakes pure black; at 0.05 it is 1–3%, at 0.1 about none. The map still looks half black at any
  bias, because the inner shell is legitimately dark and owns half the atlas — so it is judged by
  shape: whole black charts are the shell, speckle inside a lit chart is the error.
- **Two gates.** **`scripts/inspect_glb.py`** is the numeric one: triangles against a budget (over
  by 5% or under half of it fails), material count, texture size, required texture slots, bytes;
  exit 0 / 1 / 2, one JSON object out. The QA renders each template saves beside the GLB are the
  visual one — `front`, `right`, `back`, `left`, `top`, `clay`, `occlusion`, `uv_atlas`, and on
  the single-image templates `crop`, which is all the model saw of the input.
- **`scripts/comfy_asset_client.py`** takes a repeatable `--set NODE.INPUT=VALUE` (JSON when it
  parses, so a list rewires a link), refuses to submit while any input still holds a
  `REPLACE_WITH_` placeholder, and prints `elapsed_seconds` and `vram_free_min`.
- **`codex-visual`** gains `reference/image-to-3d-input.md` — the image a 3D graph can use: the
  mask crop is everything the model sees, lighting in the image becomes base colour, a contact
  shadow becomes geometry, the project's usual key colour needs no change, and a turnaround is
  asked as four objects in one row on flat black with the approved three-quarter image attached.
- **An instrumental bed that stays instrumental.** MiniMax Music 3 is a song model, and a
  background bed with a voice in it fights the game's own sound. Fifty-odd 30-second takes across
  a chase bed, a menu bed and a world-map bed, each screened by separating the vocal stem and
  tagging the stem: a plain caption with **empty lyrics** came back with a hum or a voice on 4 of
  8; `[Instrumental]` in the lyrics on 1 of 8; a caption that only mentioned a choir pad on 1 of
  2; and the form now documented — a three-section caption whose Vocal Details spell the
  exclusions out and name the lead instrument, with `[Intro]` / `[Instrumental]` / `[Outro]` as
  the only lyrics — on 1 of 23. **`reference/instrumental-bgm.md`** carries that wording, a
  caption skeleton, what makes a caption a bed rather than a song, and three worked captions for
  the courier run. Length is the other finding: `max_duration` is only a ceiling — a 90-second
  request with one described section came back at 26–35 s, and the same bed with five described
  sections at one to two minutes, varying by seed. **`scripts/check_instrumental.py`** is the
  screen (a stem separator alone calls a flute a voice; the tagger on the stem tells them apart),
  and the client's `--set` takes `@file`, so a caption with line breaks is not a shell-quoting
  problem. The music template's default lyrics are now `[Intro]` / `[Instrumental]` / `[Outro]`.
- **`codex-visual` is easier to enter and harder to fool.** `SKILL.md` opens on a table from what
  you want (a set that matches, a loop that jitters, a fringed cut-out, a source image for 3D) to
  where to read. **`scripts/codex_generate.py`** makes the generation call and proves it:
  `codex exec` exits 0 when the agent model is rejected and when no image was made, so the script
  probes the model, runs from a scratch directory (the image tool leaves a copy under `output/`
  wherever it runs), takes the original from `generated_images` and reads back its size — exit 3
  for a rejected model, 4 for no image. **`scripts/audit_3d_source.py`** gates an image before a
  conversion: square, a flat field out to the frame, one piece, clear of the edge; and with
  `--views`, four views at one scale. `reference/animation-sheets.md` had grown to three times the
  size of `SKILL.md` and is now three files by purpose — the prompt side stays there, diagnosis
  and acceptance thresholds are `reference/animation-faults.md`, script usage, previews, the
  pixel post-process and the handoff are `reference/animation-scripts.md` — with every pointer
  renumbered. `SKILL.md` no longer repeats the four locks in full and has room again.
- **`unity-3d-models`** no longer tells you to simplify a mesh that was generated at budget: its
  normal map and occlusion are baked from the dense mesh onto the decimated one, and a later
  simplify throws that correspondence away. Inspect first; set the budget in the graph and
  regenerate. Largest extent is about 1 unit with the origin at the bounding-box centre, so scale
  and offset go on the `Model` child.

## 0.18.0

`codex-visual` learns that position and size are never the model's job — and gets the scripts
that make the promise hold, plus the gate that reads it back from the files that shipped.

- **The stray-pixel finding.** A keyed render keeps one or two pixels at alpha ~20 in a canvas
  corner. `slice_grid.py` and `normalize_set.py` measured a plain `alpha > 16` bounding box, so
  that pixel dragged the box to the canvas edge: a set asked at 78% of the canvas shipped at 58–68%,
  pushed up to 14% of the canvas off-centre, per asset by a different amount — and read as "the
  model draws some sprites off-centre". A set shrunk the same way in every cell was even internally
  consistent (identical bboxes, 0% spread), so the old CV line passed it. Both scripts now isolate
  the **subject** (pixels at alpha ≥ 96 grown through their connected soft pixels; a speck never
  joins and is cleared), place the subject's **core** (alpha > 40, so a glow's haze does not steer
  it), and paste mask-free — a masked paste onto transparency had been squaring the alpha of every
  soft rim. `--raw-bbox` keeps the old behaviour for a diff against an old delivery.
- **`scripts/audit_set.py`** — the geometry gate on shipped files: per asset the core, the centre
  offset, the fill against `--expect-frac`, the strays; the set's width/height spread; with
  `--symmetry` mirror IoU, tilt and rim level for upright objects. Exit 1 on a centre over 2 px or
  a fill more than 0.02 off. It is the step between "normalised" and "registered".
- **`slice_grid.py`** cuts on the found gutters (the emptiest row/column within a third of a cell
  of each equal split) instead of the exact split, reports a haze-only cell as EMPTY instead of
  scaling the haze up, warns when a subject — not its haze — touches the cell edge, and takes
  `--canvas-h` for a non-square asset. **`normalize_set.py --recenter`** repairs a shipped set by
  translation only, no rescale, for the files whose keyed source is gone.
- **`sheet_to_frames.py --drop-strays`** — the same speck, in an animation sheet, gives one cell
  `edge yes`, a bottom at the cell edge and a baseline of 0; the flag clears it before measuring
  and prints what it dropped, leaving the alpha ≤ 16 haze to `--clear-below-thr`.
- **`SKILL.md`** gains the symptom table for this — including the question "can I hand the model a
  1x1 / 2x2 / 4x4 template with crosshairs so it draws in the right place?" (no: it paints the
  guides and still places approximately; the grid belongs on the output side, one sheet per
  family), and why a single member regenerated alone drifts from its siblings while the same three
  on one sheet come back identical to the pixel. `reference/codex-runtime.md` §5 records it as
  keying Trap 3; §8 and `reference/image-model.md` §6 carry the new flags and the gate step.

The same rule, for **animation**: where a frame sits is never the model's job either, and neither
is its edge. Both findings come from one shipped set of 25 animation sheets whose characters
"jittered wildly" and whose cut-outs had a pink rim — re-measured from the raw sheets, old pipeline
against new.

- **The jitter finding.** `sheet_to_frames.py` kept each cell's in-cell position, on the belief that
  in a sheet of frames the arc *is* the cell-to-cell offset. On a generated sheet it is the model's
  grid: over 21 character sheets the body wandered 17–119 px inside its cell (3–24% of it), the
  grid **column** explained 81–100% of the sideways spread on 18 of them and the **row** 90–100% of
  the vertical spread on 19 — the two exceptions were a jump and a leap. Written that way, one idle
  pose sat 65–120 px apart on alternate frames and feet lines 16–57 px apart; `--align both`, the
  repair the skill offered, still left 8–45 px on 14 of 21, because a centroid is steered by a bat.
  A contact sheet tiling one frame per cell shows none of it. `--register ground | free` now seats
  every frame on one reference by its **core silhouette** (the solid shape opened by 4 px, by FFT
  overlap; feet locked to one line for a grounded action): 0 px out of register on all 21 and feet
  within 2 px on the 19 grounded ones, on the same sheets, with no regeneration — the eleven takes
  a regeneration had replaced pass too. **`--register` is required to write** (`ground` · `free` · `centroid` · `keep`);
  `keep` is the old behaviour and is gated when the kept wander follows the grid.
- **The cut finding.** The model does not draw its rows at thirds: the equal split cut the subject
  in 34 of 85 frames on one take and 21 of 85 on its regeneration with a stricter prompt (asked for
  75% of the cell height, drew 86–98%). `sheet_to_frames.py` now cuts on the found gutters, columns
  per row — 0 of 85 on both takes — and a cut already on an empty line does not move, so
  `--gutters nominal --register keep` reproduces an old set byte for byte.
- **The fringe finding.** A binary key leaves the anti-aliased rim opaque and half key: 25–40% of
  the rim within 150 RGB of the key (`fringe`) and 43–60% measurably mixed with it (`tint`);
  `remove_chroma_key.py --despill` left 5–52% / 26–84% per static asset. *Alpha Is Transparency*
  repairs transparent pixels, and these are opaque — the claim in `sheet_to_frames.py` that it
  covered this was wrong. **`scripts/key_unmix.py`** un-mixes the 2 px boundary band only (alpha
  along key→outline; `--edge fill` projects an effect's rim onto the fill beside it): 0.0–0.2% /
  0.0–0.3%, interior untouched. `--defringe` repairs sprites already shipped (49 assets to
  0.0–0.7% / 0.0–0.4%, bounding boxes within 1 px). Two simpler keys are documented as wrong, with
  numbers: alpha from RGB distance everywhere (36–83% of the interior translucent, or the rim left
  33–41% mixed), and an effect keyed by spill (a pink rim on 29% of a yellow spark) — `tint` exists
  because `fringe` reads 0.00% on both.
- **Gates instead of numbers.** `sheet_to_frames.py` ends on `verdict OK | FAIL` and **exits 3** on
  a fault with one repair: a subject cut by the sheet edge or a cell line, foreign pixels on the
  cut, frames clipped by the canvas, a feet line or a slip over its limit, grid wander under
  `keep`, key colour on the rim. The first pipeline had printed `bleed`, `content will be cropped`
  and a 22 px residual on that set and exited 0. `--no-gate` restores exit 0; `--report` can now
  fail. **`scripts/audit_frames.py`** re-reads the written PNGs (feet, slip, fringe, tint, cut;
  `--hold` classifies a one-pose loop `hold` / `BOIL`; `--onion` writes one onion skin per
  sequence), `audit_set.py --key-color` does the rim for static sets, and `frames_to_anim.py`
  gains `--onion` and `--bg`. **`scripts/sprite_ops.py`** holds the definitions all of them share,
  and is the first script here that the others import.
- **`unity-2d-sprites`** reads the new sidecar: the pivot is `pivot_norm` (the feet line, which is
  not the canvas floor once a foot margin sits under it), the canvas is whatever was fitted rather
  than 512, and a one-pose loop whose frames are different drawings (`iou_to_ref_min` 0.76–0.80
  against 0.96 for a true hold) plays ONE frame with engine motion instead of a clip.
  **`resources/Tests/SpriteFramesAudit.cs`** re-measures shipped frames in the Editor from their
  own bytes, because the slicer's verdict is the slicer's.
- **What this does not do.** It does not rescale a frame to fit: `--scale-search` exists, is off,
  and warns — on 21 sheets it gained at most 0.04 IoU and on a crouch-to-rise it shrank the
  character 4–8% with the head unchanged. It does not fix a boiling idle, only names it. It does
  not recover a jump's rise or a lunge's advance from a generated sheet (`free` holds the body
  still; travel goes on the transform) and warns when the offsets it removed did not follow the
  grid. `slice_grid.py` and `normalize_set.py` still end a resample in an alpha 1–3 ring of noise
  colour (6–9 px per 256 px icon) — `--defringe` clears it, the scripts do not yet. And
  `SpriteFramesAudit.cs` has run only in halves: its measuring kernel matched the Python gate on
  210 frames outside Unity, and its NUnit half compiles against 6000.3 and 6000.4 but has not been
  run in an Editor.

## 0.17.0

`comfyui-asset-generation` grows the MiniMax H3 path that transfers motion from a reference clip
onto a character, and hardens the two scripts around it.

- **`reference/h3-motion-transfer.md`** — one input owns identity and wardrobe, the other owns
  motion, cadence and framing, and the prompt says which is which. Why a 60 fps reference passed
  through unchanged softens the cadence, what to write instead of "fast" when timing matters, and
  a QA pass that compares motion phase at matching timestamps in a synchronized side-by-side
  rather than trusting a successful `/prompt`.
- **`scripts/prepare_h3_motion_reference.py`** — a motion reference normalized to 24 fps and an
  exact 17k+5 frame count, then read back with `ffprobe` and refused unless the frame count, rate
  and codecs are what was asked for. Audio is dropped by default; `--keep-audio` keeps it and
  verifies the track covers the whole timeline. A source too short to fill the requested frames is
  rejected before ffmpeg runs, naming the duration it would need.
- **`scripts/comfy_asset_client.py`** — `upload_image` is now `upload_asset`, because video and
  audio inputs go through the same endpoint and field name. The run reports `vram_after_unload`
  from `/system_stats`; a failure to read it no longer discards the outputs of a job that
  succeeded.

## 0.16.0

Thirty-six skills. Two new ones cover the part of the loop that happens **on a phone on your
desk** — the part an editor-side harness cannot reach.

- **`unity-device-testing`** — acceptance on a real Android or iOS device from a terminal. A probe
  scene that logs one tagged line per state change and one `k=v` line per second; an `adb` driver
  and a `devicectl` driver that assert on those lines with a timeout per step; system dialogs found
  by window focus and tapped by coordinates that respect rotation; physical steps (unplug, replug,
  background) detected **from the device** so a latency assertion starts at the real event; files
  pulled back from `persistentDataPath` on both platforms; and three exit codes — pass, a verdict
  about the app, a broken harness. Its pre-flight names the five things that look like bugs and are
  not: a dozing screen, a stale install, another app holding the hardware, an adb server restarted
  by a headless build, and a presence check that reads history instead of the present.
- **`unity-ios-build`** — from a Unity project to a process on an iPhone without opening Xcode:
  the headless build that produces an Xcode project and nothing else, an unsigned compile gate that
  needs no device, signing decided by the intersection of certificate, profile and device on this
  Mac (`doctor` prints it; the id in a certificate's name is a person, not a team), `devicectl`
  install, and `--console` as the only log channel. Native `.mm` plugins: the `.meta`, the
  `__Internal` import with stubs elsewhere, Objective-C exceptions being off, and iterating native
  code in 30 seconds by syncing into the generated project. App Store submission is out of scope.
- **Neighbours route to them.** `unity-android-release`, `unity-debug`, `unity-play-harness` and
  `unity-cli` each gained the row that hands you over.

## 0.15.0

Thirty-four load-by-situation skills, each teaching the same three things: what to check, the call
that checks it, and the script that does it for you.

- **`unity-urp-migration`** — a Built-in Render Pipeline project moved to URP in five gated phases,
  every gate read back from the **saved** project rather than from the converter log, plus the four
  traps that let a half-moved project report success: an assignment that sits in Graphics settings
  but not in the quality tiers, 3D materials claimed by the 2D shader provider, a Volume profile
  that reloads empty because its overrides were never added as sub-assets, and lighting that is
  still Built-in baked data.
- **`unity-search`** — a *find / where is / which prefabs use / what references X* question turned
  into one Unity Search query: asset type filters, folders, labels, `ref=` relationships and scene
  component queries, written out before it runs and opened in a live Editor when one is reachable.
  Read-only — it never selects, moves or edits a result.
- **`unity-cli` grows the two surfaces a repo hits first.** `reference/version-control.md` covers
  the verbs that know what a scene is — `vcs diff` and `blame` by object and field with their
  identity-confidence levels, `merge-setup` and its `--check` exit, `sync`/`switch` refusing while
  an Editor holds the project, `affected`/`summarize` and why their answer is a lower bound, and
  the three different meanings of `--since`. `reference/ci-preflight.md` covers `unity ci init`,
  the `doctor --ci` exit codes that say whether a retry is honest, and `cache key`.
- **The TMP Essentials import no longer hard-codes a package path.** `unity-localization` scans
  `Library/PackageCache` for the resource package instead, and names the menu item that returns
  `true` and then blocks a headless run on a modal dialog.
- **Smaller additions across the UI, 2D, runtime and backend skills** — USS patterns, sprite and
  atlas scripts, NavMesh areas and costs, a URP pre-flight snippet, package selection, and the
  documentation maps the services SDKs publish.
- **One layout for every skill.** `SKILL.md` is a router with a symptom table; `reference/` holds
  the depth it names; `resources/`, `scripts/` and `templates/` hold what you run or copy. No skill
  keeps content at its own root.
- **Every section is a method section** — what to check and how to check it, in present tense,
  never a record of how this repo checked it. A doubt that should change what you do is written as
  a step you run, not as a hedge.
- **Package tables** keep ids and API floors, and point at `Packages/packages-lock.json` for what
  actually resolved.
- **Skills route to each other, never out of the repo.** Each one's `Scope — what this skill does
  NOT do` section hands you to the right neighbour, so you land in the right skill from any
  direction.
- **Gates, run by CI on every push and pull request:** `tools/lint-skills.py` (frontmatter, name
  matches directory, shipped executables parse), `tools/check-consistency.py` (the two manifests
  agree, every route out of this repo is declared) and `tools/sync-codex-manifests.py` (the Codex
  manifests are generated — never hand-edit them).
