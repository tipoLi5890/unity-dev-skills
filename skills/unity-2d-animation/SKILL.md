---
name: unity-2d-animation
description: >-
  Skeletal 2D characters: PSB rig, bones and weights, sprite swaps, 2D IK (2D
  Animation package).
---

# unity-2d-animation — a skeletal sprite is a mesh, and it costs like one

> **A bone turns a sprite from a quad the 2D renderer batches for nothing into a skinned mesh.**
> Every vertex is moved by up to four bones every frame, on the CPU unless four separate
> conditions hold, and each part of the character is its own renderer. A twelve-part runner is
> twelve skinned meshes; a patrol of twenty sentries is two hundred and forty. Frame animation
> pays in texture memory and nothing per frame; skeletal animation pays per vertex, per part, per
> frame. Choose per character, and count before the art is drawn.

## The situation → what to read

| The situation | Read |
|---|---|
| "Bones or frame-by-frame"; what a rig costs in memory, CPU and draw calls; when GPU deformation is on and why a part fell back; mixing both on one character | `reference/skeletal-vs-frames.md` |
| "Import this PSB as a character"; importing a PSB; mosaic, rig and layer-group settings; a `.psd` that imports as one flat texture; "the bones came off after a layer was renamed"; sharing one skeleton between two PSBs | `reference/psd-to-rig.md` |
| Skinning Editor order; "the elbow folds like paper"; a part left behind when the body moves; `SpriteSkin` states, Auto Rebind, bounds and culling; one part passing in front of another on the same sprite | `reference/bones-and-weights.md` |
| Sprite Library assets, categories and labels; "swap the helmet at runtime"; a whole-skin swap; animating the resolver; variant libraries; a swapped part frozen in its bind pose | `reference/sprite-library.md` |
| IK Manager 2D; Limb, CCD or FABRIK; "the 2D leg bends backwards"; IK on top of a clip; feet on a slope | `reference/ik-2d.md` |
| Frame clips: equal-canvas frames into an `AnimationClip` | `unity-2d-sprites` → `reference/sprite-animation.md` |
| Sprite metadata from script; the bone and mesh data providers on the importer | `unity-2d-sprites` → `reference/data-provider.md` |
| Animator parameters and the bridge that writes them | `unity-animation` → `reference/parameter-contract.md` |
| The idle, run, jump, fall, hurt graph over these clips | `unity-animation` → `reference/sprite-state-graph.md` |
| Footsteps, hit windows and other events on a clip | `unity-animation` → `reference/events-and-windows.md` |
| A limb drawn over the torso when it should be under; Sorting Group on a multi-part character | `unity-2d-rendering` → `reference/sort-order.md` |
| Packing the parts with the rest of the art | `unity-sprite-atlas` |
| Where the frame time goes once the rig is in the scene | `unity-profiling` → `reference/where-the-time-goes.md` |
| Adding the 2D packages to a project | `unity-new-project` → `reference/package-bootstrap.md` |

Copy `resources/SkinSwap.cs` into a Runtime assembly that references `Unity.2D.Animation.Runtime`,
and `resources/Editor/SpriteLibraryBuilder.cs` and `resources/Editor/SkinningAudit.cs` into an
Editor one that also references `Unity.2D.Animation.Editor`. IK types live in a third assembly,
`Unity.2D.IK.Runtime`, under `UnityEngine.U2D.IK`.

```
PSB layers ─► PSD Importer ─► sprites + a prefab ─► Skinning Editor ─► SpriteSkin on each part
              (mosaic, rig)   (one renderer/layer)  bones→geometry→weights   (bone Transforms)

per frame:   Animator writes bone Transforms
             SpriteResolver  (order −20)  picks the sprite a part shows
             IKManager2D     (order −10)  LateUpdate: solvers overwrite the limb chains
             SpriteSkin      (order +10)  deforms the mesh from the Transforms it finds
```

| Layer | Owns | Never knows about |
|---|---|---|
| The `.psb` and its `.meta` | layers, sprite ids, bones, geometry, weights | the scene |
| `SpriteSkin` | which Transform drives which bone of the sprite it shows | what the pose means |
| `SpriteLibrary` + `SpriteResolver` | which sprite a category and label resolve to | bones |
| `IKManager2D` and its solvers | the last word on a limb chain each frame | game state |
| The Animator | bone rotations and resolver keys over time | devices, physics |

The bones are ordinary Transforms. Anything that can rotate a Transform animates the rig, and
anything that renames, re-parents or deletes one breaks it without a compile error.

---

## 0. Is the package here, and which path deforms

```bash
grep -n -A1 '"com.unity.2d.animation"\|"com.unity.2d.psdimporter"' Packages/packages-lock.json
grep -n 'meshDeformation' ProjectSettings/ProjectSettings.asset    # 0 CPU · 1 GPU · 2 GPU (Batched)
grep -rn 'm_UseSRPBatcher' --include='*.asset' Assets Settings 2>/dev/null
```

- **Neither package resolved** — `com.unity.feature.2d` brings both; a 3D project adds
  `com.unity.2d.animation` and `com.unity.2d.psdimporter`. Majors pair with the Editor: 13.x and
  12.x on 6000.3, 14.x and 13.x on 6000.4. Everything in `resources/` compiles on both.
- **`meshDeformation: 0`, or no URP, or the SRP Batcher off** — every `SpriteSkin` deforms on the
  CPU and the 2D renderer batches the results. That is the right default for many small parts.
- **All three set** — parts whose shader supports sprite skinning deform on the GPU and draw
  through the SRP Batcher, one draw per part. `reference/skeletal-vs-frames.md` says when that
  wins and which features silently push a part back to the CPU.

## 1. Start here

1. **Decide per character, before the art exists.** The runner bends at eight joints, wears four
   helmets and is on screen once: skeletal. A hazard that flickers through six frames: frames.
   Twenty sentries on one screen: count vertices first. → `reference/skeletal-vs-frames.md`
2. **Get the art in as a rig.** A `.psb` (not `.psd`), one layer per part, unique layer names,
   neutral pose. Import Mode *Individual Sprites (Mosaic)*, *Use as Rig* on.
   → `reference/psd-to-rig.md`
3. **Rig in order: bones, geometry, weights.** Weights are generated from the bones that overlap
   the geometry, so a bone moved afterwards means weights redone. Then *Apply*, or nothing is
   saved. → `reference/bones-and-weights.md`
4. **Audit what was built** — `resources/Editor/SkinningAudit.cs`, one JSON object:

```bash
unity command eval 'return SkinningAudit.Json("Assets/Art/Runner");'
```

   `problems` is 0 when no vertex is unweighted, no weight names a missing bone, and every
   `SpriteSkin` is `Ready`. The `characters` rows are the budget: skins, bone Transforms,
   vertices and triangles one instance deforms each frame.
5. **Make the swappable parts a library.** `resources/Editor/SpriteLibraryBuilder.cs` builds a
   `.spriteLib` from `Helmet/courier.png`-style folders or from `helmet_courier`-style sprite
   names; it reports and waits. `resources/SkinSwap.cs` changes skins and equipment at runtime.
   → `reference/sprite-library.md`
6. **Add IK only to chains gameplay has to place** — a hand on the gate switch, feet on a
   sloped roof. → `reference/ik-2d.md`
7. **Hand the clips to the Animator.** Parameters, states, events and transitions are the same
   as for any other clip: `unity-animation` → `reference/parameter-contract.md`.

## 2. The cost model in one table

| | Frame clip | Skeletal, CPU deformation | Skeletal, GPU deformation |
|---|---|---|---|
| Paid in | texture area: one cell per frame | CPU: vertices × influences, per part, per frame | GPU compute, plus one SRP-batched draw per part |
| Renderers per character | 1 | 1 per layer | 1 per layer |
| Batches with its neighbours | yes, same atlas and material | yes — the 2D renderer batches deformed parts | per-object draws; no dynamic batching |
| New animation costs | a new set of frames | a clip of rotations: kilobytes | the same |
| Breaks when | the canvas or pivot differs between frames | a bone Transform is renamed or missing | also: a `MaterialPropertyBlock`, a sprite mask, a `ShadowCaster2D` sourced from the skin |
| Fits | few frames, pixel art, effects, crowds | many low-vertex parts | a few high-vertex characters |

Off-screen cost is a switch on each side: `SpriteSkin.alwaysUpdate` and `IKManager2D.alwaysUpdate`
both default to on. Turn them off on anything that is not the runner and a culled sentry stops
deforming and solving.

## Discipline

- **Count before drawing.** Vertices × parts × instances is decided when the artist splits the
  layers, not when the profiler complains. Run the audit on the first rigged character and set
  the budget from its `characters` row.
- **Bones, then geometry, then weights — and *Apply*.** Editing a bone after weighting leaves
  weights that describe a skeleton that no longer exists. Nothing reaches the `.meta` until
  *Apply*.
- **Judge weights in an extreme pose.** A rest pose hides every bad weight. Bend each joint to
  its limit with *Preview Pose* before leaving the editor; *Reset Pose* afterwards.
- **Four bones per vertex is the ceiling, two is the target.** A vertex stores four influences;
  a limb joint needs two. Three and four are for a torso or a face.
- **A layer name is an id.** With mapping by layer name, a renamed layer is a new sprite with no
  bones. With mapping by layer id, a layer deleted and redrawn is. Agree on one with the artist
  and write it in the brief.
- **A category and a label are an id too.** The resolver's key is a hash of `category_label`.
  Rename either and every clip and prefab keyed on it stops changing the sprite, with no error.
- **Every swappable rigged part has Auto Rebind on, and the same bone names.** The importer
  leaves it off. Without it a swapped sprite keeps the old bone list and deforms wrongly or not
  at all.
- **`AddOverride` with a library asset does not refresh.** Call `RefreshSpriteResolvers()`
  after it, or use `resources/SkinSwap.cs`, which does.
- **IK has the last word, so give it few words.** A solver overwrites whatever the clip wrote
  to its chain. Blend with `weight`; do not key the bones of a chain and solve it at full
  weight at once.
- **Solver order is dependency order.** A torso solver sits above the arm solver that hangs
  from it.
- **Do not skin what does not bend.** A helmet, a crate, a pickup carried in the hand: parent
  the renderer to the bone. No `SpriteSkin`, no weights, and it batches as a plain sprite.
- **Flip the root, never a bone.** Facing is the root's `localScale.x` sign or a 180° turn about
  Y. A negative scale on one bone mirrors what hangs from it and nothing else, and the rig's
  left and right stop agreeing.
- **The human keeps the look verdict.** The audit says no vertex is unweighted; it cannot say
  the shoulder reads well. Capture the extreme pose and show it.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Animator state graphs, blend trees, override controllers; 2D lights and shadows on the character | `unity-animation`; `unity-2d-rendering` |
| Slicing, pivots, an Aseprite or sheet source | `unity-2d-sprites` |
| Moving the character: grounding, jumps, slopes, facing from velocity | `unity-2d-controller` |
| Colliders and hitboxes that follow a bone | `unity-physics-2d` |
| Pixel-art filtering and camera snapping | `unity-2d-pixel-perfect` |
| 3D rigs, Humanoid Avatars, Mixamo | `unity-rigged-character` |
| Rigging and animating a 3D mesh in Blender | `character-autorig` (default) · `blender-character-rig` (hand-built fallback) |
| Generating the layered artwork | `codex-visual` |
| Recording a run and asserting on it | `unity-play-harness` |
