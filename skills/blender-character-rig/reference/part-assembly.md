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
- **A covered neck** (`anchor.neck.covered`, and a line in the output's `warnings`). When the ring goes
  on below the band no wider (≤ 1.2 × its radius) for ≥ 0.1 head heights with loops nested in it on at
  least half the rows (a stand collar fused to the jaw, hair fused to the nape), the band sits on the
  jaw and the anchor has no neck to measure. The plan says so, counts it a collar (seam `overlap`,
  `collar_top` = the band's low), and puts the seam under the collar: `part_bottom_y` reaches the
  cover's foot (the last height before the ring passes 1.5 × the radius), so the generated neck runs
  down inside the collar. The jaw and collar faces in that column are dropped from the keep masks but
  not grown upward (grown, they take the chin and the mouth), and in the side views the neck prior is
  a round neck whose back is the nape (`covered.nape_z`), not the jaw-deep band ring.
- **Hair hanging below the cut** (`views.hanging`). A piece of the faces between `part_bottom_y` and
  `cut_y` that meets the deleted head at the cut with most of that rim outside the neck disc (a
  ponytail, long locks; a collar or a hood meets kept faces there) is kept in the head's views down to
  `part_bottom_y` (`views/head/hang_<view>.png`), so the guide is not cut flat at the cut; the
  assembly keeps the anchor's own below the cut.
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
  neck is removed by geometry, never by colour; a plain projected silhouette keeps it. Over a covered
  neck the column's faces are not grown (above).
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
| Seam colour | The part's neck takes the anchor's skin at the seam, where the necks cross (§4) | `seam.colour`: just above the seam ΔE ≤ 6 to the anchor just below it, sharpest lightness step ≤ 12 per 0.1 radius (provisional) |
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
   The face is never hair, by geometry: within 35° of the front around the head's centre and below
   0.45 of the way from the chin to the top (lips and a mouth can read nearer a brown or red hair
   colour than the skin and stand out of the map). `split.tries[].face_share` reports its area.
4. Majority smoothing; pieces under 0.5 % of the hair go back to the head. `hair.components` counts
   the pieces holding ≥ 2 % (a few loose strands are hair; a split that shatters is not).
   Near the poles a row's bins are slivers, so a polar row takes its smallest radius everywhere
   (else the crown's hair reads as scalp).
5. Ladder: delta from the plan (0.03), then 0.05. Both fail → `Head` keeps the hair, the report says
   `degraded: "hair joined to head"`, exit 2. `--accept-joined-hair` continues with exit 0 and the
   failed gates kept, marked `accepted`: the hair is then in the rig mesh and the markers' height
   includes it again.

**To its share.** The head job spends most of its triangles on the hair (spikes are geometry), often
more than twice the face's. A smaller job would starve the face, so the split hair alone comes down
to its `budget_share`, before the rig: its share of the parts built so far may not pass its share of
their shares (`part_math.hair_target`: share / (sum of those shares − share) × the others' triangles;
body 0.46, head 0.22, hair 0.12 → 0.176 × body and head), so with the hands added later it stays
under its share of the whole. The hair is **welded first**, then Blender's collapse decimate runs:
the glTF import splits vertices along every UV seam, and a collapse of the split mesh opens each seam
into a crack, while on the welded mesh each corner keeps its UVs on its own side of the seam. Gates
`hair.reduce.tears` (open edges of the welded hair not more than before: a count, so a collapse that
closes old edges while it opens new ones can pass; provisional) and `hair.reduce.silhouette` (four
views, before against after, ≥ 0.95, provisional); reported in `hair_budget`. `--keep-hair-tris`
leaves it whole (a warning). Never reduce the merged or rigged mesh.

The hair keeps the head's material and UVs. A head that was only upscaled, not redrawn, has flat hair
hugging the scalp: the split shatters and the gates catch it. Light hair close to skin colour may not
separate by colour; the geometric term carries it, and the gates decide.

## 4. Seams

| Mode | When | How | Gates |
|---|---|---|---|
| `overlap` | Default with a collar (hood, high neckline) | The part's neck runs down inside the anchor's stump to `part_bottom_y` and is cut flat there; then centre and tuck (below) | `seam.centre` and `seam.tuck` ≤ 0.25 of the neck radius; `seam.hidden` ≥ 0.95: the part's flat bottom edge and the anchor's rim at `cut_y` both have geometry outside them on the outward horizontal ray (the other mesh at least 0.03 × radius out, or the collar; a coincident surface fights and does not count). Reported: `seam.gap`, `neck_inside_stump` |
| `bridge` | Default without a collar; `--seam bridge` or the plan's `seam.mode` forces it | Both cut at `cut_y`; the inner shell deleted near the cut on both (ray test on the uncut mesh); the anchor's loop zipped to the part's with new faces on Body | `seam.loops` one per side; `seam.gap` mean ≤ 0.10, max ≤ 0.25 of the radius (provisional). Never bridged when a gate fails |

A hood that is open at the front hides the seam only at the sides and back, and the redraw draws a
neck of its own: its column may stand off the anchor's axis and its section is round where the
anchor's is not. Overlap therefore makes two bounded moves before it measures:

1. **Centre.** The part's neck axis (the centroid of its slice loop at three heights between
   `part_bottom_y` and `cut_y`, the median) is shifted onto the anchor's: fully at and below `cut_y`,
   fading to nothing one neck radius above it, so the face does not move. It runs before the hair
   split, so the hair moves with the head. Gate `seam.centre` ≤ 0.25 × radius.
2. **Tuck.** The stump is first cut into 8 rows between `part_bottom_y` and `cut_y` (near the axis
   only), so it bends smoothly instead of per triangle. Along each ray from the axis, a vertex that
   stands outside the other mesh's outermost surface (cast inward, so an inner shell never answers)
   and that no collar or torso covers is pulled inside it. Covered means every ray of a horizontal
   fan (outward, ±35°, ±70°) meets the collar: a hood far out at the side covers the radial ray but
   not the front view. The anchor's stump goes to 0.90 of the part's neck along the **whole band**,
   from the rim down to the lowest 35 %, and comes back out over that 35 % to nothing at
   `part_bottom_y`; the part's flat bottom goes to 0.92 of the stump there, fading to nothing at the
   top of the same 35 %. The two cross once, low, at a clear angle. A stump about as wide as the
   part's neck must still go in: at 0.97 with a fade over the whole band the two necks sat within a
   millimetre and fought along a ragged line under the chin, the stump's pale top edge showing in
   the hood opening. Below the rim's quarter, a stump vertex more than 0.25 × radius outside the
   part is a flare (shoulders, a collar's foot) that covers the part: it stays. Gate `seam.tuck`
   ≤ 0.25 × radius for the largest move.

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
   two sides' medians (linear RGB). The seam height is where the necks cross after the tuck (overlap:
   per angle the highest height where the anchor stands outside the part, the median over the angles
   no collar covers; `seam_colour.seam_y`; bridge: `cut_y`). Target: the anchor at the same place
   below the seam; at and above it, the anchor's skin from the seam − 0.3 × radius up to the seam,
   per angle, because that is what shows beside the part's neck. A cell whose sides differ by more than 20 (CIELAB, the
   lightness term at a quarter: shade is allowed, another hue is not) is two materials, a scarf or a
   collar drawn on the neck: it stays 0. The grid is blurred around the neck, never in height.
3. The head's base-colour texels near the neck (its triangles rasterised in UV space, grown 2 texels)
   take the difference × weight: 1 up to the seam + 0.15 × radius, fading to 0 at the chin (`neck.band`
   top, at least the seam + 0.5 × radius) and from 1.3 to 1.8 × radius off the axis, so the face keeps
   its own colour. The image is repacked: the GLBs and the `.blend` carry it; the hair shares it and
   is untouched.

Gate `seam.colour` reads only the 30° sectors where the seam is in the open (an outward ray from the
part just above the seam meets nothing of the anchor but its neck within 3 radii); under a collar a
mismatch is never seen. Per sector, worst kept: ΔE between the part's skin just above the seam (to
+0.15 radius) and the anchor just below it ≤ 6, and the sharpest lightness step between 0.1-radius rows going
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
| `<c>_rig.glb` | `Body` + `Head` joined into one mesh, both materials (`fine`: and both hands, four, §7) | S6: `autorig.py all` |
| `<c>_hair.glb` | The hair alone, same frame | `autorig.py all --hair` → `bind` |
| `<c>_eyes.glb` | `Eye.L`, `Eye.R` (`eye_fit.py fit`, §6), same frame | `autorig.py all --eyes` → `eyes_bind` |
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

**Ship track.** Preview and showcase keep the parts and their materials. The ship track merges them
into one mesh, one material and one atlas per map **before** S6 and rigs once, on that mesh: §8.

## 6. Eyeballs (tier `fine`): `eye_fit.py`

A generated head has its eyes in the paint, on a nearly flat surface, so the eyes cannot turn and
Auto-Rig Pro's face has no eyeball to fit. `eye_fit.py fit` puts a sphere behind each painted eye
of the assembled head and cuts the painted eye out in front of it; `bind` puts each ball on its eye
bone after the rig. Run `fit` after `assemble` (and the paint), before the rig:

```
python3 skills/blender-character-rig/scripts/eye_fit.py fit ArtDirection/parts/runner/assembly
python3 skills/character-autorig/scripts/autorig.py all OUT .../assembly/runner_rig.glb --name Runner \
        --height 1.70 --hair .../assembly/runner_hair.glb --eyes .../assembly/runner_eyes.glb --facial
```

`fit` (host Python, numpy and Pillow) reads the head primitive (material `<c>_head`) of
`<c>_rig.glb` and renders its front at head width / 1300 per pixel, with each pixel's face, 3D point
and texel:

- **Find.** Sclera is light and not warm (R − B < 55, lum > 120 of 255) on faces turned to the
  camera, in 0.2–0.8 of the head's height from the top. Pieces split by the iris group per side of
  the head's centre line. The eyes are the mirrored pair of groups, 0.05–0.30 × head width wide, and
  neither touches the centre line (teeth do). The opening is the convex hull of the sclera and the
  iris (the largest dark blob next to it, opened with a disk of 0.1 × lid width, which drops lash
  lines and lid shadow).
- **Sphere.** Radius 0.55 × the lid-corner width, Auto-Rig Pro's proxy rule. Axis: the mean normal of
  the faces seen in the opening. Centre: R behind the opening's most forward point, then moved so
  the lid edge rests on the ball (least squares on the rim, kept behind it), then pushed back along
  the axis until the skin ring around the opening cuts into the ball by at most 0.9 × the
  `eye.poke` limit.
- **Hollow.** Removed: faces seen in the opening whose centroid lies inside it and whose corners all
  lie on the ball's disc (along the axis and from the front). Also removed: faces no front view sees
  (an inner shell, a lid's underside) inside the ball, or in front of it on its disc. A face reaching
  past the disc keeps its paint, so the opening never shows what lies behind.
- **Texture.** Planar along the axis, 512 px: the painted opening projected onto the ball, the median
  sclera elsewhere. An equirect map would put the iris on the pole and blur it.

Gates (gate/1 `<c>.eyes.gate.json`, provisional):

| Gate | Passes when |
|---|---|
| `eye.found` | the mirrored pair is there |
| `eye.symmetry` | centre heights within 0.5 × radius, radii within 15 % |
| `eye.poke.<side>` | the skin ring (0.012–0.08 × lid width outside the opening) cuts into the ball by ≤ 0.02 × radius |
| `eye.rim_gap.<side>` | p90 of the lid edge's distance off the ball ≤ 0.25 × radius |
| `eye.removed.<side>` | 1 face up to 3 % of the head's faces removed |
| `eye.in_opening.<side>` | from the front, the ball is what shows on ≥ 0.98 of the pixels whose face was removed |

Only when every gate passes does `fit` write `<c>_eyes.glb`. Each eye has its own mesh, material and
PNG, with node extras `eye`, `centre`, `radius` and `axis`. `fit` also cuts the eye faces out of
`<c>_rig.glb` and `<c>_parts.glb`, with no importer round trip. It keeps the files `assemble` wrote
as `*.pre_eyes.glb`: a second `fit` starts from them, and an `assemble` after it replaces them.
Unless `--no-render`, it writes `eyes.png` for a person: front and 3/4, painted and with eyeballs.
`<c>_parts.blend` is not edited.

**Rig.** With `--facial`, the smart stage gives the eyeballs to Auto-Rig Pro's face detection
(`arp_smart.py --eyes objects`). The add-on then places `eye_offset_ref` from the real ball, and the
rig stage builds `c_eye.l` / `c_eye.r` there. `eyes_bind` (`eye_fit.py bind`, after `parts_bind`)
works like the hair's bind:

- It opens `rig/<NAME>_arp.blend` (backed up once to `<NAME>_arp.pre_eyes.blend`) and recovers the
  prep transform (`eyes.transform_residual` ≤ 1e-5 × height).
- It binds each ball with weight 1.0 (`eyes.bound`) to the contract's `Eye.L` / `Eye.R`.
  `contract_map.py` maps `c_eye.l/.r` to these extra roles: Unity's optional LeftEye / RightEye. A rig
  without a face has no eye bones; the balls then ride `Head`, and the report says `degraded`.
- It moves the skin's weights on the eye bones to their parents (`eyes.skin_off_eye_bone`): only the
  ball turns with the gaze. The face rig is mirrored and a generated head is not, so it also moves the
  eye bones onto the balls' centres, with every bone pivoting at them (lids, the eye target).
  `pivot_offset` and `pivot_offset_after` (× radius) report the move.
- It turns each eye bone ±`--turn` (25°) left, right, up and down, as Unity turns LeftEye / RightEye.
  The add-on's aim constraint and the lids' follow are muted meanwhile.
  - `eyes.follows_bone`: the bone turned by the angle, and the evaluated ball is its rigid motion.
  - `eyes.poke_turned`: what the turns add to the skin's cut into the ball is ≤ 0.02 × radius.
  - Reported: the cut at rest (hidden vertices count there too), and the cut with the lids following
    (Blender's own face rig).
- It re-exports the FBX through `brt_arp`. The balls are their own objects in it: the deformation
  gate picks the body by the bones it is weighted to, so they never stand in for it.

## 7. Hands (tier `fine`): `hand_parts.py`

A whole-body job fuses the fingers (0–2 of 40 slices across the hand show four separate fingers).
Each hand is generated as its own part (`comfyui-asset-generation` → `reference/image-to-3d-parts.md`
§Hands) and replaces the anchor's hand from the sleeve's cuff down. Run it on the `three` assembly,
before the eyes, into a folder of its own (same file names), then `eye_fit.py fit` and the rig on that:

```
python3 scripts/part_math.py plan ... --tier fine ...     # also measures both forearms (hand_parts.plan_hands)
blender -b --factory-startup -P scripts/assemble_parts.py -- hands ArtDirection/parts/runner/runner.parts.json \
        --assembly ArtDirection/parts/runner/assembly --out ArtDirection/parts/runner/assembly_fine
```

**Measured on the anchor** (the part's `wrist` in the plan):

- **Forearm axis.** Sections perpendicular to a first axis (the hand's outermost point toward the
  shoulder at chest height) are tracked up the arm. The axis is refitted through the forearm's section
  centroids, from the wrist (the narrowest single section with the palm before it) to the cuff, then
  measured again along it.
- **Cuff and wrist plane.** The cuff is the first section past the wrist wider than 1.4 × the forearm
  radius. The **wrist plane** is fitted through the cuff's edge in 16 sectors around the axis (the first
  step of the outer surface past the mid radius, at the cuff's own radius), so an angled cuff keeps its
  whole lip. Past 40° of tilt, or with fewer than 8 sectors, the plane is perpendicular to the axis.
- **Bottom plane.** The wrist plane moved 1.8 × the forearm radius into the sleeve: one forearm
  diameter of overlap, where the part's forearm ends flat.
- **Region, boxes, keep masks.** The faces past the plane in pieces no farther from the wrist than the
  hand (never the thigh beside it). Boxes are L × L on shared rows, covering the region and the forearm
  stub. The view the body hides takes the mirrored box and keep mask of the opposite side view.

**`hands`**, per hand, on `<c>_parts.blend`:

1. **Register** the painted part (`generated.painted`, else `paint/<part>/<stem>_painted.glb`), exactly
   as `hand_parts.py gate` did after generation: crop scale L / 1024 at the boxes' centre, then trimmed
   point-to-plane ICP onto the anchor's hand region (the head's limits).
2. **Cut** the part flat at the bottom plane.
3. **Budget.** The job was generated at `--hand-ratio` (0.2) × the anchor's triangles
   (`part_views.py generate` sets the face target), so nothing is reduced here. A hand over budget is
   welded and collapsed; a collapse on the imported mesh tears it open along its UV seams, and on a
   non-manifold mesh it stops short. All reduction comes before the rig binds.
4. **Gate** `hand.fingers` again on the hand as attached, against the slices of step 1.
5. **Remove the anchor's forearm and hand** past the wrist plane. The sleeve's faces past it stay: those
   with a corner past 1.2 × the forearm radius that connect to the sleeve above, so the hem's inner fold
   stays whole instead of leaving a ragged edge.
6. **Cap** the opening with a fan whose centre sits 0.2 × the forearm radius inside the sleeve. Its UVs
   point at a free block of the body texture, painted a **lining** colour: the sleeve's darkest tenth at
   the cuff, at 40 % brightness. Without a free block, the nearest texel in brightness is used. The cap
   never takes body texels, and no extra material is added.

| Gate | Limit | Catches |
|---|---|---|
| `part.register.*` | scale ± 5 %, RMS ≤ 3 % of the region height, rotation ≤ 6° | a part from another crop, a turned hand: generate again (another seed) |
| `hand.fingers` | ≥ 4 sections in ≥ 30 % of 40 slices, 0.55–0.95 of the hand's length | fused fingers, or a reduction that fused them |
| `hand.triangles` | ≤ `--hand-ratio` × the anchor's triangles | hands outweighing the body (two Template hands are half a character's triangles) |
| `seam.sleeve_clearance` | the part's radius at the wrist plane ≤ 0.8 × the opening's | a forearm as wide as the sleeve: the seam would show |
| `seam.hidden` | ≥ 0.95 of the part inside the sleeve, from half a forearm radius past the wrist plane to the bottom, hidden from 8 cameras (front, back, sides, four into the cuff 30° off its axis); nearer the cuff the forearm is seen going in, as on the anchor | a sleeve cut open, a cuff the plane missed, the cut end showing |

Outputs in `--out`: `<c>_parts.blend` (`Body`, `Head`, `Hair`, `Hand.R`, `Hand.L`, vertex groups
`part.*`), `<c>_parts.glb`, `<c>_rig.glb` (Body + Head + both hands, one mesh, each part's material),
`<c>_hair.glb`, `<c>.hands.gate.json` and `hands.png`: per hand, the anchor and the assembly, clay and
textured, front, three-quarter, side and from below the wrist.

## 8. Ship merge: `ship_merge.py`

The ship track's mesh from a character in parts: one mesh, one material, one atlas per map, made
**before** the rig (S6 rigs once, on it). `assemble_parts.py ship` runs the same script:

```bash
blender -b --factory-startup -P assemble_parts.py -- ship <c>_parts.glb --eyes <c>_eyes.glb --out ship/ \
    --plan <c>.parts.json [--atlas 4096|2048] [--separate hair] [--max-tris N]
    [--budgets ART_DIRECTION.md --class character] [--min-density 0.5]
```

- **Parts.** The mesh objects of a `.blend`'s collection `Parts` or of a `.glb` (or `--objects`), each
  with one material. The
  plan maps each object to its part by name or region (`Hand.R` → `hand.R`, `Eye.L` → `eyes`) and so
  to its `budget_share`.
- **Tiles, no rebake.** One square tile per set of images (Head and Hair share one: the hair is split
  from the head job). Each part's UVs are scaled and offset into its tile, uniformly and unrotated,
  so tangent-space normals still hold, and its texture is resized into the tile with 8 px of its
  border repeated around it, so mip levels do not bleed. A tile starts at its texture's side; while
  the tiles do not fit, the one with the highest texel density on the surface halves (mirrored L/R
  pairs together, never below atlas/16); then a tile that can grow back to its own side without
  breaking the fit does. On a 4096 atlas a `fine` character's four 2048 textures (body, head and
  hair, two hands) fit whole; one more tile halves the hands, still denser than the body; 2048
  halves everything again.
- **Maps.** Base colour; normal (flat for a part without one); ORM (occlusion, roughness, metallic:
  the glTF metallic-roughness and occlusion images, or the part's factors) when any part has one.
  `--atlas` 4096 for showcase and PC, 2048 for mobile; default the calibrated budget row's
  `target_tex_px`, else 4096. The FBX carries base colour and normal; Unity imports them at the
  folder's Max Size: set `maxTextureSize` 4096 in `character-pipeline.json` for a 4096 atlas
  (`unity-rigged-character` → `reference/textures.md`), or Unity keeps 2048.
- **UVs.** A face whose corners lie in two UV cells is refused (exit 1: re-unwrap or cut the seam); a
  face wholly in another cell, or a decimated corner just past the edge, comes back into 0..1.
- **Hair joins by default.** `character-autorig`'s secondary stage finds hair spikes on a fused mesh
  by the body search, as on the anchor alone, and adds their chains; Unity draws one mesh. So the ship
  rig runs **without** `--hair`, and H is the full height again (the note above inverts).
  `--separate hair,eyes` keeps those parts as their own objects with the same material, e.g. hair
  bound rigidly by `bind` or eyes bound to the eye bones; each is then one more draw call.
- **Vertex groups** `part.<part>` stay on the merged mesh in the `.blend`, for a later bind by part.
- **Eyeballs.** `eye_fit.py fit` cuts the painted eyes out of the GLBs, not `<c>_parts.blend`: with
  eyeballs, merge from `<c>_parts.glb` and pass `--eyes <c>_eyes.glb` (`--eyes` with a `.blend`, or a
  parts GLB `fit` edited without `--eyes`, is refused: holes where the eyes were). The balls take
  tiles of the atlas like any part but never join the mesh, where they would take the auto-rigger's
  weights: `Eye.L` and `Eye.R`, their `centre`/`radius`/`axis` extras kept, go to
  `<c>_ship_eyes.glb` (gate `ship.eyes`), and the rig binds each to its eye bone:
  `autorig.py all OUT ship/<c>_ship.glb --eyes ship/<c>_ship_eyes.glb --facial` (`eye_fit.py bind`
  drops the import's copy of the atlas material for the body's, so the FBX keeps one material).

Gates: `ship.materials` = 1; `ship.uv_in_tiles` = 1.0; `ship.density` each part's tile side over
its texture's side ≥ 0.5 (one halving; texels per unit before and after reported per part; a
mobile 2048 atlas halves twice, so pass `--min-density 0.25` there knowingly); `ship.triangles` and
`ship.tris.<part>` (≤ `budget_share` × the limit) when a limit is known: `--max-tris`, or a calibrated
row's `ceiling_tris`; over 1.25 × a part's share of `target_tris` only warns; with neither, counts
only. `ship.inspect_glb`: `comfyui-asset-generation` `inspect_glb.py` on the GLB (one material, base
and normal slots, the row or `--max-tris`). Reduce a part over its share **before** the merge, on the
part (`game-mesh.md`), never on the merged or rigged mesh.

Outputs in `--out`: `<c>_ship.glb` (what `autorig.py all` takes), `<c>_ship_eyes.glb` (with `--eyes`),
`<c>_ship.blend`,
`atlas_basecolor.png`, `atlas_normal.png`, `atlas_orm.png`, `<c>.ship.gate.json`, `inspect_glb.json`
and `merge.png` (front, three-quarter, the face, each hand, the atlas) for a person. In Unity the
body is then one `SkinnedMeshRenderer`, one sub-mesh, one material with base and normal bound; each
eyeball is a small renderer of its own with that same material, turned by `LeftEye`/`RightEye`.

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
| `hair.reduce.tears` fails | The hair was reduced unwelded, or the head job's mesh has coincident but distinct surfaces: check the hair close up; `--keep-hair-tris` and reduce it by hand, never on the merged mesh |
| `hair.reduce.silhouette` fails | The share is too small for the spikes: raise the hair's `budget_share` in the plan (the others' shrink), never the limit |
| `ship` refused: eyes | A parts GLB `eye_fit.py fit` edited needs `--eyes <c>_eyes.glb`; `--eyes` needs that GLB, not the `.blend` (§8) |
| `eye.found` fails | The paint has no light sclera (closed, stylised or tinted eyes) or the eyes are not mirrored: keep the painted eyes; never widen the colour rule to pass |
| `eye.rim_gap` or `eye.poke` fails | The head's surface at the eye does not follow a ball (a flat or bulging paint surface): check `eyes.png`; repaint or regenerate the head, never a larger limit |
| `eyes.poke_turned` fails | `pivot_offset_after` is not 0: an eye bone could not be moved (a renamed bone), or skin still rides a bone that turns with the eye; look at the turned poses. Never a larger limit |
| `degraded`, eyes on `Head` | The face was not built: rig again with `--eyes` and `--facial` |
| `hand.fingers` fails after `hands` but passed at `gate` | The hand came over budget and the collapse fused or tore it: generate it at its budget (`part_views.py generate --hand-ratio`), never a lower finger limit |
| `seam.hidden` fails on a hand | Look at `hands.png` from below the wrist: a cuff the wrist plane missed (`wrist.plane` perpendicular, few `sectors`) or a forearm drawn wider than the sleeve |
| `ship` refused: faces cross a UV cell border | The part's UVs wrap (a cylinder map, a seam across 0/1): re-unwrap that part or cut the seam, then merge again |
| `ship.density` fails | The atlas is too small for the parts: 4096, fewer parts, or a part reduced before the merge; on mobile accept the halving with `--min-density` set on purpose |
| `ship.tris.<part>` fails | That part outweighs its share (hands at Template, hair spikes): reduce the part first, or move shares in the plan with a person; never decimate the merged or rigged mesh |
| `assembly.head_extent_ratio` out | The head job's crown differs (lost or longer spikes): compare `compare_head.png`; regenerate at Template or Showcase, never Large on hair |

Avoid: a seam plane from view pixels; one plane assumed clean for both meshes without slicing both;
deleting the inner shell as a component; bridging a pair that failed its gates; Large on hair.
