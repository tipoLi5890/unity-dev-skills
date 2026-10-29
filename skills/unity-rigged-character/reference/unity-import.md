# Unity import and Animator wiring

The importer decisions and one controller layout, whichever route made the FBX. Automate all of
it: `reference/editor-scripts.md` runs every step below from one config file.

## 1. Rig type and the Avatar

Every clip reaches Unity already on the character's skeleton: retargeted in Blender
(`blender-retarget`), at Mixamo on that route, or, on the fit route, because the character was
fitted to the clip pack's own skeleton and the purchased files play unchanged
(`reference/shared-skeleton-generic.md`). Unity never retargets across skeletons in this pipeline,
so the rig type follows from what the game needs, not from where the clips came from.

| Animation Type | Choose when | Gives up |
|---|---|---|
| **Generic** — the default for clips retargeted or keyed in Blender, and for a pack's clips on characters fitted to its skeleton | the clips were baked onto this skeleton, or this skeleton is the clips' own | the body-part AvatarMask (a Generic mask lists transform paths), Humanoid foot and hand IK |
| **Humanoid** | the game needs a body-part AvatarMask, foot or hand IK, or the clips must also play on other avatars | exactness: muscle space re-solves every pose (below) |
| **Legacy** | the old `Animation` component only | the Animator: no blend tree, no layers, no mask |

**Generic reproduces Blender.** World rotations match the Blender action within the importer's
key reduction: under a tenth of a degree with **Anim. Compression Off**, around a degree with the
default Keyframe Reduction. When a held prop must line up with something in the world, turn
compression off (`ModelImporter.animationCompression = Off`) or tighten the rotation error.

**Humanoid moves the pose, so measure it on the real clip.** On a 22-bone courier rig playing a
jog keyed on its own skeleton in Blender, Humanoid put bones 17–20° off the Blender pose at the
worst frames and a hand socket 13–15 cm away from where Blender had it; compression made no
difference. Even with character and clips on **the same skeleton** (a fitted character playing
its pack's mocap), the muscle-space round trip moved limbs 1.5–4.4° and the head up to 5.3°, put
the arm pose 8% off and pushed added foot slide to 2.7 cm on a forehand, where Generic stayed at
0.0002°; foot IK pulled the slide back to 1.2 cm but bent the knees 5–9° more
(`blender-retarget` → `reference/route-bakeoff.md`). The automatic mapping took all 22 body bones
and no finger: a Humanoid with fingers needs an explicit finger map. Build it with
`CharacterHumanoidAvatar.cs` (Build Humanoid Avatar) from the contract map or a `humanMap` file
(`reference/humanoid-contract.md`); it gates on `isValid`, `isHuman`, Chest and the finger count. A clip
whose pose is outside the muscle limits (a knee bent backwards) is clamped, and that joint ends far
off. Before choosing Humanoid:

1. Rig tab → Humanoid → **Configure**. Check that every bone is mapped, not only the required
   ones, and that no left and right are swapped. The automatic mapping can leave an optional bone
   out: a bone named `Chest` was left unmapped while Spine, Neck, both Shoulders and both Toes were
   taken. Map it by hand (or through `ModelImporter.humanDescription`), and re-check `isValid`.
2. Play the clip on a Generic copy and a Humanoid copy of the same FBX and compare a hand or a
   socket at the frames that matter (contact, the widest reach). If the difference shows on
   screen, the clip stays Generic and the mask is built from transform paths instead.
3. **The default pose is not the Blender rest pose.** Unity's imported default pose matched the
   clip's first frame, whether the FBX was exported at a posed frame or with every action baked.
   A Humanoid Avatar built on the assumption of a T-pose is then built on frame 0: use **Enforce
   T-Pose** in Configure, or give `humanDescription.skeleton` the rest pose explicitly.

- **Avatar Definition**: the body takes **Create From This Model**; every animation-only file
  takes **Copy From Other Avatar**, pointing at the body's Avatar (§2). This holds for Generic too:
  a Generic Avatar is what lets several files share one skeleton.
- Check `avatar.isValid` (and `avatar.isHuman` for Humanoid) on every body, from a script, after
  each re-export.

### A GLB character and Humanoid clips

glTFast imports a GLB with its own importer, not the Model Importer, so the file has no Rig tab
and no Avatar Definition. When a GLB character must take Humanoid clips, build the Avatar in code
from bone names, in the Editor or at runtime:

```csharp
// using System.Linq; using System.Collections.Generic;
// glbPrefab: the imported GLB; boneFor: Unity human name -> this rig's bone name
GameObject go = Object.Instantiate(glbPrefab);
Transform[] all = go.GetComponentsInChildren<Transform>(true);
var human = new List<HumanBone>();
foreach (string humanName in HumanTrait.BoneName)
    if (boneFor.TryGetValue(humanName, out string bone) && all.Any(t => t.name == bone))
    {
        var hb = new HumanBone { humanName = humanName, boneName = bone };
        hb.limit.useDefaultValues = true;
        human.Add(hb);
    }
var desc = new HumanDescription
{
    human = human.ToArray(),
    // every transform under the root, at the pose the Avatar is built on
    skeleton = all.Select(t => new SkeletonBone { name = t.name, position = t.localPosition,
                                                  rotation = t.localRotation, scale = t.localScale }).ToArray(),
    upperArmTwist = 0.5f, lowerArmTwist = 0.5f, upperLegTwist = 0.5f, lowerLegTwist = 0.5f,
    armStretch = 0.05f, legStretch = 0.05f, hasTranslationDoF = false
};
Avatar avatar = AvatarBuilder.BuildHumanAvatar(go, desc);
if (!avatar.isValid || !avatar.isHuman) throw new System.Exception("unmapped or misnamed bone");
if (!go.TryGetComponent(out Animator animator)) animator = go.AddComponent<Animator>();
animator.avatar = avatar;
animator.Rebind();                       // without it the Animator keeps the old bindings
```

Instantiate first: `BuildHumanAvatar` reads a live hierarchy, not the asset. The clip then plays
as it does on the FBX Humanoid model. Check the GLB the same way as an FBX: `isValid && isHuman`,
then one clip played and compared at a contact frame. The Generic advice above still applies: an
Avatar is needed only for what Humanoid buys.

## 2. Five importer settings that need automation

1. **Exporters name clips for themselves.** Every Mixamo clip is `mixamo.com`; others arrive as
   `Take 001`, after the Blender scene (`Scene`), or as `<rig>|<action>` when every action was
   baked. Rename each clip from its file name on import, or the Animator cannot tell run from
   jump. The contract: `<name>.fbx` is the body, `<name>@<Clip>.fbx` one clip each.
2. **One FBX = one animation, and only the body carries the mesh.** Animation files set the Rig
   tab to **Copy From Other Avatar**, pointing at the body's Avatar. Otherwise each builds its own
   and **none of them retarget** — the character **T-poses in place** while the Animator reports
   nothing wrong.
3. **Import order is not guaranteed.** Unity may import an animation before the body, when the
   Avatar does not exist yet, and a link made then fails silently. The Avatar link **must be a
   re-runnable command**, not only an `AssetPostprocessor`.
4. **Set `loopPose`, not just `loopTime`.** `loopPose` matches the first and last frames. A run
   cycle is often short, e.g. 17 frames (0.57 s at 30 fps): a one-frame mismatch reads as a hitch
   twice a second, the "something's off but I can't say what" class of bug.
5. **Animator: `applyRootMotion = false`** — belt and braces with In Place clips, since either
   alone is easy to forget.

Plus the prop gotcha: **imported models land on layer 0.** If the camera's culling mask excludes
it, the character **shows in the Scene view and is invisible in the Game view**. Set the model
and all children to the prefab root's layer after parenting (`unity-3d-models` covers this).

**All Editor automation must be re-runnable** — rebuild from a clean state rather than
reconciling with what is there. Re-exports happen constantly.

## 3. Two Rig-tab settings that decide what the game can reach

- **Optimize Game Objects removes the bone Transforms** from the imported hierarchy; the Animator
  still poses the skin, but there is no `Hand.R` GameObject left to parent to. A held prop's
  socket — an empty bone or GameObject under the hand holding the grip offset
  (`blender-retarget` → `reference/unity-handoff.md`) — is gone with them unless it is listed in
  **Extra Transforms to Expose** (`ModelImporter.extraExposedTransformPaths`, the full path from
  the model root, e.g. `RunnerRig/Hips/…/RightHand/PropSocket`).
  - An exposed transform is **re-parented as a direct child of the model root**, not left under
    the hand, and still follows the animated hand. Code that finds it by its old path
    (`Find("RunnerRig/Hips/…/PropSocket")`) gets null: find it by name.
  - Check: with the option on, the socket exists, and at a mid-clip frame it sits where the same
    socket sits on a copy imported with the option off.
- **Skin Weights defaults to Standard: four bones per vertex.** It is the same four the Blender
  skills gate with `max_influences` ≤ 4 (`blender-character-rig`, `blender-retarget`), so a rig
  that passes there needs nothing here. **Custom** (`ModelImporter.skinWeights`,
  `maxBonesPerVertex`) raises the count at a skinning cost; read that cost with `unity-profiling`
  before choosing it.
- **The quality tier's Skin Weights cap wins over the import.** A tier at 2 Bones skins a 4-weight
  character with its two largest weights: new self-intersections rose 6.2 → 6.8%, 3.7 → 4.6% and
  5.5 → 6.4% on three clips, joints unchanged. Set every tier to what the skin stage gates, or
  gate the skin stage at the tier's count (`reference/shared-skeleton-generic.md`).

## 4. An FBX authored in Blender

The Blender side — what goes in the file, the clip name, scale 1, a prop or socket under its hand
bone, the re-import gate — is `blender-character-rig` → `reference/fbx-export.md`; a library baked
from Auto-Rig Pro is `blender-retarget` → `reference/unity-handoff.md`. The Unity-side
differences from a Mixamo set:

- **One file can hold the mesh and the clip**, so there is nothing to link with Copy From Other
  Avatar, and the importer script renames only `@` files — name that clip on the Animation tab,
  or export each further action as `<name>@<Clip>.fbx`.
- **Scale arrives at 1.** Exported with `apply_scale_options: 'FBX_SCALE_ALL'` and unit scale
  applied, the model imports at File Scale 1, the root at (1, 1, 1), and bone positions equal the
  Blender metres once the axis change is applied (Blender (x, y, z) reads as Unity (−x, z, −y)).
  Anything else is unapplied scale in the .blend or an export without `FBX_SCALE_ALL`: fix it
  there, not with the importer's Scale Factor.
- **A socket bone exported deform-only must carry the Deform flag.** The deform-only option drops
  every bone whose flag is off, weighted or not; the socket needs the flag, not weights.
- **Metallic and roughness do not arrive bound** — `reference/textures.md`.

### A held prop with a shape key

A prop or hand that changes shape while held (a strap that tightens, a grip that closes) is a
shape key in Blender. Unity receives it as a BlendShape on the SkinnedMeshRenderer, and only as
values that were keyed: **a Blender driver does not reach Unity.**

1. In Blender, bake the driven value: step through the clip's frames, key the shape key's value
   at each, then remove the driver (`blender-retarget` → `reference/unity-handoff.md`, *What
   survives the export*). The exporter must write shape keys; check its options on your Blender.
2. In Unity, Model tab → **Import BlendShapes** on (`ModelImporter.importBlendShapes`). Open the
   clip: a `blendShape.<name>` curve must be listed. Unity weights run 0–100 where Blender's value
   runs 0–1.
3. Play the clip and read `SkinnedMeshRenderer.GetBlendShapeWeight` at the grip frame. No curve
   → the value was never keyed, or the exporter dropped shape keys.
4. A shape that depends on game state (grip on pickup, open on release) is not animation: drive it
   with `SetBlendShapeWeight` from game code, and leave it unkeyed in the clips.

## 5. Animator structure

**Two run clips (slow + fast) earn a 1D Blend Tree.** Do not time-scale a single clip: slow down
a sprint and the arms still swing like a sprint; speed up a jog and it reads as cartoon
fast-forward. **Blending changes the gait itself.** Drive the blend parameter with the current
speed normalised between minimum and maximum run speed. With one clip only, fall back to scaling
playback rate.

**An upper-body mask on an override layer** for reactions: a hit plays on torso and arms while
the legs keep running, so the character does not stall on every graze. On Humanoid the mask is
expressed in body parts, needs no bone names and survives a re-rig. On Generic it is a transform
mask: an `AvatarMask` with the spine, arm and head paths enabled (`AvatarMask.AddTransformPath`),
rebuilt when bones are renamed. `CharacterAnimatorBuilder.cs` builds the body-part mask on
Humanoid and leaves the Hurt layer unmasked on Generic, and says so in its report.

The controller this describes, and the parameter names the runtime bridge writes, are built by
`resources/Editor/CharacterAnimatorBuilder.cs` (`reference/editor-scripts.md`).
