---
name: codex-visual
description: >-
  Generate 2D game art with the `codex` CLI image model in one project art
  style: an art bible (ART_DIRECTION.md) plus an anchor image, icon and sprite
  sets as one grid sheet normalised to one size, short animations generated as
  one sprite sheet and sliced into registered frames, transparency via chroma
  key; also reads screenshots. Load for: "generate / edit a sprite, icon,
  tileset or key art", "lock the art style", "the assets don't match / the
  style drifted", "make a transparent PNG", "a fringed cut-out", "make a GIF /
  an idle loop", "the animation jitters", or any `codex exec` image work (bare
  `codex` hangs). Unity import: `unity-2d-sprites`; audio, video, 3D:
  `comfyui-asset-generation`.
---

# codex-visual — consistent asset generation via Codex CLI + a project art bible

Image generation is **stateless**, so a project's look drifts as it grows. This skill routes
visual work through **one canonical project spec**.

> **This skill decides no art.** Style, dimensionality (2D / 2.5D / 3D), the generation engine,
> asset formats, palette and folder layout all live in the project's `/ART_DIRECTION.md`, chosen
> *with the user*; the skill provides only the *method* and the codex mechanics. Reference images a
> user shows you are **inspiration to characterize a target, never artwork to copy or ship.**

## Files this skill governs

| Path | Role |
|------|------|
| `/ART_DIRECTION.md` | **Single source of truth** (art bible). Read before EVERY generation. |
| `/ArtDirection/refs/` | User-supplied reference images. |
| `/ArtDirection/candidates/` | Bootstrap explorations. |
| `/ArtDirection/anchors/` · `anchors/sets/` | Locked reference image(s) fed via `-i`; `sets/` = per-set anchors (an approved first member). |
| `/ArtDirection/manifest.md` | Registry of every generated asset. |
| skill `scripts/` | **Key:** `key_unmix.py`. **Sets:** `slice_grid.py` · `normalize_set.py` · `audit_set.py`. **Animation:** `sheet_to_frames.py` · `audit_frames.py` · `frames_to_anim.py`. **Pixel:** `pixel_snap.py` · `audit_pixel.py`. **3D source:** `turnaround_to_views.py` · `audit_3d_source.py`. **Call:** `codex_generate.py` |
| project asset dir | Shippable art, at the path the spec defines (e.g. `Assets/…` for Unity). |

`<repo>` = the project root, as an **absolute path**.

## Step 0 — prerequisite check

```bash
command -v codex && codex --version
```

Missing → **stop and ask the user** to install it; never auto-install. Generation needs no
`OPENAI_API_KEY`: `$imagegen` — codex's bundled image skill, typed literally into the prompt —
uses the ChatGPT login (`codex login status`).

> **Golden rule — always `codex exec`** (bare `codex "..."` hangs; the Bash tool cannot drive a
> TUI), and never trust its exit code: it is 0 when the model was rejected and when no image was
> made. `scripts/codex_generate.py --prompt-file P --out DEST -i <anchor>` makes the call and
> proves it: probes the model, runs from a scratch directory, takes the **original** from
> `$CODEX_HOME/generated_images` and reads its real size. By hand: `reference/codex-runtime.md`
> §1–4.

## Models — agent vs image

Every `codex exec` call involves **two** models.

- **Agent model** — analysis and orchestration, `-m <slug>` or config `model =`: the default for
  generation, the strongest for PHASE 2 and PHASE 4. A pinned slug that errors is the usual sudden
  failure: pass `-m` explicitly, check `codex exec --help`, record a project pin in
  `ART_DIRECTION.md`.
- **Image model** — renders the pixels; `-m` does not choose it. **Read which one rendered from
  the file itself** (`reference/image-model.md` §1). It takes **a prompt and reference paths,
  nothing else**, renders **a fixed ~1,572,864-pixel budget** and has **no native transparency**
  (§2–4 there).

## Which mode am I in? (check first, every time)

Read `/ART_DIRECTION.md`. **Missing / `Status: PENDING`** → **PHASE 1** first, whatever was asked.
**`Status: LOCKED`** → start from the request:

| You want | Go to |
|---|---|
| A look for a new project; "lock the art style" | PHASE 1 → 2 |
| One sprite, icon, key art or background | job shape (below) → PHASE 3 |
| A matching set — icons, pickups, variants; one more for a shipped set | PHASE 3S |
| An idle loop, a walk, an attack, a GIF; "the animation jitters" | PHASE 3A |
| A transparent PNG; "a fringed cut-out" | `reference/codex-runtime.md` §5 |
| "Off-centre", "one is smaller"; a crosshair template | `reference/geometry-gate.md` |
| "The assets don't match / the style drifted" | PHASE 4 |
| A source image for image-to-3D | `reference/image-to-3d-input.md` |
| Read a screenshot; compare two images | `reference/codex-runtime.md` §7 |
| Which model rendered it; size and quality limits | `reference/image-model.md` |

## Decide the shape of the job

Three shapes, three priorities; the wrong one is why a sheet comes back unusable.

| Shape | Priority | Path |
|---|---|---|
| **Static single** — key art, hero, boss, background | **quality** | one generation at the full pixel budget, style anchor via `-i`, plus the family anchor if one exists → PHASE 3 |
| **Static set** — icons, pickups, avatars, variants | **quality, then consistency** | 2x2 or 3x3 per sheet (627 / 418 px cells); more members → more sheets chained to the first; then `slice_grid.py` + normalize → PHASE 3S |
| **Animation** — loop, one-shot, transformation, UI feedback | **stability** | frames → grid → cell px → style floor → split; key → `sheet_to_frames.py --register` (**never** `slice_grid.py`) → gate → onion skin + GIF → Unity handoff → PHASE 3A |

### The four locks — every grid prompt opens with them

After the verbatim `STYLE PREAMBLE`, in English, pasted from their only full copy
(`reference/animation-sheets.md` §1): **1** fixed sheet structure · **2** position and scale
locked · **3** nothing crosses a cell (~3% of the cell width as margin) · **4** one continuous
action. **Static sets use locks 1–3; animation sheets all four.**

### Grid from frame count — the built-in path

The canvas is fixed, so **the grid alone decides the cell**: `cell = sqrt(1,572,864 / (rows *
cols))` for a square sheet; a non-square ask is honoured by *aspect* (`w = round(sqrt(1,572,864 *
cols / rows))`). The square sheet is 1254x1254:

| Grid | 3x3 | 4x4 | 5x5 | 6x6 | 7x7 | 8x8 |
|---|---|---|---|---|---|---|
| Cell (px) | 418 | **313** | 250 | 209 | 179 | 157 |

> **"Bigger grid → ask for more resolution" does NOT work here.** A 4x4 sheet asked at 2048x2048
> comes back 1254x1254, no error. **Bigger grid = smaller cells.**

So: frame (or member) count → grid → cell → against the style floor → below it, split into sheets
of the same cell size and aspect, each at most the style's maximum grid, every later sheet chained
via `-i` to the FIRST sheet (drift compounds down a chain): `reference/animation-sheets.md` §3d.

### The CLI-fallback path — where the rule does hold

`gpt-image-2` through the bundled `image_gen.py` takes a real `size` argument, so the canvas scales
with the grid (2880x2880: 4x4 720 px cells). It costs an `OPENAI_API_KEY` and a user decision; when
it earns them: `reference/image-model.md` §3.

### Style floors — the smallest cell each style survives

- **Pixel style:** working floor **128 px** per cell for a big-head character, so 5x5, 6x6 and
  7x7 work on one built-in sheet; **8x8 (157 px) is the edge.** Confirm it on one test sheet
  first (`reference/animation-scripts.md` §3).
- **Normal style** (flat / cartoon / painterly): **≤ 4x4 per sheet** (313 px), **≤ 3x3** (418 px)
  for a detailed character.
- **Static sets:** 2x2 (627 px) or 3x3 (418 px); 4x4 (313 px) only for small icons that
  ship at ≤ 128 px.

## PHASE 1 — Bootstrap a direction

1. **Settle the axes with the user** and record them; default to nothing:
   - **Dimensionality / render target:** 2D · 2.5D (billboarded sprites in a 3D world) · 3D.
   - **Style family:** pixel · flat/vector cartoon · low-poly · painterly · …
   - **Asset-template formats needed:** item-icon sheet · auto-tile tileset · character
     spritesheet · animation sheet · tileable texture · skybox · UI/HUD — *layouts*, not looks.
   - **Generation engine / approach:** `$imagegen` is **weak at true pixel art**; pixel work needs
     a **pixelation post-process**, another engine or **hand-authoring**
     (`reference/image-model.md` §7).
2. **Gather inputs — a scenario and/or reference images:** a 1–3 sentence brief (theme, hero, key
   objects, obstacles) and/or images → `ArtDirection/refs/`. **Inspiration only; never copy or
   ship them.** Analyze them (`reference/codex-runtime.md` §7).
3. **Explore options:** 2–3 **distinct candidate boards** into `ArtDirection/candidates/`, one per
   style unless the user pinned one (`reference/image-model.md` §7).
4. **Present & pick.** Summarize each (`codex exec "描述每張的風格差異" -i optionA.png …`); the user
   picks or asks for another round.

## PHASE 2 — Lock the direction (write `/ART_DIRECTION.md`)

1. **Set the anchor:** the chosen board (or user ref) → `ArtDirection/anchors/master.png`.
2. **Extract ground truth** with vision, never invented (`reference/codex-runtime.md` §7).
3. **Fill the spec:** `Status: LOCKED`, version and every section of `reference/art-direction-schema.md`.
4. **Log** it in `manifest.md`.

## PHASE 3 — Generate one asset consistently

1. **Read `/ART_DIRECTION.md`.** If PENDING → Phase 1.
2. **Follow the recorded engine/approach:** *codex `$imagegen`* — `STYLE PREAMBLE` verbatim ＋ the
   asset request on a flat key colour, anchor via `-i`, original copied to `DEST`
   (`reference/codex-runtime.md` §9); *pixel via post-process* — snap to the spec's grid and
   palette, then `audit_pixel.py` (`reference/pixel-grid.md`); *transparency* — `key_unmix.py`,
   never a binary key (`reference/codex-runtime.md` §5); *another engine* — the
   spec's recipe.
3. **Verify + register:** `ls -la "$DEST" && file "$DEST"`, then a `manifest.md` row (date, path,
   type, size, spec version, one-line prompt); an animation is one row for the set
   (`reference/animation-scripts.md` §4).

## PHASE 3S — Generate consistent SETS

Three SCOPES of consistency, each owned by one mechanism; they **stack** in one call:

| Scope — "must match…" | Mechanism | How |
|---|---|---|
| **Global style** (the project) | style anchor | `-i anchors/master.png` on EVERY gen |
| **Within a set** (its siblings) | **grid one-shot** | the whole set as ONE gridded image → one context, no drift |
| **Across sets / over time** (shipped work) | **reference-chaining** | ALSO `-i` the prior approved sheet — a FIXED promoted anchor, never the previous output |
| *guarantee* (size and centre) | **normalize + gate** | `slice_grid.py` / `normalize_set.py`, then `audit_set.py` |

So the canonical call is **style anchor + family anchor (chain) + grid layout, in ONE generation**,
then slice + normalize (`reference/image-model.md` §6).

- **New set of N≥2 siblings** → grid one-shot: `cols=ceil(√N)`, `rows=ceil(N/cols)`, leftover
  cells blank or repeated, the static-set floors above, a related family's anchor chained. Too
  many members? Split, chain every later sheet to the first, normalize all to one target.
- **+1 member for an already-shipped set** → pure reference-chaining to that set's anchor +
  normalize (its sheet can't be re-generated).

### Recipe — grid + chain in one call

Style anchor, then family anchor; locks 1–3; capture → key → slice → **gate** → promote. The call:
`reference/image-model.md` §6. Off-centre or shrunken sprites, crosshair templates:
`reference/geometry-gate.md`.

> One cell wrong? **Re-gen the whole sheet** — never patch one cell: a repair request re-renders the
> whole canvas, so no untouched cell comes back unchanged (`reference/animation-faults.md` §3, with
> the local splice).

## PHASE 3A — Animation sheets (one short motion as ONE gridded sheet)

PHASE 3S's stack, but the cells are **moments of one character**. The sheet decides the drawings,
**not where they sit**: frames are seated by silhouette afterwards, never centred per cell
(`slice_grid.py` never touches the sheet). No skeletons here.

1. **Shape the job** (above): idle 3–8, walk 6–12, attack 4–12 frames; 8 on a 3x3 as a half cycle
   plus `--reverse-loop` beat 16 half-dead cells → `reference/animation-sheets.md` §3d, §3a.
2. **Write the prompt:** `STYLE PREAMBLE` → the four locks → identity lock (colours as words
   *and* hexes) → time structure; a one-shot over 12+ frames is **staged** → same file, §1, §3.
3. **Anchors: order fixed, roles named in prose** — style, identity, family → same file, §2.
4. **Generate, key, then measure before you write anything:** the `generated_images` original,
   `key_unmix.py`, then `sheet_to_frames.py <keyed> … --report`. Empty cells, near-duplicates or
   a subject cut by the sheet edge → re-generate → `reference/animation-faults.md` §2.
5. **Write the frames — `--register` is required** (`ground` · `free` · `centroid` · `keep`; exit
   3 = a failed gate), then `audit_frames.py` and `frames_to_anim.py --onion --bg`: **one frame
   per cell on a contact sheet is not evidence about an animation** →
   `reference/animation-scripts.md` §1, §2.
6. **One cell wrong** → a new sheet or a local splice; **jitter, cut feet, a fringe, a boiling
   idle** → not a re-generation → `reference/animation-faults.md` §3, §1a. **Pixel style** →
   post-process the whole sheet, then register → `reference/pixel-grid.md`.
7. **Outputs and the handoff:** frames + `frames.json` (`pivot_norm` = the pivot) + the keyed
   sheet (→ `anchors/sets/<action>.png` if the next animation must match) + previews →
   `reference/animation-scripts.md` §4.

## PHASE 4 — Audit & evolve

- **Consistency audit:** the audit call in `reference/codex-runtime.md` §7, strongest agent model.
- **Changing the style:** bump `version` + changelog; flag pre-version assets in the manifest as
  re-gen candidates. Version the palette; never silently edit it.
- **New IP later** → re-run PHASE 1→2 (bump version); keep old anchors reproducible.

## Scope — what this skill does NOT do

- **Unity import and frame animation** — texture type, PPU, slicing, pivots, 9-slice, sprite
  sub-assets, `AnimationClip` / `AnimatorController`, loop vs one-shot playback, UI `Image` frame
  animation: `unity-2d-sprites`. This skill stops at a normalised PNG, or at the frames,
  `frames.json` and a GIF/APNG/WebP preview — **Unity plays none of those three formats**.
- **3D meshes** — this skill draws the source image (`reference/image-to-3d-input.md`); conversion:
  `comfyui-asset-generation`; import: `unity-3d-models`; playable characters:
  `unity-rigged-character` or `blender-character-rig`.
- **Audio and video**, a real moving-camera clip included — music, SFX and MiniMax H3 video through
  a self-hosted ComfyUI: `comfyui-asset-generation`.
- **Where the art goes in a HUD**, type sizes, contrast: `unity-game-ui`.
