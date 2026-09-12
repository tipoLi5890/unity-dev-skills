---
name: codex-visual
description: >-
  Generate 2D game art with the `codex` CLI image model in one project art
  style: an art bible (ART_DIRECTION.md) plus an anchor image, icon and sprite
  sets as one grid sheet normalised to one size, short animations generated as
  one sprite sheet and sliced into frames with a GIF / APNG / WebP preview,
  transparency via chroma key; also reads screenshots. Load for: "generate /
  edit a sprite, icon, tileset or key art", "lock the art style", "the assets
  don't match / the style drifted", "make a transparent PNG", "make a GIF / an
  idle loop", "the frames don't line up", or any `codex exec` image work (bare
  `codex` hangs). Unity import: `unity-2d-sprites`; audio and video:
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
| skill `scripts/` | **Sets:** `slice_grid.py` · `normalize_set.py`. **Animation:** `sheet_to_frames.py` · `frames_to_anim.py`. |
| project asset dir | Shippable art, at the path the spec defines (e.g. `Assets/…` for Unity). |

`<repo>` = the project root, as an **absolute path**.

## Step 0 — prerequisite check (once)

```bash
command -v codex && codex --version
```

Missing → **stop and ask the user** to install it; never auto-install. Generation needs no
`OPENAI_API_KEY`: `$imagegen` — codex's bundled image skill, typed literally into the prompt —
uses the ChatGPT login (`codex login status`).

> **Golden rule — always `codex exec`** (bare `codex "..."` hangs; the Bash tool cannot drive a
> TUI): `codex exec --sandbox workspace-write --skip-git-repo-check '<prompt>' -i <anchor>
> < /dev/null` — prompt FIRST, `-i` LAST; a generation prompt is English and single-quoted. The
> file lands ONLY in `$CODEX_HOME/generated_images/<session-id>/`, so **capture that original
> yourself** and read its real size with Pillow — never trust the agent's own copy. →
> `reference/codex-runtime.md` §1–4.

## Models — agent vs image

Every `codex exec` call involves **two** models; don't conflate them.

- **Agent model** — analysis and orchestration, `-m <slug>` or config `model =`: the default for
  generation, the strongest for PHASE 2 and PHASE 4. A pinned slug that errors is the usual sudden
  failure: pass `-m` explicitly, check `codex exec --help`, record a project pin in
  `ART_DIRECTION.md`.
- **Image model** — renders the pixels; `-m` does not choose it. **Read which one rendered from
  the file itself** (`reference/image-model.md` §1). It takes **a prompt and reference paths,
  nothing else**, renders **a fixed ~1,572,864-pixel budget** and has **no native transparency**
  (§2–4 there).

## Which mode am I in? (check first, every time)

Read `/ART_DIRECTION.md`. **Missing / `Status: PENDING`** → run **PHASE 1**. **`Status: LOCKED`** →
decide the job shape (next section), then **PHASE 3** (one asset) · **PHASE 3S** (a set of
siblings) · **PHASE 3A** (frames of one motion) · or the analysis recipe
(`reference/codex-runtime.md` §7).

## Decide the shape of the job

Three shapes, three priorities; the wrong one is why a sheet comes back unusable.

| Shape | Priority | Path |
|---|---|---|
| **Static single** — key art, hero, boss, background | **quality** | one generation at the full pixel budget, style anchor via `-i`, plus the family anchor if one exists → PHASE 3 |
| **Static set** — icons, pickups, avatars, variants | **quality, then consistency** | 2x2 or 3x3 per sheet (627 / 418 px cells); more members → more sheets chained to the first, or one chained generation per member that needs the whole budget; then `slice_grid.py` + normalize → PHASE 3S |
| **Animation** — loop, one-shot, transformation, UI feedback | **stability** | frames → grid → cell px → style floor → split; `sheet_to_frames.py` (**never** `slice_grid.py`) → align → GIF/APNG/WebP → Unity handoff → PHASE 3A |

### The four locks — every grid prompt opens with them

After the verbatim `STYLE PREAMBLE`, in English. **Static sets use locks 1–3**; **animation sheets
use all four**, pasted from their only full copy: `reference/animation-sheets.md` §1.

1. **LOCK 1 — fixed sheet structure:** `<cols>` x `<rows>` equal cells read left→right then
   top→bottom; one flat key colour inside and between cells; no gridlines, numbers, text, UI,
   scenery.
2. **LOCK 2 — position and scale locked:** same body centre, foot baseline and camera distance in
   every cell; anchor on the **body**, never on hair, props or effects.
3. **LOCK 3 — nothing crosses a cell:** a margin of **~3% of the cell width** around everything; a
   pose that won't fit shrinks the motion or effect, never the character.
4. **LOCK 4 — one continuous action** (animation only): consecutive moments of ONE action,
   **explicitly not a collection of poses**; a full loop returns to frame 1, a half cycle stops at
   the far end (`--reverse-loop` plays the return), a one-shot settles over its last 3–4 frames.

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
with the grid — by the arithmetic of `image_gen.py`'s limits, 2880x2880 gives 4x4 720 · 6x6 480 ·
8x8 360 px cells; confirm with one generation before planning a set. It costs an
`OPENAI_API_KEY` and a user decision; when it earns them: `reference/image-model.md` §3.

### Style floors — the smallest cell each style survives

- **Pixel style:** working floor **128 px** per cell for a big-head character, so 5x5 (250 px),
  6x6 (209 px) and even 7x7 (179 px) work on one built-in sheet; **8x8 (157 px) is the edge.** The
  floor is a starting point: confirm legibility on one test sheet before committing a set
  (`reference/animation-sheets.md` §9).
- **Normal style** (flat / cartoon / painterly): **≤ 4x4 per sheet** (313 px), **≤ 3x3** (418 px)
  for a detailed character.
- **Static sets:** 2x2 (627 px) or 3x3 (418 px); 4x4 (313 px per item) only for small icons that
  ship at ≤ 128 px.

## PHASE 1 — Bootstrap a direction

1. **Settle the axes with the user** and record them; default to nothing:
   - **Dimensionality / render target:** 2D · 2.5D (billboarded sprites in a 3D world) · 3D.
   - **Style family:** pixel · flat/vector cartoon · low-poly · painterly · flat · …
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
3. **Fill the spec:** `Status: LOCKED`, version and every section of the schema below.
4. **Log** it in `manifest.md`.

## PHASE 3 — Generate one asset consistently (anti-drift core)

1. **Read `/ART_DIRECTION.md`.** If PENDING → Phase 1.
2. **Follow the recorded engine/approach:** *codex `$imagegen`* — `STYLE PREAMBLE` verbatim ＋ the
   asset request on a flat key colour, anchor via `-i`, original copied to `DEST`
   (`reference/codex-runtime.md` §9); *pixel via post-process* — downscale NEAREST to the spec's
   grid, quantise to its palette size, snap to grid, validate; *transparency* — chroma-key it out
   and verify the transparent fraction (`reference/codex-runtime.md` §5); *another engine* — the
   spec's recipe.
3. **Verify + register:** `ls -la "$DEST" && file "$DEST"`, then a `manifest.md` row (date, path,
   type, size, spec version, one-line prompt); an animation is one row for the set
   (`reference/animation-sheets.md` §10).

## PHASE 3S — Generate consistent SETS (a composable stack, not either/or)

Three SCOPES of consistency, each owned by one mechanism; they **stack** in one call:

| Scope — "must match…" | Mechanism | How |
|---|---|---|
| **Global style** (the project) | style anchor | `-i anchors/master.png` on EVERY gen |
| **Within a set** (its siblings) | **grid one-shot** | the whole set as ONE gridded image → one context, no drift |
| **Across sets / over time** (shipped work) | **reference-chaining** | ALSO `-i` the prior approved sheet — a FIXED promoted anchor, never the previous output |
| *guarantee* (exact pixel size) | **normalize** | `slice_grid.py` / `normalize_set.py`, after gen |

So the canonical call is **style anchor + family anchor (chain) + grid layout, in ONE generation**,
then slice + normalize (`reference/image-model.md` §6).

- **New set of N≥2 siblings** → grid one-shot: `cols=ceil(√N)`, `rows=ceil(N/cols)`, leftover
  cells blank or repeated, the static-set floors above, a related family's anchor chained. Too
  many members? Split, chain every later sheet to the first, normalize all to one target.
- **+1 member for an already-shipped set** → pure reference-chaining to that set's anchor +
  normalize (its sheet can't be re-generated).

### Recipe — grid + chain in one call

Style anchor, then family anchor; locks 1–3; capture → key → slice → promote. Step by step, with
the call: `reference/image-model.md` §6.

> One cell wrong? **Re-gen the whole sheet** — never patch one cell: a repair request re-renders the
> whole canvas, so no untouched cell comes back unchanged (`reference/animation-sheets.md` §8, with
> the local splice).

## PHASE 3A — Animation sheets (one short motion as ONE gridded sheet)

PHASE 3S's stack, but the cells are **moments of one character**: the arc *is* the cell-to-cell
offset, so nothing may be re-centred or rescaled per cell and `slice_grid.py` must never touch the
sheet, and nothing that wants a skeleton belongs here. § = `reference/animation-sheets.md`.

1. **Shape the job** (above): idle 3–8, walk 6–12, attack 4–12 frames; 8 on a 3x3 as a half cycle
   plus `--reverse-loop` beat 16 half-dead cells (§3d, §3a).
2. **Write the prompt:** `STYLE PREAMBLE` → the four locks (§1) → identity lock (colours as words
   *and* hexes) → time structure; a one-shot over 12+ frames is **staged** (§3, §4).
3. **Anchors: order fixed, roles named in prose** — style, identity, family (§2).
4. **Generate, then measure before you write anything.** Take the `generated_images` original
   (`reference/codex-runtime.md` §2, §4); gate on `sheet_to_frames.py <sheet> --rows R --cols C
   --bg-color '#ff00ff' --report`, reading empty cells → near-duplicates → bleed (re-generate) →
   baseline drift → centroid drift (what `--align` repairs) (§7).
5. **Then write the frames** (`--align baseline --max-shift 24 --outdir … --canvas 512 512 --pivot
   bottom-center --fps-hint 10`) and the preview (`frames_to_anim.py`); after a moving `--align`,
   **gate on the `post_align metric` block** (§5–§7).
6. **One cell wrong** → a new sheet or a local splice (§8). **Pixel style** → post-process the
   whole sheet at once, then align (§9).
7. **Outputs and the handoff:** frames + `frames.json` + the keyed sheet (→
   `anchors/sets/<action>.png` if the next animation must match) + previews (§10).

## PHASE 4 — Audit & evolve

- **Consistency audit:** the audit call in `reference/codex-runtime.md` §7, strongest agent model.
- **Changing the style:** bump `version` + changelog; flag pre-version assets in the manifest as
  re-gen candidates. Version the palette; never silently edit it.
- **New IP later** → re-run PHASE 1→2 (bump version); keep old anchors reproducible.

## `/ART_DIRECTION.md` schema (sections the file must contain)

Every section from Status to Changelog, with the **STYLE PREAMBLE** prepended verbatim to every
prompt: `reference/art-direction-schema.md`.

## Scope — what this skill does NOT do

- **Unity import and frame animation** — texture type, PPU, slicing, pivots, 9-slice, sprite
  sub-assets, `AnimationClip` / `AnimatorController`, loop vs one-shot playback, UI `Image` frame
  animation: `unity-2d-sprites`. This skill stops at a normalised PNG, or at the frames,
  `frames.json` and a GIF/APNG/WebP preview — **Unity plays none of those three formats**.
- **3D meshes** — image-to-3D, decimation, FBX/GLB import: `unity-3d-models`; playable characters:
  `unity-rigged-character`.
- **Audio and video**, a real moving-camera clip included — music, SFX and MiniMax H3 video through
  a self-hosted ComfyUI: `comfyui-asset-generation`.
- **Where the art goes in a HUD**, type sizes, contrast: `unity-game-ui`.
