# Skinned LOD — lighter levels on the same skeleton, built by a stage

> Part of the `blender-character-rig` skill. Runs as the `lod` stage of
> `reference/headless-pipeline.md`, after proof and before export. How Unity picks a level:
> `unity-3d-models` → `reference/asset-classes.md`; `unity-scene-optimisation` → `reference/lod.md`.

Each level is made **from level 0, never from the level above**, and stays skinned to the same
armature with the same bind pose, so one skeleton drives all of them. In a tennis game the body
went 17,910 → 6,000 → 3,000 triangles and the prop 1,491 → 600 → 300.

## Read level 0 first

Three faults in a generated level 0 stopped the decimation. Look for them before tuning ratios.

| Found | Effect | Fix used |
|---|---|---|
| **A hidden inner body:** a whole naked body under the clothes plus inner shoes, 5,727 faces, 32% of the mesh, invisible from any direction | collapse could not go below 3,422 triangles and grew spikes 0.86 to 1 m long below 3,500 | drop hidden shells first: an island goes only if **none** of its faces sees out along any of 256 ray directions, so a visible island is kept whole and no hole opens. Another body had only 198 such faces |
| **A prop in shards:** a GLB decimated unwelded came out as 333 pieces of 1 to 38 faces | collapse to 300 floored at 339 with 10 cm spikes; welding the source first floored at 1,758 | per level, voxel remesh (voxel 0.55% of the prop's length), drop pieces under 5% of the largest, then collapse; transfer UVs from level 0 by nearest face. The thin string bed became an open hoop, acceptable under a flat colour |
| **Custom normals far from the geometry:** p95 57° (median 8.7°) after prep's decimation interpolated the GLB's normals | a second interpolation by collapse made it p95 115° | clear custom normals on every level, use geometric smooth normals |

Level 0 itself was left as it was in that game (a person's call: fixing it changes the installed
character); the faults are worth fixing at the game-mesh stage (`reference/game-mesh.md`).

## Building one level

1. Copy level 0 (skinned), drop hidden shells.
2. Decimate (collapse, triangulate) to the target, retrying the ratio until within 1%.
3. **Weight vertices within 1 cm of the bounding box 0.5** in the decimate vertex group, so the
   silhouette's extremes (soles, fingertips, the top of the head) collapse last. **Not 0:** a
   weight of 0 locks those edges and grew an 88 cm spike on the lowest level.
4. Remove pairs of faces on the same three vertices (zero-thickness fins: 3 pairs on one level).
5. Re-apply the skin rule: at most 4 influences, drop weights under 0.01, normalise. The same
   Armature modifier and parent as level 0; same materials and UV layers (shared material).
6. Name levels `<id>_L1`, `<id>_L2`, **never `_LOD<n>`** when the game picks a level per quality
   tier: Unity's FBX importer turns `_LOD<n>` names into a LODGroup that culls by screen size,
   which is how a tree's LOD1 vanished on the low tier (`unity-3d-models` →
   `reference/asset-classes.md`).

## Gates (the limits that held)

| Gate | Limit | Measured (two bodies, L1 / L2) |
|---|---|---|
| triangles | target ± 5% | 5,999 / 2,993; prop 600 / 300 |
| influences, weight sum error, unweighted vertices | ≤ 4, < 1e-4, 0 | 4, 0, 0 |
| bounding box against level 0 | < 1 cm | body 0 / 0.79 cm; prop 0.36 / 0.38 cm |
| vertex distance to level 0's surface, at rest | ≤ 3 cm | 0.44 / 1.34 cm |
| the same over proof's 22 posed frames | ≤ 3 cm | 0.88 / 1.66 cm |
| same materials, UV layers, armature; prop on the same socket; no `_LOD<n>` name; same hashes when rebuilt | yes | yes |

**Look at it.** A sheet per contact frame: columns level 0, 1, 2; rows the whole body, the
prop hand, the feet. Level 1 was nearly indistinguishable; level 2 kept the silhouette, grip and
shoes with no spikes or tears, but smeared the texture (a striped shirt broke into patches), turned
hands into mittens and faceted the forearms. Whether that is enough is a person's call against the
quality target; better needs level 2's own UVs and a baked texture (no longer a shared material).

## What it costs and saves

- The character FBX grew 1.08 → 1.59 MB with two levels.
- **Vertices fall less than triangles.** A generated mesh had about 700 UV charts, so after Unity
  split the seams level 0 / 1 / 2 had 16,789 / 7,050 / 4,057 vertices: skinning at level 2 costs
  about 4× less, not 6×. Budget skinning by imported vertex count, not triangles.
