# Parallax layers — a generated scene as an endless parallax rig

> Part of the `unity-2d-rendering` skill. A scene picture split into depth layers becomes one
> prefab: a child per layer with `ParallaxLayer` (how fast it follows the camera) and
> `ParallaxTiles` (what keeps the view covered, endlessly). Timing, factors and `Snap()` are
> `reference/parallax.md`; this page is the layers, the tiling and the builder.

## From picture to rig

1. **Split the scene.** `comfyui-asset-generation` → `scripts/scene_layers.py run` splits a scene
   by depth with Qwen-Image-Layered and gates the result. It writes canvas-sized `<name>.png`
   layers, `scene.json` (back to front), `scene.psd`, and `props/` (each prop of the front layer
   with its box). `--names sky,skyline,shops,road,props` names the layers after the band split
   (sky above, road below a transparent band) and the ground cut (shopfronts off the road).
2. **Give every layer a scroll speed**: `scene_layers.py --scroll sky=0.04,road=1,…` writes it
   into `scene.json`, or pass `-scroll` to the builder. Depth order is not enough: the sky and
   the road come out of one model layer, and only you know which layer is the play line.
3. **Build the rig** — `resources/Editor/ParallaxRigBuilder.cs`:

```bash
Unity -batchmode -projectPath P -executeMethod UnityDev.Rendering2D.ParallaxRigBuilder.BuildFromCommandLine \
  -sceneJson /path/street/scene.json -scroll sky=0.04,skyline=0.15,shops=0.45,road=1,props=1.35 \
  -out Assets/Level/Street -groundPx 470 [-ppu 100] [-pixelSnap] [-psd /path/street/scene.psd]
```

It prints `parallax-rig: {report}` (per layer: tiling, variants, factors, order, tile files) and
exits 0 built, 2 refused with the reason, 1 usage error. Interactive: Tools → Unity Dev →
2D Rendering → Build Parallax Rig From Scene JSON… (default options: every layer needs `scroll`
in the JSON), or `ParallaxRigBuilder.Build(json, outFolder, options)`.

Output: `<out>/<name>.prefab` and `<out>/<name>_tiles/*.png`. Rebuilding overwrites both in
place: the prefab keeps its GUID, so scenes that use it keep working, and tiles of props that
are gone are deleted.

## What the builder reads

`scene.json` as `scene_layers.py` writes it, plus the keys only the rig needs:

```json
{"tool": "scene_layers", "width": 1024, "height": 576, "order": "back_to_front",
 "pixels_per_unit": 100, "ground_px": 470,
 "layers": [
  {"name": "sky",     "png": "sky.png",     "role": "strip", "tile": true,  "scroll": 0.04},
  {"name": "road",    "png": "road.png",    "role": "strip", "tile": true,  "scroll": 1},
  {"name": "skyline", "png": "skyline.png", "role": "strip", "tile": true,  "scroll": 0.15},
  {"name": "shops",   "png": "shops.png",   "role": "strip", "tile": true,  "scroll": 0.45},
  {"name": "props",   "png": "props.png",   "role": "props", "tile": false, "scroll": 1.35,
   "gap": [200, 600]}]}
```

| Key | Meaning | Default |
|---|---|---|
| `width`, `height` | The canvas in pixels; every PNG is this size | required |
| `layers[]` | Back to front; its index is the draw order | required |
| `scroll` | Speed against the world: `1` the play line, `0` fixed to the camera, above `1` passes in front. `-scroll name=S` wins | required |
| `scroll_y` | The same, vertically | `1`: no vertical parallax |
| `tiling` | `repeat`, `mirror`, `shuffle` or `auto` | `auto` (below) |
| `gap` | `[least, most]` empty pixels between shuffled props | `[0.25, 1] × width` |
| `pixels_per_unit` | World size of the canvas; `-ppu` wins | `100` |
| `ground_px` | The canvas row (from the top) put on world y = 0, where the runner's feet go; `-groundPx` wins | the middle row |
| `psd` | Read the layers by name from this `.psd`/`.psb` instead of the PNGs; `-psd` wins | — |

`scroll` is `1 − factor` of `ParallaxLayer`; the builder converts. For a layer meant to be `d` times
as far away as the play line, `scroll = 1/d`.

The draw order is one sorting layer (`-sortingLayer`, default `Default`): Order in Layer
`−1000 + 10·i` for the play line and everything behind it, `+1000 + 10·i` for layers faster than
the world. The runner at order 0 walks between them. To give each depth its own sorting layer,
see `unity-2d-level` → `reference/layer-stack.md`; the builder never edits the sorting-layer list.

## Tiling: what keeps an endless view covered

`ParallaxTiles` gives tile `i` one slot of `Pitch` world units and asks `TileSequence` what the
slot holds. The answer depends only on the seed and `i`, so a renderer recycled from the far side,
a `Snap()`, a respawn or walking back all show the same art in the same place.

| Mode | Each tile | Use |
|---|---|---|
| `Mirror` | The whole layer; every odd tile flipped | Continuous art that was never drawn to tile: sky, skyline, shopfronts, road |
| `Repeat` | Variants in order, touching | Art made to tile at its own width |
| `Shuffle` | One prop per tile, from a seeded bag, at a seeded offset inside its slot | Separate props on transparency |

`auto` picks `Shuffle` when the layer is marked `tile: false` or `role: "props"`, or when its
columns are less than 85 % filled (props with empty space between them); `Mirror` otherwise.

**Why props are never mirrored.** Mirroring a props strip puts the hydrant at its right edge next
to its own flipped copy at the start of the next tile. `Shuffle` cuts the layer at its empty
columns, one tile per prop (2 px margin), and draws them from a bag: every prop once per round,
never the same prop twice in a row, nothing flipped, with a seeded gap from `gap[0]` up. A prop
that touches the canvas edge was cut by the frame; it is left out while another prop remains, and
the report counts it (`droppedEdgeProps`).

Shuffled props pass behind or in front of the runner but are not level design: a hydrant the
runner must jump belongs in the level, placed from `scene_layers.py`'s `props/` files — never as
a tile.

## Pixel-perfect

`-pixelSnap` sets `ParallaxLayer.pixelsPerUnit` to the PPU, imports the tiles point-filtered and
uncompressed with that PPU (what `unity-2d-pixel-perfect`'s `SpriteImportFix` checks), and
`TileSequence` rounds every pitch and offset to the `1 / PPU` grid. Tile widths are whole pixels
by construction. Use one PPU for the scene, the runner and the Pixel Perfect Camera.

## Repainting in an image editor

Open `scene.psd`, repaint, save as 8-bit RGB, and rebuild with `-psd`. Layers are read **by
name** from the file itself (`PsdLayerReader`: PSD or PSB, RLE or raw), with the place each layer
has on the canvas, so neither Unity's PSD Importer nor a copy inside `Assets/` is needed. A
renamed layer is a new layer: give it a `scroll` and rebuild. 16-bit, CMYK and ZIP-compressed
files are refused with the reason.

## Checks

- Enter Play with the camera at x = 0: every `Mirror` layer shows the source picture in place.
- Run the camera past several tile widths in both directions and back: no seam, no gap, no prop
  beside its own copy, and the same props where they were.
- The report: each layer's tiling, variant count and `droppedEdgeProps`; a props layer with one
  variant repeats its single prop at varied gaps — generate a scene with more props.
- `ParallaxTiles` on a layer whose `ParallaxLayer.wrapWidth` is above 0 logs a warning: the two
  wraps fight. The builder leaves it at 0.
