# 2D queries: casts, overlaps and the filter that decides what they see

Part of the `unity-physics-2d` skill. SKILL.md §2 and §3 state each rule in a line; this file holds
the calls, the overload families and the filter in full.

## Two overload families with two sets of defaults

Every `Physics2D` query comes in two families, and they do not agree on what "default" means.

| | Mask overloads | Filter overloads |
|---|---|---|
| Shape | `Raycast(origin, direction, distance, layerMask, minDepth, maxDepth)` | `Raycast(origin, direction, contactFilter, results, distance)` |
| Returns | One `RaycastHit2D` or one `Collider2D`: the nearest | A count; hits land in a `List<>` or an array you own |
| Triggers | `Physics2D.queriesHitTriggers` (`true`) | `contactFilter.useTriggers` (`false` in `new ContactFilter2D()`), and only while the global is `true` |
| Layers when unset | `Physics2D.DefaultRaycastLayers` — everything except `Ignore Raycast` | Every layer |
| Depth when unset | No limit | No limit |
| Allocates | No | No, once the list has capacity |

A cast that finds a pickup through one family and misses it through the other is this table, not a
broken collider. Pick the filter family for gameplay code and set every field on purpose:

```csharp
// Solid ground for the side run: the Rooftop layer, no triggers, any depth.
ContactFilter2D _solid;
readonly List<RaycastHit2D> _hits = new List<RaycastHit2D>(4);

void Awake()
{
    _solid = new ContactFilter2D();
    _solid.SetLayerMask(LayerMask.GetMask("Rooftop"));   // also sets useLayerMask
    _solid.useTriggers = false;
}
```

`ContactFilter2D.noFilter` is the opposite starting point: every layer, triggers included.

`RaycastAll`, `OverlapCircleAll` and the other `…All` methods allocate a new array per call, and the
`…NonAlloc` names are deprecated. The `List<>` overloads replace both: the list is cleared, grown
when needed, and the return value is the count. They exist with the same signatures in 6000.3 and
6000.4, which is not true of every array overload — write gameplay code against the lists.

## The calls

| Call | Asks | Typical courier-run use |
|---|---|---|
| `Physics2D.Raycast` | First collider along a ray | A sentry's line of fire; a ledge probe ahead of the runner |
| `Physics2D.Linecast(start, end, …)` | The same between two points | Line of sight from a depot sentry to the runner against `Obstacles` |
| `Physics2D.BoxCast(origin, size, angle, direction, …)` | A box swept along a direction | A ground or wall check shaped like the runner |
| `Physics2D.CircleCast(origin, radius, direction, …)` | A circle swept along a direction | A projectile's movement for one step |
| `Physics2D.CapsuleCast(origin, size, CapsuleDirection2D, angle, direction, …)` | A capsule swept | The same for a capsule-shaped runner |
| `Physics2D.OverlapCircle` / `OverlapBox` / `OverlapCapsule` / `OverlapArea` | What is inside a shape now | A launch pad's blast radius; a spawn point that must be clear |
| `Physics2D.OverlapPoint(point, …)` | What contains a point | A click on a pickup; "is this cell solid" |
| `Collider2D.Cast(direction, filter, results, distance, ignoreSiblingColliders)` | This collider's own shape, swept from where it is | The runner's ground check — no size to keep in step with the collider |
| `Rigidbody2D.Cast(direction, filter, results, distance)` | Every collider on the body, swept | A moving platform asking what it is about to hit |
| `Collider2D.Overlap(filter, results)` / `Rigidbody2D.Overlap(filter, results)` | What this shape or body overlaps now | A gate asking whether the doorway is clear before it closes |
| `Collider2D.Raycast(direction, filter, results, distance)` | A ray from the collider's position | A probe that must not return its own collider |
| `Collider2D.Distance(other)` | Separation or overlap as a `ColliderDistance2D` | How deep two shapes overlap, and along which normal |
| `Collider2D.ClosestPoint(position)` | Nearest point on the perimeter | Where a sentry's beam meets the runner |
| `Physics2D.GetRayIntersection(ray, distance, layerMask)` | A 3D ray against the 2D shapes | Picking under a perspective camera |

`Collider2D.Cast` and `Collider2D.Raycast` ignore the collider itself; with
`ignoreSiblingColliders` left at `true` the cast also ignores the other colliders on the same
`Rigidbody2D`. `Rigidbody2D.Cast` ignores every collider attached to that body. The static
`Physics2D` calls ignore nothing: the caster's own collider is one more collider in the scene.

Colliders with no `Rigidbody2D` all sit on the one hidden static body, so they are siblings:
`Collider2D.Cast` from a body-less collider with the flag at `true` returns none of the level.
Give the caster a body, or pass `false`.

## Reading a `RaycastHit2D`

| Field | Value |
|---|---|
| `collider`, `rigidbody`, `transform` | What was hit; `collider == null` means no hit, and the struct converts to `bool` on that test |
| `point` | Where the query shape touched the surface |
| `normal` | The surface normal at that point |
| `distance` | How far the shape travelled before touching |
| `fraction` | `distance` over the distance asked for, `0`–`1`; multiply a step's movement by it to stop at the surface |
| `centroid` | The centre of the query shape at the moment of contact — the position to move a body to |

Results in a list are ordered by distance, nearest first.

A ground test reads the normal, not the hit: `Vector2.Angle(hit.normal, Vector2.up) <= 50f` is a
floor, anything steeper is a wall the same cast happened to touch at its corner.

## Starting inside a collider

| Query | Starts inside or overlapping | Result |
|---|---|---|
| `Raycast`, `Linecast` | `queriesStartInColliders == true` (default) | That collider, `distance` 0, `fraction` 0, `normal` opposite to the ray |
| `Raycast`, `Linecast` | `queriesStartInColliders == false` | That collider is skipped; the ray reports the next one |
| `BoxCast`, `CircleCast`, `CapsuleCast`, `Collider2D.Cast` | `queriesStartInColliders == true` (default) | The overlapped collider at `distance` 0, with a normal that describes no surface |
| `BoxCast`, `CircleCast`, `CapsuleCast`, `Collider2D.Cast` | `queriesStartInColliders == false` | The overlapped collider is skipped; the cast reports the next one |
| Any query against `GeometryType.Outlines` or an `EdgeCollider2D` | Start is "inside" the outline | Nothing: an edge has no interior, the query reports the edge only where it crosses it |

Three consequences:

- A ray from the runner's centre with the runner's layer in the mask returns the runner. Mask the
  layer out, or use `Collider2D.Raycast`.
- A box cast downward from a box resting on the floor reports the floor at distance 0 only when
  the two touch or overlap; resting contact leaves a gap of about
  `Physics2D.defaultContactOffset` (`0.01`), so cast at least `0.02` further than the skin you want.
- A hit at `distance` 0 carries a normal that describes the overlap, not a surface to stand on.
  Treat it as "already inside" and resolve with `Collider2D.Distance`, whose `normal` and
  `distance` give the push-out.

`Physics2D.raycastsStartInColliders` and `Physics2D.raycastsHitTriggers` are the obsolete names of
the two globals.

## `ContactFilter2D`, field by field

| Field | Setter | Effect |
|---|---|---|
| `useLayerMask`, `layerMask` | `SetLayerMask(mask)` | Only colliders on those layers |
| `useTriggers` | — | `true` includes trigger colliders, `false` leaves them out |
| `useDepth`, `minDepth`, `maxDepth` | `SetDepth(min, max)` | Only colliders whose Transform Z is inside the range |
| `useOutsideDepth` | — | Inverts the depth test: only colliders outside the range |
| `useNormalAngle`, `minNormalAngle`, `maxNormalAngle` | `SetNormalAngle(min, max)` | Only hits whose normal angle is inside the range: 0° is +X, 90° is +Y |
| `useOutsideNormalAngle` | — | Inverts the normal test |

`ClearLayerMask()`, `ClearDepth()` and `ClearNormalAngle()` switch a test off; `isFiltering` says
whether the filter would remove anything at all.

A normal filter turns a contact query into a ground query without a loop:

```csharp
// Contacts whose normal points within 40° of straight up: something to stand on.
var ground = new ContactFilter2D();
ground.SetLayerMask(LayerMask.GetMask("Rooftop", "Platform"));
ground.SetNormalAngle(50f, 130f);
bool grounded = body.IsTouching(ground);
```

`Rigidbody2D.IsTouching(filter)` and `GetContacts(filter, list)` read contacts the last step
produced, so they are one step old; a cast is current. Which of the two a character should use
is `unity-2d-controller` → `reference/platformer.md`.

## The Z range

Collision in 2D ignores Z: a runner at Z 0 and a wall at Z 5 collide. Queries can filter on it.

- `minDepth` and `maxDepth` compare each collider's Transform Z, in world space.
- The mask overloads default to an unlimited range; a filter tests depth only after `SetDepth`.
- Use it to keep one physics layer per kind of thing while still separating planes: the depot's
  mezzanine sits at Z 1, the floor at Z 0, and a sentry on the floor casts with `SetDepth(-0.5f,
  0.5f)`.
- A sprite moved in Z to fix draw order moves out of a depth-filtered cast. Draw order belongs to
  sorting layers — `unity-2d-rendering` → `reference/sort-order.md`.

## A projectile is swept, not stepped

```csharp
// Bullet.cs — a pooled projectile that cannot tunnel, whatever the step is.
// Drop on the bullet prefab; no Rigidbody2D is needed for the movement.
using System.Collections.Generic;
using UnityEngine;

public class Bullet : MonoBehaviour
{
    public float speed = 14f;
    public float radius = 0.1f;
    public LayerMask hits;                       // Obstacles, Sentry — not the shooter's layer

    static readonly List<RaycastHit2D> _results = new List<RaycastHit2D>(4);
    ContactFilter2D _filter;
    Vector2 _direction;

    public void Fire(Vector2 direction)
    {
        _direction = direction.normalized;
        _filter = new ContactFilter2D();
        _filter.SetLayerMask(hits);
        _filter.useTriggers = false;
    }

    void FixedUpdate()
    {
        float step = speed * Time.fixedDeltaTime;
        Vector2 from = transform.position;
        if (Physics2D.CircleCast(from, radius, _direction, _filter, _results, step) > 0)
        {
            RaycastHit2D hit = _results[0];
            transform.position = hit.centroid;
            hit.collider.SendMessage("OnBulletHit", hit.point, SendMessageOptions.DontRequireReceiver);
            gameObject.SetActive(false);         // back to the pool
            return;
        }
        transform.position = from + _direction * step;
    }
}
```

The cast is exact at any speed and any step. A bullet made reliable by halving the fixed timestep
still tunnels at twice the speed.

## Picking from the screen

| Camera | Call |
|---|---|
| Orthographic | `Physics2D.OverlapPoint(camera.ScreenToWorldPoint(screenPos), mask)` |
| Perspective | `Physics2D.GetRayIntersection(camera.ScreenPointToRay(screenPos), distance, mask)` |

`Physics2D.Raycast` takes a 2D origin and a 2D direction in the XY plane; handing it the origin
and direction of a camera ray casts along the plane from wherever the camera's X and Y happen to
be. UI is not in this world at all: a click on a Canvas is answered by the EventSystem —
`unity-ui-ugui`.

## Outside play mode, and right after a move

Queries read the shapes as of the last step. After creating or moving a collider from an Editor
script, or after writing a Transform in the same frame as the query, call
`Physics2D.SyncTransforms()` once before the first query. Do not call it every frame: a body moved
with `MovePosition` or velocity never needs it.
