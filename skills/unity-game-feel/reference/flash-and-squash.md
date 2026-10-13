# Flash, squash and tweens — change the look, then give it back exactly

> Part of the `unity-game-feel` skill. A hit flash on meshes and sprites and what each method
> costs the batcher; squash and stretch about the feet that keeps volume; a tween runner with
> easing and no third-party library; springs for motion that chases a moving target.

Every effect here borrows something — a colour, a material, a scale — and the bug is always in
the giving back. Capture once, from rest; restore on every way out (time up, disabled, destroyed,
pooled).

## 1. A hit flash — three methods, three costs

`resources/RendererFlash.cs` does all three behind one call, chosen by `mode`:

| Mode | How | Batching | Use for |
|---|---|---|---|
| `PropertyBlock` | One colour property (`_BaseColor`, falling back to `_Color`) set through a `MaterialPropertyBlock` | A renderer carrying a property block drops out of the SRP Batcher while it carries one; the block is removed on restore, so it batches again after | A handful of characters for a few frames — the default |
| `MaterialSwap` | Every material replaced by `flashMaterial`, the originals put back | All flashing objects share one material and batch together | A crowd flashing at once; a sprite that must turn solid white |
| `SpriteTint` | `SpriteRenderer.color` | Free | A sprite flashing a colour darker than itself — red, never white |

```csharp
flash.Flash();                              // configured colour, 0.08 s
flash.Flash(Color.red, 0.12f, 0.4f);        // 40 % of the way to red: a softened flash
flash.Cancel();                             // end now, look restored
```

Defaults: `colour` white, `seconds` 0.08 (five frames at 60 — long enough to see, short enough to
read as a hit), `colourProperty` `_BaseColor`, `unscaledTime` on (the flash ends on time inside a
hit stop).

**White on a lit material is not white on screen.** `_BaseColor` multiplies the albedo texture
and the light; at full white the character is its texture under the scene's light, not a white
silhouette. For a true white-out, use `MaterialSwap` with an unlit material (URP
`Universal Render Pipeline/Unlit`, base colour white), or a shader with an additive flash
property. A sprite's `color` multiplies the texture, so `SpriteTint` can only darken and tint:
white needs `MaterialSwap` with a Sprite Unlit Shader Graph that outputs the flash colour with
the texture's alpha — the stock `Universal Render Pipeline/2D/Sprite-Unlit-Default` multiplies,
so it cannot.

**Why capture-once matters.** A second hit inside the first flash calls `Flash` again. A flash
that captures "the original" on every call captures the flash colour, and restores it. The
component captures only when it starts from rest; a second call extends the end time and never
shortens it. `FEEL_JOURNEY_BREAK=flash` swaps in the capture-every-call version, and the
overlapping-flash test catches the tinted sentry coming back white.

**What a property block keeps.** The flash starts from the block that was there (a per-instance
tint, a texture offset set by another script) and writes only its colour into it, so the other
values survive. Restore puts the saved block back, or clears it with `SetPropertyBlock(null)`
when there was none.

**Pooling.** `OnDisable` restores, so a sentry returned to the pool mid-flash comes back with its
own colour. Call `Collect()` after swapping the renderers under the object (a new skin, a
weapon attached).

**Invincibility blink is not this.** Blinking the runner while it cannot be hit is presentation
reading `Invincible` from the damage receiver each frame — `renderer.enabled = (int)(t * 15) % 2 == 0`
on the visual child — and nothing reads the renderer to learn whether the runner can be hit
(`unity-combat` → `reference/iframes-and-knockback.md`). Under `reduceFlash`, replace the blink
with a steady 50 % alpha.

## 2. Squash and stretch about the feet

```csharp
Tween.Squash(visual, Vector3.one, 0.8f, 0.12f, false);     // land: 80 % tall, eased back
Tween.Squash(visual, Vector3.one, 1.25f, 0.15f, false);    // launch: 125 % tall
```

| Rule | Why |
|---|---|
| Pivot at the feet | A scale about the centre lifts the soles off the ground on a squash and sinks them on a stretch. For a mesh, parent the visual under an empty at the feet; for a sprite, set the pivot to bottom-centre on import (`unity-2d-sprites` → `reference/sprite-animation.md`) |
| Keep volume | In 3D the two side axes take `1/sqrt(y)`; in 2D the one visible side axis takes `1/y`. A squash that only shortens reads as shrinking |
| Scale the visual child, never the body | A scaled collider changes what the runner stands on and fires contacts |
| `Ease.OutBack` back to rest | Overshoots about 10 % and settles: one wobble, then still |
| 80–150 ms | A landing squash longer than the next step reads as rubber |

Squash and the Animator both write the visual's scale if a clip keys scale. Remove scale curves
from the clips on that object, or put the squash on a parent of the animated object. The tween
runs in `LateUpdate`, after the Animator, so whichever writes last is what is drawn — and two
writers of one property is a fight decided by script order.

For a looping breathe on an idle sprite — code-driven, about 1 % of the height over ~3 s — use
the snippet in `unity-2d-sprites` → `reference/sprite-animation.md` §5; it is a sine on the same
feet-pivoted scale, not a tween.

## 3. The tween runner

`resources/Tween.cs`: tweens are structs in a fixed array of `capacity` 64, so nothing allocates
after start-up. A tween over capacity is refused and counted in `Tween.Dropped`, never
allocated.

```csharp
Tween.Scale(visual, Vector3.one, 0.12f, Ease.OutBack);
Tween.MoveLocal(visual, Vector3.zero, 0.12f, Ease.OutCubic);
Tween.Move(pickup, gateSlot.position, 0.3f, Ease.InOutQuad);
TweenHandle h = Tween.Value(light, 2f, 0f, 0.2f, Ease.OutQuad,
                            (target, v) => ((Light)target).intensity = v);
h.Complete();          // jump to the end and stop
```

- **One writer per property.** A new `Scale` on a transform replaces the running one. Two tweens
  on one scale fight every frame and the later slot wins by accident.
- **`Value` takes its target back as an argument**, so the lambda captures nothing; a lambda that
  captures a local allocates a closure on every call. When the target is a `UnityEngine.Object`
  the tween ends by itself once that object is destroyed.
- **A destroyed transform ends its tweens.** A pooled object being disabled does not: call
  `Tween.CancelAll(transform)` on release.
- **`unscaled` true** for anything that accompanies a hit stop or animates a pause menu.
- **A `TweenHandle` is safe to keep after the tween ends.** `IsAlive` reads false; `Cancel` and
  `Complete` do nothing.

| Ease | Shape | Use for |
|---|---|---|
| `OutQuad`, `OutCubic` | Fast start, soft stop | Most UI and object moves |
| `InOutQuad`, `InOutCubic` | Soft both ends | A pickup sliding onto a gate cell; camera-free pans |
| `InQuad`, `InCubic` | Soft start, hard stop | Something falling into place, hitting at the end |
| `OutBack` | Overshoots ~10 %, settles | Arrivals, pop-ins, squash return |
| `OutElastic` | Rings past the end three times | A counter or a badge; never a character |
| `OutBounce` | Bounces at the end | A dropped item landing |

An `AnimationCurve` field is the alternative when a designer wants to draw the curve:
`Mathf.LerpUnclamped(a, b, curve.Evaluate(t))` in a `Value` tween. Curves cost an evaluation per
frame; the enum is arithmetic.

## 4. Springs — motion that chases

A tween goes from A to B in a fixed time. When B moves while the motion runs — a health bar
chasing its value, a recoil that a second shot interrupts, a visual lagging behind a body that
teleported — use a spring instead:

```csharp
Spring lean;                                     // a field; value and velocity persist
void LateUpdate()
{
    float target = runner.LaneChangeVelocity * -2f;            // degrees of lean
    float a = lean.Step(target, 4f, 0.6f, Time.deltaTime);     // 4 Hz, damping 0.6: one overshoot
    visual.localRotation = Quaternion.Euler(0f, 0f, a);
}
// a hit: lean.Push(-120f);  — velocity added, the spring brings it back by itself
```

| Damping | Behaviour |
|---|---|
| 1 | Arrives without overshoot |
| 0.5–0.6 | One overshoot — alive without wobbling |
| 0.2 | Rings — a jelly, a spring-loaded sign |

Frequency is oscillations per second: 2–3 Hz reads heavy, 6–8 Hz snappy. The integrator in
`Spring.Step` is implicit, so a long frame (a hitch, a hit stop ending) cannot make it explode.

## 5. Checking it

The journey asserts that a flash returns the property block, the tinted sentry's own block and
the sprite's own colour after two overlapping flashes. Squash has no journey: a person judges it,
from a windowed capture at real speed. To see whether a squash or a spring is jittering rather
than moving, measure frame-to-frame change in a crop around the runner — `unity-debug` →
`reference/motion-and-timing.md`.
