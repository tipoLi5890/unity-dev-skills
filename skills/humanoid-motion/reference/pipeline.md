# The back half — from a keyed rig to a recorded clip

> Part of the `humanoid-motion` skill. The front half (the two-camera take, the reader, the fit,
> `twocam.py prepare` → `capture`): `reference/two-camera.md`.

The two-camera solve leaves the motion keyed on the character's own contract rig
(`unity-rigged-character` → `reference/humanoid-contract.md`), so there is no retarget. The back
half takes that keyed rig to a clip every contract character plays: contact bake → loop cut →
`motion_metrics` gate → FBX and `rig_gate` → Unity → ledger record.

```
runs/runner/clips/walk/motion.json ── twocam.py bake
  └ apply_motion --save keyed.blend ── contact_bake (Blender, --legs contract --rig-info) ── baked.blend
      └ motion_metrics on the baked samples ── loop cut ── gate on the cut
          └ FBX + rig_gate ── Unity ── registry (the clip depends-on the video)
```

A clip from a pack is not this route: it is retarget work, in place or with translation, in
`blender-retarget` (`blender-retarget` → `reference/rest-pose-and-conjugation.md`), and joins here
at the contact bake when its feet need locking.

## 1. Stages and gates

| # | Stage | Run | Gate before the next |
|---|---|---|---|
| 1 | Contact bake | `twocam.py bake`, or by hand: `blender -b keyed.blend -P contact_bake.py -- --armature RunnerRig --action ... --legs contract --rig-info rig_info.json --readings samples.json --out baked.blend --samples-out X.samples.npz` | exit 0: `plants_found`, slide p95 ≤ 1.5 cm, max ≤ 3 cm, `reach_m` |
| 2 | Loop cut | `motion_metrics.py X.samples.npz --state walk --loop` → `loop.start`, `loop.length`; set the action's range; `contact_bake.py ... --sample-only --frame-range` on the cut | exit 0: `loop_period_found`, `loop_periodicity`, `loop_seam_ratio`, `root_vertical_drift_m` |
| 3 | Gate | `motion_metrics.py CUT.samples.npz --state walk --pops-min-move 0.03` (no `--loop`: the cut is one period, its seam gated in 2; reading noise on a short segment is not a pop) | exit 0 |
| 4 | FBX | `blender-character-rig` `bcr_fbx` ops `snapshot` → `export` → `reimport` → `discard`, then `rig_gate.py` | `rig_gate.py` exit 0 (`bones`, `parents`, `action`) |
| 5 | Unity | `unity-rigged-character` `SharedSkeletonClipImporter.cs` on the clip folder | every binding resolves on every contract character |
| 6 | Record | `art-asset-registry` `registry.py ingest` of the video, then of the clip with `--link depends-on=<the video's id>` | `check` exit 0 for the declared sales territory |

Exit codes differ between tools, so read each one's own: `twocam.py`, `contact_bake`,
`motion_metrics`, `contract_map`: 0 pass, 2 gate failed, 1 refused. `rig_gate.py`: 0 pass, 1 gate
failed, 2 unreadable.

## 2. Commands, the runner's walk

The runner's walk was filmed, read and fitted with `twocam.py ... capture`, and its overlay and
`two_view_agreement` look right (`reference/two-camera.md`).

**1, the contact bake.** `twocam.py capture` exits 2 on `foot_slide_p95_m` by design: the solve's
feet are not locked yet. `twocam.py bake` keys the motion on the rig, saves `keyed.blend`, bakes
the legs and gates the baked samples; `bake --render` also renders `baked.blend` from the layout's
front and side cameras (`baked/` frames, `baked.mp4` beside the take when ffmpeg is on the PATH).
By hand, on the saved keyed rig:

```bash
S=<repo>/skills/humanoid-motion/scripts
blender -b runs/runner/clips/walk/keyed.blend -P $S/contact_bake.py -- --armature RunnerRig \
    --legs contract --rig-info runs/runner/rig/rig_info.json \
    --readings runs/runner/clips/walk/samples.json \
    --out work/runner_walk_baked.blend --samples-out work/runner_walk.samples.npz --report work/bake.json
```

`--rig-info` reads each foot joint's rest height above the ground (`twocam.ground`): an ankle stands
about 7 cm over its sole, so without it the ankle never comes under the 4 cm plant height and the
detector finds no plant in a clip that plainly steps. The report lists the offsets it used, and
`--samples-out` carries them (`sole_offsets`) to `motion_metrics`. A samples file that already has
`sole_offsets` (from `solve.py --samples-out`) can be given to `--rig-info` instead.

A rig whose bones carry other names (Auto-Rig Pro's `thigh_stretch.l`, `leg_stretch.l`, `foot.l`,
`toes_01.l`) is found through the same `rig_info.json`: `twocam.contract_names` maps each rig bone to
its contract name, so `--legs contract` and the contract-named ground offsets reach the rig's own
bones. `--readings` takes the capture's `samples.json` and writes its `reading_joints` into the baked
samples under the rig's names (a twist bone between two read joints is read at its place along that
segment), so `motion_metrics` keeps a pop the video has under `pops_in_source` instead of gating it.
Reading index 0 is the first baked frame; `--readings-offset N` shifts it.

Exit 2 names the gate. `plants_found`: the sole offsets are missing or the clip never stands still;
read the report's `sole_offsets`. `reach_m`: a foot is locked where the leg cannot reach (a plant
longer than the step; shorten it with `--min-frames` or cut that part of the take). Slide still
over the gate: read `slide_after_m.per_side` and the plants it names.

**2, the loop cut**, on the baked samples:

```bash
B=<repo>/skills/blender-retarget/scripts
python3 $B/motion_metrics.py work/runner_walk.samples.npz --state walk --loop --out work/loop.json
```

`loop.start` and `loop.length` index the sampled frames (sample 0 = the action's first frame F0).
Set the clip to the cut, closing on the frame after it so Unity's Loop Time wraps on an ordinary
step:

```python
act = bpy.data.actions["RunnerWalk"]
act.use_frame_range = True
act.frame_start, act.frame_end = F0 + start, F0 + start + length
act.use_cyclic = True
```

**3, the gate.** Sample the cut alone and gate it:

```bash
blender -b work/runner_walk_baked.blend -P $S/contact_bake.py -- --armature RunnerRig \
    --frame-range A B --legs contract --rig-info runs/runner/rig/rig_info.json \
    --readings work/runner_walk.samples.npz --readings-offset START \
    --sample-only --samples-out work/runner_walk.cut.npz
python3 $B/motion_metrics.py work/runner_walk.cut.npz --state walk --pops-min-move 0.03
```

with `A = F0 + start`, `B = F0 + start + length - 1`, `START = start` (the baked samples' readings
begin at F0). Leave `--loop` off here: the cut holds one
period, and the period search needs two (the walk window stops at half the clip), so it would
refuse a good cut. Stage 2 gated the period and the seam on these same frames.

A one-shot (a leap, a strike) skips the loop: cut it from the settle before to the settle after by
eye, and gate without `--loop`. A clip without travel for a controller is made in
`blender-retarget` (in place), not here.

**4–6** follow their skills. For 5, set `SharedSkeletonClipImporter`'s constants to the contract:
`RootNode` is the armature object's name in the FBX and `RootBonePath` is `RootNode +
"/Root/Hips"`, the one bone allowed to translate. Every contract character shares that skeleton,
so the clip plays on all of them unchanged.

## 3. The ledger record

| Asset | `licence` | Link |
|---|---|---|
| an H3 video on local open weights | `minimax-h3-local`, `{"excludes": ["US", "EU", "UK", "KR"]}` (`film.py` writes it into `film.json`) | its prompt and `ref.png`, `depends-on` |
| an H3 video run on fal | `fal-h3`, `worldwide` | same |
| the solved clip | none of its own | `depends-on`: the video |

```bash
python3 registry.py ingest --json runs/runner/videos/walk/s1/film.json --kind other \
  --source generated --write
python3 registry.py ingest --json runs/runner/clips/walk/solve.json --kind clip \
  --source generated --link depends-on=<the video's id> --write
```

Record the video first, then the clip with that link, so the clip carries the H3 territory without
copying it (`art-asset-registry` → `reference/licences.md`). `check` then fails an approved clip
whose chain excludes the declared `Sales territory:`; with `Sales territory: undecided` it warns.

## 4. When a gate fails

| Gate | Usual cause | Fix |
|---|---|---|
| `contact_bake` `plants_found`, or `motion_metrics` `plants_min_per_foot` | the sole is read at the ankle: no sole offsets | `--rig-info rig_info.json`; check the report's `sole_offsets` |
| `contact_bake` `reach_m` | a plant longer than the leg allows | `--min-frames`, or trim the take |
| `contact_bake` `contact_height_m` | with `--contacts`: contacts that disagree with the pose | bake with the detector (leave `--contacts` out) |
| `motion_metrics` `pops` | a one- or two-frame snap the fit added | `solve.py` despikes by default and lists `despiked`; a pop left after it on a long segment (upper arm, forearm, thigh, shin) is real: look at that frame in `overlay.mp4`, reroll or trim |
| `motion_metrics` `pops_in_source` (reported, not gated) | the readings snap too: the video model drew the limb jumping | look at the frame in the video; reroll the seed if it shows |
| `motion_metrics` `jitter_p95_mps2` | reading noise the fit passed through | raise `solve.py --acc-weight`; set the threshold once per source, never per clip |
| `motion_metrics` `loop_period_found` | under three strides in the take | film a longer take (or ask the prompt for more strides) |
| `two_view_agreement` | the halves were animated differently | reroll the seed (`reference/two-camera.md`, Limits) |
| `retarget.translation_kept` (a pack clip) | `translate: False`, or Hips not mapped | `blender-retarget` |
