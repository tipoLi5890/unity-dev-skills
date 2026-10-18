# Asset classes: what each kind of model is made to

> Part of the `unity-3d-models` skill. Per class: where the pivot sits, the size it is made to,
> its collision, its LODs, its names and its prefab, in the courier run. The class key is the
> `class` column of `3D asset classes` and `3D budgets` — `reference/budgets.md`. Kit pieces
> (walls, floors and trims that snap to a grid) are not a class here: their corner pivot, grid and
> names are `unity-3d-level` → `reference/modular-kit.md`.

## The shape every class shares

```
Obstacle_LaneBarrier       root: scale (1,1,1); scripts, Rigidbody, triggers; the gameplay layer
├── Model                  the imported model: scaled, offset and rotated HERE
└── Collision              solid proxies on the World layer
```

- **The root is never scaled.** Scale, offset and rotation go on `Model`, and new art replaces
  the `Model` child — the swap is step 5 of `reference/import-and-decimate.md`; the shape and its
  reasons are `unity-3d-level` → `reference/prefab-architecture.md`.
- **`scale: real`** — 1 unit is 1 metre and the asset is made at its real size. A generated GLB
  arrives with its longest side ≈ 1 unit and its origin at the bounding-box centre, so its `Model`
  child is scaled and offset to that size once, on import. An FBX from Blender arrives at size
  with its transforms applied.
- **`pivot: base-centre`** — the root's origin is the centre of the footprint at ground level, so
  the asset stands on whatever it is placed on. For a character: between the feet, facing +Z.
- **No `MeshCollider` on a render mesh**, and the model's import keeps Generate Colliders off.
  Which proxy shape each piece gets, and the layer it sits on, is `unity-3d-level` →
  `reference/collision-proxies.md`.

## Per class

| Class | Courier example | Pivot | Collision | LODs | Prefab |
|---|---|---|---|---|---|
| pickup | A parcel token the runner collects in the lane | Base centre. A token that spins or bobs animates `Model`, offset so it turns about its own centre | One trigger on the root, on the `Trigger` layer; nothing solid | None: it is small on screen and gone in a second | `Pickup_ParcelToken` |
| obstacle | `LaneBarrier`, a stacked-crate block | Base centre | Box proxies on `Collision`, flush with the greybox block the art replaced | Two below LOD0, culled far down the lane | `Obstacle_LaneBarrier` |
| env-prop | A parcel cart, a bench, a sign beside the lane | Base centre | A proxy where the runner can reach it; none when it is out of reach, under 0.1 m across or above head height | Two, culled sooner than an obstacle | `EnvProp_ParcelCart` |
| hero-prop | The gate at the end of the lane, where the camera rests | Base centre | Proxies, as for an obstacle | Two, with LOD0 held to a smaller screen height | `HeroProp_DepotGate` |
| character | `Runner`, skinned to `RunnerRig`; a lane `Sentry` | Between the feet at ground level, facing +Z | A capsule on the root, sized from the character's height and shoulders | Two: sentries and other runners are seen down the lane. A player who never leaves the camera's distance can hold LOD0 with the group's culling set, but the levels still ship | `Character_Runner` |
| rigged-prop | `GateLatch`, with its own bones and its `GateLatchPop` clip | Base centre; a hinge is a bone, not the pivot | Proxies under the moving bone, a kinematic `Rigidbody` on the root | None | `RiggedProp_GateLatch` |

The default rows of `3D asset classes` carry these choices as short tokens: `base-centre`,
`real`, `trigger`, `proxy`, `proxy-or-none`, `capsule`, `proxy-on-bone`, a count for `lods` and
the prefab pattern. A project replaces a whole row, never a single cell.

- **A held prop** — the `Mallet` on `RunnerRig`'s right hand — travels in the character's FBX and
  is checked with the character. Imported on its own, it is a hero-prop with its pivot at the grip.
- **A collider under a bone** needs that bone in the imported hierarchy. With Optimize Game
  Objects on, list the bone under Extra Transforms to Expose, or the collider has nothing to
  follow.
- **The capsule, not the mesh.** A hitbox sized from a skinned mesh's renderer bounds can come
  out far wider than the body; size the capsule by hand — `unity-rigged-character`.

## Names and folders

- **One PascalCase name per asset, everywhere it appears:** `ArtDirection/raw/3d/LaneBarrier/`,
  `ArtDirection/sources/LaneBarrier.blend`, `Assets/Models/Obstacle/LaneBarrier/LaneBarrier.glb`,
  `Obstacle_LaneBarrier.prefab`.
- **The prefab is the class key in PascalCase, an underscore, the name.** The prefix keeps the
  wrapper apart from the model asset of the same name in every picker, and makes a class one
  search: `t:Prefab Obstacle_`.
- **Shipped files go in `Assets/Models/<Class>/<Name>/`**, `<Class>` being the key in PascalCase
  (`EnvProp`, `RiggedProp`): the model, its textures and its materials together. A class is then
  one folder tree to audit — `reference/model-audit.md`.
- **Clips beside their model:** `Runner.fbx`, `Runner@GateLatchSwing.fbx`. The importer rules in
  `unity-rigged-character` key on the part after `@`.
- **LOD names say who picks the level.** Levels chosen by distance end `_LOD0` … `_LODn`, and the
  FBX importer then **builds a LODGroup by itself** that culls by screen height; the hand-over
  heights are `unity-scene-optimisation` → `reference/lod.md`. Levels the game picks per quality
  tier (one level enabled, the others off) must **not** end `_LOD<n>`: the importer's LODGroup
  then culls the tier's level by screen size. A tree's LOD1 vanished on the low tier that way;
  name them `_L1`, `_L2`, and assert in a test that the imported prefab has no LODGroup.
- **Each level is decimated from level 0, never from the level above**, at
  `target_tris × lod_ratio`. A skinned class's levels are either made from the game mesh before
  rigging and skinned in the same pass (`blender-character-rig` → `reference/game-mesh.md`), or
  collapsed from skinned level 0 by a gated stage that re-limits and re-normalises the weights and
  measures each level against level 0 in posed frames (`blender-character-rig` →
  `reference/skinned-lod.md`); an ungated decimation of a rigged mesh carries broken weights.

## The look comes from the anchor

Image-to-3D inherits the look of the 2D image it was made from, so a mesh stays on-style with
`ART_DIRECTION.md` when its source image does. Make the source image in `codex-visual` against the
project's anchor, then bring it 3D; a class whose look drifts is fixed at the image, not in Unity.

## Licence and where it came from

Every model is recorded in the project ledger, `ArtDirection/assets.jsonl`, with its source —
generated, authored, purchased or third-party — and `class` set to the key above: skill
`art-asset-registry`. A purchased or third-party model also carries its licence
(`purchased:<pack>`, `cc0`), and its files are vendor files: kept outside git or under an ignored
path. The pack's licence decides whether its files may enter a repository at all; read it before
the first import, not after the first commit.

## Where each need is answered

| Need | Read |
|---|---|
| The numbers each class is held to, and how they are picked | `reference/budgets.md` |
| Import, decimate, wire the prefab | `reference/import-and-decimate.md` |
| Kit pieces: grid, corner pivot, kit names | `unity-3d-level` → `reference/modular-kit.md` |
| Proxy shapes and the layer scheme | `unity-3d-level` → `reference/collision-proxies.md` |
| Prefab, variant, nested; the `Model` child | `unity-3d-level` → `reference/prefab-architecture.md` |
| LOD groups and hand-over heights | `unity-scene-optimisation` → `reference/lod.md` |
| A character's import, Avatar and Animator | `unity-rigged-character` |
| Collider shapes under a scaled transform | `unity-physics-3d` |
| Recording the asset, its source and licence | `art-asset-registry` |
