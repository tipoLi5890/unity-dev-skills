# The two hit ladders in full

> Part of the `unity-combat` skill (SKILL.md §1–§2). Every cause, in the order to check it, for a
> hit that lands twice and a hit that never lands.

## §1. The hit lands twice, or once per step

Count before changing anything: log `hitbox.SwingId`, `hitbox.ContactsThisSwing` and the
target's `DamageEvents` when the window closes. A 0.2 s window over two hurtboxes reads about
`contacts=20 events=1`; `events` equal to `contacts` means nothing is deduplicating.

1. **Damage is dealt from `OnTriggerEnter` / `OnTriggerStay` on the weapon.** Enter fires per
   collider pair and again on every re-entry; Stay fires every step. Move the damage call out of
   the callback and into a hitbox with a hit list.
2. **The hit list is keyed by collider, not by receiver.** Two hurtboxes are two keys. Resolve
   `collider.GetComponentInParent<IDamageable>()` first and list that.
3. **The list is never cleared, or cleared on the wrong edge.** It is cleared in `Open()`, and
   only there. Cleared in `Close()` it is empty for a re-entrant open; cleared per step it is no
   list.
4. **Two windows are open.** An AnimationEvent pair whose closing event was skipped leaves the
   first swing live under the second. `Open()` here ends a swing that is still open; the cause
   is §3.
5. **Two hitbox components answer one window** — one on the prefab and one on its variant, or a
   trigger collider left on the weapon beside the query. Search the hierarchy for both.
6. **Invincibility hides it.** A runner with 0.6 s of invincibility takes one hit from a broken
   attack; the sentry, which has none, takes ten. Test the attack against a target whose
   `invincibleSeconds` is 0.

A move that is meant to hit three times is three windows, each a new swing id — never one window
with the rule switched off. The contract and the list: `reference/attack-windows.md`.

## §2. The hit never lands

Work down. First match wins.

1. **The window never opened.** Read `hitboxOpen` in the probe while the attack plays. Closed
   throughout: the state has no window behaviour, the receiver is not beside the Animator, or
   the Animator is culled off screen — `unity-animation` → `reference/events-and-windows.md`.
2. **The query leaves triggers out.** Hurtboxes are triggers. In 3D pass
   `QueryTriggerInteraction.Collide`; never rely on `Physics.queriesHitTriggers`. In 2D a
   `new ContactFilter2D()` has `useTriggers == false` — set it. Both files here do.
3. **`ContactsThisSwing` is 0 with the gizmo over the target.** `hurtMask` lacks the `Hurtbox`
   layer; the hurtbox objects are not on it — a child does not inherit its parent's layer; or
   `owner` is wrong. Left empty it is `transform.root`: a whole level object, when characters
   are parented under one, and every collider under the owner is skipped.
4. **`ContactsThisSwing` is above 0 and `HitsThisSwing` is 0.** In order: no `IDamageable` on
   any parent; same `team`; `blockMask` has a solid between owner and target (or the floor, when
   `originOffset` is at the feet); the receiver refused — dead, or invincible.
5. **The pose is stale.** A collider moved by a bone, a motor or a teleport reaches PhysX at the
   next physics step. After a respawn or a teleport call `Physics.SyncTransforms()` once.
6. **The volume is somewhere else.** Select the hitbox: its gizmo is the box that is queried, in
   world units, ignoring scale. A sprite flipped by negative scale does not mirror a 2D query;
   move the child.
7. **A fast, short swing stepped over the target.** Leave `sweep` on:
   `reference/melee-queries.md`.

Queries that miss for physics reasons: `unity-physics-3d` → `reference/queries.md`,
`unity-physics-2d` → `reference/queries-2d.md`.
