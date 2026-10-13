# Hit and hurt layers — three kinds of collider that must never be confused

> Part of the `unity-combat` skill. A character carries up to three kinds of volume, each on its
> own layer: the **body** the solver pushes, the **hurtboxes** where it can be hit, and the
> **hitboxes** it attacks with. The body is the wrong shape to be hit and the hurtbox must never
> push anything. Keep them on separate layers and exactly one pair is left for combat.

## 1. The three kinds

| Kind | Layer | Collider | Trigger | Body above it | Who reads it |
|---|---|---|---|---|---|
| Body | `Runner`, `Sentry` (or one `Body`) | The capsule or `CharacterController` that walks into walls | No | The character's own | The solver, the motor's casts |
| Hurtbox | `Hurtbox` | Primitives on the root or on bones | Yes | The character's own | Hitbox queries, shots |
| Hitbox | `Hitbox` — trigger hitboxes only | None for a query hitbox; a trigger for a trigger hitbox | Yes | The attacker's own | The engine's trigger pairs |

- **A hurtbox is not the body.** The body is a capsule sized so the runner fits through a door;
  the hurtbox is sized so a near miss is a miss. In the lane run the body is 0.8 wide and the
  hurtbox 0.5: lanes are 1.3 apart and a hazard in the next lane must not touch it.
- **A hurtbox is a trigger.** As a solid it joins the character's compound shape and the runner
  snags on a sentry's elbow.
- **A query hitbox has no collider at all** and needs no `Hitbox` layer. `Hitbox3D` and
  `Hitbox2D` are that kind.

## 2. The 3D matrix

`Project Settings → Physics → Layer Collision Matrix`. `yes` is a ticked cell; every
other cell is cleared.

| | World | Runner | Sentry | Hurtbox | Hitbox |
|---|---|---|---|---|---|
| **World** | — | yes | yes | — | — |
| **Runner** | | — | yes | — | — |
| **Sentry** | | | yes | — | — |
| **Hurtbox** | | | | — | yes |
| **Hitbox** | | | | | — |

- **`Hitbox × Hurtbox` is the only combat pair**, and it matters only to trigger hitboxes.
- **With query hitboxes the `Hurtbox` row is empty.** A query reads the layer mask it is given;
  the matrix is not consulted. An empty row means the solver never forms a pair with a hurtbox,
  which is the cheapest a collider can be.
- **`Hurtbox × Hurtbox` cleared** stops two crowded sentries generating trigger pairs between
  each other's heads.
- **`Hurtbox × World` cleared**: a hurtbox resting in a wall is not an event.

From script, for a set-up step or a test:

```csharp
int hurt = LayerMask.NameToLayer("Hurtbox"), hit = LayerMask.NameToLayer("Hitbox");
for (int layer = 0; layer < 32; layer++)
{
    Physics.IgnoreLayerCollision(hurt, layer, layer != hit);
    Physics.IgnoreLayerCollision(hit, layer, layer != hurt);
}
```

`Physics.IgnoreLayerCollision` changes the project's matrix until it is changed back; a test
that calls it restores every cell it wrote, reading the old value with
`Physics.GetIgnoreLayerCollision` first.

**One prefab that differs** uses the per-collider overrides instead of a new layer:
`Collider.excludeLayers` and `Collider.includeLayers` (and the same two on `Rigidbody`).

## 3. The 2D matrix

`Project Settings → Physics 2D → Layer Collision Matrix` — a different asset from the 3D one.
Add two layers to the scheme in `unity-physics-2d` → `reference/layers-and-matrix.md`:

| | Rooftop | Runner | Sentry | Hazard | Hurtbox | Hitbox |
|---|---|---|---|---|---|---|
| **Hurtbox** | — | — | — | — | — | yes |
| **Hitbox** | — | — | — | — | yes | — |

```csharp
Physics2D.IgnoreLayerCollision(hurt, layer, layer != hit);    // same loop, the 2D call
```

- **Z separates nothing in 2D.** A hurtbox at Z 3 is hit by a hitbox at Z 0. Depth is a filter a
  query may add (`ContactFilter2D.SetDepth`), never a property of collision.
- **Per-collider overrides**: `Collider2D.excludeLayers`, `includeLayers`, and `callbackLayers`
  for a pair that should touch and stay silent.
- **A hurtbox merged into a `CompositeCollider2D` loses its own trigger flag.** Hurtboxes are
  never children of a composite.

## 4. Hurtboxes on a rig

```
Sentry                    Health, SentryBrain, Rigidbody (kinematic)           layer Sentry
├─ Body                   CapsuleCollider                                      layer Sentry
├─ Model                  Animator
│  └─ … Spine             Hurtbox.Torso: BoxCollider, trigger                  layer Hurtbox
│     └─ … Head           Hurtbox.Head: SphereCollider, trigger                layer Hurtbox
└─ Strike                 Hitbox3D                                             (no collider)
```

- **A child does not inherit its parent's layer.** Set `Hurtbox` on each hurtbox object.
- **Size from constants, never from `Renderer.bounds`.** A skinned mesh reports its bind pose,
  arms out — `unity-rigged-character` → `reference/gameplay-rig.md`.
- **One body at the root, none below it.** A second `Rigidbody` on a bone cuts every collider
  under it out of the character.
- **A moved collider reaches PhysX at the next physics step**, whoever moved it: a bone, a
  motor, a teleport. A query in `FixedUpdate` therefore sees hurtboxes where the last step left
  them — one step behind the drawing, which no window should be tight enough to notice. After a
  respawn or a teleport, call `Physics.SyncTransforms()` once before anything queries.
- **Trigger messages need a body.** A hazard zone or a trigger hitbox raises nothing against a
  hurtbox when neither side has a `Rigidbody`; give the character's root a kinematic one. Query
  hitboxes do not need it.
- **Primitives only.** `Collider.ClosestPoint`, which gives the hit point, needs a box, sphere,
  capsule or convex mesh.
- **Uniform scale on every parent of a `SphereCollider`**; under `(1, 3, 1)` the sphere takes
  the largest axis.
- **An Animator that is culled stops moving its bones.** Under
  `AnimatorCullingMode.CullCompletely` or `CullUpdateTransforms`, a sentry off screen keeps its
  hurtboxes in the last drawn pose. A character that fights off screen uses `AlwaysAnimate`, or
  one hurtbox on the root.
- **How many.** One capsule for the runner in the lane run and the depot. Two to four on a
  sentry when where it is hit matters to the eye. More is a fighting game, and then each is
  authored per animation frame.
- **In 2D** the same tree with `BoxCollider2D` / `CircleCollider2D` triggers, on the bone
  transforms of a skinned sprite or on the root for frame animation, where the hurtbox does not
  follow the drawing and one box per character is the honest shape.

## 5. Trigger hitbox or query hitbox

| | Trigger hitbox | Query hitbox |
|---|---|---|
| What it is | A trigger collider on `Hitbox`, enabled during the window | A script that calls `OverlapBox` and `BoxCast` during the window |
| Needs | A `Rigidbody` on one side of every pair; the matrix cell | A layer mask |
| Reports | `OnTriggerEnter` once per collider pair, after the next physics step | Every overlapping collider, at the call |
| A fast swing | Triggers are not swept: a weapon that moves further than the target is wide passes through | Cast from the last pose to this one |
| A window shorter than one step | May never be simulated while enabled | `Close()` queries once |
| Already overlapping when the window opens | Depends on the engine raising a new pair; run §6 on the project | Reported on the first query |
| Cost while closed | A disabled collider: none | None |
| Cost while open | The broadphase tracks it against every `Hurtbox` collider | One overlap and one cast per open hitbox per step |
| Dedupe | Still needed: one Enter per hurtbox collider, and one per re-entry | Needed: every step reports every collider |

Both need the hit list. The query is the default here because it answers at once, sweeps, needs
no body, and ignores the matrix — one fewer place for a hit to go missing.

A trigger volume is still the right tool for a thing that is always on and slow: a hazard zone, a
vision cone, a pickup. It reports who entered and left; an attack on a timer reads that set
(`reference/iframes-and-knockback.md`).

## 6. Checks

| Check | How |
|---|---|
| The matrix leaves one combat pair | Loop the 32 layers and log every `j` where `!Physics.GetIgnoreLayerCollision(hurt, j)`; expect `Hitbox` or nothing |
| Every hurtbox is a trigger on `Hurtbox` | For each `Health` in the scene, `GetComponentsInChildren<Collider>(true)`; for each on the `Hurtbox` layer assert `isTrigger`. Then assert every receiver has at least one |
| Hurtboxes that a trigger zone must see have a body | For each, log `collider.attachedRigidbody == null`; expect none |
| The hitbox sees both hurtboxes | Open it over the sentry and read `ContactsThisSwing` after two steps: 4 |
| A trigger hitbox enabled while overlapping | Enable it inside a hurtbox, step twice, count `OnTriggerEnter`; if 0, that project needs the query |
| A callback or a query that fails for physics reasons | `unity-physics-3d`, `unity-physics-2d` → `reference/layers-and-matrix.md` |
