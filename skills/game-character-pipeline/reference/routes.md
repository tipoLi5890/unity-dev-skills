# The routes — body × rigging tool × clip source

Chosen once at G0, before S1, because the route decides the art. Every route ends with clips that
already play on the character's skeleton: Unity never retargets across skeletons.

| The body | Rigging (S6, always local) | Clips (S7–S9) | S1 draws |
|---|---|---|---|
| Standard adult proportions — **the default** | `character-autorig`: `mesh_check` → `arp_markers` → `brt_arp` `pipeline` (Auto-Rig Pro) → `contract_map --require contract` → `deform_gate`; the rig is on the humanoid contract | `humanoid-motion` two-camera (a front and a side view in one generated video), or a pack retargeted in `blender-retarget` | the realistic humanoid variant: A-pose, arms 30–60° down, straight elbows, legs apart |
| Standard proportions, Auto-Rig Pro absent or failing on the Blender in use | `character-autorig`'s hand-built route: the same markers into `blender-character-rig`'s `bcr_armature` with contract names, `bcr_skin`, the same contract and deformation gates | as above | as above |
| A custom body: short limbs, a large head, ears, a tail, mitten hands | `character-autorig`'s hand-built route when every marker can be placed; otherwise positional skinning in `blender-character-rig` | `humanoid-motion` two-camera for a contract body; keyed in `blender-character-rig`; stock clips retargeted in `blender-retarget` | the mascot A-pose, thin parts drawn thick |
| Standard adult proportions, the motion from **one** purchased or captured pack | the fit route: the pack's own skeleton fitted to the mesh headless (`blender-character-rig` → `reference/fit-to-clip-skeleton.md`) | the pack's files, played unchanged (Generic) | the realistic humanoid variant |

## Where each route reads

- **Contract routes** (rows 1–3 on the contract): the skeleton and its acceptance,
  `unity-rigged-character` → `reference/humanoid-contract.md`; the Auto-Rig Pro call,
  `character-autorig` → `reference/arp-pipeline.md`; the hand-built route, `character-autorig` →
  `reference/hand-built-route.md`; the mesh and deformation gates, `character-autorig` →
  `reference/gates.md`.
- **Clips onto the contract**: two cameras (a front and a side view of the character in one
  frame, animated by a local image-to-video model, read by a reader trained for that character and
  triangulated straight onto its skeleton, no retarget), `humanoid-motion` →
  `reference/two-camera.md`; then the back half (contact bake, loop cut, `motion_metrics` gate,
  FBX, Unity, record), `humanoid-motion` → `reference/pipeline.md`.
- **The two runners, in order**: `character-autorig` → `scripts/autorig.py all OUT Runner.glb`
  (the rigged `rig/<Name>_arp.blend`, or `repair/aN/` after a weight repair), then
  `humanoid-motion` → `scripts/twocam/twocam.py prepare` on that .blend and its later stages.
- **Pack clips onto any rig**: `blender-retarget` → `reference/clip-sources.md`, then
  `blender-retarget` → `reference/rest-pose-and-conjugation.md`.
- **The fit route** replaces S6, S8, S9 and S11 with headless stages,
  `prep → fit → skin → proof → lod → export → unity-gate`, each a command with a gates JSON and
  exit 0/1/2 (`blender-character-rig` → `reference/headless-pipeline.md`). A clip from another
  skeleton is converted to the pack's skeleton once, offline, and then joins the library
  (`blender-retarget` → `reference/route-bakeoff.md`, which also holds the measured comparison
  between fitting and retargeting).
- **What each route hands Unity**, and the questions that settle it: `unity-rigged-character` →
  `reference/source-art-and-3d.md`.

## Exit codes differ between tools

`mesh_check.py`, `arp_markers.py`, `deform_gate.py`, `contract_map.py`, `motion_metrics.py`,
`clip_metrics.py`, `contact_bake.py`, `autorig.py` and `twocam.py` exit 0 pass, 2 a gate failed,
1 refused input or a usage error. `rig_gate.py` exits 0 pass, 1 a gate failed, 2 refused. A stage runner reads
each tool's own table; it never treats every non-zero exit alike.

## Not a route here

- **Cloud rigging.** An image-to-3D service's auto-rig, or Mixamo, rigs off this pipeline's gates;
  rigging stays local. A cloud service may make the **mesh**, only in the upgrade track
  (`reference/start-gate.md` §4).
- **Text to motion.** Not in this release.
