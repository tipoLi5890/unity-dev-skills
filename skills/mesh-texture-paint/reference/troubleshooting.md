# Troubleshooting — symptom → cause → fix

Read `report.json` and the view's three files in `views/` (`_guide.png`, `_s<seed>.png`,
`_aligned.png`) before changing anything. Change one thing per run.

## The paint call

| Symptom | Cause | Fix |
|---|---|---|
| The output is the guide, unchanged | denoise below 1 | denoise 1.0; the guide survives through the VAE-encoded latent, not through denoise (`painting.md` §1) |
| The guide comes back almost unpainted | a third image in the call | exactly two: guide, then one reference |
| Ghostly, half-transparent output | 20 steps without the Lightning LoRA | the LoRA at strength 1, 4 steps, cfg 1, euler / simple |
| Output shifted or rescaled far past ±16 px / ±3 % | the guide was not 1024 × 1024, or the latent is an empty latent | `--size 1024`; latent = `VAEEncode(guide)` |
| `paint job failed`, a missing model in `/object_info` | the server stores the model files under other names | `paint_loop.py --models '{"unet": "…"}'` with the server's names for any of unet / clip / vae / lora (`painting.md` §7) |
| A view paints a stale or wrong guide | an upload name reused | leave the hashed upload names alone (`mtp_guide_<sha10>.png`) |

## What the model drew

| Symptom | Cause | Fix |
|---|---|---|
| Several small figures side by side (a collage); `edge_p90` 70+ | the whole turnaround sheet as picture 2 | the outline gate rejects it and the next try uses the nearest view; on a subject that does it often, `--ref nearest` |
| A three-quarter camera repainted as a straight side | a single concept view copied with its facing | the next try uses the sheet; keep `--ref sheet` |
| Mirrored straps or pockets on the sides | `left.png` and `right.png` swapped | `left.png` is the subject's own left, front toward the left image edge; recut with `turnaround_to_views.py --order` |
| Dark hair or fabric came back **silver / grey** | unpainted surface shown flat or clay grey: the model reads it as grey material | `--context fill` (the default) with `--prior self`; `--max-lighten` rejects what still slips through |
| **Purple** spreading into hair, socks or trim | a magenta marker on unpainted surface | `--context fill`; never a hue-coded marker |
| Wrong colours carried across: a side pocket's orange on the back of the shorts | `--prior ''`: the nearest painted colour as context | `--prior self`, or `--prior PATH` to a texture on the same UVs |
| Neutral greys turned **olive** or tinted | the prior matched per channel | the shipped one-gain match (`painting.md` §5); do not swap in a per-channel fit |
| A **green fringe** on edges | key bleed; despill switched off because the concept views contain key-green | if the subject is not green, check the concept views for a green background or rim; a green subject wants another key |
| A pale, washed-out figure; `bg_dev` over 40 | the model washed out the whole image | rejected by the background gate; the next seed usually returns a saturated key |
| A strap or flap colour smeared onto the body | the strap drawn a few pixels off | the 6 px outline band keeps it out; check the view was not accepted with `edge_p90` near the limit |
| The face is soft or blurry | painted at full-body scale only | `--detail head` (three close-ups that win the refine test) |
| A good front repainted dull by later views | refine off | `--refine 1.5` (default); `0` blends every view |
| Visible seams between views; `seam_delta` high | colour match skipped or off | check `match: skipped` in the views (that view painted different content there) and `--no-match` in `settings`; a seam the turntable still shows: rerun without that camera in `--anchors` |

## Cameras

| Symptom | Cause | Fix |
|---|---|---|
| Side views rejected on IoU | a narrow side silhouette scores low IoU for a small shift | read `edge_p90`: under 24 means the drawing fits; `--min-iou 0.87` for that subject |
| Low-angle or top-down views rejected | the model redraws steep views at eye level | keep `--pitch-range -40 50`; the bottom stays on the prior |
| Zoomed views of a thin prop come back unrecognisable | a crop of a thin shape has no recognisable outline | zoom is automatic only when the smallest extent is at least 15 % of the largest, and for objects only up to ±30° pitch; for a borderline prop pass `--no-zoom` |
| A thin prop (strings, a frame with holes) fails IoU around the holes | holes too small for the 6 px band and the mask opening | `--min-iou 0.85`; keep `--max-edge` |
| A flat prop (a shield, a board) keeps the wrong colours on one face: the image-to-3D texture's, or the other face's emblem | after the first view every view is a context render, and the model keeps what the prior shows there; `--prior ''` shows the other face's colours (the nearest painted texels lie through the slab) | paint the wrong face first, as a clay render: `--anchors 180:0,0:0,45:0,315:0,135:0,225:0,90:0,270:0 --no-zoom` for a wrong back (a thin prop over 15 % thick still zooms without `--no-zoom`) |
| One camera keeps failing all tries | the model cannot read that view (a narrow edge-on side, a crevice) | it is logged `rejected` and the loop moves on; if it is an anchor, drop it from `--anchors` and let NBV find a nearby angle |
| Inside of a double-shell mesh painted, or stays dark | the inner shell faces inward | the 75° facing cut excludes it; it keeps the prior and is not seeable |

## The loop

| Symptom | Cause | Fix |
|---|---|---|
| Coverage stops early, well under the target | `--max-views` reached (rejections count), 3 next-best views rejected in a row, 3 next-best views in a row with nothing unpainted, or the next view adds under `--min-gain 0.003` — `stop` in `report.json` says which | read the last views' `fails` and their `tries`; fix what rejects them, then `--resume` with a larger `--max-views` |
| Views that look right are rejected for `drift`, one after another | the first view came back off the concept (a darker skin, another hair colour) and correct views disagree with it — typical of a run painted from single views (`sheet` null in `report.json`) | pass `--sheet`, or leave it out and let the loop compose one from the concept views (`painting.md` §3); repaint the whole run — the first view is the anchor every later view is measured against |
| A `nearest` try comes back larger and a few pixels off (`scale` at a search limit, `iou_after` under `--min-iou`) | the model redrew the single concept view at its own framing | the nearest view already goes in fitted to the guide's silhouette box (`views/<name>_ref_nearest.png`); after a failed outline the next try uses the sheet, on a back camera too — keep `--ref sheet` |
| Head detail passes rejected, `edge_p90` 50–200 | the model redrew the head larger and higher than the render, or drew the whole figure | the tries alternate the front drawing and its head cut (`views/detail_ref_head.png`); for a hard face `--detail-tries 8`; a face with a seam down the middle in `turntable.png` means every pass failed |
| Coverage stops low and it is not clear why | — | `unpainted.causes` in `report.json` splits the seeable unpainted texels: `never_seen` (no used or rejected camera saw them: a pitch or view budget question), `rejected_only` (fix what rejects those cameras), `outside_drawing` (the drawing misses that surface), `outline_band` (near where the drawing's outline and the render's disagree), `edge_ramp` (silhouette and depth-step pixels). A hand part also gets `coverage_plane`: the same past its wrist plane, without the forearm stub the sleeve hides |
| Thin parts (a frame, strings, straps) stay on the prior | they are a few pixels wide on screen, all edge | unpainted texels already take a narrow 0.5–2 px edge ramp (`projection.md` §3); check `coverage_screen` and the turntable before adding views |
| Coverage stays near 0.7–0.8 on a prop | bottoms and inner faces are outside the pitch band or behind other surface | expected; they keep the matched prior. Check `coverage.png`: dark grey = seeable unpainted |
| The run stopped (network, server restart) | — | rerun the same command with `--resume`; `state.npz` and `report.json` carry the used cameras |
| Exit 3, `no view was painted` or `paint server error` | no `--server` / `COMFYUI_SERVER_URL`, the server is down, or a model file name is wrong (`errors` in `report.json`) | fix the server or `--models`, then rerun; views that fail with no output count as rejections, so three stop the run |
| `no prior texture found` | the GLB has no base-colour image | expected for a white mesh; context falls back to the nearest painted colour, and the painted GLB gets a new base-colour texture |
| A black slab or sheet in the mesh shows up in every view | the four views went into Pixal3D multi-view with their backgrounds | regenerate the mesh after `four_view_background_removal_api.json` (`pipeline.md` §3) |
| The GPU stays busy after the run | the model left loaded (`--keep-loaded` between views) | `/free` once the queue is empty (`pipeline.md` §6) |
