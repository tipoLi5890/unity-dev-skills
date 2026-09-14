# NavMeshAgent API: what the calls return, the names that do not exist, the defaults

Part of the `unity-navigation` skill. SKILL.md §2 and §3 state the rules; this file holds the
tables behind them.

## 1. What `NavMesh.CalculatePath` returns

Against two deliberately disconnected islands and a target with no NavMesh near it:

| Case | returned | status | corners |
|---|---|---|---|
| Reachable | `True` | `PathComplete` | 2 |
| Disconnected island | **`True`** | `PathPartial` | 2 |
| Nothing near the target | `False` | `PathInvalid` | 0 |

## 2. Names people reach for

| Reach for | Actually is | Status |
|---|---|---|
| `agent.target` | `agent.destination` | `target` **absent** |
| `agent.navMeshPath` | `agent.path` | `navMeshPath` **absent** |
| `path.waypoints` | `path.corners` | `waypoints` **absent** |
| `NavMesh.Bake()` | `NavMeshSurface.BuildNavMesh()`, from `com.unity.ai.navigation` | `Bake` **absent** |
| `link.costOverride` | `link.costModifier` | present but `[Obsolete]` → `costModifier` |
| `agent.Stop()` / `agent.Resume()` | `agent.isStopped = true / false` | **present**, but `[Obsolete]` — see below |

> **`Stop()` and `Resume()` still exist**, carrying `[Obsolete("Set isStopped to true instead.")]`.
> Code using them compiles with a warning rather than failing, which is why it survives in
> projects for years. `Move(Vector3)` is **not** obsolete and is **not** a teleport — it applies a
> relative motion; `Warp(Vector3)` is the teleport.

> **`agent.velocity` is read-write and not deprecated** — that it is read-only is a common
> belief, and it is wrong. The three are different things, not one right answer:
> **`velocity`** read gives actual post-avoidance velocity and write overrides steering for that
> frame; **`desiredVelocity`** is read-only and is the intended, pre-avoidance direction;
> **`speed`** is the maximum steering will use. Feed animation from `velocity`, lean and turn from
> `desiredVelocity`, and tune movement with `speed`.

`NavMesh.AllAreas` is a `const int` equal to `-1`, not a property — it will not show up if you
enumerate properties looking for it.

## 3. Defaults on a freshly added `NavMeshAgent`

Worth knowing before you "tune" anything:

| | | | |
|---|---|---|---|
| `speed` 3.5 | `angularSpeed` 120 | `acceleration` 8 | `stoppingDistance` **0** |
| `autoBraking` true | `radius` 0.5 | `height` 2 | `autoTraverseOffMeshLink` true |
| `updatePosition` true | `updateRotation` true | | |

A `stoppingDistance` of zero is why "jitter at the destination" is the common case, not the
unusual one (SKILL.md §3).

## 4. Links: the component to author with, and crossing one by hand

**`OffMeshLink` is the legacy component.** It still exists and still works, which is why it keeps
turning up in older scenes and in older sample code — but the one to author with is
**`NavMeshLink`** from `com.unity.ai.navigation`, which adds width, transform-relative endpoints
and runtime updates. Migrate an `OffMeshLink` you find rather than adding a second one beside it.

The runtime API kept the old name either way: the agent members are `isOnOffMeshLink`,
`currentOffMeshLinkData` and `CompleteOffMeshLink()` regardless of which component created the
link, so `OffMeshLink` in code is not evidence that the scene uses the legacy component.

With `autoTraverseOffMeshLink` off, the crossing is four steps and the last one is the one people
drop:

1. Detect `agent.isOnOffMeshLink`.
2. Read `agent.currentOffMeshLinkData` for `startPos` and `endPos`.
3. Play or lerp the traversal yourself — the jump, the ladder climb, the vault over a gate.
4. Call `agent.CompleteOffMeshLink()`. Without it the agent never leaves the link, and the report
   arrives as "it freezes at the gate", not as a link problem.
