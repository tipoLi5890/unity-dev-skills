# Characters on the clip pack's skeleton — Generic import, measuring in batchmode

> Part of the `unity-rigged-character` skill. The Blender side (fitting the mesh to the pack's
> skeleton): `blender-character-rig` → `reference/fit-to-clip-skeleton.md`. Why this route, with
> the bake-off numbers: `blender-retarget` → `reference/route-bakeoff.md`.

On the fit route every character shares one skeleton, the clip pack's, so Unity plays the
purchased clip files themselves on every character. Nothing is retargeted. In a tennis game 75
clips took 4.2 MB in Unity and played within 0.0002° of the same clip on the pack's own body.

## Import rules

`resources/Editor/SharedSkeletonClipImporter.cs` applies all of this to two folders only.

| | Character FBX | Clip FBX (the purchased files, unedited on disk) |
|---|---|---|
| Animation Type | Generic | Generic |
| Avatar | Create From This Model | Create From This Model, or Copy From Other Avatar (both worked): Generic curves bind by **path**, so what proves the sharing is a test that every binding resolves on every body, not the Avatar setting |
| Root node | none: the root bone's translation stays in the clips | none |
| Compression | — | Optimal (forehand added slide 0.84 cm; with compression off 1.16 cm: it is not where the error lives) |
| Skin Weights | Standard, 4 bones | — |
| Optimize Game Objects | off: feet, hands and sockets read by IK and tests | — |
| After import | — | RemapRoot, StripNonRootPositions, BakeNodeDefaults (below) |

The three post-import steps, each from a measured fault in the pack:

- **RemapRoot.** The root node's name varied: 63 clips one name, 7 and 8 others. Generic binds by
  path, so those 15 clips bound nothing. Rename the path prefix; no retargeting is involved.
- **StripNonRootPositions.** Four clips carried 2 to 4 keys of sub-1e-4 cm translation on a
  finger, forearm, shoulder or toe. Left in, they replace the fitted character's bone lengths with
  the pack body's. Keep position and scale curves on the root bone only.
- **BakeNodeDefaults.** Keyframe reduction deleted some bones' curves entirely; on the pack's body
  those bones hold that file's node default (a head 8.7° off, one clip's hand 72°), on another body
  they would hold **its** default. Write the file's default rotation as a constant curve.
- `preserveHierarchy` matters only for a clip file with no mesh: with a single root node Unity
  folds it away and every path loses a level. The pack's files each carry the demo body, so they
  need nothing; a converted clip written without a mesh does.

**The prefab:** the character FBX under a root whose scale is `display_scale` (1 / the fit's
canonical scale, written by the fit stage into a manifest: 0.946533 for one body, 0.88037 for
another). The skeleton itself stays at the pack's size so the clips' root translation lands
unchanged. Animator Generic, Apply Root Motion off when the game moves the character, the prop
under its socket. Anything measured in world units on a character (contact points, reach) is
measured on a named reference body and scaled by each body's `display_scale`.

**What Generic gives up:** Humanoid foot IK, humanoid body-part masks, other skeletons' clips.
A Generic Avatar Mask lists transform paths, which still splits upper and lower body. Clips from
another skeleton are converted to the pack's once, offline (`blender-retarget` →
`reference/route-bakeoff.md`).

## Measuring in batchmode: two traps (seen in Unity 6000.3 batchmode)

The import gate samples every clip on the character and on the pack's body in a throwaway lab
project outside the repository (`blender-character-rig` → `reference/headless-pipeline.md`).

| Trap | Measured | Do instead |
|---|---|---|
| A manually updated `PlayableGraph` does not pose the Animator in a batchmode editor: after `graph.Evaluate()` the bones stay in the default pose | every sample read the bind pose | `AnimationMode.StartAnimationMode()`, then per frame `BeginSampling()`, `SamplePlayableGraph(graph, 0, t)`, `EndSampling()`; Humanoid foot IK set on the clip playable is applied too. The same trap waits in an EditMode test |
| `SkinnedMeshRenderer.BakeMesh` keeps returning the bind pose after the bones move | every frame identical | compute linear blend skinning yourself from the imported mesh: per vertex, Σ wᵢ · (boneᵢ.localToWorldMatrix · bindposeᵢ) · v, the same sum Unity skins with. Truncating to the two largest weights and renormalising reproduces a 2-bone quality level |

- **Weld before counting intersections.** Unity splits vertices along UV seams (8,507 positions
  became 16,789 vertices); seam twins read as touching triangles until welded back by position.
- **Compare against the reference in the same lab.** Play the clip on the pack's own body there
  too and measure both with one formula (`blender-retarget` → `scripts/clip_metrics.py`).

## Gates that held

| Gate | Limit | Measured |
|---|---|---|
| clips imported | all | 75 of 75 |
| bindings with no bone, position curves off the root bone | 0, 0 | 0, 0 |
| every clip finite, the root bone moves in every clip | all | all |
| Avatar valid, Generic | yes | yes |
| LODGroups created by the import | 0 | 0 |
| renderers' names, types and triangles equal the export manifest | yes | 6 of 6 |
| every skinned level shares level 0's bones and bind poses; bones per vertex | < 1e-4; ≤ 4 | 3e-5; 4 |
| representative clips: added slide p95 / max; sole height error in plants p95 | ≤ 1.5 / 3 cm; ≤ 3 cm | 0.94 / 0.97 cm; 2.11 cm |
| new self-intersections p95 | ≤ 8% | 6.2% |

In the game itself, two tests earned their place: the contact frame of every swing clip found in
Unity within 0 frames of the frame measured in Blender (30 clips, both bodies), and no late-starting
curve on the bone chain that holds the prop (`blender-retarget` → `reference/route-bakeoff.md`).

## Skin weights: 2 bones or 4

A low quality tier at 2 bones measured, on three clips, new self-intersections 6.2 → 6.8%,
3.7 → 4.6%, 5.5 → 6.4% with joints unchanged. The game raised every tier to 4 bones, which is
what the skin stage gates; the alternative is a skin stage limited to 2 influences so the tier and
the asset agree.

## What the runtime will ask of the clip library

A game that drives these clips from a simulation and corrects them with IK needs more than the
clips: plant windows per loop (annotated at 0.5 m/s, since 0.15 m/s found almost no stance in
in-place mocap loops), each swing's tool-point path around contact (−0.4 to +0.3 s at 120 Hz),
per-joint peak angular speeds for the pop metric, and knee and elbow hinge axes sampled from a
ready pose at rig build. Bake them when the library is built, not at runtime: `unity-animation` →
`reference/foot-lock-and-prop-ik.md` and `unity-animation` → `reference/motion-metrics.md`.
