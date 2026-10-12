# Pixel-perfect follow — two components write one number

> Part of the `unity-camera` skill. A pixel-perfect camera and a Cinemachine camera both set
> orthographic size every frame. This file is the rule that makes them agree, the limits that
> follow from it, and what damping does to pixel art. The pixel-perfect component itself — which
> of the two to use, reference resolution, snapping modes, import settings — is
> `unity-2d-pixel-perfect`. Names are Cinemachine 3.x; `reference/version-and-names.md`
> translates.

## The conflict

The pixel camera computes the one orthographic size at which an art pixel covers a whole number
of screen pixels and writes it to the `Camera`. The Brain writes the live Cinemachine camera's
`Lens.OrthographicSize` to the same `Camera`. Whichever ran last wins that frame: the size pops
between two values, sprites shimmer, and framing jumps on every camera switch.

## The rule

**Add the `CinemachinePixelPerfect` extension to every Cinemachine camera that can go live, on
the camera's own GameObject.**

Each frame the extension asks the pixel camera for the nearest legal size to the one the lens
wants — `PixelPerfectCamera.CorrectCinemachineOrthoSize(float)` — and puts that in the camera
state. From the first such call the pixel camera stops writing the size itself and leaves it to
Cinemachine. Two consequences:

- **One camera without the extension breaks all of them.** When it goes live the pixel camera is
  no longer writing and nothing corrects the lens, so that shot renders at an arbitrary size.
  The pixel camera resumes only after it is disabled and enabled again.
- **The extension is found only on the camera's own object.** It registers in `Awake` by looking
  for a Cinemachine camera beside it; on a child or a parent it is never called.

## Four checks before believing it works

1. **The extension is compiled in.** `CinemachinePixelPerfect` is real only when the project has
   URP 14.0.5 or newer, or `com.unity.2d.pixel-perfect` 2.0.3 or newer. Without either, the class
   still exists, as an empty component that does nothing. Read `Packages/packages-lock.json` for
   one of the two.
2. **It is looking for the component you have.** In a URP project the extension looks for the
   URP `PixelPerfectCamera` and for nothing else. The standalone package's component of the same
   name on the camera is invisible to it. Which of the two a project should carry:
   `unity-2d-pixel-perfect` → `reference/pipeline-and-migration.md`.
3. **The pixel camera is on the Brain's object.** The extension reads it from the `Camera` the
   Brain drives, and only while it is enabled.
4. **The size on the `Camera` is a corrected one.** In play mode, read it back:

```bash
unity command eval 'var c = UnityEngine.Camera.main; return c.orthographicSize + " " + c.pixelWidth + "x" + c.pixelHeight;'
```

   Change `Lens.OrthographicSize` on the live Cinemachine camera by a small amount. A corrected
   size stays put or jumps to the next legal value; an uncorrected one follows the lens exactly.
   In edit mode the correction applies only while the pixel camera's Run In Edit Mode is on.

## Which sizes are legal

Call the pixel camera's own size B (its `orthographicSize` property; with a cropped frame that is
`refResolutionY / (2 × assetsPPU)`, so 180 lines at 16 pixels per unit is 5.625) and its integer
scale z (how many screen pixels one art pixel covers: 6 for a 180-line reference on a 1080-line
screen). The correction divides by a whole number:

| Pixel camera mode | Sizes Cinemachine can land on | With B = 5.625, z = 6 |
|---|---|---|
| `gridSnapping = UpscaleRenderTexture` | B, B/2, B/3 … | 5.625, 2.81, 1.875 … |
| `PixelSnapping` or `None` | z × B, then that divided by 2, 3, 4 … | 33.75, 16.875, 11.25, 8.44, 6.75, 5.625 … |

- **With the upscale texture, Cinemachine can zoom in by whole factors and cannot zoom out at
  all.** A lens asking for 8 gets 5.625.
- **Without it, more sizes are legal, and each is a different whole number of screen pixels per
  art pixel.** A lens asking for 8 gets 8.44: a wider view than the reference resolution was
  designed for, drawn at 4× where the art was drawn for 6×.
- **Ask for a legal size.** Set each Cinemachine camera's lens to the size it will actually get,
  so the composer's dead zone and the confiner are computed for the real view. For the designed
  framing that is B.
- **A smooth zoom is not available.** A zoom animated on the lens arrives as steps. Design zooms
  as cuts between two legal sizes, or as a short blend that accepts the step.

## Limits to design around

- **A blend between two cameras of different sizes is not pixel-perfect while it runs.** The size
  interpolates and is corrected each frame, so it steps. Blends between cameras of the same size
  are clean; for a size change, cut.
- **`UpscaleRenderTexture` leaves the fewest legal sizes**, so framing can land further from what
  was asked.
- **Group framing stays choppy.** `CinemachineGroupFraming` wants a continuously changing size
  and receives steps. Track the group for position and keep the size constant, or frame groups
  with fixed cameras.
- **With a confiner, the corrected size is the size the confiner needs.** The extension runs
  first by execution order, and the confiner reads the corrected lens — but it does not notice a
  later change. After a resolution change at the same aspect ratio, call
  `confiner.InvalidateLensCache()`.

## Damping and the pixel grid

The pixel camera snaps the *view matrix* to the pixel grid at render time. It does not move the
Transform. Two things follow.

**The numbers a test reads are unsnapped.** `camOffset` from `resources/CameraProbe.cs` is the
continuous offset. That is the right quantity for the two-clocks check in
`reference/update-order-and-jitter.md`, and it says nothing about what the snap does afterwards.

**A damped camera and a snapped sprite round at different moments.** While the camera eases, its
position crosses a pixel boundary on one frame and the runner's crosses on another, so the runner
steps one pixel back and forth against the background. The offset is smooth; the picture is not.
In order of preference:

1. **Zero damping on the axis of travel.** The runner's column is locked to the screen and the
   two always round together. This is the default for a pixel-art side run.
2. **A dead zone and no damping.** The camera is still, or rigidly locked, and never easing.
3. **`UpscaleRenderTexture`.** The scene is drawn at the reference resolution, where one camera
   pixel is one art pixel, so sub-pixel disagreement cannot be drawn. It brings the UI and
   post-processing consequences listed in `unity-2d-pixel-perfect`.
4. **Keep the damping and accept it**, for slow cameras where a one-pixel wobble is below notice.

Look-ahead is damping with prediction: the same rule, and the same preference for a fixed
`ScreenPosition` offset over `Lookahead` in pixel art.

A runner on a `Rigidbody2D` needs interpolation before any of this is judged. An uninterpolated
body adds a real clock error under the rounding, and the two look identical by eye —
`scripts/camera_jitter.py` tells them apart: a clock error shows in the flip rate, a rounding
wobble does not.

## What a headless run can and cannot confirm

A batch-mode run confirms the size on the `Camera` and the flip rate of the offset. It does not
show shimmer, the one-pixel wobble or a soft upscale: those need a windowed run at the target
resolution and a person looking — `unity-debug` → `reference/visual-checks.md`.

## Related skills

Reference resolution, snapping modes, import settings and tilemap seams:
`unity-2d-pixel-perfect`. The 2D renderer the pixel camera belongs to: `unity-render-urp`.
