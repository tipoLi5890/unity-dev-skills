# Motion and the upscale — Cinemachine, UI text, post-processing, physics stutter

> Part of the `unity-2d-pixel-perfect` skill. `SKILL.md` §6, §7 and §8 state the rules; this file
> holds the limits, the ranked alternatives and the routing behind them. Confirm each fix in a
> windowed run: the upscale symptoms need a canvas and a volume in the scene, and micro-stutter
> needs play mode with a moving rigidbody — a headless Editor shows none of them.

## 1. Cinemachine writes orthographic size too

Both Cinemachine and the pixel camera set orthographic size every frame, and the loser is
whichever ran first: jitter, plus framing that pops between shots. Add the
**`CinemachinePixelPerfect` extension** through the Add Extension dropdown on each virtual camera.
It calls the component's `CorrectCinemachineOrthoSize(float)` and hands back the nearest
pixel-perfect size, which is what makes the two agree. Adding the extension by `AddComponent` does
not register it with the virtual camera's extension list.

Three limits to design around rather than fix: a blend between two virtual cameras is not
pixel-perfect *during* the blend; `UpscaleRenderTexture` narrows the set of valid orthographic
sizes, so framing can land further from what you asked for; and a target group driven by a
framing transposer stays visibly choppy.

## 2. `UpscaleRenderTexture` versus UI text and post-processing

One cause, two symptoms: the scene is rendered small and then scaled up, and anything that runs
after that scale-up — or gets caught inside it — is working at the wrong resolution.

**Post-processing.** It runs after the upscale, so it filters an already-enlarged image and the
whole frame goes soft. Leaving `gridSnapping = PixelSnapping` puts post-processing back at native
resolution. Keeping the upscale means injecting a 2D renderer feature after post-processing rather
than a 3D one — a plain `ScriptableRendererFeature` added to a URP 2D renderer is **ignored without
an error**, which is the trap. On Unity 6 the 2D-side pair is `ScriptableRendererFeature2D` with
`ScriptableRenderPass2D`, injected at `RenderPassEvent2D.AfterRenderingPostProcessing` and
recording work through `AddRasterRenderPass`; confirm those four names against the URP version the
project resolved before writing the feature, because a wrong base class is the failure that
produces no message at all. The `OnRenderImage` plus `Graphics.Blit` shape does not belong in any
of it — that pair is incompatible with the render graph. Render Graph review for that work is
`unity-render-urp` → `reference/render-graph-review.md`.

**UI text.** A Screen Space – Camera canvas renders into the low-resolution buffer and is scaled
up with the scene, so text softens while the art stays crisp. Confirm the behaviour on your Unity
version in a windowed run before committing a canvas architecture to it. In reliability order:

1. Set the canvas to **Screen Space – Overlay**. It bypasses the camera entirely and draws at
   native resolution. This is the route that holds.
2. A separate UI camera with no pixel camera component on it, canvas in Screen Space – Camera.
3. Raise the font material's sharpness — on the material's Inspector, **Font Material → Debug
   Settings → Sharpness**, moved towards `1`. It addresses SDF threshold calibration at low
   reference resolutions and nothing about the buffer, so it is a partial mitigation: the text
   is still being scaled up with the scene.

Canvas render modes and scaler behaviour are `unity-ui-ugui`; CJK and SDF font atlases are
`unity-game-ui` → `reference/text-and-cjk.md`.

## 3. Micro-stutter is physics, not rendering

A sprite driven by `Rigidbody2D` stutters while everything else in the scene is smooth. Physics
advances on a fixed timestep and rendering does not, so the sprite's position is stale on frames
with no physics step and jumps on frames with one — then snapping quantises the result differently
each frame, which makes a sub-pixel error visible.

- `Rigidbody2D.interpolation = RigidbodyInterpolation2D.Interpolate` on every physics-driven
  sprite. This is the fix; the rest is tightening.
- Match the fixed timestep to the frame rate you actually run at (`Time.fixedDeltaTime = 1f / 60f`
  for 60 fps), so a step and a frame stay in step.
- Camera follow belongs in `LateUpdate`, after everything that moved this frame. In
  `FixedUpdate` the camera samples positions the renderer will not use.
