# Budget, and where the frames actually go

## Performance checklist (in priority order)

1. **Decimate the mesh** — the #1 fix (1M → ~3k tris = ~300× fewer triangles).
2. **Shrink textures** — Max Size 512 (or 256) + compression.
3. **Reduce pool sizes** — pooled objects multiply cost; drop counts that
   over-provision (e.g. spawner's `coinPoolSize`/`obstaclePoolSize`).
4. **GPU Instancing** — enable on the material so identical meshes batch.
5. **LOD groups** — lower detail at distance (advanced).
- Draco/meshopt compression shrinks the *file*, not runtime cost — skip it for
  frame-rate problems.

## Notes

- **Orientation/scale:** glTF is Y-up (matches Unity). Models may still need a
  rotation/scale tweak on the `Model` child. Spawners that measure a
  `MeshFilter`'s bounds auto-normalize size.
- **Colliders:** keep a simple primitive collider on the root; never add a
  MeshCollider to a dense model.
- **Characters:** anything that needs a skeleton, retargeted animation, or an
  AvatarMask goes through `unity-rigged-character` (FBX + Mixamo). Decimate
  there too — but **before** rigging, since decimating a rigged mesh destroys
  its skin weights.
- **Style consistency:** image-to-3D inherits the look of the 2D anchor it came
  from, so it stays on-style with `ART_DIRECTION.md` (see the `codex-visual`
  skill). Generate the source sprite there, then bring it 3D here.
