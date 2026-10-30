# Sharpness — the import settings, the reference resolution, the seam ladder

The depth behind `SKILL.md` §2, §3 and §5. Section numbers here match the router's.

## 2. The four import settings that decide sharpness

Bilinear filtering is the single most common cause of soft pixel art, and it is the import
default — not a setting anyone chose — so every untouched sprite is on `FilterMode.Bilinear`.

| Setting | Value | Why |
|---|---|---|
| `filterMode` | `FilterMode.Point` | Bilinear interpolates between texels; every edge in the art softens |
| `mipmapEnabled` | `false` | A mip chain hands the GPU a pre-blurred texture the moment scale drops below 1:1 |
| `textureCompression` | `Uncompressed` | Block compression invents colours that were never in the palette |
| `spritePixelsPerUnit` | one value, project-wide | Mixed PPU means two sprites disagree about the size of a pixel |

Two more that are not on the importer:

- `QualitySettings.antiAliasing = 0` and `anisotropicFiltering = Disable`, plus the URP asset's
  `msaaSampleCount = 1`: AA exists to soften edges. Read them rather than assume, since the values
  belong to the **active quality level** and another tier can differ.
- On the camera: `allowHDR`, `allowMSAA` and `allowDynamicResolution` all `false`.

> **A centre pivot on an odd-sized sprite lands on half a pixel.** A 15×15 sprite pivoted at
> `(0.5, 0.5)` anchors at 7.5 px, and the whole sprite renders half a pixel off the grid — which
> reads as "only this one sprite is blurry". Set `alignment = SpriteAlignment.Custom` and a pivot
> that resolves to a whole pixel, or author on even dimensions. Editing pivots and rects is
> `unity-2d-sprites`.

**Editor grid snapping**, so hand-placed objects land on pixels: grid size `1 / assetsPPU` on all
axes (PPU 16 → 0.0625, PPU 100 → 0.01), snapping enabled in the Grid and Snap overlay, and
*Align Selected → All Axes* to pull objects that are already off-grid back on.

Code: `resources/SpriteImportFix.cs` — survey and fix, one
texture at a time, with the reimport that makes it real.

## 3. Reference resolution, chosen once

Pick it before art production and do not move it: it sets the pixel size of every asset, and
changing it later is a re-draw.

| Reference resolution | 1920×1080 | 2560×1440 | 3840×2160 |
|---|---|---|---|
| 320 × 180 | 6× | 8× | 12× |
| 480 × 270 | 4× | 5.33× | 8× |
| 640 × 360 | 3× | 4× | 6× |

320×180 fits the three common targets at whole numbers, which is why it is the safe default.
A fractional factor is where pixel decimation comes from: at 5.33× some source pixels occupy 5
screen pixels and their neighbours 6, and the art looks unevenly ribbed. Screens with no integer
fit at all (1366×768 against 320×180 is 4.27×) are handled by giving up the extra pixels rather
than the grid — `cropFrame = Windowbox` — not by stretching.

`Camera.orthographicSize` follows from the choice: `(refResolutionY / 2f) / assetsPPU`. At
320×180 and PPU 16 that is `90 / 16 = 5.625`. The component's own `orthographicSize` is a
separate, read-only value; do not conflate the two.

## 5. Tilemap seams — work the ladder in order

Hairline gaps between tiles have six ordinary causes and one that only appears in motion. Work
top to bottom; the popular workarounds (a negative cell gap, PPU 31.99 for a 32 px tile) break the
moment the camera moves.

| # | Check | If it fails |
|---|---|---|
| 1 | Atlas: Tight Packing **off**, Padding **≥ 4**, packing actually enabled | Neighbouring tiles bleed into each other's edge texels |
| 2 | Mipmaps off on the tileset textures **and** on the atlas | A mip level is sampled and the tile edge fades |
| 3 | AA 0 in the active quality level, MSAA off on the camera | §2 above |
| 4 | Compression `Uncompressed` | Block artefacts land on the tile boundary |
| 5 | Every tile sprite has **even** pixel dimensions | Odd sizes put the grid on a half pixel — §2 above |
| 6 | `assetsPPU` equals the tile's pixel width (16×16 → 16) | A PPU mismatch is a real gap in world space, not a sampling one |
| 7 | Gaps appear **only while the camera moves**, everything above passing | This is the case pixel snapping exists for: set `gridSnapping = PixelSnapping` |

Rows 1 and 2 are atlas territory — `unity-sprite-atlas` owns packing, padding and packer mode;
authoring the tilemap is `unity-tilemap`.
