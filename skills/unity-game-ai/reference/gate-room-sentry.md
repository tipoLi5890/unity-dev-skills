# The gate room sentry, step by step

> Part of the `unity-game-ai` skill (SKILL.md §1). The starting numbers, the build, the probe keys,
> the three journey tests and the deliberate breaks.

1. **Decide the numbers** before the room exists. They are fairness, not tuning:

| Number | Start | Decides |
|---|---|---|
| Sight range · cone | 6 units · 70° | Whether the player sees the cone before it sees them; keep it inside the camera's view |
| Keep range · cone | 7.5 units · 100° | Hysteresis: a runner on the cone's edge is not seen and lost every tick |
| Decision interval | 0.1 s | Worst-case delay before anything is noticed; the cost of every sentry |
| Reaction time | 0.4 s | How long the player has to break sight after the sentry turns |
| Memory | 3 s | How long hiding takes to work |
| Patrol · chase speed | 2 · 4 (the runner is 5) | Whether a seen runner can still get away |
| Stopping distance · attack range | 1 · 1.5 | Where the chase ends and combat begins |
| Leash | 15 units from home | How far a sentry can be dragged off its post |

2. **Build the sentry.** `SentryBrain` + one mover (`NavMeshAgentMover` beside a
   `NavMeshAgent`) + a target. Cover goes on its own layer and into `blockers`; the sentry and the
   runner never sit on a cover layer. In 2D set `plane` to XY, both heights to 0, and add
   `resources/Perception2D.cs`.
3. **Register with the probe**, where the game wires its harness:

```csharp
GameProbe.Register("sentry", () => sentry.StateName);     // Patrol · Suspicious · Chase · Return
GameProbe.Register("sentryAlert", () => sentry.Alert);    // 0..1
```

4. **Prove it** with `templates/SentryJourneyTest.cs`, which builds a post, a wall and a runner
   from primitives and needs no NavMesh:

| Test | Asserts |
|---|---|
| `Sentry_DoesNotReact_OutsideTheConeOrBehindAWall` | With the runner in range behind the sentry, then behind cover, the state never leaves Patrol and alert stays 0 |
| `Sentry_NoticesWithinOneDecisionTick_AndChasesAfterItsReactionTime` | Never before the room says the runner is visible; out of Patrol within 0.1 s of it; Chase 0.4 s after, give or take a tick; closes to the stopping distance and no nearer |
| `Sentry_ReturnsToPatrol_AfterLosingTheRunnerForTheMemoryTime` | The chase is held for 3 s after the runner vanishes, not less and not more; then Return, then Patrol at the post |

5. **Show the gate can fail.** `SENTRY_JOURNEY_BREAK=los` (the cast is skipped) turns the first
   two tests red, `=cone` (360°) the first, `=memory` (30 s) the third. A journey nobody has
   seen fail proves nothing.
6. **Then add the world**: the surface and the agent (`unity-navigation`), the attack
   (`unity-combat`), the gate the sentry cannot pass (`unity-interaction`).
