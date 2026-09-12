# Preparing the mesh for auto-rigging

Decimate first, then clean. Both before Mixamo ever sees the file.

## 5. Decimate BEFORE rigging

AI characters routinely arrive at **~47k vertices / ~94k triangles** — an order of
magnitude over a mobile hero budget (**3–10k tris**, see `unity-3d-models`) — and a
raw image-to-3D mesh can be denser again, past 1M triangles. Inspect the file in hand.
**Decimating a rigged mesh destroys its skin weights**, so it must happen first. Discover
the cost after rigging and the only route is decimate, then run Mixamo again.

## 6. Clean the mesh for Mixamo — `fbx2mixamo.py`

**Symptom: the Mixamo upload progress bar stops mid-way and never errors.** The upload
succeeded; the server-side parse is stuck. Three causes, all handled by the script:

1. **Stray disconnected shells.** A thin sliver unconnected to the body — typically a
   "ground spike" spanning the whole scene depth — can inflate the bounding box from a
   normal 36 to 91.7. The auto-rigger infers skeleton placement from the bounding box,
   so a skewed box means it never finds a humanoid.
2. **Wrong axes.** Geometry authored Z-up (Blender-native) while the FBX header declares
   Y-up: anything trusting the header sees a character lying down. The error isn't even
   consistent — one export can carry its arm-span on X, the next on Y. So
   **infer axes from the body's own extents** (height > arm-span > depth, facing from the
   toes) instead of hardcoding a conversion matrix.
3. **Embedded PBR textures.** Four 2048²/4096² maps can be 90%+ of the file and are
   worthless to the auto-rigger.

**Symptom: Mixamo rejects the file — it already has a skeleton.** Detect a pre-existing
rig by scanning the **raw bytes** for `LimbNode` / `Deformer` / `Cluster`. Skeleton nodes
carry no array properties, so a parser inspecting only decoded arrays reports "no rig" and
sends you into an upload that was never going to work.

```bash
python3 scripts/fbx2mixamo.py <character>.fbx <character>_mixamo.obj --height=170
```

Output: T-pose, Y-up, feet on the origin, scaled to `--height` units, UVs preserved, no
textures. `--keep-spike` disables stray-shell removal. **Check the printed ratios before
uploading:** arm-span/height **0.8–1.0**, depth/height **0.2–0.3**. A depth/height near
0.54 means stray geometry is still polluting the bounding box — re-clean, don't upload.
The ASCII front/side views printed at the end should read as a T-pose.
