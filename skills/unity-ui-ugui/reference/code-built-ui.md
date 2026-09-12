# Building uGUI from C#, with no prefabs

> Part of the `unity-ui-ugui` skill. Read when the UI is constructed at runtime by a factory
> rather than authored as prefabs — an agent-built project, a project whose screens must exist
> before anyone opens the Editor, or PlayMode tests that must not depend on serialised assets.

## 1 · The things the Editor menu does that `AddComponent` does not

Both of these fail **silently** — no exception, no console warning, just an empty screen.

### Canvas defaults to WorldSpace

```csharp
var go = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
var c  = go.GetComponent<Canvas>();
c.renderMode = RenderMode.ScreenSpaceOverlay;   // REQUIRED — the default is WorldSpace
```

`GameObject ▸ UI ▸ Canvas` sets Screen Space – Overlay for you. A component added from script does
not: it is a world-space quad at the origin, invisible for reasons that have nothing to do with the
UI on it.

**Two defaults will surprise you when you build a Canvas from script.** One is `renderMode` above;
the other is `CanvasScaler`, which defaults to **`ConstantPixelSize`** with a reference resolution of
**(800, 600)** and `matchWidthOrHeight = 0`. So "this project
uses Constant Pixel Size" is the out-of-the-box state, not evidence that someone chose it.

### There is no EventSystem, and the input module depends on the package set

A fresh scene has **no** EventSystem, so a code-built UI has to create one, and which module it
needs depends on whether the Input System package is present. With Active Input Handling
(Player Settings) set to Input System (New) — the usual state once the package is installed —
a `StandaloneInputModule` receives nothing at all, and the UI is visible and completely inert.

```csharp
static void EnsureEventSystem()
{
    if (UnityEngine.EventSystems.EventSystem.current != null) return;
    var es = new GameObject("EventSystem", typeof(UnityEngine.EventSystems.EventSystem));
#if ENABLE_INPUT_SYSTEM
    es.AddComponent<UnityEngine.InputSystem.UI.InputSystemUIInputModule>();
#else
    es.AddComponent<UnityEngine.EventSystems.StandaloneInputModule>();
#endif
}
```

Call it from the same helper that creates the Canvas, so no screen can forget.

## 2 · A custom `Graphic` needs `typeof(CanvasRenderer)` spelled out

`[RequireComponent]` is honoured by `AddComponent` and by the inspector's Add Component flow — it
is **not** processed by the multi-`Type` `GameObject` constructor. So this builds, runs, lays out
correctly, and draws absolutely nothing:

```csharp
new GameObject("Card", typeof(RectTransform), typeof(RoundedRect));   // WRONG — no renderer
```

`Graphic` has no `CanvasRenderer` to hand its mesh to. In a factory-built UI this blanks every
`Graphic` at once — cards, buttons, focus rings, glows — with an empty console; an EditMode test
surfaces the real message:

```
UnityEngine.MissingComponentException : There is no 'CanvasRenderer' attached to the "Card" game object,
but a script is trying to access it.
```

The fix is to list it:

```csharp
new GameObject("Card", typeof(RectTransform), typeof(CanvasRenderer), typeof(RoundedRect));
```

Do this in **every** factory method that produces a `Graphic` subclass, and pin it with the test in
§3 — a blank screenshot is a bad way to find out.

## 3 · Verify procedural geometry in EditMode, without rendering

A custom `Graphic` can be checked with no Play mode, no screenshots, and no working shader
compiler — which matters most on a machine where screenshots cannot be trusted, and it runs in
about a minute instead of a full PlayMode + screenshot loop.

```csharp
[Test]
public void Shape_generates_vertices()
{
    var canvas = new GameObject("C", typeof(Canvas)).GetComponent<Canvas>();
    canvas.renderMode = RenderMode.ScreenSpaceOverlay;

    var go = new GameObject("Card", typeof(RectTransform), typeof(CanvasRenderer), typeof(RoundedRect));
    go.transform.SetParent(canvas.transform, false);

    Canvas.ForceUpdateCanvases();
    var mesh = go.GetComponent<RoundedRect>().canvasRenderer.GetMesh();
    Assert.Greater(mesh.vertexCount, 0);

    Object.DestroyImmediate(canvas.gameObject);
}
```

Exact vertex counts pin the geometry harder than "greater than zero" — e.g. a polyline test that
asserts `2 * 4 + 3 * 14` (two segments of four vertices plus three round caps of a centre plus
thirteen ring vertices), and that a degenerate one-point polyline still emits the 14 of a single
cap. That catches "the widget silently produces no mesh" regressions a green scene hides.

## 4 · Raycast discipline, in both directions

Two symmetric traps, both of which a factory makes systematic:

- **To make something clickable it needs *some* `Graphic`.** A `Button` on a bare GameObject never
  receives a click. A fully transparent `UnityEngine.UI.Image` plus `Button.transition =
  Selectable.Transition.None` is the standard invisible hit box.
- **Every decorative graphic a factory emits defaults to `raycastTarget = true`** and silently eats
  clicks meant for what is underneath. On a screen assembled from many factory calls, sweep it once
  after building rather than remembering per call:

  ```csharp
  foreach (var img in root.GetComponentsInChildren<UnityEngine.UI.Image>(true))
      if (img.GetComponent<UnityEngine.UI.Button>() == null &&
          img.GetComponentInParent<UnityEngine.UI.Button>() == null)
          img.raycastTarget = false;
  ```

- **Give every extra Canvas an explicit `sortingOrder`.** A second overlay Canvas (countdown, pause,
  toast) defaults to the same order as the main one and can end up under a game HUD drawn on
  another Canvas — e.g. 5 for the in-game stage Canvas and 10 for the flow Canvas that owns the
  overlays; the numbers matter less than being explicit about both.

## 5 · Refresh a cached widget in `OnEnable`, not only on a timer

A widget that redraws only when a polled value differs from a cached "last drawn" value shows the
*previous screen's* state after a screen switch, for up to one poll interval. Invalidate the cache
when the object comes back:

```csharp
void OnEnable()
{
    _shown = (InputMode)(-1);        // impossible enum value → next Refresh always redraws
    if (_label != null) Refresh();
}
```

Any uGUI element that caches what it drew and is disabled/re-enabled as screens change needs the
same treatment.

## 6 · Two compile errors that only a batch edit produces

Programmatic UI hosts accumulate helper methods and static settings, and both can collide with the
UI types they sit next to. Neither is visible to the script making the edit — a test harness reports
only "no results, compile failed".

| Error | Cause | Fix |
|---|---|---|
| `error CS0119: 'ViewBase.HintBar(string, Color?)' is a method, which is not valid in the given context` | A base-class helper method named the same as a `MonoBehaviour` type hides that type in every subclass | Fully qualify the type at the use site (`MyProject.UI.HintBar.Height`), or rename the helper |
| `error CS0102: The type 'GameFlowController' already contains a definition for 'Grid'` | A new static settings property collides with an existing `public GridView Grid => _grid` | Rename the new member everywhere (controller, views, tests) |

Before adding a member to a programmatic-UI host, check for a same-named type or property in scope.

## 7 · Importing TMP essentials headlessly

Use `TMP_PackageResourceImporter.ImportResources()`. **Do not** call
`EditorApplication.ExecuteMenuItem("Window/TextMeshPro/Import TMP Essential Resources")` — it opens
a modal dialog and blocks whatever invoked it until a human dismisses it, which in an automated run
is an indefinite hang. `AssetDatabase.ImportPackage()` is also the wrong API here.
