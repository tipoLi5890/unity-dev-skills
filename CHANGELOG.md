# Changelog

Versions are the plugin's, in `.claude-plugin/plugin.json`.

## 0.32.0

Sixty skills. Methods ported from sprite-gen under the Apache License 2.0, credited file by file in
`THIRD_PARTY_NOTICES.md` and in each ported file's header: keying against the colour a model
actually painted rather than the one it was asked for, a key colour chosen before generating, a
breathing idle made from one still, and two new frame gates. A new skill, `sprite-from-video`,
turns one character still into transparent loops and one-shots through an image-to-video model on
a self-hosted ComfyUI. Every new script depends only on Python 3, numpy and Pillow (the video
scripts also on ffmpeg/ffprobe 5.1 or later), has a `--selftest` that builds its inputs in a
temporary directory, and documents its exit codes; except for `audit_frames.py` (below), options that already existed
keep their defaults and their output byte for byte.

**Behaviour change:** `codex-visual/scripts/audit_frames.py` gains two gates that are on by
default. A sequence fails when any frame has more than 120 pixels at alpha above 16 within RGB
distance 150 of the key (the key is `--key-color`, else the sidecar's `set_metrics.key_color`; with
neither, the column reads n/a and does not gate), or when any frame has fewer pixels at alpha above
0 than ceil(sqrt(W×H)) of its canvas, half that for a centroid (effect) sequence. A bare PNG
directory now includes its empty frames, which then fail the sparse gate; a run driven by
`frames.json` still skips frames marked empty. `--residual-max -1 --sparse-min 0` restores the
earlier verdicts.

**Keying: the key the model painted**

- **`codex-visual` → `scripts/key_unmix.py --edge tint`, `reference/codex-runtime.md` §5.** An
  image or video model paints its "pure" key a little off: a green asked for as `#00FF00` comes
  back near (0..4, 235..243, 1..4), 12 to 22 away. Tint mode reads the painted key from the
  border (corner patches and the 1 px ring, 8-wide bins, a 12% bar) and erases two balls of radius
  96, one around the declared key and one around the painted one, the second grown 8-connected
  from key-signature pixels. A pixel whose key tint is under 18 is the subject and is never
  touched; within 4 rings of the keyed region the rest is un-mixed along the key, blends within
  180 of the key only in rings 1–2; small trapped spill (at most max(32 px, 0.5% of the subject),
  one pixel past tint 40) is recoloured with its alpha kept, or left under `--no-despill`. A rim
  whose material is itself key-tinted (a teal jacket on green) is un-mixed against that
  material's tint rather than against zero, so it keeps its hue instead of turning blue; the run
  reports those pixels as `baseline_px`. `--lo`
  and `--band` default to 96 and 4 here and stay 60 and 2 for outline and fill. Name the key hex
  in tint mode. The keyer is one shared block, `tools/shared-blocks/chroma_unmix.py`, carried by
  `key_unmix.py` and `sprite-from-video/scripts/video_frames.py`.
- **`codex-visual` → `scripts/pick_key.py`, `reference/codex-runtime.md` §5.** Which key to
  generate on, decided against the base image before generating: magenta, green, cyan or blue
  (`#004DFF`), each scored by the 1st-percentile and minimum distance to the subject's pixels and
  eligible only when its nearest subject pixel is farther than 96, the tint erase radius; ties go
  to magenta. The background is read from the border ring (75% within 48), enclosed flat regions
  are told from material, specks dropped. One JSON object per run; exit 1 names the subject pixel
  and the box that every key would erase.

**Frames: fit, anchor, resample, gate**

- **`codex-visual` → `scripts/sheet_to_frames.py`, `scripts/sprite_ops.py`,
  `reference/animation-scripts.md`.** Three opt-in options. `--scale reach` shrinks the whole set
  by one factor (at most 1) so every frame reaches no closer than 4 px to the canvas edge about the
  anchor it is already placed on; when content under the feet line would limit it, the foot
  margin grows to hold that content instead (a NOTE names it), and an explicit `--foot-margin` too
  small for it draws a WARN naming the one that keeps full size. `--align foot` moves each frame's foot centroid
  (alpha-weighted over the bottom 20% of its content rows) onto the set's median, in the keep
  family. `--resample split` scales a registered frame without inventing colours: opaque pixels
  stay inside the source's per-channel range, which LANCZOS does not promise. New `frames.json`
  `register` keys appear only when an option is used.
- **`codex-visual` → `scripts/audit_frames.py`, `reference/animation-faults.md`.** The residual
  and sparse gates above, with `resid` and `opaque/floor` columns, `residual_px` and `opaque_px` in
  the CSV, owner rows with the fix order (re-key with `--edge tint`, re-generate on a `pick_key`
  colour, then re-slice), and a `--selftest`.

**An idle from one still**

- **`codex-visual` → `scripts/breathe.py`, `reference/animation-scripts.md`,
  `reference/animation-sheets.md` §5.** A breathing loop made from one still pose on the same
  canvas, in which every output pixel is a copy of an input pixel: whole rows duplicated or deleted
  under a tapered envelope, a monotone column map about a fixed axis column, the feet pinned on the
  content's bottom line, the head bit-identical in every frame above the band that deforms (the neck found as
  the narrowest width minimum in the top 5–60% of the figure, else a height fraction), and phases
  folded on integers so the loop closes exactly. A row strained past 0.25 or an opaque pixel pushed
  off the canvas is refused (exit 2) with nothing written. `--depth` defaults to `auto`: the
  head lift is aimed at max(3 px, 1.5% of the height) with depth at most 0.06, so a 64 px sprite
  breathes at 0.06 and a 280 px figure at about 0.017 (±4 px, not the ±13 px a fixed 0.06 gives). It also repairs an idle that boils.

**A still into a loop: `sprite-from-video`**

- **`sprite-from-video` → `SKILL.md`, `reference/pipeline.md`.** One approved still, one clip, one
  cut: a canvas, a generated clip, keyed frames, a loop or a one-shot, a handoff to Unity and the
  registry, and a re-roll budget, each stage with its gate. Plain image-to-video plus period
  detection makes a loop; a first-and-last-frame clip on one still comes back almost frozen and is
  not used for loops; a breathing idle is `codex-visual`'s `breathe.py` first and an image-to-video
  idle second; a jump, a launch or an attack is a one-shot.
- **`sprite-from-video` → `scripts/video_canvas.py`.** The still padded onto an exact-key canvas
  shaped for the motion (square for a gait, 3:4 tall with 0.34 headroom for a jump, 16:9 wide with
  lead and trail for an attack), feet on the floor, long side 768 and the other a multiple of 16,
  every pixel the keyer would erase repainted to the exact key. It prints the `--set` arguments
  for the ComfyUI graph; a white or uneven base is refused.
- **`sprite-from-video` → `scripts/video_frames.py`.** Every frame extracted with its timing
  intact, keyed with the shared block against the key painted on frame 0, specks dropped, and a
  flatness report (painted key off by, border spread, drift). A frame touching the top or a side
  is refused with a fix that depends on what touches: leftover key (normalise the still and
  regenerate) or the subject (a taller or wider canvas).
- **`sprite-from-video` → `scripts/video_loop.py`, `reference/loop-detection.md`.** The period
  from a lag profile over a 96 px frame-distance matrix, within per-state windows (a walk 0.5–1.6
  s); the smallest minimum within 15% of the deepest; a half-stride guard that doubles the period
  or refuses; periodicity at least 0.15; the start picked by a seam score, gated at 2.0 on the shipped frames and at the source rate; drift
  spread as a whole-pixel ramp. A walk at 24 fps whose two steps take 22 frames comes out as one
  cycle subsampled to about 12 fps, with `fps_hint` the output frames over the cycle's seconds.
  A one-shot is cut between matching rest poses, and `--mode once` keeps a jump from its crouch to
  standing still with `hold_last`. Equal-canvas frames, a GIF preview and a `frames.json` with
  `register` (`ground` with every frame seated on one feet line when it spreads by at most max(3 px,
  2 % of the body), `keep` for vertical travel), `pivot_norm`, `loop`, a
  `verdict` and a `producer`. Exit 2 refuses with nothing handed over; exit 3 writes the frames
  with `verdict.ok` false for a suspected multi-cycle or harmonic.
- **`sprite-from-video` → `reference/video-prompts.md`.** What the prompt must say (preserve the
  first frame, in place, fixed camera, one flat key for the whole clip, no floor or shadow,
  real-time pace, silent), the wording that fixes each failure, and worked prompts for the
  runner's walk, run and launch and the sentry's swipe and idle.

**Routing and records**

- **`art-asset-registry` → `scripts/registry_ingest.py`, `reference/ingest.md`.** A `frames.json`
  that names its `producer` (`{skill, script}`) is read as frames and recorded under that
  producer, so `breathe.py` and `video_loop.py` output ingests like `sheet_to_frames.py`'s; the
  still or the clip it names as `source` becomes the record's input.
- **`comfyui-asset-generation`, `game-character-pipeline`, `codex-visual`.** Their Scope sections
  route a clip turned into a sprite loop, and a 2D character's frames from a video, to
  `sprite-from-video`.

## 0.31.0

Fifty-nine skills. Everything in this release comes from building one 3D game, a tennis game,
end to end in a day: a deterministic simulation on its own thread, a headless character pipeline,
animation driven by the simulation and corrected with IK, a polish pass, and several agents
sharing one machine. Each page keeps the numbers that decided it, including the lesson that came
last and belongs first: measure what the clip library can do before setting a single simulation
number. New scripts depend only on the Python standard library and numpy and have a `selftest`;
the pure C# resources (`SimHost`, `SimClock`, `BallFlight`) were compiled and run outside Unity.

**Behaviour change:** `unity-debug/scripts/lanes.sh` now caps Editors per machine. `MAX_UNITY`
defaults to 2, so `run` queues (or, with `--no-wait`, exits 6) while two Editors are running
anywhere on the machine, whatever project they belong to, and `status` prints the count. Set
`MAX_UNITY=0` to restore the old unlimited behaviour.

**Simulation and timing**

- **`unity-gameplay` → `reference/genre-timing-sports.md`.** A recipe for racket and bat games
  that opens with the clip library. A tennis simulation ran at 7 m/s against a 2.7 m/s run loop
  and put contact points 25 to 65 cm from where the clips put the racket; the gap became 1.8×
  playback, 1.5× stride warping, a serve root correction pinned at its cap, and about 40% of the
  remaining pops. The method: sample loop speeds and racket-bed centres at the contact frame on
  the reference body, three height classes interpolated and clamped, scaled per body, hashed into
  the replay header; then the simulation's numbers (top speed lowered to 6.0 m/s). Then contact
  decided by the simulation (a prototype that judged hits from the animated racket gave PERFECT
  presses that missed and replays that diverged), reaction floors of 1.5 / 1.0 / 0.75 s as a
  property test, no time-scale change during a rally, and a bot-vs-bot balance grid with a
  counter matrix and two gates written before tuning (each counter wins by at least 10 points; no
  shot kind above 40% usage).
- **`unity-gameplay` → `reference/sim-host-and-clock.md`, `resources/SimHost.cs`,
  `resources/SimClock.cs`.** The layer after the simulation/presentation split, for a simulation
  that is heavy on some ticks and graded against a real clock: 120 Hz on its own thread, the
  target tick from absolute `Stopwatch` time, a triple-buffered snapshot swapped once per frame,
  commands drained before each step, a 16-tick catch-up cap, events that carry their own tick and
  position, and a render tick one behind the clock that is never clamped to the snapshot
  (clamping slowed the cue ring and biased every press late). A Mono JIT stall held the ball on
  the racket for 25 to 50 ms on the first strikes; a throwaway warmup match of about 40 ms fixed
  it (worst lag 1 tick over 22 s), in the order warmup, then restart the clock, then construct
  the host. The first attempt warmed up after the host existed and raced its thread. Also a
  sim-lag smoke gate. `unity-game-brief` → `reference/sim-presentation-split.md` ("Picking the
  tick") now points here for a heavy or timing-graded simulation.
- **`unity-input` → `reference/timing-press.md`.** Grading a press on a device with about 90 ms of
  latency and timestamps quantised to about 43 ms: each press carries its device timestamp and
  the tick it arrived; a timestamp subtracts only the pauses that ended before it (subtracting
  the total made a pre-pause press read early by the whole pause); PERFECT is never narrower than
  one quantum, asserted per difficulty; the ideal press sits at contact − (capture + late window
  + 1 tick), about 0.29 s, so a late press still connects. Both cue schemes were built and
  played: press-then-swing landed 60% against 13% for a dwell scheme at a typical 90 ms timing
  spread, because dwell truncates the late window. Plus one press per player rather than per
  sensor, and a development keyboard that drives the real signal path.
- **`unity-physics-3d` → `reference/own-ball-physics.md` and `resources/BallFlight.cs`.** When a
  ball should not be a `Rigidbody`: drag (k ≈ 0.0206 /m), Magnus lift with
  C_L = 1 / (2 + |v|/(r|ω|)), spin decay, 8 substeps per 120 Hz tick so a substep stays shorter
  than a diameter (6.25 cm at the 60 m/s clamp), earliest contact by bisection, an impulse bounce
  whose tangential impulse is the lesser of pure rolling and μ·J_n (topspin kicks, backspin
  checks, energy never grows over 10 000 random contacts), a net with a height curve, an
  absorbing body and a cord, and a shooting-method solver gated at ≥ 99.5% convergence over
  10 000 random launches with landings within 2 cm. Faults come from scattering the target and
  flying a real shot. The resource is pure C#, double precision, and bit-identical on rerun.
  `unity-combat` → `reference/projectiles.md` points here for a projectile your own code
  integrates.

**Characters: fit the mesh to the clip pack**

- **Fit, as a first-class route.** When one purchased pack supplies the motion, each character's
  mesh is fitted once to the pack's skeleton (names, parents and rest rotations kept, gated
  < 0.5°) and every clip plays as bought, Generic. `game-character-pipeline` gains the route in
  G0, its stage mapping and an S7 gate that measures loop speeds and contact points before
  gameplay numbers freeze; the method is `blender-character-rig` →
  `reference/fit-to-clip-skeleton.md`. Retargeting stays for custom bodies and clips from many
  skeletons.
- **`blender-character-rig` runs headless.** Every module runs unchanged under
  `blender -b --factory-startup`. `reference/headless-pipeline.md`: the stages prep → fit → skin
  → proof → lod → export → unity-gate, one gates JSON per stage with exit 0/1/2, two runs giving
  the same mesh hashes and a byte-identical FBX (the exporter's per-process UUID salt and header
  time pinned), and a Unity lab project outside the repo that waits while two Editors are open.
- **`blender-retarget` → `reference/route-bakeoff.md`: the measured choice.** Fit + Generic
  played within 0.0002° of the clip on the pack's own body; Humanoid on the same skeleton was off
  by 1.5 to 4.4° and failed the slide gate; per-clip baking was 6.7× larger and carried Blender's
  reading of late-starting curves. 75 clips took 4.2 MB, against about 9 MB, about 28 MB, and
  387 MB for the old interactive workflow. A naive per-clip retarget starts 55 to 72° off.
- **Gate the added foot slide, not the absolute.** The pack's own mocap read 1.8 / 3.3 / 4.4 cm
  against an absolute p95 gate of 1.5 cm. `blender-retarget/scripts/clip_metrics.py` measures
  plants on the reference body and the slide a route adds on top; `scripts/bakeoff_report.py`
  joins per-route reports into one table with the misses in bold. Exit 0/1/2.
- **`unity-rigged-character` → `reference/shared-skeleton-generic.md` and
  `resources/Editor/SharedSkeletonClipImporter.cs`.** The import fixes a pack needs: RemapRoot
  (root names varied 63/7/8), StripNonRootPositions, BakeNodeDefaults (curveless bones otherwise
  hold another model's defaults), `display_scale` on the prefab root, and what the runtime will
  ask of the library (plant windows, tool-point paths, peak angular speeds). In batchmode,
  `AnimationMode.SamplePlayableGraph` poses the Animator where `PlayableGraph.Evaluate` does not,
  and `BakeMesh` returns the bind pose, so compute skinning yourself; the same trap is now
  `unity-debug` → `reference/unity-gotchas.md` §24.
- **Skinned LODs built by a stage, named so Unity leaves them alone.**
  `blender-character-rig` → `reference/skinned-lod.md` drops hidden inner shells (32% of one
  body), voxel-remeshes a prop that came out as 333 shards, uses geometric normals, and weights
  the boundary 0.5 rather than 0 (0 grew an 88 cm spike). `unity-3d-models`: `_LOD<n>` names make
  the FBX importer build a `LODGroup`, which hid a tier-selected LOD1. Skin method and bone count
  by measurement: positional 6.3% against heat 13.2% new self-intersection on a double shell, and
  2 bones per vertex added 0.6 to 0.9 percentage points, so every quality tier uses 4
  (`unity-android-release` → `reference/player-settings-android.md` carries the tier table).

**Animation that follows the simulation**

- **`unity-animation` → `reference/sim-driven-animation.md`.** One hand-built `PlayableGraph` per
  character, `DirectorUpdateMode.Manual`, clip time computed from the simulation tick every frame
  (never `+= dt`), so the contact frame lands on the contact tick by construction (0.00 ms on
  every hit). The swing schedule (rate 0.8–1.25, start trimmed when clamped, two height variants
  on one tick, late input at up to 1.6×, start from the predicted stop), root-correction caps by
  stroke (0.15 / 0.25 / 0.35 m) and the locomotion stack for a mover far faster than its clips,
  linked back to the design-time method in `unity-gameplay`.
- **`reference/foot-lock-and-prop-ik.md` with `resources/FootLockJob.cs`,
  `resources/TwoBoneIKJob.cs` and `resources/AnimJobMath.cs`.** IK as Animation Jobs after the
  mixer, for Generic rigs. The rule the pops taught: every target and weight continuous in
  velocity, not only position. A foot lock released by a critically damped spring starting at
  minus the foot's velocity (a 0.15 s smoothstep popped the knee), landing anticipation 0.08 s
  ahead, a hinge-axis two-bone solver that cannot flip, plant windows annotated at 0.5 m/s, and
  prop IK with the wrist solved last. Foot slide p95 per plant 109–225 cm → 0.12–0.27 cm;
  racket-to-ball p50 18.5 cm → 3.4–4.1 cm.
- **`reference/motion-metrics.md` and `resources/MotionMetricsSampler.cs`.** A read-only motion
  gate for PlayMode tests: slide and speed per plant, root against the simulation, root velocity
  jumps, pops and contact timing. Pops are spikes in the final pose the clip does not have,
  attributed per layer: 0–2 of 31–63 per match came from clips or blends, so inertialization
  would not have helped. Pitfalls with numbers: an Editor hitch across a contact, PNG capture
  blocking about 100 ms, a 2.7-against-3.0 gate that was a flake waiting to happen.
- **`unity-3d-controller` → `reference/animator-bridge.md`.** A mover faster than every clip:
  lower its speed first, expose acceleration and a predicted stop so gait and standing actions
  anticipate, and leave the rest to stride warping and a foot lock.

**Venue, look and feel**

- **`unity-3d-level` → `reference/venue-from-scripts.md`.** A rules-fixed venue built by a Blender
  script in game coordinates (an asymmetric axis-marker test proves the FBX equals game space),
  collision exported from a `COLLISION` collection as JSON rounded to 0.1 mm and checked against
  proxies, rule lines drawn from the rule constants (a prior model's were 2.75 cm off), merged by
  material and zone, one command per step.
- **`unity-render-urp` → `reference/material-validation.md` and
  `resources/Editor/UrpMaterialValidation.cs`.** URP 17.3's validation removes `_EMISSION` unless
  the GI flags include AnyEmissive and rewrites a hand-made alpha blend to shader-side
  premultiply; a builder that runs `BaseShaderGUI.SetMaterialKeywords` itself leaves no diff on
  rebuild, and the audit lists what would drift. Also a see-through fence that does not shimmer,
  and a grade per venue with effects per tier in `reference/volume-templates.md`.
- **`unity-scene-optimisation` → `reference/lod.md`, `reference/culling-distances.md`.** A fixed
  camera picks LOD by quality tier, and the importer's own `LODGroup` has to go: on merged venue
  meshes it chose LOD0 and culled the LOD1 trees on medium and low. Strip it at prefab build,
  assert zero in a test, count each tier's triangles from the one camera (worked case 103 020
  high, 39 516 medium and low), and reopen the zone behind a fixed camera when a shot needs it.
- **`unity-lighting` → `reference/shadows.md`, `reference/environment.md`.** Per-tier shadow
  distance and cascades for a long fixed view (52 m, 2 cascades at 0.36 on high; 2048 at 50 m on
  medium; blob only on low), one shadow map per split-screen camera; fog kept off the play area,
  and mist placed from known limits.
- **`unity-camera` → `reference/broadcast-sports.md`.** Broadcast framing for a court sport set
  by projecting the court against the HUD: 31° solo, 36° per split half; a critically damped
  follow of your own player with 30% of the ball; a 1.2 m push between points, a winner close-up
  that reopens the culled back layer, a 4 cm smash dip, and no hit stop during play.
- **`unity-game-feel` → `reference/sports-readability.md`, `resources/MinScreenSize.cs`,
  `scripts/screen_smoothness.py`.** A fast ball at least 11 px on a 1080-line reference, outlined
  and trailed by speed; extrapolated up to 1.5 ticks when the snapshot is late so it never parks
  for a frame; a screen-speed wobble metric (p95 13.2% to about 5%); grade-coloured hit rings
  with the opponent's fainter (a white disc read as a second ball).
- **`unity-audio` → `reference/synth-and-band-limits.md` and `scripts/spectrum_check.py`.**
  Effects synthesised in C# under a hard 16 kHz ceiling (raised-cosine attacks, Hann fades, noise
  filtered first, final 7 kHz stages, loops cross-faded after filtering), gated at −60 dB above
  the cutoff after a 17 kHz calibration tone proves the FFT can see a failure; measured about
  −120 dB. One-shots are measured without a window and must end at zero.
- **`unity-profiling` → `reference/gc-per-phase.md`, `reference/frame-hygiene.md`,
  `reference/runtime-asset-leaks.md`, `resources/GcAllocProbe.cs`, `resources/OwnedAssets.cs`,
  `templates/AssetLeakSoakTest.cs`.** `GC.GetAllocatedBytesForCurrentThread` returns 0 under
  Unity's Mono; a `GC.Alloc` recorder gated per phase, with self-calibration, took a presentation
  layer from 419/419 allocating frames to 3–4 of about 420. A busy machine read 4–10 ms where a
  quiet one read 1.6–2.4 ms. Runtime materials and meshes get an owner, and a nine-match soak
  keeps their counts flat.
- **`unity-ui-ugui` → `reference/text-and-image-traps.md` §6.** TMP outline setters copy the font
  material per label (sixteen per match); one cached shared material replaces them.

**Process: tests, machines and several agents**

- **`unity-new-project` → `scripts/pure_tests.py` and `reference/pure-test-lane.md`.** A
  project's engine-free tests run without an Editor, with the .NET runtime, Roslyn compiler and
  NUnit the Editor already ships: each `noEngineReferences` asmdef compiled under its own name (so
  `InternalsVisibleTo` behaves as in the Editor), test files that touch the engine excluded with
  their reason, NUnit's own runner expanding `[TestCase]`, and a suite error or zero tests counted
  as a failure. Exit 0, 2 or 3; `selftest --e2e <project>` compiles and runs a synthetic suite.
  `unity-debug` → `reference/cli-harness.md` and `unity-cli` → `reference/editor-binary.md` point
  to it.
- **`unity-new-project` → `reference/version-control-setup.md` §5–§7.** An LFS ledger against the
  plan's quota with real per-import costs, decimation before commit, pushes from a shared working
  tree (`git log origin/main..HEAD` first; a push publishes every ancestor), pre-commit hooks that
  check the index rather than the working tree, and purchased material kept private with its
  licence as an open question.
- **`unity-debug` → shared machines.** `reference/parallel-runs.md` measures what other work does
  to a run (frame times 2 to 5 times high, a smoke lag assertion red 5 > 3 under load and green
  alone, a pure-C# "under 3 ms" assertion reading 6.6 to 9.8 ms), caps Editors per machine
  rather than per project (three on 16 GB timed out a watchdog), and adds a throwaway lab
  project outside the repo for pipeline work. `scripts/lanes.sh` gains `MAX_UNITY` (the
  behaviour change above).
- **`unity-debug` → captures that tell the truth.** A fixed Game-view resolution through
  `PlayModeWindow` and a wait on `ShaderUtil.anythingCompiling`, installed as hooks from an Editor
  assembly; every reported image is opened; a PNG capture stalls the frame about 100 ms, so
  events are timed by interpolating across the straddling frames; motion is recorded with
  `AsyncGPUReadback`, resampled by game time to 60 fps. `reference/unity-gotchas.md` gains §22
  (first-Play cyan placeholders), §23 (the Mono JIT first-use stall on a worker-thread
  simulation, told the same way as in `unity-gameplay`) and §24 (batchmode sampling reads the
  bind pose).
- **`unity-play-harness` → shot lists and the autoplayer.** One parameterised `Shots` test over
  every situation id, prefs made read-only during situations, the same ids in a built player; an
  autoplayer that presses through the real input funnel with seeded timing noise (σ 40 ms); and
  the smoke run's assertions, including a sim-lag counter and that the autoplayer's own seat hit
  the ball.
- **`unity-game-brief` → `reference/running-the-build.md`, `templates/AGENT_BRIEF.md`,
  `templates/DECISION_LOG.md`.** When to rebuild a prototype rather than port it, milestones with
  ★ gates only the person closes, feel questions settled by building both behind a runtime
  switch, a three-bucket decision log (locked, small and reported, open with a default),
  doc/code reconciliation after each milestone, and an ownership block for every agent's brief,
  with the multi-agent failures behind each line (a push that published other agents' commits,
  a hook that blocked on another agent's uncommitted work).
- **`unity-android-release` → `reference/player-settings-android.md`.** A 3D game's baseline:
  IL2CPP/ARM64, `minSdk` as the person's market decision, `targetSdk` set explicitly rather than
  `Auto`, Vulkan then GLES3, three quality tiers, and 4 skin weights on every tier.

## 0.30.0

Fifty-nine skills. A game can now be seen before its first gameplay script, and every picture
and clip on the way is made from a JSON spec that can be run again, so a changed rule is a
re-run, not a redraw. `unity-game-brief` sets the order (flow diagram, key art, screen mockups at
the target resolution, layout and keyframes, a timed simulated-gameplay preview, then the greybox
playable) and ships the compositor and the reel; `codex-visual` groups the pictures into themed
overview sheets; `comfyui-asset-generation` draws the keyframes' layout maps and gates their
camera. Every script depends only on the Python standard library, Pillow, numpy and
ffmpeg/ffprobe, has a `selftest`, and skills exchange only JSON on disk.

- **`unity-game-brief` → `reference/preview-before-code.md` and a "Preview before code" section
  in SKILL.md.** What to make, in order, each only after the one before it is agreed, what each
  answers and what a person says yes to. A polished image is not proof of gameplay: a preview
  shows intent and timing, and its timings are constants written down, the same numbers the brief
  and the invariants use. A timeline keyed by hand is a drawing, and nothing can be checked
  against it. `templates/GAME_BRIEF.md` gains a row for the previews and the constants they were
  made from.
- **`scripts/preview_compose.py TIMELINE.json --out preview.mp4 [--sfx-dir DIR] [--guides]`** —
  a timed preview from layered sprites. The timeline lists `assets` (a path, anchor `c` or `bc`,
  scale, cells in a horizontal strip), layers with keys (`t`, `x`, `y`, `scale`, `alpha`, `rot`,
  `frame`) eased `linear`, `in_out`, `out` or `step`, timed text with an optional `color` kept
  inside the title-safe inset, and events (`t`, `sfx`, `vol`). Frame i is drawn at i / fps,
  composited in `z` order and piped raw to ffmpeg (libx264 -crf 18, yuv420p, faststart). Next to
  the video: `<stem>.events.json` (every event with its frame number, and one sha256 over all raw
  frames, so two runs can be compared) and `<stem>.contact.png` (eight frames with their times).
  With `--sfx-dir` each event's sound is placed with `adelay`, mixed with `amix` (normalize=0)
  over a silent track of the exact length and normalised in two passes to −16 LUFS integrated,
  −1.5 dBTP, falling back to a fixed gain and a limiter when linear gain has no room. An event
  with no sound file is still logged and listed under `sfx_missing`. On-screen text uses Pillow's
  built-in face, so it draws Latin letters, digits and ASCII punctuation only. Exit 0 written,
  2 an invalid timeline, 3 an unreadable input or an ffmpeg failure.
- **`scripts/preview_reel.py REEL.json --out reel.mp4`** — previews joined into one reel: an
  opening title card, a card before each segment with a `title` or `sub`, every clip scaled and
  padded to one size and fps, one music bed looped to the length and faded over the last second,
  and each clip's logged events placed again from `sfx_dir` at the clip's start in the reel (or,
  without it, each clip's own audio). The mix is normalised to −16 LUFS as in the compositor.
  Cards take a `font`; without one they draw Latin letters, digits and ASCII punctuation only.
  `<stem>.timeline.json` lists every card, clip and event in reel time, `sfx_missing`, and the
  integrated loudness read back with ebur128.
- **`scripts/examples/courier_run_preview.py --out DIR`** — the worked case, written from its
  rules. The Runner runs three lanes past pickups and a patrolling sentry toward two gates that
  open on a fixed rhythm. Lane width, run speed, the lane plan, pickup spacing, the gate period
  and open window and the sentry's sweep sit in one constants block, and every position, switch
  and sound follows from it. It draws its own placeholder sprites and tones, writes
  `timeline.json`, runs `preview_compose.py` as a subprocess, and emits a `pickup` event for each
  pickup in the Runner's lane and a `gate_pass` or `gate_hit` when it reaches a gate, with an
  on-screen label for each gate outcome ("gate open: through", "gate closed: hit"). Its selftest
  checks the frame count against fps × duration, the encoded duration within one frame, one event
  per rule trigger against a count worked by hand, and the same events and frame hashes on two
  runs.
- **`codex-visual` → `scripts/overview_sheet.py SPEC.json --out DIR [--cell 480]` and
  `reference/overview-sheets.md`.** A project's scattered pictures on a few themed pages, one
  question per sheet (style and brand, flow screens in player order, modes, game screens at the
  target aspect). Each sheet is `DIR/<name>.png`: a title band, then per cell the caption and,
  under it in grey, the source path as the spec wrote it. Sources are only read, never moved;
  an absolute path is refused. A path that is not a file becomes a red "missing" cell and one
  Pillow cannot open a red "unreadable" cell, and either exits 2 with the rest of the page drawn.
  `DIR/overview.json` records each sheet's `png_sha256` and, for every present item, its
  `sha256` and size; the same spec over the same files gives the same bytes. Non-Latin captions
  take a `font` shipped with the project. An overview page is ungated, so a decision that rests
  on numbers still goes through `contact_sheet.py --require`; `reference/review-sheets.md` says
  which is which.
- **`contact_sheet.py`** — the grid is one function both composers use, with any number of
  caption lines per cell, and a write that fails part way puts back the sheets an earlier run
  left under the same names and removes this run's files. Its CLI and exit codes are unchanged.
- **`comfyui-asset-generation` → `scripts/layout_map.py SCENE.json --out DIR [--check-paths]
  [--margin 0]`.** Each keyframe's arrangement drawn by program from ground coordinates in
  metres through one fixed camera (vertical fov, eye height, pitch, target): flat colours, boxes,
  discs and standing figures far to near, a mark on top and a wedge on the ground for facing, no
  text. A box's width runs along its facing and its depth across it. `DIR/layouts.json` holds the
  resolved camera, the horizon row and each placed object's pixel box, centre and depth.
  `--check-paths` moves every object in a straight line between consecutive frames and reports
  each pair whose swept footprints touch, with `clearance_m` (negative is the overlap depth);
  objects moving together by the same displacement are one group, and pairs where neither moves
  are skipped. Exit 0 no crossings, 2 crossings found, 3 an invalid scene or an unwritable
  folder (every frame is drawn before the first file is written).
- **`scripts/camera_gate.py --ref K1.png CAND.png [--column 0.1] [--tol 6] [--size WxH]
  [--dist 40] [--run 3]`** — rejects a keyframe whose camera moved. It walks down a 3-pixel
  strip at one column, takes the median colour of the top 5% of rows, and reads the horizon as
  the first row that stays more than `--dist` from it for `--run` rows. Pass when the sizes match
  and the rows differ by at most `--tol`. One JSON line whose `which` (`ref`, `cand`, `both`,
  `args`) tells a bad roll from a bad setup; exit 0 pass, 2 fail, 3 no horizon or an unreadable
  image, 64 a usage error.
- **`reference/h3-keyframe-segments.md`** — keyframes chained from the first on one camera, with
  the loop written out: generate, gate, move a `cand` reject and its verdict to `rejected/`, retry
  up to N, and stop on a crash or a bad reference instead of rolling again. Layout maps come from
  `layout_map.py` with the horizon kept in frame (pitch under fov / 2), and crossing moves are
  re-ordered until `--check-paths` exits 0. Its thresholds are starting points to retune per
  resolution. SKILL.md gains one routing row for maps, crossings and the gate.
- **`art-asset-registry` → `reference/ledger-schema.md`** gains the link words `flow-node`
  (`flow:<node>`, for a mockup or a screen) and `beat` (`beat:<id>`, for a keyframe or a preview
  clip). A flow node may carry `planned`, `mocked` or `approved` in the flow document, and nothing
  validates it. `registry_ledger.py check --strict` accepts both words without a vocabulary
  warning.
- **`game-character-pipeline`** — the preview track ends in a timed gameplay preview and reel:
  `unity-game-brief` → `reference/preview-before-code.md`. `unity-game-brief` loads for "preview it
  before code".

## 0.29.0

Fifty-nine skills. A rigged character made from an image now has one stage order, from the
quality target to an approved import, and every artefact on the way has a ledger record. The two
new skills are `game-character-pipeline`, which holds the order and the gates and routes each
stage to the skill that does it, and `art-asset-registry`, the ledger. In `unity-3d-models` a
3D budget is a person's pick between real versions of one asset, never a fixed cap.
`unity-rigged-character` becomes the Unity side of a rigged character, whichever route made the
FBX. The generation skills gain four-view removal, a graph diff and one review-sheet composer.

- **`game-character-pipeline` — the order, the gates, the artefacts; no scripts.** G0 is decided
  once per character, by a person, before the first image. First the quality target. Then the
  route: body proportions × rigging tool × clip source (Auto-Rig Pro for a standard body, the
  positional rig of `blender-character-rig` for a custom one, Mixamo as an option). Then the
  track:
  - **Preview**: rig the dense mesh as it is, for a prototype only.
  - **Ship**: budget → game mesh → rig once.

  Stages S0–S13 run from the budget to the ledger. Each row gives the stage's owner, what it
  enters with, the exit gate and what it leaves on disk, and where the gate needs a person.
  Clips are all retargeted in Blender, and Unity never retargets across skeletons. Every
  decimation, retopology and rebake of a mesh that will be skinned happens before the rig. A
  table names the stage to go back to after each upstream change, and the courier run walks the
  Runner with its Mallet down the ship track. The Scope tables and Related lines of the skills it
  routes to point back to it, as do `unity-gameplay`, `unity-game-brief` (`visual-direction.md`,
  `GAME_BRIEF.md`) and `unity-profiling`.
- **`art-asset-registry` — one append-only ledger per project, `ArtDirection/assets.jsonl`,
  schema 1.**
  - **What a record holds:** an id made once from a path, a `rev`, `kind`, `status`, and
    `files[]` with sha256 and bytes. Every `.blend` version is hashed: a working file is
    `role: source, mutable: true`, and the Blender file an asset came out of is in `file`.
    Lineage is `parent`, `inputs` and `links: [{rel, to, rev?}]` (rels `made-under`,
    `made-by`, `evidence`, `explained-by`, `depends-on`; `to` is a ledger id or `ns:key` such as
    `art:direction` or `job:<id>`). It also holds the producer's `tool` and `params` (a prompt's
    file and hash, never its text; a `server_label`, never a URL), gates, a verdict, `source`
    and `license`.
  - **Vocabularies:** `kind` is an open slug with a documented vocabulary (`check --strict`
    warns on other words). The statuses are `candidate`, `approved`, `rejected`, `superseded`,
    `unused` and `diagnostic`. A diagnostic run is kept and never approved.
  - **Ids and versions:** ids are NFC Unicode in any script, so `ArtDirection/角色/跑者.png`
    keeps its own id; a name with no letter or digit falls back to `<folder>/<sha8>`. The current
    version is the latest approved revision. `history` marks it and the previous good one, and
    gives `current_version: null` after a rejected, superseded or unused last record.
  - **`scripts/registry.py`:** `init`, `record`, `check [--strict]`,
    `stale [--art-version N] [--at NS:KEY=N]`, `status ID STATE`, `history`, `mv`, `render`,
    `adopt`, `ingest` and `selftest`, with exit codes 0 green, 2 failed or refused, 3 harness.
    `status ID approved --approver NAME --evidence ID` is a person's act. It refuses whatever
    `check` would fail: a failed verdict or gate, a missing or changed file, a file another id
    holds, a cycle, the output of an unsaved Blender file (`--allow-dirty` overrides that one),
    a diagnostic run. `status ID superseded --by X` refuses an unknown, dead or circular
    successor.
  - **`check`'s rules:** they include `parent-cycle`, `superseded-cycle` and `dual-owner`.
    NaN and Infinity are never read or written. A torn last line is a warning and is moved
    aside on the next write; a corrupt line in the middle stops every write.
  - **`stale`:** it reads every link: an upstream id whose content rev moved, or an outside
    version given on the command line.
  - **References:** `reference/workflow.md` adds a change-record template (problem, source
    version and sha, check, hypothesis, change, verification, result, rollback) and the order in
    which evidence wins, starting from a re-opened saved file.
- **Adopt and ingest.** `registry_adopt.py` reads a hand-written `manifest.md` once into records
  and never writes it:
  - Header words are matched in English and Chinese, `Filename` and `Asset` among them.
  - A live row wins over a struck row of the same path.
  - `not **unused**` is not unused.
  - A numbered range stops at 10,000 names with a `range-capped` warning.
  - A folder cell is not taken whole: it warns `folder-cell` and asks for a glob.

  `registry_ingest.py` turns a producer's JSON into a partial record and `--write` records it.
  It takes anything with a `record` key (the `bcr_*`/`brt_*` reports, the producer scripts
  below), `frames.json` or a codex call. `tools/check-registry.py`, a new CI step, runs the
  selftests and the negative fixtures. It also holds the default budget table to one file, which
  `art-direction-schema.md` links to, and fails a skill file that still quotes a fixed triangle
  band.
- **`unity-3d-models` — routed by source, budgeted by a person.** `SKILL.md` routes an
  image-to-3D GLB, a ship-track character (its game mesh before the rig), an FBX character, a
  Blender rig and a purchased pack. `reference/budgets.md` is the generation preset ladder:
  - The showcase is the baseline per class, biased to quality.
  - The same asset is generated at every preset up to it, Small, Medium, Template, Large,
    Showcase. The presets are generation settings and no class is held to them.
  - The rungs are placed **static**, unrigged, in the real game scene at the class's instance
    count. They are compared side by side under the game camera and timed with a `perf-window/1`
    window on the target device.
  - A person picks a rung, and the `3D budgets` row gets its `calibrated` date. Until then
    every tool reports and fails nothing.

  The two tables are `3D asset classes` and `3D budgets`, with six default rows to replace (the
  character class keeps 2 LODs). A table says when to use `gltf-transform` and when Blender, and
  anything skinned is decimated before it is rigged. `reference/asset-classes.md` gives each
  class's pivot, scale, collision, LODs and prefab. `reference/model-audit.md` covers two Editor
  scripts:
  - `ModelAudit.cs` (read-only; `Tools/Unity Dev/3D Models/Audit Folder` or
    `-executeMethod ModelAudit.AuditBatch`) logs one `[MODEL-AUDIT]` line per class folder,
    with texture sizes as imported after Max Size.
  - `ModelImportPolicy.cs` applies a folder's `.modelpolicy.json` on a model's first import
    only.

  The fixed triangle tables and the stock 512 px texture size are gone from
  `import-and-decimate.md`, `performance-budget.md` and `unity-scene-optimisation` →
  `reference/texture-streaming.md`. `unity-3d-level` and `unity-gameplay` route a class's
  budget to `reference/budgets.md`.
- **`blender-character-rig` → `reference/game-mesh.md`.** This is the ship track's mesh, made
  before the rig. Route A regenerates at the picked preset. Route B, for joints that deform
  badly, is retopology, UVs and a Selected-to-Active rebake from the showcase. The preview rig's
  weights, carried over by Data Transfer, test the joints in extreme poses before the real rig;
  used as a head start, they pass the same skinning gates and are never taken unseen. Gates check
  the budget, silhouette, UVs, bake and joints, and a person approves the side-by-side. The FBX
  example exports with `FBX_SCALE_ALL` and applied unit scale. `fbx-export.md`'s Unity check
  reads three bones against Blender to the millimetre.
- **`unity-rigged-character` — the Unity-side contract.** The order is import → Avatar →
  Animator → gameplay rig, for any route: Auto-Rig Pro, a Blender rig, Mixamo (optional,
  `reference/mixamo-route.md`) or an auto-rig service.
  - **Rig type:** Generic for clips retargeted in Blender. Humanoid only for a body-part mask, IK
    or other avatars, and measured first: on a test rig it moved bones up to 20° and a hand
    socket 13–15 cm on the same clip.
  - **A GLB's Avatar:** a GLB takes Humanoid clips through an Avatar built from bone names with
    `AvatarBuilder.BuildHumanAvatar`.
  - **`reference/unity-import.md`:** it gains a held prop's shape key as a BlendShape. A Blender
    driver does not reach Unity, so its value is baked to keys.
  - **`reference/textures.md`:** Blender's FBX carries metallic and roughness, but Unity binds
    only base colour and normal, so the metallic/smoothness map is built from a staging folder.
  - **`reference/gameplay-rig.md`:** it names the three bounds boxes and shows why a gameplay
    volume is a constant.
  - **`reference/source-art-and-3d.md`:** it holds the route table, the positional multi-view
    trap (`[front, back]` reads back as left) and the mirrored left/right check.
  - **`reference/troubleshooting.md`:** its symptom rows are by stage.
  - **Editor scripts:** four parameterised files in `resources/Editor/`, configured by
    `character-pipeline.json` (`reference/editor-scripts.md`): `CharacterImportSettings.cs`,
    `CharacterAvatarLinker.cs`, `CharacterAnimatorBuilder.cs` and `MixamoTextures.cs`. The
    prefab step is a snippet in the same page.
- **Generation.**
  - **`codex-visual`:** `reference/image-to-3d-input.md` gains a realistic humanoid A-pose
    variant (straight elbows, true 90° profiles, empty hands, fingers apart only for a close
    grip) and a T-pose variant for the Mixamo route. `art-direction-schema.md` gains a `## 3D`
    chapter that links to the budget tables instead of copying them.
    `scripts/contact_sheet.py` composes the 8-view QA sheet, animation contact sheets, preset
    comparisons and before/after pairs, and writes nothing unless every `--require` file passes
    (exit 0 written, 2 refused, 3 unreadable or unwritable; `reference/review-sheets.md`).
  - **`comfyui-asset-generation`:**
    - Four views are cleaned before upload with BiRefNet: an RGBA cut-out, a mask preview and a
      black composite per view, with the mask polarity checked per tool and unique upload
      names.
    - `scripts/graph_diff.py` compares the project graph with the official template node by
      node and input by input (exit 0 same, 1 differ, 3 unreadable) before any knob moves.
    - The presets are Small, Medium, Template, Large and Showcase: generation settings, none a
      target. Generating each once is cheap.
    - Diagnosis is by stage and hedged, and its outcomes include "switch to a known-good
      baseline graph" and "adopt the usable baseline and record its limits".
- **Producers pin their output — added keys, the same exit codes.**
  - `codex_generate.py` adds `model`, `prompt_sha256`, `inputs[]` with hashes, `out_sha256` and
    a `record`. `--job-log PATH` writes one line per call, with the prompt and any URL replaced.
  - `comfy_asset_client.py` adds `workflow_sha256`, `workflow_name`, `overrides` (text values as
    a 12-hex hash), `server_label`, `output_files[]` with hashes, a hash per upload and a
    `record`. It warns when the server renamed an upload, and takes `--server-label` and
    `--job-log`. The server's address never reaches stdout or the log.
  - `inspect_glb.py` adds `gates`, `warnings`, `sha256` and `record`, plus `--class` with
    `--budgets ART_DIRECTION.md` (a file with no `3D budgets` table: report only) and
    `--json-out`.
  - `audit_3d_source.py` adds `--json-out`.

**Changes a project must know.**
- The Editor menus are `Tools/Unity Dev/Rigged Character/…` (Reimport Character Folder, Link
  Animation Avatars, Build Animator, Apply Mixamo Textures) and `Tools/Unity Dev/3D
  Models/Audit Folder`. Nothing answers on the old `Tools/Art/Character → …` items, and a project
  that copied the old templates keeps its own copies.
- `CharacterImportSettings` no longer forces Max Size to 512. Max Size is left alone unless
  `character-pipeline.json` sets `maxTextureSize`, or `targetTexPx` from the character's budget
  row.
- `MixamoTextures` binds the mask only from a `*_MetallicSmoothness` map. It names a skipped raw
  metallic map in `note`.
- A status change is one command, `status ID STATE [--by ID] [--allow-dirty] [--approver NAME]
  [--evidence ID]`. `--art-version N` writes a `made-under art:direction` link with `rev` N.
- The pages `editor-templates.md`, `mixamo.md`, `mesh-prep.md` and `character-art-brief.md` are
  gone from `unity-rigged-character`. Their content is in `editor-scripts.md`, `mixamo-route.md`
  and `codex-visual` → `reference/image-to-3d-input.md`.
- The image-to-3D presets are named Small, Medium, Template, Large and Showcase, where they were
  Pickup, Obstacle, Hero, Close-up and Showcase. The budget class is `hero-prop`, not `hero`.

## 0.28.0

Fifty-seven skills. The new one, `blender-retarget`, moves stock or purchased clips onto a
character already rigged in Blender and turns a batch of them into a library the saved file can be
trusted to hold: a manifest of clips before any retarget, each clip converted onto the rig through
an installed Auto-Rig Pro or a pure-bpy bone map, a local weight repair where a moving joint shows a
fault, a prop checked against its hand bone in every clip, one NLA review track, and an audit that
re-opens the file. Four neighbours gain the route that leads to it.

- **Six `brt_*` modules over a shared `brt_common.py`, called like the `bcr_*` ones.** Each is
  `run(params) -> dict` behind a short stub sent through the Blender MCP server's code tool, and
  returns `ok`, `gates`, `created`, the Blender version, `schema`, the loaded file's path and save
  state, `warnings` and a `record` that an asset ledger can take as it is. A call that raises removes what it created.
  Actions are Blender 5 layered actions, played only through `animation_data.action` and its slot.
- **`reference/rest-pose-and-conjugation.md` and `brt_retarget` — a key is a turn from its
  bone's own rest.** Two skeletons rest differently, so copying the four numbers turns the target
  the wrong way. Each mapped bone's rotation is conjugated, q_t = K·q_s·K⁻¹, with one constant
  built from both rests; every key is normalised and kept in the hemisphere of the one before. A
  `reference_frame` where the source stands in the target's rest rebases the clip, so a T-pose
  source fits an A-pose target. The bones the reference walk aims (`reference_map`, less
  `no_aim`) are separate from the bones written (`map`), so a wrist converts with its arm aimed
  and the hand itself unaimed when a rig's hand tail does not lie along the palm. Translation is
  not retargeted, and the result says so (`translation_keyed` names the source bones that move).
  Output goes to a new action (refused on a taken name unless `overwrite_action`) or, with
  `into_action`, into one that exists, such as the action an Auto-Rig Pro retarget baked: only
  the mapped rotation curves are added, a channel already there refuses unless `replace`, and
  every other curve is left as it was. `max_step` is reported, not gated: conjugation keeps
  angles, so it measures how fast the clip moves, never whether the map is right. K, the bones
  aimed for each K and a hash of both rests are stored on the action. Stock bpy only.
- **`reference/arp-route.md` and `brt_arp`** — the route through an Auto-Rig Pro the user has
  installed: ops `probe`, `markers`, `match`, `bind`, `retarget`, plus `source_bones`, which needs
  no add-on and reads an FBX's skeleton so the bone map is built from the bones that file has,
  never from another skeleton's map. Nothing of the add-on lives in this repository: each call
  finds the enabled copy, drives only the operators it registered, and refuses, changing nothing,
  when one it needs is missing. Before anything bakes, every clip's file, map, switches and
  metadata are checked, so a missing metadata key fails the batch before the first bake. Then, per
  clip: the rig's active action cleared (fake user kept) and every pose bone back to identity; the
  IK/FK switches set from the rig's own bones (hands FK, feet IK by default, the add-on's value
  convention) and keyed at the first frame; hand and finger sources dropped with `exclude`; the
  previous clip's rest offset removed before the rest is redefined. Each clip reports its `bake`
  and its `metadata` phase apart, and each action is stamped with provenance properties
  (`brt_clip`, `brt_source_file`, `brt_origin`, `brt_family`) for lookups that never go by name.
  `dry_run: True` runs the first clip end to end and puts it back; the armature modifiers' viewport
  display is paused for the batch. The page adds the bind on the exact source mesh (no weld: the
  add-on binds through a voxel proxy), marker search windows labelled as one body's example, a
  deform-only weight-sum check right after binding, and what to do before a long session: a
  smoke test on a cube (a localised UI renames nodes), `PoseBone.select` in Blender 5, Python
  references that go stale when an operator replaces an object, and a client timeout sized by job
  class with Blender inspected before anything is resubmitted.
- **`reference/clip-sources.md`** — clips from an online stock library, fetched one at a time in
  the user's own browser, or from a purchased pack end in one manifest, one entry per clip, written
  before downloading and checked before any retarget starts; only what it lacks is downloaded.
- **`reference/weight-repair.md` and `brt_weights`** — a dent or a pull that shows only when a
  joint moves is repaired where it shows, not by re-skinning: `probe` a region (a mask by distance
  from the mid-plane and a height band given as fractions of the rig's height, both feathered;
  read-only), `snapshot` it, `transfer` part of an over-reaching limb's weight onto the spine
  bones, split between them by height (a reach-based share is optional), normalise the deform
  groups only, and `restore` exactly what changed; a restore onto changed topology refuses. Any
  move made to fit a prop is capped at about a quarter of the handle's radius.
- **`reference/action-library.md`, `brt_library` and `brt_drift`.** Every action carries the
  rig's slot, a fake user and an asset mark, and plays alone with finite values at its first,
  middle and last frame; one NLA track holds one strip per clip with a marker at each start; a
  catalog is written as JSON and CSV. Names are not identifiers: an action is found by its
  provenance property or the manifest's `action`, a stale take of the exact name beside it is an
  error, and a `.NNN` name is a warning, not a failure. `brt_drift` reads a carried prop against
  its anchor bone at rest and checks evenly spaced samples of every clip for both slip (2e-5 m)
  and turn (0.5°), since a prop spinning about its grip point moves no grip point.
- **`brt_audit` — a library call that passed is evidence about the session, not the file.** It
  re-opens the saved .blend in a background Blender from the host shell and compares it with what
  the caller expects: the library's own actions (those `brt_library` registered, not every action
  in the file) and their slots, NLA strips, invalid and Python drivers, unpacked and unused images,
  shape keys, finite bones as the file plays, and with `--props` each prop's parent and parent
  bone. One `BRT_AUDIT_JSON` line; exit 0 pass, 1 fail, 2 refused input (an empty `{}` checks
  nothing, so it never passes). It never saves.
- **`reference/defect-triage-and-stop.md`** — the quality target agreed with the user first; then
  four layers a rigged, retargeted character can be wrong in (geometry, skinning, animation,
  material) and the tests that separate them, one layer changed at a time at the same camera and
  frame. Stop rules: a failed call is never sent again unchanged, and a limit with no gain is
  recorded while the working baseline is kept.
- **`reference/unity-handoff.md`** — the contract chosen before export: the rig exports the
  skeleton and the clips are baked onto it, or the source clips stay the animation and Unity
  retargets them, never mixed per clip; then the smallest export that tests it.
- **One copy of shared code, checked.** A skill stays self-contained, so code two skills need is
  pasted into each between `# >>> shared:<name>` and `# <<< shared:<name>`. The canonical copy is
  `tools/shared-blocks/<name>.py`, whose first line names its targets, and
  `tools/check-consistency.py` fails on any drift. The first block, `blender_common`, sits in
  `bcr_common.py` and `brt_common.py`, so `blender-character-rig` results gain the same `schema`,
  `file`, `warnings` and `record` keys and the same `destructive_guard`.
- **`blender-character-rig`** routes retargeting stock clips to `blender-retarget`, and
  **`reference/prop-on-bone.md`** gains a section on a grip that stays stable across clips: one
  fixed local offset on an anchor Empty under the hand bone, checked by `brt_drift` and, in the
  saved file, `brt_audit --props`, and an optional grip shape key.
- **`unity-rigged-character`, `unity-animation` and `unity-3d-models`** each gain one routing row
  to `blender-retarget` for clips retargeted onto a character already rigged in Blender; in
  `unity-rigged-character` the character comes back at stage 4 with its FBX.

## 0.27.0

Tests stop queueing on one Editor, and five more ways to test arrive. The Editor's lock is per
project folder, so clone *lanes* beside the repository run several Editors on one machine at once.

- **`unity-debug` → `reference/parallel-runs.md` and `scripts/lanes.sh`.** A lane links `Assets`,
  `Packages` and `ProjectSettings` back to the repository, copies `Library` (`cp -cR`, an APFS
  clone, with the two asset-database locks removed) and keeps its own `Temp` and `Logs`. Lane 0
  is the repository itself. `lanes.sh setup [N] | status | clean | run [--main-only] [--lane K]
  [--no-wait] -- <Unity args>` takes a free lane under a `mkdir` lock with a pid (a dead holder's
  lock is reclaimed, a lane with an open Editor or a lockfile is skipped, a run queues by default),
  substitutes `{project}` and `{lane}`, exports `LANE` and `GAME_DATA_DIR`, and returns Unity's own
  exit code. Clone lanes run read-only work (compiles, EditMode and PlayMode tests); anything that
  writes assets runs on lane 0. The page covers what each lane must keep to itself (results, logs,
  save data through `resources/LaneDataPath.cs`, PlayerPrefs as a check step), the
  `runInBackground` restore after every leg, compiling a new file on lane 0 first so two lanes
  never write two `.meta` GUIDs, lanes per GB of RAM, Smoke/Full/Perf/Soak categories with the
  `-testCategory` syntax (`;`-separated regexes, `!` to exclude), why the ParrelSync package's save
  block argues for script-built lanes, and one multiplayer role per lane.
- **`scripts/merge_results.py`** merges a suite split across lanes: every shard must be this
  run's (`--since`), no test may appear twice, none may be missing against `--inventory`, and an
  inconclusive test is a gate that did not run (`--allow-inconclusive` opts out). Exit 0 green,
  2 a real failure, 3 the harness failed — do not retry.
- **`reference/player-tests.md`** — tests run inside a macOS or Android player
  (`-testPlatform StandaloneOSX` / `Android`, `-playerHeartbeatTimeout`) for what only a build
  shows: stripping, platform defines, initialisation order. Builds write assets, so lane 0 only.
- **Golden images:** `reference/visual-checks.md` gains a baseline flow, and
  **`scripts/golden_diff.py`** judges a run's screenshots against accepted baselines by mean,
  p99 and changed-pixel share, with per-image masks, heatmaps, `[SHOT]` state lines checked
  against the log, and `--record` as the only way a baseline changes. Same 0/2/3 exit codes.
- **`unity-profiling` → `reference/perf-tests.md` and `templates/PerfRegressionTest.cs`** — a
  frame-time gate on the Performance Testing package, judged by the median against this machine's
  recorded baseline plus a tolerance. It never asserts until a row for this machine is recorded,
  and it owns the machine: no other lane runs beside it.
- **`unity-play-harness` → `reference/soak.md` and `templates/SoakTest.cs`** — minutes of seeded
  random input through the game's own input funnel over every situation, invariants checked by
  `journey_report.py`, and the seed and step printed so a red run replays. `[Category("Soak")]`
  keeps it out of every ordinary run; a soak suits a clone lane.
- **`unity-multiplayer` §4** — a host and a client on two lanes as an automated first pass, and
  why it never replaces two devices on two networks.
- `unity-debug/reference/test-verdicts.md`: Unity also exits 2 when the only problem is an
  inconclusive test. `unity-cli/reference/ci-surface.md` §4 contrasts local lanes with
  `unity test --shard`.

## 0.26.0

`codex-visual` returns the image its own call rendered, and `comfyui-asset-generation` builds a
multi-step clip from keyframes. Both come from one game project's concept and storyboard work, and
the counts below are that project's.

- **`codex_generate.py` no longer takes another job's image.** It took the newest PNG to appear
  anywhere under `$CODEX_HOME/generated_images` during the call, so a concurrent codex session's
  render could come back as the result (once: a storyboard keyframe returned as another job's
  pixel-art character), and a call that rendered twice was silently resolved to one image (8 of 35
  concept screens). Each call now runs under a private, temporary `CODEX_HOME` (`auth.json`
  linked, `config.toml` copied, removed afterwards; `--shared-home` opts out, `--keep-home` keeps
  it), and the capture reads the `session id:` line codex prints and takes only that session's
  folder; under `--shared-home` with no id, only session folders created during the call. Every
  new image is written (`DEST`, then `<stem>.2.png`, …) and listed under `images`, with exit 5
  when there is more than one. `--expect-size WxH` exits 6 on a mismatch, the file written for a
  look; `--size-tolerance` defaults to 1 px because one 16:9 ask came back both 1672x940 and
  1672x941. Existing flags, JSON fields and exit codes 0, 2, 3 and 4 are unchanged.
  **Behaviour change:** isolation is the default. With no `auth.json` (a keyring or API-key login)
  the call falls back to the shared home and says so under `isolation_skipped`; if codex ever
  replaces the `auth.json` link with a file, the private home is kept and flagged
  (`auth_link_replaced`), not deleted. Tested offline in 11 scenarios against a stand-in `codex`,
  and with one real generation in a private home (exit 0, 1254x1254, the session id matching the
  folder, the user's `generated_images/` and `auth.json` untouched).
- `reference/codex-runtime.md` §1–§3 and §9 and `reference/image-model.md` §6–§7 replace the
  "copy the newest PNG" recipes with the script or a by-hand capture by session id.
- **Candidate boards are game screens, not posters** (`image-model.md` §7, PHASE 1 step 3): style
  x 2–3 key screens, each style's first screen chained with `-i` to its others, numbers the only
  text, a Pillow contact sheet to present and the originals to judge, and a house-rules block that
  grows by one line per recurring defect. One project chose and locked its style from 35 such
  screens over four rounds, none re-rolled. `unity-game-brief`'s `visual-direction.md` says it in
  one bullet, and names a flat-versus-juiced composited preview as the answer to "will it look
  flat", pointing at per-lane hit stop in `unity-game-feel`.
- **Character families and static pose sheets** (`animation-sheets.md` §4–§5): one finished action
  sheet as the animation reference for its siblings, with `{WHO}`, `{FEATURES}` and `{KEY_HEX}`
  filled per character and a key colour per character; nine static poses per character with the
  motion made downstream, feet and grip anchors measured off the keyed cells and checked on a dot
  sheet, the feet as the pivot and the grip as a child transform (`unity-2d-sprites`
  `sprite-geometry.md` §3 points there). One project, one run each: 3 of 3 and 4 of 4 sheets
  first try, 36 feet and 8 grip anchors right by eye.
- **`comfyui-asset-generation`: MiniMax H3 keyframe segments.** `templates/minimax_h3_fl2v_api.json`
  is the I2V template plus a second `LoadImage` on `last_frame`, at the upstream 768x768 default.
  `reference/h3-keyframe-segments.md`: split a multi-step clip into ~5 s first/last-frame
  segments; chain every keyframe to the first on one camera and re-roll one whose fixed scene
  feature moved (27–37 px off produced an invented dolly, 21 px off showed nothing, and the 6 px
  tolerance was chosen, not found); a drawn layout map as the layout authority; one action per
  segment and no crossing paths, with the counter-example that non-crossing turns made all at
  once still failed; wording that avoids motion on twos, and why every segment is measured
  anyway; assembly, the audio caveat, and batching with the server redacted from logs. Evidence:
  36 H3 generations on disk, 10 in the final cut. `minimax-h3.md` points at the template and the
  reference; `multiframe-reference.md` records the one 362-frame multi-frame trial that failed,
  as one trial.
- **`scripts/video_motion.py`** (`profile`, `smooth`) **and `scripts/assemble_segments.py`**: a
  clip's still head and tail, stall% and jerk from a 224x128 grayscale mean frame difference
  (threshold 0.6, one project's value, to be retuned; `--max-stall` gates with exit 1); held
  frames dropped and rebuilt by motion-compensated `minterpolate` at the same frame count;
  segments trimmed to their moving span and crossfaded, with `:keep`, `:xN`, `:toN`, `:holdS`,
  `:rA-B`, `|` chapter breaks and `--timeline`. A segment without audio gets silence; mismatched
  sizes or frame rates are refused with exit 2. Run on synthetic clips (ffmpeg `testsrc` with a
  sliding box): a clip on twos read 48.9% stalled and 0.0% after `smooth`, frame count kept, and
  a seven-segment assembly used every suffix.

Not done here: the FL2V template and the two video scripts were not run against a ComfyUI server
in this change (the template differs from the project's working copy only in width and save
prefix); the shared-home path was tested only against the stand-in; and nothing here makes the
image model place objects to the pixel.

## 0.25.0

`codex-visual` makes pixel art that is pixel art. A pixel-style brief returns blocks of a few
source pixels that are uneven, anti-aliased and at a different phase in every cell, and
point-sampling them at a fixed step reads block edges as often as block centres. Snapping fits a
fixed number of cells to the image's own colour edges instead, holds every sheet and set of a
character to one palette, and a new gate reads the lattice, the alpha and the colours back off the
shipped files.

- **`sheet_to_frames.py --pixel-method snap`.** With `--pixelate N` it cuts every cell into N cells
  along its own block edges, takes each cell's centre colour — the median only when the centre is
  an isolated speck, so a blended edge never becomes a new colour — makes alpha 0 or 255, applies
  the palette to the small sheet and upscales by `--upscale F`. Every cut, pad, canvas and paste
  offset is then a multiple of F, so registration moves frames by whole blocks. `--snap-warp on`
  (the default) lets each cut move onto the colour edge beside it; `off` keeps one phase per cell
  for a source whose blocks really are evenly spaced. The run prints how each cell was cut
  (`warped`, `fitted`, `uniform`), `edge_fit` and `unit_gaps` — always from the unwarped fit —
  and `native_block_px` and `native_cells`, the generator's own block and the count it implies,
  to compare with N; none of them is gated. Snap is refused (exit 1, nothing written) without
  `--pixelate`, with `--dither floydsteinberg`, with more cells than the frame has pixels and with
  a `--canvas` that is not a multiple of F. `nearest` stays the default, and a run without the new
  flags writes the same files as before.
- **One palette across sheets.** `--palette K` under snap builds K colours from the small sheet;
  `--palette-file` holds a sheet to a fixed palette — the `role | hex | usage` table under the
  `Palette` heading of `ART_DIRECTION.md` (`--palette-section` names another), a `.hex` / `.txt`
  or a palette `.png` — and `--palette-out` writes the palette used as a `.hex` for the next sheet.
  The key colour is left out of a palette file whenever `--key-color` or `--bg-color` names it.
  `--colour-metric lab` (CIEDE2000, the default) or `rgb` decides what nearest means. Every
  `--pixelate` run adds a `pixel` block to `frames.json`: method, cells, block size, alpha
  (`binary`, or `soft` for a nearest run without `--palette`), the lattice evidence and the palette.
- **`scripts/pixel_snap.py`** is the last step of the static path: images already sliced and
  normalised to their final canvas are snapped to `--cells N` along the long side (or
  `--cells-wh NX NY`), one colour per cell, written as F px blocks, with the same palette and warp
  flags. `--report` measures and writes nothing; `--sweep LO HI` prints the lattice evidence for
  every cell count in a spacing range. A read-back of the written files — block lattice, binary
  alpha, colour count, nothing empty — exits 3 when it fails (`--no-gate`: 0).
- **`scripts/audit_pixel.py`** is the gate on either kind: one block size over the set, a canvas
  that divides by it, blocks starting at 0,0 in every file, F x F tiles of one colour, no pixel
  between alpha 0 and 255, at most K opaque colours per file and over the whole set, every one on
  the palette; specks are printed, never gated. Expectations come from the sidecar's `pixel` block
  or from `--block`, `--max-colours` and `--palette-file`, so several sheets can be held to one
  palette. Exit 1 on a failed gate, 2 when there is nothing to read or nothing to check against.
- **`scripts/pixel_ops.py`** is the module the three share, so the writer and the gate read one
  definition of a cell, a block and "on the palette": the cut-line fit, the per-cell colour
  recovery, the Lab / CIEDE2000 distance, the palette selection and the lattice read-back. It
  carries code ported under the MIT licence, credited in `THIRD_PARTY_NOTICES.md`.
- **`reference/pixel-grid.md`** holds the path: the five properties the gate reads, why the
  generator's grid defeats point-sampling, the Pixel spec in `ART_DIRECTION.md` — cells per frame
  N, block scale F, a fixed palette or K colours, now spelled out in
  `reference/art-direction-schema.md` — both command sequences for the courier run, the derived and
  the authored palette, the half-block budget a snapped asset needs in `audit_set.py`, and one N
  and F per character in place of a resample. `SKILL.md`, `reference/image-model.md`,
  `codex-runtime.md`, `animation-scripts.md` and `geometry-gate.md` point at it.
- **`slice_grid.py` and `normalize_set.py` gain `--resample nearest`**, which keeps hard edges for
  art that is already pixel art and warns when the scale is not an integer; `lanczos` stays the
  default.

What the pixel path does not do: choose N — the cell count is the caller's, read off the art
bible, and an N far from the drawn grid aliases with no setting to repair it; dither under snap;
redraw an outline thinner than a cell; check that a tile's edges wrap; or judge the drawing, so a
dead sheet snaps into a dead pixel sheet and the animation gates still apply.

## 0.24.0

Fifty-six skills. Five new ones carry the vertical slice and its polish: `unity-interaction`,
`unity-combat`, `unity-game-ai`, `unity-scene-flow` and `unity-game-feel`. `unity-gameplay`'s
genre files name an owner, by file, for every need of every view; the neighbours that left a
switch, a hit, a sentry, a save or a shake to "the game" route to them; and the README lists the
skills in the order a game needs them.

- **`unity-interaction` — detection is chosen by perspective; the contract is the same
  everywhere.** Finding what is in reach is the easy part; the complaints are about selecting one
  target and keeping it, and about who owns the change. `resources/IInteractable.cs` is the
  contract: the interactor selects and delivers a press, the interactable decides what the press
  means and refuses on its own. `resources/Interactor2D.cs` finds candidates from a trigger list or
  a circle on a tick with a facing cone, `Interactor3D.cs` from a sphere on a 0.1 s tick with a 60°
  cone and one line of sight, or one ray from the camera in first person; cells are a board lookup
  and pointer hotspots a hit, then a walk. `resources/GateSwitch.cs` is a one-shot, toggle or held
  switch and a gate that is a four-state machine refusing a press while it moves, and
  `resources/Pickup.cs` reports once on touch or on use. `templates/InteractionJourneyTest.cs`
  opens the 3D gate once with one press and selects nothing behind the runner, and holds the 2D
  selection between two switches without flicker; `INTERACTION_JOURNEY_BREAK` set to `range`,
  `reentry`, `cone` or `flicker` turns one test red. Six reference files: the detection choice,
  the interactable contract, prompts, pickups, doors and switches, and point-and-click.
- **`unity-combat` — one swing is one damage event, and the engine will not enforce it.**
  `OnTriggerEnter` counts collider pairs, not attacks, so the trigger is demoted to a question and
  the attack keeps the list of who it has hit. `resources/DamageInfo.cs` is the message, a struct
  carrying amount, team, direction, knock-back, stun, tags and the swing id;
  `resources/Health.cs` decides whether it lands — alive, another team, not invincible — and
  raises `Damaged` and `Died`, death being a state. `Hitbox3D.cs` and `Hitbox2D.cs` query their
  volume every fixed step while a window is open and offer each hurtbox owner one hit per swing;
  `Projectile3D.cs` and `Projectile2D.cs` cast from the last position to the next, so a fast shot
  stops at a thin wall. Knock-back is a request the controller's motor carries out.
  `templates/CombatJourneyTest.cs` asserts one damage event from one swing across a sentry with two
  hurtboxes, none inside the invincibility window, and a shot covering 1.2 units a step stopped by
  a wall 0.1 thick; `COMBAT_JOURNEY_BREAK` set to `hitlist`, `iframes` or `cast` turns a test red.
  Six reference files: the damage contract, hit and hurt layers, attack windows, melee queries,
  invincibility and knock-back, and projectiles with bullet patterns as data.
- **`unity-game-ai` — perception on a budget, decisions on a tick, movement by whoever owns the
  transform.** An enemy that re-plans every frame and moves itself is slow and it jitters, so the
  brain is three layers on three clocks. `resources/Perception.cs` tests range, then angle, then
  spends one cast from a shared budget, and remembers; `Perception2D.cs` is the same test on
  Box2D. `resources/StateMachine.cs` evaluates transitions against a blackboard at most once per
  decision tick, and `resources/SentryBrain.cs` patrols, notices, chases and returns, asking an
  `IMover` for a destination and never writing a transform; `NavMeshAgentMover.cs` is that mover
  on a NavMesh, and the 2D motors and the cell map take its place elsewhere.
  `resources/WaveSpawner.cs` plans waves from a seed with a live cap.
  `templates/SentryJourneyTest.cs` needs no NavMesh: the sentry ignores a runner outside its cone
  or behind a wall, chases after its reaction time once it sees, and walks back to its post when
  its memory runs out;
  `SENTRY_JOURNEY_BREAK` set to `los`, `cone` or `memory` turns tests red. Seven reference files:
  the state machine, a small behaviour tree, perception, patrol and chase, 2D pathfinding,
  spawners and waves, and tactics AI that scores every reachable cell.
- **`unity-scene-flow` — one scene that never unloads owns what must survive a load; everything
  else is rebuilt from data.** `resources/Bootstrap.cs` is the root of a Boot scene that creates
  the services once, in order, and hands them out from a registry; `resources/SceneLoader.cs`
  loads and unloads additively with progress, a stall limit and one operation in flight;
  `resources/GameState.cs` is seven phases and a table of legal transitions, pause being one of
  them. `resources/SaveStore.cs` holds a versioned `SaveData`, a migration chain and a write that
  leaves the old save or the new one and never neither, `PersistentId.cs` names a scene object to
  the save, and `PickupObjectPool.cs` lives in Boot with the counters that show whether it is
  working. `scripts/save_check.py` reads a save from outside Unity and exits 1 on a missing
  version, a missing key or a serialised object reference. `templates/SaveRoundTripTests.cs`
  reads back what it writes, migrates a version 1 file to version 2, recovers the backup from a
  file cut short and never overwrites a save from a newer build; `templates/SceneFlowJourneyTest.cs`
  keeps Boot alive under an unloading level, refuses an illegal transition and respawns the same
  pooled pickups, and `SCENEFLOW_JOURNEY_BREAK` set to `illegal`, `boot` or `pool` turns one test
  red. Seven reference files: bootstrap, additive scenes, game state and pause, the save format,
  checkpoints, pooling, and ScriptableObject config.
- **`unity-game-feel` — feedback is a stack per event with a budget.** Juice added effect by
  effect makes every event loud and none of them important, so each gameplay event — hit, pickup,
  launch, land, fail — gets one row: what plays on each channel, for how long, how strongly, at
  what priority. `resources/Feedback.cs` plays a row's motion, flash, particles, shake, sound,
  haptics and time under a global budget and the player's reduce-motion and reduce-flash settings,
  and sends shake and rumble out as events so it compiles without Cinemachine or the Input System.
  `resources/HitStop.cs` is the one owner of `Time.timeScale`, with a request queue;
  `RendererFlash.cs` captures the look once and restores it on every way out; `Tween.cs` squashes
  and eases with no library; `SfxPlayer.cs` pools voices with variance, cooldowns and per-event and
  global caps; `resources/Editor/ParticlePresetBuilder.cs` builds hit, pickup, landing and launch
  emitters and reports before it creates. `templates/FeelJourneyTest.cs` asserts time back at its
  earlier scale after overlapping stops and a requester destroyed mid-stop, a flash that restores,
  and thirty pickups in 0.1 s starting no more sounds than the cap; `FEEL_JOURNEY_BREAK` set to
  `restore`, `flash` or `voices` turns tests red. Seven reference files: the feedback stack, hit
  stop and time, flash and squash, particles, trails, SFX events, and haptics.
- **`unity-gameplay`'s genre matrix is complete.** The hub's routing table gains a row for each of
  the five, and every genre file ends on a table that names the owning skill and file for each
  need — controller, camera, level, physics, draw order or light, animation, interaction, combat,
  AI, scene flow and saving, feel, journeys. The essentials the genre files carried for want of an
  owner go: the 3D switch and sentry, the side view's pickups and hazards, the top-down sentry's
  state machine and cone, the grid's enemy turns, and the fixed screen's picking code now route to
  `unity-interaction`, `unity-combat`, `unity-game-ai`, `unity-scene-flow` and `unity-game-feel`
  by file. `reference/pipeline-stages.md` names the slice's level and loop skills and the polish
  stage's feedback stack, and hands saving to `unity-scene-flow`; `templates/GAMEPLAY_RECIPE.md`
  gains rows for interaction, damage, opponents, scene flow and feedback.
- **Neighbours route to them.** `unity-2d-controller` and `unity-3d-controller` send use presses
  to `unity-interaction`, health and knock-back requests to `unity-combat`, and what a sentry
  decides to `unity-game-ai`, where it was "the game's". `unity-input` names `unity-interaction`
  for the interact press and `unity-scene-flow` for pause; `unity-animation` names `unity-combat`
  for the hitbox an attack window opens, and `reference/ik-and-rigging.md` reads `SentryBrain`.
  `unity-camera` leaves which event shakes to `unity-game-feel`; `unity-audio` and
  `reference/mixer-routing.md` send SFX events, voice caps and cooldowns there, in place of a line
  that put mixing outside the library. `unity-navigation` no longer claims chase and patrol: its
  description and Scope send what an enemy sees and decides to `unity-game-ai`. `unity-physics-3d`
  and `unity-physics-2d` send hit and hurt layers to `unity-combat` and pickup and switch triggers
  to `unity-interaction`. `unity-new-project` and `unity-game-brief`'s architecture proposal and
  simulation/presentation split route the Boot scene, the save and an enemy's decisions to
  `unity-scene-flow` and `unity-game-ai`. `unity-2d-level` and `unity-lighting`'s mobile subset
  replace the placeholder `SentryController` and `PickupPool` with `SentryBrain` and
  `PickupObjectPool`, and `unity-play-harness`'s courier situations point at both.
- **The README follows the pipeline.** The skills table, in all four languages, is grouped by the
  stage a game is in, top to bottom: every stage (terminal and search), concept, 3C prototype,
  the vertical slice's 2D world, 3D world, systems and UI, production assets and AI asset
  generation, polish and optimisation, shipping, and backend and commerce. A line above the table
  says so and sends any gameplay request to `unity-gameplay` first. The plugin description lists
  the skills under the same stages.

## 0.23.0

Fifty-one skills. Four new ones are the 3D world: `unity-3d-controller`, `unity-3d-level`,
`unity-lighting` and `unity-scene-optimisation`. `unity-gameplay` routes its 3D recipe to them by
file, and the neighbours that sent 3D lighting, scene cost and the character's bridge nowhere name
an owner.

- **`unity-3d-controller` — choose who owns the transform before writing a line of movement.** Most
  3D controller bugs are two components moving one object — a `CharacterController` beside a
  non-kinematic `Rigidbody`, an agent beside a controller, root motion under a script that calls
  `Move` — so the first decision is the owner, written down per character. Once it is a
  `CharacterController`, rules and collision are two halves that never mix:
  `resources/CharacterMotor3D.cs` finds ground by its own cast and handles slopes, steps and the
  platform under the feet, whose velocity for a rider `resources/MovingPlatform3D.cs` works out, and
  `ThirdPersonController.cs`, `FirstPersonController.cs` and `TopDownController3D.cs` read one
  `RunInput` struct and call `Move(velocity, dt)` once per frame.
  `resources/LaneRunnerController.cs` is a kinematic body moved by `MovePosition`, the lane index
  being the position, and `resources/AnimatorBridge3D.cs` is the one writer of the Animator. Apex
  height and time to apex are the tunables; gravity and jump velocity are derived, and moving by the
  mean of the velocity before and after gravity keeps the apex at every frame rate.
  `templates/Controller3DJourneyTest.cs` builds its own room and asserts a 30° ramp climbed
  grounded, a 0.3 step climbed and a 0.6 one refused, the apex at 1.2 within 0.05, the stick
  relative to a yawed view, pitch clamped at 85° and a lane change landed in 0.15 s;
  `CONTROLLER3D_JOURNEY_BREAK` set to `slope`, `step`, `tallstep`, `tap`, `pitch` or `lane` turns
  one test red. Seven reference files: the model choice, grounding and slopes, jump and air, third
  person, first person, top-down and fixed cameras, and the Animator bridge.
- **`unity-3d-level` — a greybox is the level with the art missing.** The order is fixed and each
  step is proven before the next: a metrics sheet derived from the body and the jump — door 1.2 ×
  2.2, step 0.3, ramp 30° or less, jump gap 3.0 — checked by `unity-gameplay`'s `level_metrics.py`,
  then blocks on a `World` layer, a walk journey, and only then kit pieces.
  `resources/Editor/GreyboxBuilder.cs` builds the gate room from the sheet with primitives and
  reports every number that disagrees with the body before it builds; `GreyboxBuilderProBuilder.cs`
  builds the same room as editable ProBuilder meshes, in a file of its own so the first compiles
  without the package. `templates/GreyboxJourneyTest.cs` walks through the door, up the step and the
  ramp to the ledge and asserts the walker is never inside a block; `GREYBOX_JOURNEY_BREAK` set to
  `door`, `step` or `ramp` stops the walk and names where. `resources/Editor/KitAudit.cs` reads each
  kit prefab against the 1/2/4 m grid, the floor-corner pivot, its scale and its colliders, and
  `PrefabOverrideAudit.cs` lists the open scene's overrides by kind, both read-only;
  `CollisionProxyBuilder.cs` adds boxes, a capsule or convex hulls on a `Collision` child and
  reports first. `resources/SplineLane.cs` turns distance and lane into a pose along a spline. Six
  reference files: the greybox, the modular kit, prefab architecture, collision proxies, Terrain,
  and splines and decals.
- **`unity-lighting` — a light's mode decides what it can ever light.** Most lighting reports are
  not a value to tune: a Baked light does not exist at runtime, a lightmap lights only the surface
  it is painted on, and nothing warns when either leaves an object dark. A symptom table, first
  match wins, routes to six sections: the bake that changed nothing, dynamic objects black beside
  baked ones, reflections, shadows, a scene that is flat or too dark, and the Editor against the
  phone. `resources/Editor/LightingAudit.cs` prints the open scene's lighting as one JSON object —
  the URP asset in force and its shadow fields, each light's mode beside what it was baked as,
  static flags, the bake, probes, the environment — with named findings such as
  `dynamic-without-probes`, and changes nothing. `resources/Editor/BakeAndReadBack.cs` reports its
  plan, waits, bakes and prints lightmap and probe counts before and after; `baked-empty` means it
  ran and wrote nothing. Six reference files: light modes, bake set-up, probes, shadows, the
  environment, and the mobile subset.
- **`unity-scene-optimisation` — optimise the counter that moved, not the one you remember.** Every
  lever moves one counter and leaves the others alone: the SRP Batcher lowers SetPass calls and not
  draw calls, a `LODGroup` does nothing for a frame waiting on fill, and baked occlusion returns
  nothing in an open lane. Each section starts from a number `unity-profiling` reports, runs one
  global switch that shows in a single window whether its lever can move that number at all, and
  ends with the same number read again: batching, LOD, occlusion, per-layer culling distances,
  texture memory, and overdraw with 2D draw cost. `resources/Editor/SceneCostAudit.cs` prints the
  open scene's cost census as one JSON object and changes nothing; `LodGroupBuilder.cs` builds a
  `LODGroup` from `_LOD0` … `_LODn` children and `OcclusionBake.cs` bakes occlusion and reads the
  data size back, each reporting before it writes. Six reference files: batching, LOD, occlusion,
  culling distances, texture streaming, and 2D draw cost.
- **`unity-gameplay` routes its 3D recipe.** The hub's routing table gains a row for each of the
  four, and `reference/genre-3d.md` stops carrying the motor in essentials: it sends the controller
  by column — third person, first person, fixed or overhead camera, lane run — to
  `unity-3d-controller`, the greybox and the walk journey to `unity-3d-level`, and light modes, the
  bake, probes and shadows to `unity-lighting`, and its traps name the file that owns each fix.
  `reference/level-metrics.md` reads a `CharacterController` motor's reach table with `--integrator
  exact`; `reference/perspective-fingerprint.md` names the controller file on each 3D verdict;
  `reference/pipeline-stages.md` names the skills for the 3D greybox, the slice's final light and
  the change after a counter; `templates/GAMEPLAY_RECIPE.md` points the 3D motor, bridge and level
  rows at the new skills and gains rows for lighting and scene cost.
- **Neighbours route to them.** `unity-profiling` sent distant triangles to `unity-3d-models` and
  draw calls, GPU time and shadow casters to `unity-render-urp`; they now go to
  `unity-scene-optimisation` and `unity-lighting`, and `reference/where-the-time-goes.md` keeps the
  `lodBias` test and hands the `LODGroup` over. `unity-render-urp` names `unity-lighting` for light
  modes, the bake, probes, shadows, sky and fog, and `unity-urp-migration` points lighting after the
  move at it. `unity-rigged-character`'s Animator template no longer leaves its runtime bridge "not
  shown": `AnimatorBridge3D` writes its four parameters. `unity-3d-models` sends modular-kit
  conventions to `unity-3d-level` and LOD and scene draw cost to `unity-scene-optimisation`, and
  `reference/performance-budget.md` no longer tells a URP project to tick GPU Instancing, which
  changes nothing once the SRP Batcher has taken those renderers. `unity-animation`'s
  `reference/root-motion.md` no longer bakes Position (XZ) into the pose on every locomotion clip:
  on a clip that travels it stays unbaked, so the travel is root motion and is discarded with
  `applyRootMotion` off, and it is baked only on a clip authored in place. `unity-physics-3d`,
  `unity-input`, `unity-camera`, `unity-animation`, `unity-rigged-character` and
  `blender-character-rig` name `unity-3d-controller` for the character that moves.
- **What this does not do.** No skill covers interaction, combat, AI behaviour, scene flow and
  saving, or game feel.

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
