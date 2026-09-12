# Driving the rig as a gameplay object

Two traps appear the moment the rigged character stops being scenery and starts colliding,
attacking or being hit. Both look like the model is broken; neither is.

**A `SkinnedMeshRenderer`'s bounds are its BIND POSE, and the bind pose is a T-pose.**
So `Renderer.bounds` on a character is **arm-span wide**. Anything that measures the mesh to size a
gameplay volume — a hitbox, a spawn footprint, a lane occupancy check — gets a box nearly as wide as
the character is tall. In a three-lane courier run at 1.3-unit spacing, a hurt box sized that way
spills into the neighbouring lanes: the runner dodges a hazard, is clear on screen, and still loses
a heart.

Author humanoid volumes as explicit constants (~0.5 wide × 1.0 tall × 0.6 deep for a 1.0-unit
character), expose them in the inspector, and regression-test the **world-space** width against the
lane pitch — colliders are LOCAL, so divide by the root scale the prefab normalisation applies:

```csharp
// normalisedHeight: the world height the prefab normalisation scales the character to
float scale = normalisedHeight / Mathf.Max(0.001f, baseColliderHeight);
box.size   = hitBox / scale;
box.center = new Vector3(0f, hitBox.y * 0.5f / scale, 0f);   // rises from the feet, not centred
```

**Never put `[RequireComponent(typeof(Animator))]` on the root of an imported character.**
The Animator that matters lives on the model CHILD. RequireComponent silently adds a second, empty
one to the root, `GetComponent<Animator>()` finds that one first, and every `SetTrigger` logs
*"Animator is not playing an AnimatorController"* while the character stands still. Resolve the
first Animator that actually has a controller bound:

```csharp
foreach (Animator a in GetComponentsInChildren<Animator>(true))
    if (a.runtimeAnimatorController != null) return a;
```

> **`GetComponentsInChildren<T>()` returns empty for an inactive hierarchy** unless you pass
> `includeInactive: true`. Pooled characters are configured while still deactivated, so without the
> flag the setup silently does nothing — and the failure only shows on the second spawn.

Rotate the **model child**, not the root, when an animation needs re-aiming (a lane-change dive that
travels sideways relative to the character, say). Rotating the root drags the collider with it and
changes the hit box mid-action.

---

## Why a hit box sized from the renderer is arm-span wide

> **`SkinnedMeshRenderer.updateWhenOffscreen` defaults to `false`.** That is the whole cause.
> With it off, Unity does not recompute the skinned bounds from the current pose; it reports a
> precomputed volume derived from the **bind pose** — which for a Mixamo-rigged humanoid is a
> T-pose, arms out.

For a Mixamo-rigged humanoid, e.g.:

| | size |
|---|---|
| `SkinnedMeshRenderer.bounds` | **(1.55, 1.81, 0.60)** |
| `sharedMesh.bounds` (the asset, bind pose) | (1.55, 1.70, 0.41) |
| `updateWhenOffscreen` | `false` |

The **1.55** is the number that matters: against a 1.3-unit lane, a hit box sized from the
renderer is **wider than the lane the character is standing in** — it collides with hazards in the
next lane. Note also that `bounds` is not simply `sharedMesh.bounds`; it is the bind-pose volume
transformed, so comparing the two does not reveal the problem either.

Setting `updateWhenOffscreen = true` makes `bounds` track the pose, at a per-frame cost on every
such renderer. **Do not turn it on just to measure.** Author the gameplay volume as a constant —
that is the rule this file opens with, and this is why.

## Four collider traps that are silent on a character rig

The bind-pose bounds trap is the headline one, covered above. Four more fail the same way — the
scene looks correct and the physics does not. General PhysX triage is `unity-physics-3d`; these
are the ones a character rig hits.

- **Non-uniform scale on a parent breaks a `SphereCollider`.** PhysX has no ellipsoid, so the
  sphere takes the **largest** axis — under a `(1, 3, 1)` parent, a unit sphere's collider
  bounds come out `(3, 3, 3)` while the mesh renders `(1, 3, 1)`. Uniformly too big in
  every direction, and the gizmo and the mesh both look right. A `BoxCollider` under the same
  parent scales correctly. Fix it at the source — apply scale in the DCC tool (Blender:
  `Ctrl+A → Scale`) so the FBX arrives at `(1, 1, 1)` — not by compensating on the collider.
  Full triage: `unity-physics-3d` §5.

- **A child `Rigidbody` cuts the compound body in half.** A parent `Rigidbody` governs every
  collider beneath it *until it meets another `Rigidbody`*. Adding one to a held prop or a hit
  volume detaches everything below it from the character's body without any warning.

- **A ragdoll that explodes on the first frame has overlapping colliders in its start pose** —
  one frame of depenetration turns overlap into velocity. The only real fix is to **shrink the
  colliders**. Joint limits, joint projection, mass ratios and `Enable Collision` are the
  standard misdiagnoses and none of them is the cause. Confirm with
  `Window > Analysis > Physics Debugger`, which draws the overlapping pairs.

- **A `CharacterController` never raises `OnCollisionEnter`.** Use `OnControllerColliderHit`.
  Do not "fix" it by adding a `Rigidbody` — `CharacterController` and rigidbody dynamics are
  mutually exclusive movement models, and running both gives you neither.
