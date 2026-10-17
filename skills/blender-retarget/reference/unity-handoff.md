# Handing off to Unity: contracts to choose before export

> Part of the `blender-retarget` skill. How a `brt_*` module is called and what every `run`
> returns are in `SKILL.md`.

A retargeted library in Blender is a control rig driving a mesh. Unity needs a runtime skeleton,
skin on it, and clips keyed on that skeleton. Choose the contract first — which skeleton is the
runtime one, which file is the animation source, which side owns the hand and prop corrections —
then export the smallest set that tests it.

## Two routes, pick one

| | (a) The rig exports the skeleton | (b) The source clips stay the animation |
|---|---|---|
| Character | deform skeleton and skin, exported from the rig | the same export, built into a Humanoid Avatar |
| Clips | baked from the control rig onto the deform bones | the source clip FBX files, imported Humanoid; Unity retargets them |
| Clip corrections made in Blender (rest conversion, wrist, mapping) | baked into every clip | not in the clips: the source files predate them |
| A clip fixed later | re-bake and re-export that clip | nothing to export; the fix must be made in Unity, if it can be |
| Bones outside the humanoid set | animate as keyed | outside the mapping; check in Play mode that they move |
| Choose when | the Blender corrections matter, or the clips are few | the source clips are clean humanoid motion, and many |

**Do not mix the routes per clip.** The same move fixed in Blender and played raw from its source
file behaves two ways, and nobody can tell which one a bug report means.

## A control rig is not a runtime skeleton

An Auto-Rig Pro control rig — like any control rig — carries controllers, IK targets, poles and
mechanism bones beside the deform bones. Exported as it stands, Unity gets hundreds of transforms
that deform nothing, IK that never evaluates there, and a hierarchy the Avatar cannot map.

- Export the deform skeleton only, through the rig's own export path for a humanoid target, and
  bake the clips onto it. Confirm that exporter's options on the installed version before relying
  on one; do not carry them over from another rig.
- Deform-only is right here and wrong for a hand-built rig whose root is non-deform:
  `blender-character-rig` → `reference/fbx-export.md` keeps `use_armature_deform_only` off for
  that reason. Either way, check the exported skeleton keeps a single root above the hips.
- Count the exported bones and read their names. The hips → spine → chest → neck → head chain,
  and per side the shoulder, upper arm, forearm, hand, thigh, shin and foot, are what the Avatar
  maps.

## Clips and who moves the character

| Setting | Default | Note |
|---|---|---|
| Clip variant | in place (clip vendors label it NoRoot or InPlace) | the controller owns the position |
| Apply Root Motion | off | `unity-animation` → `reference/root-motion.md` |
| Bake Into Pose, Root Transform Rotation | on for locomotion | no slow turn over a long run |
| Bake Into Pose, Root Transform Position (Y) | on, except a clip whose height change the game wants (`HurdleVault` may) | read Based Upon (Original or Feet) per clip |
| Bake Into Pose, Root Transform Position (XZ) | only on a clip authored in place | §3 of that reference says why |
| Foot IK on the Animator state | decided per clip, in Play mode | Humanoid only |

Confirm the exact option names in the installed Unity version before scripting any of them.

- **Root motion only with a single writer of position**: the Animator, or a script in
  `OnAnimatorMove` — never also a controller calling `Move` with its own velocity
  (`unity-3d-controller`).
- **A take's length is not the game's window.** A source take carries lead-in and settle. Start,
  contact and end frames and the input windows are design decisions, written as events
  (`unity-animation` → `reference/events-and-windows.md`).
- Locomotion becomes a blend tree over direction and speed; one-off actions become states.

## What survives the export

| In Blender | In the FBX | Do instead |
|---|---|---|
| a prop parented straight to a hand bone | a child of that bone | expected; confirm in Unity |
| a prop held by an anchor Empty or a Child Of constraint | the constraint is not written; the Empty arrives as a bare node, and only when empties are exported | parent the prop to the bone for the export, or leave it out and build the socket in Unity |
| a driver, on a shape key or a bone | nothing | key its result, or drive the value from game code |
| bone constraints and IK | sampled into bone keys by the bake | expected; the constraint itself is gone |
| a shape key | a BlendShape, only when the exporter writes shape keys | check that option on your exporter version: the stock FBX exporter documents that Apply Modifiers prevents shape keys. In Unity, Import BlendShapes on the Model tab |
| a shape held through every clip | — | bake it into the mesh, but only if the open shape is never needed |

A prop is its own mesh, parented at runtime to a hand socket: an empty GameObject under the hand
bone that holds the grip offset read in Blender, the prop's rest transform relative to that bone.
The grip point is the prop's origin, or `brt_grip_local` (a 4x4 in the prop's own space) when the
origin sits elsewhere: the same point `brt_drift` checks. Swapping, dropping and handing over are
then game code, not animation.

## The minimal validation

Export the character, the prop, the idle and one action (`GateLatchSwing`) before the library.
Before any export:

- **The prop stays in the hand across every clip**: `brt_drift`, `drift.max_drift` (position) and
  `drift.max_rotation` (angle), with `per_action` and `per_action_rotation` naming the clip that
  slips.
- **Pack only what is used.** Images no material uses can point at paths that do not exist on this
  machine, and `pack_all` then fails on them. Remove or report the images without users, then pack
  the textures the character and the prop use.
- **The saved .blend passes `brt_audit`** from the host shell: exit 0 on `audit.expect_matches`
  (an `--expect` that includes `"images_without_users": 0` and `"images_unpacked": 0`) and
  `audit.props_parented` (`--props`: the anchor's parent and bone, the prop's parent). Exit 1 is a
  failed gate; exit 2 is refused input, such as an empty `--expect`. Its one `BRT_AUDIT_JSON` line
  holds the metrics; `actions` counts only the library's registered actions.

All of these read the file as Blender plays it; none reads the FBX.

1. **Back into Blender.** Bone names and parents, scale 1, weights (groups present, at most 4
   influences, nothing unweighted), each action's frame range. `blender-character-rig` →
   `reference/fbx-export.md` runs it as snapshot → export → re-import → gate.
2. **Into Unity.**
   - Rig tab Humanoid; Configure: every required bone mapped, no left and right swapped.
   - Pose: the Avatar's T-pose matches the character; Enforce T-Pose when it does not.
   - Axes: the character faces +Z with the root at rotation (0, 0, 0). A −90° X on the root is an
     axis conversion that was not baked.
   - Scale (1, 1, 1) on the root and the authored height.
   - Materials: textures found, no white mannequin.
   - The idle and the action play on the character, and the prop follows the hand.
3. **Route (b) only.** Clip files from one source rig get one Humanoid Avatar built from that rig,
   shared among them with Copy From Other Avatar; the character keeps its own Avatar, and Humanoid
   retargets between the two. Clips from the A-pose rig and the T-pose rig need one Avatar each.
   The importer mechanics are `unity-rigged-character` → `reference/unity-import.md`.
4. Only then the whole library.

## What retargeted clips do not know

Retargeting moves a pose from one skeleton to another. It knows nothing of the game.

- **Contact and timing**: when the swing meets the latch, where the latch is, which way the face
  points. Events and windows in the Animator; the target's position comes from the game.
- **Reach**: a different body puts the hand somewhere else. Hand IK toward a target is a runtime
  layer (`unity-animation` → `reference/ik-and-rigging.md`).
- **Feet**: no planting on uneven ground. Foot IK and grounding (`unity-3d-controller`).
- **A second actor**: a two-person clip needs two characters, their relative placement and one
  shared clock — not two clips played one after the other.
- **The budget**: a dense generated mesh needs LODs, retopology and rebaked maps for the target
  platform, and no triangle count fits every game. Retopology or decimation after skinning breaks
  the weight backups (`reference/weight-repair.md`) and the UV match of the baked maps: plan it
  once the Avatar and the movement are proven, before rigging the final asset.

## Where the rest lives

| Need | Skill |
|---|---|
| The importer, the Avatar, Copy From Other Avatar, the Animator layout | `unity-rigged-character` |
| Animator states, blend trees, events and windows, root motion, IK | `unity-animation` |
| Who moves the character, the Animator bridge, grounding | `unity-3d-controller` |
| The FBX round trip from Blender | `blender-character-rig` |
