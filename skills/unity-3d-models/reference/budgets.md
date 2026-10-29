# Budgets: the generation preset ladder

> Part of the `unity-3d-models` skill. How a class's triangle and texture budget is found (stage
> S0 of the ship track, once per class), the two tables a project keeps in `ART_DIRECTION.md`
> under `## 3D`, their default rows, and how a tool reads a row. Checking an imported folder
> against a row is `reference/model-audit.md`.

This skill ships no triangle cap. A budget is a person's pick between real versions of one asset,
seen in the real game, and quality comes first.

- **The baseline is the showcase** — the best version of the asset the project can make. It need
  not ship; every cheaper version is compared with it.
- **The rungs are the generation presets** of `comfyui-asset-generation` →
  `reference/image-to-3d-tuning.md`, from the smallest up to the class's baseline. Their settings
  live there; the face counts here are e.g. values:

  | Preset | Face target, e.g. | Texture side, e.g. |
  |---|---|---|
  | Small | 2000 | 1024 |
  | Medium | 4000 | 1024 |
  | Compact | 8000 | 1024 |
  | Large | 20000 | 2048 |
  | Template (the templates' default) | 70000 | 2048 |
  | Showcase | 700000 | 4096 |

- **Generating every rung is cheap.** Generation time barely moves with the face count (e.g.
  ≈ 80 s at 20000 faces against ≈ 90 s at 700000 on one server), so one asset at six presets is
  minutes of server time. A preset is a generation setting, not a game target: Showcase is the
  official template's own settings, and 700000 faces is where the comparison starts, not a number
  any class is held to.

## The ladder, step by step

Pick one representative asset of the class, with its source images already approved (stage S1).

1. **Generate it at every preset up to the class's `baseline`**, from the same inputs and seeds,
   one change per run (the preset), every upload named per asset and rung
   (`crate_front_large.png`): a reused name can make the server answer with an older file.
   Before the first rung, diff the project's graph against the official template field by field
   — `comfyui-asset-generation` → `reference/image-to-3d-tuning.md`.
2. **Inspect each GLB** with `inspect_glb.py --json-out` (`comfyui-asset-generation`) and keep
   its JSON. The
   rung's cost is the counted `triangles` and the largest image side, not the preset's face
   target: a thin double shell counts twice.
3. **Static copies in the real scene.** Import each rung unrigged — a character too, in its rest
   pose — and place `instances` copies where the game puts them, under the game camera, at its
   usual distance and at its closest. Same light, same post-processing, nothing else changed.
4. **One side-by-side sheet.** A screenshot per rung from the same camera, composed into one
   labelled image (rung, triangles, texture side, ms), refused while a rung's inspect JSON is not
   green — the preset comparison in `codex-visual` → `reference/review-sheets.md`.
   When the baseline is below Showcase, add the next preset up once: no visible difference means
   the baseline is saturated and stays; a difference means the class's `baseline` moves up. A
   Showcase baseline is the top of the ladder.
5. **A frame window per rung.** One `perf-window/1` record per rung, labelled `<class>/<preset>`,
   plus one with no copies to subtract — `FrameSampler.cs` and `compare_windows.py`,
   `unity-profiling` → `reference/frame-windows.md` and `unity-profiling` → `reference/compare.md`.
   An Editor window gives the shape of the curve; the absolute milliseconds come from the target
   device — skill `unity-device-testing`.
6. **A person picks**, biased to quality: the cheapest rung they cannot tell from the baseline at
   the closest usual distance, inside `frame_ms`. Unsure between two: the richer. The rung they
   can tell apart costs more than `frame_ms`: the richest rung inside it, `cost-limited` in
   `note` with what is lost — the person accepts the loss or the design changes. Nothing picks a
   rung automatically.
7. **Write the row** in `3D budgets`: the preset, `target_tris` and `target_tex_px` from that
   rung's inspect JSON, the date in `calibrated`, the asset in `note`. Record the approval in the
   ledger with the person who approved it and the sheet as its evidence — skill
   `art-asset-registry`.

Run the ladder again when `instances`, `frame_ms`, the game camera or the target device changes:
the pick moves with each.

**A rigged class.** The ladder measures a static mesh. Skinning, bone count and blend shapes add
cost the ladder never sees: confirm the rigged character under the game camera with a frame window
at import (`unity-rigged-character`). A low rung that reads well static can still deform badly at
the joints; the game mesh (stage S5) decides between regenerating and retopology —
`blender-character-rig` → `reference/game-mesh.md`.

## The two tables

Each sits under a heading of exactly that name in `ART_DIRECTION.md`, inside `## 3D`
(`codex-visual` → `reference/art-direction-schema.md`). A tool finds a table by its heading,
ignoring case, as the first table under it whose first column is `class`. A numeric cell is a
plain number; `-` or an empty cell is not set.

### 3D asset classes

The intent, written by a person.

| Column | Meaning |
|---|---|
| `class` | The key. The same name keys the `3D budgets` row and the ledger's `class` |
| `baseline` | The preset the ladder climbs to: the showcase for this class |
| `instances` | The most of the class on screen at once: the ladder places this many |
| `frame_ms` | The frame time those copies may cost together, on the target device |
| `pivot` · `scale` · `collision` · `lods` · `prefab` | The class's conventions — `reference/asset-classes.md` |

Default rows — starting points, e.g. values to replace, not measurements:

| class | baseline | instances | frame_ms | pivot | scale | collision | lods | prefab |
|---|---|---|---|---|---|---|---|---|
| pickup | Large | - | - | base-centre | real | trigger | 0 | `Pickup_<Name>` |
| obstacle | Large | - | - | base-centre | real | proxy | 2 | `Obstacle_<Name>` |
| env-prop | Large | - | - | base-centre | real | proxy-or-none | 2 | `EnvProp_<Name>` |
| hero-prop | Showcase | - | - | base-centre | real | proxy | 2 | `HeroProp_<Name>` |
| character | Showcase | - | - | base-centre | real | capsule | 2 | `Character_<Name>` |
| rigged-prop | Large | - | - | base-centre | real | proxy-on-bone | 0 | `RiggedProp_<Name>` |

Showcase is a class's baseline only where the camera gets close enough to show it — a hero prop,
a character. A pickup seen at a few dozen pixels never shows 700000 faces. `instances` and
`frame_ms` are the game's questions; fill them before the ladder.

### 3D budgets

The pick, approved by a person.

| Column | Meaning | Checked as |
|---|---|---|
| `preset` | The rung the person picked | Reported |
| `target_tris` · `target_tex_px` | That rung's counted triangles and largest texture side | Over `target × 1.25`: a warning, never a failure |
| `ceiling_tris` · `ceiling_tex_px` | An optional hard limit, empty by default | A failure when exceeded |
| `max_materials` | Material slots per model | A failure when exceeded |
| `max_bones` | Bones in the skeleton, for a rigged class | A failure when exceeded |
| `max_mb` | The model file on disk, MB of 2^20 bytes | A failure when exceeded |
| `lod_ratio` | Each LOD level's triangles as a fraction of the level before it | Reported |
| `calibrated` | The date a person approved the row, `YYYY-MM-DD`, or `-` | Anything else is an error |
| `note` | `cost-limited` and the accepted loss; the asset the ladder ran on | — |

Default rows — nothing picked yet:

| class | preset | target_tris | target_tex_px | ceiling_tris | ceiling_tex_px | max_materials | max_bones | max_mb | lod_ratio | calibrated | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pickup | - | - | - | - | - | - | - | - | - | - | - |
| obstacle | - | - | - | - | - | - | - | - | - | - | - |
| env-prop | - | - | - | - | - | - | - | - | - | - | - |
| hero-prop | - | - | - | - | - | - | - | - | - | - | - |
| character | - | - | - | - | - | - | - | - | - | - | - |
| rigged-prop | - | - | - | - | - | - | - | - | - | - | - |

## Reading a row

1. `-` or empty is not checked.
2. **No date in `calibrated`: report only.** A tool prints the counts, warns that the class has no
   budget yet, and fails nothing on that row. A hard limit wanted before the ladder is passed to
   the tool as an explicit number.
3. On a dated row the ceiling is the only gate on triangles and texture side; past
   `target × 1.25` is a warning; `max_materials`, `max_bones` and `max_mb` fail when set and
   exceeded.

The tools read the project's file and nothing else. Copy the default rows into `ART_DIRECTION.md`
as the starting tables; a project row replaces a whole row, cells are never merged, and a project
may rename classes or add its own. `inspect_glb.py --budgets ART_DIRECTION.md --class hero-prop`
reads one row (a file with no `3D budgets` table: report only); `ModelAudit.cs` takes the row's
numbers as arguments — `reference/model-audit.md`.

## gltf-transform or Blender

Every decimation of a mesh that will be skinned happens **before rigging**: decimating a rigged
mesh breaks its weights and its UVs, and every weight snapshot, wrist and grip measurement taken on
it. The ship track reaches the budget first and rigs once.

| The mesh | Tool | Why |
|---|---|---|
| A static GLB prop, base colour only, over its target | `gltf-transform simplify` (`reference/import-and-decimate.md`) | One command, GLB in and out, no Blender |
| A GLB generated at a face target with baked normal and occlusion maps | Neither: regenerate at the next preset down | Simplifying moves the surface out from under the baked maps |
| LOD meshes of a static prop | `gltf-transform simplify`, each level from the source | Scriptable per level |
| A character or rigged prop, still unrigged | Blender, before rigging — `blender-character-rig` → `reference/game-mesh.md` | Retopology, UVs and a rebake from the showcase; joint loops where it bends |
| LOD meshes of a skinned class | Blender, from the game mesh, before rigging; each level skinned in the same rig pass | A level decimated after skinning carries broken weights |
| An FBX, or hard-surface edges to keep (planar dissolve, symmetry) | Blender's Decimate modifier | gltf-transform reads glTF only |
| Many static props in CI | `gltf-transform` | Node only, no Blender install |

Whichever tool ran: inspect again, and look at the result beside the rung it came from.

## Where the result goes

`ArtDirection/budgets/<class>/`: the rung GLBs (git-ignored), one inspect JSON per rung,
`sheet.png`, and `perf.jsonl` with every window. The row goes into `ART_DIRECTION.md`; the
approval is one ledger record pointing at `sheet.png`.

| Need | Read |
|---|---|
| Presets, their settings, the graph diff | `comfyui-asset-generation` → `reference/image-to-3d-tuning.md` |
| Checking an imported folder against a row | `reference/model-audit.md` |
| Pivot, scale, collision, LODs and naming per class | `reference/asset-classes.md` |
| The `## 3D` chapter of `ART_DIRECTION.md` | `codex-visual` → `reference/art-direction-schema.md` |
| Frame windows and comparing them | `unity-profiling` → `reference/frame-windows.md`, `unity-profiling` → `reference/compare.md` |
| A character's game mesh before rigging | `blender-character-rig` → `reference/game-mesh.md` |
| The whole character route, preview and ship tracks | skill `game-character-pipeline` |
