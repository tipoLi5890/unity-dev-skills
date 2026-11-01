# Auto-Rig Pro's AI — body, finger and face markers from the user's licensed copy

> Part of the `character-autorig` skill. The stage order is in `SKILL.md`; the slice markers it is
> checked against are in `reference/markers.md`; the pipeline that writes the references onto the
> rig is in `reference/arp-pipeline.md`.

Auto-Rig Pro's Smart step can place its markers with a set of AI files: the body (chin, neck,
shoulders, elbows, wrists, hand tips, root, hips, knees, feet, head top), each finger joint, and
the face (eyes and lids, brows, nose, lips, jaw, cheeks, ears). Stage `smart` drives that step from
a script on the user's own licensed copy, then hands the result to the slice markers: the body is
cross-checked, the fingers and the face come from the AI. Without the AI files, or when a step
fails, the slice markers carry on alone, exactly as before.

## The licence and the AI files

Auto-Rig Pro is a paid add-on by Artell. Buy a genuine licence from the author's own stores,
[Gumroad](https://artell.gumroad.com/l/auto-rig-pro) or
[Superhive](https://superhivemarket.com/products/auto-rig-pro): it funds the add-on's development and
brings its updates. Documentation: <https://www.lucky3d.fr/auto-rig-pro/doc/>.

- **The AI files come with the licence**, downloaded from the store where it was bought. They are
  licensed per device: one machine per licence.
- **Install them with the add-on's own installer**, Preferences › Add-ons › Auto-Rig Pro › Install
  AI Files…, which also clears macOS's quarantine flag on the inference programs. An inference
  program that is blocked writes nothing, and `smart` fails `smart.ai_files`: reinstall through
  that button. This skill never lifts a quarantine flag, a signature check or any other OS
  protection.
- **Never copy them** into a project, this repository, a CI runner, a GPU host or another machine.
  Nothing of the add-on is copied here either: `arp_smart.py` calls its operators by name and
  refuses when a name is not registered, never guessing another.

## Why it needs a window

Every AI call takes its pictures from the 3D viewport (`render.opengl` on the open view), so
`blender -b` cannot run it. `arp_smart.py` opens Blender with a window on the normalised file, runs
the chain from a timer on that window's 3D view, saves the result and quits Blender itself, also on
an error or a timeout. The window freezes while the AI works. Keep one Blender per machine for the
run; it starts without `--factory-startup`, since that turns the add-on off.

Before the first call it turns off saving of preferences (quitting would otherwise store the run's
settings), sets the view's smooth transitions off, makes the scene's root collection active (the
add-on links its temporary cameras there), sets the viewport to **Material** shading, and refuses
a file that already holds an Auto-Rig Pro rig (Go! would open a dialog to pick one).

## The chain

| # | Operator | Does | Checked by |
|---|---|---|---|
| 1 | `id.get_selected_objects` (EXEC) | copies the mesh into the add-on's working body and hides the rest | the working body exists |
| 2 | `arp.guess_markers` | body markers from a front, side and top picture | all eleven `*_loc` markers and their mirrored twins exist |
| 3 | `arp.guess_fingers` | finger joints of the left hand, mirrored | `thumb1_loc` exists (a failure is a popup that raises nothing) |
| 4 | `id.facial_setup`, `arp.guess_facial`, `id.validate_facial_setup` | the face template projected onto the mesh | at least half the facial markers moved, validation raised nothing, mouth and eyes kept |
| 5 | `id.go_detect` (INVOKE) | builds the rig and places every reference bone: body, fingers, face | the rig's data holds the `has_match_to_rig` key (its value is False on success: test the key) |

Then every `*_ref` bone is read in edit mode as world positions (Go! scales the rig object, so a
head is `matrix_world @ head`), with its roll, parent and group (body, finger, facial). Go!
deletes the markers, so a copy of the file with them is saved just before it.

**Order and conditions that matter.**

- **Fingers before the face.** The face setup hides the working body the finger step needs.
- **Material shading for the face.** The face pictures carry the mesh's texture only in Material
  or Rendered shading. A generated mesh has its mouth and eyes in the paint, not the geometry: in
  Solid shading the lips go unseen, and the add-on silently drops the mouth and jaw.
- **Eyes on a generated mesh.** The add-on wants a separate eyeball object, which an image-to-3D
  mesh does not have. `--eyes proxy` (default) places a sphere behind each eye from the lid
  markers, points the add-on at them in its manual eyeball mode, and removes them after Go!;
  `--eyes none` turns eyes off (no eye or lid references). A character in parts with real eyeballs
  (`blender-character-rig` `eye_fit.py fit`, `autorig.py all --eyes <c>_eyes.glb --facial`) runs
  `--eyes objects`: the fitted balls go in instead of the proxies (moved by the prep's transform from
  `--eye-frame-glb`), so the eye references sit on the real balls; they too leave after Go!, and
  `eyes_bind` puts them on `c_eye.l/.r` after the rig.
- **The face rig is symmetric; a generated head is not.** Go! mirrors the eye references, so one eye
  bone can sit off its ball (about 0.2 × radius was seen). `eyes_bind` moves both eye bones, and every
  bone pivoting with them (lids, the eye target), onto the balls' centres. It also moves skin weights
  off the eye bones, so that only the ball turns with the gaze. In Blender the eyes are aimed with
  `c_eye_target`; Unity turns LeftEye / RightEye directly.
- **A face that fails** is cancelled before Go! (`id.cancel_facial_setup`, the proxies removed):
  Go! then still builds the body and the fingers, and `smart.facial` fails alone.
- **Errors come two ways.** A reported error raises in the script, in the user's interface
  language, so the text is never matched; a popup raises nothing. Every step is judged by the
  scene it leaves, never by a message.

## The command

```bash
blender Runner.blend -P scripts/arp_smart.py -- --mesh Runner --out rig/Runner.smart.json \
  --save-blend rig/Runner_smart.blend
blender -b -P scripts/arp_smart.py -- --probe      # headless: add-on, operators, AI files; no AI run
```

`--probe` prints `operators_missing`, the AI version and each inference program's state, and exits 0
when all is there, 2 when not. `autorig.py` runs the window as stage `smart` only when that probe
passes; `--no-smart` skips both. There the face runs only with `--facial`, and `--fingers` passes
through. The environment variable `ARP_AI_DIR` points one run (probe and window) at another AI
folder, set in memory only; an empty folder tries the fallback without touching the preferences.

| Option | Default | Does |
|---|---|---|
| `--save-blend` | none | the rig saved here for a person to look at, and the markers beside it (`_markers.blend`) |
| `--fingers` | 5 | how many fingers the AI fits: 5, or 4 (thumb, middle, ring, little: the add-on's four-finger hand has no index); 5 that fails is tried again with 4. The AI fits whatever count it is asked for and does not tell a four-fingered hand from five |
| `--facial`, `--no-facial` | on | the face step |
| `--eyes` | proxy | `proxy` or `none`, as above; `auto` lets the add-on find separate eyeball objects (a mesh that has them; it fails on a single-mesh character); `objects` takes `--eye-glb` and `--eye-frame-glb` (autorig passes them with `--eyes`) |
| `--body-samples`, `--finger-samples` | the add-on's | front pictures per body guess, hand pictures per finger guess |
| `--timeout` | 600 s | the whole chain; on a timeout the result is written and Blender quits. The inference programs are CPU-bound, so a busy machine is slow |

## The result (`autorig-smart/1`)

World space, metres, +Z up, facing −Y, `.L` on +X: the frame of `autorig-markers/1`.

| Key | Holds |
|---|---|
| `body_markers` | `root`, `neck`, `chin`, `head_tip` and the sided `shoulder`, `elbow`, `hand`, `hand_tip`, `thigh`, `knee`, `foot` `.L/.R` |
| `fingers` | `requested`, `count`, `fell_back` (5 failed, 4 used), `names`, and `markers` per joint (`thumb1.L` … `pinky4.R`, 4 the tip) |
| `facial` | whether it ran, the features the add-on kept, keypoints found, the eye proxies |
| `refs` | per reference bone: `head`, `tail`, `roll`, `group` (body, finger, facial, ear), `parent` |
| `rig_matrix_world` | Go!'s rig object, so a reader can check it holds no rotation |
| `steps`, `warnings`, `blend`, `blend_markers`, `elapsed_s` | each operator's seconds and error; what a person should look at; the saved files |
| `gates`, `pass` | gate/1 |

| Gate | Passes when |
|---|---|
| `smart.ai_files` | the AI files are a version the add-on accepts and the inference wrote its keypoints |
| `smart.body_markers` | all eighteen body markers placed (four central, seven per side) |
| `smart.fingers` | the finger markers exist (`thumb1_loc`) |
| `smart.facial` | asked for: at least half the facial markers moved, validation passed, the mouth and eyes kept |
| `smart.go` | Go! finished: the `has_match_to_rig` key |
| `smart.refs` | every body reference bone, the thumb when fingers were found, the jaw when the face passed |

Exit 0 every gate passed; 2 the AI ran and a gate failed; 1 refused or an error (add-on or AI files
missing, an operator not registered, no window, a timeout). `autorig.py all` never stops on
`smart`. Without the add-on or its AI files the probe skips the window and the exit code is
unchanged. A smart that fails makes the run's exit 2 and the run goes on: the markers stage gets
`--smart` whenever the window wrote a report, passed or not, and takes only what passed in it (a
failed face still leaves the AI's fingers); with no report it goes on from slices alone. `smart` run
on its own without the AI refuses (exit 1) and names the probe's failed gate.

## How the markers stage uses it: `arp_markers.py --smart`

```bash
blender -b Runner.blend -P scripts/arp_markers.py -- --mesh Runner --smart rig/Runner.smart.json \
  --out rig/Runner.markers.json --preview-dir rig/markers/
```

- **The body stays measured.** The slice markers keep the bend hints, the spine count and the
  symmetry gate. Each AI body marker is paired with its slice landmark in `smart_agreement`: the
  distance and the height difference as fractions of H, `agrees` within `--smart-tol` (0.03 H). The
  two methods put a joint at different depths (below), so the window is what decides, not the
  distance: a near miss, a landmark at most `--smart-tol` outside its window whose AI marker lies
  inside it, passes `markers.windows`, the gate carrying `confirmed_by: "auto-rig-pro-ai"`, the
  AI's heights in `ai` and `outside_by`, in place of a person accepting the body. A landmark
  further out, or one the AI puts outside too, fails as before: the pictures, `--adjust`, or the
  hand-built route.
- **The fingers come from the AI** when the slices could not part them (`fixed`: a glove, fingers
  held together) and the AI found them. Go!'s hand and finger references replace those in
  `arp_refs`, and the wrist (the AI's sits on the cuff, where Go!'s finger bases start) and the
  finger joints in `landmarks` follow, so `contract_bones` does too. `fingers.mode` is `ai`, with
  `count`, `names` and the slices' own verdict under `fingers.slices`. A finger the AI did not fit
  (the add-on's four-finger hand has no index) keeps the fixed shape, so the contract still gets 30
  finger bones; a joint a person adjusted keeps its position. Fingers are `.l` only, mirrored.
- **The face comes from the AI.** Every facial and ear reference goes into `arp_refs` and `facial`
  is true; `.r` face references are taken as Go! placed them (it projects each side on its own), not
  mirrored. The pipeline turns the face (and the ears) on at the head and places each one
  (`arp.face_added`, `arp.refs_placed`), and the export carries the face bones; the contract maps
  the jaw (`c_jawbone.x`) as `Jaw`, and `autorig.py` adds the `jaw_open` deform pose
  (`--poses all,jaw_open`).
- **Rolls.** Every reference taken from Go! has its roll in `ref_rolls`, which the pipeline writes as
  it is instead of turning it with the hand.
- **A smart file that does not fit.** Body markers over 0.10 H from the slices on median (another
  mesh, or another frame): nothing is taken, `smart.rejected` is true and a note says why, and the
  slices carry on alone. A malformed file (another schema, a coordinate that is not three numbers,
  a rig matrix with a rotation) refuses, exit 1. A run that failed is noted in `smart`, and only
  what passed in it is taken.

## Where the AI and the slices differ by design

Read these off the pictures before taking either side:

- **Head top.** The AI's head top is the skull under the hair; the slices take the highest vertex,
  a hair spike included. A spiky or tall hairstyle raises H and pushes the slice shoulder below its
  window, which is the case the AI check exists for.
- **Shoulder.** The AI puts it at the top of the deltoid; the slices at armpit height, inside the
  joint.
- **Hips.** The AI's sit higher, near the waistband, closer to the anatomical joint; the slices sit
  just above the crotch. Both fall inside the hip window.
- **Chin.** On a face with a long nose the slice chin can land on the nose tip; the AI chin is the
  jaw.
- **Foot bank.** Go! puts the bank references on the heel line; the slice markers at the ball.
- **Brows.** A fringe over the forehead can catch the AI brows, in front of the lids: `warnings`
  names a facial reference that sits far in front of the face.

## When it fails

| What failed | Fix |
|---|---|
| refused: add-on or AI files missing | install them as above; the rig goes on from slice markers |
| `smart.ai_files`: no keypoints written | the inference programs are blocked or out of date: reinstall with Install AI Files…; never clear OS protections by hand |
| `smart.body_markers` | look at the saved markers file; rig from slice markers |
| `smart.fingers` | the hand is too small in the pictures, or the count is wrong for the character: `--fingers 4`, or keep the slice fingers |
| `smart.facial` | eyes: `--eyes proxy` (or `objects` with real eyeballs); the mouth dropped: the viewport was not in Material shading, or the face is not painted; else `--no-facial` |
| `smart.go` | Go! built no rig: a second rig in the file, or a face left half set up; rerun on a clean copy |
| timeout | a busy machine: run again when it is idle, or raise `--timeout` |
