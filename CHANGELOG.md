# Changelog

Versions are the plugin's, in `.claude-plugin/plugin.json`.

## 0.47.0

The 2D frame-set audit reads more of what a viewer sees. Swapped legs are read on legs of one
colour, and a loop seam says when it cannot tell a skipped stretch from an ordinary wrap. Every
new number stays report-only.

- **`codex-visual`: `audit_identity.py` reads swapped legs on legs of one colour.**
  - The two legs are the two blobs below the crotch, told apart by their shading.
  - Two frames are compared only while the legs stay apart and neither has passed the other. A
    swap is a frame that trades looks with both neighbours.
  - The gate reports `method` (colour or shape) and `checked`. It stays null with the reason when
    the legs touch, look alike or move too far to compare.
  - The colour read is set aside when the legs themselves, where apart, never differ by CIE76 12:
    its halves were reading an arm, a belly patch or the light.
- **The loop seam says when it is saturated.** It reports `span_ratio` (how far apart the frames
  ever get, in ordinary steps), `saturated` (below 1.25) and `overlap_median`, with a warning.
  - A skipped stretch then reads like an ordinary wrap. A stall still reads under 1 and a pop still
    reads high, so the value stays measured.
- **Run on eight 2D clips of two characters.**
  - The leg swap is measured on 5 of 8 (was 1), all 0, with 2–8 frames checked.
  - A shading swap planted at one frame is found at that frame on three clips.
  - One earlier 0 (a front-view idle) is now null: its halves differed by 13.5, while its legs
    differ by at most 3.6.
  - The seam is saturated on the four 6-frame clips (span 1.03–1.09) and not on the four longer
    ones (1.50–2.08). Silhouette overlap does not separate the two groups.
- **Still open.**
  - The shape read sees shading, not which leg is drawn on top.
  - Nothing reports a run whose same leg leads in every frame.
  - The `paint_loop` work (per-try records, a composed sheet when none is given, an outline-aware
    retry order) was interrupted twice and is not in this release; its data so far did not show a
    gain over 0.46 with a sheet given.
  - Painting moved the back view away from the concept on two characters (palette ΔE 3.3 → 5.6).

## 0.46.0

Steadier and fairer measurements: the AI's body guess barely moves from run to run, a chibi knee no
longer comes from a pocket, `compare` tells a designed repair and far-off noise from a regression,
and the game mesh keeps the tips the remesher rounds off. No limit was widened.

- **`arp_smart.py`: each AI body guess averages 30 front pictures** (`--body-samples`, the add-on's
  most; it used the add-on's 10). Each picture turns the camera by a random whole degree, and which
  angles get drawn is what moved the guess. One guess's wrist scattered 1.97 mm (sd) and now
  scatters 0.22 mm, at a somewhat longer time per guess. Across separate runs the wrist's height sd
  went from 1.40 mm to 0.17 mm. `body_runs` gains `marker_spread_m`. `--body-runs` stays 3 with the
  per-marker medoid (a coordinate median was within noise at 30 pictures). `--body-samples` takes
  1–30; 0 leaves the add-on's setting.
- **`arp_markers.py --body chibi`: shorts over the knee.** A hem 35–70 % of the way up the leg where
  the section steps out going up is shorts over the knee, and no knee cue above it is used (a cargo
  pocket read as a kneecap); the knee takes the 0.52 fallback. A knee pad's lower edge reads the same
  way (documented).
- **`autorig.py --repair-near M` (default 0.05; 0 turns it off): a reading on its limit is repaired
  too.** With the wrist steady, an elbow that sat just under its limit stayed unrepaired in every
  run. The repair ladder now also runs when deform passed with an elbow or knee volume margin under
  M, and keeps the bind with the larger worst margin over the deform gates. It never keeps one that
  fails a gate, and the stage's exit stays 0. The repair block gains `trigger` (failed /
  near_limit), `kept_repair` / `kept_original` and both worst margins. Why 0.05: the AI's noisy
  wrist moved such an elbow's volume by about ±0.01 (margin ±0.03), and `--min-margin 0.05` is the
  room a repeated run asks for. No limit changed.
- **`rig_exam.py` bench records the repair ladder** per character (the chosen run and each
  `--repeat` run). `compare` lists `repair_now` / `repair_gone` / `repair_changed` /
  `repair_unknown` (no repair key, or a run's summary not read). A still-passing `deform.*` margin
  drop goes to `repair_tradeoffs` only when the character's repair changed and another still-passing
  `deform.*` gate of the same step rose by more than `--margin-drop`. A drop of at most `--near`
  (1.0) that ends at `--near` or more goes to `informational` (only `>=` gates past twice their
  limit; never `stable`). Pass → fail, `stable`, a gate no longer read and the exam lines always
  regress. `--tradeoff-floor` (0.05): a trade-off is only the ladder's own pair (volume loss and
  self-intersection), only when one side's bind is a repair, and only when the new margin stays at
  the floor or above. bench/1's repair reading has `trigger`, `used` and `runs.used`, and the
  deform stage reads the kept bind. `--selftest` exits 2 on failure (was 1). These are the
  detector's floors, not gate limits.
- **`game_mesh.py` pulls back the tips QuadriFlow rounds off** (`--tips`, default half the extent
  limit). The voxel surface keeps extent within 0.0014 H; QuadriFlow loses it, so a finer voxel
  cannot fix it (and breaks the fill: solid 0.41–0.44). Each lost spot's nearest game vertex moves
  onto its farthest point, neighbours follow and are projected back; no vertex or face is added. A
  pull that flips a face, lifts one off the surface or runs past 3 edge lengths is refused.
  - When the cavity fill leaves pieces apart (legs up a shorts hem), the fill closes wider, up to 4
    voxels, until there is one solid piece.
  - Default `--ray` 0.06 → 0.10 × H: Blender keeps the first front-facing hit and only drops it past
    the distance (of 2,098,050 texels hit at 0.08, none changed at 0.10).
- **Run on real assets** (rig exam and `autorig.py all --repeat 3` on the four characters, benched
  and compared with 0.45.0 re-benched with its repair reading).
  - **All four characters pass `stable` for the first time.**
    - The mascot's leg ratio goes from 0.847 to 0.925 (margin −0.0052 → +0.1304).
    - The gatekeeper's elbow sat at 0.344–0.347 (margin 0.0074) once the wrist was steady. It is now
      repaired in 3 of 3 runs to 0.071–0.072 (margin 0.79), with self-intersection p95 at 0.073
      (margin 0.077). In 0.45 the noisy wrist got it repaired by chance.
    - The runner and the guard are unchanged: stable 0.189 and 0.01.
  - **AI wrist spread:** across separate runs, the wrist's height sd went from 1.40 mm to 0.17 mm.
  - **Rig exam:** identical to 0.45.0. The near-limit ladder fired on no exam body, whose highest
    hinge reads 0.27.
  - **`compare` against 0.45.0 exits 2 on one pair:** the runner's self-intersection margin
    0.45 → 0.42 (p95 0.0443 → 0.0464) in the chosen run. Its three runs read 0.0442–0.0464, inside
    the 0.0442–0.0575 its runs have read since 0.43, so it is run-to-run spread, not a change.
    Informational: one finger-length margin 7.66 → 7.43. Improvements: 11, mascot and finger lengths.
  - **`game_mesh.py` at 8,000 triangles:**
    - runner and gatekeeper now pass every gate. `game.extent` goes 0.0111 → 0.0025 and
      0.0183 → 0.0045, and the gatekeeper's bake misses 0.0063 → 0.0045. The guard still passes.
    - Silhouette IoU is up on all four: 0.961 → 0.970, 0.964 → 0.971, 0.954 → 0.963 and
      0.959 → 0.972.
    - The mascot is now one surface (3 → 1) and solid (0.821 → 1.003). It fails bake misses instead
      (0.004 → 0.0088): the closed floor under its shorts hem, whose rays first meet a culled
      backface.
- **Still open.**
  - The mascot's knee is the 0.52 fallback, because the real knee is hidden under the shorts.
  - The shorts-hem rule is chibi only.
  - The near-limit ladder stops at the first attempt that passes, without trying a softer amount.
  - `game_mesh.py`: the mascot's bake misses under the shorts. The extent at another seed sits
    close to the limit (0.0084 and 0.0097).

## 0.45.0

The 3D chain's generated mesh, made lighter and gated. Pixal3D's hidden inner shell can be cut
from the GLB before import, the ship track's game mesh is one gated headless run instead of a
recipe, and the armoured guard no longer stops at deform. No limit was widened. Two models in the
0.43 plan are not in this release: SkinTokens is deferred, and BEN2 is not taken in.

- **`blender-character-rig`: `scripts/shell_strip.py IN.glb --out OUT.glb`** removes an
  image-to-3D mesh's inward-facing inner shell from the GLB, on the host (numpy, Pillow, SciPy,
  `mesh-texture-paint`'s `mvtex.py`).
  - A triangle seen from outside (512 orthographic views at 256 px, both faces drawn) is always
    kept. An unseen triangle whose straight-behind ray first meets a seen sheet facing the other
    way is removed. The rest take their nearest label across edges that do not fold over.
  - Only geometry changes: every vertex attribute is cut together and the images are written
    byte for byte.
  - Gates, read back from the written file: `seen_kept` and `texture_coverage` (write checks),
    silhouette IoU and view match over 10 check views that are not strip views (≥ 0.995), images
    identical. Removed and freed-UV shares are reported. A quantized GLB is refused.
  - The result is still not manifold enough for QuadriFlow.
- **`blender-character-rig`: `scripts/game_mesh.py SHOWCASE --out DIR --target-tris N`** runs
  S5 route B as one gated headless call.
  - Steps: voxel remesh with the generator's hollow inner shell filled into a solid; QuadriFlow,
    or AutoRemesher (`--autoremesher PATH`, under `--timeout`, falling back to QuadriFlow on a
    hang, a crash, no output or a result over budget); Smart UV with fold re-projection; a Cycles
    rebake of base colour, normal and occlusion from the showcase, metallic held at 0 for the
    colour bake.
  - Gates: triangle budget, one surface, solid, extent, silhouette IoU, UV bounds, overlap and
    stretch, bake misses, bake colour difference, and `mesh_check.py --body`. Each limit has a
    planted case that fails it.
  - It refuses a missing showcase before Blender starts, and a mesh_check that crashed never reads
    as a pass from an old report.
- **A held prop modelled into the arm rides the hand whole.** A strip of a shield's face that the
  cut boxes or the arm's clearance missed (a piece of the outward skin every path from which to
  the body runs over the prop) now goes with the prop, with the inner shell right behind it
  (`autorig.py` `prop_pieces`). `deform_gate.py` leaves it out of the self-intersection count only
  when the bind made it rigid on the hand (`cut_off`, reported in `prop`): a strip left on the
  forearm still counts. The new gate on the previous bind still fails (0.0815), so the gate is
  not loosened.
- **`arp.hand_reach_export` is written on every run** (`reexport` true or false). It was written
  only when hand_reach moved weight, so a compare could miss it on one run and not the next.
- **Asset toolchain:** AutoRemesher 1.2.0 (MIT since 1.0.0) in `VERSIONS.md` and
  `THIRD_PARTY_NOTICES.md`. `licences.md` gains a BiRefNet row: MIT weights trained on DIS5K,
  whose terms bar commercial use; record cut-outs with `licence.source` `birefnet`.
- **Run on real assets.**
  - **Rig exam:** the same as 0.43.0 (joints p95 0.0294, every planted fault caught, controls pass).
  - **`autorig.py all --repeat 3` on the four characters:**
    - The guard passes for the first time: `deform.self_intersection_p95` 0.0706 (margin
      +0.1175) in 3 of 3 runs, 0.0809 (−0.0112) in 0.43.0. Its `mitten_tear` margin moves from
      0.705 to 0.655; the bind, not the measurement, moves it.
    - The runner passes (stable margin 0.173).
    - The gatekeeper passes. Its elbow, which sat 0.004–0.03 from the volume limit, crossed it
      before repair in 6 of 9 runs. The elbow repair then fixed it: volume margin 0.78, but
      self-intersection margin 0.09 instead of 0.16. The stable margin went from 0.004 to 0.09.
      What decides it is the AI's wrist. Its hand length (wrist to hand tip) varied from 0.2486 to
      0.2539 m over 18 runs. A longer hand leaves a shorter forearm, and above about 0.2516 m the
      elbow at 120° loses more than 0.35. The bind is fixed by the markers: the same markers bound
      three times, or bound by the 0.44.0 and the 0.45.0 code, give the same reading. Where a run
      lands depends only on the AI's read. The 0.44.0 code crossed in 1 of 9 runs on the same
      machine; the 0.45.0 runs drew longer hands.
    - The mascot fails `markers.limb_ratio` at −0.0052, as in 0.43.0.
  - **`rig_exam.py compare` against 0.43.0 exits 2.** The lines are the gatekeeper's repaired
    elbow, the guard's `mitten_tear`, and `markers.finger_lengths` on the runner and gatekeeper.
    The finger readings sit at about 0.09 against a 0.01 limit; their margins are near 8, so a
    0.02 absolute drop means nothing there.
  - **`shell_strip.py`:** 41–58 % of the triangles removed (the runner 68,757 → 34,784), every
    gate passing. Worst view match 0.99907; the worst of 26 independent directions 0.99715.
    `mesh_check`'s `inner_shell` falls from 0.63–0.84 to 0.05–0.37 (a cape is seen from both
    sides and kept).
  - **`game_mesh.py` at 8,000 triangles, QuadriFlow:** the guard passes every gate (IoU 0.959,
    ΔE 2.66). The runner fails extent (0.0111, its hair tips). The gatekeeper fails extent
    (0.0183, a fingertip) and bake misses (0.0063, webbing under the arms). The mascot fails solid
    (0.821) and one surface (3: its legs under the shorts).
- **Still open.**
  - **SkinTokens is deferred.** Its inference path carries GPL-3.0 code, and its training data
    carries no licence.
  - **BiRefNet stays.** BEN2 is trained on DIS5K as well, so it would not settle the question.
    The DIS5K risk is noted in `licences.md`, and the call is the project's.
  - **AutoRemesher was never run here.** The fallback path is tested with fake executables.
  - **game_mesh questions:** whether one surface should allow legs under a hem; whether the 1 %
    extent fits hair tips at a low budget; roughness and metallic are not baked.
  - **ARP AI runs cannot share a machine.** They write to one inference folder.

## 0.44.0

What a person looks at, measured and pre-read. A finished mesh is compared with its concept views,
a frame set is read for identity, seams, flicker and swapped limbs, and before a person approves a
sheet Claude answers a fixed defect checklist on it twice, so the person reads only what was
flagged. Every new number is reported only: no gate rests on it until real distributions set a
limit. A person still approves.

- **`codex-visual`: `scripts/embed.py`**, the perceptual-metric engine. DINOv2
  (`facebook/dinov2-base`) and SigLIP 2 (`google/siglip2-base-patch16-224`), both Apache-2.0,
  pinned to the revisions in `VERSIONS.md`. Cosine per image pair, alpha laid over mid-grey.
  `--pairs pairs.json --out sims.json`: paths are relative to the pairs file, so the folder can be
  copied to a GPU machine and run with any Python that has torch and transformers. Without torch
  it writes every value null with the reason and exits 3: not measured is never a pass.
- **`mesh-texture-paint`: `scripts/concept_match.py MESH.glb --view NAME=PNG ...`** renders the
  mesh from each concept view with `paint_loop.py`'s cameras (several primitives and a skinned
  mesh's bind pose included), seats each concept view on the render, and reports per view the
  silhouette IoU, the palette distance in CIELAB ΔE and the DINOv2 / SigLIP 2 similarity, plus
  `compare.png`. A view on black without alpha is cut from its border colour. `--sims` reads
  `embed.py`'s output from another machine; `--embed` measures here.
- **`codex-visual`: `scripts/audit_identity.py FRAMES`** reads a frame set for what a viewer
  calls "not the same character", "it pops", "it flickers" or "the legs swapped": frame-to-frame
  and still-to-frame similarity, front against side, the loop seam (the wrap over the ordinary
  step, as `sprite-from-video` reads it), the largest one-frame A → B → A change inside the stable
  silhouette (with its frame), and leg colour signatures that swap while the legs do not cross.
  Legs of one colour report the swap as not measured, never as 0.
- **Report-only gates.** A gate with `limit: null`, `pass: true`, `"report_only": true` and no
  margin; a value that could not be measured is null and named in `not_measured: [{name, why}]`.
- **Claude pre-review: `codex-visual` `scripts/prereview.py`** and `schemas/review-1.json`.
  - `list` prints a stage's binary defect checklist (S1, S3, S3b, S3c, S5, S6, S8, S12, and A2 for
    a 2D clip's frames); the checklists live only in the script.
  - `new` composes sheet a in the spec's order and sheet b shuffled (`contact_sheet.py --order
    SEED`, seeded from the subject's sha256); a sequence (S8, A2) is reversed instead, so each
    frame keeps its neighbours. `answer` records each pass; `check` flags any defect or unsure
    answer and any item the passes disagree on, and exits 2 when anything is flagged.
  - It approves nothing. `registry.py ingest` records a review against its subject, refuses a
    draft, a review whose answers no longer give its flagged ids, or a sheet changed since, and
    `check` warns when an approved asset's latest review flagged items.
- **`schemas/skeleton-1.json` and `schemas/motion-samples-1.json`** for the two stamps that had
  none; `check-contracts.py` validates their producers' samples, the NPZ form included.
- **`audit_frames.py` sorts frames by number** (`walk_2` before `walk_10`). A folder of frames
  named without zero padding was read out of order, which moves every number that depends on
  order. `audit_identity.py` says so when a `frames.json` names files that are not beside it.
- **Run on real assets.**
  - **The four characters against their S1 views:** silhouette IoU 0.926–0.950 per view except
    the guard's back (0.859) and right (0.887), where the shield sits elsewhere than drawn; palette
    ΔE 2.5–4.6; DINOv2 0.856–0.957, SigLIP 2 0.943–0.971. The same pairs on the GPU host (CUDA) and
    on a Mac (MPS) agree to four decimals.
  - **2D, eight clips of two characters from a shipped project:** frame-to-frame similarity
    0.917–0.988; still-to-frame 0.803–0.991; loop seam 0.29–1.25 steps. The idle's largest flicker
    (0.173) names a frame whose head tilts for one frame.
  - **Pre-review,** one 3D anchor (S3, with the concept row on the sheet) and one 2D idle (A2):
    the anchor flagged 2 of 11 items (its orange soles came out tan in both passes; its bag's place
    seen in one), the idle 1 of 9 (the passes disagreed on the same one-frame head tilt).
- **Still open.**
  - **BEN2 does not settle BiRefNet's question:** its card says it is trained on DIS5K as well
    (and a proprietary set), and ComfyUI 0.39's background removal loads only BiRefNet.
  - **SkinTokens** (0.45's second opinion on the markers) is MIT with GPL-3.0 Michelangelo code
    in its inference path, names only Mixamo or VRoid joint templates, needs CUDA with flash-attn
    and has no Windows path; its VRoid Hub and ModelsResource training data carry no licence.
  - The seam ratio saturates on coarse cycles whose frames barely overlap; SigLIP 2 downloads its
    text tower too (about 1.5 GB).

## 0.43.0

A measurement round. Quality has been read one character at a time, and each 0.42.x fixed one
case; what was left open were readings at the edge of a limit and runs of Auto-Rig Pro's AI that
differ. This release makes those visible and comparable: every gate says how far it is from its
limit, a rig can be run N times and judged on its worst run, and a release can be benched and
compared with the last. No limit was widened.

- **gate/1 gains `margin`; `ok` is gone.**
  - **`margin`** is the signed, normalised distance to the limit: `<= L` gives (L − v) / |L|,
    `>= L` gives (v − L) / |L|, a range [lo, hi] gives min(v − lo, hi − v) / ((hi − lo) / 2), a
    zero limit the plain difference. Positive is safe, negative fails, 0 sits on the limit. A
    bool, a string or a dict value has none. `schemas/README.md` has the table.
  - **One copy** in `tools/shared-blocks/gate_margin.py`, pasted into each producer and kept equal
    by `check-consistency.py`: `deform_gate.py`, `mesh_check.py`, `arp_markers.py`,
    `motion_metrics.py`, `inspect_glb.py`, `autorig.py`, `rig_exam.py`, `paint_loop.py` and
    `video_loop.py`. The markers' symmetry, arm angle, limb ratios (the worst limb) and finger
    lengths now carry one.
  - **`ok`**, the old name of `pass`, is no longer written by any gate report, and
    `schemas/gate-1.json` refuses a report or a gate that carries it. A Blender op that reports
    with no gates is a result, not a verdict, and keeps `ok`. The pipeline readers still read an
    unstamped 0.34 report with a warning; `registry.py ingest` refuses `ok` at every level
    (exit 3).
  - `smart.ai_files` says its limit as `version 1.20 or newer`: a version is not a reading, so it
    has no margin.
- **`character-autorig`: `autorig.py all --repeat N [--min-margin X]`.**
  - Prep and check run once. Smart, markers, arp, contract and deform (with the repair ladder) run
    N times, each in `OUT/repeat/rN/`.
  - **`OUT/autorig.stability.json`** (gate/1): per gate the value's min, median and max, how many
    runs passed it, and the worst margin; a gate failed in a run that read no margin carries none.
    A `stable` gate passes when every run exited 0 and every margin is at least `--min-margin`
    (default 0, never negative).
  - **The run kept** is the median one: runs are ordered errors first, then failed gates, then
    passes, each by its worst margin. Its rig, export, repair and logs are copied into OUT, and the
    spring chains run once on it. The exit code is that run's, plus 2 when `stable` fails.
  - `--repeat 1` (the default) is the single run as before.
- **`rig_exam.py bench` and `compare`.**
  - **`bench EXAM [--real OUT ...] --out FILE [--label]`** writes `bench/1`: the exam's summary
    and, for each real character, every gate its stages read with the margin, its stability, its
    worst margin and its failed gates.
  - **`compare OLD NEW [--margin-drop 0.02]`** exits 2 on a gate that went from pass to fail or is
    no longer read, a new gate that fails, a margin that fell by more than the drop, a lost case,
    exam outcome or finger read, and a new false pass, slipped fault or failed control. An empty
    baseline is refused. Improvements are listed.
  - Bench files stay outside the repository, in the exam's own folder.
  - New schemas `schemas/bench-1.json` and `schemas/exam-1.json` (truth, reference, fault and
    report). `CONTRIBUTING.md` lists all eight stamps.
- **The finger vote (opt-in).** `arp_markers.py --finger-votes K`, passed through by
  `autorig.py markers|all --finger-votes K`: K readings of the hand (seed k, stations shifted by
  0, ±0.005 L, ±0.01 L …), the majority wins, a tie reads `fixed`, and `fingers.votes` records
  each reading. The default is 1, the single reading, unchanged (see below).
- **`mesh-texture-paint`: `OUT/gates.json`** (gate/1) beside `report.json`, which is unchanged.
  - `paint.coverage` holds `coverage_seeable` to `--min-coverage`, by default from
    `--coverage-for`: character 0.85, prop 0.75, part reported only. `paint.seam_delta` and
    `paint.views_refused` are reported only.
  - A run stopped by a paint server error adds a failing `paint.run_complete`. A run that paints
    nothing leaves no `gates.json`, and an earlier one is removed first.
  - It carries a partial ledger record (the painted GLB, its inputs, the seeds and models of the
    views used), so `registry.py ingest --json gates.json --write` records it.
  - `hand_views.py` paints its parts with `--coverage-for part`.
- **`sprite-from-video`: `OUT/NAME.gates.json`** beside `frames.json` (unchanged): `frames.cut`,
  `frames.periodicity`, `frames.seam`, `frames.seam_source_rate` and `frames.faults`, with the
  source clip as an input.
- **What made an asset is kept.**
  - **`layer_split.py fills`:** each fill in `fills.json` keeps its job's `record`: workflow
    sha256, overrides, prompt id, seed, prompt sha256 and model files. A fill whose gates failed is
    recorded as failed.
  - **`scene_layers.py`:** `run.json` records the seed, prompt sha256, models, workflow sha256
    and the client's record.
  - **`codex_generate.py`:** `model` is now the image model, read from the PNG's C2PA manifest
    (null when unreadable); the agent's `-m` moved to `agent_model`, and `codex_version` is new.
    Readers of `model` see a different value. Usage errors exit 1 (they exited 2, the code for a
    missing `codex`).
- **`art-asset-registry`: licences follow the inputs.** An input already in the ledger, matched by
  sha256 or else by path, becomes a `depends-on` link on every shape ingest reads. Frames cut from
  a MiniMax H3 clip now inherit its excluded territories, and `check` refuses them for a project
  sold there. `licences.md` gains `qwen-image-layered` and `openai-gpt-image`.
- **`VERSIONS.md`: an asset toolchain section.** Blender, Auto-Rig Pro (version and licence),
  ComfyUI (0.37.0 or newer for every shipped template), and each model the templates load
  (Pixal3D, TRELLIS.2, the DINOv3 encoder, MoGe-2, BiRefNet, Qwen-Image-Edit-2511 and its
  Lightning LoRA, Qwen-Image-Layered, MiniMax H3, MiniMax Music 3, Stable Audio 3 Medium,
  gpt-image), each with its licence, territory, official source and check date.
  `THIRD_PARTY_NOTICES.md` links each licence; no weights ship. Auto-Rig Pro now lists Blender
  5.2, and the docs say so.
- **Tests.** The Blender tests in `blender-retarget/scripts/tests/` and `test_arp_pipeline.py`
  read `pass` (all pass in Blender 5.2.1; the pipeline test with Auto-Rig Pro ends 16/16).
  `codex_generate.py` has a selftest and a row in `run-selftests.py`.
- **Benched against 0.42.3** (the exam on four bases, the four real characters with `--repeat
  3`): `compare` exits 0. 0.42.3's deform reports wrote bare limits, so this first compare saw
  pass and fail only; margins compare from 0.43.0 on.
  - **Rig exam:** unchanged. Eight true passes, `spiky_hair` a true fail; joints p50 / p95
    0.0094 / 0.0294 H; fingers right on 8 of 9; 31 planted faults caught, no false pass, every
    control passes. The accepted runner's base (seven more faults) was not rebuilt for either
    version: its accepted FBX was not at hand.
  - **The runner:** three of three pass. Worst margin 0.168–0.189, on `deform.volume_loss_max`
    (0.284–0.291 against 0.35).
  - **The gatekeeper:** three of three pass, but with 0.004, 0.011 and 0.030 to spare: its elbow
    volume reads 0.340–0.349 against 0.35. It takes the AI's fingers, and they move from run to
    run. On 0.42.3 the same elbow read 0.340 in one run and needed the repair ladder in two.
  - **The mascot:** stops at `markers.limb_ratio` in every run, the legs at 0.847 against 0.85
    (margin −0.0052). 0.42.2's and 0.42.3's code read the same on this file; 0.42.3's pass came
    from inputs that can no longer be traced.
  - **The guard:** stops at deform in every run, `self_intersection_p95` 0.0809 against 0.08
    (−0.0112); `skirt_tear` passes with 0.01 to spare.
  - **On the host:** the mascot's repaint used two views and stopped after three rejections
    (coverage 0.32); its `gates.json` fails with margin −0.624 and is recorded as failed. The
    courier's four layer fills pass, each with its record.
- **Still open.**
  - **The finger vote** with five readings turned `spiky_hair` to `detected` (4 of 5) and gave the
    gatekeeper its own fingers (3 of 5): the same elbow read 0.2885 in every run (margin 0.176).
    It also turned `thin` to `fixed` (2 of 5), which sent it down the mitten route and failed
    `deform.mitten_tear` (0.0026 against 0.002), and `compare` caught it. The separable hands read
    2–5 of 5 and the closed or mittened ones 0–1, one vote apart, so the default stays one reading
    until a second opinion on the hand (0.45) can settle it.
  - **The mascot's legs** (−0.0052) and **the guard's plates over cloth** (−0.0112).
  - **BiRefNet's weights:** the file the templates load is the author's MIT model, not BRIA's
    non-commercial RMBG-2.0, but its card says it was trained on DIS5K, whose terms allow only
    non-commercial research use of the data. Whether that reaches the weights is a legal call.
  - **OpenAI's terms pages** refused a direct read (HTTP 403); the gpt-image rows rest on their
    indexed text.
  - `audit_3d_source.py` and `inspect_glb.py` exit 2 on a bad flag, a code their docstrings give
    to an unreadable file.

## 0.42.3

A strengthening round from a fourth 3D character, an armoured depot guard in a tunic and a cape
with a round shield held at the left hand, from the chibi mascot's own detection run and the
gatekeeper's one failing run in four, and from a 2D courier on a board. A held prop now rides its
hand instead of being read as the arm, a hip bag, a cap's crown and a cape are told apart from
hair and from a back bag, the heavy body's hip and shoulder are placed right, and in 2D a board
keeps both feet planted through a push and an ollie.

- **`character-autorig`: a held prop.** A shield standing beside one arm from above the armpit
  ran its own vertical track, so the arm read vertical and was refused.
  - **`arp_markers.py`** sets that track aside and searches the arm again (up to twice). That
    arm becomes the other arm mirrored, the fingers are read on the free hand, and the track's
    cut boxes are written as the report's `prop` (side, slices). If both arms set a track
    aside, the markers are refused, as before, because there is nothing to mirror from.
  - **`mesh_check.py`** takes the midline from the feet when the extent under 0.4 H is more than
    0.02 H off them.
  - **`bcr_import_prep.py`** centres X on the feet when the bounding box is more than 0.01 H
    off them.
  - **`autorig.py` arp stage:** the prop's skin, less the arm's own, goes rigid onto the hand
    bone. The fingers on that hand fold onto the hand, so a fist cannot close them into the prop.
  - **`deform_gate.py --prop`** (which `autorig.py` passes) leaves that rigid skin out of the
    self-intersection count, as it would a separate object.
  - A prop that only starts under the hand is not handled; expect `markers.symmetry` to fail
    (untested). Attach such a prop after the rig.
- **The hip and the shoulder.**
  - **The hip** is the crotch plus the leg's half-width just under it, at least 0.02 H: thick
    thighs meet a thigh's radius below the hip joints. Over a measured knee the thigh is at most
    1.1 × the shin, because shorts widen the leg at the crotch.
  - **The shoulder** sits a quarter of the arm's radius outside the torso's edge, not a half (a
    heavy chest reaches past the joint).
  - **On the skirt route**, a crotch measured inside the skirt places the hip a leg loop's
    radius over it, as in trousers.
  - The chibi route is unchanged.
- **`deform_gate.py`.**
  - **The `fist` pose:** Index to Little now curl about the knuckle line (Index1 → Little1). A
    finger placed a few degrees off parallel no longer swings its tip across the palm into the
    thumb. The angles and the limits are unchanged.
  - **`hinge_reach`:** one test, used by both the volume patch and `deform.hinge_blended`, so a
    hinge one of them refuses is no longer read as 0.0 blended by the other.
- **`secondary_chains.py`.**
  - **Hip bag (`bagL`, `bagR`):** the back-bag rule turned 90° onto the lateral profile. It takes
    one bone hung from the hips or the spine. A side bulge taller than 0.25 H (a cape's edge) is
    refused.
  - **Crown rule for hair:** a cluster whose outer envelope is a smooth dome is a cap's or a
    helmet's crown, rigid on Head.
  - **Skirt route:** a back bulge mostly of the skirt's own skin is its drape, not a bag. A cape
    (both back sectors reach the hem, neither front one) is chained on its live sectors, each
    half hung from the thigh it hangs behind.
- **`layer_split.py`.**
  - **Props:** a prop whose own fill fails is completed from what shows. A round shield becomes
    its fitted ellipse, its hidden part copied from its mirror images. Any other prop has the
    bands other layers cut through it filled.
  - **Boards:** `--props name@feet=…` puts a board on its own `board` bone (a child of hips),
    with both feet as contacts.
  - **The side view's near arm** is now the arm whose sleeve is drawn over the body.
  - **New gates:** `fill.alone` (a prop fill that kept the character fails), `split.prop_whole`
    and `split.prop_contact`. `rig2d/1` gains an optional `props`.
- **`unity-2d-animation`.**
  - **`RigDriver2D`:** a `board` bone turns on two-bone leg IK, with new `Motion.Push` and
    `Motion.Ollie`, and the readouts `FootMiss`, `SinkBelowGround`, `PushGap` and `BoardLift`.
  - **`AutoRig2D`'s pose gate** adds the ride, five push and five ollie poses, and a contact gate.
    Its attack poses now apply only to prop layers with a side suffix.
  - **`Rig2DLayout`** binds an unsided `prop_<name>` to `board`.
  - A new EditMode test.
- **On the guard.**
  - **Before:** the left arm was refused as vertical, then `markers.symmetry` was 0.082, then `markers.limb_ratio` failed (the leg
    0.80), then the fist folded the fingers into the shield (self-intersection 0.234, p95 0.205).
  - **Now:** markers pass (symmetry 0.012, leg 1.0), and the shield's 2,589 vertices ride
    `hand.l`. The fist reads 0.076 and p95 0.0805 against a limit of 0.08.
  - **Secondary:** the helmet is a crown, the cape's drape is no longer a back bag (0.735 of it
    skirt skin), and the cape gets `hemBL` and `hemBR` with every secondary gate green.
  - `all --body skirt` still stops at deform, on `self_intersection_p95` 0.0805 and `skirt_tear`
    0.00209 (limit 0.002). Both come from rigid plates folding over cloth at the elbows and
    shoulders, which the repair ladder does not handle. No limit was widened.
- **On the mascot.** Without its marker file the detector now gives 12 chains: the hip satchel as
  `bagR`, five hem chains and six shorts chains. The five cap "hair" spikes are rejected as
  crowns. With the marker file it gives the same 11 as 0.42.2.
- **On the gatekeeper.** Four runs of four pass (0.42.2: three).
  - **`fist`:** 0.039–0.055 (was 0.054–0.078).
  - **Final p95:** 0.0754–0.0757 (was 0.0752–0.0815).
  - **Hem chains:** six each.
  - **Elbow volume after repair:** 0.275 against the 0.35 limit (was 0.250).
- **On the courier runner.**
  - **`fine`:** exits 0 with the same 12 chains (p95 0.071 → 0.072).
  - **The ship track:** exits 0 (p95 0.030 → 0.027) with 18 chains, not 19. The bag now covers
    0.274 of the back-left hem sector, past the 0.25 limit (it was 0.246). `fine` has never had
    that chain (0.274–0.28), so the ship now matches it.
- **Rig exam against 0.42.2.**
  - **`heavy`:** true fail → true pass (worst joint 0.066 H pelvis → 0.033 H shoulder; hip
    0.066 → 0.018).
  - **The accepted runner:** false fail (`markers.windows`) → true pass, though its pelvis is now
    0.017 H off the accepted position (was 0.006).
  - **All bodies:** joints p50 / p95 0.0136 / 0.0365 → 0.0091 / 0.0286; fingers p95
    0.033 → 0.018.
  - All 38 planted faults are caught, the five controls pass, and there is no false pass.
- **README, in four languages.** Two new showcases: the long-coat sentry before and after the skirt
  route with the chibi mascot's poses (`coat.jpg`, `chibi.jpg`), and the 2D guard's pole and shield
  with the courier's push and ollie (`guard.gif`, `skate.gif`). Two "Try asking" rows, SciPy listed
  for `comfyui-asset-generation`'s part, layer and scene scripts, the hip bag, coat hem and cape
  among the chains, the script counts, and four skill rows brought up to date.
- **Still open.**
  - **The guard's deform:** plates over cloth at the elbows and shoulders, outside the repair
    ladder.
  - **`spiky_hair`'s fingers** now read `fixed` (`fingers_right` 10 → 9). The shoulder rule moved
    its wrist 3 mm, and that drew another sample set. Denser sampling restores it, but it reads
    four fingers on the accepted runner's closed hand, so it was not taken. The finger read needs
    a vote over several samplings.
  - **Thin margins:** the crown rule (real hair spikes from 0.343, crowns to 0.150, two fine-runner
    candidates at 0.175 / 0.206) and the prep centring (0.0073 H on `asym` against the 0.01 H
    rule). Heavy's shoulder is 0.033 H against a 0.04 H tolerance.
  - **2D:** the deck under each shoe is not completed (a 5–9 px notch when a foot lifts), the
    shorts' hem opens on big thigh swings (ollie holes 590 against a limit of 739), and there is
    no front view of the board rider.

## 0.42.2

A strengthening round from a third character, a chibi courier mascot (a head a third of its
height, short thick limbs, mitten gloves, a satchel), from the gatekeeper's runs and from a 2D
street-guard enemy holding a pole and a shield. A chibi now has its own route through the rig
instead of the hand-built fallback, a mitten bends as one piece, a hand no longer drags a coat,
and in 2D a held prop is a layer of its own that rides its hand through a new attack.

- **`character-autorig`: the chibi route (`autorig.py all --body chibi`).** Chosen by a person at
  G0 (`game-character-pipeline` routes and start gate gain the row); the gates' limits are the
  same, the bands and windows follow the body type, and an adult body on this route fails them.
  - **`mesh_check.py --body chibi`.** The crotch is searched from 0.10 H, `legs_separated` reads
    0.06 H up to under it and `arms_separated` 0.35–0.65 H. Fused legs still fail.
  - **`arp_markers.py --body chibi`.** Its own windows (shoulder 0.45–0.72 H, neck 0.50–0.78 H, …)
    and arm ratios; the hip is the crotch plus the leg's half-width, the shoulder sits at the
    torso's edge, the ankle where a big shoe starts, and the neck and head base split the short
    neck in thirds.
  - **`deform_gate.py --body chibi`.** `arms_up` stops 45° from vertical and `elbow_120` bends
    90°: past that the mittens enter the head and a thick forearm meets the upper arm.
  - **Short thick hinges.** An elbow or knee whose patch holds fewer than 8 triangles reaches 1.25 ×
    the nearest skin, but only when that skin sits around the joint (an opening at the joint
    stays unmeasured); one whose patch does not wrap (a shorts hem's lining) keeps the limb's own
    skin within 1.3 × its radius.
- **Mittens.** Fingers count only where the hand's surface cuts into four loops (`hand_loops`),
  so a mitten no longer reads as four fingers. `mitten_bind` (contract stage) folds Index, Ring
  and Little onto Middle; a new `mitten` pose (Middle 40°, the thumb 20°) replaces `fist` and adds
  `deform.mitten_tear`. `smart.fingers` failing alone on a hand the markers read as `fixed` (the
  AI and the slices agree on a mitten) adds no exit 2 to `all`.
- **`hand_reach`** (arp stage): a hand's or finger's weight farther than 1.0 × the hand's length
  over the skin is removed, and the FBX exported again (`arp.hand_reach_export`): a thumb tip held
  the gatekeeper's coat back 0.4 m away, so a fist dragged the coat.
- **The elbow and knee repair** measures its bands along the limb, from the plane square to it at
  the joint (a world-Z band cut a sloping arm on a slant); the amounts go 1.0 → 0.8 → 0.6.
- **`markers.limb_ratio`**: a thigh shorter than 0.85 × the shin fails (a hip read low at a heavy
  body's crotch); the arm and the upper bound stay 0.5–2.0.
- **`secondary_chains.py`.** The hem's sectors and each leg's shorts chains share one ring's
  skin, so no sector is dropped and the regions mirror.
- **Rig exam.** The `chibi` body is rigged on its route; a new planted fault, `mitten_split` (the
  mitten back on four strips), is expected at `deform.mitten_tear`; `faults` re-measures a base's
  markers on its own body route and gates it with the base's poses.
- **`layer_split.py`: held props.** `fills --props "pole=…;shield=…"` (one `noprop_<name>` and one
  `prop_<name>` fill per prop, a thin prop painted out along its track when the edit re-poses the
  arm) makes each prop the layer `prop_<name>_<side>`, bound to a hand (`name@near|far|R|L` to
  choose) and stacked where it recomposites best; `--only` redoes single fills, `split --far-arm
  hidden` gives a shielded far arm bones but no layers. New gates `split.prop_layer`,
  `split.sleeve_own` (an armband is kept, not painted out) and `split.head_pivot` (the head pivots
  at the bottom of the neck skin and carries its chin). An arm held out level is cut too.
- **`scene_layers.py`: `scene.ground_split`.** Shopfronts and road returned as one layer are cut
  at the top of the flat ground band (`--no-ground-cut` keeps them whole).
- **`unity-2d-animation`.** `RigDriver2D` gains `Motion.Attack` (a poke: drawn back, thrust,
  hold, recover, the wrist turned so the prop keeps its angle); `Rig2DLayout` binds a
  `prop_<name>_X` layer to `wrist_X`; `AutoRig2D`'s pose gate adds the attack's draw-back and hit
  when a prop layer exists and checks only joints with art on both sides. A new EditMode test.
- **`codex-visual` → `layered-2d-source.md`.** How to draw a held prop (out in front at chest
  height; a prop held at the hip pulls the arm onto the body) and the street-guard brief.
- **On the mascot.** The default rules refuse it (legs 0.81, arms 0.01; hip, shoulder and neck
  outside their windows); on the chibi route every stage passes. Deform before the chibi poses
  and hinge readings: `arms_up` 0.189, `elbow_120` 0.140, the knee unmeasured; after: volume loss
  0.049, self-intersection p95 0.043, the knee read. `mitten_tear` 0.0024 on the plain bind → 0
  (worst edge 4–5 × → under 1.9 ×). `autorig.py all` exits 0 (was 2 on `smart.fingers`).
- **On the gatekeeper.** `hand_reach` cleans 1,600–2,300 vertices a run; on one rig `fist` 0.111
  → 0.059 and p95 0.098 → 0.068. Four runs: three pass (repair at 0.8, p95 0.075), one exhausts
  the ladder (p95 0.082) where the AI's finger placement curls the fingertips into the palm; on
  0.42.1 the run stopped at deform.
- **On the street guard.** The 0.42.1 split failed it (recomposite IoU 0.773); all 13 gates now
  pass (IoU 0.998), the props left drawn in the body (shield 0.999, pole 0.729) → 0.001, and in Unity 16/16 layers rig
  with every pose inside its hole limit.
- **On the courier runner.** `fine` and the ship track exit 0 with the same chains (ship p95
  0.036 → 0.030, 198 vertices cleaned by `hand_reach`); the head pivot goes from the chin to the
  neck (0.11 / 0.28 → 1.43 / 1.24 eye-to-mouth distances under the mouth); EditMode 12/12.
- **Rig exam** against 0.42.1: `chibi` expected fail → true pass (worst joint 0.30 H → 0.016 H),
  `heavy` false pass → true fail (`markers.limb_ratio`, its thigh 0.79 × the shin), joints p95
  0.065 → 0.037; the other bodies read as before. All 38 planted faults are caught (16 on the new
  chibi and mitten bases) and the five controls pass.
- **Still open.** One gatekeeper run in four fails `fist` after the repair; the heavy body's hip
  and shoulder are still placed wrong (now caught); a hip satchel is not found by the bag
  detector and a cap's crown can read as hair (a marker file covers both); in 2D the shield's
  part hidden under the near arm is missing, so a thin gap shows in the attack.

## 0.42.1

A strengthening round, from an end-to-end run on a second character (a gatekeeper in a
knee-length greatcoat with a ponytail and a peaked cap) and from the 0.42 2D showcase. A long
coat, a skirt or a robe now has a route through the rig instead of being sent back to the
drawing. Look-alikes no longer become spring chains, a ponytail can be one, and a collar fused to
the jaw no longer breaks the head part. In 2D, the background slivers in a crouch, the strap cut
out with the sleeve, the hidden open mouth and the one-prop street are fixed, each with a gate
that fails on the 0.42 output.

- **`character-autorig`: the skirt route (`autorig.py all --body skirt`).** A person chooses it at
  G0 (`game-character-pipeline` routes and start gate gain the row); the default body reports
  `skirt_hint` when it sees a hem instead of a crotch.
  - **`mesh_check.py --body skirt`.** The first cut across the midline is the hem; the legs are
    read under it, a new `skirt_hem` gate needs ≥ 0.08 H of leg showing (a floor-length robe
    fails: the hand-built route), and `double_shell` is gated outside the skirt zone, the zone's
    own share reported as `skirt.layer` (a coat over trousers is two sheets by design).
  - **`arp_markers.py --body skirt`.** Each leg is followed up inside the skirt on the cut's own
    loops. A crotch found there places the hip as in trousers; a hidden one places it at 1.86 ×
    the knee's height. A knee cue at the hem's lip or outside 40–65 % of the way (a boot top) is
    refused. The markers carry `body` and a `skirt` block, which `skirt_region` turns into the
    skirt's own skin for the three readers below.
  - **`skirt_bind`** (a contract-stage step): the skirt's skin goes to Hips and both thighs, the
    thighs rising to 0.85 at the hem and blended left to right across twice the hip width, so no
    seam runs between the thighs; then the FBX is exported again.
  - **`deform_gate.py --skirt`: `deform.skirt_tear`.** The share of the skirt's outward edges
    stretched past 3 × in any sample, ≤ 0.002. A coat on the plain bind tears between the thighs
    in `leg_raise` while volume and self-intersection stay green. The leg joints' volume patches
    leave the skirt out.
  - **`secondary_chains.py --skirt`.** Up to six two-bone hem chains wherever the hem hangs, each
    hung from the thigh that holds most of its skin and taking its share from that thigh first;
    no shorts hem is searched under a skirt. The four-influence limit merges only chains on the
    same parent, so a pose moves the skirt as the bind did.
  - **Rig exam.** The `skirt` body is rigged on the route, and a new planted fault, `skirt_split`
    (the skirt split at the midline onto each side's thigh), is expected at `deform.skirt_tear`.
- **`secondary_chains.py`: look-alikes are no chains.** A back component spanning more than 180°
  round the spine line wraps the body (a belt against a vented coat back); a hood narrower than
  0.12 H or a bag narrower than 0.08 H is hair or a strap; a hair cluster whose sides face one
  way is a plate (a cap brim); a shorts drop on one leg alone is a hem. Each rule has a
  counterexample in the selftest that is found as the kind it mimics with the rule off. A `hair`
  marker chain (a ponytail) may skin the neck and back, hangs from Head and gets the Back sphere
  when it hangs below the neck.
- **`blender-character-rig` → `part_math.py plan`: a covered neck and hanging hair.** A neck ring
  that goes on below the band no wider, with loops nested in it (a stand collar fused to the
  jaw), is reported as `anchor.neck.covered` with a warning: the seam goes under the collar, the
  column is dropped from the keep masks without growing (grown, it took the mouth), and the side
  views put the neck on the nape. Hair hanging below the cut outside the neck (a ponytail) is
  kept in the head views (`views.hanging`, `hang_<view>.png`).
- **`comfyui-asset-generation` → `part_views.py`.** `prompt_hint_back` is the back view's own
  hint (a cap's band, a ponytail); a view that keeps hanging hair is told to keep it over the
  neck. **`--accept VIEW:SEED --accepted-by NAME`**: a person signs off a near miss already
  redrawn from the same guide (within fixed near-miss limits, recorded in `views.accepted` with
  the redraw's hash); the gates keep `pass: false` with `accepted`, and a farther miss is
  refused. `schemas/parts-1.json` gains these fields.
- **`layer_split.py`.** The meshes cover every solid pixel (dropped triangles given back, corner
  vertices added): new gate `split.mesh_cover` (0 pixels left out). `sleeve_fill` repaints what
  lies over the sleeve and is not sleeve (a strap, a buckle, drawstrings), gated at ≤ 0.25 of the
  arm (`split.sleeve_fill`). The torso is cut back from the eyes and mouth, gated by
  `split.swap_visible` (≥ 0.9 of each swap's change still shows); `fill.changed` catches a fill
  that changed nothing.
- **`scene_layers.py`: `scene.props_whole`** (≥ 2 props clear of the frame), so Shuffle has more
  than one prop to deal.
- **`unity-2d-animation` → `AutoRig2D.cs`.** A rig file's mesh must cover 99.95 % of its layer
  (pixel centres, no slack; was 98 % within one pixel). A new pose gate skins the prefab on the
  CPU in the standard poses: no solid pixel undrawn at rest, no seam opening at a bending joint,
  every limb joint covered. Two new EditMode tests: a rig-file layer with no sprite is a problem,
  and the pose gate passes the rig and catches a mesh with triangles cut out.
  `auto-rig-2d.md` says to frame a run capture on the whole cycle, not the rest pose.
- **On the gatekeeper.** mesh_check: `legs_separated` 0.731 → 1.0, `double_shell` 0.252 → 0.161,
  hem at 0.315 H. Markers: the hip read at the hem (0.335 H, outside its window) → the crotch
  found inside the coat at 0.465 H, hip 0.485 H. Deform: `skirt_tear` 0.0045 on the plain bind
  (25 edges over 3 × in `leg_raise`, worst 5.1 ×) → 0, deep squat's worst edge 1.7 ×;
  `cross_side_weight` 0.035 → 0.013 with no bone holding the other side. Six hem chains found
  where none were, and six false chains (bag, hood, cap brim, three shorts) gone. The head part's
  front view passes on default settings and the back with its own hint; the profiles are near
  misses for a person to sign off.
- **On the courier runner.** The detectors find exactly the chains they found before, the head
  plan is identical, and the 2D split leaves 0 uncovered pixels (was 3,467 front, 2,879 side); in
  Unity the open mouth changes 1,093 px against the closed one (was 172); EditMode 11/11 (the
  auto-rig). `fine` and the ship track both exit 0 with the same chains. Their deformation
  readings move only where the AI's own markers moved between runs: on `fine` the face (body
  markers identical; `jaw_open` takes self-intersection p95 from 0.067 to 0.072), on the ship
  track the elbows and fingers by up to 4 mm (volume loss 0.304 → 0.310, p95 0.034 → 0.036).
- **Rig exam.** The `skirt` body goes from a true fail (hip 0.10 H off, read at the hem) to a
  true pass (hip and pelvis 0.02 H off); the other eight bodies and the reference read exactly as
  before. All 22 planted faults are caught (eight on the new skirt base) and the three controls
  pass.
- **Still open.** On the gatekeeper the skirt route is clean in every run (no tear, no other
  side's skin held), but the elbow passes its volume gate only through the repair, which raises
  `elbow_120`'s self-intersection from 0.074 to 0.104; with the AI's finger placement in
  `fist` varying between runs, `self_intersection_p95` lands either side of 0.08, so some runs stop
  at deform. The limit is unchanged.

## 0.42.0

Layered 2D characters and scenes. A drawing of a character becomes a PSB with one layer per
moving part, the parts it hides filled in, and Unity's 2D Animation rigs it with bones, meshes and
weights and no Skinning Editor step; the face swaps, idle, blink, talk and a side-view run come with
it. A scene becomes parallax depth layers that scroll endlessly without a prop beside its own copy.
The same layers are written as a PSD ready for Live2D Cubism, which a person rigs in Cubism Editor
under Live2D's own licence; nothing of Live2D's is downloaded or redistributed.

- **`comfyui-asset-generation` → `layer_split.py`.** `fills` makes the hidden parts with
  Qwen-Image-Edit-2511 (`templates/qwen_image_edit_2511_fill_api.json`, 4-step Lightning): an
  armless torso, a bald head, eyes closed, mouth open and, with `--cubism`, a blank face, each from
  a square-padded crop of the source and never from another edit, gated on alignment, silhouette
  and staying inside the source, with a seed retry. `split` cuts by geometry, not by a part map:
  neck, crotch, hem, ankles and armpits from the silhouettes, each arm a capsule from its shoulder
  joint, the wrist at the narrowest section. Where an arm hid the torso's side, the torso is
  bridged, rounded and outlined, so a raised arm no longer shows a straight shoulder edge. A side
  view (`--view side --facing right|left`, sides `near` / `far`) puts the shoulder where the arms'
  axes meet and sweeps the far arm on under the torso. It writes the layer PNGs, `rig2d.json`,
  `debug.png`, `pose.png` and the PSB, and gates the composite (IoU, pixels off), interior
  semi-transparency, joint overlap, the layer names, the limbs and `split.shoulder_notch`.
- **`psd_write.py`.** PSD and PSB, 8-bit RGB with transparency, PackBits, `luni`, `lyid`, groups,
  hidden layers and a merged composite, from Adobe's specification; ids kept by name in `ids.json`
  so a repaint keeps every sprite id in Unity. `read` prints the tree; the selftest reads its
  output back, and with psd-tools (MIT, optional) when it is installed.
- **`cubism_psd.py`.** The Cubism-ready PSD: the face split on the 1024 px head crops (blank face,
  eye white, iris and lash per side, brows, nose, mouth line, the inside of the mouth hidden in a
  folder), the body layers in depth folders; gates the composite, the 100-layer cap of the FREE
  edition, unique names, version 1, 8 bit, RGB.
- **`scene_layers.py`.** Qwen-Image-Layered (`templates/qwen_image_layered_api.json`, the
  official graph) splits a scene by depth; a layer with a transparent band is cut in two (sky and
  road), the front layer's props are also written one by one, and `--scroll` writes each layer's
  parallax speed into `scene.json`. Gates recomposite, coverage, interior semi-transparency and
  depth order. The server inventory gains the fp8mixed weights and the layered VAE (Apache-2.0).
- **`unity-2d-animation` → `AutoRig2D.cs`, `Rig2DLayout.cs`, `RigDriver2D.cs`.** Reads
  `rig2d.json` (`rig2d/1`, `schemas/rig2d-1.json`) beside the PSB, or infers the bones from the
  layer names alone, and writes the skeleton, each part's bones and its mesh and weights through
  the data providers, then `Apply()` and a reimport. Bones are named after joints so the importer
  never renames one; GUIDs are a hash of the name, so a re-run keeps every binding and a hand rig
  is left alone unless overwritten. A rig-file mesh that covers less than 98 % of its layer is
  replaced by a grid. It builds `<name>_Faces.spriteLib` and a Prefab Variant with resolvers and
  `RigDriver2D` (idle, blink, talk at 8 Hz, a front run in place, a side run with the legs in
  opposite phase, 2D springs on the hair). Gates: every layer rigged, weights summing to 1, every
  `SpriteSkin` ready, and every layer the rig file names back as a sprite. Batch:
  `-executeMethod UnityDev.Rig2D.AutoRig2D.RunFromCommandLine`, with graphics. A renamed layer loses
  its rig, and a PSB re-split over its old `.meta` can tear; both are documented with the fix.
- **`reference/live2d-import.md`.** The Cubism route without promising automation past the PSD:
  the Editor's own manual rules for the PSD, the SDK for Unity installed by each developer from
  Live2D, blink and lip sync components, the standard parameter IDs, and the licences: never
  vendor the SDK, read Live2D's SDK licence page before release, and buy the licence a project
  needs.
- **`unity-2d-rendering` → `ParallaxTiles.cs`, `TileSequence.cs`, `ParallaxRigBuilder.cs`,
  `PsdLayerReader.cs`.** One prefab from `scene.json` (or the layers read by name from the PSD):
  a `ParallaxLayer` per layer, factor 1 − scroll, and tiles that are a function of the seed and
  the tile index, so a respawn or walking back shows the same art. Mirror for continuous strips,
  Repeat, and Shuffle for props: one per tile from a seeded bag, never twice in a row, with seeded
  gaps; props cut by the canvas edge are left out. Batch:
  `-executeMethod UnityDev.Rendering2D.ParallaxRigBuilder.BuildFromCommandLine`.
- **`codex-visual` → `reference/layered-2d-source.md`.** How to draw a front or side character
  and a scene for cutting: limbs apart, neutral face, a flat key, the canvas padded square for the
  edits.
- **Tools.** `unity-compile-check.sh` adds the PSD Importer to its package set;
  `check-contracts.py` knows `.rig2d.json`; four selftests and four usage probes.
- **On the courier runner.** A front and a side view and a street, all fills passing on the
  first seed (alignment p75 3.1–10.0, silhouette IoU ≥ 0.989). The split: composite IoU 0.9988 /
  0.9978, pixels off 0.0004 / 0.0021, interior semi-transparency 0.0078 / 0.0067, 22 px joint
  overlap, shoulder notch 0.00001 / 0.0004; both PSBs read back by psd-tools pixel for pixel. The
  Cubism PSD: 23 layers, IoU 0.9988. In Unity, from a fresh import: 16/16 layers rigged per view
  from the rig file's own meshes, 0 bad weights, 16/16 skins ready; EditMode 42/42 (the auto-rig
  9, the parallax 33). The street: sky, road, skyline, shops and props, recomposite 4.65,
  coverage 1.0, depth order 0.828; built from the PSD or the PNGs, the tiles match pixel for pixel.
## 0.41.2

A strengthening round. On the ship track the elbow no longer needs a repair: its marker follows
the wrist the AI places. Weight that crosses the midline (a sole bound to the other foot) is now
repaired. Hand paint can refuse a colour the concept never has. A shorts hem no longer shows
inside its own thigh, and a red mouth is no longer split off as hair. An end-to-end run on a new
character (a long-coated gatekeeper) turned up two script bugs and two missing runner flags; all
four are fixed here.

- **`character-autorig` → `arp_markers.py`: the elbow follows the wrist.** A proportion elbow
  sits at 0.42 / 0.75 of shoulder → wrist, wherever the wrist lands: on a narrowing found by the
  slices, or on the AI's wrist with `--smart`. An adjusted elbow stays where it was put. The AI
  places the wrist where the hand leaves the forearm (about 0.67 of shoulder → hand tip). The elbow
  used to stay at 0.42 of shoulder → hand tip, which made the forearm about a quarter short (limb
  ratio 1.68–1.83), and the elbow gate measured that short span. The gate and its 0.35 limit are
  unchanged. Results:
  - The ship rig reused from the same AI output reads 0.305 at the elbow without a repair. Before,
    it read 0.479 and needed a repair.
  - Six whole-runner reruns read 0.305–0.312, all passing without a repair. Before, they read
    0.36–0.44: four ran out of rungs and two passed after a repair.
  - Fresh full runs: ship ×3 at 0.298–0.306 and whole ×3 at 0.305–0.308, all exit 0.
  - On a proportion wrist the elbow lands where it did before, so the rig exam is unchanged.
- **The repair ladder moves weight across the midline.** `deform_gate.py`'s
  `skin.cross_side.{L,R}.bones` names the other side's bones that hold each side's skin, with their
  summed weight. When `deform.cross_side_weight` fails, alone or together with a hinge volume loss,
  `autorig.py` adds a cross-side move to the attempt. Past the gate's band from the midline (faded
  in from half of it), each named bone's weight goes in full to its mirrored twin (`brt_weights`
  transfer, share `reach`, so the bone keeps its own side's skin). If the gate still fails after
  the move, the ladder stops for a rebind. Tested on two cases:
  - On the 0.41.0 ship rig (the right sole on `foot.l`/`toes_01.l`): share 0.0144 with 336 vertices
    held went to 0 / 0. Volume stayed at 0.278, and self-intersection p95 fell from 0.054 to 0.028.
  - On the exam's planted `leg_smear`: 0.1436 / 1488 went to 0 / 0.
  This replaces 0.41.1's "a repair never moves weight across the midline".
- **`arp_markers.py --adjust`: the spine follows an adjusted pelvis.** The proportion spine points
  now move with an adjusted `pelvis` or `neck_base`, each by its share of how far both ends moved.
  Before, they stayed at the old proportions, so a raised pelvis turned `root_ref` upside down
  while every gate passed. A spine point the person adjusts stays where it was put.
- **`autorig.py`: `markers --adjust FILE` and `arp --resolution N`** (both also on `all`). These
  pass through to `arp_markers.py --adjust` and to the bind's resolution (brt_arp), so both manual
  rungs the ladder names can be run through the runner. Its message now names them.
- **`secondary_chains.py`: a hand-placed `hair` chain no longer crashes.** The colliders took the
  head centre from a hair chain that only detected chains have (`KeyError: 'centre'`). A marker
  chain along a ponytail now runs the full stage.
- **`mesh-texture-paint` → `paint_loop.py`: off-palette colours, measured and gateable.**
  - **What it measures:** the share of the figure whose colour is more than 15 from every colour in
    the concept views. The comparison is in Lab, with a and b scaled up in dark colours so a navy
    is not "near black", after a 2 px opening. Each view records it as `off_palette`, and a try
    over 1.5 % leaves `_offpal.png` with the flagged colours in magenta. `--seed` sets the first
    seed.
  - **Where it is a gate:** only when `--max-off-palette` is set. The parts route
    (`hand_views.py --paint`, heads and hands) sets 0.03. On the earlier hand and head views,
    clean views read 0–0.014 and navy or silver ones 0.05–0.52.
  - **Why it is off by default:** an offline replay of earlier runs gave these readings:
    - The accepted runner anchor's views: at most 0.007.
    - The gatekeeper's two back views: 0.033 and 0.034, from the ponytail's sheen plus one real
      teal smudge.
    - Backpack and racket runs: 25–40 % of the views they used were over 0.03 (an olive flap, a
      navy grip band).

    The replay compares raw outputs, not the warped view the gate reads. No live run has measured
    what the lost views cost in coverage.
  - **Live hand runs with the gate:** the left hand's navy palm is gone, at coverage 0.68–0.70.
    On the right hand the silver first view was correctly refused, but coverage fell from 0.77 to
    0.29 on one seed, and on another seed every try was refused.
  - **A part with no painted view:** it now keeps its generated texture, with a warning, and the
    plan records `generated.paint {status "unpainted"}`. Before, the whole generate step stopped
    with exit 3.
- **`unity-rigged-character` → `SpringChain.Write`: written bones stay outside the colliders.**
  A drawn bone follows a segment up to one substep old, while its colliders are already at this
  frame's pose. Before drawing, a tip that would sit inside one of the chain's colliders is pushed
  out, keeping its length. The particles are untouched. In the runner's Unity capture, shorts-hem
  collisions fell from 18–103 per rate to 0 at 10–144 fps and jittered, and the front hem's sink
  fell from 2.7 to 1.9 cm (its rest distance). A new EditMode test with a hem beside a swinging
  thigh fails on the old code and passes now (13/13).
- **`blender-character-rig` → `part_math.split_hair`: the face is never hair.** Faces within 35° of
  the front and below 0.45 of chin → top stay on the head whatever their colour. On the runner, 83
  mouth faces that had gone to the hair go to 0, and every hair gate stays green.
- **Docs:** `image-to-3d.md` says views cut from a turnaround sheet are scaled up to 1024 by
  `turnaround_to_views.py`, and that this is expected.
- **On the courier runner, end to end.**
  - `fine` exits 0 with the same deformation readings as 0.41.1: volume loss 0.296,
    self-intersection p95 0.067, cross side 0 / 0, hinge blend 0.13. The hair splits at 49,621 faces
    (50,298 before) with every hair gate green.
  - The ship track exits 0 and passes the elbow gate first time at 0.304, with limb ratio 1.27.
    In 0.41.1 it read 0.479, needed a repair, and had limb ratio 1.68.
  - The rig exam reads the same as 0.41.1 on every body, on the reference and on every planted
    fault: all 14 faults are caught and both controls pass.

## 0.41.1

A strengthening round. Four defects the rig exam planted used to pass every gate; each now has a
gate that reads it without a pose. The hood no longer sinks into the back and the bag's lower
edge no longer stretches at a lane change. The ship mesh gets its eyeballs back, the split hair
comes down to its triangle share, and the smart stage keeps a steadier AI guess.

- **`character-autorig` → `deform_gate.py`: two readings of the bind at rest.**
  `deform.cross_side_weight`: away from the midline (half the hip half-width from the Hips), the
  share of a side's limb weight held by the other side's limb bones ≤ 0.05 (`--cross-side-max`) and
  no vertex held ≥ 0.5 by the other side (`held` 0); twist bones count with their limb, `cc_`
  chains with none. `deform.hinge_blended`: at each elbow and knee, the share of nearby vertices
  both bones hold ≥ 0.1 of, the least ≥ 0.03 (`--hinge-blend-min`); no hinge to read fails. The
  report gains `skin`. The repair ladder never moves weight across the midline: a failed
  cross-side reading stops the run for a rebind.
- **`arp_markers.py`: `markers.limb_ratio`** (upper over lower segment of each arm and leg inside
  0.5–2.0, set from anatomy) and **`markers.finger_lengths`** (the shortest phalanx ≥ 0.01 ×
  wrist → hand tip), adjusted and AI markers included.
- **The rig exam** expects the gate that catches each fault. On the standard body and the accepted
  runner, all 14 planted faults are caught by their expected gate (before: `leg_smear`, `rigid`,
  `finger_collapse` and `elbow_shift` slipped on the standard body, two of them on the runner too);
  both controls pass; the nine bodies and the reference keep their outcomes and joint errors
  (p50 0.0174 H, p95 0.0656 H). On the controls the new readings sit far from their limits (cross
  side ≤ 0.0001 and 0 held, hinge blend ≥ 0.11, limb ratio 0.67–1.27 on the cast, phalanx ≥ 0.024).
- **`secondary_chains.py`.** The hood loses the torso capsules it rests inside, so it gets a `Back`
  sphere (radius 0.5 H on UpperChest, centre in front, its surface just under the rest joints;
  `colliders.added`): in the Unity capture its sink into the back fell from 4.5–6.1 cm to
  0.4–1.2 cm across 10–144 fps. The bag's share fades smoothly from 0.012 H outside its bulge to
  0.04 H inside (it was a step): the worst edge stretch at the lane change fell from 9.17 to 2.43
  (p99 4.08 → 1.76). The bag now swings visibly less: most of it carries 0.4–0.8 of its bone.
- **`blender-character-rig` → `ship_merge.py --eyes`.** The ship mesh merges from `<c>_parts.glb`
  (the file `eye_fit.py fit` edited) with `--eyes <c>_eyes.glb`: the balls take atlas tiles, stay
  `Eye.L`/`Eye.R` with their extras, go to `<c>_ship_eyes.glb` (gate `ship.eyes`) and bind to the eye
  bones with `autorig.py all … --eyes … --facial`; `--eyes` with a `.blend`, and a fitted parts GLB
  without `--eyes`, are refused. `eye_fit.py bind` drops the import's copy of the atlas material,
  so in Unity the body is one renderer, one sub-mesh, one material and each eye a renderer with that
  same material. With the eye tiles in a 4096 atlas the hand tiles drop to 1024 (density still 0.5).
- **`assemble_parts.py`: the hair to its share.** The split hair is welded, then collapse-decimated
  to `part_math.hair_target` before the rig (share over the other built parts' shares × their
  triangles, so it stays under its share once the hands join); gates `hair.reduce.tears` and
  `hair.reduce.silhouette` (≥ 0.95), both provisional (the tear gate counts open edges);
  `--keep-hair-tris` skips it. On the courier runner: 50,298 → 14,126 triangles, open edges
  1,356 → 1,086, silhouette 0.98. A collapse only tears the UV seams of an unwelded import; the docs
  that said it always tears are corrected.
- **`arp_smart.py`: steadier guesses.** The body guess runs `--body-runs` (3) and the finger guess
  `--finger-runs` (5) times; per marker (body) and per finger the run nearest the median is put
  back. The worst finger disagreement between whole runs fell from 21.8 to 10.7 mm and the wrist's
  from 6.7 to 3.0 mm, for about 24 s more. A later guess that fails keeps the good ones and is
  reported; a finger guess that takes the markers with it is followed by one more (both guarded,
  not yet seen in a run). In nine full runs the fist never failed: the occasional failure was the
  left elbow's volume at 120° (0.35–0.43 first, then a repair failing self-intersection) where the
  AI's wrist is taken, and it stays (about one run in three before and after).
- **`mesh-texture-paint`, hands.** `hand_views.py --paint` paints with `--prior ''` (the nearest
  painted colour as context, not the hand job's own bake, whose grey forearm streaks and olive palm
  the model continued), and after a rejected next-best view the next keeps 35° away from it. Both
  palms now read black as in the concept; the evidence is mixed (left painted share 0.71 → 0.78,
  right 0.85 → 0.77, one seed each) and a gate on the paint's colours against the concept is still
  missing.
- **On the courier runner, end to end.** `fine` (assemble, hands, `eye_fit.py fit`, `autorig.py all
  --hair --eyes --facial`) exits 0 with the deformation gate passing first time (volume loss 0.296,
  self-intersection p95 0.063, cross side 0 and 0 held, hinge blend 0.13; limb ratio 1.27 / 1.03),
  three body and five finger guesses (spread 8.6 / 5.7 mm). The ship track (`ship --eyes`, one rig
  with the eyes) exits 0: one material, both eyes bound to their bones; its elbow read 0.48 first
  and passed after one repair (0.12), the AI wrist's limb ratio 1.68.

## 0.41.0

Tier `fine`: hands and eyeballs of their own, and the ship merge. A whole-body job fuses the
fingers and paints the eyes on a flat surface, so the fist pose has nothing to curl and the eyes
cannot turn. `fine` generates each hand as its own part and sets it into the sleeve, puts a ball
behind each painted eye and binds it to the face rig's eye bone. For the ship track, the parts now
merge into one mesh, one material and one atlas per map before the rig. The neck seam of `three`
no longer shows a pale stump edge in an open hood.

- **The parts plan.** `fine` is built: `three` plus either hand or both. Eyeballs come from
  `eye_fit.py` after the assembly, not from a plan part; `eyes` and `accessory` parts are refused,
  and `custom` stays reserved. `part_math.py plan --tier fine` measures both forearms
  through `blender-character-rig` → `hand_parts.py plan_hands`: the forearm axis from tracked
  sections, the wrist plane fitted through the cuff's lip in 16 sectors (an angled cuff keeps its
  whole edge), the part's flat bottom 1.8 forearm radii inside the sleeve, crop boxes and keep
  masks; the view the body hides is the mirror of the opposite side view. `parts/1` gains `wrist`,
  `views.hidden`, `seam.depth_r_fore` and `generated.attempts`.
- **`comfyui-asset-generation` → `hand_views.py`** (through `part_views.py`, whose `--part` now
  takes a list). The hand guide paints the forearm the sleeve hid as a cylinder ending flat at the
  bottom plane; the redraw asks for black gaps between the fingers; the gates are bands around the
  guide's silhouette (`part.redraw_inside`, `redraw_cover`, `redraw_colour` by whole cells,
  `sharpness`), not IoU, which the dropped cloth between the fingers would fail. `generate` makes
  each hand at `--hand-ratio` (0.2) × the anchor's triangles, runs `hand_parts.py gate`
  (registration, `hand.fingers`: ≥ 4 sections in ≥ 30 % of 40 slices) and on a failure generates
  again with every seed moved, up to `--hand-seeds`; `--paint` then repaints each part with
  `mesh-texture-paint` (`--kind object`), which brings the glove back from brown to orange.
- **`assemble_parts.py hands`.** Registers each painted hand, cuts it flat at the bottom plane,
  gates the fingers again, removes the anchor's forearm and hand past the wrist plane (keeping the
  sleeve's hem whole) and caps the opening with a fan recessed into the sleeve, its UVs on a free
  block of the body texture painted a lining colour. Gates `hand.triangles`,
  `seam.sleeve_clearance`, `seam.hidden` (eight cameras, four into the cuff); writes
  `<c>.hands.gate.json` and `hands.png`.
- **`blender-character-rig` → `eye_fit.py`.** `fit` (numpy and Pillow, no Blender) finds the
  painted eyes by their sclera, fits a ball behind each (radius 0.55 × the lid width, pushed back
  until the skin around the opening cuts into it by at most the limit), cuts the painted eye out in
  front of it, projects the opening onto the ball and writes `<c>_eyes.glb`; gates `eye.found`,
  `eye.symmetry`, `eye.poke.*`, `eye.rim_gap.*`, `eye.removed.*`, `eye.in_opening.*`. `bind` puts
  each ball on its eye bone with weight 1, moves the mirrored face rig's eye bones (and the lids and
  target pivoting with them) onto the balls, takes the skin's weights off the eye bones, and turns
  each bone ±25° to gate `eyes.follows_bone` and `eyes.poke_turned`.
- **`character-autorig`.** `autorig.py all --eyes <c>_eyes.glb --facial`: the smart stage gives
  the real eyeballs to Auto-Rig Pro's face detection (`arp_smart.py --eyes objects`), and an
  `eyes_bind` step after `parts_bind` binds them before the deformation gate (a failed bind stops
  the run). `contract_map.py` maps `c_eye.l/.r` to the extra roles `Eye.L` / `Eye.R`, Unity's
  LeftEye / RightEye, outside the contract count.
- **`ship_merge.py`** (`assemble_parts.py ship`). Every part's texture becomes a square tile of one
  atlas per map (base colour, normal, ORM), its UVs scaled and offset into the tile without
  rotation or a rebake; tiles halve by texel density until they fit, mirrored pairs together.
  Hair joins the mesh by default, so the ship rig runs without `--hair` and the secondary stage
  still finds the hair spikes. Gates `ship.materials`, `ship.uv_in_tiles`, `ship.density`,
  `ship.triangles` and `ship.tris.<part>` against each part's `budget_share` when a limit is known,
  and `inspect_glb.py`.
- **The neck seam.** The anchor's stump was tucked only where it stood outside the head's neck, so
  in an open hood the two necks, nearly coincident, fought along a ragged line. The stump is now cut
  into rows and pulled to 0.90 of the head's neck along the whole band, coming back out over its
  lowest 35 %; a surface counts as covering an edge only 3 % of the radius outside it, and a collar
  covers only when a fan of rays meets it, not one ray far to the side. The colour match targets
  where the necks now cross.
- **On the courier runner.** The three-tier assembly reproduces with the new seam: 806 stump
  vertices tucked (18 before), largest move 0.199 of the neck radius, `seam.hidden` 0.963,
  `seam.colour` 1.68 ΔE. Hands at 13,544 / 13,264 triangles (limit 13,751): registration
  0.974 / 1.015 scale, 3.7° / 5.3°; `hand.fingers` 0.375 / 0.325 (the anchor's hands 0.05 / 0.0);
  `seam.hidden` 1.0 / 0.999. Eyes: lid gap p90 0.181 / 0.248 radius, the ball seen on 0.999 /
  0.995 of the cut-out pixels. `autorig.py all --hair --eyes --facial`: the AI's body, five
  fingers and all 48 face points; fingers `detected` by the slice markers as well; the deformation
  gate passes first time (volume loss 0.296, self-intersection p95 0.058; the `three` run needed an
  elbow repair); the right eye bone moved 0.42 radius onto its ball; 12 spring chains. In Unity:
  a valid Humanoid avatar with LeftEye, RightEye and Jaw, 30 finger bones, base and normal bound
  on every material, the eyes as their own skinned meshes, 12 spring chains set up. The ship merge:
  5 draw calls → 1, a 4096 atlas with every tile at full size (153k triangles; the hair is 50k of
  them, over its 0.12 share of any limit), rigged once, fingers detected by the slices too, 18 chains with the hair. The
  rig exam's nine bodies and the reference score as in 0.40.0.

## 0.40.0

A character in parts. Image-to-3D spends one job on the whole body, so the face comes out soft and
the hair as one lump. A character whose face the camera comes close to can now take tier `three`:
the whole-body mesh stays the anchor that fixes the proportions, the head is redrawn from the
concept at its own scale and generated as a job of its own, its hair is split off as a third mesh,
and the three are assembled, gated against the anchor and rigged as one character. Tier `whole`
(the demo) is unchanged. The knee marker no longer lands on a shorts hem, and the head's neck
takes the anchor's skin colour at the seam.

- **The parts plan, `parts/1`** (`schemas/parts-1.json`). `blender-character-rig` →
  `part_math.py plan` measures the anchor (neck band, collar, seam heights, head height), fits it
  onto the four clean views (one scale, an offset per view, the silhouette IoU) and writes each
  generated part's crop boxes and keep masks; the hood in front of or behind the neck is removed by
  geometry, never by colour. The plan pins the anchor by hash, and each writer rewrites only its
  own keys. `fine` (hands, eyes, accessories) and `custom` are reserved names the tools refuse.
- **`comfyui-asset-generation` → `part_views.py`.** `views` crops the part from the clean views,
  paints the neck the hood hid as a shaded cylinder, redraws each view sharp with Qwen-Image-Edit
  2511 and Lightning (the guide as both pictures, a prompt of its own for the back of the head),
  gates it (`part.redraw_iou`, `redraw_colour`, `neck_reach`, `neck_width`, `sharpness`, the next
  seed on a failure), removes the background and writes the four views and sheet;
  `generate` runs one Pixal3D multi-view job per part, never `Large` on a part with hair.
  `reference/image-to-3d-parts.md`.
- **`blender-character-rig` → `assemble_parts.py assemble`.** Registers the head onto the anchor
  (trimmed similarity ICP from the crop's scale), splits the hair off by colour and by height above
  a scalp-radius map, cuts the anchor's head away above the neck and seams the two: `overlap` under
  a collar (the head's neck centred on the anchor's and tucked inside its stump), `bridge` without
  one. The head's neck then takes the anchor's skin at the seam: both meshes sampled through their
  UVs on a grid around the neck, the difference added to the head's base colour up to the chin and
  faded out before the face, a second material (a scarf) left alone. Gates `part.register.*`,
  `hair.*`, `head.top_closed`, `part.cut.collar_kept`, `seam.centre`, `seam.tuck`, `seam.hidden`,
  `seam.colour`, `part.coverage.*`, `assembly.silhouette.*` and `assembly.head_extent_ratio`; a
  hair split that fails both tries keeps the hair on the head and exits 2 unless a person accepts
  it. Writes `<c>_rig.glb` (body and head), `<c>_hair.glb`, `<c>_parts.glb`, the gate report and
  `compare.png`, `compare_head.png` and `neck.png` for a person. `reference/part-assembly.md`.
- **`character-autorig` → `autorig.py all --hair`.** The hair GLB is copied beside the prepped
  mesh; after the contract, a `parts_bind` step (`assemble_parts.py bind`) binds it rigidly to the
  contract's Head bone and exports the FBX again, so the first deformation gate, every repair and
  the spring chains already have it (gates `parts.transform_residual`, `parts.hair_bound`; a failed
  bind stops the run before deform). The hair takes the rig's own copy of the head material when the
  images match, so the FBX embeds each texture once. The rig mesh has no hair, so the markers'
  height is the skull top. `secondary_chains.py` finds the separate hair object, never searches the bald scalp for
  hair, and keeps the hair rigid on Head unless `--hair-chains` puts spike chains on that object
  only; `deform_gate.py` gates the mesh weighted to the most bones, not a large hair.
- **The knee marker.** `arp_markers.py` cut the legs at fixed fractions of H, so a change of H or a
  shorts hem moved the knee (on the parts runner it sat on the hem and `deform.joints_measured`
  failed both knees). Each leg is now cut across its own hip → ankle line every 1 % of its length,
  read by girth: a kneecap bulge (further forward than back) at its peak, else the narrowing
  between calf and thigh at its lowest point; a girth step of 10 % or more is a hem and the pinch
  under it is ignored; else 52 % as before. On the rig exam's nine bodies the knee's median error
  drops from 0.025 to 0.0005 H and long_limbs passes truly; the accepted runner's knee moves
  0.006 H. `reference/markers.md`, `failures.md`.
- **`game-character-pipeline`.** G0 asks a fourth question, the parts tier (`whole`, `three`,
  `fine` reserved); S3 makes the anchor, then the parts; a new S3c assembles them; S6 runs
  `all --hair`. `reference/start-gate.md` §5 says what `three` gains and costs and how a `whole`
  character moves up later. `art-asset-registry`'s workflow links each part to the anchor so a
  repainted part makes only the assembly stale; `unity-3d-models`' budgets give a character in
  parts three materials until the parts merge into one mesh.
- **On the courier runner** (anchor plus one head job): register scale ratio 0.967, RMS 0.022,
  2.6°; one hair piece; `seam.hidden` 1.0; `seam.colour` 25.98 → 1.77 ΔE; whole-body silhouette
  IoU 0.98–0.99. `autorig.py all --hair`: the knee at 0.507 m on the narrowing (0.520–0.534 m on
  the hem before) and `deform.joints_measured` empty. From slices alone the deformation gate passes
  first time (volume loss 0.330, self-intersection p95 0.047); with the Auto-Rig Pro AI, two runs
  in three pass after one elbow repair (0.149–0.157, 0.069–0.070), and in the third the AI's
  fingers came out a few millimetres apart and the fist kept p95 over 0.08 after both repairs. The
  FBX holds body and hair (25 MB, not 35 MB with the head's textures twice); 12 body chains, the
  hair rigid on Head. The README shows the runner whole and in parts (`parts.jpg`).
- **CI.** `part_math.py`, `part_views.py` and `assemble_parts.py` have `--selftest` rows (the last
  under `--blender`) and exit 1 on a usage error; `check-contracts.py` validates `parts/1` samples
  and the doc example; Blender rows run with `--python-exit-code 1`, so a selftest that crashes no
  longer reads as a pass.

## 0.39.0

Secondary motion, free: the hood, back bag, jacket hem, shorts hems and hair spikes of a fused
image-to-3D shell get spring-chain bones at rig time and swing, lag and settle in Unity, with a
spring runtime that ships here (plain C#, no package). The chains change no deformation reading.
Two fixes ride along: an Auto-Rig Pro FBX's embedded maps now bind on import, and the bake's
jitter gate no longer reads a punch the video has as jitter.

- **`character-autorig` → `secondary_chains.py`, stage `secondary`.** On the bound rig it finds
  the loose regions (hood and bag: a bulge ≥ 0.04 H off the opened back profile; hem: a lip
  ≥ 0.004 H in at least four of six sectors; shorts: a thigh-radius drop ≥ 1.35 × and ≥ 0.01 H;
  hair: clusters with ≥ 0.12 of their skin facing sideways), adds plain `cc_` bones under the
  contract bone each hangs from with an unweighted `cc_<chain>_end` tip, moves a share of the
  existing weights onto them inside the region only (four influences, sum 1), sizes body capsules
  and a head sphere clear of every chain joint, exports through `brt_arp` and writes
  `<name>.secondary.json` (`secondary/1`). A strap is a marker chain only (one stiff bone with a
  mid-span sag); `--markers` places or skips chains by hand. Gates `secondary.chains_placed`,
  `weighted_vertices`, `max_influences`, `weight_sum`, `body_weights_unchanged`, `tip_unweighted`,
  `leak` (25° turn, 1 mm outside the region), `rest_penetration`, `export_bones`,
  `export_weights`. A body with nothing loose writes an empty chain list, adds no bone and passes.
  `autorig.py` runs it last, on the passing repair's rig, then contract and deform again on its
  export (`--no-secondary`, `--secondary-markers`); the summary puts both volume readings side by
  side. On the courier runner: 19 chains, every gate green, volume loss 0.1955 and
  self-intersection p95 0.0772 with and without the chains. `reference/secondary-chains.md`;
  `gates.md`; the per-stage commands move to `arp-pipeline.md` ("The stages by hand").
- **Chain-free tails.** Blender's FBX importer lengthens a bone to its children, so a hair chain
  under the Head doubled its length. `deform_gate.py`, `brt_arp`'s skeleton/1 and
  `humanoid-motion`'s `prepare_rig.py` read each tail as without the `cc_` bones
  (`tools/shared-blocks/chain_tails.py`); a rig without chains, or one built in Blender, reads as
  before.
- **`unity-rigged-character` → spring runtime and `SecondaryMotionSetup.cs`.** `SpringSolver`,
  `SpringChain`, `SpringCollider`, `SecondaryMotionSystem`, `SecondarySpec` (namespace
  `UnityDev.SecondaryMotion`): fixed 60 Hz substeps with Verlet, pull to the animated pose,
  capsule and sphere push-out, an angle clamp and exact bone lengths; reset on teleport and
  `ResetPose()`; a frame with no substep still moves; bones a clip does not write go back to rest,
  so it runs under Generic and Humanoid. Add Secondary Motion (menu, or batch
  `SecondaryMotionSetup.SetupFromCommandLine`, exit 0/2/1/3) builds chains and colliders from `secondary/1`, refuses
  Optimize Game Objects, a missing `cc_` bone or a parent more than 1 cm off its bind pose, and
  shrinks or drops a collider a joint starts inside; an empty chain list clears what a run built.
  EditMode tests in `SecondaryMotionTests.cs`. `reference/secondary-motion.md`. The README
  shows the runner chains off and on (`secondary.gif`, `secondary.jpg`).
- **`unity-rigged-character` → `CharacterImportSettings.cs` embedded maps.** Unity bound none of an
  Auto-Rig Pro FBX's packed images until extracted, then bound by file name (another character's
  `Image_0.png` as readily). A body FBX in a character folder now has its base-colour and normal
  slots extracted once as `<Body>_BaseColor` / `<Body>_Normal`, the normal imported as a normal
  map, both bound on its own material on every import; `Maps(folder)` checks it.
  `CharacterImportTests.cs`; `fbx_textures.py` prints each map's slot, names generic images by it
  and gains `--selftest`.
- **`blender-retarget` → `motion_metrics.py`.** With `reading_joints`, the jitter gate takes each
  joint's jitter less 1.2 × the readings' on the same frame and joint (`jitter_over_source_mps2`;
  the absolute `jitter_mps2` stays in the report); a finger with no readings takes its hand's
  allowance, and its pops are held to the forearm-to-hand readings. The courier's baked uppercut
  passes (jitter gate 26.5 → 0, pops 1 → 0). On real two-camera clips the readings' own jitter
  (p95 about 33) is above the output's almost everywhere, so the gate now catches only jitter
  beyond the readings' on the same frames; read `jitter_mps2` beside it.
- **CI.** `fbx_textures.py --selftest` and the usage-error exit 1 of `secondary_chains.py` and
  `fbx_textures.py`; `secondary_chains.py --selftest` runs with `run-selftests.py --blender`;
  `check-contracts.py` validates `secondary/1` samples and the doc example, and asks a script for
  samples from one of its selftest rows, not every row (`contact_bake.py --selftest-blender`).

## 0.38.0

Three measured gaps closed or charted. `character-autorig` gains an exam that scores the automatic
rig against bodies whose joints are known and checks that its gates catch planted defects; the
two-camera solve stops smoothing a punch away; and `mesh-texture-paint` paints thin parts and stops
re-aiming at specks. The exam's first run on 0.37.0 exits 2, by design: it names what the gates miss.

- **`character-autorig` → `rig_exam.py`, `rig_exam_blender.py`.** `build` makes a seeded cast of
  nine metaball bodies around known skeletons (standard, chibi, heavy, thin, long_limbs, mitten,
  spiky_hair, skirt, asym) with `exam/1` truth files; `run` puts each through `autorig.py all
  --no-smart`; `faults` plants defects on a good rig (an elbow marker off the crease, swapped
  knees, a collapsed index finger, a leg weighted to the other side, 50/50 blends at the elbows and
  knees, a rigid skin, an unchanged control); `reference` adds a rig a person accepted; `score`
  writes `exam.json` and a contact sheet (truth green, markers red) and exits 2 on a false pass or
  a fault no gate failed. The joints' error is reported over H for the markers and for the
  exported skeleton, with the volume check that the deform limit still separates good rigs from
  blended ones. `--smart` records Auto-Rig Pro's AI as a second opinion only, never as truth, a
  label or a limit. On 0.37.0: joint median 0.019 H; heavy (pelvis and hips low) and long_limbs
  (a knee just over 0.04 H) pass falsely; a limb weighted to the other side, a collapsed finger
  chain and, on a slim body, a rigid skin or a shifted elbow pass every gate; the 0.35 volume limit
  still separates (the old per-bone patch would have failed most sound binds). `reference/rig-exam.md`;
  `gates.md` lists what the gates miss and `failures.md` what to do on a mitten read as fingers and
  on an exam that exits 2. No gate or limit changes.
- **`humanoid-motion` → `twocam/solve.py`.** The acceleration term is robust per joint and frame:
  quadratic up to `--acc-delta-px` (10 px/frame²), Cauchy beyond, so a strike's hand is followed
  instead of traded for a smooth path; `--acc-delta-px 0` is the old term and the default with
  `--compat-anymove`. New gate `two_view_limb_reprojection_px` (the worst hand or foot per frame,
  on trusted axes and confident views, worst 3-frame median, `--limb-px` 32 × H/768), with
  `limb_worst` in the report: the all-joint median cannot see one arm. On the courier runner's
  uppercut the right arm is now up at frame 48 (limb gate 21 px; the old fit 104 px). The bake of
  that clip now fails `blender-retarget`'s `jitter_p95_mps2` and one finger `pops`, which read the
  punch as jitter (the readings alone exceed the jitter limit); `two-camera.md` says how to read
  it. **`twocam/exam.py`** `make --strike-frame/--strike-px/--strike-side` plants a hand whip and
  `score --max-worst-cm` gates the worst joint (`max_cm`, `max_at`). `motion.gif` is rebuilt from
  the new solve.
- **`mesh-texture-paint` → `mvtex.py`, `paint_loop.py`.** Texels no view has painted take a narrow
  0.5–2 px edge ramp (every texel on a thin mesh), painted ones keep 2–8 px so seams stay; one
  `Mesh.thin` test; next-best view drops unpainted regions under the speck area on screen and
  re-applies its 5 % test; `--zoom-max-pitch` (30° for objects) keeps steep cameras unzoomed;
  `--max-views` defaults to 20 for a character, 16 for an object; three next-best views in a row
  with nothing unpainted end the loop; `report.json` adds `coverage_screen` (the painted share of
  rendered pixels), `rejected` and `stop`. A racket's coverage rises about 0.05; a racket's
  near-miss band, and a back view drawn as the front just under the drift limit, stay open
  (`projection.md`, `gates.md`, `troubleshooting.md`).
- **CI.** `rig_exam.py --selftest` (numpy, planted data) and both exam scripts' usage-error exit 1;
  `rig_exam_blender.py --selftest` runs with `run-selftests.py --blender`.

## 0.37.0

`character-autorig` can use Auto-Rig Pro's own AI for the markers: the body, each finger and the
face. Two cases needed a person before. A glove, or fingers held together, gave the slice markers
no fingers to find, so the hand took a fixed shape. A hairdo that raises the mesh's top pushed a
marker just outside its window, and only a person could pass it. The AI runs on the user's licensed
copy, through its own operators, and the slice markers stay the fallback for every part of it.

- **`character-autorig` → `arp_smart.py`, stage `smart`.** The AI takes its pictures from the 3D
  viewport, so `blender -b` cannot run it. The script opens Blender with a window and drives the
  chain from a timer on that window's 3D view: `id.get_selected_objects`, `arp.guess_markers`,
  `arp.guess_fingers`, the facial setup with `arp.guess_facial`, then Go! (`id.go_detect`, invoked).
  It writes every marker and every reference bone Go! placed to `autorig-smart/1`, saves the file
  for a person, and quits Blender itself, also on an error or a timeout. Gates `smart.ai_files`,
  `smart.body_markers`, `smart.fingers`, `smart.facial`, `smart.go`, `smart.refs`; exit 0/2/1. Each
  step is judged by the scene it leaves: an add-on error arrives in the user's interface language,
  and a popup raises nothing.
- **What the chain needs.** Material viewport shading for the face, since a generated mesh has its
  mouth and eyes in the paint: in Solid shading the lips go unseen and the add-on drops the mouth
  and jaw without an error. Fingers before the face, whose setup hides the body the finger step
  reads. Proxy eyeballs, since an image-to-3D mesh has no eye objects; or eyes off. A face that
  fails is cancelled before Go!, which then still builds the body and fingers. Preferences are not
  saved on quit, and a file that already holds a rig is refused. Go! scales the rig object, so
  references are read in world space. The add-on's four-finger hand has no index finger.
- **`arp_markers.py --smart`.** The body stays measured from slices and is paired, landmark by
  landmark, with the AI's markers in `smart_agreement`. The two put a joint at different depths
  (the AI shoulder on the deltoid, the slice one at the armpit), so the window decides, not the
  distance: a near miss, a landmark at most `--smart-tol` (0.03 H) outside its window whose AI
  marker lies inside it, passes `markers.windows` with `confirmed_by: "auto-rig-pro-ai"`; one
  further out fails whatever the AI says. The AI's head top sits on the skull under the hair, so it
  is not thrown by a spiky hairdo that pushes the slice shoulder below its window. A hand the
  slices could not part takes Go!'s hand and finger references (`fingers.mode` `ai`), and the
  wrist follows the AI's, on the cuff where Go!'s finger bases start; a finger the four-finger hand
  lacks keeps the fixed shape. The face and ears go into `arp_refs` with `facial`, each side as Go!
  placed it; every reference from Go! keeps its roll in `ref_rolls`. A file whose body sits over
  0.10 H from the slices (another mesh or frame) is noted and nothing is taken from it; a malformed
  one refuses.
- **`blender-retarget` → `brt_arp` `pipeline`.** With `facial`, the face is turned on at the head
  limb (and ears added, `arp.add_limb`) before the references are placed: gate `arp.face_added`, and
  `arp.refs_placed` covers the face. A bone in `ref_rolls` takes that roll as it is instead of
  turning with the hand, checked within 0.1° (`rolls_given`, `worst_roll_miss_deg`). A rig with a
  face exports with the add-on's Full Facial on; without it the exporter folded secondary face
  weights onto `head.x` and the jaw, past 4 influences. `probe` reports `ai_ready`, read without
  changing any permission.
- **Fixes in `brt_arp` and `arp_markers` for every character.** The fixed hand's palm frame came out
  as a zero vector, so the fixed-shape knuckles sat in a line about 2 mm apart: they fan out across
  the palm again. The human preset edits with X-mirror on, so writing a `.r` reference overwrote
  its `.l` twin's roll; placement now turns X-mirror off and puts it back. `brt_arp.OPERATORS` lists
  Go! as `id.go_detect`, the name it registers.
- **`autorig.py`.** Stages `prep → check → smart → markers → arp → contract → deform`. `smart` runs
  when a headless probe finds the add-on and its AI files, in a window and without
  `--factory-startup`; `--no-smart` skips it, `--facial` adds the face and `--fingers` passes
  through. A failed `smart` never stops `all`: the run exits 2, and the markers take what passed in
  its report (slices alone when it wrote none); without the AI the stage is skipped and the exit
  code unchanged. `ARP_AI_DIR` points one run at another AI folder, in memory only. `fingers.mode`
  `ai` counts as fingers found.
- **`deform_gate.py` pose `jaw_open`.** The jaw 20° down, run only when named (`--poses
  all,jaw_open`), under the same self-intersection limit; `autorig.py` names it when the markers
  carry the face and the contract maps a Jaw. **`unity-rigged-character` → `contract_map.py`**
  maps `c_jawbone.x` to `Jaw` in the `arp` preset, an extra role outside the contract: it reaches
  `retarget_map`, `extra_roles` and Unity's optional Jaw, never the contract tier or the bone count.
- **`deform_gate.py` measures a joint's patch joint to joint.** The patch radius was half the
  shorter adjoining bone; Auto-Rig Pro's `forearm_stretch` ends at the twist bone, short of the
  wrist, so on a sleeve wider than that half no skin fell in the patch and the elbow went
  unmeasured. It is now half the shorter adjoining span, from the joint to the next contract joint;
  a bone with no mapped next joint keeps its length. The limits do not change.
- **A genuine licence.** Auto-Rig Pro is a paid add-on by Artell. `character-autorig`,
  `blender-retarget` and the READMEs now ask for a genuine licence from the author's Gumroad or
  Superhive store, which funds its development and brings its updates. The AI files come with the
  licence, one device each, installed with the add-on's own Install AI Files…, which also clears
  macOS quarantine; they are never copied into a project, this repository, CI or another machine.
  `art-asset-registry`'s `auto-rig-pro` row says so.
- **Docs.** `character-autorig` → `reference/arp-ai.md` holds the flow, options, gates, fallbacks
  and where the AI and the slices differ by design (head top, shoulder, hips, chin, foot bank,
  brows). Every "no Smart detection, headless only" statement is rewritten; `game-character-pipeline`
  S6 accepts the markers on AI agreement or a person's look. `blender-retarget` →
  `reference/arp-route.md` names Go! by its registered name, `id.go_detect`.
- **CI.** `arp_smart.py --selftest` (no add-on, no Blender) and its usage-error exit 1.

## 0.36.2

The rigged-character example now follows the courier from the texture example, through its
repainted mesh, and an Auto-Rig Pro export keeps every texture of an image-to-3D mesh.

- **`blender-retarget` → `brt_arp.py` export.** An image packed from a .glb has no file path, and
  Auto-Rig Pro's own FBX exporter embeds one picture per path and, unlike Blender's, names no
  pathless image. Every texture of an image-to-3D mesh then read back as the first one: the base
  colour sat in the normal slot, in Blender and in Unity. The export now gives each packed image a
  file name of its own for the call and puts the empty path back after.
  `tests/test_arp_export.py` checks the names the exporter sees and that two packed textures read
  back apart.
- **README.** "From one drawing to a moving, rigged character" is redone with the teal courier
  from the texture example: its mesh repainted by `mesh-texture-paint`, rigged by
  `character-autorig`, filmed by MiniMax H3 from two cameras, and solved onto its own skeleton by
  `humanoid-motion` with a reader warm-started from the earlier runner's. The banner's 3D row shows
  the same courier: concept, painted mesh, rig and deform check. The three translations follow.

## 0.36.1

CI is green again. No skill method, threshold or manifest description changes.

- **`sprite-from-video` → `video_frames.py --selftest`.** The "leftover key at the edge" clip check
  failed on CI since 0.34.0 put the ffmpeg selftests there, and passed on a developer machine. Its
  synthetic leftover-field patch, `(0, 140, 0)`, sat about 96 from the painted key, which is exactly
  `KEY_THRESHOLD`. An encoder that decodes the field one or two levels darker puts the patch inside
  the hard cut, so the whole patch is keyed away, nothing touches the edge, and the run exits 0. The
  patch is now `(0, 110, 0)`: the same key hue, about 125 from the painted key, so the check passes
  whatever the field decodes to. The gate itself is unchanged.
- The clip checks print their exit code, the painted key and the edge contact when they fail, so a
  CI log shows why.

## 0.36.0

Sixty-one skills. Image-to-3D gives a good shape and a dull, blotchy, guessed texture: the multi-view
mesh is darker and less saturated than the art it came from, and its unseen sides are invented. A
new skill, `mesh-texture-paint`, keeps the mesh, its UVs and its normal and occlusion maps, and
repaints only the base colour from the concept art. It renders the mesh from one camera, has a
local image-edit model paint that view guided by the concept art, registers the painted image to
the render's silhouette, gates it, projects the painted pixels into the UV texture, picks the next
camera, and repeats. The finished GLB is the original with only its base-colour image replaced.
The same route serves a character and a prop (the courier backpack, the parcel bag, a cone); a thin
prop works too, with a looser silhouette around its holes. The scripts depend only on Python 3,
numpy, Pillow and SciPy, each has a `--selftest` that needs no network, and a usage error exits 1.

**The route**

- **Inputs.** The image-to-3D GLB from `comfyui-asset-generation` (Pixal3D multi-view, run after
  `four_view_background_removal_api.json`: without it the mesh grows black slabs), the four concept
  views `front`, `left`, `back`, `right` on black, and the turnaround sheet they were split from
  (`codex-visual`: a three-quarter image, then a 4:1 sheet, then `turnaround_to_views.py`). Yaw 0
  looks down +Z at the front; yaw 90 sees `left.png`, the model's own left.
- **The paint call** (`qwen_paint.py`). Qwen-Image-Edit-2511 int8 with the 4-step Lightning LoRA
  on a self-hosted ComfyUI, submitted through `comfyui-asset-generation`'s client. Exactly two
  images: picture 1 is the guide render at 1024×1024, whose layout is kept, and picture 2 is one
  reference. A third image leaves the guide almost unpainted. The latent is the encoded guide;
  ModelSamplingAuraFlow 3.1, CFGNorm 1, the multi-reference latent method `index_timestep_zero`,
  4 steps at cfg 1, euler/simple. Twenty steps without Lightning come back ghostly, and a denoise
  below 1 returns the guide unchanged.
- **The guide** (`mvtex.py`, `paint_loop.py`). The first view is the front: a plain clay render on
  `#00FF00`, with the whole sheet as reference. Every later view is a context render: what is
  painted so far in colour, and the unpainted surface shown as a prior, the GLB's own texture
  brightness-matched to the painted texels with one gain and offset for all channels (`--prior
  self`; with no texture in the GLB, the nearest painted colour). Specks under 400 px take the
  nearest painted colour. The prompt asks for a repaint that matches picture 2, keeping what is
  already well painted, and ends with "Draw only this one <subject>, no other views or copies."
- **Reference fallback.** The sheet first; on a failed try, the single concept view nearest the
  camera's yaw. A sheet can make the model paint a collage of several figures; a single view can
  make it copy that view's facing.
- **Cameras.** Perspective, fov 20, the conditioning Pixal3D's multi-view model saw. Eight anchors
  at pitch 0 (yaw 0, 45, 315, 90, 270, 135, 225, 180), then next-best-view over 128 Fibonacci
  directions: pitch within −40..50 (a steeper view comes back drawn at eye level), at least 20°
  from every used camera, at least 5% of the visible surface unpainted, zoomed onto the unpainted
  region but never tighter than 25% of the largest extent. A thin mesh (smallest extent under 15%
  of the largest) is never zoomed: a zoomed crop of one comes back unrecognisable. A character adds
  three head close-ups (yaw 0, 40, 320) repainted from the front view, which win the refine test
  through their zoom weight and give a sharp face. The loop stops at 0.97 of the seeable surface,
  16 views or 3 rejections in a row, then runs the detail passes; `--resume` continues from
  `state.npz`.

**The gates, per try** (up to 3 tries per view, seeds and references alternating)

- Silhouette IoU at least 0.90 after a similarity alignment search (±3% scale, ±16 px shift).
- Outline distance p90 at most 24 px at 1024 (a collage scores 70 and up).
- At least 0.3 of the unpainted pixels painted.
- Already-painted pixels: at most 8% change brightness by more than 60 levels, and at most 6% go
  from dark to light (dark hair turning silver).
- Background at most 40 from the key: a washed-out key comes with a washed-out figure.
- Pixels within 6 px of an outline disagreement (a strap that moved) are neither projected nor
  counted in the drift tests. When the concept art has no key-green hue, green bled in from the
  background is clamped (G ≤ max(R, B) + 8) before projection.

**Projection.** A per-texel depth test (eps 0.004 × the bounding-box diagonal) and a 75° facing cut,
which also drops the inner shell of a double-shell image-to-3D mesh. Weight = view weight × cos⁴ ×
edge falloff (0 within 2 px of a silhouette or depth edge, 1 from 8 px); a zoomed camera's view
weight is min(3, full radius ÷ zoom radius). A painted texel takes a new view only when that view's
weight beats its best earlier one by 1.5×. Before blending, a per-channel gain and offset from robust
quantiles over the texels both views cover matches the colours, skipped as implausible outside gain
0.85–1.18 or offset 25. Texels no view reaches keep the matched prior; the gutter is filled by a
distance-transform push. A run writes `basecolor.png`, `<glb-stem>_painted.glb`, `coverage.png`,
`turntable.png`, `report.json` and `views/` (each guide, output and aligned image).

**Tried and rejected for the unpainted surface.** Flat grey and clay grey read as grey material
(dark hair turned silver). Magenta, as some multi-view texturing add-ons use it, bleeds into purple
hair and socks. A nearest-colour fill spreads wrong colours (a side pocket's orange onto the back of
the shorts). A per-channel prior match turns neutral greys olive. The one-gain prior is what is left.

**Licences.** Qwen-Image-Edit-2511 and its Lightning LoRA are Apache-2.0. Qwen Image 2.1 is research
and evaluation only, and nvdiffrast is non-commercial: the skill uses neither, and rasterises in
numpy. No code is ported; the method borrows ideas only.

**Integration**

- `game-character-pipeline`: a new stage **S3b, repaint texture**, between S3 (generate) and S4
  (normalise), when S3's texture is below the target; its exit is the painted GLB with mesh and UVs
  unchanged and its turntable accepted by a person. A request row points a dull generated texture
  there, "nine skills" is now ten, and `reference/upstream-changes.md` says what a new repaint sends
  back through (S4's file, S5's rebake on the ship track, S11, S12) and what stands (rig, clips).
- `comfyui-asset-generation`: the Scope and `reference/image-to-3d.md`'s hand-off say the
  image-to-3D texture is a prior to repaint here; `reference/server-inventory.md` lists the
  image-edit family's four files and that it is a separate model family from 3D.
- `codex-visual`: the request table and Scope point the concept views and sheet at the repaint;
  `reference/image-to-3d-input.md` §5 says to keep them after the mesh is made.
- `unity-3d-models`: a request row for a dull generated texture.
- `art-asset-registry` → `reference/licences.md`: the `qwen-image-edit-2511` source (`worldwide`),
  the two non-shippable models named, and a repainted texture linked `depends-on` its GLB.
- `tools/run-selftests.py` gains a `scipy` dependency tag and the three rows; CI installs SciPy and
  probes the three scripts for exit 1 on a bad flag; `tools/cross-skill-deps.txt` declares
  `qwen_paint.py` → `comfy_asset_client.py`.
- The skill listing stays inside its budget: the `unity-live-services` and
  `game-character-pipeline` descriptions are shorter, their main use case first and unchanged.
- Two routing evals, `art-texture-repaint` (the runner) and `art-texture-repaint-prop` (the courier
  backpack), route a dull generated texture here rather than to `comfyui-asset-generation` or
  `codex-visual`.
- README and its three translations: sixty-one skills, the new row with the AI asset skills, and the
  skill in the rigged-character chain; SciPy among the optional requirements; and a "See it work"
  section, from a dull generated texture to one that matches the concept: a turntable of the
  runner and the courier backpack, baked texture beside repainted, and one loop step in five
  panels.

## 0.35.0

Sixty skills. This release is about data contracts: the files one skill writes and another reads.
Until now each was prose, restated in every skill that touched it, and the copies had drifted. One
producer wrote `margin_px` where another wrote `foot_margin_px`. Only one of three producers
recorded its chroma key, so the Unity audit measured a green-keyed set's fringe against magenta and
passed it. Gate reports came in two dialects (`ok` and `pass`), and the two stage runners counted a
gate with neither key as passed. Three timeline readers each carried their own key lookup, and two
claimed an order they did not follow. Nothing in Unity applied the pivot that `frames.json`
recorded, although one doc said something did. Each contract is now defined once in `schemas/` as
JSON Schema. Producers stamp what they write, and CI validates their selftest output against the
schema.

**Behaviour change — `frames.json` is `frames/1`.** `sheet_to_frames.py`, `breathe.py` and
`sprite-from-video`'s `video_loop.py` stamp `"schema": "frames/1"` and always write:
- `key_color`: the declared key, lowercase `#rrggbb`. It is `null` only for an explicit
  `--key-color none` (art never keyed). `video_loop.py` copies it from `frames.report.json`'s
  `key.declared` and records the painted colour as `key_painted`.
- `register.reference_core_height_px`: an integer, measured on the written reference frame after
  any `--upscale`, in every register mode.
- `register.foot_margin_px`: the one name for the gap under the feet. `video_loop.py` used to
  write `margin_px`, which was its canvas margin (`--margin`). It now writes that value as
  `canvas_margin_px`, and `foot_margin_px` as the rows under frame 0's feet. `frames/1` refuses
  `margin_px`.
- `loop`, plus `hold_last` (a bool: a one-shot that ends on its last pose and holds it).

A producer that writes frames with no key at all now refuses with exit 1. Pass `--key-color HEX`,
or `--key-color none` for native alpha. `breathe.py` takes the key from the `frames.json` beside
the still, and `video_loop.py` from the report, so an ordinary run needs no new flag. A bare PNG
folder given to `video_loop.py` needs `--key-color`. New flags: `sheet_to_frames.py --no-loop` and
`--hold-last-pose`, and `--key-color` on `breathe.py` and `video_loop.py`.

**Behaviour change — gate reports are `gate/1`.** Every gate script stamps `"schema": "gate/1"`.
The report carries `pass`, and each gate is `{name, value, limit, pass}`. A gate's `ok` is gone.
The report still writes `ok` equal to `pass` for one release, for old readers. **A missing `pass`
is a failure everywhere.** In `autorig.py` and `twocam.py` a gate with neither `pass` nor `ok`
now fails, where it used to pass. `registry.py`'s approval check treats any gate without
`pass: true` as failing. `contact_sheet.py --require` accepts a `gate/1` file only on
`pass: true`. `brt_audit.py` exits 1 on a result with no gates. `twocam/skeleton.py rig-info`
passes only with at least one gate. A Blender op that reports no gates returns a result, not a gate
report: it carries no stamp and keeps its `ok`.

**Behaviour change — the timeline stamp is `"schema": "timeline/1"`.** `JourneyRecorder.cs`
writes it on the meta line instead of the integer `1`. GameProbe's live probe response keeps its
own integer stamp.

**Migration, one release.** Readers still accept the 0.34 dialect: an unstamped `frames.json`,
`margin_px`, `set_metrics.key_color`, a gate's `ok`, and a timeline stamped `1` or not at all.
Each prints one `WARN` naming the old key, and 0.36 removes them. Only an unstamped file gets that
grace. A file stamped `frames/1`, `gate/1` or `timeline/1` that lacks a required key is a producer
bug, and the reader fails on it.

**Behaviour change — `SheetToAnimationClip` exit codes.** It used to exit 1 on every failure. Now
it exits 1 on a usage error or a refused file, 2 when the clip reads back different, and 3 when
there is nothing to build. With `-framesJson` it takes `loop` and `hold_last` from the file unless
`-loop` is given. It refuses a `frames/1` file without `loop`, and one with `hold_last` true and
`loop` true. `-holdLast N` is unchanged: it still adds N held frames.

**Behaviour change — Android `targetSdk`.** Google Play now requires target API 36 for new apps
and updates, and 16 KB page support for anything that targets 35 or higher. Pinning `targetSdk`
to 34 is therefore no longer a way to ship a 4 KB-aligned native library to the store.
`unity-android-release` now says to rebuild the library with 16 KB alignment or replace it. A 34
pin is only for builds sideloaded outside Play. `build-android.sh` changes its wording only: its
preflight still refuses a 4 KB library under targetSdk 35 and up, and still only warns at 34 or
below.

**Removed from the docs:** `-autoplay` is no longer documented as a harness flag. A game may ship
its own autoplay switch, but `unity-play-harness/resources/` ships none. `PackageProbe.RunAsync`
never existed. `package-bootstrap.md` now builds its transcript around the doc's own
`ProjectBootstrap.PackageInstaller.Install`, whose codes are 0 resolved and 3 for a UPM error or a
timeout.

**Contracts and the checks on them**

- **`schemas/`** (new): `frames-1.json`, `gate-1.json` and `timeline-1.json`, plus a `README.md`
  with what each field means, who writes it, who reads it, the PPU rule and the migration rule.
- **Selftests hand over samples.** Each producer's selftest writes the shapes it emits to
  `$UNITY_DEV_CONTRACT_OUT` (a fixed temp folder when unset) and prints `selftest-output: PATH`.
  Skills still never import a validator. Each selftest checks its own required keys by hand, so a
  skill stays copyable on its own.
- **`tools/check-contracts.py`** (new, in CI as "Data contracts") runs four checks:
  - every selftest sample validates against the schema its stamp names, and a timeline also passes
    the file rules (meta first, one end line and only last, the right sample count);
  - every long flag in a documented `scripts/*.py` command is defined by that script, and every
    documented `-executeMethod Class.Method` is a static method in shipped C# or in the doc's own
    C# block;
  - every skill script that builds a path into another skill is declared in the new
    `tools/cross-skill-deps.txt`, and both paths exist (the four READMEs now point at that list:
    those rigging and motion skills install together);
  - version tokens match `VERSIONS.md`.

  Exit 0 pass, 2 a contract violated, 3 harness error, 1 usage. `--only` runs one check.
- **`VERSIONS.md`** (new): the version facts the skills depend on: Play's target API and 16 KB
  rule, the Unity LTS streams and releases after 6000.4, the Android `minSdk` floor per Editor
  (26 from 6000.5), and the UGS, IAP, LevelPlay, Input System, Cinemachine, 2D Animation,
  Netcode and AI Navigation packages. Each row has an official source link and the date it was
  checked. **The version check is narrower than "every number lives in `VERSIONS.md`".** It
  checks only a package pin in a manifest, a package-table row or `pkg` 1.2+ floor, and a
  `targetSdkVersion` or `minSdkVersion` assignment. Other version numbers in prose, such as an
  Editor version in an example or the LevelPlay 9.4 / 9.5 API forks, are not checked.
- **UGS floors made conditional, not equal.** `unity-ugs` keeps its general floors and says they
  rise to Core 1.18.0 and Authentication 3.8.1 once IAP 5.4 direct-to-consumer payments are in
  the project. `unity-iap`'s page now says the same.
- **One timeline lookup.** `journey_report.py`, `jump_report.py` and `camera_jitter.py` carry one
  pasted `resolve()` (`tools/shared-blocks/timeline_resolve.py`), with `pos.x` and `vel.y` first.
  A stamped timeline with a missing field or a wrong end count exits 2. `camera_jitter.py` gains
  its first selftest.
- **`.github/CONTRIBUTING.md`** gains a Data contracts section: how to change a contract, the
  selftest hand-off, the four checks, keeping `VERSIONS.md` up to date, and the C#
  `-executeMethod` exit table.

**Frames into Unity**

- **`FramesJsonImporter`** (new, `unity-2d-sprites/resources/Editor/`): an `AssetPostprocessor`,
  and the one place that applies `frames.json`'s import settings. A PNG listed in the
  `frames.json` beside it gets Sprite / Single, a Custom pivot from `pivot_norm`, and PPU =
  `reference_core_height_px` ÷ the character's world height. A pixel set also gets Point and
  Uncompressed, and Max Size is raised to fit the canvas. The world height comes from
  `-worldHeight`, else the value stored on the frame's `.meta`, else an EditorPref, else 1.8.
  `UnityDev.Sprites.FramesJsonImporter.RunFromCommandLine -framesDir <one set folder>` re-applies
  the settings and reads them back. It exits 0 when they match, 2 on a mismatch, 3 when a file is
  missing, and 1 on usage. `SheetToAnimationClip` still owns the clip (fps, loop, hold) and never
  sets the pivot. `sprite-from-video`'s `pipeline.md` now says so, where it used to credit the clip
  builder with the pivot.
- **`SpriteFramesAudit`** measures the rim against each set's own `key_color` and never against
  an assumed magenta. A set with no key is skipped with a warning, and if every set is skipped the
  test is inconclusive, never green. A `frames/1` set with no core height fails the size test.
- **`audit_frames.py`** reads the key from `frames.json` for the fringe and tint checks as well as
  for the residual. `registry_ingest.py` records the canvas, `pivot_norm`, `key_color`, `fps_hint`,
  `loop`, `hold_last`, `block_px`, the core height and the foot margin. A `contact_bake` report
  can now be ingested with `--write`.
- **The PPU rule in one sentence, everywhere it applies.** PPU = core height ÷ world height, one
  PPU per character. For pixel art, choose the world height so that PPU ÷ F is whole.
  `unity-2d-pixel-perfect` now says that frames upscaled by F import at F × the art-pixel PPU.
- **Checking the importer** is a Unity step, run before a release with a licensed Editor: compile
  with `tools/unity-compile-check.sh`, then re-import a frames set under `Assets/` and run
  `SpriteFramesAudit`'s pivot and key tests. The compile check now also stops the Roslyn compiler
  server the Editor leaves behind.

**Headless Unity entry points**

- **`BatchAudit.Run`** (new, `unity-cli/resources/Editor/`): runs any Editor audit that returns
  its report as a string. Examples are `KitAudit`, `PrefabOverrideAudit`, `Physics2DAudit` and
  `LightingAudit`, which had only a menu item. Use `-audit Type[.Method]`; each method parameter
  becomes a flag, and `-scene` and `-out` are also accepted. The exit code is the report's own
  verdict (`pass`, then `ok`, then `verdict`): 0, 2 or 3. A census audit with no verdict needs
  `-census`, because a report with no verdict never passes. The new
  `unity-cli/reference/batch-audit.md` lists which audit carries which verdict. `unity-3d-level`'s
  "run the audits headless" handoff now points there.
- **`SituationBoot`** now implements `-screenshotDir DIR`, which writes one PNG once the situation
  is ready, and `-quit`. A built player exits 0 when ready, 2 when the ready set timed out, 1 on an
  unknown id, and 3 when the shot could not be written.
- **Test asmdef.** `unity-debug`'s `cli-harness.md` now matches the fourteen PlayMode templates:
  it references `UnityEditor.TestRunner`. It also says journey tests run only in the Editor.

**Courier-run preview**

- **`unity-game-brief/resources/Sim/courier_rules.json`** (new) holds every `RunConfig` field, plus
  the preview-only staging (lane plan, pickups, the gate rhythm, the sentry). A new
  `RulesMatchCourierRulesJson` test in `RunSimulationTests` fails when the C# defaults and the file
  differ.
- **`courier_run_preview.py`** reads that file and moves the runner by the simulation's own rules:
  launch, acceleration up to the launch speed, a lane change at the press with its speed scrub,
  and a stop at the gate. `.github/media/preview.gif` is regenerated from it.

**Handoff gaps closed**

- `unity-2d-animation` → `unity-physics-2d`: new `reference/bone-colliders.md` (colliders that
  follow a bone, hitbox and hurtbox layers, physics-step animation).
- `unity-2d-grid` → `unity-game-ui`: new `reference/board-hud.md` (turn-order strip, range legend).
- `unity-combat` → `unity-live-services` `multiplayer.md` §2: who decides damage, as an
  intent / resolution / presentation table.
- `unity-scene-flow`: host migration goes to `unity-multiplayer-services`, and networked scene
  management is marked out of scope.
- `unity-animation`'s footstep event goes to `unity-game-feel`'s `SfxPlayer`, with a receiver
  example in `events-and-windows.md`.
- `unity-2d-controller`'s click-to-move goes to `unity-2d-grid` on a tile board and to
  `unity-navigation`'s new recipe §9 in a free 2D world.

**Lean**

- `unity-rigged-character` states its Generic-against-Humanoid comparison as a method (play one
  clip under both rig types and compare bone rotation and socket position) in place of measured
  numbers. `blender-character-rig`'s headless pipeline drops its stage timings.

## 0.34.0

Sixty skills. This release is about routing and verification. Claude Code lists every installed
skill's name and description within about 1% of the context window (about 8,000 characters at
200K; Codex allows 2%). When the listing overflows it drops descriptions, starting with the
skills used least. A fresh install has no usage yet, so even the start-here routers could lose
theirs. The plugin's descriptions added up to several times that budget. They are now rewritten
to fit it, and a gate keeps them there. Two skills are folded into `unity-live-services`, which
becomes the fourth start-here router. The routers are slimmed so a `SKILL.md` only routes. The
selftests run in CI, a usage error no longer reads as a failed gate, and the C# templates gain
static rules and fixes.

**Removed skills:** `unity-multiplayer` and `unity-monetization` are gone. A request that used to
load either now loads `unity-live-services`, the START HERE router for any backend, online or
monetisation request. Nothing was dropped:
- `unity-multiplayer` → `unity-live-services/reference/multiplayer.md`: topology and its two
  questions, state ownership and reconnection, the microphone handover, permissions, mute,
  positional voice and the channel caps, and testing. It also says plainly that netcode APIs are
  out of scope for the plugin.
- `unity-monetization` → `unity-live-services/reference/monetization.md`: sandbox modes,
  subscribe first then connect, the consumable that disappears once confirmed, what an SDK does to
  the build, store declarations, and where receipts are validated.

Every cross-reference, the four READMEs and the manifests point at the new places.
`unity-live-services` keeps its section numbers, so existing `§N` pointers still land.

**Behaviour change:** `blender-retarget/scripts/clip_metrics.py` now uses `motion_metrics.py`'s
codes: 0 pass, 2 a gate failed, 1 refused. The old 1 is now 2 and the old 2 is now 1. A stage
runner that branched on the old codes must swap them. `bakeoff_report.py` reads reports, not exit
codes; its own exit codes are unchanged.

**Behaviour change:** in the scripts where 2 means a gate failed, a usage error (a bad flag, a
missing argument) now exits 1 instead of argparse's 2, so a typo can no longer pass for a failed
check. This covers `motion_metrics`, `clip_metrics`, `arp_markers`, `deform_gate`, `mesh_check`,
`contract_map`, the `humanoid-motion` two-camera scripts (`detect`, `exam`, `film`, `layout`,
`make_prompt`, `skeleton`, `solve`, `train`, `blender/prepare_rig`), `compare_windows`,
`breathe`, `key_unmix`, `sheet_to_frames`, `audit_pixel`, `pick_key`, `layout_map` and
`pure_tests`. Scripts with an older convention keep it; `.github/CONTRIBUTING.md` lists them.

**Behaviour change:** `unity-android-release/templates/build-android.sh` no longer puts
`-keystorePass` or `-keyaliasPass` on the Unity command line. It exports `UNITY_KEYSTORE_PASS` and
`UNITY_KEY_ALIAS_PASS`, which `BuildScript.cs` already reads, so the secrets stay out of `argv` as
the skill says they must.

**Behaviour change:** the `unity-game-feel` tween helpers `Tween` and `Ease` now sit in the
`UnityDev.GameFeel` namespace, so they no longer clash with DOTween's types. Code that uses them
adds `using UnityDev.GameFeel;`.

**Descriptions and the listing**

- **Every description rewritten.** The routers run to about 200 characters and every other skill
  to about 100. The first sentence names the main situation. Method detail and "X is handed to Y"
  clauses are out of the descriptions; handoffs live in each skill's Scope section.
- **Triggers moved, not deleted.** Each `SKILL.md` now opens with a request or symptom table that
  covers what its old description listed. It loads only once the skill is invoked.
- **`tools/lint-skills.py`.** A description is capped at 250 characters. A new gate estimates the
  whole listing as one `- unity-dev:<name>: <description>` line per skill and fails above 8,000
  characters. A `SKILL.md` is capped at 12 KB. Syntax is checked with `compile()`, so linting no
  longer writes `__pycache__` under `skills/`.
- **The plugin description.** `plugin.json` and the marketplace entry shrink from a catalogue of
  every skill to under 300 characters: what the plugin is, and the four start-here routers.

**Routers**

- **Four start-here routers**: `unity-gameplay`, `unity-game-ui`, `game-character-pipeline` and
  `unity-live-services`. `game-character-pipeline`'s description now says START HERE, as the
  manifest did. `unity-gameplay` gains routing rows for `unity-render-urp`, `unity-audio`,
  `unity-sprite-atlas` and `unity-debug`.
- **Routers slimmed.** Every `SKILL.md` is at or under 12 KB. The depth went to `reference/`
  (about forty new files) and each symptom row points at it. Where a numbered section moved, a
  short stub keeps its number, so outside `§N` pointers still resolve. `unity-game-ui`'s routing
  detail, IMGUI primitive, build order and design principles moved to `reference/routing.md` and
  `reference/design-principles.md`.
- **Rigging scope.** `character-autorig` gains a Scope section. `blender-character-rig` now names
  `character-autorig` as the default route and itself as the hand-built fallback, and so does
  `unity-rigged-character`.

**Verification**

- **`tools/run-selftests.py`.** One row per selftest, with its call and its dependencies (stdlib,
  numpy/Pillow, ffmpeg, bpy, torch/cv2). A missing dependency prints SKIP; Blender rows run only
  with `--blender PATH`. Any failure exits 1, and so does a script with a selftest that has no row.
  Every selftest accepts both `selftest` and `--selftest`.
- **New selftests** for five stdlib verdict scripts: `merge_results`, `journey_report`,
  `compare_windows`, `level_validate` and `jump_report`. Each builds its input in a temporary
  directory and checks the exit code for passing and failing input.
- **The exit-code convention.** `.github/CONTRIBUTING.md` has the table for new scripts: 0 pass,
  2 the check failed, 3 a harness or IO error, 1 refused input or a usage error. It also lists the
  older conventions still in use.
- **CI.** Runs on Python 3.10 and 3.12 and installs numpy, Pillow and ffmpeg. It runs the
  selftests, probes each verdict script with `--no-such-flag` and requires exit 1 with no
  traceback, and runs the C# static check.

**C#**

- **`tools/check-csharp.py`** (in CI). A MonoBehaviour's class is named after its file. A file that
  uses `UnityEditor` sits under an `Editor/` folder or is wrapped in `#if UNITY_EDITOR`. No new type
  goes in the global namespace; the existing ones are on an allow-list.
- **Fixes.** `GateTarget`, `PickupBag`, `GameProbeReporter`, `SituationBoot` and `PooledPickup`
  each get their own file, so they can be added in the Inspector as the docs say;
  `ScriptablePackerExample.cs` is renamed `GridAtlasPacker.cs` after the class it holds. The editor
  scripts of `unity-2d-sprites`, `unity-tilemap`, `unity-sprite-atlas` (`AtlasBuildGenerator`,
  `AtlasContentBuild`), `unity-urp-migration` and `L10nBatchProcessor` move to `resources/Editor/`,
  and `IosPostprocess` is guarded by `#if UNITY_EDITOR`, with the documented paths updated, so a
  copied script no longer breaks a player build. `Tween` and `Ease` are namespaced, as above.
- **`tools/unity-compile-check.sh`.** A local compile of every skill's C# in a throwaway Unity 6
  project with the packages the code uses, one asmdef per skill, built with and without the
  optional defines. It fails on any `error CS`, opens one Editor at a time and deletes the project
  afterwards. CONTRIBUTING says to run it before a release; it is not in CI.

**Routing evals**

- **`evals/routing/`.** About thirty cases, each graded on which skill was loaded. They cover every
  group of overlapping skills, with a request that should load each skill and one that should not,
  the start-here request of each of the four routers, and a plain-Python request that should load
  none.

## 0.33.1

README only; no skill, script or manifest description changes.

**The README**

- **`README.md`.** The banner has two rows: the 2D route on top (a character still, the keyed
  sprite, its run loop, the sprite running in Unity) above the 3D row from 0.33.0. "See it work"
  now follows the order of development in three parts. First, the game before code: a
  simulated-gameplay preview of the courier run from `unity-game-brief`, timed from the game's
  own rule constants and drawn with art from `codex-visual`. Second, from one still to a sprite
  that runs in Unity: idle, walk, run and jump on transparency from one still, a close-up of a
  plain green key beside the `sprite-from-video` key, and a Unity 6 capture of the runner sprite
  jumping cones and collecting parcels, with the skill chain from `codex-visual` to
  `unity-2d-controller`. Third, the rigged 3D character, unchanged. One line now credits MiniMax H3
  for both the sprite clips and the motion video. "Try asking" gains a seventh request, a walk
  loop from a still, answered by `sprite-from-video`. The three translations in `.github/` follow the
  same structure. The new images live in `.github/media/`.

## 0.33.0

Sixty-two skills. Humanoid rigging and motion now run locally first, onto one skeleton: the
**humanoid contract** (`unity-rigged-character` → `reference/humanoid-contract.md`), 53 bones in
Blender names with a non-deform `Root`, an A-pose rest, +Z up and facing −Y. Every motion source
reaches it through a role map, so a clip made for one contract character plays on every other. Two
new skills: `character-autorig` rigs a mesh onto the contract with the user's own Auto-Rig Pro,
headless and in one command, and `humanoid-motion` turns a move into a clip on it with two cameras:
a front and a side view of the character in one frame, animated by local H3 image-to-video, read by
a reader trained for that character and triangulated straight onto its skeleton, then a shared back
half that bakes contacts, cuts the loop, gates and ships. The two-camera route is ported from
patch-gg/anymove under the Apache License 2.0, credited in `THIRD_PARTY_NOTICES.md` and in each
ported file's header. No cloud rigging service is used anywhere; a paid cloud service may remake a
character's **mesh**, only on a new upgrade track a person chooses after the demo. Every record can
now carry a `licence` with a sales territory, and the registry refuses to approve an asset the
declared territory excludes. Every new script prints one JSON object, has a `--selftest` that builds
its inputs in a temporary directory and documents its exit codes; the host scripts need Python 3 and
numpy only, the Blender ones Blender's own Python, and the two-camera reader torch, opencv and
transformers, imported lazily so `--help` works without them.

**Behaviour change:** `blender-retarget`'s `brt_retarget` now retargets root translation by
default. The translation bone is the mapped bone whose source is the root-most bone of its chain
with a moving location and that has no mapped ancestor; its motion is scaled by `k`, the target's
hip height over the source's. `translate: False` drops it, `"in_place"` keeps only the rise, and
`translation_scale` replaces `k`. The result reports `translation` (`"retargeted"`, `"in place"`,
`"dropped"`, `"present in into_action"`, or `"not retargeted"` when no mapped bone moves, as
before) with `translation_k` and the hip heights, alongside `translation_keyed`. A new gate,
`retarget.translation_kept`, fails a clip whose translation bones stand still in the output while
the source's move, so a clip run with `translate: False` fails it whenever its source travels.
Rotation output is unchanged.

**Behaviour change:** pops fail. `blender-retarget/scripts/clip_metrics.py` gains a `pops` gate
(a pop the route added fails; the same jump in the reference is not a pop), and the new
`motion_metrics.py` gates `pops` at 0 by default. The runtime C# sampler in `unity-animation` still
only logs them. For motion read from video, `--pops-min-move M` requires a spike to move the
segment's end by M metres, so reading noise on a short segment (a clavicle) is not a pop;
`twocam.py capture` passes 0.03. When the samples carry the joints triangulated straight from the
video (`reading_joints`), a spike the video shows too is reported as `pops_in_source` and not
gated; only the pops the solve added count. `motion_metrics.py` counts both as events, one per
frame and parent joint: the segments that leave one joint turn with that bone, so a shin and the
Auto-Rig Pro twist segment beside it spiking on one frame are one pop, not two. `--pops-max`
applies to that count; `segments` counts the segments that spiked and `list` names each.

**Behaviour change:** one plant definition. A foot is planted over a run of at least 3 frames whose
sole is under 4 cm above the floor and whose ground-relative horizontal speed is under 0.15 m/s; an
in-place loop declares its travel speed (`travel_mps`) and gets it added back before the speed test,
and supplied contact probabilities at or above 0.5 define the plant instead. When the samples carry
`sole_offsets` (each foot joint's rest height above the ground), a foot's sole is the lowest of its
joints' heights minus their offsets, so a plant is found though the ankle stands well above the
sole. `motion_metrics.py` holds it; `clip_metrics.py` and `humanoid-motion`'s `contact_bake.py`
import it, and `unity-animation` → `reference/motion-metrics.md` and
`reference/foot-lock-and-prop-ik.md` now state the same sentence (the second said 0.5 m/s, which
only made up for in-place loops). `clip_metrics.py`'s options and output are unchanged apart from
the added `pops` key and gate. `motion_metrics.py`'s plant gate is renamed: what was gated as
`plants_found` is now `plants_min_per_foot`, the fewest plants on one foot, at least 1 with
`--state walk|run` or on a foot that stands on the ground; `plants_found` is now the total over
both feet, reported beside `plants_per_foot` and not gated, as `contact_bake.py` reports it.
`contact_bake.py` still gates its own `plants_found`.

**Behaviour change:** the image-to-3D templates (`pixal3d_image_to_model_api.json`,
`pixal3d_multiview_to_model_api.json`, `trellis2_image_to_model_api.json`) default to 70000 faces
(`186.target_face_count`), a 768 remesh (`241.resolution`) and 2048 textures (`288.value`), where
they had 8000, 384 and 1024. A run with no `--set` now gives a mesh about nine times denser and a
GLB about three times larger, in about a quarter more time. The old defaults are the Compact
preset: `--set 186.target_face_count=8000 --set 241.resolution=384 --set 288.value=1024`.

**Behaviour change:** `unity-rigged-character`'s `CharacterImportSettings.cs` defaults
`character-pipeline.json`'s `"rig"` to `"Generic"`, as the documentation already said; only the
exact word `"Humanoid"` turns Humanoid on. A project that relied on the implicit Humanoid default
sets `"rig": "Humanoid"`. New fields: `"humanMap"` (a `unity-human-map/1` file; empty = the
contract's own names) and `"minFingerBones"` (default 10).

**Behaviour change:** the sales territory is gated. Once `ART_DIRECTION.md` declares
`Sales territory: worldwide | <ISO codes or EU> | undecided`, `registry.py check`,
`status ID approved` and `record --status approved` exit 2 on an approved record whose own licence,
or any upstream reached through `parent` or a `depends-on` link, excludes a declared territory. No
declaration, or `undecided`, is a warning; candidates are never refused. Records without `licence`
behave as before.

**The humanoid contract**

- **`unity-rigged-character` → `reference/humanoid-contract.md`, `scripts/contract_map.py`.** The
  bone table, the rest and axes, and role maps for Mixamo, Auto-Rig Pro's Unity export with and
  without Rename for UE, and the contract itself; a skeleton without a preset gets its own map from
  `suggest`. `contract_map.py map` reads a skeleton JSON, a Blender dump or a BVH header and gates
  it: Unity's 15 required bones; with `--require contract` all 53, `Root` non-deform at the origin
  between the feet and the upper arm 30–60° below horizontal; `--min-fingers`; unique sources;
  parent chains; sides; axes. It writes `retarget_map` in `brt_retarget`'s orientation and a
  `unity-human-map/1` for Unity. `bvh`, `contract` (the reference skeleton as JSON, for other
  skills to read rather than import), `suggest` and `presets` complete it. Exit 0 pass, 2 a gate
  failed, 1 refused.
- **`unity-rigged-character` → `resources/Editor/CharacterHumanoidAvatar.cs`.** Builds a Humanoid
  Avatar from an explicit `humanDescription` (Tools/Unity Dev/Rigged Character/Build Humanoid
  Avatar), so Chest and the fingers are mapped rather than left to auto-mapping; its gate requires
  `isValid`, `isHuman`, Chest and at least `minFingerBones` fingers, and `CharacterAvatarLinker`
  uses it when the rig is Humanoid. Generic stays the default on the contract; Humanoid is for a
  body-part mask or IK.
- **Unity clips on the contract.** `SharedSkeletonClipImporter` takes `RootNode` = the armature
  object's name and `RootBonePath` = `<rig>/Root/Hips`; motion samples from a contract rig are
  read with `--root Hips` unless they come from `contact_bake.py`, which names Hips itself.

**Rigging, locally: `character-autorig`**

- **`character-autorig` → `SKILL.md`.** Seven stages, one command each, and one command for them
  all: riggable mesh, markers, Auto-Rig Pro, contract, skin, deformation, FBX. Auto-Rig Pro is the
  default when the user has installed it; the hand-built route (`reference/hand-built-route.md`)
  uses the same markers through `blender-character-rig`'s `bcr_armature`, `bcr_skin`, `bcr_fbx` and
  `rig_gate.py`. Check the Blender version first: on a Blender newer than the add-on lists, run
  `scripts/tests/test_arp_pipeline.py` before the first character, and rig in the listed version or
  by hand if it fails. Failures are fixed locally, never by loosening a limit.
- **`character-autorig` → `scripts/mesh_check.py`, `reference/gates.md`.** Before any rig: legs
  part below the crotch (slice connectivity), both arms hang clear in the arm band, and the
  double-shell ratio stays at or under 0.25. Only a same-facing double layer counts: a thin inner
  shell lying back to back with the skin, its normals pointing in (a fixed product of some
  image-to-3D generators), is reported as `inner_shell` and kept. GLB, glTF or OBJ; a fail goes
  back to the views or the 3D generation.
- **`character-autorig` → `scripts/arp_markers.py`, `reference/markers.md`.** Every Auto-Rig Pro
  reference marker measured from horizontal slices, in Blender or on the host: heights inside their
  windows, left and right within 0.02 H, the upper arm 30–60° down, fingers found where the hand
  splits into four parts or a fixed hand shape scaled to the hand, front and side pictures for a
  person, `--adjust` for one marker. A marker a person adjusted leaves the symmetry test and is
  listed under `asymmetry_accepted`; the markers left unadjusted are still held to it. No marker is
  placed by eye and no Smart detection runs. It also writes a contract-named bone spec for the
  hand-built route.
- **`blender-retarget` → `brt_arp` op `pipeline`, `character-autorig` →
  `reference/arp-pipeline.md`.** Append, reference bones placed from the markers, Match, bind,
  influences limited to 4 and normalised, the Unity FBX exported and read back, and a `skeleton/1`
  dump whose deform flags come from the weights, in one call; a gate that fails before the bind
  rolls the rig back. The record carries `licence: {source: "auto-rig-pro", territory:
  "worldwide"}`. The add-on's spine Count counts its root: Count 4 gives the contract's three
  spine bones.
- **`blender-retarget` → `brt_arp` op `export`, `scripts/tests/test_arp_export.py`.** Re-exports a
  bound rig after a weight repair with the pipeline's own settings, the 4-influence limit, the
  skeleton dump and the licence. `reference/arp-pipeline.md` carries the ladder for an elbow or a
  knee that collapses, tried in order on a copy and stopped at the first pass. The first rung, which
  `autorig.py` runs, is the weights: two `brt_weights` transfers across the hinge between deform
  bones only, below the joint to the lower bone (its twist bone included) and above it to the upper
  one, each band handed over whole (`amount` 1.0) with the crease band left blended and the torso
  kept out by an X range, then the deform gate again. A finer bind and the marker moved to the
  crease follow, by hand. A loose sleeve hides the crease, and only the weight transfer holds
  there, which is why it comes first.
- **`character-autorig` → `scripts/autorig.py`.** The stages for one character in one command:
  `prep` (`bcr_import_prep`), `check`, `markers`, `arp`, `contract`, `deform`, or `all` in that
  order, into one folder. `--blender`, `--python`, `--threads N` (Blender's `-t N`), `--no-render`
  (no marker pictures, no pose renders) and `--dry-run`; `--min-fingers` and the `fist` pose follow
  the markers' `fingers.mode`. Commands are argument lists with no shell and no inline Python, so a
  Windows path passes as is, and the Blender-side work runs this same file inside Blender; prep,
  markers and deform run with `--factory-startup`, arp and the repair without it. It prints one
  JSON summary (each step's exit code, seconds, log, report and failed gates, the repair attempts
  and the files to take on) and writes it to `OUT/autorig.<stage>.json`; exit 0 pass (after a
  repair that passed, too), 2 a gate failed, 1 refused or an error. The repair ladder runs only
  when `deform.volume_loss_max` is the one failing gate and every joint over the limit is an elbow
  or a knee: each attempt starts from the unrepaired `rig/NAME_arp.blend`, moves the weights across
  that hinge on both sides with bands computed from the markers and scaled with the height, exports,
  keeps a copy in `repair/aN/` and gates again. A hinge that only now fails is added at the same
  amount; volume held but self-intersection failed retries at 0.9; anything else stops, after at
  most 3 attempts, with exit 2, every attempt listed and the two manual rungs named. Limits never
  change; `--no-repair` turns the ladder off.
- **`blender-retarget` → `brt_arp`, headless.** With no window, the 3D view is taken from the
  file's own screens and passed with its `space_data`, so markers, Match, bind and export run under
  `blender -b`. `--factory-startup` still turns the add-on off.
- **`character-autorig` → `scripts/deform_gate.py`.** Six poses — arms up, deep squat, torso twist,
  fist, leg raise, elbow at 120° — stepped in, gated on volume loss at hinge and spine joints (at
  most 0.35; shoulders and hips reported, not gated) and on new self-intersections over the
  triangles that moved (p95 at most 8 %), with renders for a person. Both are measured on the outer
  skin only: a triangle that sees out of the mesh is skin; one with a back-to-back sheet right
  behind it and no way out is inner shell; the rest take the side of their edge neighbours, and a
  connected piece no triangle of which sees out (eyes behind lids, teeth) is left out. Vertices are
  welded by position first, so a UV seam neither splits a sheet nor counts as a rest crossing.
  `deform.joints_measured` fails when an elbow or a knee could not be measured, where it used to
  read 0 and pass. This is the 3D self-intersection count that was only described before.
- **Exit codes.** `mesh_check.py`, `arp_markers.py`, `deform_gate.py`, `autorig.py`,
  `contract_map.py`, `motion_metrics.py`, `contact_bake.py` and the `twocam/` scripts exit 0 pass, 2
  a gate failed, 1 refused; `rig_gate.py` and `clip_metrics.py` keep 0 pass, 1 a gate failed, 2
  refused. A stage runner reads each tool's own table.

**Motion from video: `humanoid-motion`**

- **`humanoid-motion` → `SKILL.md`, `reference/two-camera.md`, `scripts/twocam/`.** A front and a
  side view of the contract character side by side in one 1376 × 768 frame, animated by a local
  MiniMax H3 image-to-video template through `comfyui-asset-generation`'s client (`film.py`, audio
  dropped, sizes checked against `/object_info`); a reader trained for that character on DINOv2 from
  Blender renders of its own rig (`render_dataset.py`, `train.py`, `detect.py`, `--device`, bf16
  only on CUDA, training refused on Apple GPUs); a solve that triangulates the two views straight
  onto the character's skeleton with joint limits in an anatomical frame, no retarget (`solve.py`);
  and two gates handed to `motion_metrics.py`: two-view agreement at least 0.8, read only on the
  frames where a foot reads at confidence 0.3 or more in both views, and reprojection p95 at most 8
  px at 768 px height, read as the median over joints. `exam.py` builds a synthetic motion with
  known truth to score a solve in centimetres; `--compat-anymove` reproduces the upstream solve
  exactly. The acceleration weight defaults to 0.005 for humanoids (0.02 in compat mode). The
  upstream cloud video call and LoRA training are not ported. H3 output carries `licence: {source:
  "minimax-h3-local", territory: {excludes: [US, EU, UK, KR]}}`.
- **`humanoid-motion` → `scripts/twocam/twocam.py`.** One runner in Python, the same on Windows,
  macOS and Linux, with a subcommand per stage in the order a person checks them: `prepare` → `ref`
  → `film` (look at the H3 take before anything is trained on it) → `dataset` → `train` → `capture`
  → `bake`. Blender comes from `--blender` or `BLENDER`; every child runs with
  `PYTHONIOENCODING=utf-8`. Exit 0 pass, 2 a gate failed (capture and bake carry on, so the overlay,
  the fit and the GLB are there to read), 1 refused or an error (the stage stops); the failed gates
  are named from each tool's own report, whether it marks a gate `ok` or `pass`, on stdout or in its
  `--out` file. `capture` runs detect and the solve with `--samples-out` on the same `--device`
  (auto by default), `motion_metrics.py` and the GLB; `bake` keys the rig, runs `contact_bake.py` in
  Blender with `--legs contract --rig-info rig_info.json --readings samples.json` and gates the
  baked samples, so an Auto-Rig Pro rig bakes under its own bone names and the video's pops stay out
  of the gated count. `bake` refuses a clip whose `samples.json` has no `reading_joints`.
  `bake --render` (`--samples`, `--engine`, `--device`) runs the new `blender/render_baked.py` on
  `baked.blend`: every frame from the layout's front and side cameras on the studio grey, into
  `baked/front/` and `baked/side/`, and with ffmpeg on the PATH `baked.mp4`, front | side, the
  take's own layout; gated on every frame written and on the encode. Every summary gives each
  step's `seconds`. `reference/two-camera.md` adds how to run long jobs on a Windows host.
- **`humanoid-motion` → `scripts/twocam/solve.py`.** `--samples-out` adds `sole_offsets` (each foot
  joint's rest height above the ground, from `rig_info.json`) and `reading_joints` with
  `reading_names` (the joints triangulated from the readings alone), so `motion_metrics.py` finds
  plants on the sole and tells the fit's pops from the video's. `--despike`, on by default, replaces
  a one- or two-frame pop the fit added with a slerp of the bone's local rotation between its
  neighbours and lists `despiked` bones and frames; `--no-despike` keeps the raw fit. `--device
  cpu|cuda|auto` (auto: CUDA when present, else the CPU); the fit runs in float64, which MPS lacks,
  so `twocam.py capture --device mps` reads on MPS and fits on the CPU. The agreement skips a foot's
  frames that read under confidence 0.3 in either view (a foot hidden behind the other) and reports
  `frames_used`; a foot needs at least 8 such frames and a quarter of the clip. When no foot has
  them the gate fails with no value and `unread` names the feet; `--agreement-min -1` turns it off
  after a person has looked at the overlay. A clip whose feet barely move leaves the gate out with a
  warning.
- **Training and rendering.** `train.py`: the dataset pickles, so DataLoader workers run under spawn
  on Windows; loaders are built once with persistent, pinned workers; batches travel as uint8 and
  are normalised on the GPU, with TF32, a fused AdamW and SDPA attention on CUDA. `--batch 20` and
  `--epochs` 20 from scratch, 12 with `--init` when not given, run in full: the cosine schedule
  spans them and `reader.pt` is always the best epoch. Early stops are off by default, since a
  reader stopped before the cosine ends reads video less well: `--patience N` (0) stops after N
  evals that improve the best by less than `--min-delta` (0.1 px), counted only after the 300-step
  warmup (`--warmup-steps`), because a warm start's held-out error rises while its rate warms up;
  `--target-px PX` stops at the first eval at or under PX, for a quick preview. `twocam.py train`
  passes `--epochs` and `--patience` only when given. `--cache` decodes the PNGs once into a uint8
  memmap, and every run closes its memmaps when it ends; `--init OLD.pt` warm-starts the next
  character from a reader with the same joint names, on about 1,000 new samples; `--follow` trains
  while the dataset still renders. `render_dataset.py` keeps render data between the front, the side
  and the next pose, renders 8 samples with the GPU denoiser by default, takes `--engine
  cycles|eevee|workbench` and `--png-compression`, and the runner splits the dataset over 3
  processes. Cycles stays the default: EEVEE rendered the set more slowly and its reader read the
  same clips no better; `workbench` is for the selftests. **Behaviour change:** each sample draws
  from its own seed, so a dataset is the same however it is split, but differs from what the same
  `--seed` gave before; metas already written are kept.
- **`detect.py`, `film.py`.** The detect selftest passes on Python 3.12 and Windows. `film.frames`
  counts frames with opencv, else `ffprobe -count_frames`; with neither, the gate is listed and
  fails instead of disappearing.
- **`humanoid-motion` → `reference/pipeline.md`, `scripts/bvh_io.py`.** The back half, numbered
  1–6: contact bake, loop cut, `motion_metrics.py`, FBX through `rig_gate.py`, Unity, and a ledger
  record whose `depends-on` link reaches the video, so the video's territory reaches every clip
  solved from it. A clip pack goes through `blender-retarget`, in place or with translation. Hands
  ship with a fixed pose by default (`reference/hands.md`). Text to motion is not in this release.
- **`humanoid-motion` → `scripts/contact_bake.py`.** Plants from contact probabilities or the shared
  detector, the foot point locked per plant with an analytic two-bone leg IK and blended over 3
  frames, on a BVH or on a Blender action; gated on `plants_found`, `contact_height_m`, `reach_m`,
  slide p95 and max and penetration; `--sample-only` measures. `--rig-info` reads the sole offsets
  from `rig_info.json` (a samples file's `sole_offsets` work too) and the baked samples carry them;
  its `twocam.contract_names` maps an Auto-Rig Pro rig's bones (`foot.l`, `toes_01.l`) to the
  contract, so `--legs contract` bakes such a rig, and a rig with other names and no map is refused.
  `--readings samples.json` carries the capture's `reading_joints` into the baked samples under the
  rig's names, a twist bone between two read joints placed between them, and `--readings-offset N`
  aligns them with a cut loop, so a pop the video has stays under `pops_in_source` after the bake.
  It imports `motion_metrics.py` from `skills/blender-retarget/scripts` by a path relative to
  itself, so the two skills ship together.

**Motion gates**

- **`blender-retarget` → `scripts/motion_metrics.py`.** One clip's joint positions
  (`motion-samples/1` JSON or NPZ): plant slide p95 and max, penetration, jitter (acceleration p95
  on the residual after a short moving average, default 20 m/s²), joint limits, the loop period and
  seam (the lag-profile and cut search of `sprite-from-video`'s `video_loop.py`, with joint distance
  in place of pixel distance), root drift, pops and `pops_in_source` (both counted per event),
  translation kept against the source scaled by `k`, and the two-view gates. Plants are counted per
  foot and in total, and gated as `plants_min_per_foot`. An NPZ carries the readings as
  `reading_joints` with `reading_names`, as JSON does. A foot that moves but finds no plant gets a
  warning. Exit 0 pass, 2 a gate failed, 1 refused. Confirm the jitter limit once per capture type
  on a clean clip before relying on it.
- **`blender-retarget` → `reference/rest-pose-and-conjugation.md`, `reference/route-bakeoff.md`,
  `reference/clip-sources.md`; `unity-animation` → `reference/motion-metrics.md`,
  `reference/foot-lock-and-prop-ik.md`.** Updated for translation, pops, sole offsets and the one
  plant sentence.

**3D sources**

- **`codex-visual` → `scripts/audit_3d_source.py`, `reference/image-to-3d-input.md`.** The
  turnaround audit compares the left and right side views' silhouettes, as drawn and with one
  mirrored, and fails two side views that face the same way; when both match it reports the facing
  as inconclusive. `--selftest` builds the silhouettes.
- **`comfyui-asset-generation` → `reference/image-to-3d.md`, `reference/comfyui-api.md`,
  `templates/four_view_background_removal_api.json`.** The four-view background removal wrote
  RGBA with the alpha inverted: `JoinImageWithAlpha` takes an InvertMask of `RemoveBackground`'s
  mask, while `ImageCompositeMasked` and `ImageCropToMask` take the mask as it is. `LoadImage`'s
  MASK is 1 where the image is transparent, so cropping on an alpha-cut input goes through an
  InvertMask too. The new template carries the corrected graph for all four views.
- **`comfyui-asset-generation` → `templates/pixal3d_*`, `templates/trellis2_*`,
  `reference/image-to-3d-tuning.md`.** The new defaults (70000 faces, remesh 768, texture 2048)
  and a preset ladder that gains two rungs: Compact (8000 / 384 / 1024, the old defaults) and
  Template (70000 / 768 / 2048, no `--set`), between Small, Medium, Large and Showcase. Every rung
  now names its texture size; Large sets only the face count and Showcase the face count and
  texture, on the template's 768 remesh. Raising the face count without the remesh adds no detail, and the remesh
  costs the time, not the face count. A preview rig takes the template's mesh as it is.

**Licences and the sales territory**

- **`art-asset-registry` → `reference/licences.md`, `scripts/registry_ledger.py`,
  `scripts/registry.py`.** An optional record field, `licence: {source, id?, territory}`, where
  territory is `worldwide` or `{excludes: [...]}` in ISO 3166-1 alpha-2 codes or `EU` (expanded to
  its members; `UK` reads as GB). It is separate from the existing `license` string, carried over on
  re-record and passed through by ingest from a producer's `record`. Known sources: local H3
  (excludes US, EU, UK, KR), hosted H3, footage the team shot itself and Auto-Rig Pro (worldwide).
  `check --json` reports the declared `territory`. Two negative fixtures, `bad_territory` and
  `bad_territory_upstream`, keep `tools/check-registry.py` able to fail on it.

**Routing**

- **`game-character-pipeline` → `SKILL.md`, `reference/start-gate.md`, `reference/routes.md`.**
  The start gate and the route detail move to `reference/`. S3 stays the local multi-view
  generation and the quality target no longer decides where the mesh is made; `mesh_check.py` gates
  every mesh before S6, keeping a back-to-back inner shell and sending a same-facing double layer
  back to S1 or S3; S6 is `character-autorig` (Auto-Rig Pro by default, the hand-built route or
  `blender-character-rig` as the fallback) and never a cloud rigging service; S7 and S8 take
  `humanoid-motion`'s two cameras or a clip pack. A third track, **upgrade**: after the demo is
  approved, a person chooses to have a paid cloud service (Tripo, Meshy) regenerate only the mesh;
  it re-enters at S4 and the mesh gate, is rigged locally onto the same contract through the same
  gates, and the demo's clips carry over unchanged. The Mixamo and rigging-service rows leave the
  route table.
- **`blender-retarget`, `blender-character-rig`, `unity-animation`, `comfyui-asset-generation`.**
  Their tables and Scope sections name `character-autorig` and `humanoid-motion`.

**The README**

- **`README.md` and the three translations in `.github/`.** The page opens with what the skills
  do and a banner of one character through four skills (concept art, 3D mesh, rig, deform check),
  then six requests in the courier-run setting and the skill that answers each, the install with
  required and optional tools apart, a two-camera motion clip, and how a request reaches a gate.
  The skills table keeps its stage groups, now folded, one line per skill linked to its
  `SKILL.md`. The images live in `.github/media/`.
- **`.github/CONTRIBUTING.md`.** The repo's own checks and its two manifest rules move here from
  the README.

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
