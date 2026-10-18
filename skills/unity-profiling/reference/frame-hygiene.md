# Frame time you can trust: the machine, the pair, the instrument

> Part of the `unity-profiling` skill. Before a frame-time number goes into a report or a gate.
> Worked setting: a tennis game measured in the Editor on a machine shared with other agents'
> Blender and Unity jobs.

## A busy machine multiplies the number

The tennis game's per-tier frame-time test read **4 to 10 ms** a frame while another job was
running Blender and a second Unity Editor on the same machine. The same test on a quiet machine read
**1.6 to 2.4 ms** (means, every tier and screen mode). Nothing in the game had changed. A smoke test
that checks the simulation keeps up with its clock also failed once under the same load (5 frames
more than 2 ticks behind, against a limit of 3) and passed when rerun on the quiet machine.

Before any frame-time window:

```bash
ps -axo %cpu=,comm= | sort -rn | head          # nothing else above a few % CPU
pgrep -fl "Contents/MacOS/Unity( -|$)"         # one Editor: yours
pgrep -fl Blender                              # none
```

Record the check's output with the window. A number taken under load is not a slower version of
the real number; it is a different measurement, and it cannot be compared with anything.
Running several Editors and agents on one machine (the Editor cap, the lane queue): `unity-debug`
→ `reference/parallel-runs.md`.

## Measure the thing as a pair

A cost is the difference of two windows in the same situation with one switch flipped:

- **Post-processing:** a window with `UniversalAdditionalCameraData.renderPostProcessing` on, then
  one with it off on every camera. In the tennis game the difference was 0.1 to 0.45 ms a frame
  across tiers, about 0.2 ms on the low tier.
- **Scripts:** the `Update.ScriptRunBehaviourUpdate` and `PreLateUpdate.ScriptRunBehaviourLateUpdate`
  markers summed per frame: about 0.07 ms together. Everything else in the growth from about 1 ms
  to 1.6–2.4 ms was the picture itself (sky, transparent fence, longer shadows, particles, more
  objects), not attributed item by item.
- **`PlayerLoop`** excludes the Editor's own work; report it beside the frame time.

Unlock the frame rate for these windows (`Application.targetFrameRate = -1`, vSync off), and put
the targets back after.

| Tier | Situation | Before polish, mean / p95 ms | After, mean / p95 | Post off, mean | Triangles (with shadows) | Batches |
|---|---|---|---|---|---|---|
| High | Solo | 0.92 / 1.09 | 2.00 / 2.58 | 1.55 | 223k | 240 |
| High | Split screen | 1.33 / 1.64 | 2.43 / 3.06 | 2.00 | 123k | 416 |
| Medium | Solo | 0.98 / 1.21 | 1.63 / 2.21 | 1.54 | 84k | 207 |
| Low | Solo | 0.89 / 1.08 | 1.58 / 1.98 | 1.39 | 56k | 144 |

Editor, quiet machine. These say what changed between two builds of one game on one machine, and
nothing about a phone.

## The Editor cannot split CPU from GPU

An Editor frame time is CPU and GPU together, plus the Editor. A GPU-bound frame and a CPU-bound
frame of the same length look identical, and the desktop GPU in the Editor is not the device's.
For the split, use a development player on the target with the GPU frame-time counters
(`reference/counters.md`) or the platform's GPU tools. Until then, say "Editor, not device" next
to every number.

## Other things that skew a window

- **Blocking work inside the window.** Encoding a PNG screenshot blocked the main thread about
  100 ms in the same project and showed up as a hitch in a timing metric. Take screenshots outside
  measured windows.
- **First-play shader compilation.** The Editor compiles shaders asynchronously on first use and
  draws a cyan placeholder for a second or two; warm up past it.
- **JIT on first call.** Under Mono the first call into a large method compiles it. A simulation
  that stalls on its first hit tick is the JIT; run a short throw-away warm-up before the clock
  starts.
