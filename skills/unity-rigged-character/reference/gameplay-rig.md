# Driving the rig as a gameplay object

Two traps appear the moment the rigged character stops being scenery and starts colliding,
attacking or being hit. Both look like the model is broken; neither is.

**A hit box sized from a `SkinnedMeshRenderer`'s bounds is not the body on screen.** The
renderer's box is fixed at import, carried by the root bone, and does not follow the pose
(below), so it can be far wider or deeper than the body in the pose on screen. Anything that sizes a gameplay volume from the renderer — a hitbox, a spawn
footprint, a lane occupancy check — inherits that box. In a three-lane courier run at 1.3-unit
spacing, a hurt box sized that way can spill into the neighbouring lanes: the runner dodges a
hazard, is clear on screen, and still loses a heart.

Author humanoid volumes as explicit constants (~0.5 wide × 1.0 tall × 0.6 deep for a 1.0-unit
character), expose them in the inspector, and regression-test the **world-space** width against
the lane pitch — colliders are LOCAL, so divide by the root scale the prefab normalisation
applies:

```csharp
// normalisedHeight: the world height the prefab normalisation scales the character to
float scale = normalisedHeight / Mathf.Max(0.001f, baseColliderHeight);
box.size   = hitBox / scale;
box.center = new Vector3(0f, hitBox.y * 0.5f / scale, 0f);   // rises from the feet, not centred
```

**Never put `[RequireComponent(typeof(Animator))]` on the root of an imported character.** The
Animator that matters lives on the model CHILD. RequireComponent silently adds a second, empty one
to the root, `GetComponent<Animator>()` finds that one first, and every `SetTrigger` logs
*"Animator is not playing an AnimatorController"* while the character stands still. Resolve the
first Animator that actually has a controller bound:

```csharp
foreach (Animator a in GetComponentsInChildren<Animator>(true))
    if (a.runtimeAnimatorController != null) return a;
```

> **`GetComponentsInChildren<T>()` returns empty for an inactive hierarchy** unless you pass
> `includeInactive: true`. Pooled characters are configured while still deactivated, so without
> the flag the setup silently does nothing — and the failure only shows on the second spawn.

Rotate the **model child**, not the root, when an animation needs re-aiming (a lane-change dive
that travels sideways relative to the character, say). Rotating the root drags the collider with
it and changes the hit box mid-action.

---

## What the renderer's bounds are

Three boxes, and only one of them is the culling box:

| Box | What it is | Changes with the pose |
|---|---|---|
| `sharedMesh.bounds` | the bind-pose mesh, in mesh space | never; not used for culling |
| `SkinnedMeshRenderer.localBounds` | the culling box, relative to `rootBone` (the hips), set at import | no, while Update When Offscreen is off |
| `Renderer.bounds` | `localBounds` carried to world space by the root bone | it moves with the hips, but is refreshed only when the renderer is culled or rendered |

- **Read bounds after a rendered frame.** Straight after an Animator evaluate, `bounds` still
  holds the previous frame's value; after the next `Camera.Render()` it has moved with the hips.
- **`updateWhenOffscreen = true`** recomputes `localBounds` from the bones every frame, at a
  per-frame cost on every such renderer. That box is still built from the bones and is looser
  than the skinned vertices.
- **A pose that swings far outside the box** — a long reach, a prop swing — can be culled while
  part of it is on screen. Check it: at the widest frame of each such clip, compare
  `localBounds` with the extents of `SkinnedMeshRenderer.BakeMesh`. If the baked mesh sticks out,
  widen `localBounds` in code (once, at spawn), or turn Update When Offscreen on for that renderer.

**Do not size a gameplay volume from any of the three.** Author it as a constant — that is the
rule this file opens with, and this is why.

## Colliders on a rig

General PhysX triage is `unity-physics-3d`: a `SphereCollider` under a non-uniformly scaled
parent, a child `Rigidbody` that cuts the compound body, a ragdoll that explodes on its first
frame (§5), and a `CharacterController` that never raises `OnCollisionEnter` (§1). The lines
specific to a character:

- **Visual children keep no colliders.** An imported model's colliders share the root's
  `Rigidbody` and merge into one compound body, so the character collides with its own
  accessories. Strip them from the model child; the root's collider is the hit box.
- **A held prop or hit volume that stops following the body** has a `Rigidbody` of its own —
  §5 of `unity-physics-3d`. Remove it, or make the split deliberate.
- **Fix scale at the source.** The FBX imports at `(1, 1, 1)` on the root and the armature;
  anything else is unapplied scale in the DCC file or an export without `FBX_SCALE_ALL`, fixed
  there and re-exported, not with the importer's Scale Factor.
