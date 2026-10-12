# Layers, the 2D matrix and the per-object overrides

Part of the `unity-physics-2d` skill. SKILL.md §1 step 5 and §7 state the rules in a line; this
file holds the matrix, two layer schemes, the overrides and the ignore calls in full.

## Four things decide whether a pair can touch

Any one of them saying no is silence.

| Level | Where | Scope | Survives a scene load |
|---|---|---|---|
| Simulation layers | `Physics2D.simulationLayers` | A whole layer is outside the simulation | Project setting |
| Layer matrix | `Project Settings → Physics 2D → Layer Collision Matrix`; `Physics2D.IgnoreLayerCollision(a, b, ignore)`, `Physics2D.SetLayerCollisionMask(layer, mask)` | Every pair on two layers | Project setting; a runtime change lasts until changed back |
| Layer overrides | `includeLayers`, `excludeLayers`, `layerOverridePriority` on a `Collider2D`; `includeLayers`, `excludeLayers` on a `Rigidbody2D` | One collider, or every collider on one body | Serialised on the component |
| Instance pair | `Physics2D.IgnoreCollision(a, b, ignore)` | Two collider instances | No — runtime state of those two instances |

The 2D matrix is its own asset (`Physics2DSettings.asset`) with its own page. The 3D matrix under
`Project Settings → Physics` has no effect on a `Collider2D`, and the reverse.

One call answers for the matrix and the overrides together, and one for the instance pair:

```csharp
bool possible = a.CanContact(b);                       // matrix and layer overrides
bool ignored  = Physics2D.GetIgnoreCollision(a, b);    // the instance pair
LayerMask sees = a.contactMask;                        // every layer a can contact, after overrides
```

`Physics2D.GetLayerCollisionMask(layer)` is the matrix row alone, and
`Physics2D.GetIgnoreLayerCollision(a, b)` one cell of it. `resources/CollisionDebugger2D.cs` logs
the first two per pair, with the simulation-layer bit for each side, and `resources/Editor/Physics2DAudit.cs` lists every collider whose
`contactMask` is empty.

## A layer scheme for the side run

Layers name roles, not objects. Seven are enough.

| Layer | On it | Body |
|---|---|---|
| `Runner` | The runner's body collider | Dynamic or Kinematic, per the motor |
| `Rooftop` | Solid level: the composite Tilemap | Static |
| `Platform` | One-way ledges with a `PlatformEffector2D` | Static, or Kinematic when it moves |
| `Hazard` | Spikes, crushers, the kill plane | Trigger; Static or Kinematic |
| `Pickup` | Collectables and the gate's trigger | Trigger; none or Kinematic |
| `Sentry` | Sentries' body colliders | Kinematic |
| `Projectile` | Anything fired | Swept by cast, or Dynamic with `Continuous` |

| | Runner | Rooftop | Platform | Hazard | Pickup | Sentry | Projectile |
|---|---|---|---|---|---|---|---|
| **Runner** | — | yes | yes | yes | yes | yes | yes |
| **Rooftop** | | — | — | — | — | yes | yes |
| **Platform** | | | — | — | — | yes | — |
| **Hazard** | | | | — | — | — | — |
| **Pickup** | | | | | — | — | — |
| **Sentry** | | | | | | — | yes |
| **Projectile** | | | | | | | — |

What the empty cells buy:

- `Hazard × Sentry` off: a patrol can cross spikes without a special case in the hazard script.
- `Pickup × Sentry` and `Pickup × Projectile` off: only the runner collects, with no tag test in
  `OnTriggerEnter2D`.
- `Projectile × Platform` off: shots pass through ledges, as the runner does from below.
- `Sentry × Sentry` off: two patrols meeting on a ledge do not push each other off.
- `Sentry × Rooftop` needs `useFullKinematicContacts` on the sentry to report, since both sides
  are non-Dynamic; a sentry that finds ledge ends with a cast does not need the contact at all.

Query masks follow the same names. The ground check uses `Rooftop | Platform`; a sentry's line of
sight uses `Rooftop`; a projectile's sweep uses `Rooftop | Sentry` or `Rooftop | Runner` by who
fired it.

## A layer scheme for the depot

Top-down, no gravity, aisles as lanes.

| Layer | On it | Body |
|---|---|---|
| `Runner` | A circle at the runner's feet, radius 0.3 | Dynamic, gravity scale 0 |
| `Obstacles` | Shelving: the composite Tilemap | Static |
| `Sentry` | Sentries' feet circles | Kinematic |
| `Vision` | Each sentry's cone, a `PolygonCollider2D` trigger on a child | Uses the sentry's body |
| `Pickup` | Parcels on the floor, and the carried parcel's drop trigger | Trigger |
| `Gate` | The gate: a solid collider while shut, plus a delivery trigger | Static |
| `Projectile` | Twin-stick shots | Swept by cast |

| | Runner | Obstacles | Sentry | Vision | Pickup | Gate | Projectile |
|---|---|---|---|---|---|---|---|
| **Runner** | — | yes | yes | yes | yes | yes | — |
| **Obstacles** | | — | yes | — | — | — | yes |
| **Sentry** | | | — | — | — | yes | yes |
| **Vision** | | | | — | — | — | — |
| **Pickup** | | | | | — | yes | — |
| **Gate** | | | | | | — | yes |
| **Projectile** | | | | | | | — |

- `Vision` touches `Runner` and nothing else, so the cone's `OnTriggerEnter2D` needs no filtering.
  The cone says "inside the shape"; whether shelving blocks the view is one
  `Physics2D.Linecast` against `Obstacles` — `reference/queries-2d.md`.
- `Pickup × Gate` on: a carried parcel's trigger entering the gate's delivery trigger is the
  delivery. One of the two has a non-Static `Rigidbody2D`, or the pair never reports.
- The cone is a child collider, so it attaches to the sentry's `Rigidbody2D` and moves with it. Its
  callbacks arrive on the cone's GameObject and on the body's.

The sorting yard needs no scheme: movement is decided by the cell map, and the only physics is
picking — one layer for cell colliders, if any.

## Layer overrides on a collider or a body

Unity 6 lets one object depart from the matrix without a layer of its own.

| Property | On | Effect |
|---|---|---|
| `includeLayers` | `Collider2D`, `Rigidbody2D` | Adds layers this object contacts, beyond its matrix row |
| `excludeLayers` | `Collider2D`, `Rigidbody2D` | Removes layers from it |
| `layerOverridePriority` | `Collider2D` | When the two colliders of a pair disagree, the higher priority decides |
| `forceSendLayers`, `forceReceiveLayers` | `Collider2D` | Which layers this collider pushes, and is pushed by, in a collision |
| `contactCaptureLayers` | `Collider2D` | Which layers' contacts are stored for `GetContacts` |
| `callbackLayers` | `Collider2D` | Which layers' contacts raise `OnCollision*2D` / `OnTrigger*2D` |

A body's include and exclude masks apply to every collider attached to it.

Uses that replace a layer:

- A ghost pickup the runner collects and sentries walk through: already covered by the matrix. A
  **boss** sentry that also blocks projectiles other sentries let pass: `includeLayers` on that one
  collider.
- A crusher that pushes the runner and is never pushed back by debris: `forceReceiveLayers` without
  the debris layer.
- A hazard that should collide but not call back for debris: `callbackLayers`.

The price is visibility. The matrix is one page; an override is a foldout on one component, and
"contact with no callback" or "no contact although the matrix allows it" has no other tell. That is
why `CanContact` is the question to ask, and why the audit reports overrides that empty a mask.

## `Physics2D.IgnoreCollision`, and why it does not survive pooling

`Physics2D.IgnoreCollision(a, b, true)` removes one pair of collider instances from collision and
trigger detection. It is the right tool for a pair — a runner dropping through one platform, a
projectile and the sentry that fired it — and it is state held between those two instances, not on
a prefab, a layer or a component you can read in the inspector.

Pooling breaks it in both directions:

- **Stale ignores.** A projectile ignores sentry A, hits a wall, returns to the pool, and is fired
  again by sentry B. It still ignores A and now collides with B's own muzzle.
- **Missing ignores.** A pool that grows instantiates a fresh projectile; code that set the ignore
  once at start-up never saw that instance.
- **Timed restores that never run.** The drop-through coroutine restores the pair after 0.25 s; a
  runner deactivated at 0.1 s stops the coroutine, and that runner falls through that platform
  for the rest of the session.

The pattern that holds:

```csharp
// On the pooled projectile. The owner is whoever fired it this time.
Collider2D _self, _owner;

public void Launch(Collider2D owner)
{
    _owner = owner;
    Physics2D.IgnoreCollision(_self, _owner, true);
}

void OnDisable()
{
    if (_owner != null) Physics2D.IgnoreCollision(_self, _owner, false);
    _owner = null;
}
```

Set on use, clear on return, and assert with `Physics2D.GetIgnoreCollision(_self, other)` in a
test that fires the same pooled instance from two owners.

`Physics2D.IgnoreLayerCollision(a, b, true)` is the opposite mistake: every pair on two layers,
changed for the whole game until something changes it back, and invisible to whoever reads the
matrix page in the Editor afterwards. A rule that permanent belongs in the matrix; a rule that
temporary belongs on the pair, or in `excludeLayers` on the one body it concerns.

## A `Collision2D` is recycled

`Physics2D.reuseCollisionCallbacks` is on by default: one `Collision2D` instance is handed to every
collision callback. A reference kept past the callback — in a list of "things touching me", in a
coroutine — describes a later contact between other objects. Copy `collider`, `relativeVelocity`
and the contacts you need inside the callback.

## Layer names in code

- `LayerMask.NameToLayer("Rooftop")` returns `-1` when the layer is not defined, and
  `LayerMask.GetMask("Rooftop")` returns `0`. Neither logs. A filter built from `0` matches
  nothing; `1 << -1` is not a mask you meant.
- Resolve once at start-up and assert:

  ```csharp
  int rooftop = LayerMask.NameToLayer("Rooftop");
  Debug.Assert(rooftop >= 0, "Layer 'Rooftop' is not defined in Tags and Layers");
  ```

- A `[SerializeField] LayerMask` set in the inspector stores bits, not names. Reordering layers in
  `Tags and Layers` silently repoints it; adding layers at the end does not.
