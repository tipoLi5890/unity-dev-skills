# `/ART_DIRECTION.md` — the sections the file must contain

The project's art bible, written in PHASE 2 of `SKILL.md`. PHASE 2 fills `Status: LOCKED`, version,
**dimensionality**, **style family**, **engine/approach**, palette, mood, **pixel spec if pixel**
(cells per frame, block scale, palette, view angle, frame counts, outline), **asset-format
conventions**, the verbatim **STYLE PREAMBLE**, anchor path(s), do/don't.

- **Status / Version / Last updated**, **Scenario / IP brief**
- **Dimensionality / render target** (2D / 2.5D / 3D), **Style family** (from the board/refs)
- **Generation engine / approach** (which engine above; + any post-process; + pinned agent model,
  if the project pins one)
- **Asset-template formats** this project needs
- **Palette** — a `role | hex | usage` table under a heading named `Palette` (extracted from the
  anchor). The pixel scripts read exactly that with `--palette-file ART_DIRECTION.md`: every
  `#RRGGBB` in the section, in order, the first column as the role
- **Pixel spec** — *only if style = pixel*: **cells per frame N** (e.g. 64), **block scale F**
  (e.g. 4, so a 256 px frame), the palette as **the fixed `Palette` table or K colours**, view
  angle, frame counts, outline (`reference/pixel-grid.md` §3)
- **Mood / keywords**; **Anchors** — path(s) to canonical reference image(s)
- **STYLE PREAMBLE (inject verbatim)** — exact text prepended to every prompt
- **Per-asset conventions** — sizes/format/transparency/tiling per type
- **Set / sheet conventions** — which asset groups are one grid sheet (grid size, cell count,
  chroma key, canvas/content-frac), where per-set anchors live
- **Animation conventions** — one row per action: frame count · grid · cell px · fps · loop or
  one-shot (and whether the loop is authored as a half cycle for `--reverse-loop`) · frame canvas
  and pivot · in-cell safe margin · key colour · preview formats · naming stem. E.g. `idle | 8 |
  3x3 | 418 px | 10 fps | loop, half cycle | 512² bottom-centre | 13 px | #FF00FF | GIF+APNG |
  hero_idle`. Frame counts here override anything a per-asset row says
- **Do / Don't**, **Changelog**

## 3D (only if Dimensionality includes 3D)

A chapter of its own in `ART_DIRECTION.md`, after **Animation conventions** and before **Do /
Don't**, holding these nine `###` sections under exactly these names: tools find the two tables by
their heading. Every column, the default rows and how a row is read are in skill
`unity-3d-models` → `reference/budgets.md`; the conventions per class are its
`unity-3d-models` → `reference/asset-classes.md`.

### 3D scope

The render target (pipeline, platforms), the game camera (perspective or orthographic, field of
view, the distance each class is usually seen from), units (1 unit = 1 metre) and the up axis
(Y-up, as Unity and glTF are; a Z-up Blender file is converted at export, never in the scene).

### 3D route

One row per class: how its models are made — image-to-3D from an image made in this skill
(`comfyui-asset-generation`), authored and rigged in Blender (`blender-character-rig`),
purchased, or stock clips retargeted onto a rig (`blender-retarget`) — and the anchor its look
comes from. E.g. `obstacle | image-to-3D | anchor: depot_props.png`. A character also names its
track: preview (rig the dense mesh) or ship (budget, game mesh, then rig once) — skill
`game-character-pipeline`.

### 3D asset classes

The intent, written by a person: one row per class with its baseline preset, the most on screen
at once (`instances`), the frame time they may cost together (`frame_ms`), and its pivot, scale,
collision, LOD count and prefab pattern. Start from the default rows in `unity-3d-models` →
`reference/budgets.md` and replace a whole row to change it; this file holds no copy of them.

### 3D budgets

The pick, approved by a person: the preset chosen from the generation preset ladder, its
`target_*` counts, an optional hard ceiling (`ceiling_*`), the other limits, and the approval date
in `calibrated`. The columns, the default rows and the ladder are `unity-3d-models` →
`reference/budgets.md`. A class with no date is reported, never failed.

### 3D naming and layout

| Path | Holds |
|---|---|
| `ArtDirection/raw/3d/<Asset>/` | Undecimated source files, as generated or bought; git-ignored |
| `ArtDirection/sources/<Asset>.blend` | The editable source of anything authored or rigged |
| `ArtDirection/budgets/<class>/` | The ladder per class: one inspect JSON per rung, `sheet.png`, `perf.jsonl`; the rung files git-ignored |
| `ArtDirection/previews/` | Turntables and QA renders |
| `Assets/Models/<Class>/<Name>/` | What ships: the model with its textures and materials |
| `ArtDirection/assets.jsonl` | The ledger: what exists, where it came from, its hashes |

Then the names: one PascalCase name per asset across all of these, the prefab as the class key in
PascalCase plus the name (`Obstacle_LaneBarrier`), clips as `<Name>@<Clip>.fbx`, LOD meshes ending
`_LOD0` … `_LODn`. Purchased and third-party files are `vendor: true` in the ledger and live
outside git or under an ignored path.

### 3D materials and textures

The shader (URP Lit unless the look says otherwise), the texture set per class (base colour,
normal, packed occlusion-roughness-metallic), the longest side (the class's `target_tex_px` once
picked), colour space (sRGB for base colour, linear for normal and data maps), one texel
density for things seen side by side, and which materials a class shares. The packing differs
between formats: glTF keeps roughness in G and metallic in B; URP Lit reads metallic from RGB and
smoothness, which is 1 − roughness, from A.

### 3D rig and animation

Per rigged class: the rig type (Humanoid for a character that shares clips, Generic for a prop
with bones), the skeleton and its bone names, at most 4 influences per vertex (Unity's default
skin weights), the rest pose the views are drawn in (A-pose for the Blender route, T-pose for
Mixamo), and per clip its name, frame range, fps, loop or one-shot, and root motion. Building it:
`blender-character-rig`, `blender-retarget`; the Unity side: `unity-rigged-character`.

### 3D licence and provenance

The sources each class may use (generated, authored, purchased, third-party), the licence string
a purchased or third-party asset carries in the ledger (`purchased:<pack>`, `cc0`), where vendor
files live, and who approves. The ledger keeps hashes of prompts and workflows, never prompt text
or server addresses — skill `art-asset-registry`.

### 3D review gates

What a model passes before its ledger record is `approved`: the audit of its class folder
(`unity-3d-models` → `reference/model-audit.md` — over a ceiling or a `max_*` fails, over
`target × 1.25` warns, a class with no budget yet only reports); a look at its QA renders or a
turntable, and at the model under the game camera; for a rigged class, a valid Avatar or
skeleton, at most 4 influences per vertex and one extreme pose seen; for a budget, a person's
approval of the ladder's `sheet.png`.
