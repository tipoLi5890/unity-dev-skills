# Auto-rig 2D — a layered PSB to a moving character with no Skinning Editor step

`resources/Editor/AutoRig2D.cs` rigs a PSB from its layer names and positions, or from the rig
file a layer splitter wrote beside it. It writes bones, a mesh and weights for every layer
through the same data providers the Skinning Editor's *Apply* uses. It then builds a Sprite
Library of the face states and a Prefab Variant that carries `resources/RigDriver2D.cs`, which
drives idle, blink, talk and a run cycle.

The tool replaces the hand rig. It does not replace the person who looks at the result (§7).

## 1. Run it

Copy `AutoRig2D.cs`, `Rig2DLayout.cs` and `SpriteLibraryBuilder.cs` into one Editor folder. Copy
`RigDriver2D.cs` into a Runtime assembly that references `Unity.2D.Animation.Runtime`. The
Editor assembly also references `Unity.2D.Animation.Editor`, `Unity.2D.Psdimporter.Editor`,
`Unity.2D.Sprite.Editor` and that Runtime assembly.

- **In the Editor:** select one or more `.psb` files, then choose *Tools/Unity Dev/2D
  Animation/Auto-Rig Selected PSB*. It asks before it replaces bones it did not write.
- **In batch mode:**

```bash
Unity -batchmode -projectPath . -quit \
  -executeMethod UnityDev.Rig2D.AutoRig2D.RunFromCommandLine \
  -rig2dPsb Assets/Art/Courier/Courier_front.psb,Assets/Art/Courier/Courier_side.psb \
  -rig2dPpu 512 -rig2dReport Logs/autorig2d.json
# optional: -rig2dJson PATH|none   -rig2dView front|side   -rig2dFacing right|left   -rig2dOverwrite
```

Exit codes: 0 rigged; 2 a gate failed, or a hand rig was left alone; 1 usage error; 3 harness
error.

The report has one row per PSB:
- `source`: `rig.json` or `layers`.
- Counts: `bones`, `sprites`, `rigged`, `badWeights`, `skins`, `skinsReady`.
- Outputs: `library`, `variant`.
- `parts`: one line per layer, with its bones, vertices and triangles.
- `notes`: renames, replaced meshes, a kept variant.
- `problems`: empty when every gate holds.

It needs graphics: run it without `-nographics`. The layer alpha comes from the importer's
readable copy of the packed texture.

## 2. Layer names are the contract

Layer names are matched case-insensitively. The side suffix is `_L` / `_R` in a front view (the
character's own left and right, so `_R` is on screen left) or `_near` / `_far` in a side view.

| Layer | Bones it is weighted to |
|---|---|
| `torso` or `body` (required) | `hips` → `chest`; `hips` sits in the pelvis |
| `pelvis` | `hips` |
| `head` | `neck`, which runs from the neck to the top of head and hair |
| `eyes_*`, `eye_*`, `mouth_*`, `brow*`, `nose*`, `blush*` | `face`, a child of `neck` |
| `arm_X`, or `upperarm_X` + `forearm_X` | `shoulder_X` → `elbow_X`; the shoulder is the end nearer the neck |
| `hand_X` | `elbow_X`, `wrist_X` |
| `leg_X`, or `thigh_X` + `shin_X` | `hip_X` → `knee_X` |
| `foot_X` | `knee_X`, `ankle_X` |
| `hair*`, `bag*`, `tail*`, `scarf*`, `cape*`, `ponytail*`, `ribbon*` | its own `<layer>_pivot`, hung from the item's top: hair from `neck`, anything else from `hips`, `chest` or `neck` |
| anything else | the nearest bone, rigid |

**Bones are named after joints, never after a part.** The importer renames a bone that shares
a layer's name: bone `head` beside layer `head` becomes `head_1`. A clip, a driver or a script
that looks for `head` then finds nothing, and nothing reports an error.

A rig file that still uses part names (`head`, `hand_R`, `upperarm_R`, `thigh_R`, `foot_R`,
`hair`) is mapped to the joint names on read. Any other bone that clashes with a layer gets a
`_bone` suffix. Every rename is listed in `notes`.

**Swap states.** Two or more face layers named `<category>_<state>` form one category of the
Sprite Library: `eyes_open` / `eyes_closed`, `mouth_closed` / `mouth_open`, `eye_L_open`, and so
on. A side token (`L`, `R`, `near`, `far`, `front`, `back`, `upper`, `lower`) is never a state,
and body layers never swap: `bag_strap` and `bag_body` are two parts.

A splitter saves the non-default states hidden. The tool turns on the importer's *Include
Hidden Layers* (`m_ImportHiddenLayers`, which has no public property), so those states become
sprites.

## 3. Where the bones and meshes come from

**From a rig file** (`<name>.rig2d.json` or `rig2d.json` beside the PSB, or `-rig2dJson`):

- **Format:** `rig2d/1` from `comfyui-asset-generation` → `scripts/layer_split.py`. Bones are
  `{name, parent, hx, hy, tx, ty}` in image pixels with y down; the tool flips y. Each part is
  `{name, bones, verts, indices, bw}`, where `bw` is `i0, w0, i1, w1` per vertex.
- **`view` and `facing`** set the variant's driver.
- **Weights:** each vertex keeps its two largest weights, normalised to sum to 1.
- **Coverage gate:** a part's mesh must cover at least 99.95 % of the layer's solid pixels
  (alpha ≥ 50 %): the pixel's centre inside a triangle, with no slack. The mesh cuts off
  whatever it leaves out, and a thin wedge cut off an edge shows as a background sliver in
  every pose, so a mesh below that line is replaced by a grid mesh, with a note.
- **Pose gate:** the prefab is skinned on the CPU in the standard poses (front: rest, arm up,
  head turn, crouch, all three; side: rest and four phases of the run). At rest no solid layer
  pixel may be drawn by no triangle (0.05 % of the silhouette at most). Posed, the background
  cells a small closing fills inside the silhouette may grow by at most 0.2 % over rest, and a
  small disc round each elbow, wrist, hip, knee and ankle stays 97 % covered.

**From the layers** (no rig file, or `-rig2dJson none`):

- **Joints:** found from each layer's alpha. A limb's principal axis gives its two ends. The
  root joint is the end nearer the neck (arms) or the hips (legs), set in by half the limb's
  width. The far joint is set in from the other end. The middle joint is the centroid of the
  pixels halfway between, so a bent sleeve still gets its elbow on the sleeve.
- **Mesh:** a grid over the layer, keeping every cell that holds a visible pixel. A cell is
  about a twelfth of the square root of the opaque area, between 4 and 48 px, so a limb bends
  over several rows of vertices.
- **Weights:** two bones per vertex, w ∝ 1/(d² + r²)², where d is the distance to each bone's
  segment and r is a fifth of the part's shorter side. A weight under 2 % is dropped.

A rig file places joints better, because the splitter knows the landmarks: the narrowest
wrist, the kneecap, the armpit. The layer route rigs any PSB that follows the names, including
one an artist drew by hand.

## 4. How the providers are written

The writes go through `SpriteDataProviderFactories` → `GetSpriteEditorDataProviderFromObject`.
The PSD Importer implements the provider interfaces explicitly. The tables are in
`reference/psd-to-rig.md` §7.

| Provider | What is written | Space |
|---|---|---|
| `ICharacterDataProvider` | `CharacterData.bones`: the whole skeleton. `parts[i].bones`: the skeleton indices one layer uses | Document pixels, y up. A root bone is at its document position with its world angle; a child is local to its parent, with x along the parent bone |
| `ISpriteBoneDataProvider.SetBones` | That layer's subset, parents first | A bone whose parent is not in the subset becomes a root, placed against the layer's corner (`spritePosition`) |
| `ISpriteMeshDataProvider` | `SetVertices` (position and `BoneWeight`), `SetIndices`, `SetEdges` (the boundary edges) | Pixels from the layer's bottom-left corner, clamped to its size. Weight indices point into the subset |

Then the tool calls `Apply()` and `SaveAndReimport()`. The importer regenerates the prefab with
a `SpriteSkin` on each part.

Facts the tool depends on:

- **Edit the parts array the getter returned and pass that array back.** `SetCharacterData`
  stores parts in reverse order, and the getter matches them to sprites by id.
- **Bone GUIDs are a hash of the bone name.** A re-run over a repainted file keeps every
  binding. A bone with any other GUID marks a hand rig, and the tool will not replace it
  without `-rig2dOverwrite` or the dialog's *Replace*.
- **Take sprite ids from `GetSpriteRects()`.** `Sprite.GetSpriteID` cannot be reached from a
  user assembly.
- **`SpriteSkin.isValid` is internal.** `AutoRig2D.SkinState` rebuilds the same ladder from
  public data: sprite, bind poses, `rootBone`, `boneTransforms` length, no nulls.
- **Copy each native view at once.** `GetVertexAttribute`, `GetBindPoses` and `GetIndices`
  return views that are invalid after the next accessor call.

## 5. The library and the variant

- **The library:** `<name>_Faces.spriteLib`, written through `SpriteLibraryBuilder.Build`. It
  is rebuilt on every run and keeps its GUID.
- **The variant:** `<name>_Rig.prefab`, a Prefab Variant of the generated prefab. It is written
  only when it does not exist yet, so later runs keep a person's edits on it. Delete it to have
  it built again. It holds:
  - a `SpriteLibrary`;
  - a `SpriteResolver` on each category's default state (`open` for eyes, `closed` for the
    mouth), with Auto Rebind on;
  - the other states, disabled;
  - `RigDriver2D`, with its eye and mouth resolvers and spring bones filled in.
- **Every swap state shares the face bone**, so a resolver swap rebinds cleanly
  (`reference/sprite-library.md` §4).

## 6. RigDriver2D

Every pose is an offset from the bind pose that `Bind()` records. A bone the rig lacks is
skipped, so a sheet without hands still plays.

| Field | Does |
|---|---|
| `motion` | `Idle`: breath, sway. `Talk`: idle plus mouth swaps at 8 Hz and a nod. `Run`. `None`: leaves the bones to an Animator; blink, mouth and springs still run |
| `view`, `facesRight` | `Front`: the run in place, knees lifting outward. `Side`: the thighs swing about the hip, the knee folds most in mid-swing, the foot stays near level, each arm swings against its leg, the body leans and bobs. Facing flips the side view for art drawn facing −x. Flip the root, never a bone |
| `stride`, `breathPeriod`, `speed` | Seconds per run cycle (two steps), seconds per breath, time scale |
| `blink`, `blinkInterval` | A 0.12 s blink on a fixed, uneven rhythm |
| `mouthOpen` | Set 0..1 from a lip-sync source to override the talk pattern; −1 leaves it |
| `springs`, `springBones`, … | A 2D spring per `_pivot` bone: Verlet with stiffness and drag per 1/60 s converted per substep, a share of the pivot's motion carried without lag, a pull back to the animated pose, an angle clamp, and a reset on a teleport. These are the ideas behind `unity-rigged-character`'s SpringSolver, in 2D |

The driver writes bones in `Update`, before `SpriteSkin` deforms them. A capture or a test
disables the component and calls `Evaluate(t)` then `StepSprings(dt)` per frame. Frame a
run capture on the bounds of the whole cycle, sampled over one stride, not on the rest pose:
the swinging arms and legs reach half as far again as they do at rest, and a rest-framed
camera cuts them off.
`PoseArmUp`, `PoseHeadTurn` and `PoseCrouch` are the front view's extreme poses for judging
weights. For game states, drive `motion` from the controller, or bake clips from the driver and
hand them to the Animator (`unity-animation`).

## 7. What still needs a person, or the Skinning Editor

- **The look.** The gates prove that weights sum to 1, that every skin is Ready, and that a
  raised arm opens no hole. They cannot say that the shoulder reads well. Capture the extreme
  poses and show them.
- **A visible flaw** is fixed in the art or the split, not in the weights. A straight shoulder
  edge or a sleeve stub under a raised arm comes from the torso fill: `layer_split.py`'s
  `split.shoulder_notch` gate checks for it.
- **Finer weights** where a joint creases (shoulder, hip), an extra bone (fingers, a ponytail
  chain, a cape with several segments), or vertices along an outline: the Skinning Editor, on
  top of the generated rig. Bones you add there have their own GUIDs, so the next auto-rig
  refuses the file until you pass overwrite.
- **IK targets**: `reference/ik-2d.md`. **A shared skeleton** across files:
  `reference/psd-to-rig.md` §5.

## 8. Re-exports and renames

| The splitter or the artist… | Result |
|---|---|
| repaints layers under the same names (same `lyid`) | Sprite ids, bones, meshes and weights are kept. Re-run the tool anyway when the shapes moved, because the geometry is stored, not regenerated |
| renames a layer | **That part loses its rig.** It becomes a new sprite with no bones; `rigged` falls below `sprites` and `problems` names it. Re-run: it takes seconds. Going back to the old name does not bring the rig back |
| adds a layer | No bones until the re-run, which gives it bones by name |
| re-splits the art, so layer bounds and shapes change, and copies the new PSB over the old one | Delete the PSB's `.meta` first. An import over the old file's settings can keep its sprite rects and meshes: the rig comes out torn, and a layer can go missing. The report names a rig-file layer with no sprite |
| changes the side view to a front view | Use a separate PSB. The two views are separate characters |

The variant survives every re-run. A renamed swap state still needs its resolver fixed by hand,
or the variant deleted and rebuilt.

## Checks

- The report's `problems` is empty, and `rigged` equals `sprites`.
- The EditMode tests in `resources/Tests/Editor/AutoRig2DTests.cs` pass. They build their own
  PSB, so they need no art: every layer rigged, weights summing to 1, every skin Ready, the eye
  swap, a raised arm opening no hole and keeping the shoulder covered, the side run's legs in
  opposite phase, a spring that stays finite and in limits, rig-file bones renamed away from
  layer names, a rig-file layer with no sprite reported, the pose gate passing the rig and
  catching a mesh with triangles cut out, and the rig2d/1 reader.
- A still of rest, arm up, head turn and crouch, and one run cycle per view, looked at by a
  person.
