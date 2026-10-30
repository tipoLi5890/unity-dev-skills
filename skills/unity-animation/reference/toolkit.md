# The files this skill ships, and where they go

> Part of the `unity-animation` skill. The Editor tools, runtime behaviours and Animation Jobs
> under `resources/`, and how to install them.

Copy `resources/AttackWindowBehaviour.cs` and `resources/FootIK.cs` into a Runtime assembly, the
four files under `resources/Editor/` into an Editor one, and the template into a PlayMode test
assembly next to the harness files.

The four job-side files (`AnimJobMath`, `FootLockJob`, `TwoBoneIKJob`, `MotionMetricsSampler`)
need only the built-in animation module.

| File | Does | Writes assets |
|---|---|---|
| `resources/Editor/AnimatorParamAudit.cs` | Parameters × graph × script text scan, as JSON | No |
| `resources/Editor/DirectionalBlendTreeBuilder.cs` | A 2D directional tree state from clips named by direction | Yes — `Report` first |
| `resources/Editor/SpriteStateGraphBuilder.cs` | Idle / run / jump / fall / hurt controller from named clips, rebuilt in place | Yes — `Report` first |
| `resources/Editor/ClipEventWriter.cs` | Adds or moves an event by normalised time; reads the clip back | Yes — report clip, function and time first |
| `resources/AttackWindowBehaviour.cs` | Open / close callbacks by normalised time, closed on any exit | — |
| `resources/FootIK.cs` | Humanoid foot planting from two raycasts | — |
| `resources/AnimJobMath.cs` | Critically damped spring, soft reach (absolute and clip-relative), C1 bump, hinge-axis and hint two-bone solvers on `AnimationStream` | — |
| `resources/FootLockJob.cs` | `IAnimationJob`: stride warp, grounding, plant lock, spring release, landing anticipation, procedural step, pelvis drop, hinge knees | — |
| `resources/TwoBoneIKJob.cs` | `IAnimationJob`: one limb onto a goal, optionally a held tool point onto it, end bone solved last | — |
| `resources/MotionMetricsSampler.cs` | Read-only test metrics: slide per plant, plant speed, root vs sim, root velocity jumps, pops, contact timing | — |
