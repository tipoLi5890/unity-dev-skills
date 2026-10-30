# Pickups — taken once, counted once, handed back to the pool

> Part of the `unity-interaction` skill. `resources/Pickup.cs`: a pickup collected by touch or by
> the interact press, a magnet that is a distance check; `resources/PickupBag.cs`: `PickupBag` as
> the smallest inventory; and what "already taken" means across a save. Worked settings: parcels along the **side run**
> and the **depot** aisles; a key in the **gate room**.

## 1. Two kinds, one component

| | Touch | Interact |
|---|---|---|
| `mode` | `PickupMode.Touch` | `PickupMode.Interact` |
| Collected when | The runner's body overlaps it, or the magnet brings it in | It is the selected target and the press lands |
| Prompt | None | "Take", through the interactor like a switch |
| Layer | `Pickup` — outside the interactor's mask | `Interactable` — inside it |
| Use for | Many, small, no decision: parcels on a run, coins, ammunition | Few, meaningful, or contested: a key, an item that fills a slot, anything beside something else usable |
| Count per level | Hundreds | Tens |

Both go through one method, `TryCollect(collector)`, which is true exactly once per life of the
pickup. Three rules sit in it:

- **The pickup decides it was taken, and sets `Taken` before it tells anyone.** A runner built
  from two colliders raises two `OnTriggerEnter` calls in one step; the second finds `Taken`
  and returns. A handler on the runner that counts in its own callback counts twice.
- **A sensor is not a body.** The trigger callbacks return at once when the other collider is
  a trigger. An interactor's reach circle, a magnet field and a sentry's vision cone all touch
  the pickup long before the runner does; none of them collects it.
- **The collector is found by interface.** `GetComponentInParent<IPickupReceiver>()` on the
  body that touched it. A sentry, a crate and a projectile have no receiver and pass through.

The trigger pair needs what every trigger pair needs — a body on one side and the layer pair
enabled: `unity-physics-2d` → `reference/layers-and-matrix.md`, and `unity-physics-3d` §1 for
the 3D ladder. The runner carries the body; the pickup is a trigger collider with none.

## 2. The magnet is a distance check

```
magnetRadius 0     off; at 1.5 the nearest PickupBag inside it starts the pull
magnetSpeed  12    units/s, and it never lets go once it has started
collectRadius 0.3  inside this it is collected — no trigger involved
```

- **No second collider.** A large trigger around every pickup is one more pair for the physics
  step per pickup and collects through walls. `PickupBag.Nearest` walks a static list of
  enabled bags; with one runner that is one subtraction per pickup per frame.
- **Faster than the runner, by at least 2×.** At 12 against a run speed of 5 the pickup closes
  1.5 units in about 0.2 s. At equal speed it trails behind for ever.
- **It does not let go.** A pickup that drops back at the rim reads as a miss. The exception
  is a refused pickup — a full bag — which stops chasing.
- **`magnetRadius` 0 is off**, the default: a touch pickup with no magnet is collected by its
  trigger alone. Raise it to 1.5 for a lane run, where the runner cannot steer onto every
  parcel, and treat a larger radius as an upgrade the player earns.
- **Hundreds of magnetised pickups** want the check on a tick or a spatial grid, not per frame
  each; measure first — `unity-profiling`.

## 3. Back to the pool, never destroyed

```csharp
// The pool, when it spawns one:
pickup.Release = p => pool.Return(p);          // PickupObjectPool is the game's
```

`Pickup` calls `Release` when it is taken, and with nothing assigned it deactivates itself. It
never calls `Destroy`: a run that collects forty parcels a minute would allocate and collect
garbage on every one.

| On reuse | Who resets it |
|---|---|
| `Taken`, the magnet's target | `Pickup.OnEnable` |
| Position, parent, item id | The pool, before `SetActive(true)` |
| Trail, particle and animation state | Whoever owns each — `unity-scene-flow` → `reference/pooling.md` |
| `Release` | Assigned once, when the pool creates the instance |

- A pickup deactivated while inside the interactor's sensor is pruned from its list on the next
  scan; nothing has to tell the interactor.
- A `Physics2D.IgnoreCollision` pair binds two instances and rides along into the pickup's next
  life: set it on spawn and clear it on return — `unity-physics-2d` →
  `reference/layers-and-matrix.md`.
- Building the pool itself — warm-up size, growth, what a returned object must forget:
  `unity-scene-flow` → `reference/pooling.md`.

## 4. Counting

```csharp
Pickup.Collected += (pickup, collector) => score.Add(pickup.itemId, pickup.amount);   // one place
GameProbe.Count("parcels", () => bag.CountOf("parcel"));
```

| Signal | Raised | For |
|---|---|---|
| `Pickup.Collected` (static) | Once per collection, after the bag accepted it | Score, objectives, sound, the save |
| `PickupBag.Changed(itemId, count)` | When a count changes, for any reason | The HUD counter — redraw on the event |
| `InteractableBase.onInteracted` | Interact mode only | The object's own effect |

- **The bag is the count.** A HUD that keeps its own integer and increments it on a sound
  event drifts the first time a pickup is refused or restored from a save.
- **A journey asserts the number, not the feeling:** drive the run past five parcels and
  assert `CountOf("parcel") == 5` at the end and that it never decreases —
  `unity-play-harness` → `reference/journeys.md`.
- **The sound and the pop** subscribe to `Collected` and are pooled like the pickup —
  `unity-game-feel` → `reference/feedback-stack.md`.
- Statics are cleared on `SubsystemRegistration`, so a second play session with domain reload
  off starts with no stale subscribers.

## 5. An inventory, in brief

Items are data. The pickup carries an id; what the id means lives in an asset:

```csharp
[CreateAssetMenu(menuName = "Courier/Item")]
public class ItemDefinition : ScriptableObject
{
    public string id;            // "parcel", "gate-key" — the only thing a save stores
    public string displayKey;    // string-table key
    public Sprite icon;
    public int stackLimit = 99;
}
```

| Layer | Holds | In this skill |
|---|---|---|
| Definitions | What an item is: name, icon, stack limit | The sketch above — `unity-scene-flow` → `reference/scriptable-objects.md` |
| State | How many of each the runner has | `PickupBag`: a dictionary from id to count |
| View | The HUD counter, the bag screen | Listens to `Changed` — `unity-game-ui` |

`PickupBag` implements two interfaces, and nothing else in the game names the class:

| Interface | Asked by | Methods |
|---|---|---|
| `IPickupReceiver` | `Pickup` | `Receive(itemId, amount)` — `false` refuses, and the pickup stays in the world |
| `IKeyHolder` | `GateSwitch` | `HasKey(id)`, `UseKey(id)` |

A real inventory — slots, weight, equipment — replaces `PickupBag` and keeps the two
interfaces. `capacityPerItem` (0 is no limit) is the one limit the bag enforces; a full bag
refuses the pickup, which is why `TryCollect` asks before it marks itself taken. Dragging items
between slots is UI — `unity-ui-toolkit` → `reference/manipulators-and-drag-drop.md`.

## 6. Already taken

Two kinds of pickup, and only one is saved:

| Kind | `saveId` | After a reload |
|---|---|---|
| Respawning: parcels on a run, ammunition | Empty | Present again |
| Unique: a key, a collectable | A stable string, unique in the game | Absent if it was taken |

```csharp
// Where the game wires its save:
Pickup.AlreadyTaken = id => save.taken.Contains(id);
Pickup.Collected += (pickup, _) => { if (pickup.saveId != "") save.taken.Add(pickup.saveId); };
```

- **The id is authored, not derived.** `GetInstanceID`, the object's name and its position all
  change between sessions or edits. Type the id, or generate a GUID in the editor once and
  serialise it.
- **The pickup removes itself in `Start`**, not `OnEnable`: an object cannot deactivate itself
  while it is being activated. It leaves through `Release` with no `Collected` event — nothing
  was collected this session.
- **The bag is saved separately**, as id and count pairs from `PickupBag.Items`, and restored
  through `Set`. The world's "taken" set and the bag's contents are two facts: a key that was
  picked up and spent is taken and not carried.
- **Assign `AlreadyTaken` before the level's pickups start**, in the bootstrap —
  `unity-scene-flow` → `reference/bootstrap.md`.
- The file, its versioning and when to write it: `unity-scene-flow` → `reference/save-format.md`.

## Checks

- Give the runner a second solid collider and walk through one parcel: the bag reads 1.
- Add an `Interactor2D` sensor of radius 2 to the runner: a touch parcel 1.5 units away stays
  on the floor until the body reaches it.
- Fill the bag to `capacityPerItem` and touch another: it stays in the world, `Taken` false.
- Collect forty parcels with the Profiler's GC Alloc column visible: no allocation on the
  frames a parcel is taken.
- Take a key with a `saveId`, save, reload the level: the key is absent and the bag has it.
- Search for `Destroy(` in pickup code and for `count++` in HUD code: both are the bugs above.
