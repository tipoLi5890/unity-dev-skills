# Pointer adventures — hotspots, walk-to then act, and a queue of one

> Part of the `unity-interaction` skill. The pointer picks the target; the runner still has to
> get there. The contract is unchanged — one target, one press, the interactable decides — and
> the interactor is replaced by a small queue. Worked setting: the **depot** seen as a fixed
> screen — click the switch on the far shelf, the runner walks over and uses it.

## 1. What changes and what does not

| | Body-driven (every other file) | Pointer-driven |
|---|---|---|
| Who selects | The interactor, by reach | The pointer, by what is under it |
| When the press lands | The step it is made | When the runner arrives |
| The selected target | `InteractorBase.Target` | The hotspot under the cursor (hover) and the hotspot in the queue (intent) — two things |
| What is called | `target.Interact(actor)` | The same |
| Refusals, cooldown, events | The interactable's | The same |

A `GateSwitch` or a `Pickup` in Interact mode works as a hotspot unchanged. The pointer never
calls `Interact` from a distance: that is the switch used from across the room.

## 2. A hotspot

A hotspot is an `IInteractable` with a collider the pointer can hit and a place to stand:

```csharp
// Hotspot.cs — beside any InteractableBase on the Interactable layer. No package needed.
using UnityEngine;

public sealed class Hotspot : MonoBehaviour
{
    [Tooltip("Where the runner stands to use it. A child transform on walkable ground.")]
    public Transform standPoint;
    [Tooltip("Face this way on arrival. Empty means face the hotspot.")]
    public Transform lookAt;
    [Tooltip("Cursor verb while hovering: an index into the game's cursor table.")]
    public int cursorVerb = 1;

    public IInteractable Interactable => GetComponent<IInteractable>();
}
```

- **The collider is the clickable area, not the art.** Make it generous — at least 44 points
  across on a phone — and convex. A hotspot the size of a keyhole is a pixel hunt.
- **The stand point is authored.** "The nearest reachable point" puts the runner behind the
  shelf, facing the wall. One child transform per hotspot, on the floor, clear of colliders.
- **Exits are hotspots too.** A doorway to the next room has a stand point at the threshold
  and an `Interact` that asks for the scene change — `unity-scene-flow` →
  `reference/additive-scenes.md`.

## 3. Picking under the pointer

The pointer position comes from the input source as a world point (`RunInput.aimPoint`), never
from a device — `unity-input` → `reference/pointer-and-aim.md`.

**2D, orthographic:**

```csharp
readonly List<Collider2D> _under = new List<Collider2D>(8);
ContactFilter2D _hotspots;      // SetLayerMask(Interactable); useTriggers = true

Hotspot Pick(Vector2 world)
{
    Physics2D.OverlapPoint(world, _hotspots, _under);
    Hotspot best = null;
    int bestLayer = int.MinValue, bestOrder = int.MinValue;
    foreach (Collider2D c in _under)
    {
        var hotspot = c.GetComponentInParent<Hotspot>();
        var drawn = c.GetComponentInParent<SpriteRenderer>();
        if (hotspot == null) continue;
        int layer = drawn != null ? SortingLayer.GetLayerValueFromID(drawn.sortingLayerID) : 0;
        int order = drawn != null ? drawn.sortingOrder : 0;
        if (layer < bestLayer || (layer == bestLayer && order <= bestOrder)) continue;
        best = hotspot; bestLayer = layer; bestOrder = order;
    }
    return best;
}
```

- **Overlapping hotspots are resolved by draw order**, so the click lands on the thing the
  player sees on top. Physics has no opinion on which collider is "in front" in 2D; the
  renderer's sorting layer value, then order in layer, is the answer — `unity-2d-rendering` →
  `reference/sort-order.md`. In a Y-sorted room compare the sort point's y last.
- **Compare layer values, not ids.** `sortingLayerID` is an arbitrary number;
  `SortingLayer.GetLayerValueFromID` is the position in the list.
- Under a perspective camera a 2D scene is picked with `Physics2D.GetRayIntersection` —
  `unity-physics-2d` → `reference/queries-2d.md`.

**3D:** one `Physics.Raycast` from `Camera.ScreenPointToRay` against
`interactable | blockers`, first hit only, exactly as the first-person ray in
`reference/detection-choice.md` §2 — a wall in front of the switch wins.

**Both:** a click on the HUD is not a click on the world. The reader drops a press that began
over UI before it becomes a `RunInput` press — `unity-input` → `reference/pointer-and-aim.md`,
under "A world click versus a UI click".

## 4. Walk-to, then act

```
click on hotspot ──► queue = { hotspot, verb }      ← replaces whatever was queued
                     walk to hotspot.standPoint
arrived ───────────► face lookAt
                     interactable.CanInteract(runner)?  ── no ──► Interact anyway: it refuses, with its own feedback
                     interactable.Interact(runner)
                     queue = empty
click on floor ────► queue = empty; walk there
```

```csharp
void FixedUpdate()
{
    if (_queued == null) return;
    if (!Arrived(_queued.standPoint.position)) return;
    Face(_queued.lookAt != null ? _queued.lookAt.position : _queued.transform.position);
    IInteractable target = _queued.Interactable;
    _queued = null;                                   // before the call: Interact may queue the next
    if (target != null) target.Interact(gameObject);
}
```

- **Arrival is a distance to the stand point, with a tolerance** — 0.1 units for a mover that
  stops exactly, the agent's stopping distance plus 0.05 for a `NavMeshAgent`. Waiting for
  `velocity == 0` never ends on a path that is blocked.
- **Arrival can fail.** If no path exists, or the runner has made no progress for 2 s, empty
  the queue and say so — a shrug, a line of text. A silent queue reads as a broken click.
- **Re-check on arrival, not on click.** The gate may have closed while the runner walked.
  `Interact` re-checks by contract — `reference/interactable-contract.md` §3 — so the queue
  simply delivers.
- **Walking is somebody else's:** on a NavMesh, `agent.SetDestination(standPoint.position)` —
  `unity-navigation` → `reference/recipes.md` §2. On a 2D walkable area or a grid,
  `unity-game-ai` → `reference/pathfinding-2d.md`.
- **A double click runs or skips the walk.** Raise the agent's speed, or fade and place the
  runner at the stand point; the queue and the arrival test are the same.

## 5. The queue holds one intent

| Player does | Queue |
|---|---|
| Clicks a hotspot | Replaced with it |
| Clicks another hotspot mid-walk | Replaced — the first is abandoned with no effect |
| Clicks the floor | Emptied; the runner walks there |
| Clicks the same hotspot again | Unchanged, or treated as the double click |
| Clicks during a cutscene or a hold | Ignored — the queue is disabled with input |

A queue of several pending actions sounds generous and plays badly: the third click is made
with no knowledge of what the first two did. One intent, replaced by the next, is what players
expect. A sequence that has to complete — pick up, walk, use on — is a scripted beat, driven
by a Timeline or a coroutine that calls `Interact` in order with input off — `unity-animation`
→ `reference/timeline.md`.

**Using an item on a hotspot** is the same queue with a second field: `{ hotspot, itemId }`.
On arrival the queue calls a second interface the hotspot may implement —
`bool UseItem(GameObject actor, string itemId)` — and falls back to a refusal line. Items stay
ids: `reference/pickups.md` §5.

## 6. Cursor verbs

The cursor is the prompt. It shows what a click will do before the click:

| Under the pointer | Cursor | From |
|---|---|---|
| Nothing, or the floor | Walk | Default |
| A hotspot whose `CanInteract` is true | Its verb: look, take, use, talk, exit | `Hotspot.cursorVerb` |
| A hotspot that refuses | The verb, dimmed, or a "cannot" cursor | `CanInteract(runner) == false` |
| UI | The system arrow | The pointer is over UI |

```csharp
// Called when the hovered hotspot changes, never every frame.
Cursor.SetCursor(table[verb].texture, table[verb].hotspot, CursorMode.Auto);
```

- **Import cursor textures with Texture Type `Cursor`,** 32 × 32 for a hardware cursor, and
  give each its click point: the tip for an arrow, the centre for a hand.
- **A hardware cursor does not scale with the game's resolution.** A pixel-art game that wants
  a cursor on its own pixel grid hides the system one (`Cursor.visible = false`) and draws a
  UI image at the pointer — `unity-2d-pixel-perfect`.
- **On a gamepad there is no pointer.** Either drive a virtual cursor — `unity-input` →
  `reference/pointer-and-aim.md`, under "A cursor for the gamepad" — or cycle hotspots in
  screen order with the stick and show the verb as an ordinary prompt:
  `reference/prompts.md`.
- **On touch there is no hover.** The first tap on a hotspot shows its name and verb; the
  second, or a tap held 0.3 s, queues it. Or show every hotspot's marker while a "reveal"
  button is held.
- **Name on hover:** a label at the cursor with the hotspot's `Prompt`, placed like a
  following screen-space prompt — `reference/prompts.md` §3.

## 7. Probe and journey

```csharp
GameProbe.Register("hover", () => _hover != null ? _hover.name : "");
GameProbe.Register("queued", () => _queued != null ? _queued.name : "");
GameProbe.Count("switchUses", () => gateSwitch.Uses);
```

A journey scripts the pointer through `ScriptedRunInput.SetAimPoint` and a press, then asserts
on the three values: `queued` names the switch from the click until arrival, `switchUses` is 0
at every sample where the runner is further than the tolerance from the stand point, and 1 at
the end. A second click on the floor mid-walk leaves `switchUses` at 0. Building such a test:
`unity-play-harness` → `reference/journeys.md`.

## Checks

- Click a switch across the room: the gate's state is `Closed` until the runner stops at the
  stand point.
- Click a switch, then the floor before arriving: the switch is never used.
- Stack two hotspots and click where they overlap: the one drawn on top is queued.
- Click a HUD button that sits over a hotspot: nothing is queued.
- Click a hotspot with no path to its stand point: the queue empties within 2 s and the runner
  reacts.
- Hover a locked gate: the cursor shows the refusal before any click.
