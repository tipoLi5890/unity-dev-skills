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
```

A single source passes when it is square and at least 1024 px, its background is one flat field
out to the frame, the subject is one piece, clear of the edge and at least half the canvas. It
gates the brief this skill draws to, not everything a background remover survives. Exit 1 →
regenerate; a conversion costs minutes, this a second. What no script reads:

1. No shadow attached to the subject, no glow, no rim light, no thin floating part (§3).
2. Single image: front, one side and the top all visible (§2).
3. Turnaround: `left.png` has the front pointing left (§6).

Then hand off: conversion to `comfyui-asset-generation`, import to `unity-3d-models`.
