# Bones, geometry, weights — and the component that plays them back

> Part of the `unity-2d-animation` skill. The Skinning Editor has three stages and each one is
> computed from the one before: geometry is generated to suit the bones, weights are generated
> from the bones that overlap the geometry. Go back a stage and the later ones describe a rig
> that no longer exists. At runtime `SpriteSkin` knows none of this — it holds an array of
> Transforms and trusts that entry *n* is bone *n* of whatever sprite the renderer shows.

Open it from the `.psb`'s Inspector: *Open Sprite Editor*, then pick **Skinning Editor** in the
module dropdown at the top left. Nothing is written to the `.meta` until **Apply**.

## 1. Bones

| Do | Why |
|---|---|
| One root at the hips, then spine, then limbs outward | The root is what the Animator moves for a whole-body bob; limbs inherit it |
| A bone per segment that rotates on its own; none for what does not | A bone is a Transform in every instance and a matrix in every skinned part it touches |
| Joint positions on the overlap between two layers | The pivot of the bend is the bone's start point, not the art's edge |
| Name every bone, with a side suffix: `arm_upper_l`, `leg_lower_r` | Names are how clips, Auto Rebind and IK find them. `bone_17` is a bug waiting for a second file |
| Limbs drawn slightly bent | A Limb solver bends the way the bind pose already leans — `reference/ik-2d.md` |

A humanoid runner lands at 14 to 18 bones: root, spine, chest, head, and three per limb, plus one
or two for a cape or a pack strap. A sentry seen at a third of the size does without the chest
and hands: 10.

Tools: **Create Bone** (click start, click end; keeps chaining), **Split Bone**, **Edit Bone**
(moves a bone without deforming anything — it redefines the bind pose). The Bone panel carries
the name and the **Depth** (§4). The Visibility panel's Bone tab re-parents and reorders by drag.

## 2. Geometry

**Auto Geometry**, then *Generate For All Visible*, with these as the starting values:

| Slider | Start at | Raise it when |
|---|---|---|
| Outline Detail | low: the outline may cut corners of transparent pixels | the silhouette is visibly clipped |
| Alpha Tolerance | low | soft glows drag the outline far outside the part: raise it to ignore them |
| Subdivide | 0 | a large part has to bend through its middle — a torso, a cape |
| Weights | off | on only for a first rough pass: it runs auto weights in the same click |

Then fix what the generator cannot know, by hand, with **Create Vertex**, **Create Edge** and
**Split Edge**:

- **Two rings of vertices across each joint**, one each side of the bone's start point. A bend
  needs a strip of triangles to fold through; a joint with one edge across it folds like paper.
- **Nothing in the middle of a rigid segment.** A forearm that only rotates needs its outline
  and the rings at its ends.
- **No vertex outside the sprite's rect**, unless *Sprite Padding* on the importer made room.

Vertex count is the cost (`reference/skeletal-vs-frames.md` §3). The audit prints it per
sprite; a limb segment over 30 vertices or a torso over 80 wants a second look.

## 3. Weights

A vertex stores **four** bone influences and their weights; the fifth is dropped. A limb joint
uses two.

1. **Auto Weights** with *Associate Bones* on, *Generate All*. Each sprite is bound to the bones
   that overlap its geometry, and weights fall off with distance.
2. **Bone Influence**, sprite by sprite: remove every bone that should not move this part. The
   forearm overlaps the torso in the bind pose, so the torso picked up the forearm bone — that is
   the vertex on the chest that twitches when the arm swings. Remove it, then *Normalize*.
3. **Weight Brush** or **Weight Slider** at the joints only. *Smooth* mode across the two rings
   turns a hard crease into a bend. Keep *Normalize* on: weights that do not sum to one scale
   the vertex toward the origin.
4. **Preview Pose.** Bend every joint to the limit a clip will ever use, then past it. A rest
   pose shows nothing. Look for: a crease, a vertex left behind, a part following the wrong
   bone, a gap opening at a joint. **Reset Pose** before leaving the mode.
5. **Apply.**

The order of bones in the Bone Influence panel is the order of `SpriteSkin.boneTransforms` for
that sprite. Two sprites meant to swap for each other on one part need the same bones in the
same order (drag to reorder), or Auto Rebind on (§6).

A mirrored limb is copied, not redone: select the finished sprite, **Copy**, select its twin,
**Paste** with *Bones* off, *Mesh* on, *Flip X* on.

| Symptom | Cause | Fix |
|---|---|---|
| The elbow folds like paper | One edge across the joint, or a hard weight boundary | Two vertex rings; *Smooth* across them |
| A part stays behind when the body moves | No bone associated with the sprite | Bone Influence → add the bone; generate weights. Audit: `bonelessSpritesInRiggedAssets` |
| A few vertices stay behind | Unweighted vertices added after weighting | Weight them, *Normalize*. Audit: `unweightedVertices` |
| A patch of the torso moves with the arm | Auto weights associated an overlapping bone | Remove it from that sprite's Bone Influence list |
| A joint thins out when bent far | Linear skinning | Overlap the two layers at the joint; do not add bones |
| It poses in the editor and not in the scene | No *Apply*, or the scene's `SpriteSkin` is not `Ready` | §5 |

## 4. Depth

Inside **one** sprite, which triangles draw in front is decided by the **Depth** of the bone
that influences them: higher is in front, the default is 0, negative is allowed. A torso and an
arm painted as a single layer need it — give the arm bones depth 1 and the arm passes in front of
the body it is welded to. Between **different** sprites depth does nothing: that is Order in
Layer, and `unity-2d-rendering` → `reference/sort-order.md` owns it.

## 5. `SpriteSkin`

One per rigged part, beside its `SpriteRenderer`. Namespace `UnityEngine.U2D.Animation`.

| Member | Meaning |
|---|---|
| `rootBone` / `SetRootBone(Transform)` | Where a rebind starts searching. The importer sets the prefab root |
| `boneTransforms` / `SetBoneTransforms(Transform[])` | Entry *n* drives bone *n* of the current sprite. The setter returns the new `SpriteSkinState` |
| `autoRebind` | Re-resolve `boneTransforms` whenever the renderer's sprite changes. Off by default |
| `alwaysUpdate` | Deform even while the renderer is culled. On by default |
| `forceCpuDeformation` | Also run the CPU pass under GPU deformation, for scripts that read deformed vertices |
| `ResetBindPose()` | Put the bone Transforms back in the bind pose. False when the skin is not valid |
| `HasCurrentDeformedVertices()`, `GetDeformedVertexPositionData()` | The deformed mesh, for a script that needs it |

2D Animation 14 (Unity 6000.4) adds `boundsMode`; it is absent on 13.

**A skin deforms only in the `Ready` state.** Any other state draws the part undeformed, in its
bind pose, with no error:

| `SpriteSkinState` | What is wrong |
|---|---|
| `SpriteNotFound` | The renderer has no sprite |
| `SpriteHasNoSkinningInformation` | The sprite has no bones — it was never rigged, or the rig came off on re-import |
| `SpriteHasNoWeights` | The sprite has bones and its mesh carries no weights. The audit reports the sprite as `no-weights` |
| `RootTransformNotFound` | Root Bone is empty |
| `InvalidTransformArray`, `InvalidTransformArrayLength` | `boneTransforms` is missing, or its length is not the sprite's bone count |
| `TransformArrayContainsNull` | A bone GameObject was deleted, or a prefab override dropped the reference |
| `InvalidBoneWeights` | A weight names a bone the sprite does not have |
| `Ready` | Deforming |

`resources/Editor/SkinningAudit.cs` recomputes the state for every skin in the project's
prefabs and the loaded scenes and lists the ones that are not `Ready`.

The bones are GameObjects, with everything that implies. Parenting a helmet or a pickup under a
bone is the supported way to attach a rigid thing. Deleting a bone, moving it out from under the
Root Bone, or disabling the skin's GameObject mid-clip are all edits to the rig.

A single PNG can be rigged too — bones and weights on one sprite, no PSB. Its `SpriteSkin` is
added by hand, and **Create Bones** in its Inspector builds the Transforms from the sprite's
bones. The button is live only while Root Bone is empty.

## 6. Auto Rebind

When the renderer's sprite changes, the Transform array has to be rebuilt for the new sprite's
bone list. With Auto Rebind **off** nothing happens: the old array is used by index. That is
correct only when both sprites have identical bones in identical order.

With it **on**, the skin searches under Root Bone for a Transform with each bone's **name**;
where a name occurs more than once it takes the one whose **path** matches the bone's parents.
The search runs when the skin next deforms, not at the moment of the swap. When it cannot
complete, the Console says
`Rebind failed for <object>. Could not find all bones required by the Sprite: <sprite>.` and the
part is left in a non-`Ready` state.

The contract between two files is therefore the bone names — which a shared skeleton
(`reference/psd-to-rig.md` §5) guarantees and separate skeletons have to keep by hand. A helmet rigged to `head` rebinds onto any character with a bone called `head` under its
Root Bone. Rename a bone in one file and every swap into it fails with that line.

Binding by hand, for a part instantiated at runtime:

```csharp
var skin = part.AddComponent<UnityEngine.U2D.Animation.SpriteSkin>();
skin.SetRootBone(runnerRoot);
skin.autoRebind = true;                               // resolves by name under runnerRoot
// or, explicitly:  SpriteSkinState state = skin.SetBoneTransforms(bonesInSpriteOrder);
```

## 7. Bounds and culling

The renderer's bounds follow the deformed mesh, so a part that swings far from its bind pose is
still culled correctly. Two things follow from the switches:

- With `alwaysUpdate` off, a culled part stops deforming and resumes on the frame it becomes
  visible. That is the saving, and it is safe for anything whose off-screen pose does not matter.
- A script that reads deformed vertices from a culled skin gets the last deformed pose. Check
  `HasCurrentDeformedVertices()` first; `GetDeformedVertexPositionData()` throws when there are
  none.

## Checks

```bash
unity command eval 'return SkinningAudit.Json("Assets/Art/Runner");'
```

- `problems` is 0: no `no-weights`, `unweighted-vertices` or `bad-bone-index` on a sprite, every
  skin `Ready`, no `missing-bones`, no `swap-without-rebind`.
- `maxInfluences` is 2 on limb segments; 3 or 4 only where it was painted on purpose.
- `bonelessSpritesInRiggedAssets` lists only parts that are meant to be rigid — and each of
  those is parented to a bone in the Prefab Variant.
- One captured frame of the most extreme pose in each clip, looked at by a human.
