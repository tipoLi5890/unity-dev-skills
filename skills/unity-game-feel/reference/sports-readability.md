# A fast ball you can read, and feedback that does not stop the clock

> Part of the `unity-game-feel` skill. For ball and puck games where the player times an action
> against a small, fast object: tennis, table tennis, volleyball, air hockey, rhythm-timed sports.
> Worked setting: a tennis game whose simulation runs at 120 Hz on a background thread and
> hands the renderer interpolated snapshots, played at 60 fps.

A real tennis ball is 6.7 cm across. From a broadcast camera 16 m behind the near baseline the
far baseline is about 45 m away, where the ball is a few pixels at 1080p and smaller in a
half-width split screen. Readability is the first feedback a timing game owes the player; the
flashes and dust come second.

## 1. Size, outline, trail

| Element | Rule | The tennis game's numbers |
|---|---|---|
| Display size | Draw the ball larger than life, and larger again when far, never below a pixel floor | 1.6 × real size; at least 11 px on a 1080-line reference; capped at 4.2 × real size |
| Outline | A back-face shell slightly larger than the ball, unlit, dark (`_Cull` = Front) | Shell 1.2 × the ball, ink colour; separates a light ball from a light sky or court |
| Trail | `TrailRenderer`, width and alpha driven by speed; cleared on a teleport | Time 0.13 s; nothing below 8 m/s, full above 34 m/s (about 120 km/h); width 0.55–0.95 × ball, start alpha 0.12–0.7; cleared when the ball jumps more than 2 m in a frame or is in the server's hand |
| Shadow | A soft blob on the ground on every quality tier | Grows from 1.15 to 2.4 × the ball and fades from 0.62 to 0.22 alpha as height goes 0 → 4–5 m |

The pixel floor, per camera (`resources/MinScreenSize.cs`):

```csharp
float dist = Vector3.Distance(cam.transform.position, p);
float worldPerPx = 2f * dist * Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad)
                 / (1080f * Mathf.Max(0.1f, cam.rect.height));      // the viewport, not the screen
float d = Mathf.Clamp(minPx * worldPerPx, baseDiameter, maxDiameter);
```

Measure against a fixed reference height (1080), not `Screen.height`, so the ball is the same
share of the screen at every resolution and in the Editor's Game view. In split screen each camera
needs its own copy of the ball, sized for that camera, on that camera's own layer: one transform
cannot be two sizes.

## 2. Never let the ball stop for a frame

With a simulation on its own thread, the renderer interpolates between the last two snapshots at
a render time slightly behind the simulation clock. When the simulation is late by a tick, the
newest snapshot is older than the render time, plain interpolation clamps to it, and the ball
**stops for one frame and jumps the next**. Players read that as a stutter in the ball, and in a
timing game it moves the moment they judge.

Fix: while the ball is in free flight, extrapolate from the newest snapshot with its velocity and
gravity, for at most 1.5 ticks, never below the ground:

```csharp
double ahead = renderTick - frame.Tick;
if (ahead > 0 && ballInFreeFlight)
{
    float t = (float)(System.Math.Min(ahead, 1.5) * tickSeconds);
    p = frame.BallPos + frame.BallVel * t + new Vector3(0, -0.5f * 9.81f * t * t, 0);
    p.y = Mathf.Max(p.y, radius);
}
```

Do not extrapolate a ball resting on a racket or in a hand, and do not slow the render clock to
match a late simulation: that makes every timing cue late too.

**Measure it on screen.** Record the ball's screen position and the render tick every frame, then
compare each frame's screen speed (px per tick) with the median of the two frames either side.
Skip frames near a hit, bounce or net contact (the speed really changes there) and frames where
the ball moves less than 1.5 px per tick. A deviation above 25% is a hitch.
`scripts/screen_smoothness.py` computes this from a JSONL log and has a `selftest`. In the tennis
game the deviation p95 went from 13.2% to about 5% with extrapolation, and the test asserts
hitches ≤ max(2, samples / 100). The same measure on the player's screen position checks the
character's interpolation and the camera follow together.

## 3. Feedback in a timing game

| Event | Feedback | Notes |
|---|---|---|
| Hit | A short white core flash at the contact point and an expanding ring coloured by the timing grade | Gold for perfect, cyan for great, white for good, amber for early or late, grey for a mishit. All from pools built at match start |
| The opponent's hit | The same ring, white, smaller, and a fainter core | A solid white disc at the far end of the court read as a second ball |
| Bounce | A puff of dust (count by quality tier), a faint white ring, and a mark stretched along the ball's direction that fades over 1.4 s | The mark doubles as information: where it landed |
| Net | The net mesh wobbles | No flash: the ball must stay visible |
| Smash | Four thin speed lines following the ball for 0.3 s, and the camera's 4 cm dip | `unity-camera` → `reference/broadcast-sports.md` |
| Point won | Score pop, banner animation, applause | |

**No hit stop and no slow motion during a rally.** `reference/hit-stop-and-time.md` describes hit
stop as a freeze of a few frames; in a game where the player times the next press against the
ball's flight, a freeze moves the ball off the beat they are reading. Keep the time-based
channels for between points.

Everything above is pooled and built once per match: no allocation per frame in the presentation
layer (`unity-profiling` → `reference/gc-per-phase.md`), and every runtime-made material and mesh
is owned by the object that made it (`unity-profiling` → `reference/runtime-asset-leaks.md`).

## 4. Prove it

- Screenshots of named moments: serve, cue half way, contact, bounce, point won, between points,
  match end, per venue and per quality tier. Read them; a ball that blends into the sky shows only
  on screen.
- The smoothness check above as a PlayMode smoke test.
- At contact, log the distance between the racket face and the planned contact point and the
  ball on screen; in the tennis game it was 0 to 8 cm.
