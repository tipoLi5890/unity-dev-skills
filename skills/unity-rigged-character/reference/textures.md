# Reattaching PBR maps

## 10. Reattach textures — `fbx_textures.py`

**Mixamo returns geometry + skeleton + UVs and no materials**, and you deliberately
stripped the maps before uploading (§6). Reattachment is structural, not optional.
**Symptom: the character imports as a featureless white mannequin.** The UVs survive the
round trip untouched, so the maps land exactly right.

- **Extract from the ORIGINAL pre-Mixamo export**, never from the rigged FBX.
  `fbx_textures.py` reads each image's `RelativeFilename` from the FBX `Video` node, so
  maps come out under their authored names instead of `tex0..tex3` in storage order —
  guessing normal-vs-roughness from file size is a coin flip.
  ```bash
  python3 scripts/fbx_textures.py <original>.fbx <outdir>
  ```
- **Confirm the pairing by vertex count.** With several candidate models generated, the
  rigged FBX's vertex count matches exactly one original. **Their UVs are completely
  different; the wrong one smears the whole texture.**

### The roughness ≠ smoothness trap

**Symptom: the character looks like uniform plastic.** URP Lit's **Metallic Gloss Map is
one slot carrying two datasets — RGB = metallic, Alpha = smoothness**. AI exports hand you
*separate* Metallic and Roughness JPEGs, and **`smoothness = 1 − roughness`**. **JPEG has
no alpha channel at all**, so dropping Metallic.jpg into the slot leaves Unity with no
smoothness data. Composite a PNG:

```bash
ffmpeg -i Metallic.jpg -i Roughness.jpg -filter_complex \
  "[0:v]format=rgb24[m];[1:v]format=gray,negate[sm];[m][sm]alphamerge,format=rgba" out.png
```

`extractplanes=r` **fails on JPEG** — decoded JPEG is YUV and has no R plane; convert with
`format=rgb24` first, or `format=gray` for greyscale sources.

Verify with **`signalstats`, never with `scale=1:1`**. Scaling to one pixel looks like an
easy way to read a mean, but it is not an arithmetic one — it can report alpha 33 on a map whose
true mean is 44, which reads as a broken conversion and sends you debugging a correct filter
chain:

```bash
avg() { ffmpeg -i "$1" -vf "$2,signalstats,metadata=print:key=lavfi.signalstats.YAVG" \
        -f null - 2>&1 | grep -o "YAVG=[0-9.]*" | tail -1; }
avg out.png "alphaextract"                  # must equal 255 − roughness mean
avg out.png "format=rgb24,extractplanes=r"  # must equal metallic mean
```

**If the source was GLB, the packing is different** — and using the FBX recipe on it produces
a plausible-looking but wrong material. glTF ships **one** `metallicRoughnessTexture` with the
channels packed **G = roughness, B = metallic** (R is occlusion when present). So the repack
reads two channels out of a single image rather than combining two files:

```bash
# glTF ORM  ->  URP Metallic Gloss Map:  RGB <- B (metallic),  A <- 255 - G (smoothness)
ffmpeg -i metallicRoughness.jpg -filter_complex \
  "[0:v]format=rgb24,split[x][y];\
   [x]extractplanes=b,format=gray,format=rgb24[metal];\
   [y]extractplanes=g,negate[smooth];\
   [metal][smooth]alphamerge,format=rgba" MetallicSmoothness.png
```

**A 4096² mask PNG can be 9 MB while the game only samples 512.** Downscale to 1024 (still
2× headroom) before committing; full resolution is always re-extractable from the original.

| Map | Import handling |
|---|---|
| Color / BaseColor | sRGB (default) |
| Normal | **`TextureImporterType.NormalMap`** — leave it Default and surface normals point entirely wrong |
| Composited Metallic+Smoothness | **sRGB OFF (linear)**, alpha preserved — as sRGB the raw values get gamma-warped |

**The URP shader keyword is the most hidden step.** `SetTexture` alone does nothing: URP
compiles the normal-map and metallic-map paths behind **`_NORMALMAP`** and
**`_METALLICSPECGLOSSMAP`**. Without enabling the keyword the texture **loads, occupies
memory, and is silently ignored** — and you debug the texture while the shader never asked
for it. With a mask bound, `_Metallic` comes straight from the map's RGB and `_Smoothness`
is a **multiplier** (`1.0` = "use the map as authored"). With no mask, cloth and skin want
metallic `0`, smoothness ~`0.25`; higher reads as wet vinyl. **`_BaseColor` must be white**
— the tint multiplies the map, so anything else just darkens it.

---
