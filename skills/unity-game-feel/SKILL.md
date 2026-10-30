---
name: unity-game-feel
description: >-
  Make hits feel good: hit stop, flash, squash, particles, trails, pooled
  sound effects, rumble.
---

# unity-game-feel — feedback is a stack per event with a budget, not effects added until it feels right

> **Juice added effect by effect makes every event loud and none of them important.** A hit
> that sparks, flashes, shakes, freezes and thuds is right; a pickup that does the same is a hit,
> and thirty of them in one step are a wall of noise that buries the hit. Each gameplay event —
> hit, pickup, launch, land, fail — gets one row: what plays on each channel, for how many
> milliseconds, how strongly, at what priority. The row is data a person tunes; gameplay only
> names it.

## Symptom → where to look

| The report | Go to |
|---|---|
| "the hit has no impact", which channels an event gets | `reference/feedback-stack.md`, *Start here* |
| "the game stays frozen after a hit", time stuck at a low scale | `reference/hit-stop-and-time.md` |
| "the enemy stays white after it flashes", squash about the feet | `reference/flash-and-squash.md` |
| "thirty pickups play thirty sounds", voice caps | `reference/sfx-events.md` |
| "the trail streaks across the screen after respawn" | `reference/trails.md` |
| "the controller keeps vibrating" | `reference/haptics.md` |
| Particles: presets, pooling, sorting | `reference/particles.md` |
| A small fast ball that is hard to read | `reference/sports-readability.md` |

```
gameplay ──► Feedback.Play("hit", point, normal)
               │  row lookup · priority and mute · global live-row budget · player settings
               ├─ time      HitStop.Request        one owner of Time.timeScale, request queue
               ├─ motion    Tween.Squash           visual child, pivot at the feet, unscaled
               ├─ flash     RendererFlash.Flash    capture once, restore on every way out
               ├─ particles ParticleSystem.Emit    shared emitter, World space, no instantiate
               ├─ sound     SfxPlayer.Play         variance, cooldown, per-event and global voices
               ├─ shake     Feedback.ShakeRequested   ─► camera side (Cinemachine impulse)
               └─ haptic    Feedback.HapticRequested  ─► input side (gamepad motors)
```

Shake and haptics leave as static events so `Feedback.cs` compiles with neither Cinemachine nor
the Input System installed; the side that owns the device subscribes. With no subscriber the
channel is silent.

---

## Start here — the gate room

The sentry's swing lands on the runner. The combat code raises one event and nothing else.

1. **Copy the runtime files** from `resources/` into a Runtime assembly: `Feedback.cs`,
   `HitStop.cs`, `RendererFlash.cs`, `Tween.cs`, `SfxPlayer.cs`. No package is needed. Copy
   `resources/Editor/ParticlePresetBuilder.cs` into an Editor folder.
2. **Build the runner as body → Visual.** The body carries the collider and the controller; the
   `Visual` child carries the mesh or sprite, pivot at the feet, scale one. Add `RendererFlash`
   to the runner (it collects the renderers under it) and `Feedback` (it fills the courier table
   on add).
3. **Build one emitter per effect.** `Tools/Unity Dev/Feel/Build Particle Preset/Hit Spark`
   reports what it will create and waits; drop one instance in the scene and assign it to the
   hit row's particle channel.
4. **Add one `SfxPlayer`** in the boot scene, routed to the SFX mixer group, with rows named as
   the `Feedback` rows' sound channels name them.
5. **Raise the event** where the damage is applied:

```csharp
runFeedback.Play("hit", contactPoint, -contactNormal);
```

6. **Subscribe the camera and the pad** — `reference/feedback-stack.md` §2 for shake through
   `unity-camera`, `reference/haptics.md` §2 for rumble. Route pause through
   `HitStop.SetBase` (`reference/hit-stop-and-time.md` §4).
7. **Register on the probe**: `feelMuted`, `feelUnknown`, `sfxDropped`, `stopActive`.
8. **Prove the contracts** with `templates/FeelJourneyTest.cs` — its own room, driven through
   `ScriptedRunInput`: time dips and comes back (overlapping stops, a destroyed requester, a stop
   inside slow motion), flashes restore the original look, thirty pickups start at most 8 sounds.
9. **Show the gate can fail**: `FEEL_JOURNEY_BREAK=restore`, `=flash`, `=voices` each turn their
   tests red. The registration code, every test and every break:
   `reference/gate-room-feel.md`.
10. **Hand the feel to a person.** The journey proves time comes back and the voice cap holds. It
    cannot prove the hit feels heavy — a person plays, and a complaint about a row becomes a
    threshold through `unity-play-harness` → `reference/complaint-to-test.md`.

The side run, depot and sorting yard use the same files: a 2D runner flashes with `SpriteTint`
or `MaterialSwap`, squashes with `is2D` on, and plays every sound with spatial blend 0.

## Load what the situation needs

| The situation | Read |
|---|---|
| Which events get which channels; the table, the budgets, priorities and muting; reduce motion and reduce flash; auditing rows | `reference/feedback-stack.md` |
| Hit stop, slow motion, pause beside both; time stuck at a low scale; a frozen Editor after Play; per-object freeze; what runs unscaled | `reference/hit-stop-and-time.md` |
| A flash that sticks or restores the wrong colour; white on a lit material; batching cost; squash about the feet; tweens, easing, springs | `reference/flash-and-squash.md` |
| Burst presets; shared emitter or pooled instances; stop actions; simulation space; 2D sorting of particles; VFX Graph or not | `reference/particles.md` |
| Dash trail, launch streak; a streak across the screen after a respawn or pool reuse; tracers and beams with LineRenderer | `reference/trails.md` |
| A small fast ball or puck: minimum on-screen size, outline, trail; a ball that stops for a frame and jumps; hit, bounce and net feedback in a timing game; no hit stop mid-rally | `reference/sports-readability.md` · `resources/MinScreenSize.cs` · `scripts/screen_smoothness.py` |
| Named sound events, variance, cooldown, voice cap, stealing; mixer output; 2D and 3D spatial settings | `reference/sfx-events.md` |
| Gamepad rumble that ends; pause, focus loss, quit; phone vibration and its limits | `reference/haptics.md` |
| The impulse source, listener, shake budget and tiers; shake during a hit stop | `unity-camera` → `reference/shake-and-blends.md` |
| Import settings for short effects; routing every source to a mixer group | `unity-audio` → `reference/mixer-routing.md` |
| A runtime vignette pulse through a Volume profile | `unity-render-urp` → `reference/volume-templates.md` |
| A code-driven idle breathe on a single sprite | `unity-2d-sprites` → `reference/sprite-animation.md` |
| Pause as a game phase; who else writes timeScale | `unity-scene-flow` → `reference/game-state-and-pause.md` |
| Pooling one-shot effects and what release resets | `unity-scene-flow` → `reference/pooling.md` |
| Draw order of particles and trails among sprites | `unity-2d-rendering` → `reference/sort-order.md` |
| Particle overdraw and draw cost once a counter names it | `unity-scene-optimisation` → `reference/2d-draw-cost.md` |
| Where the damage event and invincibility come from | `unity-combat` → `reference/damage-contract.md` |
| Where the pickup and switch events come from | `unity-interaction` → `reference/pickups.md` |
| Generating a set of effect clips with Stable Audio 3 | `comfyui-asset-generation` |
| A feel complaint turned into a number and a before/after | `unity-play-harness` → `reference/complaint-to-test.md` |
| Jitter or churn in a squash, measured from frames | `unity-debug` → `reference/motion-and-timing.md` |
| Rumble and vibration checked on a device | `unity-device-testing` |

Copy `templates/FeelJourneyTest.cs` into a PlayMode test assembly that references the harness
(`unity-play-harness` → `resources/`), `RunInput.cs` and `ScriptedRunInput.cs`
(`unity-input` → `resources/`) and the runtime files above; it needs
`com.unity.test-framework`, no scene, no layer and no audio file.

---

## Discipline

- **Gameplay names an event; the row decides the rest.** No clip, particle system or shake
  strength at a call site. Change the row and every place the event fires changes.
- **One row per event, one event per occurrence.** A row fired every frame of a contact is thirty
  rows. Raise it on the edge — the hit, the grounded transition, the collect.
- **Budget before tuning.** 300 ms per row, three rows live, a quarter second of continuous
  freeze, eight voices. Tune inside them; raise one only with a reason written beside it.
- **Big mutes small.** Priority 0 small, 1 medium, 2 big, the same numbers in the sfx table. The
  fail plays alone.
- **One owner of `Time.timeScale`.** Hit stop, slow motion and pause all ask `HitStop`; nothing
  else writes it. The restore goes to the value before the first request, on unscaled time, and
  survives the requester being destroyed.
- **Borrow, then give back exactly.** A flash, a freeze or a squash captures once from rest and
  restores on time up, disable, destroy and pool release.
- **Scale the visual child, never the body.** Squash about the feet, keep volume.
- **Feedback timers are unscaled; gameplay timers are scaled.** The flash, the squash, the sound
  cooldown and the rumble run through a hit stop; invincibility and attack windows stop with it.
- **Every channel is skippable.** Reduce motion removes squash, shake and time dips; reduce flash
  softens and spaces flashes under three a second; shake and haptics have 0..1 sliders. The event
  still reads through what remains.
- **Rumble has an end time.** Motors are levels, not pulses; the helper stops them on time, on
  pause, on focus loss and on quit.
- **Clear trails after a teleport.** Move, then `Clear()`, on respawn, lane snap and pool get.
- **No third-party tween or feedback library.** The runner and the spring are a few hundred
  lines with no allocation; a library is a second set of clocks to keep unscaled.
- **The verdict on feel is a person's.** The journey proves the contracts; whether the hit lands
  is played, not tested.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Impulse sources, listeners, shake amplitudes and the camera's budget; camera blends | `unity-camera` |
| Audio import, load types, mixers and snapshots, music | `unity-audio` |
| Dealing damage, hit lists, invincibility, knock-back | `unity-combat` |
| Pickups, switches, gates, the interaction prompt | `unity-interaction` |
| Pause as a state, save files, the boot scene, pools | `unity-scene-flow` |
| What an enemy decides, the alert it raises | `unity-game-ai` |
| Post-processing, Volume profiles, grades | `unity-render-urp` |
| Animator graphs, clips and animation events | `unity-animation` |
| Draw order and 2D lights | `unity-2d-rendering` |
| Measuring frame cost; changing the scene to cut it | `unity-profiling`, `unity-scene-optimisation` |
| Reading the device, rebinding, the input struct | `unity-input` |
| HUD layout, colour and contrast of the interface | `unity-game-ui` |
| Generating clips and effects art | `comfyui-asset-generation`, `codex-visual` |
| The probe, situations, journeys | `unity-play-harness` |
