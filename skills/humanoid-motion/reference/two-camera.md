# Two cameras, one generated video

A motion for a contract-rigged character, filmed by a video model from two cameras at once and fitted
straight onto the character's own skeleton: a walk, a run or an idle as well as what nobody can act
out in front of a phone (a chibi or exaggerated body, a superhuman leap, a stylised strike). The
reader is trained once per character; after that every move is one clip, read and fitted.

## Credits

- The two-camera method is [@CanItCode](https://www.youtube.com/watch?v=AS92HYsEBqo)'s: one frame
  holds a front and a side view of the same model, a video model animates both at once, and a joint
  has the same height in both halves, so two views pin it in 3D.
- The idea of a MiniMax H3 LoRA that keeps the two halves in step is
  [@Graalitoo](https://x.com/Graalitoo/status/2112548557576380659)'s. It is not ported (see
  [Not ported](#not-ported)).
- The code is ported from [patch-gg/anymove](https://github.com/patch-gg/anymove) at commit
  `7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e` under Apache-2.0. Each file's header names its upstream
  file and what changed; `THIRD_PARTY_NOTICES.md` at the repository root carries the licence.
- The reader's backbone is DINOv2 with registers (`facebook/dinov2-with-registers-base`, Apache-2.0).

## The frame

Every stage reads one layout from `rig_info.json` (`scripts/twocam/layout.py`):

| | default |
|---|---|
| frame | 1376 x 768: 16:9 at 768p, both sides multiples of 32 |
| front view (left) | 688 px, an orthographic camera at -Y looking along +Y at the face; image u grows with +X, the character's left |
| side view (right) | 688 px, an orthographic camera at -X looking along +X at the right side; u grows with -Y, so the runner faces right |
| ground | row 688; the 80 rows below are the floor band |
| scale | metres per pixel = height x 1.53 / 688: 2.6 m of frame above the ground for a 1.7 m runner, room for a leap with the arms up |
| studio | grey wall (128, 130, 134), lighter floor (152, 154, 158), a dark divider (34, 34, 38) |

x comes from the front view, y from the side view, height from both (weighted 0.25 front, 1 side).
Keep the frame fixed for a character: the reader, the calibration and the solve all assume it.

## The skeleton

The rig is the humanoid contract (`unity-rigged-character` → `reference/humanoid-contract.md`).
`scripts/twocam/skeleton.py` turns it into the solve's `rig_info.json`; `blender/prepare_rig.py`
does the same from the rigged character's real armature, so each bone's rest matrix keeps the roll
the rigging tool gave it.

- **Solved bones (22):** Hips (the solve's root: free rotation and translation), Spine, Chest,
  UpperChest, Neck, Head, and per side Shoulder, UpperArm, LowerArm, Hand, UpperLeg, LowerLeg, Foot,
  Toes. Root stays at rest; extract root motion downstream. Fingers stay at rest; put the fixed hand
  shape on after the solve.
- **Keypoints (27):** every solved bone's head, plus HeadTop, HandTip.L/R and ToesTip.L/R.
- **Feet:** Foot, Toes and ToesTip per side. Their rest heights are the ground term's clearances (a
  heel or a ball does not sink below where it stands at rest). Foot and Toes give the two-view
  agreement.
- **Limb paint:** left arm pink `#F53CD1`, right arm blue `#2F6BFF`, left leg yellow `#FFD21F`, right
  leg cyan `#19D3E0`, from the contract's .L/.R limbs. The colours keep the reader's left and right
  apart, and the prompt names them.
- **Limits:** Euler XYZ in an anatomical frame per bone, so they mean the same whatever the bone's
  roll: Y along the bone, X the body's left-right axis off the bone (world +Z for the clavicle), Z =
  X x Y. X+ swings a limb backward (hip extension, knee flexion, arm back) and bends the spine
  forward; for a leg Z+ adducts. The right side mirrors Y and Z. `skeleton.py limits` prints the
  table. When the fit stays short of a pose the clip clearly shows, read the overlay first; when the
  readings are right, widen that bone's range in `LIMITS_DEG` and prepare the rig again.

## Stages

`scripts/twocam/twocam.py STAGE CHARACTER ...` runs each stage in upstream's folder layout under
`runs/<character>/`, the same on Windows, macOS and Linux (pure Python; Blender from `--blender` or
`BLENDER`). Run them in this order: `prepare` → `ref` → `film` → look at the H3 take → `dataset` →
`train` → `capture` → `bake`. A take that is wrong (halves out of step, colours swapped, a limb
lost) costs a reroll, not a dataset and a reader. `RIGGED.blend` is the exported FBX imported into
an empty file with its transforms applied (`character-autorig` → `scripts/autorig.py` writes the
FBX), not the Auto-Rig Pro working file: that one's control and twist bones change the keypoints
and the paint, and a reader from another character then refuses it as `--init`. Times are budgets for planning on a desktop CUDA
GPU, not promises; time the first 100 samples and the first epoch on a new machine.

| Stage | `twocam.py` | Script | Writes | Budget |
|---|---|---|---|---|
| 1 prepare | `prepare CHAR RIGGED.blend` | `blender/prepare_rig.py` | `rig/rig_info.json`, `rig/twocam.blend` (painted copy) | seconds |
| 2 reference | `ref CHAR` | `blender/render_ref.py` | `ref/ref.png`, the first frame | a minute in Cycles |
| 3 prompt | | `make_prompt.py CHARACTER.json RIG_INFO.json "ACTION"` | `prompts/<move>.txt` | none |
| 4 film | `film CHAR MOVE SEED --server-label NAME` | `film.py run` → `comfy_asset_client.py` + `minimax_h3_i2v_api.json` | `videos/<move>/s<seed>/h3.mp4`, `film.json` | minutes per 5 s clip; one move per clip, two seeds |
| 5 dataset | `dataset CHAR` | `blender/render_dataset.py`, 3 processes | `dataset/<i>_{front,side}.png`, `_meta.json` (2,200 samples), `dataset_<k>.log` | about 9 min per 1,000 samples for one Cycles process at 16 samples; less at the default 8 with three processes |
| 6 reader | `train CHAR --cache` | `train.py` | `reader.pt` (the best epoch: weights, joint names, layout), `train.log` | under a minute per 1,000 samples per epoch at batch 20 with 12 GB VRAM free; 20 epochs from scratch, 12 with `--init` |
| 7 read | `capture CHAR VIDEO NAME` | `detect.py` | `clips/<name>/det.npz`, `overlay.mp4` | seconds per clip on a GPU; time one clip on a CPU |
| 8 fit | (capture) | `solve.py --samples-out` | `motion.json`, `samples.json` | under a minute on a CPU for 124 frames |
| 9 gates | (capture) | `blender-retarget/scripts/motion_metrics.py samples.json --pops-min-move 0.03` | `metrics.json` | seconds |
| 10 apply | (capture) | `blender/apply_motion.py ... --glb` | keyed rig, `joints.json`, `render/animation.glb` | seconds; renders extra |
| 11 bake | `bake CHAR NAME [--render]` | `apply_motion.py --save keyed.blend` → `contact_bake.py` (Blender, `--legs contract --rig-info --readings samples.json`) → `motion_metrics.py`; `--render`: `blender/render_baked.py` | `keyed.blend`, `baked.blend`, `baked_samples.npz`, `bake.json`, `bake_metrics.json`; `--render`: `baked/{front,side}/` frames, `baked.mp4` (front \| side, with ffmpeg) | seconds; a render of 124 frames, minutes in Cycles at 32 samples |

Stages 1, 2, 5 and 6 run once per character; 3, 4 and 7–11 once per move. After `bake` the back
half continues in `reference/pipeline.md` (loop cut, `motion_metrics`, FBX); the motion is already on
the character's own skeleton, so no retarget. Every stage prints one JSON summary and exits 0 when
every step passed, 2 when a gate failed (capture and bake carry on, so the overlay, fit and GLB are
there to read), 1 on refused input or an error (the stage stops there); each step reports its
`seconds`. `capture` exits 2 on the solve's `foot_slide_p95_m` by design: the feet are unlocked until
`bake` locks them, so read its other gates and go on to `bake`.

**Dataset.** Each sample draws from its own seed (`--seed`, its index), so a sample is the same
whichever process renders it, and a stopped run resumes where its metas end. Render data persists
between renders: the front and the side of a sample, and the next pose, reuse the scene's BVH. The
defaults are Cycles at 8 samples with the denoiser on the GPU, scale 0.6, PNGs written uncompressed;
`twocam.py dataset` splits `--count` over `--procs` processes (3) and the CPU threads between them,
and passes `--engine`, `--device`, `--samples`, `--scale` and `--png-compression`. Keep Cycles: in a
comparison on the same character, `--engine eevee` rendered the set more slowly and its reader read
the same clips no better (detect confidence, reprojection); `workbench` is for the selftests.
Uncompressed, a sample takes about 1.5 MB on disk (both views at scale 0.6), and `train --cache`
adds about 0.75 MB per view; plan the disk for the set before rendering it. `--png-compression`
1–9 writes smaller files and spends render time on it, worth it only when disk is short.

**Film.** `film.py run` sets the template's node 1 (the uploaded `ref.png`), node 7 (`prompt` from
the prompt file, `width` 1376, `height` 768, `length` 124: 5 s on H3's 17k+5 grid at 24 fps) and
node 8 (`noise_seed`), and names the server with `--server-label`, never its address. Confirm the
size before the first clip: `film.py object-info --out oi.json` saves the node's own width and height
min, max and step, and `film.py run ... --object-info oi.json` refuses a size it would not take. If
1376 is refused, use 1344 x 768 and set the same width in the character's `layout` before stage 1.
The prompt states silence, and the audio track is dropped (`ffmpeg -an`; without ffmpeg the file
keeps it, which detect never reads).

**Prompt.** One action sentence per clip, in the courier run's words:

```bash
python3 make_prompt.py runner.json runs/runner/rig/rig_info.json \
  "the runner crouches, leaps and throws a right punch at the top, then lands." \
  --out runs/runner/prompts/jump_punch.txt
```

`runner.json`: `{"name": "runner", "noun": "courier runner", "describe": "a lean courier in a grey
jacket, cargo trousers and trainers"}`. The template pins both halves to one moment from two locked
cameras, the model unchanged, the colours unswapped, the body count, the character centred.

**Reader.** DINOv2 ViT-B/14 with registers and a small conv head, one 128 x 128 heatmap per joint,
fine-tuned on the dataset's random poses laid on random backdrops and degraded like video (framing,
colour, blur, rescale, noise, JPEG). Samples whose index is a multiple of 25 are held out and read
unaugmented, so their error compares between epochs and runs. `--epochs` (20 from scratch, 12 with
`--init`) runs in full: the learning rate warms up over 300 steps, then follows a cosine over the
epochs, and `reader.pt` is always the best epoch, which the gate reads. Early stops are off by
default: a reader stopped before the cosine ends reads video less well (lower detect confidence,
higher reprojection). `--patience N` stops after N evals past the warmup that improve the best by less
than `--min-delta` (0.1 px); a warm start's held-out error rises while its rate warms up, so the
evals inside the warmup never count. `--target-px PX` stops at the first eval at or under PX, for a
quick preview reader only. `--cache` decodes the PNGs once into a
uint8 memmap in `dataset/.twocam_cache/` (rewritten renders are decoded again); `--follow` starts
training while the dataset still renders (the folder is read again each epoch); `--init OLD.pt`
warm-starts from another reader with the same joint names and refuses any other. Batches travel as
uint8 and are normalised on the GPU, with TF32, a fused AdamW and SDPA attention on CUDA.

**Fit.** Blender's forward kinematics in torch, every Euler angle squashed into its limits by a
sigmoid, fitted in both views at once. It scores the clip first (agreement, height gap, best lag) and
time-warps the front view onto the side view when that cuts the height gap by more than 15 %. It
starts from an analytic IK pose aimed at the triangulated joints, with the root from a weighted Kabsch
fit, and anneals a robust Cauchy reprojection loss from 40 px to 6 px over 1,500 Adam steps, plus
joint acceleration (weight 0.005; `--acc-weight`), angular velocity, a pull to rest and the ground
term. Raise `--acc-weight` when the joints jitter on a clean clip; lower it when a strike's hand lags
the overlay.

## Gates

| Gate | Script | Default | Fails when |
|---|---|---|---|
| `film.size_step`, `film.size_range`, `film.aspect`, `film.frames` | film | 32 step, the node's range, 16:9, 124 | before submission for size; after download for frames, counted by opencv, else `ffprobe -count_frames`; with neither the gate is listed and fails |
| `ref.inside_frame`, `ref.on_ground` | render_ref | | the character is cut off, or stands off the ground row by more than 3 px |
| `dataset.in_view`, `dataset.written` | render_dataset | 95 % | poses leave the frame; files missing |
| `reader.val_mean_px` | train | 8 px x H / 768 | the best epoch's held-out mean error is above it |
| `detect.calibration`, `detect.mean_conf_*` | detect | 0.3 | ECC did not lock the clip onto `ref.png`; the reader is unsure |
| `two_view_agreement` | solve, motion_metrics | >= 0.8 | the feet's heights do not correlate between the halves: the video model animated the views differently. Only frames where a foot reads at confidence >= 0.3 in both views count (`paw_agreement.frames_used`) |
| `two_view_reprojection_p95_px` | solve, motion_metrics | <= 8 px x H / 768 | per frame, the median over joints of the front left-right and the side error, averaged over the views, p95 over frames |
| `exam.mean_cm` | exam | 1 cm | the synthetic exam's mean joint error is above it |

Every script prints one JSON object (Blender scripts one `TWOCAM_JSON` line) and exits 0 when every
gate passed, 2 when a gate failed, 1 on refused input or an error. The agreement reads a foot only
on frames where both views are confident about it (0.3, detect's `--min-conf`): a foot hidden behind
the other leg in the side view reads at low confidence, somewhere else (on a hand), and those frames
would drag the correlation down though the views agree. A foot needs 8 such frames and a quarter of
the clip. A foot read confidently on fewer frames than that gives no correlation; when no foot is
left, the gate fails with no value and `unread` names the feet (reshoot, or after looking at the
overlay pass `--agreement-min -1`). A clip whose feet barely move (under 0.5 px of spread in both
views) gives no agreement either; the gate is then left out with a warning, and the clip is judged
by reprojection and the overlay.

`solve.py --samples-out` writes `motion-samples/1` with the `two_view` block (`agreement`,
`reprojection_px` per frame, `frame_height_px`), feet `Foot`/`Toes`, the segments and knee and elbow
limits, so `motion_metrics.py` gates plants, ground, jitter, limits and pops on the same clip. Two
more fields let it tell the fit from the video:

- `sole_offsets`: each foot joint's rest height above the ground (`rig_info.json` →
  `twocam.ground`). A foot's sole is the lowest of its joints' heights minus their offsets, so a
  plant is found though the ankle stands well above the sole. `contact_bake.py --rig-info` reads
  the same offsets.
- `reading_joints` (with `reading_names`): the joints triangulated straight from the two views'
  readings, per frame. A pop on a segment whose ends both have readings is compared with the
  readings' own segment speed: a spike the readings show too is in the video (a fast strike, a snap
  the model drew) and is reported as `pops_in_source`, not gated; only the spikes the fit added
  count in the gated `pops`. `contact_bake.py --readings samples.json` (passed by `twocam.py bake`)
  carries them into `baked_samples.npz` under the rig's own bone names, through `rig_info.json` →
  `twocam.contract_names`; a twist bone between two read joints (Auto-Rig Pro's `leg_twist.l`) is read
  at its place along that segment, so the bake keeps the same split. `pops.count` and
  `pops_in_source.count` are one per frame and joint: the twist segment turns with the shin, so
  their spike is one event (`segments` counts both).

`solve.py --despike` (on by default; `--no-despike` turns it off) replaces a one- or two-frame pop
the fit added with a slerp of the bone's local rotation between the neighbouring frames, recomputes
the joints and lists what it changed (`despiked`: bone, frames). `twocam.py capture` also passes
`--pops-min-move 0.03`: a spike counts only when it moves the segment's end by 3 cm, which
reading noise on a short segment does not (the clavicle, Hips to Spine, Spine to Chest, Head to
HeadTop, Hand to HandTip, Toes to ToesTip). A gated pop left after that is the fit's: read the
overlay at its frames; on a short segment of a clean overlay raise `--acc-weight`. Spikes under
`pops_in_source` are judged on the overlay: keep them when the move should snap, reroll the seed
when the video glitched.

`two_view_reprojection` cannot see two views that disagree: the front view constrains only x, so any
front and side pair reprojects well. Only `two_view_agreement`, which reads the feet, catches a
disagreement, so a clip whose feet stay still while the arms differ between the views is judged by
the overlay alone; read it.

## The exam

Run it after preparing a character, and after any change to limits or the fit:

```bash
python3 exam.py make rig/rig_info.json truth.json --seed 7 --frames 124
Blender -b --factory-startup -P blender/apply_motion.py -- rig/twocam.blend rig/rig_info.json \
  truth.json exam --views front,side --engine workbench --paint
python3 exam.py det rig/rig_info.json exam/joints.json det.npz --noise-px 2   # a perfect reader, plus noise
python3 solve.py det.npz rig/rig_info.json solved.json
python3 exam.py score exam/joints.json solved.json                             # gate: mean <= 1 cm
python3 exam.py video rig/rig_info.json exam exam.mp4                           # the same motion as a clip
```

To see the agreement gate fail, film a second motion on the side view: `exam.py make` it with another
seed, `exam.py fk` it to `other.json`, then `exam.py det ... --side-joints other.json`; `solve.py`
exits 2 on `two_view_agreement`.

The made-up motion moves every bone inside its limits and keeps the feet above the floor. `det` skips
the reader, so the score isolates the fit; reading `exam.mp4` through `detect.py` with the
character's reader adds the reader's error. `solve.py --compat-anymove creature.json` fits an
upstream rig_info with upstream's names and constants, for comparing with upstream on its examples.

## Reuse

- **One reader per character, trained once.** Every new move is then `film` → `capture` (→ `bake`):
  one clip, read and fitted in minutes. A new mesh, outfit or proportion needs a dataset and a
  reader again.
- **The next character on the same contract** starts from the last one's reader: about 1,000 new
  samples, `twocam.py dataset courier2 --count 1000`, then `twocam.py train courier2 --init
  runs/runner/reader.pt --cache`, 12 epochs by default, a few minutes. The joint names must match
  exactly (`train.py` refuses others); the gate is the same as for a fresh reader. Leave
  `--patience` and `--target-px` off: a warm start's best eval is often its first.
- **Rendering and training at once:** start `train --follow` once the first few hundred samples
  are written; the samples rendered since join at each epoch.

## A Windows host

- Run the runner with the venv's interpreter: `venv\Scripts\python.exe twocam.py train runner
  --cache`. Blender comes from `--blender` or `BLENDER`, else `blender` on `PATH`, else the newest
  `C:\Program Files\Blender Foundation\Blender *\blender.exe`.
- A process started in an SSH session dies with it. Start long jobs (dataset, train) through WMI,
  which gives them no session, and follow their log:

  ```powershell
  Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine =
    'cmd /c "cd /d D:\twocam && venv\Scripts\python.exe twocam.py train runner --cache > runs\runner\train_console.log 2>&1"' }
  Get-Content runs\runner\train.log -Wait
  ```

- On a console in a legacy code page (cp950 and the like), set `PYTHONIOENCODING=utf-8` before
  running a script directly: otherwise a non-ASCII character in a path or a log line stops it with
  `UnicodeEncodeError`. The runner sets it for every child and never stops on a child's line.
- DataLoader workers start under spawn on Windows; `train.py`'s dataset is a module-level class
  that pickles, so `--workers 8` works there as on Linux, and every run drops its `--cache` memmaps
  when it ends, so the cache folder can be rebuilt or removed afterwards.

## Licence and the sales territory

Local MiniMax H3 runs on open weights under the H3 community licence, whose V.4 restricts outputs
outside its territory. `film.py` writes `licence: {"source": "minimax-h3-local", "territory":
{"excludes": ["US", "EU", "UK", "KR"]}}` into the clip's record (`art-asset-registry` →
`reference/licences.md`). Record the clip, then the solved motion with a `depends-on` link to it, so
the registry's territory rule reaches the motion without copying the licence:

```bash
python3 registry.py ingest --json runs/runner/videos/jump_punch/s1/film.json --kind other \
  --source generated --write
python3 registry.py ingest --json runs/runner/clips/jump_punch/solve.json --kind clip \
  --source generated --link depends-on=<the clip's id> --write
```

With `Sales territory: undecided` in `ART_DIRECTION.md`, `check` warns; when the declared territory
meets the exclusions, it refuses to approve the motion.

**Upgrade track.** When a move must ship where local H3 output may not, regenerate its clip on H3 Max
hosted on fal, under fal's terms (`fal-h3`, `worldwide`), from the same `ref.png` and prompt, record
it with that licence, capture it with the same reader and solve, and supersede the old clip. This is
a person's decision after the demo, not a gate's.

## Limits

- **Mac:** reading and fitting run on the CPU; training does not run on a Mac (`train.py` refuses
  MPS). Train on a CUDA machine and copy `reader.pt` back. Autocast to bf16 is used on CUDA only.
- **One reader per character.** A new mesh, outfit or proportion needs its dataset and reader again
  (warm-started with `--init`, see [Reuse](#reuse)).
- **What two orthographic views cannot see:** twist about a bone, a hand hidden behind the body in
  both views, fingers. Contacts with props or another character are not solved.
- **Video models drift:** the halves play out of step (the time warp catches a constant or slow
  lag), limb colours swap, or a limb appears or vanishes. Reroll the seed before tuning the fit.
- **Root motion:** the solve moves Hips; split travel onto Root in the shared cleanup.

## Not ported

- `mocap/fal.py` and `mocap/generate.py` (the fal queue client): filming goes through ComfyUI.
- `mocap/lora.py` and the LoRA set builder. To train a two-camera H3 LoRA later, confirm first that
  musubi-tuner's `--task fl2va` trains on the installed H3 weights and that the result loads in the
  `LoraLoaderModelOnly` node of `minimax_h3_i2v_api.json`; the dataset would be clips re-rendered
  from solved motions, so the halves are in step by construction. A LoRA on H3 carries H3's
  community licence.
- The fur springs of `apply_motion.py`, the showcase video, the mesh preparation and rig building
  (character-autorig and the contract replace them), and upstream's quadruped assets.
