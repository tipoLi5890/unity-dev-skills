# Concept match — how close the mesh is to its concept views

`scripts/concept_match.py` puts numbers on "does the finished mesh still look like the approved
concept". It renders the GLB from each S1 view direction, lines the concept view up with the
render, and measures outline, colours and two image embeddings. The numbers are **reported
only**: nothing passes or fails on them yet. A person still looks at `compare.png` and decides.

## 1. Run it

```bash
S=<repo>/skills/mesh-texture-paint/scripts
python3 "$S/concept_match.py" out/runner_r01/runner.glb \
  --view front=views/runner/front.png --view left=views/runner/left.png \
  --view back=views/runner/back.png --view right=views/runner/right.png \
  --view three_quarter=concept/runner_hero.png --out match/runner_s3 --tier whole
```

| Flag | Meaning |
|---|---|
| `--view NAME=PNG` | a concept view; NAME is `front`, `left`, `back`, `right` or `three_quarter`; repeat. Give at least one |
| `--out DIR` | the output folder |
| `--tier` | `whole` (the anchor mesh, the default), `three` or `fine` (an assembled GLB); recorded in the report |
| `--sims SIMS.json` | embedding similarities measured on another machine (§4) |
| `--embed` | measure the embeddings here; needs torch and transformers |
| `--device` | for `--embed`: `auto` (cuda, then mps, then cpu), `cuda`, `mps`, `cpu` |
| `--size` | the canvas of renders and views in px (default 512) |

Use the S2 RGBA cut-outs for the four views. A view without alpha is cut from its border colour;
a black view on black loses black parts at its edge (dark hair, boots).

## 2. What it does

- **Cameras.** The same as `paint_loop.py`: front yaw 0, left 90, back 180, right 270, pitch 0,
  the same orbit, field of view and fill. A left view means the same thing in both scripts. The
  frame is set from the bounding sphere so nothing is cut off.
- **The three-quarter image** has no fixed camera. Yaw 45 or 315 and pitch 0, 10, 20 or 30 are
  tried; the best outline wins. Within 0.01 IoU (a mirror of a symmetric body) the better colour
  match wins. The chosen yaw and pitch and each searched candidate are in the report.
- **Rendering.** The base colour, unlit, on a transparent background: texture × factor, a flat
  factor, or grey clay for a part with no material. An assembled GLB has every mesh primitive
  merged with its node's world transform, each with its own texture. A skinned mesh is read in
  its bind pose: its first joint's world matrix times that joint's inverse bind matrix, so an
  armature with its own rotation or scale stands up as it does in the engine.
- **Alignment.** The concept view is warped onto the render's canvas: one uniform scale and an
  offset that match the two silhouettes' bounding boxes, then the small scale and shift search
  `align_painted` uses, run on the two alpha masks. The scale is never stretched per axis, so a
  wrong proportion stays visible. A part at the outline's edge (a bag, a cap brim) on the wrong
  side moves the box, and the outline number then reads that shift too: it drops, never rises.

## 3. The numbers

| Number | Range | Better | What it reads |
|---|---|---|---|
| `silhouette_iou` | 0–1 | higher | the outline: pose, proportions, a missing or extra part |
| `palette_de` | ΔE ≥ 0 | lower | the colours: each palette is the figure's CIELAB colours in 4-unit cells, the rarest 3 % dropped; the mean distance from each colour to the nearest colour of the other palette, both ways, averaged |
| `dinov2_sim` | cosine, up to 1 | higher | shape and parts, as DINOv2 (`facebook/dinov2-base`) sees them |
| `siglip2_sim` | cosine, up to 1 | higher | what the picture shows and its style, as SigLIP 2 (`google/siglip2-base-patch16-224`) sees it |

Each view has its own row. `summary` gives each number's min and mean over the views. The report
`DIR/concept_match.json` is gate/1 with `pass: true` and these report-only gates (limit null):

| Gate | Value |
|---|---|
| `match.silhouette_iou_min` | the worst view's outline |
| `match.silhouette_iou_mean` | the mean outline |
| `match.palette_de_mean` | the mean colour distance |
| `match.dinov2_sim_min` | the worst view's DINOv2 similarity |
| `match.siglip2_sim_min` | the worst view's SigLIP 2 similarity |

A gate that was not measured has value `null` and is listed in `not_measured` as
`[{name, why}]`. Null means "not measured", never "passed". A clay mesh has no palette number. An
embedding gate, and its `summary` min and mean, is null unless every view has its value: a min
over some of the views could hide the worst one.

Reading them:

- The render is unlit and the concept is drawn with shading, so ΔE is never 0 on a real mesh.
  Compare runs of the same character: S3 against S3b, S3b against S5.
- The three-quarter image is a design picture, often in a livelier pose than the A-pose views.
  Its outline number is lower by nature; read its embeddings instead.
- The embeddings do not see a mirror: both models were trained on flipped pictures. A bag or a
  brim on the wrong side shows in the outline number and in `compare.png`, not in the cosines.
- One weak view with the others strong points at that side: look at its row in `compare.png`
  (concept, render, outlines: white both, red concept only, cyan render only).

## 4. Embeddings on another machine

The embeddings need torch and transformers. `DIR/pairs.json` is always written, with paths
relative to `DIR`, so the folder can be measured where a GPU is:

1. Run `concept_match.py` here. The embedding gates are null.
2. Copy `DIR` to the GPU host.
3. There, in a Python with torch and transformers, run `embed.py` on it.
4. Copy `sims.json` back and run `concept_match.py` again with `--sims`.

```bash
python3 <repo>/skills/codex-visual/scripts/embed.py --pairs match/runner_s3/pairs.json \
  --out match/runner_s3/sims.json --models dinov2,siglip2 --device auto
python3 "$S/concept_match.py" out/runner_r01/runner.glb --view front=views/runner/front.png \
  --view left=views/runner/left.png --view back=views/runner/back.png \
  --view right=views/runner/right.png --out match/runner_s3 --sims match/runner_s3/sims.json
```

Use a separate virtual environment for torch and transformers. A ComfyUI venv has them, but
never install packages into someone's ComfyUI venv. When the engine is missing, `embed.py` writes
`sims.json` with `engine: null`, every similarity null and a `reason`, and exits 3.
`concept_match.py --sims` then reports those gates as not measured.

`embed.py` exit codes: 0 measured, 1 usage error, 2 selftest failed, 3 not measured.
`concept_match.py` exits 0 whenever it writes a report (with `--embed` and no engine too: a WARN,
the gates null), 1 on a usage error, 2 when `--selftest` fails.

## 5. When to run it

| Stage | GLB | Tier |
|---|---|---|
| S3 anchor | the Pixal3D GLB | `whole` |
| S3b painted | `<stem>_painted.glb` | `whole` |
| S3c assembled | `<c>_rig.glb` | `three` or `fine` |
| S5 game mesh | the game mesh exported to GLB | the route's tier |

Run each stage against the same S1 views and keep each `DIR`. A drop from one stage to the next
shows where the character moved away from the concept. A person approves every stage as before;
these numbers help them look, they do not replace the look.
