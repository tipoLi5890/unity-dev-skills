# Sourcing the mesh: T-pose art → image-to-3D

Everything downstream is decided here. A rig cannot fix a mesh that arrived in the wrong pose,
and no amount of cleanup rescues fused limbs.

## 1. Why characters go FBX, never GLB

- **glTFast cannot produce an Avatar** ([glTFast#391](https://github.com/atteneder/glTFast/issues/391)).
  You get a SkinnedMeshRenderer, but nothing settable to Humanoid or Generic. No Avatar
  means **no animation retargeting and no humanoid AvatarMask**.
- Only Unity's **native FBX importer** exposes the **Rig tab**.
- **Mixamo accepts FBX / OBJ / ZIP only** — never GLB.

Together these make FBX the only route, and most image-to-3D services hand you GLB.
**`gltf-transform` cannot convert out of the glTF family**, and Blender or assimp are heavy
installs for one format change — so use **`glb2mixamo.py`** in this skill: stdlib only, emits
a Mixamo-ready OBJ, runs the humanoid sanity checks, and extracts the embedded maps you will
need later with `--textures=DIR` (without the flag it only lists them).
(`assimp export in.glb out.obj` works too if it happens to be installed.)

> **Never run index-level connectivity checks on glTF geometry.** FBX keeps a de-duplicated
> vertex array and indexes UVs separately; **glTF binds every attribute to one vertex, so each
> UV seam splits a vertex in two**. A perfectly solid body then reports as *thousands* of
> disconnected fragments, and any stray-shell filter happily deletes real anatomy — e.g.
> 33,296 vertices read as 3,679 "shells", the largest only 724 verts, and the filter silently
> removes 4,369 vertices of body. Welding by position first collapses it to **1 shell**
> (15,514 distinct positions). `glb2mixamo.py` does this; the OBJ still stores the split
> vertices because they carry the UVs.

## 2. T-pose reference art — the input that decides everything downstream

**T-pose is the precondition for auto-rigging**: arms fully horizontal, clearly separated
from the torso, legs apart with a visible gap. A natural arms-down pose makes the
auto-rigger weld arm and torso skin weights together, and nothing downstream fixes it.

- **No text anywhere in frame.** Turnaround sheets label views `FRONT` / `LEFT` / `BACK` /
  `RIGHT`; image-to-3D treats those letterforms as **geometry to build**. Crop them out.
- **Never feed a whole turnaround sheet.** The model reads "four figures side by side +
  head close-up + accessories + colour swatch bar" as one silhouette and returns a fused
  blob. Crop each view into its own image, one per array entry.
- **Reconstruction quality is capped by the face's pixel count in the reference.**
  A 340×930 crop leaves the face ~80 px and it melts; a 1254×1254 full-body
  T-pose leaves 130–150 px and it comes out legible. **When the face collapses, check
  input resolution before switching tools** — far cheaper, and usually the real cause.
- Across views: identical character design, heights aligned in-frame, clean background.
- **A T-pose side view shows the arms pointing at the camera**, foreshortened to a stub.
  Geometrically inevitable, not a drawing error — but the model may misjudge arm length
  from it. Front/back views, where the arms are fully extended, compensate.

**Commissioning this art?** `reference/character-art-brief.md` is a ready-to-send
specification — hand it to an artist verbatim or paste it into a generation prompt. It also
carries the acceptance checklist to run *before* paying for a 3D generation, and the
file-naming scheme that keeps alphabetical order identical to the upload array order (§4).

## 3. Choosing an image-to-3D tool

How they compare on quality (these tools move fast — test one character before committing):

- **Rodin** — struggles with facial detail; eyebrows and similar elements break down.
- **Tripo** — **adds unrequested realistic detail** to stylised characters, which actively hurts
  anime faces.
- **Hunyuan3D / Trellis** — best at preserving a smooth-shaded cartoon look, most consistent.
- **Meshy** — best facial structure and proportion, least cleanup needed around the eyes, but it
  **adds the same unrequested realistic detail** to stylised characters.

The parameters usually decide it before quality does:

| Tool | Forced T/A-pose | Output formats | Multi-view input | Price/run |
|---|---|---|---|---|
| Rodin V2.5 | Yes, `ta_pose` | `geometry_file_format`: glb/fbx/obj/stl/usdz | up to 5 images | $0.40 (Extreme-High $0.80) |
| Meshy 6 | Yes, `ta_pose` | GLB / FBX / OBJ / USDZ | single image | $0.80 |
| Tripo H3.1 | No | no format param, GLB in practice | multiview endpoint, 2–4 | $0.20–0.65 |
| Hunyuan3D V3 | No | GLB mainly | front/back/left/right | $0.375–0.675 |

Confirm the current price, version and parameter names on the service's own docs before
committing to one — all of them change faster than this table.

**What `ta_pose` does is *correct* a non-T-pose input into a T-pose.** Image-to-3D
otherwise reconstructs the input pose faithfully — so **a tool without that parameter
still works if you supply a T-pose reference**. Tripo and Hunyuan3D stay viable; you just
carry the T-pose requirement yourself. **Ask "can it output FBX/OBJ?" first**, because
Mixamo won't take GLB and a GLB-only tool adds a conversion hop (§1).

## 4. Multi-view parameters (Tripo `multiview-to-3d`; others share the shape)

- **The `images` array is positional, not name-based**: `front, left, back, right`.
  `front` required, 2–4 accepted.
- **The trap:** pass `[front, back]` and **the back view is consumed as `left`** — the
  model believes it is a profile and the result is destroyed. To place a back view
  correctly you **must supply three entries**.
- Recommended: `texture_quality: detailed`, `geometry_quality: detailed`, `quad: true`,
  `pbr: true`, `texture_alignment: original_image`, `orientation: align_image`,
  `auto_size: false`.
- **Left/right semantics** (camera-left vs character-left) are rarely documented. Guess
  wrong and the model mirrors: near-symmetric characters barely notice, asymmetric
  accessories land on the wrong side.
