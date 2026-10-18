# IK and rigging — correcting the pose after the clip has spoken

> Part of the `unity-animation` skill. IK is the last writer of the pose, and it runs after the
> state machine: it can plant a foot or put a hand on a switch, and it cannot change what state
> the character is in. Keep it that way — the IK target comes from the game's world, the IK
> weight comes from the game's state, and nothing in gameplay reads where a hand ended up.

## 1. `OnAnimatorIK` — three conditions, all silent

The callback is never invoked, and nothing is logged, unless all three hold:

| Condition | Check |
|---|---|
| The Avatar is Humanoid | `animator.isHuman` — a Generic rig never gets the callback |
| The layer has IK Pass on | The cog on the layer in the Animator window, or the script below |
| The script is on the Animator's GameObject | Not a parent, not a child |

```csharp
// AnimatorController.layers returns a copy: edit, then assign the array back.
AnimatorControllerLayer[] layers = controller.layers;
layers[0].iKPass = true;                 // lowercase i, capital K
controller.layers = layers;
EditorUtility.SetDirty(controller);
```

`OnAnimatorIK(int layerIndex)` is called once per layer with IK Pass on. Return early for every
layer but the one you mean, or a two-layer controller applies the offsets twice.

Where it sits in the frame:

```
Update                    the bridge writes parameters and IK weights
  state machine, clips    the pose the clip asked for
  OnAnimatorMove          root motion — reference/root-motion.md
  OnAnimatorIK            read the clip's goals, write corrected ones
  bones written
LateUpdate                the pose is final; cameras and attached props read it here
```

Goals and weights are **reset every frame**. Set the position, the rotation and both weights on
every call; a goal set once in `Start` does nothing.

## 2. Hands

```csharp
void OnAnimatorIK(int layerIndex)
{
    if (layerIndex != 0) return;

    // _reach is 0..1, written by the bridge while the game says the runner is using the switch.
    _anim.SetIKPositionWeight(AvatarIKGoal.RightHand, _reach);
    _anim.SetIKRotationWeight(AvatarIKGoal.RightHand, _reach);
    _anim.SetIKPosition(AvatarIKGoal.RightHand, gateSwitch.handle.position);
    _anim.SetIKRotation(AvatarIKGoal.RightHand, gateSwitch.handle.rotation);

    // Without a hint the elbow picks its own side, and it picks through the torso.
    _anim.SetIKHintPositionWeight(AvatarIKHint.RightElbow, _reach);
    _anim.SetIKHintPosition(AvatarIKHint.RightElbow, transform.TransformPoint(0.4f, 1.1f, -0.2f));
}
```

- **Ramp the weight, in game time.** 0 → 1 over 0.15–0.25 s reads as a reach; a step from 0 to 1
  is a teleporting arm.
- **The goal is the wrist.** Author the handle transform where the wrist goes, rotated the way
  the palm faces — not at the surface the fingers touch.
- **Reach is limited by the arm.** A target further than shoulder-to-wrist leaves the arm
  straight and short of it; the game stands the runner inside reach before raising the weight.
- **The switch opening the gate is the game's event**, raised by `GateSwitch` when the
  interaction resolves. The hand arriving is not the trigger.

Head and eyes tracking a point is `SetLookAtWeight` / `SetLookAtPosition` in the same callback:
`unity-navigation` → `reference/recipes.md` has it against an agent's steering target.

## 3. Feet — `resources/FootIK.cs`

Two raycasts per frame, one per foot, straight down from above where the clip put the foot:

1. Read the clip's goal: `GetIKPosition(AvatarIKGoal.LeftFoot)`.
2. Cast down from `castUp` above it. The hit is the ground under that foot.
3. Goal position = hit point + the rig's own sole height (`Animator.leftFeetBottomHeight`) + the
   height the clip was holding the foot above the character's ground plane — so a stride still
   lifts the foot.
4. Goal rotation = the clip's rotation tilted onto the hit normal.
5. Lower the hips (`bodyPosition`) by the deeper of the two reaches, clamped. Without this the
   leg on the low side has to stretch beyond its length and the foot floats.
6. Smooth the weight and the hip offset over about 0.1 s; raw ray hits flicker on rough ground.

| Field | Default | Tune when |
|---|---|---|
| `groundMask` | everything | Always — exclude the character's own layer, or a foot plants on its own collider |
| `castUp` / `castDown` | 0.5 / 0.45 | Steps taller than `castDown` are not reached: the foot stays with the clip |
| `maxHipDrop` | 0.35 | Hips sink too far on stairs → lower it |
| `smoothTime` | 0.1 | Feet lag on fast slopes → lower; feet jitter → raise |
| `planted` | true | **Written by the bridge** from the game's grounded state |

`planted` is the contract. When the game says the runner is airborne the feet go back to the
clip, on that frame, whatever the rays hit. A foot that decides for itself from a raycast is a
second opinion about `Grounded`.

Three things this is not:

- **Not the Foot IK tick on a state** (`AnimatorState.iKOnFeet`). That one pulls the feet back to
  where the source animation had them after retargeting; it knows nothing about the ground.
- **Not a ground check.** The capsule or the controller decides grounded; the rays only dress it.
- **Not free on a crowd.** Two raycasts and an IK solve per character per frame: leave it off
  sentries the player cannot see up close.

## 4. Animation Rigging — when the package is worth it

REQUIRES `com.unity.animation.rigging`. Read `Packages/packages-lock.json` before writing a
`using UnityEngine.Animations.Rigging;` line.

| Stay with `OnAnimatorIK` | Take the package |
|---|---|
| Humanoid rig | **Generic rig** — the callback never runs for it |
| Feet, hands, look-at | Aim a spine chain or a turret, a tail, a prop parented to a hand and released |
| One or two goals | Several constraints in a fixed order, with weights animated by clips |
| No extra components | A `RigBuilder`, a `Rig` and one component per constraint, set up in the hierarchy |

```
Sentry                Animator, RigBuilder (layers → AimRig)
├── Armature …
└── AimRig            Rig                      weight 0..1
    ├── HeadAim       MultiAimConstraint       constrained object = head bone
    └── ArmIK         TwoBoneIKConstraint      root / mid / tip, target, hint
```

```csharp
using UnityEngine;
using UnityEngine.Animations.Rigging;

// Runtime wiring for a rig assembled in code. In the Editor the same fields are set by hand.
public static class SentryRig
{
    public static Rig AddArmIK(Animator anim, Transform upperArm, Transform foreArm, Transform hand,
                               Transform target, Transform hint)
    {
        var rigGo = new GameObject("AimRig");
        rigGo.transform.SetParent(anim.transform, false);
        var rig = rigGo.AddComponent<Rig>();

        var ikGo = new GameObject("ArmIK");
        ikGo.transform.SetParent(rigGo.transform, false);
        var ik = ikGo.AddComponent<TwoBoneIKConstraint>();
        ik.data.root = upperArm;                 // data is a ref property: assign through it
        ik.data.mid = foreArm;
        ik.data.tip = hand;
        ik.data.target = target;
        ik.data.hint = hint;

        var builder = anim.GetComponent<RigBuilder>();
        if (builder == null) builder = anim.gameObject.AddComponent<RigBuilder>();
        builder.layers.Add(new RigLayer(rig));
        builder.Build();                         // required after any structural change
        return rig;
    }
}
```

Rules that carry over unchanged:

- **`Rig.weight` is written by the bridge**, from game state, like any parameter. A sentry's aim
  rig goes to 1 while `SentryBrain` (`unity-game-ai`) reports `Sees` and to 0 when it does not.
- **Targets are transforms the game moves in `Update`.** Constraints read them when the
  animation evaluates, after `Update`.
- **Constraints run after the Animator, in hierarchy order under the `Rig`.** Aim first, then
  the two-bone IK that depends on the aimed chest.
- **`RigBuilder.Build()` after adding or removing a rig or a constraint at runtime.** Changing a
  weight or moving a target needs nothing.
- **It replaces `OnAnimatorIK`, it does not stack with it.** Two solvers on one arm fight; pick
  one per limb.

The rig's bones, Avatar and import settings are `unity-rigged-character` →
`reference/unity-import.md`.

## 5. Animation Jobs — IK with neither the callback nor the package

A Generic rig in a hand-built `PlayableGraph` has no `OnAnimatorIK`, and the Animation Rigging
package adds a `RigBuilder` the graph does not need. An `IAnimationJob` in an
`AnimationScriptPlayable` after the mixer reads and writes bones through
`TransformStreamHandle`s bound with `animator.BindStreamTransform`, with cross-frame state in
`NativeArray`s. That is how a foot lock that holds planted feet within millimetres at 7 m/s and a
racket face put on a ball were built: `reference/foot-lock-and-prop-ik.md`, with
`resources/AnimJobMath.cs`, `resources/FootLockJob.cs` and `resources/TwoBoneIKJob.cs`. The graph
they run in is `reference/sim-driven-animation.md`.

Two lessons carry back to `OnAnimatorIK` and the package unchanged: an IK weight or target that
is continuous in position but not in velocity pops for one frame, and a knee or elbow bent by a
hint flips when the limb straightens — store a hinge axis instead.
