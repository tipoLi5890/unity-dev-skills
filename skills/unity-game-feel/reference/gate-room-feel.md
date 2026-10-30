# The gate room feel journey: probe keys, tests and breaks

> Part of the `unity-game-feel` skill (SKILL.md *Start here*, steps 7–9). What to register, what each
> journey test asserts, and the deliberate breaks that prove the gate can fail.

7. **Register on the probe**, beside the game's harness wiring:

```csharp
GameProbe.Count("feelMuted", () => runFeedback.Muted);
GameProbe.Count("feelUnknown", () => runFeedback.Unknown);
GameProbe.Count("sfxDropped", () => sfx.Dropped);
GameProbe.Register("stopActive", () => HitStop.Active);
```

8. **Prove the contracts** with `templates/FeelJourneyTest.cs`. It builds its own room —
   primitives, a silent clip, thirty pickup positions down the middle lane — and drives the
   runner through `ScriptedRunInput`:

| Test | Asserts |
|---|---|
| `Hit_DipsTime_Flashes_AndBothComeBack` | One press, one hit; time dips and is back at 1 within the stop plus 0.1 s; the flash wrote white and the property block is gone after |
| `OverlappingStops_EndWithTheLast_AndRestoreOnce` | Two stops 0.05 s apart: never back at 1 before the second ends, back at 1 after |
| `RequesterDestroyedMidStop_TimeStillComesBack` | The object that asked is destroyed mid-stop; time still comes back |
| `Stop_InsideSlowMotion_ReturnsToTheSlowMotion` | A stop inside 0.5 returns to 0.5, not to 1 |
| `OverlappingFlashes_ReturnTheOriginalLook` | Two flashes overlap; a tinted cube gets its tint back, a sprite its colour |
| `ThirtyPickups_StartNoMoreSoundsThanTheVoiceCap` | Thirty pickup events inside 0.1 s start at most 8 sounds; every request is counted |

9. **Show the gate can fail.** `FEEL_JOURNEY_BREAK=restore` (or `1`) swaps in the coroutine
   everyone writes first and turns the overlap and destroyed-requester tests red; `=flash`
   captures the colour on every call and turns the overlapping-flash test red; `=voices` raises
   the cap to 64 and turns the pickup test red. Timelines go to `$JOURNEY_OUT`; every sample
   carries `timeScale`.
