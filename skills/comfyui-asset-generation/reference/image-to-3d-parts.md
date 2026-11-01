# Image to 3D in parts — a head job registered onto the whole-body anchor

A whole-body multi-view job spends one job's budget (structure grid, remesh grid, image
conditioning, texture) on the whole character, so the head, about a fifth of the height, gets about a
fifth of it. A job for the head alone spends all of it there: ears, eyelids, lips and nostrils form, the
face texture reads, and the hair becomes a mesh of its own. The whole-body mesh is still generated
first. It is the **anchor**: its proportions set the rig contract and the demo's clips, and each part
is registered onto it and replaces its region, so those proportions carry over.

| Tier | Generated | Pieces | Use |
|---|---|---|---|
| `whole` | the anchor | one mesh | the demo; no plan file, nothing below applies |
| `three` | the anchor + one head job | body (the anchor, head cut off), head, hair (split from the head job) | showcase and ship |
| `fine` | `three` + both hands (§Hands); eyeballs by `eye_fit.py` after the assembly | body, head, hair, hand.R, hand.L | close-ups, ship with fingers |

A person picks the tier at G0 (`game-character-pipeline` → `reference/start-gate.md`). The assembly
(register, hair split, cut, seam, gates) is `blender-character-rig` → `reference/part-assembly.md`.

## The plan: `parts/1`

`ArtDirection/parts/<c>/<c>.parts.json`, with the work folders beside it (`views/<part>/`,
`gen/<part>/`, `paint/<part>/`, `assembly/`). Paths in it are relative to the plan; geometry is in the
anchor GLB's own frame (glTF: +Y up, front = the multi-view front view). Schema: `schemas/parts-1.json`.

| Keys | Written by |
|---|---|
| `tier`, a part's `preset`, `seam.mode`, `prompt_hint`, `prompt_hint_back`, `budget_share`, `split.delta`, `views.accepted` (`part_views.py --accept`) | a person |
| `anchor` (hash, frame fit, neck band, head height), `region_box`, `seam` heights, `views.boxes`, the keep masks | `blender-character-rig` `part_math.py plan` |
| `views.dir`, `views.sheet`, `views.colours`, `generated` | `scripts/part_views.py` |

Each writer rewrites only its own keys. A plan whose anchor file no longer matches
`anchor.glb_sha256` is refused: a new anchor means `plan` again.

```json
{
 "schema": "parts/1",
 "character": "courier",
 "tier": "three",
 "anchor": {
  "glb": "../../sources/courier_anchor.glb",
  "glb_sha256": "4be1f3c09d27a6e58b1d0c3f97e2a4d6815c0b7e9f3a2d4c6e8b0a1c3e5f7092",
  "frame": {"units_per_px": 0.001053,
            "offset_px": {"front": [511.8, 517.6], "left": [510.2, 516.1], "back": [511.2, 518.1], "right": [511.8, 516.1]},
            "iou": {"front": 0.92, "left": 0.92, "back": 0.92, "right": 0.91}},
  "bbox_min": [-0.376, -0.481, -0.121], "bbox_max": [0.375, 0.493, 0.118],
  "head_height": 0.150,
  "neck": {"band": [0.337, 0.343], "axis_xz": [-0.0005, -0.003], "radius": 0.030,
           "collar": true, "collar_top": 0.350}
 },
 "parts": [
  {"name": "body", "source": "anchor", "region": "body", "budget_share": 0.6},
  {"name": "head", "source": "generate", "region": "head", "preset": "Template",
   "prompt_hint": "spiky dark brown hair, a young face with brown eyes, bare neck",
   "region_box": {"y_min": 0.322, "y_max": 0.493},
   "seam": {"mode": "overlap", "cut_y": 0.338, "part_bottom_y": 0.322, "margin_frac": 0.1},
   "views": {"source": "clean-views", "box_side_px": 192,
             "boxes": {"front": [416, 32, 608, 224], "left": [409, 32, 601, 224],
                       "back": [414, 32, 606, 224], "right": [420, 32, 612, 224]},
             "dir": "views/head", "sheet": "views/head/sheet.png",
             "colours": {"hair": "#3b2c24", "skin": "#e2a982"}},
   "generated": {"glb": "gen/head/head.glb"},
   "budget_share": 0.25},
  {"name": "hair", "source": "split", "from": "head", "region": "hair",
   "split": {"method": "scalp-radius", "delta": 0.03}, "budget_share": 0.15}
 ]
}
```

Rules the tools hold beyond the schema (exit 1 with the reason): exactly one `source: anchor`; the
tier's region set (`three` = body, head, hair; `fine` = those plus either hand or both, each with its `wrist`; eyeballs come from `eye_fit.py`, not a plan part, and `eyes` or `accessory` parts are refused); a split's `from` names a generated part; a part that
carries hair (the head, or the source of a hair split) never takes `Large`; budget shares sum to at
most 1; `custom`, or a region outside the tier, is refused. `budget_share` is a fraction of the class's
`3D budgets` row (`unity-3d-models`), never a triangle count.

## Part views (`part_views.py views`)

```
python3 scripts/part_views.py views ArtDirection/parts/courier/courier.parts.json \
  --views Work/courier/clean --seeds 42,43,44
```

`--views` is S2's clean folder: one `*front*black*.png` and one `*front*mask*.png`, likewise for
left, back and right. Per generated part and view:

1. **Crop.** The plan's box: one side `L` (1.1 × the part's largest extent over the four views), the
   same rows in every view, x centred per view; padded with black where it leaves the frame. These
   boxes are also the registration's initialiser (scale `L / 1024`), so they come from the plan and
   are never redrawn by hand.
2. **Keep mask.** The plan's `views/<part>/keep_<view>.png`: the view mask where the anchor's head
   region is the nearest surface (a depth-tested raster), minus every other visible surface grown
   upward a little (`part_math.py plan --hood-grow`). The hood in front of or behind the neck is
   removed by geometry, never by colour.
3. **Neck prior.** The neck the hood hid is painted as a **shaded cylinder** (Lambert across the width,
   0.75–1.0 of the visible neck's colour), centred on the anchor's neck axis with its radius, from a
   little above the collar top (`--prior-lift`, a fraction of head height: the drawn hood sits higher
   than the low-res mesh's) down to `clip_row`, filling only what the keep mask dropped. Below the
   chin only the neck span is kept, and the plan's hanging hair (`views.hanging`: a ponytail kept to
   the part's bottom). Rows below `clip_row` (the part's bottom, `part_bottom_y`, about a tenth of the
   head height under the anchor's clean-neck band, or the foot of a covered neck) are black.
4. **Redraw.** Qwen-Image-Edit-2511 + Lightning through `mesh-texture-paint`'s `qwen_paint.py`, with
   the guide as **both** pictures, at denoise 1.0 (4 steps, cfg 1). The prompt asks for the same head,
   pixel for pixel, the shaded column painted as a straight bare neck cut flat at the bottom edge, no
   hood, and a true 90° profile in the side views. The back view has a prompt of its own: the back of
   the head, no face, and no `prompt_hint`. Asked for "the same face" over a guide of hair above a skin
   column, the model draws a face on the back of the head, every seed. It takes `prompt_hint_back`
   instead (a person writes what the back shows: `a navy peaked cap with a black band, the hair tied
   into a ponytail at the nape`); without it the model can drop a cap and draw hair. A view that keeps
   hanging hair over ≥ 1 % of its box is also told to keep it over the neck. The redraw is clipped flat
   at `clip_row`.
5. **Gates** per view, a failing view retrying the next seed:

   | Gate | Limit | Catches |
   |---|---|---|
   | `part.redraw_iou` | ≥ 0.90 against the guide's own silhouette (keep mask + prior) | a redrawn, re-proportioned head |
   | `part.redraw_colour` | ≤ 0.06 of 32 × 32 cells moved more than ΔE 20 from the guide | a face drawn on the back of the head, hair turned to skin: the silhouette passes, the content does not |
   | `part.neck_reach` | ≥ 0.85 of the neck span covered on the last row | a neck that slants up and stops short (C-shaped in the mesh) |
   | `part.neck_width` | 0.8–1.25 × the neck diameter | a neck drawn thin or as a collar |
   | `part.sharpness` | ≥ `--sharpness-factor` (5) × the guide's Laplacian variance | the blur coming back |

   **A near miss a person signs off.** When every seed of a view fails, look at its redraws; one that
   misses only by a little (`redraw_iou` ≥ 0.85, `neck_reach` ≥ 0.70, `neck_width` 0.70–1.40,
   `redraw_colour` ≤ 0.10, sharpness ≥ 0.6 × the factor) may be accepted:
   `views PLAN --part head --accept left:43 --accepted-by NAME --accept-note WHY`. The redraw already
   made from the same guide is gated again, not redrawn; the plan records `views.accepted.<view>` (seed,
   who, why, the failed values, the redraw's hash), the gates keep `pass: false` with `accepted`, and
   the report passes with `accepted_views` naming them. A farther miss is refused: regenerate or re-plan. The usual
   case is a covered neck in profile, where the drawn neck is narrower than the prior.

6. **Background removal.** The four redraws through `templates/four_view_background_removal_api.json`,
   upload names `<c>_<part>_<view>_r_<hash>.png`; `part.bg_area` (BiRefNet mask area over the redraw's)
   in 0.95–1.05, so dark hair is kept.

Outputs in `views/<part>/`: `front|left|back|right.png` (the black composites: the Pixal3D inputs and
`paint_loop.py --concept`), `sheet.png` (the four in a row: `--sheet`), `guide_*`, `redraw_*`, and
`part_views.gate.json` (gate/1). `views.colours` holds the hair colour (the top tenth of the front
silhouette) and the skin colour (the face centre), sampled for the hair split's colour test.

## Generation (`part_views.py generate`)

```
python3 scripts/part_views.py generate ArtDirection/parts/courier/courier.parts.json
```

One `templates/pixal3d_multiview_to_model_api.json` job per generated part at its preset
(`reference/image-to-3d-tuning.md`), unique upload names, the model kept loaded between parts and
freed after the last; then `scripts/inspect_glb.py` at the preset's face target and texture size.
Writes `gen/<part>/<part>.glb` and `generated.glb` in the plan.

- **Template** already shows the gain; Showcase adds sharpness at several times the file size.
- **Never `Large` on a part with hair**: its spikes shrink.
- The redraw is required for the hair split as well as for sharpness: flat, upscaled-only hair hugs the
  scalp and the split fragments.

Then paint the head like any generated mesh, with its own part views, into `paint/<part>/` (the
assembly takes `paint/<part>/<stem>_painted.glb` from there):

```
python3 ../mesh-texture-paint/scripts/paint_loop.py gen/head/head.glb --concept views/head \
  --sheet views/head/sheet.png --out paint/head --kind character --subject "character's head"
```

## Hands (tier `fine`)

`part_math.py plan --tier fine` adds `hand_r` and `hand_l` (`hand_parts.py` measures them:
`blender-character-rig` → `reference/part-assembly.md` §7). `part_views.py` hands every hand part to `scripts/hand_views.py`;
the commands stay the same, `--part` takes a comma list:

```
python3 scripts/part_views.py views    ArtDirection/parts/courier/courier.parts.json --views Work/courier/clean --part hand_r,hand_l
python3 scripts/part_views.py generate ArtDirection/parts/courier/courier.parts.json --part hand_r,hand_l --paint
```

- **Guide.** The crop where the plan's keep mask holds: the hand where it is the nearest surface, the
  sleeve near the cuff grown half a forearm radius toward the hand (the drawn cuff hangs lower than the
  mesh's). The forearm the sleeve hid is a **shaded cylinder** of 0.8 × the forearm radius with a flat
  end at the part's bottom plane, painted in the visible forearm's colour where the keep mask dropped
  pixels. `prompt_hint` names the glove (`a fingerless orange and black glove with a black wrist strap`).
- **Redraw.** The prompt asks for pure black gaps between the fingers (cloth between them is
  background) and a bare forearm cut flat, no sleeve. Only the three views that see the hand are
  redrawn; the **hidden view** (the right hand's left view) is the source's redraw flipped, its box
  mirrored. Asked for a palm, the model keeps the back of the hand and can leave a grey ghost hand.
- **Gates** per view, a failing view retrying the next seed:

  | Gate | Limit | Catches |
  |---|---|---|
  | `part.redraw_inside` | ≥ 0.98 of the redraw within 6 px of the guide's silhouette (1024 px); the stub's corridor (one sleeve radius around the prior) not counted | a redrawn, moved or fattened hand |
  | `part.redraw_cover` | ≥ 0.85 of the guide within 6 px of the redraw | a hand cut short, fingers dropped |
  | `part.redraw_colour` | ≤ 0.06 of the 32 × 32 cells inside both silhouettes (the prior left out) moved > ΔE 20 | a ghost hand, a recoloured glove |
  | `part.sharpness` | ≥ `--sharpness-factor` × the guide's | the blur |

  IoU is the wrong gate here: the redraw rightly drops the cloth between the fingers, which the guide
  holds. A cell on a finger's edge mixes in that background, so the colour gate takes whole cells only.
- **Generate.** After each hand job, blender-character-rig `hand_parts.py gate` registers it onto the
  anchor (the head's limits: scale ± 5 %, RMS ≤ 3 % of the region height, rotation ≤ 6°) and counts
  fingers (`hand.fingers`: ≥ 4 separate sections in ≥ 30 % of 40 slices across the hand). On a failure
  the job runs again with every sampler seed moved, up to `--hand-seeds` (3) jobs: never loosen a
  gate. `generated.attempts` keeps each job's gates.
- **Paint.** `--paint` runs `mesh-texture-paint` `paint_loop.py --kind object --prior ''` on each
  passing hand into `paint/<hand>/`: the multi-view bake darkens an orange glove to brown; the paint
  loop takes the colour back from the redrawn views. The bake's own texture is not the context: it
  streaks the forearm grey and tints the palm olive, the model continues both, and with it a steep
  view comes back as another hand; the nearest painted colour reads cleanly. The palm carries the
  back's paint (the hidden view is a mirror).
- **Budget.** Each hand job keeps its preset's grid and texture but decimates to `--hand-ratio`
  (0.2) × the anchor's triangles (node 186), before it unwraps and bakes: a hand at Template's face
  count outweighs the body, and a collapse in Blender afterwards needs the mesh welded first, or it
  tears the textured mesh open along its UV seams (`blender-character-rig` → `part-assembly.md` §3).
  Template is enough: Showcase adds surface, not separation, at ten times the faces.

## GPU order and cost

One family at a time, the queue empty before every submission (`reference/operations.md`): every Qwen
redraw of every part with the model kept loaded → `/free` → BiRefNet → every Pixal3D part job →
`/free` → the paint loop (Qwen) → `/free`. `--wait-idle` waits for an empty queue on a shared server.

A part job fills its sparse grid, so it costs more than the whole body: about 2–3.5× the time and up
to twice the VRAM (a head job: 3–6 minutes, 12–17 GiB). `three` adds the four redraws (seconds each),
one BiRefNet job, one head job and one paint loop to the anchor: about 6–10 minutes of GPU time.
`fine`'s hands add six redraws, one BiRefNet job, a job per hand at its face target (about 2 minutes;
another on a failed gate) and a paint loop per hand (the longest step, about 10–15 minutes each).

## Avoid

- **Partial denoise**: the Lightning schedule returns the blur at any denoise below 1.
- **A full-body view (or the turnaround sheet) as picture 2** for the front and back: the face is
  redrawn slimmer and the head narrower. The crop itself is the reference.
- **Rectangle neck fills**: they become a box-shaped neck. Paint the shaded cylinder and let the redraw
  draw the neck.
- **Colour-segmented masks**: closing over colours fills real gaps; the keep mask is geometry.
- **Mirrored stand-ins for an occluded view**: the silhouette is right and the surface is wrong. The
  hands' hidden view is the one exception (§Hands): a palm asked of the model is worse.
- **`Large` on hair**, and **a seam plane read from view pixels**: the anchor's chin sits lower than
  the part's; the plan slices the anchor for it.
