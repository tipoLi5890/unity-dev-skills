# Manipulators and drag-and-drop

> Part of the `unity-ui-toolkit` skill. Read when an element has to respond to a pointer with
> more than a click — dragging, reordering, an inventory slot, a crafting bench.

A `Manipulator` is interaction logic that lives on the element rather than beside it. One class,
attached to any number of elements, owning its own registration. The alternative — callbacks wired
from a controller — works for a single button and stops scaling the moment two elements need the
same behaviour.

## The base pattern

```csharp
public class DragManipulator : PointerManipulator
{
    protected override void RegisterCallbacksOnTarget()
    {
        target.RegisterCallback<PointerDownEvent>(OnDown);
        target.RegisterCallback<PointerMoveEvent>(OnMove);
        target.RegisterCallback<PointerUpEvent>(OnUp);
        target.RegisterCallback<PointerCaptureOutEvent>(OnCaptureOut);
    }

    protected override void UnregisterCallbacksFromTarget()
    {
        target.UnregisterCallback<PointerDownEvent>(OnDown);
        target.UnregisterCallback<PointerMoveEvent>(OnMove);
        target.UnregisterCallback<PointerUpEvent>(OnUp);
        target.UnregisterCallback<PointerCaptureOutEvent>(OnCaptureOut);
    }
}
```

Attach with `element.AddManipulator(new DragManipulator())`.

> **Unregister exactly what you registered.** The mirror method is not decoration: an element
> removed and re-added accumulates handlers, and the symptom is a drag that moves twice as fast on
> the second attempt.

**Where these methods actually live**, because the compile error is confusing otherwise:
`AddManipulator` and `RemoveManipulator` are **extension methods**
on `VisualElementExtensions`, and `CapturePointer` / `ReleasePointer` / `HasPointerCapture` are
extension methods on `PointerCaptureHelper` — none of them are declared on `VisualElement` itself.
Both classes are in `UnityEngine.UIElements`, so ordinary code that already names `VisualElement`
has them. What the arrangement changes is the **error text** when something else is wrong: the
compiler reports no definition for `AddManipulator` on `VisualElement`, naming the method rather
than the namespace. So code that fully qualifies the element type without a using directive, or an
assembly definition that does not reference the UIElements module, both read as "this method does
not exist" instead of as a namespace that is not in scope. Add the using directive, or the
assembly reference, and look no further at the method.

## The four events of a drag

**1. `PointerDownEvent` — take the pointer and leave the layout.**

```csharp
target.CapturePointer(evt.pointerId);
m_Dragging  = true;
m_Start     = (Vector2)evt.position;     // Vector2 field; evt.position is a Vector3
target.style.position = Position.Absolute;
target.usageHints     = UsageHints.DynamicTransform;
target.BringToFront();
target.AddToClassList("dragging");
evt.StopPropagation();
```

- **Capture the pointer or the drag ends at the element's edge.** Without capture, moves stop
  arriving the instant the cursor leaves the element — which the player reads as "it only works if
  I go slowly".
- **`Position.Absolute` takes the item out of flex flow** so the row it came from does not reflow
  under the cursor.
- **`BringToFront()` is the only z-ordering there is.** USS has no `z-index`; document order is
  the whole model, and this reorders the document.
- **`UsageHints.DynamicTransform`** tells the renderer the transform will change every frame.
  The full set is `None`, `DynamicTransform`, `GroupTransform`, `MaskContainer`,
  `DynamicColor`, `DynamicPostProcessing`, `LargePixelCoverage` — `DynamicTransform` is the
  one that matters here.

**2. `PointerMoveEvent` — move with `translate`, not with layout.**

```csharp
if (!m_Dragging) return;
var delta = (Vector2)evt.position - m_Start;   // m_Start was captured on pointer-down
target.style.translate = new StyleTranslate(new Translate(delta.x, delta.y, 0f));
```

> **Writing `left` / `top` each frame runs the layout pass each frame.** `translate` is applied
> after layout, so the whole subtree is spared. This is the difference between a drag that is
> smooth with fifty inventory slots on screen and one that is not.

Test the drop target on every move so the highlight tracks the cursor, not the release.

**3. `PointerUpEvent` — validate, then commit or revert.**

```csharp
var candidate = target.panel.Pick(evt.position);
var slot = FindAcceptingSlot(candidate);
if (slot != null) slot.Accept(target); else RevertToOrigin();
target.ReleasePointer(evt.pointerId);
```

**4. `PointerCaptureOutEvent` — the only reliable end.** Capture can be lost without a pointer-up
(the panel closing, another element taking it). Put the state reset here — clear the dragging
flag, remove the USS class, restore `position`, raise whatever event the rest of the game listens
for — and let pointer-up do only the drop decision. A cleanup that lives solely in pointer-up
leaves an element stranded mid-drag the first time capture is stolen.

## Finding the drop target

Two mechanisms, and they answer different questions:

| Need | Call |
|---|---|
| What is under the cursor right now | `target.panel.Pick(position)` |
| Does *this specific* element contain the cursor | `slot.worldBound.Contains(position)` |

`Pick` walks the tree and honours `picking-mode`, so **the dragged element itself will be picked
first** unless you set its `pickingMode` to `Ignore` for the duration of the drag. That single line
is the difference between "the slot underneath is never detected" and a working drop. Restore it
on capture-out with the rest of the state. `PickingMode` has exactly two values, `Position` and
`Ignore`.

`worldBound.Contains` is the cheaper loop when the candidate set is a known list of slots.

## State belongs in USS classes

```csharp
target.AddToClassList("dragging");
dropZone.AddToClassList("drop-zone-active");
```

Not `element.style.*`. Inline styles outrank every stylesheet selector, so a shadow written inline
during a drag cannot be themed, overridden, or turned off from a stylesheet afterwards. The two
exceptions above — `position`, `translate` — are per-frame geometry that has no stylesheet
meaning; everything visual goes through a class.

**`evt.StopPropagation()` on the events you handle.** Pointer events bubble, and a draggable item
inside a button otherwise fires the button on release. This is also what stops a drag from
registering as a click on the slot beneath it.

## Constrain, and revert

- **Clamp to a parent or to the screen** on move, or a mis-drag can park an item where no pointer
  can reach it again.
- **Validate before committing.** "Does this slot accept this item type" is a data question, not a
  geometry one, and answering it after the visual move has already happened means writing an undo.
- **Revert visibly.** An item dropped nowhere should animate back to where it came from; snapping
  it back instantly is indistinguishable from the drag having been ignored.

## Inventory and crafting — ask before you build

An "inventory system", "equipment system" or "crafting system" spans a static grid of slots at one
end and a full drag-and-drop interaction model at the other, and the request rarely says which.
Ask first:

- Do players drag items between slots, or is this a display?
- Do items snap to a grid, or to named equipment slots?
- Do items stack, and do they carry quantities?

If dragging is not wanted, build the UXML and USS layout and stop there. Building the manipulator
uninvited adds a class nobody asked for and a set of behaviours the design has not decided.

When it is wanted, the checklist:

- A manipulator class, with its four callbacks and their mirrored unregistration.
- Slot elements that act as drop zones, and a rule for what each accepts.
- USS classes for the dragging state, the valid-target state, and the rejected state.
- **Item data stored apart from the visual elements** — a list, a dictionary, a bound data source.
  An element is a view; if the quantity lives only in a `Label`'s text, the first UI rebuild loses
  the save. Binding those views is `reference/runtime-binding.md`.
- Drop validation before the visual commit.
- Feedback at every stage: the item lifts, the target highlights, an invalid drop returns.
