# Skeletal or frames — the decision, and what each one is paid in

> Part of the `unity-2d-animation` skill. Frame animation is paid once, in texture area. Skeletal
> animation is paid every frame, in vertices. Neither is the modern one. The choice is made per
> character from four numbers — joints, clips, instances on screen, variants — and it is made
> before the artist splits a single layer, because the split is the cost.

## 1. The decision

| The character | Choose | Why |
|---|---|---|
| Few frames, strong poses, pixel art | Frames | A bone rotates pixels off the grid; the look is the hand-drawn pose |
| Silhouette changes: turns to camera, squash to a different shape, cloth that flips | Frames | Bones move what was drawn. They cannot draw what was not |
| Many clips on one body: run, climb, carry, launch, hurt, idle variants | Skeletal | Each further clip is rotations, not a sheet |
| Outfits, helmets, skins on one set of clips | Skeletal + a library | One set of clips drives every variant — `reference/sprite-library.md` |
| A limb that has to reach a point decided at runtime | Skeletal + IK | A frame cannot aim — `reference/ik-2d.md` |
| A crowd: twenty or more of one kind on screen | Frames, or skeletal with a hard vertex budget | The per-frame cost multiplies by the instance count |
| Effects: dust, sparks, a launch flash | Frames | Nothing bends |
| Large, smooth, high-resolution art | Skeletal | Frames at that size are the whole texture budget |

Courier-run reading of the table: the runner is skeletal — eight joints, ten clips, four helmets,
one instance. A sentry on a ledge is skeletal on a strict budget, or frames when a level puts
thirty on screen. Hazards and pickups are frames. The gate is a sprite with two states.

## 2. What frames cost

Texture area, and nothing per frame beyond a sprite swap.

```
bytes (uncompressed RGBA32) = clips × frames × canvasW × canvasH × 4
8 clips × 8 frames × 256 × 256 × 4  =  16.8 MB       one character, before compression
```

Compression divides that; atlas packing trims the transparent margin. It still scales with every
clip added and with the square of the resolution. The renderer side is as cheap as 2D gets: one
`SpriteRenderer`, a quad or a tight mesh, batched with every neighbour that shares its atlas and
material. Building the clips: `unity-2d-sprites` → `reference/sprite-animation.md`.

## 3. What a skeleton costs

One mosaic texture for the whole character, whatever the number of clips —
`1024 × 1024 × 4 = 4.2 MB` uncompressed holds a twelve-part runner at the same on-screen size as
the sheet above. Clips are curves on bone Transforms: kilobytes each. The price moved to the frame:

| Per frame, per instance | Scales with |
|---|---|
| Animator writing bone Transforms | bones × animated properties |
| IK solving | solvers × iterations — `reference/ik-2d.md` |
| Deformation | vertices × influences, per part |
| Bounds update and culling | parts |
| Drawing | parts, and whether they batch |
| Transform hierarchy | bones + parts + IK targets: all GameObjects |

Put the audit's `characters` row next to the instance count:

```bash
unity command eval 'return SkinningAudit.Json("Assets/Art");'
# "characters":[{"root":"Runner_GO","skins":12,"boneTransforms":18,"vertices":640,"triangles":900, …
```

A working budget for a mid-range phone: under 1,000 vertices and 25 bones for the one hero
character, under 300 vertices and 12 bones for anything that appears ten at a time. Treat them as
a starting line and move them with a profile, not with a feeling: the deformation shows up under
the markers `DeformationManager.LateUpdate` and `BaseDeformationSystem.ScheduleJobs`, IK under
`IKManager2D.UpdateManager` (`unity-profiling` → `reference/where-the-time-goes.md`).

The cheapest vertex is the one not generated. In the Skinning Editor's Auto Geometry panel,
*Outline Detail* and *Subdivide* set the count; a forearm needs a ring of vertices at the elbow
and almost nothing else. And a part that never bends needs no skin at all: parent its renderer
to the bone.

## 4. CPU or GPU deformation

Two paths deform a `SpriteSkin`, and the project picks between them globally. A part runs on the
GPU path only when **all** of these hold; otherwise it runs on the CPU path:

1. The platform supports compute shaders.
2. The active render pipeline is URP and its asset has the **SRP Batcher** on.
3. Player Settings → Other Settings → **GPU Skinning** is *GPU* or *GPU (Batched)*
   (`meshDeformation: 1` or `2` in `ProjectSettings.asset`).
4. The part's renderer is SRP-Batcher compatible, and its material's shader declares the
   `SKINNED_SPRITE` keyword. URP's Sprite-Lit-Default and Sprite-Unlit-Default do; a Shader Graph
   needs the Sprite Skinning node wired into the vertex stage.

| | CPU path | GPU path |
|---|---|---|
| Deforms | in jobs, on worker threads | in the vertex shader, from a bone buffer |
| Draws | through the 2D renderer's own dynamic batching: parts sharing a texture and material and adjacent in sort order merge | through the SRP Batcher: one draw per part, cheap state changes, no merging |
| Wins when | many parts with few vertices each | few characters with dense meshes |
| Falls over when | vertex count × instances climbs | part count climbs |

The 2D renderer's batching is its own system; the *Dynamic Batching* checkbox in Player Settings
does not affect it.

**What pushes one part back to the CPU while the project is set to GPU:**

- a `MaterialPropertyBlock` on the renderer — the usual way a hit flash is written;
- a sprite mask interaction on the renderer;
- a shader without the keyword. The Console says
  `<name> is using a shader … without GPU deformation support. Switching the renderer over to CPU deformation.`
  (2D Animation 14 names the shader in the middle of that line.)

Three cases to treat as having no working GPU path until a build on your own target shows a
bent joint rendering correctly:

- A `ShadowCaster2D` that takes its shape from the skin does not render correctly on the GPU
  path. Keep such characters on the CPU.
- Android on OpenGL ES 3 has no GPU path and no automatic fallback (Vulkan is supported).
- WebGL has neither (WebGPU is supported).

For a build that can land on OpenGL ES 3 or WebGL, leave GPU Skinning on *CPU*, or run the
character on that target and look at one bent joint before shipping.

`SpriteSkin.forceCpuDeformation` is not an opt-out. It makes the CPU pass run **as well as** the
GPU one, so that `GetDeformedVertexPositionData()` has something to return — the hook for a
script that needs the deformed outline. Leave it off unless something reads those vertices.

On 2D Animation 14 (Unity 6000.4) each `SpriteSkin` also has a **Bounds Mode**: *Vertex Based*
(the default; exact) or *Bone Based* (bounds from the bones, which lets the GPU path skip the CPU
vertex pass it otherwise runs for culling). On 13 the field does not exist and bounds are always
vertex based. Scripts that must compile on both leave it to the Inspector.

Check which path is live instead of inferring it: Frame Debugger, select a part's draw — an
`SRP Batch` entry is the GPU path, a merged sprite batch is the CPU path.

## 5. Off-screen

| Switch | Default | Off means |
|---|---|---|
| `SpriteSkin.alwaysUpdate` | on | a part whose renderer is culled stops deforming |
| `IKManager2D.alwaysUpdate` | on | solvers stop while none of the skins their chains drive is visible |
| `Animator.cullingMode` | Always Animate | *Cull Completely* stops the clip too — and then events on it do not fire |

Turn the first two off for everything except the runner. Leave the Animator animating when an
off-screen clip carries gameplay — a sentry whose patrol turn is an event.

## 6. Deformation quality

Skinning here is linear: a vertex lands at the weighted average of where each bone would carry
it. Two consequences decide the art direction more than any setting:

- **A sharp bend loses volume.** At 120° an elbow weighted half and half pinches inward. The
  cures are in the art and the mesh — overlap the upper and lower arm as two layers with a round
  joint, or add a ring of vertices each side of the joint — not in more bones.
- **Nothing is redrawn.** A head turn, an open hand, a blink are sprite swaps, not deformations
  (§7).

Rotation also resamples the texture. Smooth art hides it; pixel art does not, which is why
pixel-art characters are frames or rigid, unskinned parts.

## 7. Both on one character

The split that works: bones for what bends, frames for what changes shape.

| Part | Technique |
|---|---|
| Torso, limbs, cape | Skinned sprites on the skeleton |
| Hands, mouth, eyes | A rigid sprite parented to a bone, with a `SpriteResolver` keyed in the clip: category `hand`, labels `open`, `fist`, `point` |
| Helmet, pack, carried pickup | A rigid sprite parented to a bone; equipment swaps its library category |
| Dust at the feet, the launch flash | A separate child object with its own frame clip, spawned or toggled by an animation event (`unity-animation` → `reference/events-and-windows.md`) |
| One hand-drawn smear frame in a fast attack | A full-body sprite on its own renderer, enabled for two frames by the clip while the rig's renderers are disabled |

One Animator on the root drives all of it: bone rotations, resolver keys and renderer toggles are
curves in the same clip, so the state graph does not know which technique a part uses
(`unity-animation` → `reference/sprite-state-graph.md`). Keying the resolver is in
`reference/sprite-library.md` §5.

## Checks

- The audit's `characters` row × the largest instance count in any situation is inside the budget
  written in the brief.
- `grep -n 'meshDeformation' ProjectSettings/ProjectSettings.asset` matches the decision in §4
  for every build target, not only the Editor's.
- With GPU Skinning on, the Console is free of `without GPU deformation support` after one play
  through each situation.
- Frame Debugger: the runner's parts draw in the number of batches expected for the path chosen.
