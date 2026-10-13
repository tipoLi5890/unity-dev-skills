# The feedback stack — one row per event, a budget per row and for the game

> Part of the `unity-game-feel` skill. The table that decides what each gameplay event shows,
> sounds and shakes; the component that plays a row; the budget and priority rules that keep a
> burst of small events from drowning a big one; and the two player settings every channel
> honours.

Feedback written as code at the call site ("on hit: spawn sparks, play clip, shake 0.4, freeze")
grows one effect at a time until every event is loud, nothing is louder than anything else, and
nobody can say what a hit costs. Written as a table it can be read, summed and argued over.

## 1. The table

Rows are events, columns are channels. Every cell is a number a designer changes in the
inspector; gameplay names the row and nothing else.

| Channel | What it does | Unit | Goes out through |
|---|---|---|---|
| motion | Squash or stretch of the visual child, eased back | height factor, ms | `Tween.Squash` |
| flash | The renderers turn one colour and come back | colour, ms | `RendererFlash.Flash` |
| particles | A burst at the event's position, along its direction | count | `ParticleSystem.Emit` on a shared emitter |
| shake | A camera impulse | 0..1 of the camera's shake budget | `Feedback.ShakeRequested` — the camera side subscribes |
| sound | A named event in the sfx table | event name | `SfxPlayer.Play` |
| haptic | Gamepad motors | low 0..1, high 0..1, ms | `Feedback.HapticRequested` — the input side subscribes |
| time | Hit stop or slow motion | scale, ms | `HitStop.Request` |

The courier run's table — `Feedback.DefaultRows()`, what `resources/Feedback.cs` fills in when
the component is added:

| Event | Priority | Mutes lower for | Motion | Flash | Particles | Shake | Sound | Haptic low/high, ms | Time |
|---|---|---|---|---|---|---|---|---|---|
| pickup | 0 | — | 1.15, 100 ms | — | 6 | — | pickup | — | — |
| land | 1 | — | 0.8, 120 ms | — | 8 | 0.3 | land | 0.3 / 0, 60 | — |
| hit | 1 | 100 ms | 0.85, 100 ms | white, 80 ms | 12 | 0.6 | hit | 0.6 / 0.3, 120 | 0.05 for 80 ms |
| launch | 2 | 150 ms | 1.25, 150 ms | — | 20 | 0.6 | launch | 0.5 / 0.5, 150 | — |
| fail | 2 | 300 ms | — | red, 120 ms | 24 | 1.0 | fail | 1 / 1, 250 | 0.05 for 120 ms |

Read it as a set of claims: a pickup is a third of a hit; a hit is the only thing that stops time
for a step it did not end; the fail is the loudest row in the game and nothing else plays on top
of it for 300 ms. Change a claim and every place the event fires changes with it.

Shake strengths are the camera's three tiers — light 0.3, medium 0.6, heavy 1.0 — so a row picks
a tier, never an amplitude. The amplitude, the duration and the overlap rule of the impulse live
on the camera side: `unity-camera` → `reference/shake-and-blends.md`.

## 2. Playing a row

```csharp
// gameplay: the sentry's attack landed on the runner
feedback.Play("hit", contactPoint, -contactNormal);

// gameplay: the runner touched a pickup
feedback.Play("pickup");
```

`Play` returns `false` when the row was muted, over the global budget or unknown, and counts
each in `Muted` and `Unknown`. A non-zero `Unknown` is a typo between the gameplay string and the
row id — put it on the probe:

```csharp
GameProbe.Count("feelMuted", () => runFeedback.Muted);
GameProbe.Count("feelUnknown", () => runFeedback.Unknown);
```

Rules for the channels' targets:

- **The motion target is a child that only draws.** Scaling the object that carries the
  collider changes what the runner stands on. Build the runner as body (collider, rigidbody,
  controller) → `Visual` (mesh or sprite, pivot at the feet). Its rest scale is `Vector3.one`.
- **Particles come from one emitter per effect, moved to the event.** `Emit(count)` on a
  shared system in World simulation space costs no instantiate and no pool —
  `reference/particles.md`.
- **A channel with no target is skipped, not an error.** The default rows play as far as they
  are wired, so the table can be filled before the art exists.

### The shake subscriber

`Feedback.cs` names no camera type. The camera side turns `ShakeRequested(position, direction,
strength)` into an impulse; the source's shape, duration and channel are set on the camera side
as `unity-camera` → `reference/shake-and-blends.md` lays out.

```csharp
// FeedbackShake.cs — the camera side of Feedback.ShakeRequested. On the camera rig, beside the
// CinemachineImpulseSource it fires. REQUIRES com.unity.cinemachine
using UnityEngine;
using Unity.Cinemachine;                 // Cinemachine 2.x: using Cinemachine;

public sealed class FeedbackShake : MonoBehaviour
{
    [SerializeField] CinemachineImpulseSource source;

    void OnEnable()
    {
        Feedback.ShakeRequested += Shake;
        // A shake started by a hit plays through the hit stop instead of freezing with it.
        CinemachineImpulseManager.Instance.IgnoreTimeScale = true;
    }

    void OnDisable() => Feedback.ShakeRequested -= Shake;

    void Shake(Vector3 position, Vector3 direction, float strength)
    {
        Vector3 v = (direction.sqrMagnitude > 0f ? direction : Vector3.down) * strength;
        source.GenerateImpulseAtPositionWithVelocity(position, v);
    }
}
```

The haptic subscriber is the same shape on the input side: `reference/haptics.md` §2.

Who raises which event is the gameplay owner's: the hit comes from the damage receiver
(`unity-combat` → `reference/damage-contract.md`), the pickup from the interactable
(`unity-interaction` → `reference/pickups.md`), the landing from the controller's grounded
edge. They raise it once per event; a row fired every frame of a contact is thirty rows.

## 3. Budgets

Two numbers, both on `Feedback`, both checked:

| Budget | Default | Rule |
|---|---|---|
| `eventBudgetMs` | 300 | No row's longest channel runs longer. `Audit()` and `OnValidate` report a row over it |
| `globalLiveRows` | 3 | Rows live at once across every `Feedback` in the game. A fourth plays only by displacing a live row of strictly lower priority |

A row's length is its longest timed channel (motion, flash, haptic, time). A row with only sound
and particles occupies no slot: it cannot crowd anything out, and the sfx voice cap limits it
instead (`reference/sfx-events.md`).

Two more limits sit in the owners, because they hold across rows:

- **Time:** `HitStop.maxContinuousSeconds` 0.25 — thirty hits in a row freeze the game a quarter
  of a second, not thirty times as long — and a 50 ms cooldown after each stop
  (`reference/hit-stop-and-time.md`).
- **Shake:** the impulse listener's overlap rule (`UseLargest`), on the camera side.

`Audit()` also flags any row whose time channel freezes (scale under 0.2) for more than 150 ms:
past that a stop reads as a hang. Run it over every prefab that carries a `Feedback` before a
playtest:

```csharp
foreach (var f in Object.FindObjectsByType<Feedback>(FindObjectsSortMode.None))
{
    string problems = f.Audit();
    if (problems.Length > 0) Debug.LogWarning("[FEEDBACK] " + f.name + "\n" + problems);
}
```

## 4. Priorities — a big event mutes small ones

Three priorities, named by what they are: 0 small (pickup, footstep), 1 medium (hit, land),
2 big (gate, launch, fail). A row with `muteLowerMs` above zero refuses every row of lower
priority for that long. The fail mutes for 300 ms, so the pickups the runner sweeps through as it
dies are silent and the fail is heard alone.

Equal priorities do not mute each other: two hits in one step both play, and the hit stop owner
merges their time channels into one stop.

The same three numbers are the sfx table's `priority` field, so a full voice pool steals a pickup
voice for a hit and never the other way round. Keep them aligned: one priority per event, in both
tables.

## 5. Settings the player owns

`FeelSettings` holds four values every channel reads. They are not optional to honour, and the
menu that sets them is the game's.

| Setting | Default | Effect |
|---|---|---|
| `reduceMotion` | off | No squash, no shake, no time dip. Particles halve. Sound, flash and haptics still play, so the event still reads |
| `reduceFlash` | off | Every flash blends 35 % of the way to its colour (`ReducedFlashStrength`) and no flash starts within 1/3 s of the last (`ReducedFlashInterval`) — under three a second |
| `shake` | 1 | 0..1, multiplied into every shake strength. The camera side multiplies it into the listener gain too |
| `haptics` | 1 | 0..1, multiplied into both motor speeds. 0 is off |

Three a second is the ceiling for large-area flashing that photosensitivity guidance names; a
hit flash on one character is small, a red full-screen fail flash is not. A full-screen flash —
a vignette pulse through a Volume — follows the same rule: `unity-render-urp` →
`reference/volume-templates.md` for the runtime vignette tween, and skip it entirely under
`reduceFlash`.

Persist the four values with the game's other settings — a file of the device's, separate from
the playthrough save (`unity-scene-flow` → `reference/save-format.md` §2) — and apply them in the
boot scene before the first row plays.

## 6. Proving it, and what stays with a person

The journey (`templates/FeelJourneyTest.cs`) proves the parts that are contracts: time comes
back, the flash gives the look back, thirty pickups make no more sounds than the cap. It does
not prove the hit feels heavy. A feel complaint about a row — "the hit has no weight" — becomes a
situation, a quantity and a threshold the way `unity-play-harness` →
`reference/complaint-to-test.md` lays out; the quantity is a cell in this table, and the
before/after is the row before and after. Whether the new row is the feel that was meant is
the person's answer.

Change one cell at a time. Two cells changed and a better hit is credited to whichever one was
already believed.
