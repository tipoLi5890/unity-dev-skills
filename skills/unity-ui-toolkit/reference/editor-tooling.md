# Editor windows, inspectors and property drawers

> Part of the `unity-ui-toolkit` skill. Read when the UI being built is for the Editor rather
> than for the game: a tool window, a custom inspector, a drawer for one serialised type.

Editor UI is the one place immediate-mode `OnGUI` is still a legitimate choice — and it is a
narrow one. The default for anything new is UI Toolkit.

## Which of the two, decided in one pass

**New window, new inspector, new drawer → UI Toolkit.** `CreateGUI` on an `EditorWindow`,
`CreateInspectorGUI` on an `Editor`, `CreatePropertyGUI` on a `PropertyDrawer`. All three build a
`VisualElement` tree once, and everything the rest of this skill says about UXML, USS and flex
applies unchanged.

**Immediate mode, on three conditions:**

- The file already has `OnGUI` / `OnInspectorGUI` in it and the job is a change, not a rewrite.
- Every editor tool in the project is immediate-mode, and a lone UI Toolkit window would be the
  odd one out for whoever maintains it next.
- The request names `OnGUI` or immediate mode directly.

If the request is ambiguous — "add an editor window for the level data" — the question worth
asking is which of the two the project already uses, and the answer is usually in the existing
editor scripts. Look before asking.

A third case appears sometimes and belongs to neither: a **runtime debug overlay** drawn from
`OnGUI` in a `MonoBehaviour`. It is legitimate for a throwaway frame counter and nothing else —
runtime game UI is UI Toolkit or Canvas. `unity-game-ui` covers the cost of `OnGUI` at runtime and
why it is never dispatched under `-batchmode`.

## Where the code has to live

> **A script that touches the `UnityEditor` namespace outside an editor-only assembly breaks the
> player build.** Not the Editor — the build. The compile succeeds in the Editor and fails when
> the player assemblies are compiled without `UnityEditor` in scope.

Two ways to satisfy that, and a project uses one or the other consistently:

- A folder literally named `Editor` anywhere under `Assets/` — everything below it is excluded
  from player builds.
- An `.asmdef` with `includePlatforms: ["Editor"]`, which is the version that scales and the one
  to prefer in a project that already has assembly definitions.

## Naming

| Type | Shape | Example |
|---|---|---|
| Window | `<Thing>Window.cs` | `LevelEditorWindow.cs` |
| Custom inspector | `<Type>Editor.cs` | `EnemyEditor.cs` |
| Property drawer | `<Type>Drawer.cs` | `HealthRangeDrawer.cs` |

Match whatever the project already does before applying any of it. Menu paths in these templates
sit under `Tools/Unity Dev/…` so a generated tool never collides with a vendor's.

## The five types that ship in `UnityEditor.UIElements`

The assembly is not the one people guess: `PropertyField`, `ObjectField`, `Toolbar`,
`InspectorElement` and `BindingExtensions` are all in the **`UnityEditor.UIElements`** namespace
inside **`UnityEditor.CoreModule`**. `PropertyField` takes `()`, `(SerializedProperty)` or
`(SerializedProperty, string label)`. `BindingExtensions` supplies the extension methods
`Bind(VisualElement, SerializedObject)`, `Unbind`, `BindProperty`, `TrackPropertyValue` and
`TrackSerializedObjectValue`.

`Editor.CreateInspectorGUI` and `PropertyDrawer.CreatePropertyGUI` are both real virtuals
returning `VisualElement`, so `override` is correct on both.

## Template — EditorWindow, the default path

```csharp
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

public class LevelEditorWindow : EditorWindow
{
    [MenuItem("Tools/Unity Dev/Level Editor")]
    public static void Open() => GetWindow<LevelEditorWindow>("Level Editor");

    void CreateGUI()
    {
        var root = rootVisualElement;
        root.style.paddingLeft = root.style.paddingRight = 8;
        root.style.paddingTop  = root.style.paddingBottom = 8;

        root.Add(new Label("Level Editor")
        {
            style = { unityFontStyleAndWeight = FontStyle.Bold, marginBottom = 6 }
        });

        var scroll = new ScrollView(ScrollViewMode.Vertical) { style = { flexGrow = 1 } };
        root.Add(scroll);

        var row = new VisualElement { style = { flexDirection = FlexDirection.Row } };
        row.Add(new Label("Rows") { style = { flexGrow = 1 } });
        row.Add(new Button(Rebuild) { text = "Rebuild", style = { width = 90 } });
        scroll.Add(row);
    }

    void Rebuild() { }
}
```

Everything the rest of the skill says about flex applies to that tree unchanged — `flexGrow = 1`
on the scroll view is what makes it fill the window, and no size is hardcoded to the window's.
A UXML file loaded with `AssetDatabase.LoadAssetAtPath<VisualTreeAsset>(…).CloneTree(root)` is the
same window with the layout in markup, which is worth it as soon as the tree stops being a list.

> **Neither `CreateGUI` nor `OnGUI` is declared on `EditorWindow`** — a search of that class's own
> members finds no method of either name. Both are called by name. Two consequences: writing
> `override` in front of them does not compile, and misspelling
> one produces a window that opens completely empty with nothing in the Console. `EditorWindow`
> derives from `ScriptableObject`, so `OnEnable` / `OnDisable` are the object's lifecycle and they
> fire again after every domain reload — cache in `OnEnable`, and expect a plain C# field to be
> gone by the next compile unless it is serialised.

A window that edits a serialised object binds the tree once instead of reading and writing values
by hand:

```csharp
void CreateGUI()
{
    var so = new SerializedObject(Selection.activeObject);
    rootVisualElement.Add(new PropertyField(so.FindProperty("m_Interval")));
    rootVisualElement.Bind(so);          // UnityEditor.UIElements extension method
}
```

`Bind` is what makes undo, prefab override bars and multi-object editing work — the same job
`serializedObject.Update()` / `ApplyModifiedProperties()` does by hand in immediate mode. In a
window you call it yourself; in an inspector or a drawer the Editor binds the returned tree for
you.

## Template — custom inspector, the default path

```csharp
using UnityEditor;
using UnityEditor.UIElements;
using UnityEngine.UIElements;

[CustomEditor(typeof(EnemySpawner))]
public class EnemySpawnerEditor : Editor
{
    public override VisualElement CreateInspectorGUI()
    {
        var root = new VisualElement();

        root.Add(new PropertyField(serializedObject.FindProperty("m_Interval")));
        root.Add(new PropertyField(serializedObject.FindProperty("m_Prefab")));

        var spawn = new Button(() => ((EnemySpawner)target).SpawnOne())
        {
            text = "Spawn One Now",
            style = { marginTop = 6 }
        };
        root.Add(spawn);

        return root;
    }
}
```

- **No `Update()` / `ApplyModifiedProperties()` pair.** The inspector binds the tree it is handed,
  and a bound `PropertyField` writes through the `SerializedProperty` — so undo and dirtying come
  for free. That is the whole reason to prefer this form.
- **Implement `CreateInspectorGUI` or `OnInspectorGUI`, never both.**
- **React to an edit with `TrackPropertyValue`**, not by polling in a redraw: it takes the
  property and a callback and fires when the value changes.

## Template — property drawer, the default path

```csharp
using UnityEditor;
using UnityEditor.UIElements;
using UnityEngine.UIElements;

[CustomPropertyDrawer(typeof(HealthRange))]
public class HealthRangeDrawer : PropertyDrawer
{
    public override VisualElement CreatePropertyGUI(SerializedProperty property)
    {
        var row = new VisualElement { style = { flexDirection = FlexDirection.Row } };

        row.Add(new Label(property.displayName) { style = { minWidth = 120 } });
        row.Add(new PropertyField(property.FindPropertyRelative("min"), string.Empty)
                { style = { flexGrow = 1, marginRight = 4 } });
        row.Add(new PropertyField(property.FindPropertyRelative("max"), string.Empty)
                { style = { flexGrow = 1 } });

        return row;
    }
}
```

**No height calculation.** Flex measures the row, so the whole `GetPropertyHeight` problem below
does not exist on this path — a two-row drawer just works. This is the strongest single argument
for the modern form, and the reason a new drawer should never start in immediate mode.

## The maintenance path — immediate mode

The three templates that follow are for the narrow cases at the top of this file: a file that
already has `OnGUI` in it, a project where every editor tool is immediate-mode, or a request that
names `OnGUI`. Do not start here.

### EditorWindow — `OnGUI`

```csharp
using UnityEditor;
using UnityEngine;

public class LegacyLevelWindow : EditorWindow
{
    [MenuItem("Tools/Unity Dev/Level Editor (immediate mode)")]
    public static void Open() => GetWindow<LegacyLevelWindow>("Level Editor");

    Vector2 m_Scroll;

    void OnGUI()
    {
        GUILayout.Label("Level Editor", EditorStyles.boldLabel);

        m_Scroll = EditorGUILayout.BeginScrollView(m_Scroll);
        EditorGUILayout.BeginHorizontal();
        GUILayout.Label("Rows");
        GUILayout.FlexibleSpace();
        if (GUILayout.Button("Rebuild", GUILayout.Width(90))) Rebuild();
        EditorGUILayout.EndHorizontal();
        EditorGUILayout.EndScrollView();
    }

    void Rebuild() { }
}
```

### Custom inspector — `OnInspectorGUI`, with undo

```csharp
using UnityEditor;
using UnityEngine;

[CustomEditor(typeof(EnemySpawner))]
public class EnemySpawnerEditor : Editor
{
    SerializedProperty m_Interval;
    SerializedProperty m_Prefab;

    void OnEnable()
    {
        m_Interval = serializedObject.FindProperty("m_Interval");
        m_Prefab   = serializedObject.FindProperty("m_Prefab");
    }

    public override void OnInspectorGUI()
    {
        serializedObject.Update();

        EditorGUILayout.PropertyField(m_Interval);
        EditorGUILayout.PropertyField(m_Prefab);

        serializedObject.ApplyModifiedProperties();

        if (GUILayout.Button("Spawn One Now")) ((EnemySpawner)target).SpawnOne();
    }
}
```

> **`Update()` at the top, `ApplyModifiedProperties()` at the bottom, every time.** That pair is
> what registers the change with the undo system and marks the scene or asset dirty. Reaching
> through `target` and assigning a field directly skips both: the value changes, the scene does not
> know it is dirty, and the edit is gone at the next save. When there is genuinely no
> `SerializedProperty` for what you are changing, `Undo.RecordObject` before and
> `EditorUtility.SetDirty` after are the manual equivalents.

`FindProperty` in `OnEnable`, not in the draw method — the inspector redraws constantly and the
lookup is by string.

Both `OnInspectorGUI` and `CreateInspectorGUI` are real virtuals on `Editor` — unlike the window
case, where neither entry point is declared at all. Implement one or the other, not both.

### Property drawer — `OnGUI`

```csharp
using UnityEditor;
using UnityEngine;

[CustomPropertyDrawer(typeof(HealthRange))]
public class HealthRangeDrawer : PropertyDrawer
{
    public override void OnGUI(Rect position, SerializedProperty property, GUIContent label)
    {
        EditorGUI.BeginProperty(position, label, property);
        position = EditorGUI.PrefixLabel(position, label);

        var indent = EditorGUI.indentLevel;
        EditorGUI.indentLevel = 0;

        var half = position.width * 0.5f - 2f;
        EditorGUI.PropertyField(new Rect(position.x, position.y, half, position.height),
                                property.FindPropertyRelative("min"), GUIContent.none);
        EditorGUI.PropertyField(new Rect(position.x + half + 4f, position.y, half, position.height),
                                property.FindPropertyRelative("max"), GUIContent.none);

        EditorGUI.indentLevel = indent;
        EditorGUI.EndProperty();
    }

    public override float GetPropertyHeight(SerializedProperty property, GUIContent label)
        => EditorGUIUtility.singleLineHeight;
}
```

- **`BeginProperty` / `EndProperty` wrap the whole drawer.** They are what make prefab override
  bars, multi-object editing and the context menu work on your field.
- **`GetPropertyHeight` is a real virtual** and the
  default is one line. A drawer that lays out two rows without overriding it draws the second row
  on top of the next field in the inspector — the classic "my drawer overlaps everything below".
  `CreatePropertyGUI` has no equivalent to get wrong.

## Immediate-mode rules that are actually about cost

`OnGUI` runs several times per frame — once per event phase — so anything allocated in it is
allocated several times per frame, for as long as the window is open.

- **Cache every `GUIStyle`.** Constructing one inside the draw method is the standard editor-tool
  memory leak. A lazily-initialised property is the usual form:
  `_header ??= new GUIStyle(EditorStyles.boldLabel) { fontSize = 16 };`
- **Pair every `Begin` with its `End`** — horizontal, vertical, scroll view, area, disabled group,
  property. An unmatched pair does not throw where you wrote it; it corrupts layout somewhere
  further down the window, which is why the error message names a line you did not touch. The
  `using (new EditorGUI.DisabledGroupScope(…))` form removes the whole class of bug where the
  language allows it.
- **`EditorGUILayout` in editor code, `GUILayout` in a runtime overlay.** They are different
  layout systems and the editor one knows about serialised properties.
- **`EditorGUI.BeginChangeCheck()` / `EndChangeCheck()`** is how you react to an edit without
  polling a cached copy of the value.

## The parts that are the same either way

Detecting which UI system a project uses at all — the ladder, and what each signal means — is
`unity-game-ui` §0. Driving the Editor to reimport what you just wrote is `unity-debug` →
`reference/editor-control.md`; editor UXML and USS parse on import exactly like the runtime kind,
so §0 of the skill applies to them too.

One asymmetry worth knowing before you write a custom attribute converter for a custom element:
`UxmlAttributeConverter<T>` is in the **`UnityEditor.UIElements`** namespace and ships in the
editor module, so a converter lives in editor-only code
even when the element it serves is runtime UI. That does not violate the rule above, because the
runtime element never names the converter: the registry is keyed on the converted type, not on an
attribute. The working split is in
`reference/painter2d-and-custom-elements.md` → "Types an attribute can be".
