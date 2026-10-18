# A broadcast camera for a court or pitch sport

> Part of the `unity-camera` skill. A raised view from behind one end of a court that follows the
> player gently, keeps the whole court readable, and adds a few deliberate moves between points
> and at the end of a match. Worked setting: a tennis game, one full-screen camera solo and two
> side-by-side cameras in split screen. Plain `Camera` transforms driven from `LateUpdate`, no
> Cinemachine; the same moves translate to a `CinemachineCamera` with a custom extension.

## 1. Framing comes from the HUD, not from taste

The court must stay inside the space the HUD leaves. Decide the framing by projecting the court's
key points with the real camera at the target resolution and comparing them with the HUD's
rectangles, then confirm on a screenshot. In the tennis game at 1920 × 1080: the far player's name
tag sits below the score box (y ≈ 205 px), the near player's feet 2.6 m behind the baseline sit
above the timing bar (y ≈ 905 px), and the near singles sideline corner sits right of the
bottom-left legend (x ≈ 500 px).

| | Position (behind the near baseline) | Looks at | Vertical FOV |
|---|---|---|---|
| Solo, full screen | (0, 6.5, −28): about 16 m back, 6.5 m up | (0, 0, −3.9) | 31° |
| Split screen, each 960-wide half | (0, 8.5, −26.5): about 14.6 m back, 8.5 m up | (0, 0, −5.2) | 36° |

The other team's camera is the same pose rotated 180° about the court centre. A narrow lens from
far back keeps the far baseline large enough to read, at the price of some depth compression; a
half-width viewport needs a higher, wider view to keep both sidelines in.

## 2. Follow your own player, damped

```
focus target  = clamp(0.7 × own player x + 0.3 × ball x, ±3 m)    // rally, ball live
              = clamp(own player x, ±3 m)                          // otherwise
              = 0                                                  // between points
camera x      = base x + focus × 0.3      (split 0.35)
look-at x     = base x + focus × 0.5      (split 0.75)
focus         = SmoothDamp(focus, target, ref vel, 0.75 s)         (split 0.6 s, ×1.6 between points)
```

- **Follow the player, not the ball.** A camera that chases the ball swings on every shot and the
  player loses their own position. A 30% share of the ball leans the frame toward play without
  the swing.
- **Pan the look-at point more than the camera.** The view turns slightly toward the action and
  the court's perspective barely changes, so the court lines never slide.
- **Critically damped, never a lerp by a fraction per frame.** `Mathf.SmoothDamp` with an explicit
  `deltaTime` has no overshoot and is frame-rate independent; `Lerp(a, b, 0.1f)` per frame is
  neither.
- **Unscaled time, clamped:** `dt = paused ? 0 : min(Time.unscaledDeltaTime, 0.1f)`. The match clock
  ignores `timeScale`, so the camera does too, and a long editor frame does not throw it.

## 3. Moves between points and at the end

| Moment | Move | Numbers |
|---|---|---|
| Between points | Focus returns to centre; push in along the view and drop slightly | 1.2 m in, 0.3 m down, `SmoothDamp` 0.9 s; back out when the next point starts |
| Match end, own team won | Swing to in front of the winner, looking back at them | Winner + 7 m forward + 1.8 m to the side + 2.4 m up, look at 1.9 m, FOV 34°, `SmoothDamp` 0.55 s with a smoothstep blend |
| Match end, other team won | Push toward the net and look across at the winner | FOV 22° |
| A smash | A small downward kick | Velocity impulse 0.9 × strength m/s into an under-damped spring (ω 22, ζ 0.55): about 4 cm down, settled within 0.3 s |

- **Frame the close-up for the banner.** The "winner" banner sits at 30–48% of screen height, so
  the close-up puts the winner's head at about 51% and feet at about 92%.
- **Reopen what the camera normally culls.** Each camera's mask leaves out the scenery behind it
  (`unity-scene-optimisation` → `reference/culling-distances.md`). The end swing turns the camera
  round to face that scenery, so add the bit back while the close-up is on, and only once the
  camera is in front of the windscreen, so the fence does not fill the lens. Restore the saved mask
  after.

## 4. No hit stop, no slow motion during play

A timing game keeps the world moving at the speed of the clock the player is timing against. A
hit stop or a slow-motion replay mid-rally moves the ball off the beat the player is reading. The
tennis game's only rally-time camera effect is the 4 cm smash kick; slow motion, if anywhere,
belongs after the point is over. `unity-game-feel` → `reference/sports-readability.md` has the
rest of the feedback that replaced it.

## 5. Split screen

- Two cameras with `rect` viewports, each with its own culling mask: its own seat's world markers
  on a per-seat layer, the other seat's layer off, its own back scenery off.
- Shadows render once per camera; switch them off per camera on lower tiers
  (`unity-lighting` → `reference/shadows.md`).
- One `AudioListener` for the app, never one per camera (`unity-audio`).
- Size anything kept at a minimum screen size against the camera's own viewport height
  (`camera.rect.height`), not the full screen.

## 6. Prove it

- Screenshots of named situations: serve, mid-rally, contact, bounce, between points, match end
  in each venue and in split screen, read one by one.
- A smoothness measure for the camera path and the player on screen, the same median test as for
  the ball (`unity-game-feel` → `reference/sports-readability.md` §2).
