# Checkpoints — a small save, and a respawn that rebuilds instead of reloading

> Part of the `unity-scene-flow` skill. A checkpoint uses the same `SaveData` as the file on
> disk (`reference/save-format.md`); a respawn puts the level back to those facts without
> unloading it. Worked setting: the **gate room** — a checkpoint at the switch, a sentry that
> sends the runner back to it.

## 1. A checkpoint is a save taken at a known-good moment

There is one save in memory — the *current* one, which play mutates — and one copy of it taken
at the last checkpoint.

```
current ──(runner reaches the checkpoint)──► snapshot = current.Clone()  ──► SaveStore.Write
   ▲                                                      │
   └──────────(runner is caught: respawn)─────────────────┘   current = snapshot.Clone()
```

```csharp
public sealed class Checkpoints
{
    readonly SaveStore _store;
    public SaveData Current { get; private set; } = new SaveData();
    SaveData _snapshot = new SaveData();

    public Checkpoints(SaveStore store) { _store = store; }

    public void Begin(SaveData loaded)                 // from the file, or a new game
    {
        Current = loaded;
        _snapshot = loaded.Clone();
    }

    public void Reach(string checkpointId, Vector3 position, int lane, long unixSeconds)
    {
        if (Current.player.checkpoint == checkpointId) return;      // standing in it is not reaching it
        Current.player.checkpoint = checkpointId;
        Current.player.position = position;
        Current.player.lane = lane;
        _snapshot = Current.Clone();
        _store.Write(_snapshot, unixSeconds);
    }

    public SaveData Rewind()                           // what a respawn applies
    {
        Current = _snapshot.Clone();
        return Current;
    }
}
```

Provide it once, beside the pool the respawn uses —
`Bootstrap.WhenReady(boot => { boot.Services.Provide(new Checkpoints(boot.Saves)); boot.Services.Provide(pool); });`
— then three rules:

- **The snapshot is a copy.** `_snapshot = Current` shares the flag list, and the next pickup
  taken edits the checkpoint.
- **Facts change in `Current` at the moment they happen** — the pickup sets its flag when it is
  collected, not when the next checkpoint is reached. The checkpoint only copies.
- **Take it at a moment that is safe to return to**: the runner grounded, not seen, not inside
  a hazard, the phase `Playing`. A checkpoint taken one step before an unavoidable catch is a
  loop the player cannot leave. The checkpoint object checks; the trigger alone does not.

The position stored is the checkpoint's own spawn point, never the runner's position when it
touched the trigger: the first is authored to be safe, the second is wherever the edge of the
collider was.

## 2. Respawn by rebuilding

Reloading the scene to respawn pays the whole load — seconds, a loading screen, every `Awake` —
to undo a few changes the game already has a list of. Rebuild when the changes can be listed:

```csharp
public interface IResettable
{
    /// <summary>Put this object where the save says it is. Called on arrival and on every respawn.</summary>
    void ResetTo(SaveData save);
}
```

```csharp
// On the level's root. Collects once; the same pass runs after a load and after a catch.
public sealed class RoomState : MonoBehaviour
{
    readonly List<IResettable> _parts = new List<IResettable>();

    void Awake() => GetComponentsInChildren(true, _parts);

    public void Apply(SaveData save)
    {
        Bootstrap.Get<PickupObjectPool>().DespawnAll();          // everything transient goes back first
        foreach (IResettable part in _parts) part.ResetTo(save);
    }
}
```

```csharp
// The gate: open when its flag says so.
public void ResetTo(SaveData save)
{
    StopAllCoroutines();                                    // an opening in progress belongs to the old run
    bool open = save.HasFlag(GetComponent<PersistentId>().Id);
    leaf.localRotation = open ? openRotation : closedRotation;
    blocker.enabled = !open;
}
```

The respawn itself, in the object that owns the catch:

```csharp
void Respawn()
{
    GameState state = Bootstrap.Get<GameState>();
    if (!state.TryGo(GamePhase.Loading)) return;            // Lost → Loading; refused from anywhere odd
    SaveData save = Bootstrap.Get<Checkpoints>().Rewind();
    room.Apply(save);                                       // gate, switch, sentry, pickups
    runner.Teleport(save.player.position, save.player.lane);
    input.ClearPresses();                                   // the press that confirmed "retry"
    state.TryGo(GamePhase.Playing);                         // on the next frame when a fade covers it
}
```

It goes through `Loading` even though nothing loads: the phase table has one way into
`Playing`, and everything that listens for it — the HUD, the music, the probe — sees a respawn
and a fresh arrival as the same event. `RoomState.Apply` after `SceneLoader.Loaded` and after a
catch is one code path, so a load from the menu and a respawn cannot disagree.

**Reload the scene instead** when the changes cannot be listed: breakable geometry scattered by
physics, a level edited at runtime, a third-party system with no reset. Then it is
`Bootstrap.Instance.LoadContent(save.scene)` and the same `Apply` on arrival.

## 3. What resets and what persists

| Resets to the checkpoint | Persists through a respawn |
|---|---|
| The runner's position, lane, velocity, facing, health | Anything flagged before the checkpoint: pickups taken, gates opened |
| Sentries: position, patrol index, alert level, cooldowns | Pooled instances themselves (`reference/pooling.md`) |
| Pickups taken, switches thrown and gates opened **since** the checkpoint | Music position — a respawn is not a new track |
| Hazard timers and moving platforms: back to phase 0, so the room is the same puzzle | Settings, bindings, accessibility options |
| Projectiles, effects, trails: despawned | Session counters — attempts, play time — kept outside the save's flags |
| Coroutines, `Invoke`s and tweens on level objects: stopped | The camera rig, told it was a cut (§4) |
| Pending input presses | The Boot scene, whole |

Three that are routinely missed:

- **Timers.** A hazard on a cycle that keeps its phase across a respawn puts the runner back into
  a different room each time. Reset the phase, or derive it from time since the respawn.
- **Coroutines.** A gate half-way through opening finishes after the reset has closed it.
  `StopAllCoroutines()` first in every `ResetTo`.
- **Counters that should not reset.** Attempts and play time live in their own object in Boot.
  Put them in `flags` and the respawn rewinds them.

## 4. The teleport, and telling the camera

A respawn moves the runner further in one frame than it moves in a second of play. Each system
that smooths motion has to be told it was a cut, or it draws the sweep.

| System | A teleport done wrong | Done right |
|---|---|---|
| `Rigidbody`, interpolated | `MovePosition` — drawn as a sweep through the level | Assign `body.position`, zero `linearVelocity` and `angularVelocity` |
| `CharacterController` | Setting `transform.position` is overwritten by the controller's own state | Disable the controller, set the position, enable it |
| A kinematic motor | Writing the transform leaves the motor's cached ground and velocity | The motor's own teleport method, then reset its motion |
| Triggers the runner was standing in | No exit is raised at the old place until physics runs | `Physics.SyncTransforms()` after the move when something is queried in the same frame |
| Trails and particles on the runner | A streak across the room | `TrailRenderer.Clear()`; stop and clear particle systems |
| The follow camera | Damping pans across the level to catch up | Tell it the target warped — the calls are in `unity-camera` → `reference/update-order-and-jitter.md` |

The camera row is the one players notice. In a timeline it reads as one sample with a very
large camera offset followed by a long decay: a missing cut, not jitter.

A fade covers all of it when one is wanted: phase to `Loading`, fade out on unscaled time,
`Apply` and teleport while black, fade in, phase to `Playing`.

## 5. Applying a save to a scene that just loaded

The same pass, entered from the other side:

```csharp
Bootstrap.WhenReady(boot => boot.Loader.Loaded += scene =>
{
    SaveData save = boot.Services.Get<Checkpoints>().Current;
    foreach (GameObject root in scene.GetRootGameObjects())
    {
        var room = root.GetComponent<RoomState>();
        if (room != null) room.Apply(save);
    }
});
```

`Loaded` is raised after the level's `Awake` and `OnEnable`, so every `PersistentId` has
registered and every `IResettable` exists. Whether the level's `Start` has run by then depends
on the path — after `SceneLoader.Load` it has, after `Adopt` it has not — so a level object must
be correct for *any* flag value after `ResetTo`, and must not decide its own state in `Start`:
in one order the save overwrites it, in the other it overwrites the save.

Objects the level does not contain but the save implies — a pickup dropped by a sentry — are
spawned by the pass from the pool, each with the id its flag carries
(`PooledPickup.Id`, or `PersistentId.Assign` on a pooled object that has the component).

## 6. Checks

- **Respawn twice from the same checkpoint and compare.** Position, flags and the count of live
  pickups after the second respawn equal those after the first. A difference is state that
  `ResetTo` missed.
- **Nothing is created by a respawn.** `PickupObjectPool.Created` is flat across it — the journey
  asserts this for a whole level change (`templates/SceneFlowJourneyTest.cs`).
- **Kill the process after a checkpoint, start again.** The game arrives at that checkpoint.
  `python3 scripts/save_check.py <save>` passes on the file it left.
- **The phase order in the timeline** is `… Playing, Lost, Loading, Playing …` and
  `refusals` did not move.
- A checkpoint as a named moment a test can boot into → `unity-play-harness` →
  `reference/situations.md`. Its `Enter` calls `Checkpoints.Begin` with a hand-built save, then
  the same `Apply`: a situation that pokes fields instead tests a state the game cannot reach.
