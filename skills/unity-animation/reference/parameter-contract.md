# The parameter contract — one writer, once per frame

> Part of the `unity-animation` skill. An Animator parameter is a copy of something the game
> already knows. A copy with one writer is a rendering of the game; a copy with two writers is a
> second state machine, and it disagrees with the first on exactly the frames nobody tests.

## 1. The rule

Every parameter has **one writing script**, and that script is a bridge: it reads the game's state
and writes the Animator. Gameplay code never calls `SetBool`, and never calls `GetBool`,
`GetCurrentAnimatorStateInfo` or `IsInTransition` to make a decision.

| Smell | What it is | Replace with |
|---|---|---|
| `anim.SetTrigger("Jump")` inside the input handler | The Animator told about an intention | The game sets its own state; the bridge copies `Grounded` |
| `if (anim.GetCurrentAnimatorStateInfo(0).IsName("Attack")) return;` | Gameplay waiting on a picture | A game-side `attacking` flag, closed by a named event (`reference/events-and-windows.md`) |
| `SetBool` for the same name in two files | Two writers | One bridge; the other file changes the game's state |
| A parameter set once in `Start` or on change only | A copy that goes stale | Written every frame (§3) |
| A clip curve with the same name as a float parameter | The clip is a writer too | Rename one, or stop writing it from script |

## 2. Types, and why a trigger queues

| Type | Use for | Never for |
|---|---|---|
| Bool | A condition that holds: `Grounded`, `Moving`, `Aiming` | An instant |
| Float | A continuous quantity: `MoveBlend`, `VelY`, `FaceX` | A flag (`> 0.5` conditions) |
| Int | A small enumeration the graph branches on: weapon slot, lane | Anything a bool states more plainly |
| Trigger | An instant the graph can act on **now**: `Hurt` from Any State | An instant the graph may not be able to take yet |

A trigger is a bool that the Animator resets **when a transition consumes it**, and not before.
Set it while no transition that reads it is reachable and it stays set — for a frame or for ten
seconds — then fires the moment one becomes reachable. That is the "attack plays by itself after
landing" bug: `Attack` was set in mid-air, where no transition takes it, and waited.

Three ways out, in order of preference:

1. Make the transition reachable from everywhere it can be raised (Any State), so it is consumed
   on the frame it is set.
2. Use a Bool the bridge derives from game state — `Attacking` is true exactly while the game
   says so, and cannot queue.
3. Call `ResetTrigger(id)` from the bridge when the game state that made it meaningful ends.

## 3. The bridge

One component beside the Animator. It writes every parameter every frame, which is what makes
the copy self-healing: a pooled sentry that is disabled and re-enabled comes back with its
Animator in the default state and every parameter at its default (unless
`Animator.keepAnimatorStateOnDisable` is true), and the next `Update` puts them right.

```csharp
using UnityEngine;

// The only script that writes this Animator. Runs after gameplay so it copies this frame's state.
[DefaultExecutionOrder(100)]
[RequireComponent(typeof(Animator))]
public sealed class RunAnimatorBridge : MonoBehaviour
{
    static readonly int GroundedId  = Animator.StringToHash("Grounded");
    static readonly int MoveBlendId = Animator.StringToHash("MoveBlend");
    static readonly int HurtId      = Animator.StringToHash("Hurt");

    public RunController run;              // replace with your game's state owner
    public float blendDamp = 0.1f;

    Animator _anim;

    void Awake()
    {
        _anim = GetComponent<Animator>();
        Require(GroundedId, "Grounded");
        Require(MoveBlendId, "MoveBlend");
        Require(HurtId, "Hurt");
    }

    void OnEnable()  { run.Hit += OnHit; }             // replace with your game's event
    void OnDisable() { run.Hit -= OnHit; }

    void Update()
    {
        _anim.SetBool(GroundedId, run.Grounded);
        float blend = Mathf.InverseLerp(run.MinSpeed, run.MaxSpeed, run.Speed);
        _anim.SetFloat(MoveBlendId, blend, blendDamp, Time.deltaTime);
    }

    // An instant has no value to copy each frame, so it arrives as an event from the game.
    void OnHit() { _anim.SetTrigger(HurtId); }

    void Require(int id, string name)
    {
        foreach (AnimatorControllerParameter p in _anim.parameters)
            if (p.nameHash == id) return;
        Debug.LogError("[ANIM] " + name + " is not a parameter of " +
                       _anim.runtimeAnimatorController.name, this);
    }
}
```

Why each line is the way it is:

- **`Animator.StringToHash` once, in a `static readonly int`.** The string overloads hash on every
  call. More usefully, the ids become the one list of names this script writes.
- **`Require` at `Awake`.** Setting a parameter the controller does not have logs a warning and
  does nothing else — a renamed parameter is a character frozen in one pose and a line in a log
  nobody reads. The check turns it into an error on the first frame.
- **`Update`, not `FixedUpdate` or `LateUpdate`.** The Animator evaluates after `Update` and
  before `LateUpdate`, so a value written in `Update` is used this frame and one written in
  `LateUpdate` next frame. When `Animator.updateMode` is `AnimatorUpdateMode.Fixed` the Animator
  evaluates in the physics step instead: write from `FixedUpdate` there.
- **Game state read, never cached.** `run.Grounded` is read every frame from the owner.

## 4. Damped floats

```csharp
_anim.SetFloat(id, target, dampTime, Time.deltaTime);
```

This moves the stored value towards `target`, reaching most of the way in `dampTime` seconds. It
is a per-frame step, not a tween: **call it every frame or the value stops part way.** A damped
write followed by an undamped write of the same parameter elsewhere is two writers, and the
blend snaps.

| Parameter drives | Damp | Why |
|---|---|---|
| A blend tree position (`MoveBlend`, `MoveX`, `MoveY`) | 0.08–0.15 s | Hides velocity noise; a gait that changes in one frame pops |
| A transition condition (`VelY > 0`) | 0 | A damped value crosses the threshold late, and the state follows late |
| Sprite facing (`FaceX`, `FaceY`) | 0 | Frames do not blend; damping only delays the swap |
| A playback rate (`MoveSpeed`) | 0 | It has to match the ground speed this frame, or the feet slide |

## 5. The audit

`resources/Editor/AnimatorParamAudit.cs` joins the controller with a text scan of the scripts:

```bash
unity command eval 'return AnimatorParamAudit.Json(UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEditor.Animations.AnimatorController>("Assets/Animations/Runner.controller"));'
```

```json
{"controller":"Assets/Animations/Runner.controller","scanRoot":"Assets","filesScanned":41,
 "parameters":[
  {"name":"Grounded","type":"Bool","verdict":"ok","graph":["Base Layer/Move→Jump","Base Layer/Jump→Move"],
   "writers":[{"file":"Assets/Scripts/RunAnimatorBridge.cs","line":33,"call":"SetBool"}],"readers":[]},
  {"name":"Hurt","type":"Trigger","verdict":"multi-writer","graph":["Hurt/None→Hurt"],
   "writers":[{"file":"Assets/Scripts/RunAnimatorBridge.cs","line":39,"call":"SetTrigger"},
              {"file":"Assets/Scripts/HazardHit.cs","line":18,"call":"SetTrigger"}],"readers":[]}],
 "undeclaredInGraph":[],"setByScriptsNotInController":[],"problems":1}
```

| Verdict | Meaning | Fix |
|---|---|---|
| `ok` | One writing file, and the graph reads it | — |
| `no-writer` | A transition or tree reads it; no script sets it | It sits at its default forever: wire it in the bridge or delete the condition |
| `multi-writer` | More than one file sets it | Keep the bridge; the others change game state |
| `unread` | Scripts set it; nothing reads it | Delete the parameter and the writes |
| `dead` | Neither | Delete it |

`readers` lists `GetBool` / `GetFloat` / `GetInteger` calls: each is gameplay reading the picture,
and belongs on the game's own state. `setByScriptsNotInController` is where typos land.

The scan is text. It resolves a string literal and an identifier assigned from
`Animator.StringToHash("…")`; it cannot see a name built at runtime, and it attributes a write to
every controller that has a parameter of that name. Read the output as a list of files to open.
