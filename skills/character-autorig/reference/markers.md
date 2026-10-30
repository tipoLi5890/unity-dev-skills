# Markers from slices — how `arp_markers.py` finds every joint

> Part of the `character-autorig` skill. The stage order is in `SKILL.md`; the cross sections come
> from `scripts/mesh_check.py`, which `arp_markers.py` imports.

Auto-Rig Pro's Smart step asks a person to click a chin, a neck, shoulders, wrists, a spine root
and ankles in a 3D view, or asks its AI files to guess them. Neither runs headless, and a click
lands beside a limb on a generated mesh. `arp_markers.py` reads the same points from the mesh
itself, places what the mesh does not show by a stated body proportion, and draws the result for a
person before any rig exists.

## Input

The normalised mesh (`blender-character-rig` → `reference/import-and-survey.md`): +Z up, facing −Y
(its left on +X), soles on Z 0, scale and rotation applied, arms in an A-pose. In Blender it reads
the evaluated mesh of `--mesh` (or the largest mesh of `--import file`); on the host it reads a
GLB/glTF/OBJ through `mesh_check.load_mesh` (no pictures there).

`H` is top minus sole. Every height below is a fraction of `H`; every position is world metres.

## Cross sections

A horizontal plane every 0.01 H cuts the mesh. The cut's segments are rasterised at 0.008 H,
enclosed holes are filled (an inner shell or a hollow torso is one part), and the parts are the
8-connected regions. The midline is the centre in X of everything below 0.4 H. A part *spans* the
midline when its X range contains it: that is the torso (or the head) at that height.

## How each marker is found

| Marker | Method | Reported as |
|---|---|---|
| crotch | the lowest cut above 0.2 H from which one part crosses the midline in every cut up to 0.6 H | `crotch_h` |
| hip | crotch + 0.02 H; X and Y from the leg part just below the crotch | measured |
| ankle | both legs' areas summed; the lowest cut in 0.03–0.13 H within 5 % of the least there (where the foot's flare ends); each leg's centroid at that height | measured |
| knee | both legs' widths summed; a local narrowing 40–65 % of the way from ankle to hip, at least 3 % narrower than both sides; else 52 % of the way | measured / proportion |
| toe_tip, heel, ball | the foot's vertices below the ankle: front-most, rearmost, and 70 % of the way from heel to toe; the ball and toe at 35 % of the ankle's height, the heel at 25 % | measured |
| shoulder | the arm part's centroids below the armpit (the longest run of cuts with a part wholly outside the torso) lie on the arm's axis; the shoulder is the axis point half the arm's radius outside the torso's edge at the armpit cut | measured |
| hand_tip | the arm vertex farthest along the axis, projected onto the axis | measured |
| elbow, wrist | 0.42 and 0.75 of shoulder → hand_tip (`--arm-ratios`); the wrist moves to a narrowing of the arm within 0.66–0.84 when one is at least 5 % narrower | proportion / measured |
| neck | the narrowest central cut between the shoulders and 0.95 H | measured |
| chin | the lowest cut above the neck whose front reaches a quarter of the way from the neck's front to the face's | measured |
| head_base | neck + 35 % of the way to the chin (neck + 0.02 H without a chin) | measured |
| head_top | the highest vertex, at the mid-depth of the head | measured |
| neck_base | the higher of the shoulders and neck − 0.03 H | measured |
| pelvis, spine1…3 | on the midline at hip height, then the pelvis → neck_base line split evenly; Y at 55 % of the torso cut's depth (a little toward the back) | measured / proportion |

**Both sides are measured apart.** Each sided marker is found on +X and on −X, the right one
mirrored and compared (`asymmetry_m`), and the two averaged into one mirrored pair. Gate
`markers.symmetry`: the largest difference ≤ 0.02 H (3.4 cm on a 1.7 m body), over the markers no
one adjusted.

**Windows.** A marker outside its window says the proportions are not the ones this route was
built for; take the hand-built route rather than force it. `--no-window-gate` reports without
gating, for a known-odd body a person has looked at.

| Marker | Window (fraction of H) |
|---|---|
| ankle | 0.02–0.13 |
| knee | 0.22–0.36 |
| hip | 0.42–0.60 |
| shoulder | 0.72–0.88 |
| neck | 0.78–0.93 |

**Arm angle.** `markers.arm_angle`: the upper arm (shoulder → elbow) below horizontal, inside
30–60° by default (`--arm-angle`), the contract's A-pose. A T-pose never gets this far: no arm part
hangs clear of the torso, and the call refuses (exit 1).

**Bend hints.** Auto-Rig Pro reads which way a knee or elbow bends from its reference chain, and a
leg that is straight in the mesh gives it nothing to read. In `arp_refs` and `contract_bones` the
knee sits at least 1 % of the leg's length forward (−Y) of the hip–ankle line and the elbow 2 % of
the arm's length back (+Y) of the shoulder–wrist line. `landmarks` stay as measured.

## Fingers

The hand frame: x from wrist to hand_tip, z the hand's thinnest axis (the back of the hand, chosen
to point up for palms-down and outward for palms-in), y across toward the little finger, oriented
so the index side faces −Y. `L` = |hand_tip − wrist|.

- **`--fingers auto`** (default): the hand's triangles are sampled and cut across x every 0.02 L
  from 0.40 L; in each cut the samples are split along y at gaps over 0.015 L. Where two cuts in a
  row hold exactly four parts, those are index, middle, ring and little (by y), each tracked to the
  last cut it reaches; the knuckle sits 0.06 L before the split, and the joints divide knuckle →
  tip as the fixed shape does. `fingers.mode` is `detected`.
- **Fixed shape** (`--fingers fixed`, or when no cut splits into four): knuckles at 0.49–0.51 L,
  fingertips at 0.78 (little) to 1.0 L (middle), with a slight curl toward the palm, scaled to L
  and turned into the hand frame. `fingers.reason` says why detection was not used.
- The **thumb** always takes the fixed shape: from 0.10 L along and 0.11 L toward the index side,
  forward and down to 0.62 L.
- `--mitten` keeps the 30 finger bones in `contract_bones` but makes them non-deforming, so a
  hand without finger geometry skins to `Hand` in the hand-built route. The contract still holds
  every finger bone; Auto-Rig Pro binds its own fingers either way.

## The pictures

With `--preview-dir`, two orthographic Workbench renders: `markers_front.png` looks along +Y (the
character's left on the right of the picture), `markers_side.png` along −X (its front on the
left). Markers are spheres drawn in front of the mesh: **green** left, **red** right, **yellow**
centre; blue rods join each chain. Fingertips are drawn, the other finger joints are not.

What the person checks, in this order:

1. Front: hips inside the thighs at the crotch line; knees on the knee; ankles above the shoe's
   flare; shoulders inside the deltoid, not on the torso's surface.
2. Front: elbows and wrists on the arm; a wrist past the cuff of a sleeve means the sleeve is wide.
3. Side: the spine column inside the body, a little behind its middle; the neck inside the neck;
   the head top on the skull, not on a hat or a hair spike.
4. Side: toe tip at the front of the shoe, heel at its back.

## Moving a marker: `--adjust`

A JSON object `{marker: [x, y, z]}` in world metres. Each value replaces the measured marker
after measuring; a `.L` marker moves its `.R` twin to the mirror unless the twin is given too.
Every derived output (`arp_refs`, `contract_bones`, the arm angle, the gates) is rebuilt from the
adjusted markers, and `methods` says `adjusted`. An adjusted `.L` or `.R` marker leaves
`markers.symmetry`: a person placed it and its mirror, so the measured difference moves to
`asymmetry_accepted` (reported, not gated). To accept an asymmetric pose, adjust each marker that
`asymmetry_m` names over the limit; the markers left alone are still gated.

```json
{"shoulder.L": [0.17, 0.0, 1.39], "knee.L": [0.104, -0.012, 0.50]}
```

Read the position off the side or front picture and the `landmarks` already in the output; move one
marker at a time and look again.

## The output (`autorig-markers/1`)

| Key | Holds |
|---|---|
| `landmarks` | every marker, `.L` and `.R`, plus `spine1…`, finger joints `<finger><0-3>.L/.R` (0 the knuckle or thumb base, 3 the tip) |
| `methods` | per marker: measured, proportion, fixed, adjusted |
| `height`, `ground_z`, `midline_x`, `crotch_h`, `arm_angle_deg`, `asymmetry_m` | the measures above |
| `asymmetry_accepted` | the measured left/right difference of each adjusted side marker, left out of `markers.symmetry` |
| `fingers` | `{mode: detected|fixed, reason?}` |
| `hand_frames` | `{".L"/".R": {x, y, z, length}}`, the hand frames used for the fingers |
| `arp_refs` | head and tail per reference bone of Auto-Rig Pro's human preset, `.x` and `.l` only: root, spine_01…03, neck, head, shoulder, arm, forearm, hand, the finger bases and phalanges, thumb1–3, thigh, leg, foot, toes, foot_heel, foot_bank_01/02 |
| `arp_spine_count` | spine bones + 1 (the add-on's Count includes its root) |
| `contract_bones` | `{mirror: true, bones: [...]}`: a `bcr_armature` spec with the contract's names and a radius per bone |
| `previews`, `gates`, `pass` | as above; each gate `{name, value, limit, pass}` as in a gate/1 report, and `ok`, pass's old name, beside it for one release |

`arp_refs` is what `blender-retarget` → `brt_arp` op `pipeline` writes onto the preset
(`reference/arp-pipeline.md`); `contract_bones` is what the hand-built route builds
(`reference/hand-built-route.md`).
