# Layered 2D characters and scenes

A layered PSB/PSD is the shared format for two routes:

- **Unity 2D Animation** (the default, fully automatic): the PSD Importer, then
  `unity-2d-animation` → `reference/auto-rig-2d.md` puts bones, meshes and weights on it.
- **Live2D Cubism** (optional): the same art as a Cubism-ready PSD that a person rigs in the
  Cubism Editor. See `unity-2d-animation` → `reference/live2d-import.md`.

This skill makes the layers. `codex-visual` → `reference/layered-2d-source.md` draws the picture
they are cut from.

## 1. Which tool splits what

| Input | Tool | Why |
|---|---|---|
| A character | `scripts/layer_split.py`: a geometric cut plus Qwen-Image-Edit-2511 fills | Qwen-Image-Layered splits a figure by figure, background and colour, never by body part. Its own template says the prompt does not control what each layer holds. |
| A scene | `scripts/scene_layers.py`: Qwen-Image-Layered | It splits a scene by depth and fills what each layer hides: the sky behind the skyline, the shops behind the props. |

Both write a PSD/PSB with `scripts/psd_write.py`, which needs no Photoshop.

## 2. A character, end to end

The courier-run runner, drawn twice: once from the front, once from the side facing right.

```bash
S=skills/comfyui-asset-generation/scripts
# 1. key the concept (codex-visual); the fills step keys its own edits
python3 skills/codex-visual/scripts/key_unmix.py runner_front.png --out keyed/runner_front.png --edge tint
# 2. the fills, one job at a time on an idle queue (--cubism adds the blank face)
python3 $S/layer_split.py fills runner_front.png --view front --out front/fills --cubism \
  --hint "The jacket is teal with a grey chest stripe and a dark crossbody strap." --keep-loaded
python3 $S/layer_split.py fills runner_side.png --view side --facing right --out side/fills --cubism
# 3. the split, the rig file, the PSB for Unity
python3 $S/layer_split.py split front/fills/source_keyed.png --fills front/fills/fills.json \
  --out front/layers --psb Runner2D_front.psb
# 4. optional: the Cubism-ready PSD
python3 $S/cubism_psd.py front/layers --fills front/fills/fills.json --out front/cubism --name Runner2D_front
```

`split` can take the keyed concept from step 1 or the `source_keyed.png` that `fills` writes.
Both are on the same canvas.

### The fills (Qwen-Image-Edit-2511)

- **Graph:** `templates/qwen_image_edit_2511_fill_api.json`. The Lightning LoRA runs 4 steps at
  cfg 1. Picture 1 is also the latent, so the edit keeps its layout.
- **Square input:** every input is padded to a square with the painted key colour and scaled
  to 1024. A 2:3 input drifts the geometry; a square one stays aligned to the pixel.
- **Always edit the source:** never edit an edit. A second-generation edit drifts: the nose goes
  and the key field degrades. The blank face is one edit (hair, eyes, brows and mouth removed
  together), not the bald head edited again.

The fills:

| Fill | Input | Used for |
|---|---|---|
| `noarms` | the whole canvas | the torso under the arms (and without the held props) |
| `noprop_<name>` (`--props`) | the whole canvas | the body with that prop removed: the hand empty, what it covered drawn whole. One per prop: an edit asked to remove two removes one |
| `prop_<name>` (`--props`) | the whole canvas | that prop alone and complete, the character removed: its hidden parts |
| `bald` | the head crop | the head layer; brows complete under the fringe |
| `eyes_closed` | the head crop | the blink swap |
| `mouth_open` | the head crop | the talk swap; Cubism's mouth inside |
| `face_blank` | the head crop (`--cubism`) | Cubism's face |

**Gates** (`fills.gate.json`):

- `fill.aligned`: the 75th percentile of |RGB| in the zone that must not change ≤ 12. That zone
  is the head and the lower legs for `noarms`, the chin and collar for the bald and blank heads,
  and the whole head for the eyes and mouth.
- `fill.iou`: the silhouettes agree in that zone, ≥ 0.95.
- `fill.inside`: a head fill stays inside the source silhouette, ≤ 0.03.
- `fill.changed`: the closed-eyes and open-mouth fills change ≥ 1 % of the head box by more
  than 40. This only catches a fill that changed nothing; `split.swap_visible` checks the swap.

A failing fill retries the next of `--seeds`. The armless fill usually widens the jacket into
the gaps beside the arms. That is expected, because `split` clips it to the source.

### The split

The cut is geometric, never a body-part map. An edit-model part map follows clothing, not limbs:
a sleeve is coloured as the jacket.

- **Landmarks:**
  - **Neck:** the narrowest row of the armless fill in the top 8–30 %.
  - **Crotch:** the row where the two legs merge, followed up from the shins.
  - **Hem:** the row where most of the trunk's width changes colour at once.
  - **Ankle:** each leg's narrowest row near its bottom.
  - **Armpit:** the first row with three runs.
- **Arms:**
  - Below the armpit, each arm is an island of its own. An arm held out level (no island under
    an armpit row) is the part of the silhouette that sticks out of the torso fill, and its
    shoulder sits on that arm's axis.
  - **Shoulder joint:** 27 % of the way from the neck to the crotch, on the armless fill's edge
    (front view). In a side view, it is where the two arms' axes meet.
  - A capsule from the joint to the hand, with a round cap, takes the upper arm over the body.
    Any sleeve left over beside it joins the arm.
  - **Sleeve:** where the arm crosses the body, whatever lies over it there and is not in the
    forearm's palette (a strap, a buckle, a drawstring) or is a thick dark stroke is repainted
    from the sleeve around it. Otherwise the strap is cut out with the arm and swings with it.
    A band of the sleeve's own (an armband or a badge: it spans the arm and stops at the arm's
    edge instead of running on across the body) is kept.
    The side view's far arm is left alone, since it only keeps what shows.
  - **Wrist:** the narrowest cross-section at 50–80 % of the arm. The elbow is halfway.
- **Torso:**
  - The armless fill, clipped to the source.
  - Where an arm hides the torso's side, a straight segment bridges the visible edge above to
    the visible edge below.
  - The shoulder is rounded, and an outline in the source's outline colour is drawn where the
    new edge has none.
  - So a raised arm shows a round, outlined shoulder, not a straight cut.
- **Side view:**
  - The far arm keeps only what shows. Under the torso it is swept on to the shoulder, so a
    swing never opens a gap.
  - The layer order puts the far arm and leg last, under everything.
- **Head:**
  - The bald fill is the head, and the hair is what differs from it.
  - The eyes and mouth are the patches their fills changed. Each patch is written twice, once
    from the source and once from the fill, as a swap pair.
  - The torso is drawn over the head, so it is cut back from the eyes and mouth; on a hooded
    figure the neck row sits at mouth height and would otherwise hide the open mouth.
  - **Head pivot:** the bottom of the neck skin under the mouth (the face's skin, followed past
    the jaw line to the collar, at most 1.2 eye-to-mouth distances down), or the chin when no
    neck shows. The chin and neck go to the head layer, with a margin under the torso, so a
    turned head carries its chin. The narrowest row only decides where the torso layer starts:
    under a hood it is at mouth height.
- **Held props** (`fills --props "pole=the long wooden guard pole;shield=the round shield"`):
  - The body is cut from the source with each prop replaced by its `noprop_<name>` fill, so the arms,
    hands and legs behind a pole are whole.
  - Each prop is the layer `prop_<name>_<side>`: its visible pixels from the source, the parts
    the body hides from its `prop_<name>` fill. It is bound rigidly to the hand or forearm whose
    layer it touches most, or to the side named as `name@near|far|R|L`, and goes at the depth
    where the stack recomposites the source best.
  - Run the fills one prop at a time; an edit asked to remove two removes one. A thin prop
    whose removal fill re-poses the arm (no more than 40 px thick) is painted out along its
    track from the pixels around it instead. A prop whose `prop_<name>` fill fails keeps only
    what shows. `fills --only noprop_pole` redoes one fill.
  - **A far arm behind a shield** (`split --far-arm hidden`, chosen by a person): the far arm
    gets its bones but no layers, so a shield bound to it moves with it and no remnant of the
    shield is cut as an arm.
  - The arm still has to stand clear of the body. A prop held low at the hip pulls the arm
    onto the body; draw it held out in front (`codex-visual` → `reference/layered-2d-source.md`).
- **Overlap:** each lower layer runs `--overlap` px (22 by default) under the one above it at a
  joint.

Layer names are the contract, top to bottom:

| View | Layers |
|---|---|
| front | `hand_R arm_R hand_L arm_L torso hair_front eyes_open eyes_closed mouth_closed mouth_open head pelvis foot_R leg_R foot_L leg_L` |
| side | `hand_near arm_near torso hair_front eyes_open eyes_closed mouth_closed mouth_open head pelvis foot_near leg_near foot_far leg_far hand_far arm_far` |

- `_R` and `_L` are the character's own right and left, so `_R` is on screen left.
- `_near` is the limb in front, toward the facing direction.
- `eyes_closed` and `mouth_open` are written hidden.
- With `--props`, a `prop_<name>_<side>` layer per prop joins the stack where it recomposites best.
- **A renamed layer loses its rig in Unity.** Never rename one; if you must, run the auto-rig
  again.

`rig2d.json` (`rig2d/1`, `schemas/rig2d-1.json`):

- Image pixels, y down, flat arrays for `JsonUtility`.
- `bones[]`: `{name, parent, hx, hy, tx, ty}`.
- `parts[]`: `{name, bones, verts, indices, bw}`, where `bw` holds `i0, w0, i1, w1` per vertex.
  Two-bone smoothstep weights across each joint.
- `layers`, `view`, `facing`, `sides`, `swaps`, `joints` and `landmarks`.
- `unity-2d-animation` reads it.

**Gates** (`split.gate.json`, gate/1):

| Gate | Pass |
|---|---|
| `split.composite_iou` | ≥ 0.99: the shown layers against the source |
| `split.composite_px40` | ≤ 0.005: share of pixels more than 40 off |
| `split.alpha_clean` | ≤ 0.01: semi-transparent pixels 3 px or more inside a layer |
| `split.joint_overlap` | ≥ half of `--overlap` px at every joint |
| `split.names` | the view's full set, unique and non-empty |
| `split.limbs` | two arms and two legs (a hidden far arm counts by its bones) |
| `split.shoulder_notch` | where an arm moves away, a 12 px closing adds ≤ 0.1 % of the silhouette, and ≥ 0.7 of the uncovered edge is outlined |
| `split.mesh_cover` | 0 solid layer pixels left outside every triangle of the layer's mesh. An uncovered edge wedge shows as a background sliver in every pose |
| `split.sleeve_fill` | ≤ 0.25 of an arm's over-body pixels repainted. `composite_px40` leaves the repainted pixels out |
| `split.sleeve_own` | ≤ 0.05 of a sleeve's own band (armband, badge) repainted |
| `split.swap_visible` | ≥ 0.9 of each swap's changed pixels still show in the stack with the swap on. Eyes under hair are exempt |
| `split.head_pivot` | the head bone's pivot ≥ 0.5 eye-to-mouth distances below the mouth and above the armpit, and ≤ 0.05 of the chin and neck skin drawn by the torso |
| `split.prop_layer` | `--props`: each prop is a layer bound to one bone; ≤ 0.1 of its pixels still drawn in its colours by the body layers under it, ≤ 0.02 left with nothing behind it |

`pose.png` shows the rest pose and both arms raised 120°. Look at the shoulders: the gates see
notches and missing outline, not every odd shape.

### Draw it for the job

- **Front view:** for a portrait, a dialogue bust or a top-down game.
- **Side view:** for a side-scroller's run. A front view running in place reads weakly.
- **Draw limbs apart:** arms clear of the body below the armpit, legs apart. A held prop needs
  `--props`, and its arm held out clear of the body.

## 3. A scene (Qwen-Image-Layered)

```bash
python3 $S/scene_layers.py run street.png --out street --layers 4 --max-size 1024 --seed 5 \
  --names sky,skyline,shops,road,props --prompt "A flat cel-shaded side-scrolling street: ..."
python3 $S/scene_layers.py gate street.png --layers-dir street/raw --out street --names sky,skyline,shops,road,props \
  --scroll sky=0.04,skyline=0.15,shops=0.45,road=1,props=1.35
```

- **Graph:** `templates/qwen_image_layered_api.json`, the official template in API form: 20
  steps, cfg 2.5, euler/simple, shift 1. `LatentCut` drops the composite frame.
  - The prompt describes the whole picture, not the layers.
  - Use the fp8mixed weights: the bf16 file is larger than a 32 GB card.
- **Order:** layers come back back to front. An empty layer is dropped.
- **Band split:** a layer with a full-width transparent band of at least `--band` rows is cut in
  two. Typically that is sky above and road below. `--names` names the layers after both splits.
- **Ground cut:** the model can return the shopfronts and the road as one layer. A strip with a
  ragged top whose bottom rows are flat (few vertical edges: the median over column blocks, so a
  prop on the road does not count) is cut at the top of that flat band, so the shopfronts and
  the road scroll at their own speeds. `--no-ground-cut` keeps it whole.
- **Props:** the front layer's islands are also written one by one as `props/<name>_<i>.png`,
  each with its box.
  - `scene.json` marks that layer `role: props, tile: false`.
  - Place props as sprites in the level. Never tile or mirror them: a mirrored tile puts a prop
    beside its own copy.
  - The parallax rig in `unity-2d-rendering` → `reference/parallax-layers.md` reads
    `scene.json`. `--scroll` writes each layer's speed there (1 the play line, 0 fixed to the
    camera); the rig refuses a layer without one.

**Gates** (`scene.gate.json`):

| Gate | Pass |
|---|---|
| `scene.recomposite` | ≤ 8 mean \|RGB\| against the source. The model re-renders slightly. |
| `scene.coverage` | ≥ 0.99 |
| `scene.alpha_clean` | ≤ 0.03 interior semi-transparency per layer. A ghost layer fails. |
| `scene.depth_order` | where a back and a front layer overlap, the source matches the front one on ≥ 0.6 of the pixels |
| `scene.ground_split` | no strip left holding a built band over a flat ground band |
| `scene.props_whole` | ≥ 2 props clear of the left and right edges. The parallax rig leaves a prop cut by the frame out of its shuffle, and one prop can only repeat: draw the concept with every prop inside it |

## 4. PSD and PSB without Photoshop

`psd_write.py MANIFEST OUT.psb|.psd` writes 8-bit RGB with transparency, from Adobe's file
format specification:

- PackBits RLE and a merged composite.
- Per layer, `luni` (Unicode names), `lyid` (layer ids) and nested `lsct` groups.
- Hidden layers and groups.

Ids are kept in `ids.json`, keyed by name. A repaint re-exported with the same names keeps every
sprite id, bone and vertex in Unity. A renamed layer gets a new id here (Photoshop would keep
it), so Unity treats it as a new sprite with no rig: run the auto-rig again after a rename.

`psd_write.py read FILE` prints the layer tree from its own reader. The selftest writes both
formats, reads them back and, when `psd-tools` (MIT, optional, a validator only) is installed,
reads them with that too.

- **Unity:** use `.psb`, with the importer in character mode.
- **Cubism:** use `.psd`. Its manual documents PSD, not PSB.

## 5. The Cubism-ready PSD

`cubism_psd.py` follows Live2D's Editor manual:

- **Format:** 8-bit RGB, one part per layer, unique names, no masks or effects, normal blend.
- **Folders** follow the depth order.
- **Face, split on the 1024 px head crops** and scaled back with soft edges:
  - `face`: the blank fill.
  - Per eye, `eye_white_*` (drawn whole under the iris), `iris_*` (completed to its hull) and
    `eyelash_*`.
  - `brow_*`, from the bald fill.
  - `nose` (only when it differs from the blank face).
  - `mouth_line`.
  - `mouth_inside`, hidden in a `Mouth` folder.

**Gates:** composite IoU ≥ 0.99, ≤ 100 layers (the FREE edition's ArtMesh cap), unique names,
read back as version 1, 8 bit, RGB, and the mouth folder hidden.

What it cannot do: build the model. The ArtMeshes, deformers and parameters are made by a person
in the Cubism Editor. The Editor and the Cubism SDK come from Live2D (live2d.com), under
Live2D's licences:

- Never vendor or redistribute the SDK.
- Read Live2D's current terms before release, and buy the licence your project needs. The SDK
  is free to release for individuals and small-scale businesses, as Live2D defines them;
  everyone else signs a publication licence.

`unity-2d-animation` → `reference/live2d-import.md` covers the SDK side.

## 6. Housekeeping on a shared GPU

- **One family at a time:** run every fill (front, side, Cubism) in one family, with
  `--keep-loaded` on all but the last. Call `/free`, then run the layered scene. The two models
  are separate families.
- **The queue:** each job waits for an empty queue first, and nothing is queued behind another
  user's job.
