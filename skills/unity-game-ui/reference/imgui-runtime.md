# Runtime OnGUI — what the editor-tooling docs do not tell you

> Part of the `unity-game-ui` skill. Read after §0 has established the project is IMGUI.
> Immediate-mode UI is normally documented for EditorWindows, custom Inspectors and
> PropertyDrawers. This file covers the other half: `OnGUI` running every frame in a built game.

## The API boundary

`OnGUI` runs in a build. Half of what IMGUI tutorials show you does not.

`GUILayout` lives in **`UnityEngine.IMGUIModule`**,
`EditorStyles` in **`UnityEditor.CoreModule`**. The split is a real assembly boundary, not a
convention — which is why the editor half cannot reach a player at all.

| Available at runtime | Editor-only — will not compile into a player |
|---|---|
| `GUILayout.*`, `GUI.*` | `EditorGUILayout.*`, `EditorGUI.*` |
| `GUIStyle`, `GUISkin`, `GUIContent` | `EditorStyles.*` (including `boldLabel`) |
| `GUILayout.BeginArea` / `BeginScrollView` | `SerializedProperty`, `SerializedObject` |
| `Event.current` | `Undo.*`, `EditorUtility.*`, `[MenuItem]` |

Anything under `UnityEditor` must live in an `Editor` folder or an Editor-only asmdef, and a
runtime HUD cannot reference it. There are no built-in styles at runtime — you build the skin.

## The one that costs frames

> **Never construct a `GUIStyle`, `GUIContent` or `Texture2D` inside `OnGUI`.**

In an editor window this allocates on repaint. In a game it allocates **every frame, several times
per widget**, and the resulting GC pressure shows up as periodic hitching that looks like a
physics or streaming problem.

**`new GUIStyle()` costs ~49 bytes each.** Small on its own — which is exactly why it survives
review. Multiply it by the widgets on screen, by the event phases per frame, by 60 frames a
second, and it is a steady allocation rate for something that never changes.

Cache lazily and let the field own the lifetime:

```csharp
static GUIStyle _label;
static GUIStyle Label => _label ??= new GUIStyle(GUI.skin.label) {
    alignment = TextAnchor.MiddleCenter, wordWrap = false,
};
```

Same rule for `new Color(...)` in a tight draw loop, and for `string` concatenation building a
score readout — cache the string and rebuild it only when the value changes.

`OnGUI` is also called **multiple times per frame**, once per event phase. Anything with a side
effect must be guarded:

> **You cannot verify this headlessly.** A PlayMode test run under `-batchmode` ticks `Update`
> and dispatches `OnGUI` **zero** times — there is no render loop, so no GUI event phases. It is
> the same root cause as batchmode being unable to screenshot
> (`unity-debug` → `reference/visual-checks.md`). Anything about IMGUI *behaviour* — event
> phases, `GUI.matrix` versus `Event.current.mousePosition`, draw order — has to be checked in a
> windowed run or on a device. Do not conclude from a green headless suite that the HUD works.

```csharp
if (Event.current.type != EventType.Repaint) return;   // draw-only work
```

Never mutate game state from `OnGUI` — read it. State changes belong in `Update`.

## Structural rules that fail loudly, and quietly

- **Every `Begin*` needs its `End*`,** on every code path including early returns. A missed
  `EndHorizontal` does not throw where you made the mistake — it corrupts the layout of
  everything drawn afterwards, which is why the error always seems to be in the wrong widget.
- **`GUILayout` and manual `Rect`s do not mix inside one group.** Pick per region.
- **Layout is computed in the Layout event and consumed in Repaint.** Changing the *number* of
  widgets between those two passes throws `ArgumentException: Getting control N's position in a
  group with only M controls`. Cause: a condition that reads live game state and flipped between
  passes. Fix: latch the condition once per frame, not per call.

## Placement, scaling and the pixel grid

`GUILayout.BeginArea(new Rect(x, y, w, h))` is the runtime positioning primitive; `FlexibleSpace`
pushes within it. But a `Rect` in `OnGUI` is in **points, at whatever resolution the player is
running** — a layout tuned on a 1920×1080 editor window is unreadable on a 2532-wide phone and
tiny on a 4K TV.

Scale the whole GUI once, at the top of `OnGUI`, rather than scaling every number:

```csharp
var scale = Screen.height / ReferenceHeight;          // ReferenceHeight is a design constant
GUI.matrix = Matrix4x4.TRS(Vector3.zero, Quaternion.identity, new Vector3(scale, scale, 1f));
```

Two consequences to hold on to:

- **`Event.current.mousePosition` is reported in real screen points, not scaled ones.** Hit tests
  written against scaled `Rect`s will be off by exactly `scale`. Either transform the point, or
  do hit tests before applying the matrix.
- **Restore `GUI.matrix` if any other script also draws.** It is global state for the frame.

Round positions to whole pixels *after* scaling. A rectangle landing on a half-pixel is resampled,
and a resampled edge shimmers whenever the value animates — the arithmetic is in
`reference/layout-math.md`.

## Input: IMGUI does not stop the game from also reacting

There is no automatic event capture. A tap that presses a HUD button will *also* be seen by
gameplay unless you consume it:

```csharp
if (GUI.Button(rect, "PAUSE")) { Pause(); Event.current.Use(); }
```

`Event.current.Use()` marks the event handled for the rest of this `OnGUI` pass. It does **not**
protect against code reading `Input.GetMouseButtonDown` directly in `Update` — that path never
sees IMGUI at all. If the project mixes both, route input through one funnel and let the HUD
claim it first.

Draw order is source order within a script, and across scripts it follows `GUI.depth` (**lower
draws later, i.e. on top** — the reverse of what the name suggests). Two scripts both drawing at
the default depth have no defined order between them; set it explicitly rather than relying on
which one happened to run first.

## Cost

Each `GUI.*` call issues its own draw call. A HUD of a dozen elements is fine; a per-frame
scrolling list of a hundred rows is not. When a HUD grows past "a dozen glanceable things",
that is the signal to reconsider §0's routing decision — not to optimise IMGUI harder.
