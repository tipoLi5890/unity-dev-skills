# Choosing the route before the art

The route decides the art, so it is chosen first: a rig cannot fix a mesh that arrived in the
wrong pose, and no cleanup rescues fused limbs. The route is chosen once per character, in
`game-character-pipeline` (G0: body, rigging tool, clips, and what S1 draws); this table is the
Unity side of that choice.

| Route (chosen in G0) | What reaches Unity | Read |
|---|---|---|
| Auto-Rig Pro in Blender (`blender-retarget`) | one FBX body, the clips already on its skeleton | `reference/unity-import.md` §1–§3 |
| A Blender rig (`blender-character-rig`) | the same, plus its own extra bones (ears, a tail) and a prop on a bone | `reference/unity-import.md` §4 |
| Mixamo — **optional** | a body and one FBX per clip, no materials | `reference/mixamo-route.md` |
| An image-to-3D or rigging service | the service's skinned FBX | `reference/unity-import.md` §1: check the mapping before anything else |

Three questions settle it:

1. **Where do the clips come from?** In this pipeline every clip is retargeted onto the character's
   own skeleton before Unity sees it — in Blender (`blender-retarget`), or by Mixamo on that route.
   Unity imports clips that already fit; it does not retarget across skeletons
   (`reference/unity-import.md` §1).
2. **Can the rigging service you are considering take this body?** A service that rigs
   automatically asks for a T- or A-pose, standard proportions and one piece; extra parts and
   short limbs belong to the Blender route. Pose parameters, output formats and multi-view input
   change between versions: confirm them on the service's own documentation before committing,
   and test one character first.
3. **Is the design legible at the size the converter reads it?** Pose, views, background and the
   face's pixel count are decided in the image: `codex-visual` → `reference/image-to-3d-input.md`
   (§9 A-pose, §10 T-pose).

The mesh itself — image to GLB, its multi-view path and the gate on what comes back — is
`comfyui-asset-generation`. Its multi-view path, fed four level views of one character, returns an
upright, unrigged mesh in the pose of the views: the input every route starts from. A GLB reaches
FBX through the Blender route, which exports the FBX itself, or through `scripts/glb2mixamo.py` on
the Mixamo route.

## Multi-view input to a hosted service

Hosted image-to-3D services that take several views share one shape of input, and two traps in it
destroy the mesh without an error:

- **The views are read by position, not by name.** The array order is commonly
  `front, left, back, right`, with `front` required and two to four accepted; confirm the order on
  the endpoint's docs. Pass only `[front, back]` and **the back view is consumed as `left`**: the
  service takes it for a profile and the result is ruined. To place a back view you **must supply
  three entries** (front, left, back). Uploading by hand, name the files so alphabetical order is
  upload order: `runner_1_front.png`, `runner_2_left.png`, `runner_3_back.png`.
- **Left and right are rarely documented** — camera-left or the character's left. Guess wrong and
  the mesh is mirrored: a near-symmetric character barely shows it, asymmetric accessories (a
  satchel strap, a badge) land on the wrong side. Fix it by swapping the left and right entries.
  The convention the image side uses is `codex-visual` → `reference/image-to-3d-input.md` §6
  (`left.png` has the front pointing to the image's left); check one asymmetric character against
  the service before a batch.
