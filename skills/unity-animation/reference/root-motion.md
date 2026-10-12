# Root motion — who moves the transform

> Part of the `unity-animation` skill. Exactly one thing writes `transform.position`. Root motion
> is the Animator asking to be that thing. Decide per character, once, and make every other
> candidate — the mover script, the agent, the Rigidbody — either the owner or a listener.

## 1. Three arrangements

| | `applyRootMotion` | `OnAnimatorMove` on the Animator's object | Who moves the transform |
|---|---|---|---|
| **Game moves** | `false` | absent | The mover. Clips are in-place; the Animator only poses |
| **Animator moves** | `true` | absent | The Animator applies each clip's delta directly |
| **Game moves, using the clip's delta** | `true` | present | The script. The Animator computes `deltaPosition` / `deltaRotation` and applies **nothing** |

Defining `OnAnimatorMove` is the switch for the third row: the moment a component beside the
Animator has that method, the Inspector's Apply Root Motion box reads "Handled by Script" and
the transform stops moving unless the method moves it. An empty `OnAnimatorMove` left in a
script is a character that animates on the spot.

The lane run, the side run, the depot and the sorting yard are all row 1: the game's position is
a lane index, a velocity or a cell, and a clip that carried its own translation would argue with
it. Keep `applyRootMotion` off; which Bake Into Pose boxes each clip then wants is §3.

Row 3 is for a character whose stride should set its speed — the gate room's third-person
runner, where feet that slide are visible:

```csharp
[RequireComponent(typeof(Animator))]
[RequireComponent(typeof(CharacterController))]
public sealed class RootMotionMover : MonoBehaviour
{
    Animator _anim;
    CharacterController _cc;
    float _vy;

    void Awake() { _anim = GetComponent<Animator>(); _cc = GetComponent<CharacterController>(); }

    void OnAnimatorMove()
    {
        // The clip supplies the horizontal step; gravity is the game's.
        _vy = _cc.isGrounded ? -2f : _vy + Physics.gravity.y * Time.deltaTime;
        Vector3 step = _anim.deltaPosition;
        step.y = _vy * Time.deltaTime;
        _cc.Move(step);
        transform.rotation *= _anim.deltaRotation;
    }
}
```

The game's state is still the truth in row 3: the bridge writes the parameters that choose the
clip, the clip supplies distance, and the mover applies it through collision. The Animator never
decides *that* the character moves.

## 2. With a Rigidbody

| Body | Do |
|---|---|
| Kinematic | `Animator.updateMode = AnimatorUpdateMode.Fixed`; in `OnAnimatorMove`, `rb.MovePosition(rb.position + anim.deltaPosition)` and `rb.MoveRotation(rb.rotation * anim.deltaRotation)` |
| Dynamic | Same update mode; set `rb.linearVelocity` from `anim.deltaPosition / Time.deltaTime`, keeping the body's own vertical component |

With `AnimatorUpdateMode.Normal` the deltas are per rendered frame while the body steps on the
physics clock: the character stutters at any frame rate that is not the physics rate. `Fixed`
puts the Animator on the physics step, and the bridge then writes parameters in `FixedUpdate`
(`reference/parameter-contract.md` §3).

Writing `transform.position` on an object with a non-kinematic Rigidbody is the two-owners bug
in its plainest form — diagnosing what the body then does is `unity-physics-3d`.

## 3. Whether a clip has root motion at all

Read it, do not infer it from watching:

```csharp
Debug.Log($"{clip.name} hasRootCurves={clip.hasRootCurves} hasMotionCurves={clip.hasMotionCurves} " +
          $"humanMotion={clip.humanMotion} animatorHasRootMotion={anim.hasRootMotion}");
```

| Rig | Root motion comes from | Turned into pose (in place) by |
|---|---|---|
| Humanoid | The body's centre of mass, projected | The clip's **Bake Into Pose** boxes: Root Transform Rotation, Position (Y), Position (XZ) |
| Generic | The bone named as Root Node in the model's Rig tab (`ModelImporter.motionNodeName`) | Leaving Root Node at None, or the same Bake Into Pose boxes |

For a row-1 character, **Position (XZ)** depends on the clip. On a clip that travels, leave it
unbaked: the travel is stored as root motion, and with `applyRootMotion` off it is discarded, so
the body stays over the mover. Baked, the travel is in the bones — the model walks away from its
mover and snaps back each loop, whatever `applyRootMotion` says. Bake XZ only on a clip authored
in place. Bake **Rotation** on every locomotion clip, and **Position (Y)** on everything except a
clip whose height change the game really wants. Check it: play the run with the mover held still
and watch the model — it stays over the mover, or the clip's travel is in its pose.

The same rule from the bridge's side is `unity-3d-controller` → `reference/animator-bridge.md`
§4. Import settings and the Avatar are `unity-rigged-character` → `reference/unity-import.md`.

## 4. Sprites

A frame-clip character has no root motion; the equivalent mistake is a position curve in a
clip. It writes the same transform the mover writes, and whichever ran last that frame wins.
Animate offsets on a `Visual` child instead — `reference/sprite-state-graph.md` §5.

## 5. A NavMesh agent

The agent is a fourth candidate for the transform, and it moves it by default. Two arrangements
work and one hangs: agent moves and the Animator follows a speed float; or the Animator moves
with `agent.updatePosition = false` and `OnAnimatorMove` writes the transform back from
`agent.nextPosition`. Both are written out in `unity-navigation` → `reference/recipes.md` (§5),
and the agent's defaults are in `unity-navigation` → `reference/agent-api.md`.

## 6. Symptoms

| Seen | Cause |
|---|---|
| Animates on the spot | An `OnAnimatorMove` exists and applies nothing; or the clips are baked in place and nothing else moves the transform |
| Slides back to the start of each loop | Position (XZ) baked into the pose on a clip that travels: the bones carry the translation and reset with the loop — leave XZ unbaked so the travel is root motion, discarded with `applyRootMotion` off (§3) |
| Moves twice as far as it should | The mover and the Animator both apply the step: row 2 and a mover script at once |
| Drifts sideways over a long run | Root rotation not baked on a clip that is nearly, not exactly, straight |
| Jitters at some frame rates only | Root motion applied per frame to a body stepping in physics time (§2) |
