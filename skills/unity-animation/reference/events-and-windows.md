# Events and windows — the two ways a clip is allowed to speak to the game

> Part of the `unity-animation` skill. Gameplay does not wait on an animation; it may listen for
> a **named** moment in one. There are two mechanisms, and they fail differently: an
> AnimationEvent is a point that is skipped when the state is left early, a StateMachineBehaviour
> is a span that always ends. Anything that opens must be closed by the one that always ends.

## 1. Which one

| Need | Use | Because |
|---|---|---|
| A moment with no consequence if it is missed: footstep, dust puff, a sound | AnimationEvent | Lives on the clip, travels with it into every state and override |
| The end of a one-shot the game wants to hear about | AnimationEvent, **plus** a game-side timeout | An interrupted clip never reaches its last frame |
| A span that turns something on and must turn it off: hitbox, invulnerability, a trail | `AttackWindowBehaviour` | `OnStateExit` runs however the state is left |
| Different timing per weapon on the same state | The behaviour, configured after the swap — `reference/override-controllers.md` | Events ride with clips, behaviours with states |

| Left the state before the marked time, because… | AnimationEvent at that time | StateMachineBehaviour |
|---|---|---|
| a transition interrupted it (hurt during attack) | **never fires** | `OnStateExit` runs when the transition finishes |
| `Animator.Play` / `CrossFade` jumped elsewhere | never fires | `OnStateExit` runs |
| the Animator was disabled or its object deactivated | never fires | `OnStateExit` does not run; the behaviour closes from its own `OnDisable` (check in §5) |
| the controller was swapped | never fires | as above |

## 2. Writing events from script

`resources/Editor/ClipEventWriter.cs` adds or moves one event by normalised time and is safe to
re-run: an event is identified by `functionName` + `stringParameter`.

```csharp
ClipEventWriter.SetEvent(runClip,  "OnFootstep", 0.10f, "left");
ClipEventWriter.SetEvent(runClip,  "OnFootstep", 0.60f, "right");
ClipEventWriter.SetEvent(hurtClip, "OnAnimEvent", 1f, "hurt-end");   // lands on the last frame
Debug.Log(ClipEventWriter.Describe(runClip));
// {"clip":"runner_run","length":0.6667,"frameRate":12,"events":[{"time":0.0833,"normalised":0.125,…
```

- **Times snap to the clip's frame grid and stop one frame short of the end.** An event at
  exactly `clip.length` sits on the loop seam; one frame earlier it is inside the clip on every
  pass. For a sprite clip that is the last keyframe, `(N-1) / fps`.
- **A clip inside a model file is read-only.** The writer detects it, puts the event in the
  `ModelImporter`'s clip list (where its time is a fraction of the clip) and reimports the model,
  then reads the clip back and logs an error when the event is not where it was asked for. Read
  that log line; do not assume the reimport did what the importer was told.
- **Report before writing on art somebody else authored**: the clip, the function, the time.

## 3. Receiver rules

1. **The method lives on a component on the same GameObject as the Animator.** Not a parent, not
   a child. With the layout `Runner → Visual (Animator)`, the receiver goes on `Visual` and
   forwards to the game.
2. **Zero parameters or one**, of type `float`, `int`, `string`, `Object` or `AnimationEvent`.
   Take `AnimationEvent` when the receiver needs more than one field or the clip's weight.
3. **Every component on that object with a method of that name is called.** Give receivers
   names nobody else will use, and never overload one.
4. **A missing receiver is a runtime error in the log, not a compile error**, and it names the
   clip. Grep the function name across clips and scripts after every rename.
5. **One funnel beats twenty methods.** `OnAnimEvent(AnimationEvent e)` switching on
   `e.stringParameter` gives one name to grep and one place to log.

```csharp
// On the Animator's GameObject. Forwards named moments; decides nothing.
public sealed class RunAnimEvents : MonoBehaviour
{
    public RunController run;                       // replace with your game's state owner

    void OnAnimEvent(AnimationEvent e)
    {
        // §4: ignore the quiet half of a blend.
        if (e.animatorClipInfo.weight < 0.5f) return;
        switch (e.stringParameter)
        {
            case "hurt-end": run.OnHurtClipEnded(); break;       // a hint; the game's timer decides
            default: Debug.LogWarning("[ANIM] unhandled event '" + e.stringParameter + "'", this); break;
        }
    }
}
```

## 4. Events under blending

An event fires from **every clip that is playing with a weight above zero**, not from "the
current state":

- **Blend tree:** both the jog and the sprint in a 1D tree fire their footsteps. At
  `MoveBlend = 0.5` that is four footsteps per stride.
- **Cross-fade:** the outgoing state keeps playing until the fade ends, and its events keep
  firing — an attack's hit event can arrive 0.1 s into the hurt that interrupted it.
- **Layers:** a clip on a masked layer fires its events whatever the mask covers.

Filter in the receiver with `e.animatorClipInfo.weight` (the clip's weight inside its state) —
`< 0.5f` drops the quieter child of a two-clip blend. For a cross-fade, compare
`e.animatorStateInfo.fullPathHash` with `GetCurrentAnimatorStateInfo(layer).fullPathHash`, or
give the transition zero duration.

Check the edge on the project's own rig before relying on it: put a `Debug.Log` in the receiver
that prints `e.animatorClipInfo.clip.name` and `.weight`, hold `MoveBlend` at 0, 0.01 and 1, and
read which clips speak at each.

**Three settings silence events entirely**, and each looks like a broken clip:

| Setting | Effect |
|---|---|
| `Animator.fireEvents = false` | No AnimationEvent is sent |
| `Animator.cullingMode = AnimatorCullingMode.CullCompletely` | Off screen, the Animator stops: no events, no behaviour callbacks |
| A state `speed` of 0, or a `timeParameter` holding the clip still | Time never reaches the event |

A sentry whose attack is resolved by an event stops attacking the moment it leaves the camera
under `CullCompletely`. Either resolve the attack in game time, or set
`AnimatorCullingMode.CullUpdateTransforms`, which keeps the state machine and its events running
and skips only the bone writes.

## 5. Attack windows by normalised time

`resources/AttackWindowBehaviour.cs` sits on a state and calls a receiver beside the Animator:

```csharp
public sealed class StrikeWindow : MonoBehaviour, IAttackWindowReceiver
{
    public Collider hitbox;

    public void OnWindowOpen(string id)                    { if (id == "strike") hitbox.enabled = true; }
    public void OnWindowClose(string id, bool interrupted) { if (id == "strike") hitbox.enabled = false; }
}
```

Add it in the Animator window (Add Behaviour on the state) or from an Editor script:

```csharp
var w = attackState.AddStateMachineBehaviour<AttackWindowBehaviour>();
w.windowId = "strike"; w.open = 0.25f; w.close = 0.55f;
EditorUtility.SetDirty(controller);
```

What it guarantees, and how:

- **One close for every open.** Closed at `close`, in `OnStateExit`, in `OnDisable`, and on
  re-entry before the next open. Check the `OnDisable` path on the project's own rig: deactivate
  the character mid-window and read whether `OnWindowClose(id, true)` is logged. Pooled
  characters depend on it; §6 is the cover when it is not.
- **Closes when the state starts to leave**, not when the cross-fade ends. `OnStateExit` runs at
  the end of the transition out; with `closeWhenLeaving` (on by default) the behaviour closes on
  the first update in which the layer is in transition to another state, and will not open a
  window in a state that is already fading out.
- **A long frame cannot skip it.** Both edges are compared with `>=`, so a hitch that jumps from
  20% to 70% opens and closes in order on the same update — the receiver sees a zero-length
  window rather than none.
- **Looping states open once per cycle.**
- **Its fields are reset in `OnStateEnter`.** One behaviour instance exists per Animator per
  state and is reused on every entry; a flag left over from last time is the classic bug.

Normalised time is the right unit for a window: it survives a retimed clip, a `MoveSpeed`
multiplier and an override clip of another length. It is the wrong unit when the design is in
seconds — "hittable for 0.2 s" — which belongs in game time, started by `OnWindowOpen`.

## 6. The game still owns the outcome

The window is a named moment handed to the game; it is not the game's state.

- The receiver decides whether a hit lands. A window that opens while the game says the runner
  is already down does nothing.
- **Close on the game's own transition as well.** When the game leaves its attacking state for
  any reason, it disables the hitbox itself; `OnWindowClose` arriving later finds it already
  off. The behaviour is the guarantee for the cases the game did not anticipate.
- Anything the game starts from an event has a timeout in game time. The event makes the moment
  look right; the timeout makes it happen.

Read the window from outside before trusting it: register
`GameProbe.Register("strikeOpen", () => hitbox.enabled)` and assert in a journey that it is never
true while `state` is not the attacking one — `unity-play-harness` → `reference/journeys.md`.
