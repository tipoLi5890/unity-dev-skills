# ScriptableObjects — configuration that is read, and the mutation that only the Editor keeps

> Part of the `unity-scene-flow` skill. A ScriptableObject is an asset: one instance, shared by
> everything that references it, in every scene. That makes it the right home for configuration
> and a deceptive one for state. Worked setting: the **lane run** — lane spacing, run speed,
> pickup definitions.

## 1. The trap, first

> **A value changed on a ScriptableObject asset at runtime survives Play mode in the Editor and
> does not survive a restart in a build.** In the Editor the change is made to the loaded asset;
> depending on what else touches it, it is written to disk and committed with the next push. In a
> player the asset is read-only data: the change lasts until the object is unloaded or the
> process ends, and is gone on the next launch.

So "the upgrade is stored on the asset" works for every session of development and for no
player. Three symptoms, one cause:

| Symptom | What happened |
|---|---|
| "Progress saves in the Editor, resets in the build" | State was written to an asset and never to the save file |
| "The run speed is 14 after I stop Play; it was 8" | A power-up multiplied a field on the config asset |
| "The second level starts with the first level's score" | Runtime state on an asset is shared by every scene and survives a scene load — and, with domain reload off, the next Play |

The rule that removes all three: **an asset's serialised fields are written by people, in the
Inspector, and by nothing at runtime.**

```bash
# Every assignment to a field of something that looks like config. Each hit is a question.
grep -rnE "(config|settings|definition|data)\.[A-Za-z_]+ *(=|\+=|-=|\*=|\+\+|--)[^=]" Assets --include='*.cs' -i
```

## 2. Read-only configuration

```csharp
[CreateAssetMenu(menuName = "Courier/Run Config", fileName = "RunConfig")]
public sealed class RunConfig : ScriptableObject
{
    [SerializeField] float laneSpacing = 1.3f;
    [SerializeField] float runSpeed = 8f;
    [SerializeField] int laneCount = 3;

    public float LaneSpacing => laneSpacing;       // no setter anywhere
    public float RunSpeed => runSpeed;
    public int LaneCount => laneCount;

    public float LaneX(int lane) => (lane - (laneCount - 1) * 0.5f) * laneSpacing;   // middle lane, 1, is 0
}
```

- **Private serialised fields, public getters.** The compiler then enforces the rule from §1.
- **Runtime values live on the object that uses the config.** `RunController` holds
  `float _speed = config.RunSpeed;` and multiplies its own copy.
- **One asset per tuning set, referenced, not found.** A serialised field on the component, or
  provided once from Boot: `boot.Services.Provide(runConfig)`. `Resources.Load` by name puts the
  asset in every build whether or not it is used.
- **A variant is another asset**: `RunConfig_Hard`. Difficulty is a reference swap.
- **A changed default in code does not change an existing asset.** The asset serialised the old
  value. Search the assets when a default moves:
  `grep -rn "runSpeed:" Assets --include='*.asset'`.

When a value has to be modified per run and the config is deep, clone the asset once and mutate
the clone: `RunConfig run = Instantiate(config);`. The clone is a runtime object owned by
whoever made it; destroy it with its owner.

## 3. Ids for save data

The save refers to *kinds* of thing — which pickup type, which ability — as well as to objects
in a scene. A kind's id is a field on its definition asset:

```csharp
[CreateAssetMenu(menuName = "Courier/Pickup Definition")]
public sealed class PickupDefinition : ScriptableObject
{
    [SerializeField] string id = "";               // "pickup-parcel" — written to saves; never renamed
    [SerializeField] int value = 1;
    [SerializeField] GameObject prefab;

    public string Id => id;
    public int Value => value;
    public GameObject Prefab => prefab;
}
```

| Tempting id | Fails when |
|---|---|
| The asset's `name` | Someone renames the file |
| The asset GUID | The asset is recreated or a generator rewrites it; unreadable in a save diff |
| An enum value | The enum is reordered — the save holds the integer |
| The index in a list | An entry is inserted above it |
| A typed, stable string on the asset | Never, as long as nobody edits it — so test that |

A catalogue asset maps ids back to definitions on load, and one EditMode test keeps the ids
usable:

```csharp
[Test]
public void PickupIds_AreSetAndUnique()
{
    var seen = new HashSet<string>();
    foreach (string guid in AssetDatabase.FindAssets("t:PickupDefinition"))
    {
        var def = AssetDatabase.LoadAssetAtPath<PickupDefinition>(AssetDatabase.GUIDToAssetPath(guid));
        Assert.IsNotEmpty(def.Id, def.name + " has no id");
        Assert.IsTrue(seen.Add(def.Id), "duplicate id " + def.Id);
    }
}
```

An id that has shipped is frozen. Retiring a pickup kind is a migration step that drops or
remaps its flags (`reference/save-format.md`), not a deleted asset. Ids for **scene objects** —
this gate, that switch — are `resources/PersistentId.cs`, not an asset.

## 4. Shared runtime sets

A runtime set is an asset used as a meeting point: sentries add themselves when enabled and
remove themselves when disabled, and the HUD, the alarm and the audio read the list without
finding anyone.

```csharp
[CreateAssetMenu(menuName = "Courier/Sentry Set")]
public sealed class SentrySet : ScriptableObject
{
    [System.NonSerialized] readonly List<SentryBrain> _items = new List<SentryBrain>();
    public IReadOnlyList<SentryBrain> Items => _items;

    public void Add(SentryBrain s) { if (!_items.Contains(s)) _items.Add(s); }
    public void Remove(SentryBrain s) => _items.Remove(s);

    // Cleared twice on purpose: OnEnable covers a fresh load, and the static clear covers an
    // asset that stays loaded between Play sessions with domain reload off.
    static readonly List<SentrySet> s_Loaded = new List<SentrySet>();
    void OnEnable()  { _items.Clear(); if (!s_Loaded.Contains(this)) s_Loaded.Add(this); }
    void OnDisable() => s_Loaded.Remove(this);

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ClearOnPlay() { foreach (SentrySet set in s_Loaded) set._items.Clear(); }
}
```

```csharp
// SentryBrain
[SerializeField] SentrySet set;
void OnEnable()  => set.Add(this);
void OnDisable() => set.Remove(this);
```

This is runtime state on an asset, on purpose, and it stays honest under three conditions:

- **Nothing in it is serialised.** `[NonSerialized]`: the Editor then has nothing to write to
  disk, and the trap in §1 cannot spring.
- **Membership follows `OnEnable`/`OnDisable`.** An unloaded level empties the set by itself; a
  pooled sentry leaves it when released.
- **It is cleared when play starts.** With domain reload off an asset stays loaded between Play
  sessions and its non-serialised fields can keep last session's destroyed objects. `OnEnable`
  and the `SubsystemRegistration` clear both empty the list, so it is empty before the first
  scene whichever of them the editor runs. Check it: enter Play twice with domain reload off and
  log `Items.Count` from the first `Start`. An event channel's listeners (§5) need the same
  treatment.

It is a convenience for presentation and tooling. Game rules that must be saved or tested do not
read their world from a set of components — they own plain data →
`unity-game-brief` → `reference/sim-presentation-split.md`.

## 5. Event channels

An event channel is an asset with one event on it: the gate raises "opened", and the music, the
HUD and the achievement listen, with no reference between any of them.

```csharp
[CreateAssetMenu(menuName = "Courier/Event Channel")]
public sealed class EventChannel : ScriptableObject
{
    event System.Action _raised;
    public int Listeners => _raised == null ? 0 : _raised.GetInvocationList().Length;

    public void Subscribe(System.Action listener) => _raised += listener;
    public void Unsubscribe(System.Action listener) => _raised -= listener;
    public void Raise() => _raised?.Invoke();

    void OnEnable() => _raised = null;
}
```

| Use a channel | Use a direct C# event on a service |
|---|---|
| Sender and listener are in different scenes or prefabs and are wired by a designer | Both ends are code that already has the service (`GameState.Changed`, `SceneLoader.Loaded`) |
| Many unrelated listeners: audio, UI, analytics | One or two listeners |
| The event is a fact about the world: gate opened, sentry alerted | The event is part of a contract with ordering guarantees |

The costs are real: a channel has no call site to jump to, no ordering between listeners, and a
listener that forgets `OnDisable` is called after its scene has gone. Keep it bounded:

- **Subscribe in `OnEnable`, unsubscribe in `OnDisable`, always in pairs.**
- **Name the asset after the fact**, past tense: `GateOpened`, never `OnEvent3`.
- **Find who listens with a search**, since the code will not say:
  `grep -rn "guid: <the channel's guid>" Assets --include='*.unity' --include='*.prefab'`.
- **`Listeners` is 0 after a level unloads** when nothing persistent subscribed — a check for
  the leak, one line in a journey.
- **A channel never carries the phase.** Winning, losing and pausing go through `GameState`,
  which can refuse (`reference/game-state-and-pause.md`).

## 6. Lifetime, briefly

| Fact | Consequence |
|---|---|
| An asset is loaded when something loaded references it, and may be unloaded by `Resources.UnloadUnusedAssets` when nothing does | Non-serialised state on it can vanish across a level change. A set or channel referenced from Boot stays loaded |
| `OnEnable` runs when the asset is loaded, not when a scene starts | Clearing runtime state there covers a fresh load; a set referenced from Boot is loaded once per session |
| `ScriptableObject.CreateInstance<T>()` makes a runtime object with no asset | Good for tests and for clones; it is destroyed by whoever made it |
| In the Editor, `EditorSceneManager.NewScene` destroys ScriptableObjects that were never saved | Generated assets are saved first → `unity-new-project` |
