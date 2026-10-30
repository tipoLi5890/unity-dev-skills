# Headless pipeline — the same modules, run as stages with no open Blender

> Part of the `blender-character-rig` skill. The fit stage's method is
> `reference/fit-to-clip-skeleton.md`; the skinned LOD stage is `reference/skinned-lod.md`.

The MCP session is the right tool for one character explored by hand. It is the wrong tool for a
character that has to be rebuilt the same way every time: it needs an open Blender and a live
connection, a dropped connection leaves the state to be re-read, and an add-on's GUI operators
change behaviour between versions. A tennis game replaced an interactive Blender + Auto-Rig Pro
workflow (per-clip retargeting over MCP, clips about 387 MB) with the stages below: one command
per character, 93 to 137 s from GLB to a character Unity plays, no GUI anywhere.

**Every `bcr_*` module and `rig_gate.py` here, and `blender-retarget`'s `brt_retarget`, run
unchanged under `blender -b --factory-startup --python`**, rendering included. The `run(params)`
contract is the same; a stage script imports the modules and writes their gates to disk instead of
handing a dict back over the server. Vendor the modules into the project with the source commit
written beside them, and change no algorithm in the copy.

## The stage layout

One stage = one command, files in, files out, one gates JSON. A stage reads only the previous
stage's outputs, so any stage reruns alone.

| Stage | Reads | Writes | Gates (examples, with the limits that held) |
|---|---|---|---|
| vendor | the purchased archive, its sha256 pinned in config | the extracted clips, cached outside git | hash matches, else exit 2 |
| prep | the GLB | `prep/<id>.blend`, textures as base / ORM / normal | one mesh; origin at the soles, \|z\| < 1e-4 m; height ± 1 mm; faces lost to the weld ≤ 0.01%; triangles ≤ budget; decimation moves the bounding box < 1 cm |
| fit | prep, the pack's rest-pose file, the prop | `fit/<id>.blend`, `skeleton.json`, measured joints | names and parents equal the pack's, 0 differences; rest rotations < 0.5° from the pack's; left–right asymmetry < 3 cm; joints inside the mesh; rest sole \|z\| < 1 cm; bone length ratio 0.5 to 2.0 |
| skin | fit, a few representative clips | `skin/<id>.blend` | no unweighted vertex; ≤ 4 influences; weight sum error < 1e-4; no deform bone without vertices; new self-intersections p95 ≤ 8% |
| proof | skin, the representative clips | per-clip JSON, a contact sheet | the character against the pack's own body on the same clip, one formula for both (`blender-retarget` → `reference/route-bakeoff.md`) |
| lod | skin, proof's contact frames | `lod/<id>.blend`, sheets per level | `reference/skinned-lod.md` |
| export | lod | the character FBX, the prop FBX, `manifest.json` | the FBX read directly: every joint rotation equals the pack's < 0.5°, no animation, each level's face count read back |
| unity-gate | export, every clip | the lab's raw dumps, `gates.json` | `unity-rigged-character` → `reference/shared-skeleton-generic.md` |

## The gates JSON and the exit code

```json
{"schema": "gate/1", "stage": "fit", "character": "player_a", "pass": true,
 "gates": [{"name": "rest_rotation_max_deg", "value": 2e-05, "limit": "< 0.5", "pass": true}],
 "metrics": {}, "inputs": {"<path>": "<sha256>"}, "outputs": {"<path>": "<sha256>"},
 "params": {}, "tool": "fit.py", "blender": "x.y.z"}
```

- The report is a gate/1 report (`schemas/gate-1.json` in the plugin repo): a gate without a
  boolean `pass` has failed, and so has a report without one.
- **Exit 0** every gate passed; **1** a gate failed (the runner stops at that stage); **2** the
  input was refused (a missing file, a hash that does not match). The same contract as
  `blender-retarget`'s `brt_audit`.
- `inputs` and `outputs` carry file hashes, and meshes also a **content hash** (vertex positions
  to 5 decimals plus every vertex-group weight), so "same input, same output" is checkable.
- Keep one full run's gates JSON per character under version control as the sample; it is the
  evidence a ledger record links to (`art-asset-registry`), and a diff against it shows what moved.

## Determinism: two runs, the same bytes

Required, and measured: prep, fit, skin and lod give the same mesh content hashes on two runs;
export gives a byte-identical FBX; every proof and Unity number repeats.

- **Blender's FBX exporter is not deterministic out of the box.** It names nodes from Python's
  `hash()` of a string, salted per process, and stamps the header with the current time: two runs
  of the same scene differed in about 2,800 bytes. Inside the export stage's process only, wrap the
  exporter's key-to-UUID helper so a non-integer key goes through a stable digest (sha256 of its
  `repr`), and pin the header time to a fixed date. The add-on files are not edited. Checked on
  Blender 5.2's bundled exporter; these are private helpers whose names may move, so the stage
  re-checks byte equality on two runs rather than trusting the patch.
- **`--factory-startup`** keeps the user's add-ons and preferences out; a stage that silently used
  an installed add-on would not run on the next machine.
- A stage that builds the same thing twice in one process (lod) also checks that the second build
  hashes equal to the first.

## A Unity lab outside the repository

The gate that matters is how Unity plays the clips, so the last stage imports the export into a
**throwaway Unity project outside the repository** and samples it in batchmode, never the game's
own project (another editor, another agent, or a test run may own it).

- The runner refuses a lab path inside the repository (exit 2).
- It rebuilds the lab's asset folder from scratch on every run: same inputs, same lab.
- It counts the Unity editors already running and **waits while two are open** (the machine's
  limit), giving up with exit 1 after an hour.
- Creating the lab project took 5 s; the batchmode run then needs no GUI.

The Unity-side measuring, and the two batchmode traps it hit, are `unity-rigged-character` →
`reference/shared-skeleton-generic.md`.
