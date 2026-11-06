# Markers from slices — how `arp_markers.py` finds every joint

> Part of the `character-autorig` skill. The stage order is in `SKILL.md`; the cross sections come
> from `scripts/mesh_check.py`, which `arp_markers.py` imports.

Auto-Rig Pro's Smart step asks a person to click a chin, a neck, shoulders, wrists, a spine root
and ankles in a 3D view, or asks its AI files to guess them. A click lands beside a limb on a
generated mesh, and the AI needs a window and the user's licensed AI files. `arp_markers.py` reads
the same points from the mesh itself, runs headless, places what the mesh does not show by a stated
body proportion, and draws the result for a person before any rig exists. When stage `smart` ran,
`--smart` cross-checks the body with the AI and takes its fingers and face (below, and
`reference/arp-ai.md`); without it, or when it failed, the slices stand alone.

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
| hip | the crotch + the leg's half-width just under it (at least 0.02 H): thick thighs meet a thigh's radius below the hip joints; X and Y from that leg part. Over a measured knee the thigh is at most 1.1 x the shin: a wide hem at the crotch (shorts) widens the leg, and the hip is lowered there (a note says so) | measured |
| ankle | both legs' areas summed; the lowest cut in 0.03–0.13 H within 5 % of the least there (where the foot's flare ends); each leg's centroid at that height | measured |
| knee | per leg, on sections across the hip → ankle line (below); else 52 % of the way from ankle to hip | measured / proportion |
| toe_tip, heel, ball | the foot's vertices below the ankle: front-most, rearmost, and 70 % of the way from heel to toe; the ball and toe at 35 % of the ankle's height, the heel at 25 % | measured |
| shoulder | the arm part's centroids below the armpit (the longest run of cuts with a part wholly outside the torso) lie on the arm's axis; the shoulder is the axis point a quarter of the arm's radius outside the torso's edge at the armpit cut (a heavy chest there reaches past the joint) | measured |
| hand_tip | the arm vertex farthest along the axis, projected onto the axis | measured |
| elbow, wrist | 0.42 and 0.75 of shoulder → hand_tip (`--arm-ratios`); the wrist moves to a narrowing of the arm within 0.66–0.84 when one is at least 5 % narrower, and the elbow keeps 0.42 / 0.75 of shoulder → wrist (an AI wrist too), so the forearm keeps its length | proportion / measured |
| neck | the narrowest central cut between the shoulders and 0.95 H | measured |
| chin | the lowest cut above the neck whose front reaches a quarter of the way from the neck's front to the face's | measured |
| head_base | neck + 35 % of the way to the chin (neck + 0.02 H without a chin) | measured |
| head_top | the highest vertex, at the mid-depth of the head | measured |
| neck_base | the higher of the shoulders and neck − 0.03 H | measured |
| pelvis, spine1…3 | on the midline at hip height, then the pelvis → neck_base line split evenly; Y at 55 % of the torso cut's depth (a little toward the back) | measured / proportion |

**A held prop** (a shield, a board) standing beside one arm from above the armpit makes a vertical run of
cuts of its own, and the arm's search follows it (the axis comes out vertical: refused). That run is set aside
and the arm searched again (up to twice); the run's cut boxes are the report's `prop` (side, slices) and that
arm is the other one mirrored (its own cuts run into the prop), the fingers read on the free hand. `autorig.py`'s
hand_reach then gives the prop's skin (inside those boxes, less the arm's own skin) to the hand bone alone: it
rides the hand rigid. A shield modelled into the forearm (one mesh, its face joined to the body only through the
inner shell) keeps a strip of its face outside that skin, where it lies within the arm's clearance or a cut took
the gripping hand instead; that strip is a piece of the outward skin every path from which to the body runs over
the prop, and it goes with the prop, the inner shell behind it too (`prop_pieces`; `hand_reach.prop.cut_off` in
`rig/NAME.arp.json`). Left on the forearm and the upper arm, the strip does not
follow the hand with the rest of the shield, and the deform gate counts its crossings as the arm's own. The midline comes from the feet when the extent under 0.4 H is pulled more than 0.02 H
off them, and prep centres X on the feet when the box is more than 0.01 H off them: the markers mirror about
x = 0, so an offset d reads as 2 d of asymmetry (arms a few degrees apart move the box less than 0.01 H). Both
arms setting a vertical run aside leaves nothing to mirror from: refused (arms held against the body). A prop
that only starts under the hand is followed on from the hand: the hand tip lands on it and `markers.symmetry`
fails; generate the character empty-handed and attach the prop (`blender-character-rig` prop-on-bone.md).

**The knee on the leg's own sections.** Horizontal cuts at fractions of H put the knee wherever
the narrowest slice happens to fall: a change of H (hair, a hat) moves it, and on a slanted leg a
shorts hem or a flat stretch of shin can win. So each leg is cut across the hip → ankle line
instead, every 1 % of its length from 5 % to 80 %, and each section is the convex hull of the loop
around that line (edges joined by position, so seams do not split it); its girth is the hull's
perimeter. Two cues are read, in this order:

| Cue | What it looks like | Where the knee goes |
|---|---|---|
| kneecap | a bulge 40–70 % of the way up, at least 10 % above the shin below and 2 % above the leg just over it, reaching at least 1.5 × as far forward as back | its peak |
| valley | a narrowing 35–70 % of the way up, at least 3 % narrower than both sides (the calf below, the thigh above) | its lowest point |

Both use a parabola through the three sections around the extreme, so the knee is not held to
the 1 % grid. A calf swells at the back, so it is never a kneecap; a thigh swells all round. A
**hem or a cuff** is a girth step of 10 % or more between neighbouring sections. Each side of a
cue is compared only up to the nearest step. A narrowing from 6 % below a step to 2 % above it is
the hem's (the pinch under a hem), and so is the dip above a bulge when it sits in that range:
neither is used. With no cue
(a straight tube, a hem over a straight leg) the knee is placed at 52 % (proportion). The notes
say which cue each side took (`L knee: valley at 0.492 of ankle -> hip`). The knee's X and Y are the
section's centre.

## The skirt route (`--body skirt`)

A long coat, a skirt or a robe hides the crotch: the first cut that crosses the midline is the
hem, and a hip read from the hem sits at the knees (a knee-length greatcoat: hip 0.335 H, the
window starts at 0.42). With `--body skirt` (`autorig.py all --body skirt`) that cut is the hem,
and:

| Step | Method |
|---|---|
| legs inside | from 0.06 H under the hem, each leg is followed up on the cut's **own loops** (no hole filled, so a trouser leg inside a coat is a loop of its own): on its side, overlapping its loop below (box IoU ≥ 0.3), under 1.8 x its area (the skirt around it is larger) |
| crotch | where both legs end within 0.02 H of each other in one loop across the midline, no wider than 1.25 x their span and under 1.6 x their areas together: measured, hip = crotch + the leg loop's radius just under it (at least 0.02 H: a thick thigh's radius under the hip joint, as in trousers), X and Y of that loop |
| crotch hidden | a leg runs into the skirt (a solid skirt): the hip on the leg's centre line (fitted on its loops above mid-shin) at 1.86 x the knee's height over the sole (adult anthropometry, hip 0.530 H, knee 0.285 H), the knee read again on the new line; with no knee cue, 0.50 H (proportion) |
| knee | as above, on the leg's own section at each station (a loop over 1.8 x the station below is the skirt, not the leg); a cue within 0.02 H of the hem is the hem's lip, and one outside 40–65 % of the way a boot top: neither is the knee, and the knee falls back to 52 % |

The markers carry `body: "skirt"` and `skirt` {hem_h, hem_z, crotch_h, hip_from, hip_z, top_z
(hip + 0.06 H), midline_x, half_width, legs {L, R: [z, x, y, r] per followed loop}, torso (the
body's box per cut, the parts centred within the hem's reach of the midline)}. The top-level
`crotch_h` is then the crotch found inside the skirt, or null when it is hidden (never the hem).
`arp_markers.skirt_region` turns it into the skirt's own skin: rest z from 0.06 H under the hem to
`top_z`, inside that box (an arm or a hand beside the coat is not skirt) and off the legs' loops.
The bind (`autorig.py` skirt_bind), `deform_gate.py --skirt` and `secondary_chains.py --skirt` all
read it. On a knee-length greatcoat the legs show inside the coat and the crotch is measured
(0.465 H, hip 0.485 H); the knee's narrowing at the hem lip and the boot top's are both refused, so
the knee is a proportion. Check the pictures: a person may still `--adjust` a knee to the crease.

## The chibi route (`--body chibi`)

A big head (a third of H or more) on a short body with short, thick limbs and mitten hands is a body
type a person picks at G0, like the skirt: `autorig.py all --body chibi` passes it to `mesh_check`,
`arp_markers` and `deform_gate`. The default windows refuse such a body (its shoulder sits near
0.6 H); the chibi route has its own windows and placement rules, and every gate keeps its limit.

| Marker | Rule on the chibi route |
|---|---|
| crotch | as above, searched from 0.10 H up (short legs part low) |
| hip | the crotch + the leg's half-width just under it, as above, without the 0.02 H floor or the 1.1 x shin cap |
| ankle | the highest cut under the shin's narrowest whose depth reaches 1.3 x the shin's: where a big shoe starts |
| knee | as above (cue, else 52 % of ankle → hip); a hem 35–70 % of the way up where the section steps out going up is shorts over the knee: above it the leg is not seen, so a bulge or a narrowing there (a pocket, a fold) is the cloth's and is not used; a cue on the bare leg under the hem still is. A knee pad's lower edge reads as such a hem too: its bulge is refused and the knee falls back to 52 % (check the pictures) |
| shoulder | where the arm's axis crosses the torso's edge at the armpit (a thick arm joins there, not a quarter of its radius outside); the arm is followed down to 0.2 H |
| wrist, elbow | a narrowing within 0.52–0.80 of shoulder → hand_tip, else 0.66; the elbow at 0.36 / 0.66 of shoulder → wrist (a mitten is a third of a short arm) |
| neck | the narrowest central cut from the shoulder up to 0.15 H above it (under the head, never inside it) |
| neck_base, head_base | a third and two thirds of the way from the shoulder to the neck's narrowest: the head sits on the shoulders |
| spine | the contract's three bones, split evenly over the short torso |

| Marker | Chibi window (fraction of H) |
|---|---|
| ankle | 0.02–0.16 |
| knee | 0.10–0.30 |
| hip | 0.22–0.42 |
| shoulder | 0.45–0.72 |
| neck | 0.50–0.78 (the head 0.22–0.50 of H: 2 to 4.5 heads tall) |

An adult body on the chibi route fails these windows, and a chibi fails the adult ones: pick the
route from the concept at G0, never to rescue a failed window.

**Both sides are measured apart.** Each sided marker is found on +X and on −X, the right one
mirrored and compared (`asymmetry_m`), and the two averaged into one mirrored pair. Gate
`markers.symmetry`: the largest difference ≤ 0.02 H (3.4 cm on a 1.7 m body), over the markers no
one adjusted.

**Windows.** A marker outside its window says the proportions are not the ones this route was
built for; take the hand-built route rather than force it. With `--smart`, a near miss (a landmark
at most `--smart-tol`, 0.03 H, outside its window) whose AI marker lies inside it passes,
`confirmed_by: "auto-rig-pro-ai"`: a tall hairdo raising H is the usual cause. One further out
fails whatever the AI says. `--no-window-gate` reports without
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

**Segments.** `markers.limb_ratio`: per side, shoulder → elbow over elbow → wrist inside 0.5–2.0,
hip → knee over knee → ankle inside 0.85–2.0. One segment twice the other is a joint off its place
(an elbow moved toward the wrist), not a style. An adult's thigh is about the shin's length (hip
joint to knee 0.245 H, knee to ankle 0.246 H); a thigh under 0.85 of the shin is a hip read low at
a crotch whose leg half-width did not lift it far enough (thick thighs meet a thigh's radius below
the hip joints): place the hip with `--adjust`. `markers.finger_lengths`: the shortest
finger phalanx, joint to joint, ≥ 0.01 × wrist → hand_tip; a chain collapsed onto its base bends
nothing. Both read adjusted and AI markers too.

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
  tip as the fixed shape does. The surface must agree: the mesh itself, cut across the hand at the
  same stations, has to fall into four or more closed loops (each at least 0.05 L round) at two of
  them, else the four lanes were a mitten's sample gaps and the hand is `fixed`. `fingers.mode` is
  `detected`.
- **The read can be a vote** (`arp_markers.py --finger-votes K`; default 1, the single reading). On
  the rig exam five votes turned `spiky_hair` to `detected` but `thin` to `fixed` (2 of 5), so the
  vote is opt-in until a second opinion on the hand exists. Fingers about 0.015 L apart sit on the
  split's own threshold, so one sampling can flip with a wrist moved by a few millimetres. K
  readings each take 4000 samples (seed k) and cut at the stations shifted by 0, −1, +1, −2, +2 …
  × 0.005 L; reading 0 is the single reading (`--finger-votes 1`). `detected` needs more than half
  of them, so a tie reads `fixed`, and the surface's loops still veto every reading. The lanes are
  reading 0's when it detected, else the first detecting reading's. `fingers.votes` records `k`,
  the counts and each reading's seed, offset and mode.
- **Fixed shape** (`--fingers fixed`, or when no cut splits into four): knuckles at 0.49–0.51 L,
  fingertips at 0.78 (little) to 1.0 L (middle), with a slight curl toward the palm, scaled to L
  and turned into the hand frame. `fingers.reason` says why detection was not used.
- The **thumb** always takes the fixed shape: from 0.10 L along and 0.11 L toward the index side,
  forward and down to 0.62 L.
- **`--smart`** with a `fixed` hand (a glove, fingers held together): the AI's hand and finger
  references replace the fixed shape in `arp_refs`, and the wrist and finger joints in `landmarks`
  and `contract_bones` follow, with their rolls in `ref_rolls`; `fingers.mode` is `ai`. A proportion
  elbow follows the AI wrist (0.42 / 0.75 of shoulder → wrist): the AI puts the wrist where the hand
  leaves the forearm, short of the slices' 0.75, and an elbow left at 0.42 of shoulder → hand_tip
  would shorten the forearm by about a quarter, and the elbow gate reads that short span. A finger
  the AI did not fit (the add-on's four-finger hand has no index) keeps the fixed shape.
- A `fixed` hand on Auto-Rig Pro's bind is a mitten: `autorig.py`'s `mitten_bind` folds Index,
  Ring and Little phalanx i onto Middle i (the thumb keeps its own), so one chain bends the mitten
  whole and an animation that moves the fingers one by one cannot tear it (`reference/gates.md`,
  `deform.mitten_tear`).
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
adjusted markers, and `methods` says `adjusted`. The proportion spine points (`spine1..n`) follow an
adjusted `pelvis` or `neck_base`, each by its share of both ends' moves, so the root keeps pointing
up; a spine point you adjust stays where you put it. An adjusted `.L` or `.R` marker leaves
`markers.symmetry`: a person placed it and its mirror, so the measured difference moves to
`asymmetry_accepted` (reported, not gated). To accept an asymmetric pose, adjust each marker that
`asymmetry_m` names over the limit; the markers left alone are still gated.

```json
{"shoulder.L": [0.17, 0.0, 1.39], "knee.L": [0.104, -0.012, 0.50]}
```

Read the position off the side or front picture and the `landmarks` already in the output; move one
marker at a time and look again. Through the runner: `autorig.py markers OUT --adjust FILE` (or `all
--adjust FILE`), then `arp`, `contract` and `deform` again.

## The output (`autorig-markers/1`)

| Key | Holds |
|---|---|
| `landmarks` | every marker, `.L` and `.R`, plus `spine1…`, finger joints `<finger><0-3>.L/.R` (0 the knuckle or thumb base, 3 the tip) |
| `methods` | per marker: measured, proportion, fixed, adjusted |
| `height`, `ground_z`, `midline_x`, `crotch_h`, `arm_angle_deg`, `asymmetry_m` | the measures above |
| `asymmetry_accepted` | the measured left/right difference of each adjusted side marker, left out of `markers.symmetry` |
| `fingers` | `{mode: detected|fixed|ai, reason?}`; with `ai` also `count`, `names` and the slices' own `slices` |
| `hand_frames` | `{".L"/".R": {x, y, z, length}}`, the hand frames used for the fingers |
| `arp_refs` | head and tail per reference bone of Auto-Rig Pro's human preset, `.x` and `.l` only: root, spine_01…03, neck, head, shoulder, arm, forearm, hand, the finger bases and phalanges, thumb1–3, thigh, leg, foot, toes, foot_heel, foot_bank_01/02 |
| `arp_spine_count` | spine bones + 1 (the add-on's Count includes its root) |
| `smart`, `smart_agreement` | with `--smart`: the file, what was used, notes (`rejected` when its body sits over 0.10 H off: another mesh or frame, nothing taken); per landmark the distance and height difference to the AI's marker as fractions of H, and `agrees` |
| `ref_rolls`, `facial` | the roll per reference taken from the AI (hand, fingers, face), written as is; `facial` true when `arp_refs` holds the face. Empty and false without `--smart` |
| `contract_bones` | `{mirror: true, bones: [...]}`: a `bcr_armature` spec with the contract's names and a radius per bone |
| `previews`, `gates`, `pass` | as above; each gate `{name, value, limit, pass}` as in a gate/1 report |

`arp_refs` is what `blender-retarget` → `brt_arp` op `pipeline` writes onto the preset
(`reference/arp-pipeline.md`); `contract_bones` is what the hand-built route builds
(`reference/hand-built-route.md`).
