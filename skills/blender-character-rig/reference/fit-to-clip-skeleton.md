# Fit the mesh to the clip pack's skeleton — rig once, play every clip unchanged

> Part of the `blender-character-rig` skill. The stages run headless:
> `reference/headless-pipeline.md`. When this route beats retargeting, with the numbers:
> `blender-retarget` → `reference/route-bakeoff.md`.

**The character fits the skeleton; the skeleton does not fit the character.** When one purchased
or captured pack supplies the motion, its skeleton becomes the canonical one. Each new character
moves that skeleton's joints onto its mesh once, and every clip in the pack then plays as bought,
Generic, with no per-clip step. In a tennis game, 75 purchased clips played on two fitted
characters with limb directions within 0.0002° of the same clip on the pack's own body.

## What fit may change, and what it may not

| Kept exactly as the pack's | Changed per character |
|---|---|
| bone names, parents, the root node and its transform | joint positions, so bone lengths |
| every bone's **rest rotation** (its local axes, the roll convention every clip assumes) | the mesh, posed into the pack's rest pose |
| the bone count; no bone added except sockets | sockets for props, children of a hand bone |

A clip key is a rotation away from the bone's rest, so the rest rotations are the contract: gate
them (`rest_rotation_max_deg` < 0.5°; measured 0.00002°). Names and parents are gated at 0
differences, the bone count exactly.

## The fit, step by step

1. **Survey both bodies the same way.** Slice the pack's own body and the character's mesh with
   `bcr_survey`'s method (cross-section outlines: crotch, shoulder line, neck, top, torso and leg
   centre lines, shoulder to fingertip). Read each pack joint in those body-relative coordinates
   and write it back in the character's. Average left and right into a mirror pair.
2. **Canonical scale.** `k = pack hip height / character hip height`. Scale the whole character by
   `k`, so the hip translation in every standard clip lands at this character's hip unchanged; the
   Unity prefab root takes `display_scale = 1 / k` to give back the real height (one character:
   k = 1.056487, display 0.946533). Put the root node where the pack's clip files put it.
3. **Build the armature in the mesh's pose.** Limbs, neck and head are swung from the pack's
   direction onto the measured one (shortest arc, the pack's roll kept); hip and spine untouched.
4. **Bake the mesh into the pack's rest pose.** The mesh is A-pose, the pack T-pose. Skin it once
   by position (`bcr_skin`), pose every swung bone back to its pack rotation, apply the deformation,
   make that the rest pose with the pack's rotations written exactly. Discard these transport
   weights; the skin stage weights the final pose.
5. **Sockets.** The pack's demo prop, bone-parented to the hand in every clip file, is the grip
   convention: the socket sits at the prop's grip in the hand's local frame, scaled by the hand
   ratio. A second socket for the prop's working point (a racket's string-bed centre, +Y along the
   face normal) is measured from the game's own prop mesh. The prop mesh is bone-parented to the
   socket.

## Choices the numbers settled

- **Hip width: take the pack's, not the mesh's.** With the width measured from the mesh, the added
  foot slide on a forehand was 2.1 cm and on a smash 1.85 cm (gate ≤ 1.5); with the pack's width,
  1.2 and 0.95 cm. A wider stance moves the feet off the paths the mocap planted.
- **Soles on the floor: measure `k` on the straightened legs** (an option, on where needed). `k`
  read from the A-pose hip height left one character's rest soles at −1.15 cm (gate |z| < 1 cm),
  because the clips stand her on legs swung 8.6° straighter, which reach lower. Fix: after the
  bake, read the lowest sole `s` and the hip height `h`, scale everything (mesh, joints, sockets,
  bone lengths) by `c = h / (h − s)` about the vertical through the origin and lift by
  `dz = (1 − c) h`: the hip stays at the pack's height and the soles land on Z 0. Here s = −1.154
  cm, h = 1.00367 m, c = 0.98863, dz = 1.141 cm; `k` 1.14895 → 1.13589, `display_scale` 0.87036 →
  0.88037. The gate is not loosened and the mesh shape is not edited. Measuring the mesh's own hip
  width also fixed the soles, but raised added slide to 3.1 cm: rejected.
- **Turning the option on for a character already installed** changes its `k` (0.8% on the other
  body) and every measurement taken on it; it was left off there because −0.81 cm passed.
- **Skin method by measured self-intersection, not by habit.** Run bone heat and positional
  skinning (`bcr_skin`), pose both through about 18 extreme poses, count newly self-intersecting
  triangles, keep the lower. A double-shell body (clothes over a body): heat leaked no weight but
  tore the shorts, p95 13.2%; positional 6.3%. Chosen automatically, gated ≤ 8%.
- **A middle spine bone that gets no vertex** (`deform_bones_without_vertices` fails; its best
  weight 0.29 under distance ÷ radius) → weight the spine bones as one `gradients` chain
  (`reference/armature-and-skinning.md`): 156 vertices, intersections p95 2.0%.
- **Fingers do not deform** when the game camera cannot see them; their weights go to the hand.
- **At most 4 influences.** Measured with 2 in Unity: new intersections 6.2 → 6.8%, 3.7 → 4.6%,
  5.5 → 6.4% on three clips, joints unchanged. The game raised its low tier to 4 bones instead
  (`unity-rigged-character` → `reference/unity-import.md` §3).

## What fit does not fix

- **Grip error from proportions.** On every route the hand ended 5 to 7 cm from where the pack's
  body held the prop at contact (one character's shoulders 4.7 cm wider per side, arms 92% of the
  pack's): the same joint angles put a different hand in a different place. It is a position
  error, not an angle error; IK in the game closes it (`unity-animation`). Lengthening the arms in
  fit would change the character's look, which is a person's call.
- **Absolute foot slide in the mocap itself** (`blender-retarget` → `reference/route-bakeoff.md`).

## A rig from a service, on this route

An auto-rig service's export can replace fit only if it passes fit's and skin's gates: the pack's
bone names and parents exactly, the root node the pack's, rest rotations within 0.5° of the pack's
rest, joints inside the mesh, asymmetry < 3 cm, rest soles |z| < 1 cm, no unweighted vertex,
≤ 4 influences. A general service returns its own skeleton (own names, A-pose, own roll), which
fails this contract; converting it is redoing the second half of fit.
