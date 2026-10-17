# Budget, and where the frames actually go

## Performance checklist (in priority order)

1. **Decimate the mesh** — the #1 fix: AI output arrives at a million triangles or more, and
   what the game can afford is the class's `target_tris` — `reference/budgets.md`. A mesh
   generated at its target with baked maps is regenerated lower instead —
   `reference/import-and-decimate.md` step 1. A mesh that will be skinned is brought to its
   target **before rigging**, never after.
2. **Shrink textures** — Max Size = the class's `target_tex_px`, compression on.
3. **Reduce pool sizes** — pooled objects multiply cost; drop counts that
   over-provision (e.g. spawner's `coinPoolSize`/`obstaclePoolSize`).
4. **Batching** — under URP the SRP Batcher already takes these renderers, so ticking GPU
   Instancing on a URP Lit material changes nothing. Keep props on shared materials, never
   `renderer.material` or a `MaterialPropertyBlock` per object, and read the path in the Frame
   Debugger; for many identical props turn on the GPU Resident Drawer —
   `unity-scene-optimisation` → `reference/batching.md`.
5. **LOD groups** — lower detail at distance — `unity-scene-optimisation` → `reference/lod.md`.
- Draco/meshopt compression shrinks the *file*, not runtime cost — skip it for
  frame-rate problems.

## Notes

- **Orientation/scale:** glTF is Y-up (matches Unity). Models may still need a
  rotation/scale tweak on the `Model` child. Spawners that measure a
  `MeshFilter`'s bounds auto-normalize size. A GLB from the ComfyUI templates always
  needs it: largest extent ≈ 1 unit, origin at the bounding-box centre —
  `reference/import-and-decimate.md`.
- **Colliders:** keep simple primitives — a trigger on the root, solids on a `Collision`
  child, per class in `reference/asset-classes.md`; never add a MeshCollider to a dense model.
- **Characters:** an Editor-side Humanoid Avatar comes from an FBX — glTFast does not go
  through Unity's Model Importer and has no Rig tab — so a character goes to
  `unity-rigged-character`, or `blender-character-rig` when the rig is built in Blender. Bring
  the mesh to the character class's `target_tris` (`reference/budgets.md`) **before** rigging —
  `blender-character-rig` → `reference/game-mesh.md`: decimating a rigged mesh breaks its skin
  weights and UVs, and the rig is then built again.
