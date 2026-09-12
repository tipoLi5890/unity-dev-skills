# Runtime data binding — the path is a property, not a field

> Part of the `unity-ui-toolkit` skill. Read when UI values should follow game state on their
> own: health, score, ammo, a settings screen, the same number shown in three places.

The whole mechanism rests on one thing: a binding resolves a **property path** against a data
source object. If the member on the other end is not a *property* in the reflection sense, the
path resolves to nothing and the element keeps whatever it was showing. Nothing throws, nothing
logs, and the UI looks like it simply never updates.

## What exists, and where it lives

Binding ships in the core install — every type below resolves with no package added:

| Type | Where it actually lives |
|---|---|
| `DataBinding`, `BindingMode` | `UnityEngine.UIElements` (`UnityEngine.UIElementsModule`) |
| `PropertyPath`, `CreatePropertyAttribute`, `DontCreatePropertyAttribute` | `Unity.Properties` (`UnityEngine.PropertiesModule`) |
| `SetBinding`, `GetBinding`, `HasBinding`, `ClearBinding` | instance methods on `VisualElement` |

`DataBinding`'s public properties, enumerated: `dataSource`, `dataSourceType`,
`dataSourcePath`, `bindingMode`, `sourceToUiConverters`, `uiToSourceConverters`, `updateTrigger`,
`isDirty`. The two that change how you wire a screen are `dataSource` and `dataSourceType`: a
binding can carry its **own** source, independent of the element's — useful when one panel shows
two objects.

## Expose the members deliberately

```csharp
using Unity.Properties;
using UnityEngine;

public class PlayerVitals : ScriptableObject
{
    [CreateProperty]
    public int Health { get; set; }

    [CreateProperty]
    public int MaxHealth { get; set; }

    [SerializeField, DontCreateProperty]
    float m_Stamina;                       // serialised so it shows in the Inspector

    [CreateProperty]
    public float Stamina                   // …and bound through the public wrapper
    {
        get => m_Stamina;
        set => m_Stamina = value;
    }

    [CreateProperty]                       // computed: nothing to keep in sync
    public float HealthPercentage => MaxHealth == 0 ? 0f : 100f * Health / MaxHealth;

    [CreateProperty]
    public string HealthText => $"{Health} / {MaxHealth}";
}
```

Two decisions in that snippet, and both matter:

- **`[CreateProperty]` goes on the public member you intend to bind.** Marking it is what makes
  the path resolvable.
- **`[DontCreateProperty]` on the serialised private backing field.** Keep the field visible to
  the Inspector without offering a second, lower-cased path into the same value. Two paths to one
  number is how a binding ends up wired to the field the setter never runs on.

Computed, read-only members are the best data sources of all — `HealthPercentage` and `HealthText`
derive from `Health` and `MaxHealth`, so they cannot drift out of sync with the numbers they
report, and that is the one place a binding beats an assignment outright.

## `nameof`, always

```csharp
dataSourcePath = new PropertyPath(nameof(PlayerVitals.Health));
```

A string literal here is a silent failure waiting for the first rename: the compiler cannot see
it, the refactor tool will not touch it, and a lower-cased first letter looks identical in a diff.
`nameof` turns all three into compile errors. Nested paths compose the same way, one `nameof` per
hop:

```csharp
dataSourcePath = new PropertyPath(
    $"{nameof(GameState.Player)}.{nameof(PlayerVitals.Health)}");
```

## Binding modes — there are four, not three

`BindingMode` has exactly four members: **`TwoWay`, `ToSource`, `ToTarget`, `ToTargetOnce`**.

| Mode | Direction | Use for |
|---|---|---|
| `ToTarget` | data → UI | Labels, bars, anything display-only. The default choice |
| `ToTargetOnce` | data → UI, once | A value read at open time that must not follow later edits |
| `ToSource` | UI → data | Rare on its own — a control that only writes |
| `TwoWay` | data ↔ UI | Sliders, toggles, text fields the player edits |

`ToTargetOnce` is the one people miss and then reimplement by hand with a flag.

## From UXML

```xml
<ui:UXML xmlns:ui="UnityEngine.UIElements">
  <ui:Slider name="volumeSlider">
    <ui:Bindings>
      <ui:DataBinding property="value" data-source-path="MasterVolume"
                      binding-mode="TwoWay" />
    </ui:Bindings>
  </ui:Slider>
</ui:UXML>
```

`Bindings` and `DataBinding` are both in `UnityEngine.UIElements`, so **one prefix covers both** —
the visual authoring tool sometimes emits a second `xmlns` alias for that same namespace and uses
it here, which is legal and pointless. One prefix per namespace, as everywhere else.

`property` names the **element** property being driven (`value`, `text`); `data-source-path` names
the path on the source. They are two different vocabularies and swapping them is the most common
UXML binding mistake.

Set the source once on the root, and set it as a project asset reference so the authoring tool can
resolve it too:

```xml
<ui:VisualElement name="root" class="panel"
                  data-source="project://database/Assets/Settings/AudioSettings.asset?fileID=11400000&amp;guid=…&amp;type=2#AudioSettings" />
```

That URI is what lets the visual authoring tool preview live values instead of an empty panel. A
root `data-source` assigned only from C# leaves the design-time view blank, which reads as "the
binding is broken" long before the game ever runs.

## From C#

```csharp
[RequireComponent(typeof(UIDocument))]
public class VitalsPanel : MonoBehaviour
{
    [SerializeField] PlayerVitals m_Vitals;
    Label m_HealthLabel;
    ProgressBar m_HealthBar;

    void OnEnable()
    {
        var root = GetComponent<UIDocument>().rootVisualElement;
        m_HealthLabel = root.Q<Label>("healthLabel");
        m_HealthBar   = root.Q<ProgressBar>("healthBar");

        m_HealthLabel.SetBinding("text", new DataBinding {
            dataSourcePath = new PropertyPath(nameof(PlayerVitals.HealthText)) });
        m_HealthBar.SetBinding("value", new DataBinding {
            dataSourcePath = new PropertyPath(nameof(PlayerVitals.HealthPercentage)) });

        root.dataSource = m_Vitals;      // inherited by both children
    }

    void OnDisable()
    {
        if (m_HealthLabel?.HasBinding("text") == true)  m_HealthLabel.ClearBinding("text");
        if (m_HealthBar?.HasBinding("value") == true)   m_HealthBar.ClearBinding("value");
    }
}
```

- **`OnEnable` sets, `OnDisable` clears.** `UIDocument` rebuilds its tree when the component
  cycles; bindings left behind point at elements that no longer exist.
- **`HasBinding` before `ClearBinding`**, because the enable path can have been skipped entirely
  (a missing document, an early return) and the disable path still runs.
- **`rootVisualElement` is null until the document is enabled.** Querying it from `Awake` gives
  the null reference that gets blamed on the query string.

An element built in code binds identically — set the binding, set or inherit the source, then add
it to the tree:

```csharp
var label = new Label();
label.SetBinding("text", new DataBinding {
    dataSourcePath = new PropertyPath(nameof(PlayerVitals.HealthText)) });
label.dataSource = m_Vitals;
container.Add(label);
```

## Panels that rebuild themselves

Some Unity versions have a runtime panel component, `PanelRenderer`, whose
`RegisterUIReloadCallback` hands you the rebuilt root every time the UI reloads — one place to
re-establish bindings, instead of re-deriving the wiring by hand after each reload. Where it is
available it is the better host for the code in the previous section: the callback receives the
root element, so the query, the `dataSource` assignment and the `SetBinding` calls all live in it.

**Check whether your version has it before writing code against it:** scan every loaded assembly
for a type named `PanelRenderer` — zero matches means it is not there. Until you have confirmed
it, do the wiring in `OnEnable`.

## When not to bind

Binding costs a resolution per source change and a layer of indirection that does not show up in a
call stack. Skip it for:

- **A value set once** at screen open. An assignment is shorter and greppable.
- **Anything updated every frame** — a timer, a smoothed bar. Set the property directly; the
  binding system is not a substitute for `Update`.
- **One element, one value, one place.** Binding earns its keep when the same datum reaches
  several elements, or when the source changes on a schedule nobody owns.

## When a binding shows nothing

In this order, because each step is cheaper than the next:

1. **Is the source assigned?** `element.dataSource` (or an ancestor's) non-null at the moment the
   binding evaluates — not at the moment you wrote the line.
2. **Is the member a property with `[CreateProperty]`?** A public field is not a property. This is
   the single most common cause.
3. **Does `property` name a real element property?** `"text"` on a `Label`, `"value"` on a
   `Slider`. A typo here binds nothing and reports nothing.
4. **Is the mode right?** A field the player edits that never writes back is `ToTarget` where it
   should be `TwoWay`.
5. **Did the panel rebuild?** Re-enabling a `UIDocument` discards the elements you bound.

And before any of it, turn the diagnostics on: `PanelSettings` carries a `bindingLogLevel`, whose
values are `None`, `Once` and `All`. `Once` logs each
failing binding a single time, which turns the whole silent-failure problem above into Console
lines. Set it while wiring a screen and put it back to `None` before shipping.
