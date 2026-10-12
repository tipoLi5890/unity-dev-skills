# Parallax — layers that follow a fraction of the camera

> Part of the `unity-2d-rendering` skill. Parallax is one number per layer and one rule about
> timing: the layer must be placed **after** the camera has reached its final position for the
> frame. Most parallax that shimmers has the number right and the timing wrong.

## One factor per layer

`resources/ParallaxLayer.cs` goes on the root of each layer. Each frame it places the layer at

```
layer position = layer start + (camera position − camera start) × factor
```

| `factor` | On screen | Use in the side run |
|---|---|---|
| `1` | Does not move: locked to the camera | Sky gradient, sun |
| `0.9` | Crawls | Far skyline |
| `0.6` | Slow | Mid-distance towers |
| `0.3` | A little slower than the world | Near rooftops behind the play line |
| `0` | Moves with the world — no component needed | The roofs the runner crosses, hazards, the gate |
| `-0.3` | Faster than the world | Foreground pipes and aerials passing in front |

`factor` is per axis. A side run usually wants a strong horizontal factor and a weak vertical
one — `(0.6, 0.1)` — so a jump does not slide the skyline up and down with the runner. A
depot seen from above wants none: parallax under a top-down camera reads as layers sliding
over each other, and is reserved for a deliberate effect such as cloud shadows.

Pick factors from distance, not by taste. For a layer meant to be `d` times as far from the
viewer as the play line, `factor = 1 − 1/d`: twice as far → `0.5`, ten times → `0.9`.

Draw order is not derived from the factor. Each layer is its own sorting layer, ordered back
to front in the layer list; the stack for a whole level is `unity-2d-level` →
`reference/layer-stack.md`. A parallax layer's children all share that one layer, so the four
keys of `reference/sort-order.md` order them among themselves and never against the runner.

## Timing: after the camera

The camera is moved in `LateUpdate` — by a Cinemachine Brain at execution order 100, or by a
follow script. A parallax script that runs before it reads last frame's camera, and every
layer trails by one frame's travel: invisible at constant speed, a visible shudder whenever
the camera accelerates, lands or shakes.

`ParallaxLayer` runs in `LateUpdate` at execution order 200 and reads the output camera's
Transform, so it sees the final position whichever rig produced it. Three ways to break that:

- **The Brain blends in `FixedUpdate`.** The camera then moves on the physics clock and the
  layers on the render clock. Fix the rig, not the layer: `unity-camera` →
  `reference/update-order-and-jitter.md`.
- **A follow script with an execution order above 200.** Lower it, or raise the layer's.
- **Reading a Cinemachine camera's Transform instead of the output camera's.** The live
  Cinemachine camera does not carry blends or shake; the Unity `Camera` does.

Rig set-up for a side follow, dead zones and confiners: `unity-camera` →
`reference/follow-2d.md`.

### Cuts and respawns

When the camera cuts — a respawn, a room change — a layer with factor `0.6` would jump by 60 %
of the cut and show a different part of its art, or its edge. Call `Snap()` on every layer in
the frame of the cut: the layer then moves the whole distance with the camera and keeps its
place on screen.

```csharp
// On the respawn path, in the same frame the runner and camera are teleported.
foreach (ParallaxLayer layer in _layers) layer.Snap();
```

`Snap()` only sets a flag; the move happens in that frame's `LateUpdate`, after the camera.
Subscribing to the camera's cut event, and warping a Cinemachine camera with its target, are
`unity-camera` → `reference/shake-and-blends.md`.

## Endless wrap for a runner

A side run has no right-hand edge; a layer cannot be infinitely wide. Set `wrapWidth` to the
width after which the art repeats. When the camera has drifted more than half that width from
the layer's centre, the layer jumps by a whole `wrapWidth` — and because the art repeats with
that period, the jump is invisible.

Requirements, all checked by looking at the first wrap in the Scene view:

- The art tiles seamlessly at exactly `wrapWidth`.
- The layer is drawn at least **view width + `wrapWidth`** wide, centred on the camera at
  start. Three copies of a tile as wide as the view always suffice. A single
  `SpriteRenderer` in Tiled draw mode with its width set to three tiles does the same in one
  draw call.
- View width in world units is `2 × orthographicSize × aspect`. Size the layer for the widest
  aspect the game supports.

```csharp
// Far skyline: a 24-unit tile, three copies under one root.
var far = skylineRoot.AddComponent<ParallaxLayer>();
far.factor = new Vector2(0.9f, 0.2f);
far.wrapWidth = 24f;
```

The wrap is horizontal only. A vertical layer that must not run out is made tall enough for
the level's height range instead.

World coordinates grow without bound in an endless run; past a few thousand units sprite
positions lose sub-pixel precision and everything shimmers, parallax first. Shift the world
back to the origin periodically and call `Snap()` in the same frame.

## Orthographic or perspective

Two ways to get the same picture.

| | Orthographic camera + `ParallaxLayer` | Perspective camera, layers at different z |
|---|---|---|
| Parallax comes from | The script | The projection: no script |
| Factor | Exactly the number entered | `z / (D + z)` for a layer `z` behind the play plane, camera `D` in front of it |
| Layer art size | As drawn | Must be scaled up by `(D + z) / D` to look the same size |
| Pixel-perfect | Compatible | Not compatible: sizes on screen are no longer whole pixels |
| Sorting | Sorting layers | Sorting layers still decide; z is only the parallax amount |
| Zoom | Layers keep their factor | Layers spread apart correctly as the camera dollies |

Use orthographic for pixel art and for anything that needs exact factors. Use perspective when
the camera dollies in and out and the depth should respond. Under perspective with the default
sort mode, distance is measured from the camera position, so two layers on one sorting layer
sort by true distance — keep each depth on its own sorting layer anyway.

## Pixel-perfect snapping

With a pixel-perfect camera the camera's view is snapped to the art's pixel grid. A layer at
factor `0.6` lands between pixels on most frames: its texels swim against the snapped
foreground.

Set `pixelsPerUnit` on the layer to the art's pixels per unit. The layer's final position is
then rounded to the same `1 / pixelsPerUnit` grid the camera uses. The consequence is visible
and correct for pixel art: a slow layer advances in whole-pixel steps, a few times a second,
instead of gliding.

- Use factors that make the stepping regular — `0.5`, `0.75`, `0.875` — so a layer moves one
  pixel for every 2, 4 or 8 camera pixels.
- Do not snap a layer when the camera uses an upscaled render texture and the layers are meant
  to move at screen resolution; decide that once for the whole game.
- Which pixel-perfect component, its snapping modes and the reference resolution:
  `unity-2d-pixel-perfect`. A Cinemachine follow on top of it: `unity-camera` →
  `reference/pixel-perfect-follow.md`.

## Checks

- Record a run with the camera accelerating and stopping — the launch pad in the side run is
  the stress case — and step through it frame by frame. A layer that moves on the frame
  **after** the camera stops is running before the camera.
- Scene view, play mode: watch one wrap happen. A visible seam is art that does not tile at
  `wrapWidth`; a visible gap is a layer narrower than view width + `wrapWidth`.
- Respawn at the far end of the level: every layer shows the same art in the same place as
  before the cut.
