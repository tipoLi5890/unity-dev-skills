---
name: humanoid-motion
description: >-
  Make humanoid clips from video onto the humanoid contract skeleton with two
  cameras: a front and a side view of the character in one frame, animated by
  local H3 image-to-video, read by a reader trained for that character and
  fitted straight onto its skeleton (twocam.py prepare, ref, film, dataset,
  train, capture, bake), then contact bake, loop cut, motion_metrics gates,
  FBX, Unity and a ledger record with the sales territory. Load for "two-camera
  mocap", "turn this move into an animation", "train the reader", "the solve
  pops", "feet slide", "lock the feet", "where to cut the walk loop". Rig:
  character-autorig; packs: blender-retarget; Unity: unity-rigged-character.
---

# humanoid-motion — a generated two-view take in, a gated clip on the contract out

A clip here starts as one video in which a front and a side view of the character perform the
move together, and ends as an action on the **humanoid contract skeleton**
(`unity-rigged-character` → `reference/humanoid-contract.md`), so every contract character plays
it unchanged. The front half solves the motion straight onto the character's own rig; the back
half cleans, gates and ships it.

> **The solve is raw material, never the clip.** Each stage has a gate that can fail, and a take
> that fails is re-rolled, re-filmed or trimmed, not hand-repaired. Nothing here retimes a clip or
> paints a pose.

## Which source

| The move | Source | Read |
|---|---|---|
| Any move for a contract-rigged character: walk, run, idle, a strike, a leap no actor can do, a Q-version body | **two cameras**: front + side reference → local H3 video → per-character reader → two-view triangulation → fitted to the rig, no retarget | `reference/two-camera.md` |
| A clip pack already has it | a pack, retargeted (in place or with translation) | `blender-retarget` |

## The front half — `scripts/twocam/twocam.py`

One cross-platform runner, one subcommand per stage, files under `runs/<character>/`. Blender comes
from `--blender` or the `BLENDER` environment variable (default `blender` on the PATH). Exit codes:
0 pass, 2 a gate failed (the runner carries on, so the overlay, the fit and the GLB are there to
look at), 1 refused input or an error (it stops).

| # | Subcommand | Once per | Writes | Look at before the next |
|---|---|---|---|---|
| 1 | `prepare` | character | `rig/rig_info.json`, `rig/twocam.blend` (the painted copy) | the solved bones and feet it lists |
| 2 | `ref` | character | `ref/ref.png`, the first frame | `ref.inside_frame`, `ref.on_ground` |
| 3 | `film` | move | `videos/<move>/s<seed>/h3.mp4`, `film.json` (its licence) | **the H3 take itself**: both halves in step, colours unswapped. A bad take is rerolled here, before an hour of training |
| 4 | `dataset` | character | `dataset/` | `dataset.in_view`, `dataset.written` |
| 5 | `train` | character (CUDA) | `reader.pt`: 20 epochs, or 12 with `--init` for the next character on about 1,000 new samples | `reader.val_mean_px` |
| 6 | `capture` | move | `clips/<name>/`: detect → `solve.py --samples-out` (despike on) → `motion_metrics samples.json --pops-min-move 0.03` → `apply_motion --glb` | `overlay.mp4`, `two_view_agreement`, `pops`; exit 2 on `foot_slide_*` is expected, `bake` locks the feet |
| 7 | `bake` | move | `apply_motion --save keyed.blend` → `contact_bake.py` in Blender, `--legs contract --rig-info rig_info.json` (its `contract_names` find an Auto-Rig Pro rig's bones) `--readings samples.json` → `motion_metrics` on the baked samples; `--render`: `baked.mp4`, front \| side | slide, `reach_m`, `contact_height_m`, `pops` (a pop the video has stays under `pops_in_source`) |

The prompt for `film` comes from `make_prompt.py` (one action sentence per clip). Training does not
run on a Mac; read and fit do. The stages, the frame, the reader, the fit and their gates:
`reference/two-camera.md`.

## The back half

| # | Stage | Run | Gate |
|---|---|---|---|
| 1 | Contact bake | `twocam.py bake`, or `blender -b keyed.blend -P contact_bake.py -- --armature RIG --action ACT --legs contract --rig-info rig_info.json --out baked.blend --samples-out S.npz` | exit 0: slide p95 ≤ 1.5 cm, max ≤ 3 cm, `reach_m`, `contact_height_m` |
| 2 | Loop cut | `motion_metrics.py S.npz --state walk --loop` → `loop.start/length`; set the action's range; `contact_bake.py ... --sample-only --frame-range A B` on the cut | `loop_period_found`, `loop_periodicity`, `loop_seam_ratio` |
| 3 | Gate | `motion_metrics.py CUT.npz --state walk --pops-min-move 0.03` (no `--loop`: one period, its seam gated in 2) | exit 0 |
| 4 | FBX | `blender-character-rig` `bcr_fbx` snapshot → export → reimport, `rig_gate.py` | `rig_gate.py` exit 0 |
| 5 | Unity | `unity-rigged-character` `SharedSkeletonClipImporter.cs`, `RootBonePath` = `<rig>/Root/Hips` | every binding resolves on every contract character |
| 6 | Record | `art-asset-registry`: the video with its `licence`, then the clip with `--link depends-on=<the video>` | `registry.py check` exit 0 |

Commands in full, the runner's walk worked through, and what each failure means:
`reference/pipeline.md`.

## Files

| Path | Role |
|---|---|
| `scripts/twocam/twocam.py` | the runner: `prepare`, `ref`, `film`, `dataset`, `train`, `capture`, `bake`; exit 0/2/1 |
| `scripts/twocam/` | the stages it calls (layout, skeleton, prompt, film, reader, detect, solve, exam, Blender scripts): `reference/two-camera.md` |
| `scripts/contact_bake.py` | host (BVH) or Blender (action): plants from contact probabilities or the shared plant detector, sole heights from `--rig-info` or a samples file's `sole_offsets` (rig bone names through its `contract_names`), `--readings` carried into the samples, foot point locked per plant, analytic two-bone leg IK, slide before/after through `motion_metrics`; `--sample-only` measures; exit 0/2/1 |
| `scripts/bvh_io.py` | BVH read/write/FK and Euler conversions for `contact_bake.py`'s host mode |
| `reference/two-camera.md` | the front half: the frame, the skeleton, the stages, the reader, the fit, the gates, the exam |
| `reference/pipeline.md` | the back half: commands, the ledger records, failures and fixes |
| `reference/hands.md` | the fixed hand poses a clip ships with |

```bash
S=<repo>/skills/humanoid-motion/scripts
python3 $S/bvh_io.py --selftest && python3 $S/contact_bake.py --selftest
blender -b --factory-startup -P $S/contact_bake.py -- --selftest-blender
```

`contact_bake.py` imports `motion_metrics.py` from `skills/blender-retarget/scripts` (the one plant
definition); keep the two skills side by side. It needs numpy only; the reader and the fit need
torch (`reference/two-camera.md`).

## Rules the route is built on

- **One skeleton.** The solve is fitted onto the contract rig itself; nothing downstream knows how
  the motion was made.
- **Look at the take before training.** `film` comes before `dataset` and `train`: a take whose
  halves drift apart is rerolled for a few minutes of filming, not discovered after the reader.
- **Translation is part of the clip.** The solve moves Hips; `Root` stays at rest until root
  motion is split off downstream.
- **Plant once, measure everywhere.** A plant is the shared definition (sole under 4 cm, under
  0.15 m/s ground-relative, 3 frames) or a contact probability ≥ 0.5. The sole is the joint's
  height less its rest height above the ground (`sole_offsets`), and the bake and the gate read the
  same plant.
- **A pop the video has is not the solve's.** `motion_metrics` reports a spike the two-view
  readings also show as `pops_in_source`, not gated; only a spike the fit added counts in `pops`.
  Both count one event per frame and joint, so a twist bone beside the shin is not a second pop.
  `solve.py --despike` replaces a one- or two-frame pop the fit added with a slerp of its neighbours
  and lists what it changed.
- **Hands are fixed.** Two views do not resolve fingers; the clip ships with a hand pose layered on
  (`reference/hands.md`).
- **The licence travels by link.** The video carries `licence`; the clip links to it with
  `depends-on`, so a local H3 video's exclusion (`minimax-h3-local`: US, EU, UK, KR) reaches every
  clip solved from it.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Turn this move into an animation; two-camera mocap | `reference/two-camera.md`, then `reference/pipeline.md` |
| The halves of the H3 take play out of step, colours swap, a limb vanishes | reroll the seed (`reference/two-camera.md`, Limits) |
| `reader.val_mean_px` fails; train the reader | `reference/two-camera.md` (Reader) |
| `two_view_agreement` fails | `reference/two-camera.md` (Gates): the views were animated differently; reroll |
| `pops` in the solve; `pops_in_source` | `reference/pipeline.md` §4 |
| Jitter on a clean overlay | raise `solve.py --acc-weight` (`reference/two-camera.md`, Fit) |
| Feet slide; no plant found | `twocam.py bake`; `reference/pipeline.md` §2 (`--rig-info`) |
| `reach_m` or `contact_height_m` fails | `reference/pipeline.md` §4 |
| Where to cut the walk loop; the loop pops at the seam | `reference/pipeline.md` §2 |
| A clip without travel for a controller | `blender-retarget` (in place) |
| Fingers flat or wrong | `reference/hands.md` |
| Can this clip be sold in the EU? | `reference/pipeline.md` §3; `art-asset-registry` → `reference/licences.md` |

## Scope — what this skill does NOT do

- **Installing models or GPU environments**: the user does it.
- **Rigging the character** onto the contract: `character-autorig` (Auto-Rig Pro), or
  `blender-character-rig` by hand.
- **Retarget internals** and pack clips (conjugation, `k`, in place, the bake-off):
  `blender-retarget`.
- **Generating video** (the ComfyUI server, H3 templates, the queue): `comfyui-asset-generation`.
- **Unity import, Avatars and masks**: `unity-rigged-character`; runtime foot IK and blending:
  `unity-animation`.
- **Text-to-motion**: not in this release.
- **2D sprite loops from video**: `sprite-from-video`.
