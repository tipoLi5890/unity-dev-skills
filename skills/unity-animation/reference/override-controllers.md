# Override controllers — one graph, several clip sets

> Part of the `unity-animation` skill. An `AnimatorOverrideController` keeps a controller's
> states, parameters and transitions and replaces its clips. The graph is the contract with the
> bridge; the override is art. Weapon sets and skins are overrides — a second controller per
> weapon is a second contract to keep in step with the first.

## 1. Building one

```csharp
using System.Collections.Generic;
using UnityEngine;

public static class ClipSets
{
    // baseController: the graph. swaps: original clip name → replacement.
    public static AnimatorOverrideController Make(RuntimeAnimatorController baseController,
                                                  IDictionary<string, AnimationClip> swaps)
    {
        var aoc = new AnimatorOverrideController(baseController) { name = baseController.name + " (set)" };

        var pairs = new List<KeyValuePair<AnimationClip, AnimationClip>>(aoc.overridesCount);
        aoc.GetOverrides(pairs);                             // key = original, value = null
        for (int i = 0; i < pairs.Count; i++)
        {
            AnimationClip replacement;
            if (swaps.TryGetValue(pairs[i].Key.name, out replacement))
                pairs[i] = new KeyValuePair<AnimationClip, AnimationClip>(pairs[i].Key, replacement);
        }
        aoc.ApplyOverrides(pairs);                           // one rebuild for the whole set
        return aoc;
    }
}
```

- **The key is the original CLIP, not the state.** A clip used by three states is replaced in
  all three; two states that must differ per set need two different placeholder clips in the base
  controller.
- **`ApplyOverrides` once, not the indexer in a loop.** `aoc["Run"] = clip` works, and rebuilds
  the override for every assignment.
- **A name in `swaps` that matches no original changes nothing and says nothing.** After `Make`,
  call `GetOverrides` again and log every pair whose value is still null: those states play the
  base clip.
- **Build the sets once** — at load, or as `.overrideController` assets — and keep them. Creating
  one per swap allocates and leaks until the scene unloads.

## 2. Swapping at runtime

```csharp
anim.runtimeAnimatorController = spearSet;      // an override of the SAME base controller
```

What the swap does to the running Animator depends on what was assigned:

| Assigned | State machine | Parameters |
|---|---|---|
| An override whose base is the controller already running | Stays in its current state | Kept |
| A different controller, or an override of a different base | Restarts at the default state | Back to defaults |

Confirm which row a swap is on rather than assuming it — log three numbers either side:

```csharp
AnimatorStateInfo a = anim.GetCurrentAnimatorStateInfo(0);
Debug.Log($"[ANIM] before state={a.shortNameHash} t={a.normalizedTime:F2} grounded={anim.GetBool(GroundedId)}");
anim.runtimeAnimatorController = next;
anim.Update(0f);                                 // evaluate once so the read is of the new graph
AnimatorStateInfo b = anim.GetCurrentAnimatorStateInfo(0);
Debug.Log($"[ANIM] after  state={b.shortNameHash} t={b.normalizedTime:F2} grounded={anim.GetBool(GroundedId)}");
```

Whichever row it is, **treat four things as lost on every swap** and arrange for it not to
matter:

- **A cross-fade in progress.** Swap between actions, never during one.
- **The pose, when the new clip is a different length.** Normalised time carries over, so a swap
  at 40% of a 1.0 s swing continues at 40% of a 0.6 s one.
- **A trigger that was set and not yet consumed.**
- **Fields on `StateMachineBehaviour` instances.** Values set from code may return to the
  serialised ones, so §3 sets them again after the swap; a window that was open is closed by the
  game's own transition (`reference/events-and-windows.md` §6).

The bridge is why none of this needs special handling: parameters are rewritten on the next
`Update` from the game's state (`reference/parameter-contract.md` §3). A swap that must not
restart the state when it lands on the second row restores it by hand:

```csharp
AnimatorStateInfo s = anim.GetCurrentAnimatorStateInfo(0);
anim.runtimeAnimatorController = next;
anim.Play(s.fullPathHash, 0, s.normalizedTime);  // same state name must exist in the new graph
```

## 3. What travels with what

| Thing | Belongs to | On a swap |
|---|---|---|
| AnimationEvents | The clip | Replaced with the clip: every clip in a set needs its own, at its own times |
| `AttackWindowBehaviour` and other behaviours | The state | Kept, with the base controller's `open` / `close` |
| Blend tree positions and thresholds | The graph | Kept: the replacement clips must be authored for the same positions |
| Transition durations and exit times | The graph | Kept, in normalised time: a longer clip leaves later |
| Avatar masks, layer weights | The graph / the Animator | Kept |

Two consequences for a weapon set:

**Write the events across the whole set in one pass**, so no clip is left silent:

```csharp
foreach (AnimationClip swing in swingClipsOfEverySet)
    ClipEventWriter.SetEvent(swing, "OnAnimEvent", 0.45f, "swing-whoosh");
```

**Set per-weapon window timing on the behaviours after the swap**, from data the game owns:

```csharp
anim.runtimeAnimatorController = set.controller;
foreach (AttackWindowBehaviour w in anim.GetBehaviours<AttackWindowBehaviour>())
    if (w.windowId == "strike") { w.open = set.strikeOpen; w.close = set.strikeClose; }
```

`GetBehaviours` returns the instances of this Animator only, so one sentry's spear timing does
not leak into another's.

## 4. Sprite skins — two tools

| | Override controller | Sprite Library (REQUIRES `com.unity.2d.animation`) |
|---|---|---|
| A skin is | A full set of clips, one per state | A `SpriteLibraryAsset`: the same category / label names, other sprites |
| Clips animate | `SpriteRenderer.m_Sprite` | A `SpriteResolver`'s category and label |
| Cost of a new skin | Rebuild every clip against the new frames | Fill one asset; no clip changes |
| Swap | `anim.runtimeAnimatorController = skin` | `spriteLibrary.spriteLibraryAsset = skin` |
| Right when | Skins differ in timing or frame count | Skins are redraws of the same frames |

Read `Packages/packages-lock.json` for `com.unity.2d.animation` before choosing the second
column; it is part of the 2D feature set and absent from a 3D template. Clips built by
`unity-2d-sprites` → `reference/sprite-animation.md` bind `m_Sprite` directly, which is the first
column: a skin is then the same builder run over another frame folder, and an override that maps
each base clip to its counterpart by name.

For either tool, **every skin must share the base set's canvas, pivot and pixels-per-unit.** A
skin whose frames sit on another ground line makes the character hop on the swap, and no setting
on the Animator can correct art that disagrees about where the feet are.
