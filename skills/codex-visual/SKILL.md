---
name: codex-visual
description: >-
  Generate 2D art in one locked style: sprites, icons, pixel-art tilesets,
  sheets, breathing idles.
---

# codex-visual — consistent asset generation via Codex CLI + a project art bible

Image generation is **stateless**, so a project's look drifts as it grows. This skill routes
visual work through **one canonical project spec**.

## Start here — which mode am I in? (check first, every time)

Read `/ART_DIRECTION.md`. **Missing / `Status: PENDING`** → **PHASE 1** first, whatever was asked.
**`Status: LOCKED`** → start from the request:

| You want | Go to |
|---|---|
| A look for a new project; "lock the art style" | PHASE 1 → 2 |
| "Generate / edit a sprite, icon, tileset or key art": one sprite, icon, key art or background | [job shape](#decide-the-shape-of-the-job) → PHASE 3 |
| A pixel-art tileset or pixel sprites: snap to the grid and palette, `audit_pixel.py` | PHASE 3; `reference/pixel-grid.md` |
| A matching set — icons, pickups, variants; one more for a shipped set | PHASE 3S |
| "Make a GIF / an idle loop", a walk, an attack; "the animation jitters" | PHASE 3A; `reference/animation-route.md` |
| A breathing idle loop from one still (`breathe.py`); jitter, cut feet, a boiling idle | `reference/animation-faults.md` §1a |
| How many frames fit a sheet: the four locks, grid → cell, the style floors | `reference/job-shape.md` |
| A transparent PNG; "a fringed cut-out"; which key colour | `reference/codex-runtime.md` §5 |
| "Off-centre", "one is smaller"; a crosshair template | `reference/geometry-gate.md` |
| "The assets don't match / the style drifted" | PHASE 4 |
| A source image for image-to-3D; the views a generated mesh's texture is repainted from | `reference/image-to-3d-input.md`; repaint: `mesh-texture-paint` |
| A review sheet (8-view QA, clips, before/after), gated on checks | `reference/review-sheets.md` |
| Read a screenshot; compare two images | `reference/codex-runtime.md` §7 |
| Any `codex exec` image work by hand (bare `codex` hangs; exit 0 proves nothing) | Step 0; `reference/codex-runtime.md` §1–4 |
| Which model rendered it; size and quality limits | `reference/image-model.md` |

> **This skill decides no art.** Style, dimensionality (2D / 2.5D / 3D), the generation engine,
> asset formats, palette and folder layout all live in the project's `/ART_DIRECTION.md`, chosen
> *with the user*; the skill provides only the *method*. Reference images a
> user shows you are **inspiration to characterize a target, never artwork to copy or ship.**

## Files this skill governs

| Path | Role |
|------|------|
| `/ART_DIRECTION.md` | **Single source of truth** (art bible). Read before EVERY generation. |
| `/ArtDirection/refs/` | User-supplied reference images. |
| `/ArtDirection/candidates/` | Bootstrap explorations. |
| `/ArtDirection/anchors/` · `anchors/sets/` | Locked reference image(s) fed via `-i`; `sets/` = per-set anchors (an approved first member). |
| `/ArtDirection/manifest.md` | Registry of every generated asset. |
| skill `scripts/` | **Key:** `pick_key.py` · `key_unmix.py`. **Sets:** `slice_grid.py` · `normalize_set.py` · `audit_set.py`. **Animation:** `sheet_to_frames.py` · `audit_frames.py` · `frames_to_anim.py` · `breathe.py`. **Pixel:** `pixel_snap.py` · `audit_pixel.py`. **3D source:** `turnaround_to_views.py` · `audit_3d_source.py`. **Review:** `contact_sheet.py` · `overview_sheet.py` (`reference/overview-sheets.md`). **Call:** `codex_generate.py` |
| project asset dir | Shippable art, at the path the spec defines (e.g. `Assets/…` for Unity). |

`<repo>` = the project root, as an **absolute path**.

## Step 0 — prerequisite check

```bash
command -v codex && codex --version
```

Missing → **stop and ask the user** to install it; never auto-install. Generation needs no
`OPENAI_API_KEY`: `$imagegen` — codex's bundled image skill, typed literally —
uses the ChatGPT login (`codex login status`).

> **Golden rule — always `codex exec`** (bare `codex "..."` hangs; the Bash tool cannot drive a
> TUI), and never trust its exit code: it is 0 when the model was rejected and when no image was
> made. `scripts/codex_generate.py --prompt-file P --out DEST -i <anchor>` makes the call and
> proves it (model probe, scratch dir, the **original** from its own session, real size). By
> hand: `reference/codex-runtime.md` §1–4.

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

## Decide the shape of the job

Three shapes, three priorities; the wrong one makes a sheet unusable. Locks, grid → cell and the
style floors for each: `reference/job-shape.md`.

| Shape | Priority | Path |
|---|---|---|
| **Static single** — key art, hero, boss, background | **quality** | one generation at the full pixel budget, style anchor via `-i`, plus the family anchor if one exists → PHASE 3 |
| **Static set** — icons, pickups, avatars, variants | **quality, then consistency** | 2x2 or 3x3 per sheet (627 / 418 px cells); more members → more sheets chained to the first; then `slice_grid.py` + normalize → PHASE 3S |
| **Animation** — loop, one-shot, transformation, UI feedback | **stability** | frames → grid → cell px → style floor → split; key → `sheet_to_frames.py --register` (**never** `slice_grid.py`) → gate → onion skin + GIF → Unity handoff → PHASE 3A |

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
3. **Explore options:** 2–3 styles x 2–3 key **game screens, not posters**, into
   `ArtDirection/candidates/` unless the user pinned one (`reference/image-model.md` §7).
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
then slice + normalize.

- **New set of N≥2 siblings** → grid one-shot: `cols=ceil(√N)`, `rows=ceil(N/cols)`, leftover
  cells blank or repeated, the static-set floors (`reference/job-shape.md`), a related family's anchor chained. Too
  many members? Split, chain every later sheet to the first, normalize all to one target.
- **+1 member for an already-shipped set** → pure reference-chaining to that set's anchor +
  normalize (its sheet can't be re-generated).

### Recipe — grid + chain in one call

Style anchor, then family anchor; locks 1–3; capture → key → slice → **gate** → promote. The call:
`reference/image-model.md` §6.

> One cell wrong? **Re-gen the whole sheet** — never patch one cell: a repair request re-renders the
> whole canvas (`reference/animation-faults.md` §3, with the local splice).

## PHASE 3A — Animation sheets (one short motion as ONE gridded sheet)

PHASE 3S's stack, but the cells are **moments of one character**, seated by silhouette afterwards
(never centred per cell; never `slice_grid.py`). Shape → prompt with the four locks → anchors →
generate, `key_unmix.py`, `sheet_to_frames.py --report` → `--register` → `audit_frames.py` and
`frames_to_anim.py --onion --bg` → frames + `frames.json` + previews. A boiling idle, or an idle
loop from one still: `breathe.py`. Every step: `reference/animation-route.md`.

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
  `comfyui-asset-generation`; its texture repainted from these views: `mesh-texture-paint`;
  import: `unity-3d-models`; a character's route: `game-character-pipeline`.
- **Audio and video**, a real moving-camera clip included — music, SFX and MiniMax H3 video through
  a self-hosted ComfyUI: `comfyui-asset-generation`; a still → a transparent loop from a video:
  `sprite-from-video`.
- **Where the art goes in a HUD**, type sizes, contrast: `unity-game-ui`.

Related: `game-character-pipeline`, `comfyui-asset-generation`, `art-asset-registry`.
