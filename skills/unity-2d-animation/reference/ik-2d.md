# 2D IK — the solver has the last word on a chain

> Part of the `unity-2d-animation` skill. IK here is not a layer inside the Animator. It is a
> component that runs in `LateUpdate`, after the clip has posed every bone, and overwrites the
> rotations of the chains it owns. A clip and a solver on the same bones do not blend unless the
> solver's weight says so — at weight 1 the keys on that chain are dead.

## 1. The pieces

```
Runner_GO              IKManager2D          weight 1, the ordered solver list
├─ bone_root …
├─ LegL Solver         LimbSolver2D         effector: foot_l bone   target: LegL Solver_Target
│  └─ LegL Solver_Target                    the Transform gameplay or a clip moves
└─ ArmR Solver         LimbSolver2D
   └─ ArmR Solver_Target
```

| Piece | Type (`UnityEngine.U2D.IK`, assembly `Unity.2D.IK.Runtime`) | Holds |
|---|---|---|
| Manager | `IKManager2D` | `solvers` (ordered), `weight`, `alwaysUpdate`; `AddSolver`, `RemoveSolver`, `UpdateManager()` |
| Solver | `LimbSolver2D`, `CCDSolver2D`, `FabrikSolver2D` — all `Solver2D` | one chain, `weight`, `constrainRotation`, `solveFromDefaultPose` |
| Chain | `IKChain2D`, from `solver.GetChain(0)` | `effector`, `target`, `transformCount`, `transforms` |

Set-up in the Inspector: add **IK Manager 2D** to the character root; **+** on its IK Solvers
list adds a solver object as a child (named `New LimbSolver2D` — rename it for the limb); drag
the chain's tip bone into the solver's **Effector**;
**Create Target** makes the target under the solver, at the effector. A solver with no target
does nothing.

The effector is the Transform at the **tip** of the chain: the hand or foot bone itself, or an
empty placed at the end of the last bone when the chain has to reach with its end and not with
its last joint.

Do this on the Prefab Variant, not on the generated prefab (`reference/psd-to-rig.md` §3).

## 2. Which solver

| Solver | Chain | Fits | Costs |
|---|---|---|---|
| **Limb** | exactly three Transforms: the effector and its two ancestors | arms and legs — two segments and a hinge | one closed-form solve; the cheapest |
| **Chain (CCD)** | *Chain Length* Transforms up from the effector | tails, tentacles, a spine leaning toward a point, a crane arm | *Iterations* × chain length. Tends to curl the tip first |
| **Chain (FABRIK)** | the same | the same chains when the target moves fast or the pose must spread along the whole chain | fewer iterations to converge than CCD; each one costlier when bones have limits |

Default to Limb for every arm and leg. Reach for a chain solver only for more than two
segments.

Limb specifics:

- **`flip` picks the side the joint bends to.** A leg bending backwards is this checkbox, not a
  weight problem. Mirroring the character by the root's scale keeps the bend correct; a flip
  set per facing in code is a sign the mirror is being done on a bone.
- **A target out of reach straightens the limb toward it.** There is no stretch. Keep targets
  inside upper length + lower length, or expect the knee to lock.
- The effector needs two ancestors; with fewer the chain length is 0 and the solver is invalid.

Chain specifics, with the component defaults:

| Property | Default | Range | Meaning |
|---|---|---|---|
| `iterations` | 10 | 1–50 | passes per frame; the first knob to lower on a crowd |
| `tolerance` | 0.01 | 0.001–0.1 | stop early when the tip is this close, in world units |
| `velocity` (CCD only) | 0.5 | 0–1 | how far each pass moves toward the solution; low values converge smoothly over frames |

Common to all three:

| Property | Default | Meaning |
|---|---|---|
| `weight` | 1 | 0 leaves the clip's pose; 1 is the solved pose. Multiplied by the manager's `weight` |
| `constrainRotation` | on | the effector takes the target's rotation — rotate the target to tilt a foot or a hand |
| `solveFromDefaultPose` | on | each frame the chain is reset to its stored default before solving, so the result does not depend on last frame. Off: solve from the pose the clip left, which lets the clip shape a chain solver's curl |

## 3. Order

Solvers run top to bottom in the manager's list, and each sees what the ones above did. Put a
solver above every solver whose chain hangs from its bones: spine before arms, arm before a
held prop's chain. Two solvers whose chains share a bone fight; the lower one wins that bone.

Within the frame:

| Order | Who | Does |
|---|---|---|
| Animation update | Animator | writes bone rotations and resolver keys from the clip |
| `LateUpdate`, −20 | `SpriteResolver` | swaps sprites |
| `LateUpdate`, −10 | `IKManager2D` | every solver overwrites its chain |
| `LateUpdate`, 0 | game scripts | **too late to move a target for this frame** |
| `LateUpdate`, +10 | `SpriteSkin` | reads the Transforms and deforms |

A script that places IK targets runs in `LateUpdate` with `[DefaultExecutionOrder(-15)]`.
`Update` is early enough only when the target comes from gameplay data alone; anything that
reads a Transform the clip drives sees last frame's pose there. Placed at the default order,
the limb lags its target by one frame — visible as feet that trail on a moving platform.

## 4. IK with animation clips

Three arrangements, in order of how often they are right:

1. **The clip animates the target.** Key the target Transform, not the limb bones. The solver
   turns two position curves into a whole leg, a foot planted in the clip stays planted while
   the hips bob, and gameplay can still move the same target. This is the reason to rig with
   IK at all.
2. **The clip animates the bones, gameplay blends IK in.** The run cycle is keyed on the bones
   with the solver at `weight` 0. Reaching for the gate switch ramps the arm solver to 1 over
   0.1 s and back. Below 1 the solver stores the clip's pose first and blends toward its own
   solution, so the ramp is a real cross-fade.
3. **The clip animates the weight.** `weight` is a serialised float on the solver and can be
   keyed, for a clip that hands a limb to IK for part of its length.

What does not work: keys on a chain's bones **and** the solver at weight 1. The solver discards
them every frame. The clip looks right in a preview without the manager and wrong in play.

Bake when a clip has to play without solvers — on a low-budget sentry, say: *Animation window →
select the bones → Add Keyframe* at each frame with the manager enabled, then remove the
manager from that character.

States, parameters and the writer that sets a weight from game state belong to the Animator side:
`unity-animation` → `reference/parameter-contract.md`.

## 5. Feet on a slope, in brief

The side run's roofs tilt. A foot target that follows the clip floats above a rising roof and
sinks into a falling one.

```csharp
// On the runner. Moves each foot target onto the roof under it before IKManager2D runs.
[DefaultExecutionOrder(-15)]
public sealed class FootTargets2D : MonoBehaviour
{
    [SerializeField] UnityEngine.U2D.IK.Solver2D leftLeg, rightLeg;
    [SerializeField] Transform leftRest, rightRest;     // where the clip wants each foot: keyed Transforms
    [SerializeField] LayerMask ground;
    [SerializeField] float probeUp = 0.5f, probeDown = 0.6f, soleHeight = 0.05f;
    public bool Grounded;                               // written by the controller, never guessed here

    void LateUpdate()
    {
        Place(leftLeg, leftRest);
        Place(rightLeg, rightRest);
    }

    void Place(UnityEngine.U2D.IK.Solver2D leg, Transform rest)
    {
        Transform target = leg.GetChain(0).target;
        Vector2 origin = (Vector2)rest.position + Vector2.up * probeUp;
        RaycastHit2D hit = Physics2D.Raycast(origin, Vector2.down, probeUp + probeDown, ground);

        bool plant = Grounded && hit.collider != null;
        leg.weight = Mathf.MoveTowards(leg.weight, plant ? 1f : 0f, Time.deltaTime / 0.1f);
        if (!plant) { target.SetPositionAndRotation(rest.position, rest.rotation); return; }

        // Never put the foot below where the clip has it: the swing phase stays in the air.
        float y = Mathf.Max(hit.point.y + soleHeight, rest.position.y);
        target.SetPositionAndRotation(new Vector3(rest.position.x, y, rest.position.z),
                                      Quaternion.FromToRotation(Vector3.up, hit.normal));
    }
}
```

- The clip keys `leftRest` and `rightRest`, two empties under the root, not the targets. The
  script copies or corrects them onto the real targets.
- `Grounded` comes from the controller's own ground test (`unity-2d-controller`); the weight
  drops to 0 in the air so the jump clip is untouched.
- The ray, its layer mask and one-way roofs are `unity-physics-2d` → `reference/queries-2d.md`.
- When the lower foot cannot reach, lower the hips by the shortfall before the solvers run;
  the legs then both reach. The 3D counterpart, with pelvis offset, is
  `unity-animation` → `reference/ik-and-rigging.md`.

## 6. Cost and culling

`IKManager2D.alwaysUpdate` is on by default. Off, the solvers run only while a `SpriteSkin`
driven by one of their chains is visible — turn it off on every sentry. A character that never
needs a limb placed at runtime needs no manager: bake its clips (§4).

In the Profiler the work sits under `IKManager2D.UpdateManager`, then `Solver2D.UpdateIK`
per solver.

## Checks

- Every solver has a target: `solver.allChainsHaveTargets` is true and `solver.isValid` is true
  after the first frame, for each entry of `manager.solvers`.
- No clip keys a bone of a chain whose solver sits at weight 1 while that clip plays. In the
  Animation window, the chain's bones show no curves in such clips.
- A script that moves targets runs in `LateUpdate` with an execution order below −10.
- Step the runner across the steepest roof in the level with the Scene view on the feet: no
  frame with a sole under the surface, no knee bending forwards.
- The limb's bend side is right in both facings without code touching `flip`.
