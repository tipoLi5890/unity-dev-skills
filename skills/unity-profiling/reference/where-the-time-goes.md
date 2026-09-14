# Where the time goes: four causes this skill owns, and the rest routed

> Part of the `unity-profiling` skill. Read it with a window already in hand. Every section starts
> from a number in that window, not from a suspicion.

Four shapes of cost are measurement problems and belong here. Everything else is owned by the
skill that owns the subsystem, and the last table sends it there in one line.

---

## 1 · A single large `ft_max` the first time something appears

**The shape:** one frame of tens of milliseconds, the first time a material, a particle effect or
a UI screen is shown. Never again in that session. `hitches=1`, median untouched.

That is shader variant compilation and the GPU program upload that follows it. It happens once per
variant per session, which is why it disappears on the second run and reappears for the player.

**Confirm it, do not assume it.** Take a window with `warmup: 0` labelled `-cold` over the exact
moment the thing first appears, and a second window over the same moment afterwards. A first-touch
cost shows as a large `max` in the cold window and nothing in the warm one. A raw capture around
that frame names the marker directly — the GPU program creation marker is the one to look for, and
`reference/raw-capture.md` is how to read it without the Profiler window.

**The fixes, cheapest first:**

- **Preloaded Shaders** in Graphics Settings — a variant collection loaded at startup. Moves the
  cost into the load screen, where it is affordable.
- **`ShaderVariantCollection.WarmUp()`** on a collection recorded while playing the real content.
  A collection recorded in the Editor on different settings warms the wrong variants.
- **A dedicated warm-up step** that renders the offending material once off-screen during the boot
  situation. Blunt, reliable, and easy to verify with the same pair of windows.

Unity also has a shader-warmup helper type whose namespace has moved between versions — confirm
the spelling on your version before writing it into a boot path, and keep the collection route as
the fallback, because it has been stable for longer.

**Verify the fix the same way you found it:** the cold window's `ft_max` drops to roughly the warm
window's. If it does not, you warmed a different variant.

---

## 2 · GC: allocation per frame, and the collection that follows

**The shape:** `Memory/GC Allocated In Frame` has a non-zero median, and `ft_max` spikes on a
period rather than at an event. The sum across a window is the number that matters: 2 KB a frame
is 184 KB in ninety frames, and the collection that eventually frees it is the spike.

**The usual sources**, in the order they turn up:

- **String building in `Update`** — interpolation, `ToString()` on a changing number, a log line
  that is cheap to leave in. A HUD that formats a score every frame allocates more than the
  gameplay does. Building that HUD cheaply is `unity-game-ui`.
- **A `foreach` over a collection whose enumerator is a class**, or over an interface-typed
  reference to a struct enumerator.
- **Closures and lambdas captured per call**, including in event subscriptions inside `Update`.
- **Physics query methods that return arrays** rather than the `NonAlloc` variants that fill one.
- **`GetComponent` in a loop** returning a new array from the plural overloads.

**Record the GC mode with the window.** `run.gcMode` says whether incremental collection is on.
Incremental spreads the cost across frames, which turns one visible spike into a raised median —
a real improvement in feel and a *worse*-looking median in the table. Say which mode both sides
used, or the comparison argues with itself.

**The measurement, not the guess:** allocation per frame is a counter, so the before/after is a
window pair like any other. Zero allocated per frame in the steady state is an achievable target
for a small game; treat any non-zero median as a thing to explain rather than a thing to accept.

---

## 3 · Synchronous loads inside a frame

**The shape:** `ft_max` spikes exactly when something spawns or streams, and the spike lines up
with a jump in `Game/<system>.completed`. That correlation is the whole diagnosis — the work
counter timestamps the cause and the frame time measures the effect.

Synchronous `Resources.Load`, a synchronous asset-bundle or addressable load, a large
`Instantiate` of a prefab tree, and the first play of an audio clip whose load type forces a
decompression on the calling thread, all produce it.

**What to do:**

- Move the load off the frame: an async load started during the previous quiet moment, awaited by
  the situation's readiness set rather than by a sleep. Readiness as a set that must be complete
  before a moment counts as begun is `unity-play-harness` → `reference/situations.md`.
- Pre-instantiate into a pool during loading, and count pool hits and misses with a work counter so
  the pool's *effectiveness* is measurable — `reference/work-counters.md`.
- For audio specifically, the load type and compression choice is the whole cost, and that is
  `unity-audio`.

---

## 4 · Distant geometry: triangles you are paying for and nobody can see

**The shape:** `Render/Triangles Count` median is high while the camera looks at distance, and
falls sharply when it looks at the floor. Draw calls may be unremarkable — this is per-vertex
cost, not per-batch cost.

**The measurement worth taking:** the share of the window's triangles coming from objects smaller
than a few pixels on screen. Anything under roughly 8 px of screen height is contributing detail
nobody can resolve, at full vertex cost. Count those objects in the situation and report the share
— a number like "62% of submitted triangles come from objects under 8 px" makes the fix obvious in
a way that "it's a bit heavy" does not.

**The fixes:**

- **`LODGroup` with a proxy mesh at the far end.** The last LOD wants to be a genuinely different
  mesh, not a lightly decimated one.
- **`screenRelativeTransitionHeight`** on each LOD level decides where the swap happens; the
  defaults are tuned for large props, not for lane furniture seen from the sofa.
- **`QualitySettings.lodBias`** scales every transition at once — the fastest way to find out
  whether LOD is the answer before authoring anything. Halve it, take a window, look at the
  triangle median. Then put it back and do the work properly.

Generating and decimating the meshes themselves is `unity-3d-models`.

---

## The rest, routed in one line

| The window says | Owned by |
|---|---|
| Draw calls and SetPass calls high, triangles ordinary | `unity-sprite-atlas` for 2D batching · `unity-render-urp` for batching settings · `unity-game-ui` for a canvas rebuilding every frame |
| `gpuFrameTime` much larger than the CPU times | `unity-render-urp` — fill rate, post-processing, resolution |
| `Render/Shadow Casters Count` high | `unity-render-urp` — shadow distance, cascades, which lights cast |
| Pixel art shimmering or soft as well as slow | `unity-2d-pixel-perfect` |
| Slow only in the browser | `unity-web-release` |
| Slow only on the device | `unity-android-release`, after a `player-dev` window on the device |
| Slow only when audio plays | `unity-audio` |
| The frame time is fine and it still feels wrong | `unity-play-harness` — the complaint needs to become a situation before it can become a number |

And when none of the above fits: stop widening the window and narrow it instead. One raw capture
around the offending frame names the marker that owns the time, and `reference/raw-capture.md` is
how to extract it as a CSV rather than a screenshot of a UI.
