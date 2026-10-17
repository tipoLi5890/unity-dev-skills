# image-to-3d-input — the source image a converter can read

This skill draws the picture; `comfyui-asset-generation` converts it to a GLB and
`unity-3d-models` imports it.

## 1. What the converter does to the image

It masks the subject, cuts it out as a **1024x1024 crop on black** with a small margin, and **that
crop is all the model sees**.

- Outside the mask is gone: a floor slab, a cast shadow, a glow halo.
- Inside it is geometry or texture: a contact shadow becomes a dark skirt, a highlight becomes
  base colour, a glow becomes painted-on colour (emissive is not separated).

## 2. Which view to draw

| Target | Draw | The mesh comes back | It cannot show |
|---|---|---|---|
| one-image conversion — one view carries the design | **one three-quarter view from above**: front, one side, top | in the pose of the picture (tilted; rotated upright after import), true to the image | back and underside — invented |
| upright conversion — a hard-surface prop at true proportions | **a four-view level turnaround** (§5) from the approved three-quarter image | axis-aligned, posed to the front view; a little darker than the input | **the top** and underside — invented; a lid emblem is lost |
| a character that will be rigged | **a four-view level turnaround of a symmetric A-pose** (§9; a realistic humanoid, §9 variant) from the approved three-quarter image; a T-pose for the Mixamo route (§10) | upright, axis-aligned, in the pose of the views; an unrigged mesh | the top of the head and the soles — invented; nothing a limb hides |

- **Never a lone straight-on view.** Depth is then a guess: a crate comes back 2.5x too deep.
- A runner seen from above and behind shows a prop's top first: a prop whose top carries the
  design takes the three-quarter path.

## 3. What to draw

- **One object**, whole, nothing cropped, about 80% of the frame.
- **Soft, even lighting.** No shadow, ground plane, rim light or glow: lighting in the image is
  baked into base colour.
- **Chunky design.** Thin floating parts (straps, antennae, chains) fuse into blobs or are
  dropped; thicken them or attach them to the body.

## 4. Background and resolution

- **Background:** the project's usual key colour. A key colour, mid-grey and an alpha PNG from
  `key_unmix.py` convert alike, with no key spill in the base colour; no special colour is needed.
  The turnaround sheet is the exception: black (§5).
- **Resolution:** the native square render (1254 px) already exceeds the 1024 px crop. **Do not
  upscale**, and take the `generated_images` original (`reference/codex-runtime.md` §4).

## 5. The turnaround sheet

Generate the three-quarter image first and get it approved; the sheet is drawn **from** it.

- **One wide image, one row, four objects:** FRONT, LEFT side, BACK, RIGHT side, in that order.
- Straight-on at eye level, same scale, same baseline, **clear gaps** between the objects.
- **Flat pure black background** — the views keep it, and the multi-view model wants black or
  alpha.
- The approved three-quarter image attached via `-i`, so all four views are one design.
- A sheet asked at 4:1 comes back nearer 3:1, and **panels are not equal width** (front and
  back are wider than the sides): split by content, never into equal quarters.

```bash
PY=$HOME/.codex/imagegen-venv/bin/python
"$PY" <skill>/scripts/turnaround_to_views.py crate_sheet.png views/crate
#   [--pad 1.1] [--size 1024] [--order front,left,back,right] [--bg-tol 24]
```

It takes the largest side any of the four objects has and cuts every view as a square of **that
one side** x `--pad`, centred on its own object: `front.png`, `left.png`, `back.png`, `right.png`,
plus a JSON report of each object's box. `--order` names the views left to right as drawn.
**Exit 1** unless it finds exactly four separated objects — regenerate with wider gaps rather than
loosening `--bg-tol`.

**Why one scale.** The model reads each view as a camera on one rig. Fitted panel by panel, a wide
object's front is fitted to its width and its side to its height: the crate's depth comes back
stretched about 1.5x.

Then gate the four files — heights within 4% of each other, front and back one width, the two
sides one width, the largest side about 0.91 of the frame:

```bash
"$PY" <skill>/scripts/audit_3d_source.py --views views/crate      # exit 1 → regenerate the sheet
```

## 6. Left and right

`left.png` is the view **from the object's left side**: in it the object's front points to the
**left** of the image. Open both side views; the other way round → re-run with
`--order front,right,back,left`.

Swapped sides leave a near-symmetric prop's geometry intact and show up as **colour**: orange
turns yellow-green and hues bleed across neighbouring faces. Re-seeding does not fix it; swapping
the two side views does.

## 7. Prompt templates — the courier-run pickup crate

English, single-quoted, after the `STYLE PREAMBLE`, prompt first and `-i` last
(`reference/codex-runtime.md` §1, §9).

```bash
# single three-quarter view
codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. Subject: ONE pickup crate for a three-lane courier runner,
a chunky sealed supply crate with thick corner braces, a wide front latch and a courier emblem on
the lid. Three-quarter view from slightly above: the front, one side and the top all visible.
Square image, the whole crate in frame, nothing cropped, centered, filling about 80% of the frame.
Soft even lighting. No cast or contact shadow, no ground plane, no glow, no rim light, no
text. Flat solid #FF00FF background (or the key colour ART_DIRECTION.md records).' \
-i <repo>/ArtDirection/anchors/master.png < /dev/null
```

```bash
# turnaround sheet, from the approved three-quarter image
codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. A wide 4:1 turnaround sheet of the pickup crate in the
second attached image: the SAME crate four times in ONE row, left to right: FRONT view, LEFT side
view, BACK view, RIGHT side view. Every view straight-on at eye level, the top not visible, same
scale, same baseline, a clear empty gap between views, nothing overlapping. In the LEFT side view
the front of the crate points to the left edge of the image; in the RIGHT side view, to the right
edge. Match the shape, colours and details of the attached crate exactly. Soft even lighting, no
shadows, no ground, no glow. Flat pure black #000000 background. No labels, no text, no
gridlines.' \
-i <repo>/ArtDirection/anchors/master.png <project asset dir>/pickup_crate.png < /dev/null
```

## 8. Pre-flight

```bash
"$PY" <skill>/scripts/audit_3d_source.py crate.png                # a single three-quarter source
"$PY" <skill>/scripts/audit_3d_source.py --views views/crate      # the four views
"$PY" <skill>/scripts/audit_3d_source.py --views views/crate --json-out views/crate/audit.json
```

`--json-out PATH` also writes `{"gates": [{name, value, limit, pass}, …], "verdict"}` for a
script to read — `green`, `failed`, or `harness` with an `error` when a file could not be read
(exit 2) — and prints the same text. A single image's gates are named `<file name>/<check>`; the
gate shape is the one a ledger record's `gates` takes in skill `art-asset-registry`.

A single source passes when it is square and at least 1024 px, its background is one flat field
out to the frame, the subject is one piece, clear of the edge and at least half the canvas. It
gates the brief this skill draws to, not everything a background remover survives. Exit 1 →
regenerate; a conversion costs minutes, this a second. What no script reads:

1. No shadow attached to the subject, no glow, no rim light, no thin floating part (§3).
2. Single image: front, one side and the top all visible (§2).
3. Turnaround: `left.png` has the front pointing left (§6).

Then hand off: conversion to `comfyui-asset-generation`, import to `unity-3d-models`.

## 9. A character

A character that will be rigged takes the turnaround path (§5), drawn so that bones can be placed
from the mesh and every limb can be weighted apart from its neighbour.

- **Strict symmetric A-pose.** Arms straight, about 45° down, clear of the hips with open space
  under each arm; legs apart with a visible gap. A limb that touches the body fuses to it.
- **Chunky, evenly thick limbs; mitten hands.** No separate fingers, no thin wrists or ankles.
- **Thin parts thick, and the same in every view** — ears, a tail: one length, one thickness, one
  angle, never crossing the body or a limb.
- **No held prop.** Generate the prop as its own image and its own mesh; it is attached to a hand
  bone after rigging.
- **No shadow, ground or glow** (§3), and the black sheet background of §5.

The order is the same: the three-quarter image first, approved, then the sheet from it via `-i`,
`turnaround_to_views.py`, and `audit_3d_source.py --views` — the same gate passes a character
sheet.

```bash
# three-quarter view — the design to approve
codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. Subject: ONE character, the runner of a three-lane courier game, a
short-limbed plush courier mascot with long upright ears, a round head, a satchel strap moulded
flat onto the chest and a short thick tail. Standing in a strict symmetric A-pose: both arms
straight, angled about 45 degrees down and held clear of the hips, legs apart with a visible gap
between them. Chunky evenly thick arms and legs, mitten hands with no separate fingers, thick ears.
Empty hands, holding nothing. Three-quarter view from slightly above. Square image, the whole
character in frame, nothing cropped, centered, filling about 80% of the frame. Soft even lighting.
No cast or contact shadow, no ground plane, no glow, no rim light, no text. Flat solid #FF00FF
background (or the key colour ART_DIRECTION.md records).' \
-i <repo>/ArtDirection/anchors/master.png < /dev/null
```

```bash
# turnaround sheet, from the approved three-quarter image
codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. A wide 4:1 turnaround sheet of the character in the second
attached image: the SAME character four times in ONE row, left to right: FRONT view, LEFT side
view, BACK view, RIGHT side view. Every view straight-on at eye level, same scale, same baseline,
a clear empty gap between views, nothing overlapping. The same strict symmetric A-pose in all four:
arms straight, about 45 degrees down, clear of the hips, legs apart with a visible gap. In the
LEFT side view the character faces the left edge of the image; in the RIGHT side view, the right
edge; the two side views are mirror images of each other. The inner side of each ear always faces
forward, so both side views show the ears edge-on. Ears and tail the same length and thickness in
every view. Empty hands, holding nothing. Match the shape, colours and details of the attached
character exactly. Soft even lighting, no shadows, no ground, no glow. Flat pure black #000000
background. No labels, no text, no gridlines.' \
-i <repo>/ArtDirection/anchors/master.png <project asset dir>/runner.png < /dev/null
```

```bash
"$PY" <skill>/scripts/turnaround_to_views.py runner_sheet.png views/runner
"$PY" <skill>/scripts/audit_3d_source.py --views views/runner     # exit 1 → regenerate the sheet
```

What the gate does not read — open the four views:

1. **The ears agree.** An ear whose inner colour faces the viewer in one side view and forward in
   the other is the common failure; the fix is the forward-facing sentence in the prompt, then a
   new sheet. Both side views show each ear edge-on.
2. **The side views mirror each other**, and `left.png` has the face pointing left (§6).
3. **Open space under both arms and between the legs** in the front and back views.
4. **Ears and tail are one length and one thickness** across all four, and cross nothing.
5. **Nothing in the hands**, no shadow under the feet.

In a level side view an A-pose arm reads as hanging straight down, in front of the body. That is
expected, not a drawing error: the front and back views carry the angle.

### Realistic humanoid variant

The mascot above is a custom body. A character of standard adult proportions — the body an
auto-rigger's humanoid template expects — takes the same order, sheet and gate, with these
changes:

- **A-pose with straight elbows**, arms about 45° down, open space under each arm, legs apart.
- **Hands: separated fingers only if a close grip matters.** A hand that will close round a prop
  the camera sees up close needs fingers drawn apart, at the knuckle proportions of a real hand,
  touching neither each other nor the thigh: a rig cannot invent anatomy the mesh lacks. Otherwise
  a relaxed hand with the fingers together is enough, still clear of the body.
- **Empty hands.** The prop is its own image, sheet and mesh, drawn to the same brief (§3, §5),
  and attached to a hand bone after rigging.
- **One scale across the four views**: one head-top line, one sole line, one height.
- **True sides.** Each side view is a 90° profile — one eye, the shoulders narrowed to the body's
  depth — never a three-quarter turn; an image model drifts toward three-quarter, so look.
  A side view that is not a profile is a source fault: regenerate it, never tune the converter
  around it.
- **Clothing and hair clear of black**: colours that separate from the background, hair close to
  the head, nothing hanging free; no logos or text.

In both prompts above, replace the subject and pose sentences with: *Subject: ONE adult courier
of standard human proportions, cropped hair, a short-sleeved olive courier jacket, grey work
trousers, orange running shoes. Standing in a strict symmetric A-pose: both arms straight with the elbows
locked, angled about 45 degrees down, clear space under each arm, legs apart with a visible gap.
Empty hands, fingers apart and touching nothing* — or *fingers relaxed together, not touching the
body* — and in the sheet prompt add: *Each side view is an exact 90-degree profile.* Drop the
ears, tail and mitten-hands clauses.

Then hand off: conversion to `comfyui-asset-generation` (its multi-view path, the ladder up to
Showcase; the `character` row of `unity-3d-models` → `reference/budgets.md` picks the preset). The rigging route is chosen once, in `game-character-pipeline`: a standard humanoid
with Auto-Rig Pro installed is rigged, and gets its clips, in `blender-retarget`; a custom body
such as the mascot goes to `blender-character-rig`; the T-pose variant (§10) serves the optional
Mixamo route of `unity-rigged-character`.

## 10. T-pose variant (Mixamo route)

Mixamo's auto-rigger wants a T-pose; so do some auto-rig services. Everything in §9 holds — the
three-quarter image first, the sheet from it, the black background, `turnaround_to_views.py`,
`audit_3d_source.py --views`, `left.png` with the face pointing left (§6) — with these changes:

- **A true T-pose.** Arms straight out to the sides, fully horizontal, daylight between arm and
  torso; legs apart with a visible gap. Arms near the body make the auto-rigger weld arm and torso
  skin weights together, and nothing downstream unpicks it.
- **Palms down, fingers not overlapping.** Overlapping fingers fuse; mitten hands are fine.
- **Nothing hanging free.** A stock auto-rig skeleton has no bones for hair, a cape, a skirt or
  ribbons: they move rigidly with the nearest bone or cut through the legs. Long hair hangs
  straight down, clear of the body outline, or is designed out — behind a running character a
  rigid ponytail is centre-frame the whole game.
- **Symmetric where possible.** Converter symmetry options clean up topology; a one-sided element
  rules them out.
- **A level side view shows each arm pointing at the camera**, foreshortened to a stub. Expected,
  not a drawing error: the front and back views carry the arm length.
- **The face needs pixels.** Reconstruction detail is capped by how many pixels the face covers,
  not by the image size. A face that comes out broken → check its size in the view before
  switching tools; give it more pixels from a larger source, never by upscaling (§4).
- **Multi-view upload order is by position.** Endpoints read the views by array index — commonly
  front, left, back, right; confirm the order in the endpoint's docs. Passed only `[front, back]`,
  the back lands in the left slot and is rebuilt as a profile: pass three. Uploading by hand to a
  web endpoint, rename the cut views so alphabetical order is upload order:
  `runner_1_front.png`, `runner_2_left.png`, `runner_3_back.png`.

In both prompts of §9, replace the A-pose sentences with: *Standing in a strict T-pose: both arms
straight out to the sides, fully horizontal, palms down, clear space between the arms and the
torso; legs apart with a visible gap. Hair and clothing close to the body, nothing hanging free.*
Drop the mitten-hands clause if the design has fingers, and describe a body of standard humanoid
proportions: §9's short-limbed mascot with ears and a tail is a Blender-route character.

Then hand off: conversion to `comfyui-asset-generation`; cleanup, upload and export to
`unity-rigged-character`, its Mixamo route.
