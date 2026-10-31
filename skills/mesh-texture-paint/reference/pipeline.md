# Pipeline — concept art to a repainted GLB

The whole route with commands, for the courier runner (a character) and the courier backpack (a
prop). `CV` = `<repo>/skills/codex-visual/scripts`, `CA` = `<repo>/skills/comfyui-asset-generation`,
`MTP` = `<repo>/skills/mesh-texture-paint/scripts`. Python is `python3` with numpy, scipy and
Pillow.

| § | Stage | Owner | Leaves |
|---|---|---|---|
| 1 | Concept: three-quarter hero, then a 4:1 turnaround sheet | `codex-visual` | `runner_sheet.png`, the approved three-quarter image |
| 2 | Split the sheet into four views on black | `codex-visual` | `views/runner/{front,left,back,right}.png` |
| 3 | Background removal, then Pixal3D multi-view | `comfyui-asset-generation` | the image-to-3D GLB |
| 4 | Paint loop | this skill | `<out>/runner_painted.glb` |
| 5 | Check the GLB, hand it on | `comfyui-asset-generation`, `game-character-pipeline` | a gated GLB for S4 |
| 6 | Free the server | `comfyui-asset-generation` | an idle GPU |

## 0. Camera convention — fix it before drawing

Y up. Yaw 0 sits on +Z and sees the **front**. Yaw 90 sees **`left.png`**: the subject's own
left, so in that side view the front faces the **left image edge**. Yaw 180 the back, 270 the
right (front toward the right edge). Pixal3D's multi-view model reads the four views the same
way, so a sheet drawn to this convention gives a mesh and a paint reference that agree.

## 1. Concept art

The method is `codex-visual` → `reference/image-to-3d-input.md` §5 (turnaround) and §9 (a
character): a **three-quarter hero image first**, approved by a person, then the **4:1 sheet drawn
from it** with the hero attached via `-i`. The same route serves both kinds; only the prompt
differs. Painting reads colours and markings from these images, so state them plainly in the
hero prompt — every colour you leave to chance comes back different per view.

Character — the runner (hero on the key colour, then the sheet on black):

```bash
codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. Subject: ONE character, the runner of a three-lane courier game, a
short-limbed plush courier mascot with long upright ears, a round head, a satchel strap moulded flat
onto the chest and a short thick tail; teal jacket with an orange chest stripe, dark brown fur on the
ears, grey shorts, white socks. Strict symmetric A-pose, arms straight about 45 degrees down and clear
of the hips, legs apart. Empty hands. Three-quarter view from slightly above. Square image, the whole
character in frame, centered, filling about 80% of the frame. Soft even lighting. No shadow, no ground,
no glow, no text. Flat solid #FF00FF background.' \
-i <repo>/ArtDirection/anchors/master.png < /dev/null

codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. A wide 4:1 turnaround sheet of the character in the second
attached image: the SAME character four times in ONE row, left to right: FRONT view, LEFT side view,
BACK view, RIGHT side view. Every view straight-on at eye level, same scale, same baseline, a clear
empty gap between views. The same A-pose in all four. In the LEFT side view the character faces the
left edge of the image; in the RIGHT side view, the right edge. Match the shape, colours and details of
the attached character exactly. Soft even lighting, no shadows, no ground. Flat pure black #000000
background. No labels, no text.' \
-i <repo>/ArtDirection/anchors/master.png <project asset dir>/runner.png < /dev/null
```

Prop — the courier backpack:

```bash
codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. Subject: ONE courier backpack, a rounded parcel bag with a
roll-top flap, an orange body, a teal flap with a white parcel logo, two padded shoulder straps and a
side pocket with a zip. Three-quarter view from slightly above, front, one side and the top visible.
Square image, the whole bag in frame, centered, filling about 80% of the frame. Soft even lighting. No
shadow, no ground, no glow, no text. Flat solid #FF00FF background.' \
-i <repo>/ArtDirection/anchors/master.png < /dev/null

codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. A wide 4:1 turnaround sheet of the courier backpack in the
second attached image: the SAME backpack four times in ONE row, left to right: FRONT view (the logo
side), LEFT side view, BACK view (the straps), RIGHT side view. Every view straight-on at eye level,
same scale, same baseline, a clear empty gap between views, nothing overlapping. In the LEFT side view
the front of the bag points to the left edge of the image; in the RIGHT side view, to the right edge.
Match the shape, colours and details of the attached backpack exactly. Soft even lighting, no shadows,
no ground. Flat pure black #000000 background. No labels, no text.' \
-i <repo>/ArtDirection/anchors/master.png <project asset dir>/courier_backpack.png < /dev/null
```

Keep the sheet itself: it is `--sheet` in §4.

## 2. Split and audit the views

```bash
python3 "$CV/turnaround_to_views.py" runner_sheet.png views/runner     # front/left/back/right.png
python3 "$CV/audit_3d_source.py" --views views/runner                  # exit 1 → regenerate the sheet
```

One scale for all four views; `--order` if the sheet was drawn in another order. Open `left.png`:
the front must face the left edge.

## 3. Background removal, then Pixal3D multi-view

Remove the backgrounds **before** the multi-view job — views that go in with their background give
the mesh black slabs and sheets, and every paint view inherits them. Commands, node ids and the
checks on the outputs: `comfyui-asset-generation` → `reference/image-to-3d.md` (Background removal
for four views; A character).

```bash
python3 "$CA/scripts/comfy_asset_client.py" --workflow "$CA/templates/four_view_background_removal_api.json" \
  --output-dir work/clean --upload runner_front_r01.png --upload runner_left_r01.png \
  --upload runner_back_r01.png --upload runner_right_r01.png \
  --set 10.image=runner_front_r01.png --set 20.image=runner_left_r01.png \
  --set 30.image=runner_back_r01.png --set 40.image=runner_right_r01.png
python3 "$CA/scripts/comfy_asset_client.py" --workflow "$CA/templates/pixal3d_multiview_to_model_api.json" \
  --output-dir out/runner_r01 \
  --upload clean/runner_front_r01_black.png --upload clean/runner_left_r01_black.png \
  --upload clean/runner_back_r01_black.png --upload clean/runner_right_r01_black.png \
  --set 801.image=runner_front_r01_black.png --set 802.image=runner_left_r01_black.png \
  --set 803.image=runner_back_r01_black.png --set 804.image=runner_right_r01_black.png
python3 "$CA/scripts/inspect_glb.py" out/runner_r01/*.glb --max-triangles 70000 --texture-size 2048
```

Upload names are unique per view and run. The GLB carries UVs, a base-colour image (the dull,
guessed texture this skill replaces), a normal map and occlusion — the paint loop keeps all but
the base colour and uses the base colour as its prior.

## 4. The paint loop

```bash
python3 "$MTP/paint_loop.py" out/runner_r01/runner.glb \
  --concept views/runner --sheet runner_sheet.png --out paint/runner \
  --kind character --subject "courier runner" --detail head --server "$COMFYUI_SERVER_URL"

python3 "$MTP/paint_loop.py" out/backpack_r01/backpack.glb \
  --concept views/backpack --sheet backpack_sheet.png --out paint/backpack \
  --kind object --subject "courier backpack" --server "$COMFYUI_SERVER_URL"
```

`--server` falls back to `COMFYUI_SERVER_URL`, then the client's config. Each view prints one JSON
line (`gates.md` §6). A runner takes about 13 painted views plus three head passes, a few minutes
on a local server; a prop reaches about 0.7 of its seeable surface (`projection.md` §6).

Order of what happens per view: the camera (`projection.md` §1, §5) → the guide render (clay for
the first view, context after — `painting.md` §5) → up to three paint tries (`painting.md` §1–3) →
registration and gates (`gates.md`) → despill, colour match, projection (`projection.md` §3–4) →
`state.npz` and `report.json` saved.

Look at `turntable.png` (eight yaws; `--compare out/runner_r01/runner.glb` adds the original as a
first row) and `coverage.png`. Repaint the whole run — never a view by hand — when the turntable
shows a wrong design; tune one gate (`gates.md` §5) when good views were rejected.

## 5. Resume

An interrupted run continues from its last saved view:

```bash
python3 "$MTP/paint_loop.py" out/runner_r01/runner.glb --concept views/runner --sheet runner_sheet.png \
  --out paint/runner --kind character --subject "courier runner" --detail head --resume
```

Same mesh, same `--out`, same `--res`. Raising `--max-views` on resume paints more cameras; detail
passes already in `report.json` are not repeated, and a trailing run of rejections still counts
toward the three that stop the loop.

Exit codes: 0 done; 1 usage error, including a GLB whose base colour cannot be written (checked
before the first paint job); 3 no view painted, or the paint server unreachable or not configured
(the run stops at the first such error, writes out what was painted, and `--resume` continues).

## 6. Check, hand on, free the server

```bash
python3 "$CA/scripts/inspect_glb.py" paint/runner/runner_painted.glb \
  --max-triangles 70000 --texture-size 2048 --require base,normal,occlusion
```

Exit 0, then the painted GLB goes where the unpainted one would have: for a character, stage S4
(normalise in Blender) of `game-character-pipeline`; for a prop, `unity-3d-models` for import;
`art-asset-registry` records the run (`report.json`, the seed of every used view, the concept
sheet) as one asset.

**Host hygiene.** `paint_loop.py` keeps the edit model loaded between views (`--keep-loaded` on
each call). When the run is over and no paint job follows, wait for an empty `/queue`, then
`POST /free` with `{"unload_models": true, "free_memory": true}` and read `/system_stats` once
(`comfyui-asset-generation` → `reference/operations.md`). Free it too before switching to another
model family (back to Pixal3D, a video job). One GPU job at a time; never run two paint loops
against one server.
