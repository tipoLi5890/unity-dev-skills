# Part assembly — a generated head put back onto the whole-body anchor

For the `three` tier (body, head, hair). The anchor is the whole character from one image-to-3D job;
the head comes from a job of its own (`comfyui-asset-generation` → `reference/image-to-3d-parts.md`),
repainted with `mesh-texture-paint` like the anchor. The assembly registers the head onto the anchor,
splits its hair off, cuts the anchor's head away, seams the two and proves the result still has the
anchor's proportions, so the rig contract and the demo's clips carry over.

```
part_math.py plan  ->  part_views.py views / generate  ->  paint_loop.py (head)  ->  assemble_parts.py assemble
   -> autorig.py all OUT <c>_rig.glb --hair <c>_hair.glb   (its parts_bind step runs assemble_parts.py bind)
```

## Coordinates

Everything geometric in the plan is in the **anchor GLB's own frame**: +Y up, the character facing +Z
(the multi-view `front` view), the file's units. The Blender code converts at its boundary
((x, y, z) → (x, −z, y)). A view maps a point to px = cx + u / units_per_px, row = cy − y / units_per_px,
with u = x (front), −x (back), −z (left), +z (right).

## 1. Measure the anchor: `part_math.py plan`

```
python3 scripts/part_math.py plan ArtDirection/sources/runner_anchor.glb --views ArtDirection/views/runner/clean \
        --painted ArtDirection/sources/runner_anchor_painted.glb \
        --tier three --character runner --out ArtDirection/parts/runner/runner.parts.json
```

- **Neck band.** Slice the anchor downward from the head; the band is the run of heights where the
  slice holds one convex ring around the head axis (with at most its inner shell inside), at the
  narrowest radius (within 1.2 ×). A collar may sit around it but not touch it. Above the band the
  low-poly chin fuses onto the neck; below it the neck meets the hood or shoulders. No band (a raised
  hood, a helmet) → exit 2: `three` does not take that character.
- **Seam heights.** `cut_y` = band low + 0.2 × band length (the lowest height where the neck is still
  an isolated ring); `part_bottom_y` = band low − 0.1 × head height: the part's neck must reach this
  far, with a flat bottom. Never place a seam plane from view pixels.
- **Frame fit.** One scale for all four views (silhouette area against mask area, refined), an offset
  per view (the shift with the best IoU). Gate: IoU ≥ 0.90 per view, else the views are not this
  anchor's (exit 2).
- **Crop boxes.** Side L = ceil(1.1 × the head region's largest projected extent), even; rows shared
  by all views; x centred per view. The box is also the registration's start: scale L/1024, the box
  centre mapped through the frame.
- **Keep masks** (`views/head/keep_<view>.png`): per pixel, which anchor surface is nearest the camera
  (a depth-tested raster, head region against the rest). The mask keeps the head region where it is
  the visible surface, minus every other visible surface grown upward by `--hood-grow` × head height
  (0.08: a drawn hood sits a few pixels above the low-poly anchor's). A hood in front of or behind the
  neck is removed by geometry, never by colour; a plain projected silhouette keeps it.
- `--painted` records the S3b repaint as `anchor.painted_glb`; the assembly takes it over `glb`. The
  painted head is `generated.painted`, else `paint/<part>/<stem>_painted.glb` (run `paint_loop.py`
  with `--out paint/<part>`), else the generated GLB.

## 2. Assemble

```
blender -b --factory-startup -P scripts/assemble_parts.py -- assemble ArtDirection/parts/runner/runner.parts.json \
        --out ArtDirection/parts/runner/assembly
```

| Step | What happens | Gates (exit 2 when one fails) |
|---|---|---|
| Register | Start at the crop scale and box centre, unrotated. Trimmed ICP (point-to-plane; part points and anchor points both above the collar). A similarity fit checks the crop's scale; the applied fit is rigid at the crop's scale | `part.register.scale_ratio` \|s/s0 − 1\| ≤ 0.05; `part.register.rms` ≤ 0.03 of the region height; `part.register.rotation_deg` ≤ 6 |
| Split hair | On the registered, painted head (§3) | `hair.islands_returned` ≤ 0.10, `hair.components` 1–3, `head.top_closed` ≥ 0.95, `hair.coverage` ≥ 0.90 |
| Cut the anchor | Bisect at `cut_y`; delete the components above it whose rim lies in the neck disc (1.3 × radius), and floating islands above the collar (hair). A collar meeting the plane outside the disc stays | `part.cut.collar_kept` ≥ 0.99 of the collar's slice length between the cut and the collar top |
| Seam | `overlap` or `bridge` (§4) | `seam.centre`, `seam.tuck`, `seam.hidden` (overlap); `seam.loops`, `seam.gap` (bridge) |
| Seam colour | The part's neck takes the anchor's skin at the cut (§4) | `seam.colour`: just above the cut ΔE ≤ 6 to the anchor's rim, sharpest lightness step ≤ 12 per 0.1 radius (provisional) |
| Coverage | Rays from the anchor's rim toward the neck axis must meet the part (it fills the opening); rays from a sphere around the head must meet geometry | `part.coverage.rim` ≥ 0.98, `part.coverage.sphere` ≥ 0.99 |
| Proportions | Anchor against assembly, four views, 512 px; head rows reported | `assembly.silhouette.<view>` ≥ 0.95 (provisional); `assembly.head_extent_ratio` within ±5 % |

Why the applied fit keeps the crop's scale: the crop scale comes from the anchor's own projection, and
a redrawn head carries detail the anchor lacks (strands, a slimmer chin, ears). Trimmed ICP drops the
spike tips as outliers and pulls the scale down a few per cent, which shows as a smaller head
silhouette and a lower crown. The similarity fit still runs, and its scale gates the crop.

`compare.png` (whole body) and `compare_head.png`: columns front / left / back / right; rows anchor clay,
assembly clay, anchor textured, assembly textured (Workbench, back faces culled). A **person** reads
them before S6: the gates prove the geometry, not that the face is the character. `neck.png` (§4,
seam colour) shows the seam close up before and after the colour match.

## 3. The hair split

Under the spikes of a redrawn head lies a closed, hair-coloured scalp at a near-constant radius, so
removing the spikes leaves no hole.

1. Weld; the centre is the head's cross-section at 0.4 of the way from the chin to the top.
2. Scalp-radius map: per direction (36 × 72 bins) the smallest face distance, gaps filled, median
   filtered.
3. Hair = faces nearer (CIELAB) the plan's `views.colours.hair` than its `skin`, more than
   delta × part height outside the map, above the chin. No luma threshold: hair is not always dark.
4. Majority smoothing; pieces under 0.5 % of the hair go back to the head. `hair.components` counts
   the pieces holding ≥ 2 % (a few loose strands are hair; a split that shatters is not).
   Near the poles a row's bins are slivers, so a polar row takes its smallest radius everywhere
   (else the crown's hair reads as scalp).
5. Ladder: delta from the plan (0.03), then 0.05. Both fail → `Head` keeps the hair, the report says
   `degraded: "hair joined to head"`, exit 2. `--accept-joined-hair` continues with exit 0 and the
   failed gates kept, marked `accepted`: the hair is then in the rig mesh and the markers' height
   includes it again.

The hair keeps the head's material and UVs. A head that was only upscaled, not redrawn, has flat hair
hugging the scalp: the split shatters and the gates catch it. Light hair close to skin colour may not
separate by colour; the geometric term carries it, and the gates decide.

## 4. Seams

| Mode | When | How | Gates |
|---|---|---|---|
| `overlap` | Default with a collar (hood, high neckline) | The part's neck runs down inside the anchor's stump to `part_bottom_y` and is cut flat there; then centre and tuck (below) | `seam.centre` and `seam.tuck` ≤ 0.25 of the neck radius; `seam.hidden` ≥ 0.95: the part's flat bottom edge and the anchor's rim at `cut_y` both have geometry outside them on the outward horizontal ray (the other mesh, a coincident surface, or the collar). Reported: `seam.gap`, `neck_inside_stump` |
| `bridge` | Default without a collar; `--seam bridge` or the plan's `seam.mode` forces it | Both cut at `cut_y`; the inner shell deleted near the cut on both (ray test on the uncut mesh); the anchor's loop zipped to the part's with new faces on Body | `seam.loops` one per side; `seam.gap` mean ≤ 0.10, max ≤ 0.25 of the radius (provisional). Never bridged when a gate fails |

A hood that is open at the front hides the seam only at the sides and back, and the redraw draws a
neck of its own: its column may stand off the anchor's axis and its section is round where the
anchor's is not. Overlap therefore makes two bounded moves before it measures:

1. **Centre.** The part's neck axis (the centroid of its slice loop at three heights between
   `part_bottom_y` and `cut_y`, the median) is shifted onto the anchor's: fully at and below `cut_y`,
   fading to nothing one neck radius above it, so the face does not move. It runs before the hair
   split, so the hair moves with the head. Gate `seam.centre` ≤ 0.25 × radius.
2. **Tuck.** Along each ray from the axis, a vertex that stands outside the other mesh's outermost
   surface (cast inward, so an inner shell never answers) and that no collar or torso covers is
   pulled to 0.97 of that surface: the anchor's stump fully at its rim, fading to nothing at
   `part_bottom_y`; the part's flat bottom fully there, fading to nothing at `cut_y`. The two cross
   once in between; no step is left open. Gate `seam.tuck` ≤ 0.25 × radius for the largest move.

Over either limit nothing moves and the gate fails: that neck is a redraw failure (`part.neck_width`,
rerun the views), not something to hide. `bridge` is proven on synthetic
meshes only; read its renders closely.

**Seam colour.** The geometry can close while the colour does not: the head job paints its throat from
its own views (often a chin shadow running down the neck), the anchor's stump shows the full-body
paint, and texels the head's views never saw carry a fill. Under an open hood that reads as a lighter
band with a ragged top edge. After the seam moves, the assembly matches the part to the anchor:

1. Both sides sampled on their outer surface through their UVs (40 000 points each, the neck region
   within 1.8 × radius of the axis), skin only: within 35 CIELAB of the plan's `views.colours.skin`
   and nearer it than the hair colour.
2. A cylinder grid around the neck axis: 24 angles, rows 0.1 × radius. Per cell the difference of the
   two sides' medians (linear RGB). Target: the anchor at the same place below `cut_y`; at and above
   it, the anchor's rim (its skin from `cut_y` − 0.3 × radius to `cut_y`, per angle), because the
   stump is what shows beside the part's neck. A cell whose sides differ by more than 20 (CIELAB, the
   lightness term at a quarter: shade is allowed, another hue is not) is two materials, a scarf or a
   collar drawn on the neck: it stays 0. The grid is blurred around the neck, never in height.
3. The head's base-colour texels near the neck (its triangles rasterised in UV space, grown 2 texels)
   take the difference × weight: 1 up to `cut_y` + 0.15 × radius, fading to 0 at the chin (`neck.band`
   top, at least `cut_y` + 0.5 × radius) and from 1.3 to 1.8 × radius off the axis, so the face keeps
   its own colour. The image is repacked: the GLBs and the `.blend` carry it; the hair shares it and
   is untouched.

Gate `seam.colour` reads only the 30° sectors where the seam is in the open (an outward ray from the
part just above the cut meets nothing of the anchor but its neck within 3 radii); under a collar a
mismatch is never seen. Per sector, worst kept: ΔE between the part's skin just above the cut (to
+0.15 radius) and the anchor's rim ≤ 6, and the sharpest lightness step between 0.1-radius rows going
up from the rim through the part ≤ 12 (provisional); the values before the match are kept beside them.
No skin seam in the open (a covered neck, a turtleneck): the gate is skipped. `neck.png` shows the neck
close up, front and three-quarter, before and after. Lighting still differs: the anchor's low-poly
stump and the part's throat face the light differently, which no texture match removes.

The inner shell of an image-to-3D mesh is never deleted as a component: outer and inner stay
connected through thin spikes and ears. Delete it locally, near the cut.

## 5. Outputs and the rig

| File | Holds | Used by |
|---|---|---|
| `<c>_parts.blend` | Collection `Parts`: `Body`, `Head`, `Hair`, each its own material and vertex group `part.*` | a person; later tiers |
| `<c>_parts.glb` | The three meshes | display |
| `<c>_rig.glb` | `Body` + `Head` joined into one mesh, both materials | S6: `autorig.py all` |
| `<c>_hair.glb` | The hair alone, same frame | `autorig.py all --hair` → `bind` |
| `<c>.parts.gate.json` | gate/1: `degraded`, register, split tries, cut, seam, silhouettes, outputs | the ledger, a person |

The rig, in one command (`character-autorig`):

```
python3 skills/character-autorig/scripts/autorig.py all OUT ArtDirection/parts/runner/assembly/runner_rig.glb \
        --name Runner --height 1.70 --hair ArtDirection/parts/runner/assembly/runner_hair.glb
```

`prep` copies the hair to `OUT/<NAME>_hair.glb`; whenever that file is there, the contract stage ends
with `parts_bind`: `assemble_parts.py bind OUT --hair OUT/<NAME>_hair.glb --rig-glb OUT/<NAME>.glb
--name NAME --report OUT/rig/<NAME>.bind.json`. A bind that fails stops the run (exit 2) before
`deform`, which would otherwise gate an FBX without the hair. The first deformation gate, every
repair attempt and the spring chains then work on the rig with the hair; the chains leave it rigid on
`Head` unless `--hair-chains` asks for spikes on it (`character-autorig` →
`reference/secondary-chains.md`).

`bind` opens `OUT/rig/<NAME>_arp.blend` (backed up to `<NAME>_arp.pre_parts.blend`), recovers the rig
stage's import transform from `<c>_rig.glb` (scale from the z extents, shift from the minima; gate
`parts.transform_residual` ≤ 1e-5 × height), binds the hair rigidly (weight 1.0) to the contract's
`Head` bone read from `OUT/rig/<NAME>.contract.json` (gate `parts.hair_bound`), gives the hair the
head's material already on the rig (the import's `.001` copy dropped when its images match pixel for
pixel, so the FBX embeds each texture once), and re-exports the FBX through `blender-retarget`
`brt_arp` op export. It needs Auto-Rig Pro, so no `--factory-startup`.
Run by hand on a rig made without `--hair`, it changes the FBX after the deformation gate: run
`autorig.py deform OUT` again.

**H changes meaning.** The rig mesh carries no hair, so the markers' height is the skull top: spiky
hair no longer lifts the shoulder and neck markers. Pass `--height` as the skull top (the `whole`
height × the rig mesh's extent / the anchor's) to keep the metric scale, say so at G0, and compare
marker ratios against a `whole` rig with that in mind. Every marker found as a fraction of H moves
with it: read the knee and hip on the marker pictures again rather than reusing the `whole` run's.

**Ship track.** Preview and showcase keep the three meshes and three materials. For a mobile build the
parts merge into one skinned mesh with one atlas before S6 (tier `fine`); until then the ship track rigs
`<c>_rig.glb` with two materials.

## Failure → fix

| Symptom | Fix |
|---|---|
| `measure.neck_band` fails | A raised hood, a helmet or hair down to the shoulders: `three` is not for this character; stay `whole` |
| `part.register.scale_ratio` fails | The part views were cropped with another box than the plan's, or the job reframed the part: rerun `part_views.py` from this plan |
| `seam.centre` or `seam.tuck` over 0.25 | The redrawn neck stands far off the anchor's or is much slimmer: rerun `part_views.py` (another seed; check `part.neck_width`), never a larger limit |
| `part.coverage.rim` 0, `seam.hidden` empty | The part's neck stops above `cut_y`: redraw the views with the neck reaching `part_bottom_y`, flat at the bottom |
| `hair.components` many, `hair.coverage` low | The head was not redrawn (flat hair), or the colours are wrong: check `views.colours` against the sheet |
| `part.cut.collar_kept` low | The hood is fused to the head above the cut: the cut would take it. Check `compare.png`; a lower band or `whole` |
| `seam.colour` fails, cells refused | The head's neck is painted as another material (a collar, a scarf, a shadow in another hue): check the head's paint and `views.colours.skin`; repaint the head, never a larger limit |
| `assembly.head_extent_ratio` out | The head job's crown differs (lost or longer spikes): compare `compare_head.png`; regenerate at Template or Showcase, never Large on hair |

Avoid: a seam plane from view pixels; one plane assumed clean for both meshes without slicing both;
deleting the inner shell as a component; bridging a pair that failed its gates; Large on hair.
