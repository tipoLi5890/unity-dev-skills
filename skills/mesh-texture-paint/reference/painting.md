# Painting one view — the graph, the prompts, the reference, the context

One paint call turns one guide render into one painted view. Everything here is what goes **into**
that call; what happens to its output is `gates.md` (accept or reject) and `projection.md` (into
the texture).

## 1. The paint graph

`scripts/qwen_paint.py` builds the graph; `templates/qwen_image_edit_2511_view_paint_api.json` is
the same graph as a file, for a manual run through `comfyui-asset-generation`'s client: `7.image`
the guide, `8.image` the reference, `9.prompt` the prompt, `14.seed` the seed. The models:

| Role | Default file (`--models` overrides; see §7) |
|---|---|
| `unet` | `qwen_image_edit_2511_int8_convrot.safetensors` |
| `clip` | `qwen_2.5_vl_7b_fp8_scaled.safetensors` (type `qwen_image`) |
| `vae` | `qwen_image_vae.safetensors` |
| `lora` | `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors`, strength 1.0 |

The chain: `UNETLoader` → `LoraLoaderModelOnly` → `ModelSamplingAuraFlow` (shift **3.1**) →
`CFGNorm` (strength **1**) → `KSampler`. Both conditionings are `TextEncodeQwenImageEditPlus` with
`image1` = the guide and `image2` = the reference (the negative has an empty prompt), each through
`FluxKontextMultiReferenceLatentMethod` with `index_timestep_zero`. The latent is
`VAEEncode(guide)`. Sampler: **4 steps, cfg 1, euler / simple, denoise 1.0**, seed per try.

Why each choice holds:

- **Exactly two images.** Picture 1 is the canvas whose layout is kept; picture 2 is the one
  reference. Add a third image (say the sheet and a single view together) and the model leaves the
  guide almost unpainted.
- **The guide at 1024 × 1024** (`paint_loop.py --size 1024`) and its own VAE encoding as the latent:
  the output keeps the guide's pixel layout, which is what lets `align_painted` register it with a
  few pixels of shift instead of a search.
- **Lightning, 4 steps.** The base model at 20 steps without the LoRA comes back ghostly.
- **Denoise stays 1.0.** Below 1 the sampler returns the guide unchanged — no paint at all.
- Upload names carry a content hash (`mtp_guide_<sha10>.png`): the server serves the first file
  it saw under a name, so a reused name would paint a stale guide.

Run one call by hand to inspect a view:

```bash
python3 scripts/qwen_paint.py views/v03_y090_p+00_guide.png concept/left.png try.png \
  --prompt "$(cat prompt.txt)" --seed 42
python3 scripts/qwen_paint.py g.png r.png o.png --prompt x --graph-only    # print the API graph
```

## 2. The three live prompts

`paint_loop.py` picks one per view: **first** (nothing painted yet), **context** (every later view
of the main loop) and **detail** (the head passes). Placeholders: `{subject}` from `--subject`
(default: the `--kind`), `{label}` from the camera, `{refdesc}` from the reference, `{details}`
from the kind.

**First** — the front anchor, a plain clay render on `#00FF00`:

> Picture 1 is a grey clay 3D render of a {subject} on a pure green background, seen from the
> {label}. Picture 2 is {refdesc}. Paint the clay {subject} in Picture 1 as this {subject}: the
> same {details} as in Picture 2. Keep the exact pose, silhouette, size and position of Picture 1,
> pixel for pixel; only add colour and surface detail. Flat even lighting with no cast shadows and
> no highlights. Keep the pure green background. Draw only this one {subject}, no other views or
> copies.

**Context** — what is painted so far in colour, the rest shown with the prior (§5):

> Picture 1 is a 3D render of a {subject} on a pure green background, seen from the {label}.
> Parts of it are only rough colour blocks without the right details. Picture 2 is {refdesc}.
> Repaint the {subject} in Picture 1 so it matches Picture 2 everywhere: the same {details}, in
> the right places for this view. Keep the well-painted areas, and the exact pose, silhouette,
> size and position of Picture 1, pixel for pixel. Flat even lighting with no cast shadows and no
> highlights. Keep the pure green background. Draw only this one {subject}, no other views or
> copies.

**Detail** — a close-up of already coloured surface:

> Picture 1 is a close-up 3D render of part of a coloured {subject} on a pure green background,
> seen from the {label}. Picture 2 is {refdesc}. Repaint Picture 1 with clean, sharp detail so it
> matches the {subject} in Picture 2: the same {details}. Keep the colours already there, and the
> exact silhouette, size and position of Picture 1, pixel for pixel. Flat even lighting with no
> cast shadows and no highlights. Keep the pure green background.

`{details}`: `character` → "face, hair, outfit, colours, materials and details"; `object` →
"colours, materials, markings and details". Pick `--subject` as the noun a reader would use —
`"courier runner"`, `"courier backpack"` — not a file name.

`{label}` comes from the yaw: within 22.5° of 0 "front", then "front three-quarter", "side"
(67.5–112.5°), "back three-quarter", "back"; pitch over 30° adds ", looking down from above",
under −30° ", looking up from below"; a zoomed camera is prefixed "close-up of part of it, ".

A fourth template, the **grey-marker context prompt**, runs only with `--context flat|clay|magenta`
(§5, rejected): "Picture 1 is a partly coloured 3D render … The {grey} areas are not painted yet …
Paint the {grey} areas so they match the {subject} in Picture 2 and continue the existing colours
smoothly. Keep the already coloured areas …".

Worked example, the courier backpack at yaw 90:

```text
Picture 1 is a 3D render of a courier backpack on a pure green background, seen from the side.
Parts of it are only rough colour blocks without the right details. Picture 2 is a turnaround
sheet of that courier backpack (front, left, back and right views). Repaint the courier backpack
in Picture 1 so it matches Picture 2 everywhere: the same colours, materials, markings and
details, in the right places for this view. ...
```

## 3. The reference — sheet first, nearest view as the fallback

| `{refdesc}` | Picture 2 |
|---|---|
| "a turnaround sheet of that {subject} (front, left, back and right views)" | `--sheet`, the whole 4:1 sheet |
| "the concept art of that {subject} seen from the front / back / side" | the concept view nearest the camera's yaw (front 0, left 90, back 180, right 270) |
| "concept art of that {subject}" | detail passes: `--detail-ref`, default `front.png` |

`--ref sheet` (the default) tries the sheet first and alternates with the nearest view on each
failed try: with `--tries 3` the order is sheet, nearest, sheet. `--ref nearest` reverses it.
Without `--sheet` only the nearest view is used. The two fail in opposite ways, which is why each
is the other's fallback:

- **The sheet** carries every side's colours, so a back view finds the back's design — but now
  and then the model paints a **collage**, several small figures side by side. The outline gate
  catches it (`gates.md` §2).
- **A single view** cannot produce a collage, but the model can copy **that view's facing** — a
  three-quarter render repainted as a straight side.

Every prompt ends "Draw only this one {subject}, no other views or copies." — it lowers the
collage rate without hurting the single-view case.

## 4. The concept art the reference comes from

`--concept DIR` holds `front.png`, `left.png`, `back.png`, `right.png` on black — the views
`codex-visual`'s `turnaround_to_views.py` cuts from the sheet, one scale for all four. `left.png`
is the subject's **own** left: in that side view the front faces the left image edge. That is the
view yaw 90 sees. A wrong-sided `left.png` gives mirrored straps and pockets on the sides.

## 5. Context: how unpainted surface is shown

After the first view, the guide is a **context render**: painted texels in their colour, the rest
in a prior the model is asked to repaint. `--context fill` (the default) with `--prior self`
shows the **GLB's own image-to-3D texture** there — the right layout, dull colours — brightness
matched to the painted texels with **one gain and offset for all channels** (gain clipped to
0.6–1.8; applied once more than 2000 texels are painted). `--prior PATH` takes another GLB or an
image on the same UVs; `--prior ''`, or a GLB with no texture, falls back to the nearest painted
colour (mean of four neighbours in 3D). Unpainted specks under 400 px are shown in the nearest
painted colour, so the model sees clean context.

Why a prior and not a marker — each alternative fails in a way that ends up in the texture:

| Shown on unpainted surface | What the model does |
|---|---|
| flat grey (`--context flat`) | reads it as grey material: dark hair comes back silver |
| shaded clay grey (`--context clay`) | the same |
| magenta (`--context magenta`, as some texturing add-ons do) | bleeds into purple hair, purple socks, anything near that hue |
| nearest painted colour only (`--prior ''`) | spreads wrong colours: a side pocket's orange carried onto the back of the shorts |
| the prior matched per channel | neutral greys turn olive: the fit follows the main colours and tints the rest |
| **the GLB's texture, one brightness gain/offset** | right layout, believable colours to correct; kept |

Because the prior already looks painted, the context prompt asks for a repaint "so it matches
Picture 2 everywhere … keep the well-painted areas" rather than "paint the grey areas".

## 6. Despill

The background is pure `#00FF00` and a little green bleeds into the figure's edges. When the
concept views contain no key-green hue (green over both red and blue by 25 levels, on under 2 % of
the foreground pixels across the four views), every painted view is despilled before projection:
G is clamped to `max(R, B) + 8` inside the silhouette. A subject that really is green (a green
backpack) is detected and left alone — then pick concept art and a key that differ, as
`codex-visual` → `pick_key.py` does for sprites.

## 7. Model files named differently

The defaults are the file names in §1. A server that stores them under other names takes a JSON
map (inline, or a path to a JSON file) on `--models`, on `paint_loop.py` for a run or
`qwen_paint.py` for one call. Any of `unet`, `clip`, `vae`, `lora`; keys left out keep their
default, an unknown key is a usage error (exit 1).

```bash
python3 scripts/paint_loop.py runner.glb --concept views/runner --out paint/runner \
  --models '{"unet": "qwen-edit-2511-int8.safetensors", "lora": "edit-2511-lightning-4step.safetensors"}'
```

Check the names against the server's `/object_info` first (`comfyui-asset-generation` →
`reference/comfyui-api.md`).

## 8. Licences

| Component | Licence | Use here |
|---|---|---|
| Qwen-Image-Edit-2511 | Apache-2.0 | the paint model |
| Qwen-Image-Edit-2511 Lightning LoRA (4-step) | Apache-2.0 | the 4-step sampler |
| Qwen Image 2.1 | research / evaluation only, non-commercial | not used; evaluation only |
| nvdiffrast | non-commercial | not used: `mvtex.py` rasterises in numpy |
| StableGen | GPL-3.0 | ideas only, no code |

The mesh and its prior come from the image-to-3D graph; check each of its components' licences
too (`comfyui-asset-generation` → Boundaries).
