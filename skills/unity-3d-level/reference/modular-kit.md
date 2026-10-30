# Modular kit — pieces that meet on a grid

> Part of the `unity-3d-level` skill. The rules that make kit pieces snap together without
> gaps: the grid, where the pivot sits, where a wall's thickness goes, snap settings, names, the
> Blender export that keeps all of it true through the FBX, and the audit that finds the piece
> that broke the rule. Worked setting: the **depot** kit that replaces the gate-room greybox.

A kit is a contract, not a set of models. Two pieces made a month apart by different hands meet
without a seam because both obey the same four numbers. One piece that is 2.03 wide breaks
every room it is used in, and nobody sees it until the lightmap shows the crack.

## 1. The grid — 1, 2 and 4 metres

| Module | Used for | Why |
|---|---|---|
| 4 m | Floors, ceilings, big wall runs, room footprints | Fewest pieces per room; fewest seams |
| 2 m | Walls, door walls, windows, corridor bays | A 1.2 door with 0.4 of wall either side is exactly 2 |
| 1 m | Trims, half walls, pillars, stairs | The smallest thing that still has to line up |
| Height step 1 m | Wall heights: 3 or 4 | A 3 m wall holds the 2.2 door and the ceiling a full jump needs |

Powers of two, because every piece can then be replaced by two of the next size down, and any
two pieces share a line every 4 metres. A 2.5 or 3 m module shares a line with a 2 m one only
every 10 or 6 metres; mixed kits built that way never close a loop.

**The sheet's numbers are minima; the kit rounds them up to the grid.** The 2.4 corridor of
`reference/greybox.md` becomes a 4 m bay, which is 3.8 clear between walls 0.2 thick. A 2 m bay
is 1.8 clear: wide enough for the body (`2·W` = 1.6), too narrow for the sheet. Decide per row
which way it rounds, and write the kit value back into the sheet.

## 2. The pivot — a floor corner on the grid

Every piece has its pivot at the **minimum corner of its footprint, at walking level**:

```
          +Z
          │  ┌──────────┐
          │  │  piece   │        pivot = (0, 0, 0)
          │  │          │        the piece occupies x ≥ 0, z ≥ 0, y ≥ 0
          ●──┴──────────┘── +X
        pivot
```

- A piece placed at `(4, 0, 6)` with rotation `(0, 90·n, 0)` is on the grid. No offsets, no
  half units, no arithmetic in the level designer's head.
- **A floor slab is the exception on Y:** its *top* face is at 0 and its thickness hangs below,
  so walls and floors share one walking level.
- Rotation happens about the corner. A 2 m wall rotated 90° still starts at a grid point.
- A centre pivot is right for a prop and wrong for a kit piece: a 2 m wall with a centre pivot
  sits at x = 1, 3, 5, and the first 4 m piece beside it sits at 2, 6, 10.

## 3. Wall thickness — centred on the grid line

A wall is 0.2 thick and **straddles** the grid line: 0.1 either side. A wall piece therefore
occupies `x` 0…2, `y` 0…3, `z` −0.1…+0.1, with its pivot still on the line.

| Choice | Result |
|---|---|
| Centred on the line (this kit) | Two rooms share one wall; a wall serves both sides; clear width is the bay minus 0.2 |
| Inside face on the line | Clear width is the full bay, and two rooms back to back have a double wall with a void between |
| Outside face on the line | Corners need a special piece on every outside turn |

Corners follow from the choice: with centred walls an L of two wall pieces leaves a 0.1 × 0.1
notch outside and overlaps 0.1 × 0.1 inside. Ship one 0.2 × 0.2 pillar piece (pivot at its
centre line crossing, the one piece measured from −0.1) and place it on every corner.

## 4. Snapping

```csharp
// Editor: one grid for the whole kit. Hold V to drag by a vertex when a piece must meet another.
EditorSnapSettings.gridSize = Vector3.one * 2f;     // the scene grid
EditorSnapSettings.move = Vector3.one * 2f;         // increment snap, with the modifier held
EditorSnapSettings.rotate = 90f;
EditorSnapSettings.gridSnapEnabled = true;          // snaps to the grid while the handle is in Global
```

Grid snapping acts only with the move handle in **Global** orientation. A piece that was
already off the grid stays off by the same amount under increment snap. Put it back from code —
`t.position = Snapping.Snap(t.position, Vector3.one * 2f, SnapAxis.All);` — after finding the offenders (§7).

Never scale a kit piece to close a gap. The gap is a piece that is off the grid or the wrong
size; scaling hides it in this room and moves it to the next.

## 5. Names

`Kit_<Set>_<Type>_<Width>x<Height>[_<Variant>]` — sizes in metres, so the name states the
contract:

```
Kit_Depot_Floor_4x4          Kit_Depot_Wall_2x3           Kit_Depot_WallDoor_2x3
Kit_Depot_Wall_4x3           Kit_Depot_WallWindow_2x3     Kit_Depot_Pillar_0.2x3
Kit_Depot_Stairs_2x3         Kit_Depot_Ramp_2x1           Kit_Depot_Wall_2x3_Damaged
```

Mesh, prefab and collision child share the stem. Props are not `Kit_`: they have centre or base
pivots and no grid, and they live in a different folder so the audit is not run on them.

## 6. The Blender side, in brief

1. **Scene units metric, unit scale 1.** One Blender unit is one metre is one Unity unit.
2. **Model on Blender's grid** with snapping to increments; set the grid subdivisions so 0.1
   is a line.
3. **Put the origin on the corner**, at walking level: 3D cursor to the corner vertex, then
   Object ▸ Set Origin ▸ Origin to 3D Cursor.
4. **Apply transforms** — Object ▸ Apply ▸ All Transforms — so rotation is 0 and scale is 1
   in the file. An unapplied scale arrives in Unity as a scaled root, and every collider under
   it inherits that.
5. **One material per surface type**, not per piece: `Depot_Concrete`, `Depot_Metal`,
   `Depot_Trim`. Every piece that shares a material can share a batch.
6. **Export one piece per FBX**, selected objects only:

```python
bpy.ops.export_scene.fbx(
    filepath=path, use_selection=True, object_types={'MESH'},
    axis_forward='-Z', axis_up='Y',            # Unity's axes
    apply_scale_options='FBX_SCALE_UNITS',     # scale 1 on the imported root, not 100
    bake_space_transform=True,                 # no −90° X rotation left on the root
    use_mesh_modifiers=True, mesh_smooth_type='FACE', bake_anim=False)
```

Blender is right-handed and Unity left-handed, so one horizontal axis arrives mirrored and the
footprint can land on the negative side of the pivot. Do not reason about which: export **one**
piece, run the audit (§7) and read `pivotOffset`. A negative X or Z there is the axis that came
out mirrored — model the footprint towards the opposite side of the origin on that axis, export
again until `pivotOffset` is `[0,0,0]`, and only then model the other thirty. If the imported
root shows a rotation of −90 on X, turn on **Bake Axis Conversion** in the model's import
settings (`ModelImporter.bakeAxisConversion`).

Decimation, texture size and the import settings themselves are `unity-3d-models` →
`reference/import-and-decimate.md`; a character or anything with an armature is
`blender-character-rig`.

## 7. The audit

`resources/Editor/KitAudit.cs` reads every prefab in a folder and prints one JSON object. It
measures the render meshes in the prefab root's own space, so it works on assets that are not
in a scene and writes nothing.

```csharp
string json = KitAudit.Audit("Assets/Kit/Depot");                  // grid 2, wall 0.2, height step 1
string json4 = KitAudit.Audit("Assets/Kit/Depot", 4f, 0.2f, 1f);   // a 4 m kit
```

Headless, with `"ok"` as the exit code (0 pass, 2 flagged): `-executeMethod UnityDev.Cli.BatchAudit.Run
-audit KitAudit -folder Assets/Kit/Depot -grid 2 -out Logs/kit.json` (`unity-cli` →
`reference/batch-audit.md`).

| `check` | Rule | Fix |
|---|---|---|
| `off-grid-size` | Footprint X and Z are each a multiple of the grid, or exactly the wall thickness | Re-model to size; never scale the prefab |
| `off-grid-height` | Height is a multiple of the height step (floor slabs exempt) | Re-model |
| `pivot-off-corner` | `bounds.min` is `(0, 0, 0)`; −0.1 allowed on the axis a wall is centred across; `max.y` = 0 for a slab | Move the origin in Blender and re-export. `pivotOffset` is how far, in metres |
| `root-scaled` | The prefab root's scale is `(1, 1, 1)` | Apply transforms before export |
| `non-uniform-scale` | No transform inside the prefab is scaled unevenly | Apply transforms; a sphere or capsule collider under it is the wrong shape — `unity-physics-3d` §5 |
| `missing-collider` | A piece with render meshes has a collider somewhere | `reference/collision-proxies.md` |
| `dense-mesh-collider` | No `MeshCollider` over 500 triangles | Replace with a proxy |

`"ok": true` is the kit holding its contract. Run it when a piece is added and before a level
is built from the kit; a 1.8 m bay cannot be audited back into existence afterwards. With the
default grid of 2, a correct 1 m trim piece is reported — audit the trims folder with `grid` 1.

## Traps

- **Pivot at the mesh centre "because Unity's handle shows there".** The handle shows the
  centre when the tool handle position is set to Center; switch it to Pivot before judging.
- **A 4 m floor textured so it only tiles with itself.** Texture to world scale, one texel
  density for the whole kit, so a 2 m and a 4 m piece meet without a visible seam.
- **Kit pieces with their own lights, particles or scripts.** A kit piece is geometry and
  collision. Gameplay goes on a prefab that contains it — `reference/prefab-architecture.md`.
- **Fixing a bad pivot by moving or scaling the prefab root.** The root is the pivot. When the
  FBX cannot be re-exported, offset the `Model` child under an unscaled root instead — the audit
  measures from the root, and `unity-3d-models` wires props the same way.
- **One FBX holding the whole kit.** Re-exporting one piece reimports thirty and resets their
  import settings together.

## Where each need is answered

| Need | Answer |
|---|---|
| The numbers the kit rounds up from | `reference/greybox.md` |
| Kit prefabs, variants, nesting rooms from pieces | `reference/prefab-architecture.md` |
| Collision children and the layer they sit on | `reference/collision-proxies.md` |
| Importing a model, decimation, triangle budgets | `unity-3d-models` → `reference/import-and-decimate.md` |
| Rigging and exporting a character from Blender | `blender-character-rig`, its FBX export reference |
| Static batching and instancing of repeated pieces | `unity-scene-optimisation` → `reference/batching.md` |
| LOD groups on kit pieces | `unity-scene-optimisation` → `reference/lod.md` |
| Lightmap UVs and baking a room built from pieces | `unity-lighting` → `reference/bake-setup.md` |
| Finding every use of one kit prefab | `unity-search` → `reference/query-patterns.md` |
