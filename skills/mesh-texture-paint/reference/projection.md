# Projection — cameras, texels, weights and coverage

`scripts/mvtex.py` is the geometry core (numpy, scipy and Pillow; no GPU rasteriser): it reads
the GLB, renders guides, registers painted views and back-projects them into the UV texture.
`scripts/paint_loop.py` decides which camera comes next. Defaults below are the flags' defaults.

## 1. Cameras

- **Perspective, fov 20°**, the conditioning Pixal3D's multi-view model was trained on, so a
  render reads like the views the mesh was made from. A camera orbits the mesh centre at a
  distance that puts the largest half-extent at `--fill 0.92` of the frame.
- **Convention:** Y up; yaw 0 sits on +Z and sees the **front**; yaw 90 sees the subject's own
  left (`left.png`); 180 the back; 270 the right. Pitch is positive from above.
- **Anchors first** (`--anchors`, `yaw:pitch` in order): `0:0, 45:0, 315:0, 90:0, 270:0, 135:0,
  225:0, 180:0`. The front comes first because the first view is painted from clay and sets the
  palette every later view is matched to; the three-quarters come before the sides because they
  share the most surface with the front.
- **Pitch band** `--pitch-range -40 50`: steeper cameras come back drawn at eye level (the model
  redraws a top-down view as a front), so they fail registration. The band also defines what
  counts as seeable (§6).

## 2. Visibility per texel

`uv_maps` gives every valid texel of the `--res 2048` texture a 3D position and a face normal. A
texel is visible from a camera when:

- it projects inside the frame and its depth is within **eps = 0.004 × bbox diagonal** of the
  z-buffer at that pixel;
- its normal faces the camera within **75°**. This cut also drops the inner shell of a
  double-shell image-to-3D mesh, whose normals point inward.

## 3. Weights

A visible texel under the painted mask takes weight

```text
w = view_weight × cos(angle)^4 × edge_falloff
```

- `cos^4` lets a head-on view win over a grazing one by a wide margin.
- **Edge falloff**: 0 within **2 px** of the silhouette or of a depth step inside it (a step over
  1 % of the diagonal, such as an arm in front of the body), rising linearly to 1 at **8 px**.
  Edge pixels are where the drawing and the render disagree most.
- **View weight**: 1 for a full-frame camera; a zoomed camera gets `min(3, full radius / zoom
  radius)` — it puts more pixels on each texel and should win.

The mask itself excludes pixels within 6 px of any outline disagreement between the painted view
and the render (`gates.md` §3).

## 4. Refine rule and colour match

`--refine 1.5`: a texel that already has paint only takes a new view whose weight beats **1.5 ×
the best weight it has had**. Without it, every later view blends in and the texture blurs
toward an average of slightly different drawings. `--refine 0` blends every view.

Before blending, each view is **colour matched** to the texture on texels both cover (at least
2000 of them, facing within 60°): a per-channel gain and offset from the 10/50/90 % quantiles. A
fit outside **gain 0.85–1.18 or offset ±25** is skipped as implausible (`match: skipped` in the
report): then the view painted different content there, and bending all its colours would spread
the error. `--no-match` turns this off.

## 5. Next-best view and zoom

When the anchors are done (`--no-nbv` stops here) the next camera is searched over **128
Fibonacci directions**:

- inside the pitch band, at least **20°** from every used camera;
- only directions where at least **5 %** of the visible surface is still unpainted;
- scored by the sum of `cos²` over the unpainted seeable texels it sees; the best wins.

The new camera **zooms** onto the unpainted region it sees (2–98 % percentile box of those texels),
never tighter than **25 %** of the mesh's largest extent; a box over 70 % of the full radius stays
unzoomed. Zoom is off on **thin meshes** — smallest extent under 15 % of the largest, such as a
flat sign or a thin prop: the model does not recognise a zoomed crop of a thin shape and paints
something else. `--no-zoom` turns zoom off everywhere.

## 6. Coverage and stopping

**Seeable** = texels any allowed camera can see: the union of visibility from the 128 directions
inside the pitch band. **Coverage** = painted seeable texels / seeable texels. Bottoms below the
band, crevices and an inner shell are not seeable and do not count against it.

The main loop stops at the first of:

- coverage ≥ `--target 0.97`;
- `--max-views 16` views tried (a rejected view counts);
- 3 rejected views in a row;
- the next-best view adds less than `--min-gain 0.003` of the seeable surface, or none is left.

Then the detail passes run. A worked example: a courier runner reaches about 0.88 of its seeable
surface in about 13 painted views; the courier backpack about 0.7, its underside and the inner
faces of the straps staying on the prior.

## 7. Detail passes — the head

`--detail head` (characters) adds three close-ups after the main loop: yaw **0, 40, 320**, pitch
5, aimed at the head — the top 16 % of the mesh height, centred 2 % of the height lower so the
face sits mid-frame — at 1.3 × the head's extent. Each uses the detail prompt and the front
concept view (`--detail-ref` to change it). Their zoom weight (often the cap of 3) beats the
earlier weight × 1.5, so they replace the face painted at full-body scale and give it sharp eyes
and mouth.

## 8. Fill, gutter and the finished texture

- **Unreached texels** keep the brightness-matched prior (`painting.md` §5), or the nearest
  painted colour without one. The coverage map shows them dark grey (seeable, not painted) and
  near-black (never seeable); painted texels are white.
- **Gutter**: every texel outside the UV islands takes its nearest valid texel's colour (a
  distance-transform push), so mip-maps and bilinear filtering do not pull the background into
  the seams.
- **Seam delta** in the report: the mean colour step between neighbouring painted texels whose
  best view differs — a seam between two views shows up here before it shows in a turntable.
- The finished GLB is the input GLB with only the base-colour image replaced; normal, occlusion
  and every other slot stay as they were. The image is written as PNG (`mimeType` set to match).
  A GLB with no base-colour texture, an external base-colour image, or one shared with another
  slot gets a new embedded image and texture for the base colour instead.

## 9. Resume

Every view writes `state.npz` (weights, colour sums, best weight, owner, seeable mask, view count)
and `report.json`. `--resume` with the same `--out` reloads both and skips cameras (and detail passes) already used;
rerun with the same mesh, `--res` and concept folder.
