# Reattaching PBR maps

Applies to every route that brings the character in as FBX. **Symptom: the character imports as a
featureless white mannequin**, or as uniform plastic. The UVs survive the trip untouched, so maps
reattached from the source land exactly right.

## What the FBX carries, and what Unity binds

| Carrier | In the file | Bound on Unity's imported material |
|---|---|---|
| Mixamo download | geometry, skeleton, UVs; no materials (the maps were stripped before upload, `reference/mixamo-route.md`) | nothing: white mannequin |
| FBX from Blender's exporter | base colour, normal, metallic (as the FBX property `ReflectionFactor`) and roughness (`ShininessExponent`) | base colour (`_MainTex` / `_BaseMap`) and normal (`_BumpMap`) only. `_MetallicGlossMap` stays empty, `_Metallic` 0, smoothness 0.5: plastic |
| GLB through glTFast | one packed `metallicRoughness` texture beside base colour and normal (Blender packs the two maps into it) | glTFast imports the packed texture, named after both source maps, with its own material: check its slots the same way |

The Blender row holds on the Built-in pipeline and on URP Lit, with external or embedded textures:
the maps are in the file (a Blender re-import links them again) and Unity's FBX material mapping
drops them. So on an FBX from Blender's exporter or from Mixamo the metallic/smoothness map is
built by hand (below), imported linear, and bound with the `_METALLICSPECGLOSSMAP` keyword. Any
other carrier (an auto-rig service, another DCC's exporter, whose material may be bound by one of
Unity's material-description importers) is decided by the check below.

Check on each new character before rebuilding anything:

1. Import the FBX and select its material (Materials tab → **Extract Materials** if needed).
2. Read which slots are filled: base colour, normal, Metallic Gloss Map.
3. Compare with the maps the source had (the `.blend`, the GLB, the service's download). Every
   map the material does not bind is rebuilt from the source below.

An FBX with embedded textures: Unity does not necessarily extract them. It may resolve the
material's textures by file name to same-named images elsewhere in the project, so a stale map from
another character can bind silently. Extract the maps yourself (`scripts/fbx_textures.py`), with
names no other character uses, as below.

**Source maps go to a staging folder outside the character folder** (outside `Assets/`, or beside
the `.blend`). Build the `<Name>_MetallicSmoothness.png` composite there, then copy into the
character folder only `<Name>_BaseColor`, `<Name>_Normal` and `<Name>_MetallicSmoothness`. A raw
`<Name>_Metallic` or `<Name>_Roughness` in the character folder has no smoothness alpha, and
`MixamoTextures.cs` never binds it.

## Getting the maps out of the source

From the Blender route or an auto-rig service, the maps are the source's own files, copied to the
staging folder: the `.blend`'s images (`Runner_BaseColor.png`, `Runner_Metallic.png`,
`Runner_Roughness.png`, `Runner_Normal.png`), the service's download, or `scripts/fbx_textures.py`
on the exported FBX. On the Mixamo route they exist only inside the file you uploaded:

- **Extract from the ORIGINAL export**, never from the rigged FBX.
  `scripts/fbx_textures.py` reads each image's `RelativeFilename` from the FBX `Video` node, so maps
  come out under their authored names instead of `tex0..tex3` in storage order — guessing
  normal-vs-roughness from file size is a coin flip.
  ```bash
  python3 scripts/fbx_textures.py <original>.fbx <staging-dir>
  ```
  From a GLB: `scripts/glb2mixamo.py <in>.glb --textures=<staging-dir>`.
- **Confirm the pairing by vertex count.** With several candidate models generated, the rigged
  FBX's vertex count matches exactly one original. **Their UVs are completely different; the
  wrong one smears the whole texture.**

## The roughness ≠ smoothness trap

**Symptom: the character looks like uniform plastic.** URP Lit's **Metallic Gloss Map is one slot
carrying two datasets — RGB = metallic, Alpha = smoothness**. Exports hand you *separate*
Metallic and Roughness images, and **`smoothness = 1 − roughness`**. **JPEG has no alpha channel
at all**, so dropping Metallic.jpg into the slot leaves Unity with no smoothness data. Composite a
PNG:

```bash
ffmpeg -i Metallic.jpg -i Roughness.jpg -filter_complex \
  "[0:v]format=rgb24[m];[1:v]format=gray,negate[sm];[m][sm]alphamerge,format=rgba" out.png
```

`extractplanes=r` **fails on JPEG** — decoded JPEG is YUV and has no R plane; convert with
`format=rgb24` first, or `format=gray` for greyscale sources.

Verify with **`signalstats`, never with `scale=1:1`**. Scaling to one pixel looks like an easy way
to read a mean, but it is not an arithmetic one — it can report a value well off the true mean,
which reads as a broken conversion and sends you debugging a correct filter chain:

```bash
avg() { ffmpeg -i "$1" -vf "$2,signalstats,metadata=print:key=lavfi.signalstats.YAVG" \
        -f null - 2>&1 | grep -o "YAVG=[0-9.]*" | tail -1; }
avg out.png "alphaextract"                  # must equal 255 − roughness mean
avg out.png "format=rgb24,extractplanes=r"  # must equal metallic mean
```

**If the source was GLB, the packing is different** — and the two-file recipe on it produces a
plausible-looking but wrong material. glTF ships **one** `metallicRoughnessTexture` with the
channels packed **G = roughness, B = metallic** (R is occlusion when present). So the repack reads
two channels out of a single image rather than combining two files:

```bash
# glTF ORM  ->  URP Metallic Gloss Map:  RGB <- B (metallic),  A <- 255 - G (smoothness)
ffmpeg -i metallicRoughness.jpg -filter_complex \
  "[0:v]format=rgb24,split[x][y];\
   [x]extractplanes=b,format=gray,format=rgb24[metal];\
   [y]extractplanes=g,negate[smooth];\
   [metal][smooth]alphamerge,format=rgba" MetallicSmoothness.png
```

## Import settings and the material

**Max Size** is the project's call, not a constant: the importer script leaves it at the
importer's own value (2048 on a fresh importer) unless `character-pipeline.json` sets
`maxTextureSize`, or `targetTexPx` from the `character` row of the 3D budgets table
(`unity-3d-models` → `reference/budgets.md`). Commit the source at full resolution; the importer
downsizes on import, and the original stays re-extractable.

| Map | Import handling |
|---|---|
| Color / BaseColor | sRGB (default) |
| Normal | **`TextureImporterType.NormalMap`** — leave it Default and surface normals point entirely wrong |
| Composited Metallic+Smoothness | **sRGB OFF (linear)**, alpha preserved — as sRGB the raw values get gamma-warped |

**The URP shader keyword is the most hidden step.** `SetTexture` alone does nothing: URP compiles
the normal-map and metallic-map paths behind **`_NORMALMAP`** and **`_METALLICSPECGLOSSMAP`**.
Without enabling the keyword the texture **loads, occupies memory, and is silently ignored** — and
you debug the texture while the shader never asked for it. With a mask bound, `_Metallic` comes
straight from the map's RGB and `_Smoothness` is a **multiplier** (`1.0` = "use the map as
authored"). With no mask, cloth and skin want metallic `0`, smoothness ~`0.25`; higher reads as
wet vinyl. **`_BaseColor` must be white** — the tint multiplies the map, so anything else just
darkens it.

`CharacterImportSettings.cs` sets the three import types by file name. `MixamoTextures.cs` builds
the URP Lit material with the keywords on any FBX route, Mixamo or not (it needs URP and returns an
error without it). It binds only a texture whose name contains `metallicsmoothness`: name the
composite `<Name>_MetallicSmoothness.png`. Without one the material gets no mask (metallic 0,
smoothness 0.25) and the JSON carries a `note` naming any raw metallic map it skipped
(`reference/editor-scripts.md`).
