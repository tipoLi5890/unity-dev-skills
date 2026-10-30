# Colliders that follow a bone

> Part of the `unity-physics-2d` skill. Hurtboxes and hitboxes on a skinned 2D character
> (`unity-2d-animation`): where the collider lives, which body it belongs to, and when its pose
> is the one the physics step sees.

A 2D Animation bone is a plain `Transform`. Physics never sees the skinned mesh, only colliders,
so a limb that should be hit or should hit carries its own collider on that bone's hierarchy.

## Placement and shape

- **One child GameObject per box, parented to the bone**, with the collider on the child. The child
  keeps the box's offset and size editable without touching the bone, and a re-rig that renames a
  bone moves one parent link instead of a component.
- **Capsule, box or circle, sized at the bind pose.** Not a `PolygonCollider2D` generated from the
  sprite: it traces the unskinned outline, and `SpriteSkin` deformation never reaches it.
- **Keep the count small** — torso, head, the striking limb. Every moving shape is rebuilt each
  step it moves.

## Which body owns them

A collider attaches to the nearest `Rigidbody2D` up the hierarchy
([`bodies-and-simulation.md`](bodies-and-simulation.md)), so every bone collider joins the
character's root body. That has three consequences:

| Consequence | What to do |
|---|---|
| A solid limb collider changes the body's shape, and the runner trips on its own swinging foot | Hurtboxes and hitboxes are **triggers**; the body's one capsule does the walking |
| Colliders on the same body never report contacts with each other | A character cannot hit itself, with no filtering code |
| A second `Rigidbody2D` on a bone cuts that box out of the root body and fights the Animator | Do not add one; one body per character |

Give the boxes their own layers (`Hitbox`, `Hurtbox`) and turn on only `Hitbox × Hurtbox` in the
matrix ([`layers-and-matrix.md`](layers-and-matrix.md)). A sentry's swing then reports only the
runner's hurtboxes, never a wall or a pickup.

## Pose timing

- **Set the Animator's Update Mode to Fixed** (`AnimatorUpdateMode.Fixed`). The bones are then
  posed in the physics step, and the trigger tests the pose the frame shows. On Normal the step tests the pose of the
  last rendered frame, which lags a fast swing by a frame.
- **A query between steps** (`OverlapCollider` from `Update`) reads collider poses as of the last
  step. Call `Physics2D.SyncTransforms()` first when the query must see the current bone pose.
- **Triggers are not swept** (`SKILL.md` §2). A swing that crosses more than the target's width in
  one step can pass through it. Lower the step, widen the box along the arc, or `Collider2D.Cast`
  the box from the last pose to this one.

## Turning a hitbox on for its window

The active window comes from the clip: an animation event at the first and last active frame sets
`Collider2D.enabled` (`unity-animation` owns the event). Prefer events to animating `enabled` as a
curve: a curve keeps writing its value in every state of the controller, and a hitbox can stay live
through a transition. Who decides that a contact is damage is `unity-combat`.

Check it in the Scene view with the colliders drawn, stepping one frame at a time, and read
`Collider2D.attachedRigidbody` on each box to confirm the body it joined.
