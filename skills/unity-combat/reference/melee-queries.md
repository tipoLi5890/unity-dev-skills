# Melee queries — asking what the weapon touched, every step, without skipping and without garbage

> Part of the `unity-combat` skill. A query hitbox asks two questions on each fixed step of an
> open window: what does the volume overlap **now**, and what did it pass **through** since the
> last step. The second question is the one a trigger cannot ask, and it is why a fast swing
> does not step over a thin target.

## 1. Query or trigger volume

| Use | When |
|---|---|
| A query per fixed step (`Hitbox3D`, `Hitbox2D`) | Every attack with a window: swings, kicks, a dash that hurts, contact damage on a period |
| A trigger volume | Things that are always on and slow, and need to know who is inside: a vision cone, a hazard zone feeding a timer, a pickup |

The comparison in full: `reference/hit-and-hurt-layers.md` §5.

## 2. The step

```csharp
// Hitbox3D.Query, once per FixedUpdate while open
int n = Physics.OverlapBoxNonAlloc(at, halfExtents, _overlaps, rot, hurtMask,
                                   QueryTriggerInteraction.Collide);
for (int i = 0; i < n; i++) Consider(_overlaps[i]);

Vector3 delta = at - _last;
float distance = delta.magnitude;
if (sweep && distance > 1e-4f)
{
    int m = Physics.BoxCastNonAlloc(_last, halfExtents, delta / distance, _casts, rot,
                                    distance, hurtMask, QueryTriggerInteraction.Collide);
    for (int i = 0; i < m; i++) Consider(_casts[i].collider);
}
_last = at;
```

- **In `FixedUpdate`, never `Update`.** The number of queries per second of window is then the
  same on every machine, and the poses read are the ones the last physics step produced.
- **Overlap and cast, both.** The overlap finds what the box rests in when it has not moved — a
  stationary jab, a hazard. The cast finds what lay between two poses. Everything either returns
  goes through the same `Consider`, and the hit list makes the double report harmless.
- **`QueryTriggerInteraction.Collide`, written out.** Hurtboxes are triggers, and
  `Physics.queriesHitTriggers` is a project setting somebody may have cleared.
- **The mask is the `Hurtbox` layer alone.** Bodies and level geometry in the mask fill the
  buffer with colliders that resolve to no receiver.
- **Half extents are world units.** The query takes no scale; a hitbox under a scaled parent
  queries the box the fields say, which is what the gizmo draws.

## 3. Why the sweep

A box 1 unit deep on a weapon tip that moves 12 units/s travels 0.24 units per 0.02 s step —
the overlaps of two consecutive steps share three quarters of their volume and nothing is
missed. The numbers that break it:

| Tip speed | Travel per step | An overlap-only hitbox 0.3 deep misses a target thinner than |
|---|---|---|
| 12 units/s | 0.24 | — (consecutive boxes overlap) |
| 30 units/s | 0.6 | 0.3 |
| 60 units/s (a dash strike) | 1.2 | 0.9 |

- **The rule: travel per step must stay under the hitbox's depth along the motion**, or the
  sweep must be on. It is on by default.
- **A weapon on a bone moves in an arc**; the cast is the chord between two poses. At 90° per
  0.1 s and a 1.2-unit blade, the tip travels 0.38 units per step and the chord cuts inside the
  arc by under 0.02 units. Only a swing that turns more than about 45° per step needs a second
  hitbox at mid-blade.
- **The box keeps the current rotation along the cast.** Good enough at those angles; do not
  interpolate rotations per sub-step until a miss seen in play says so.
- **A hitbox that is a child of the root, not of a bone, does not sweep an arc at all**: it is a
  box in front of the runner for the length of the window. That is the right first hitbox for a
  top-down or third-person swing — readable, and independent of the animation.
- **The first step of a window has no previous pose.** `Open()` stores the pose, so the first
  cast covers only the motion since the window opened, never a line from wherever the weapon
  was during the last attack.

## 4. Other shapes

| Volume | 3D overlap · cast | 2D overlap · cast |
|---|---|---|
| Box | `Physics.OverlapBoxNonAlloc` · `Physics.BoxCastNonAlloc` | `Physics2D.OverlapBox` · `Physics2D.BoxCast` |
| Sphere, circle | `Physics.OverlapSphereNonAlloc` · `Physics.SphereCastNonAlloc` | `Physics2D.OverlapCircle` · `Physics2D.CircleCast` |
| Capsule: a blade from hilt to tip | `Physics.OverlapCapsuleNonAlloc(hilt, tip, radius, …)` · `Physics.CapsuleCastNonAlloc` | `Physics2D.OverlapCapsule` |
| A thin, fast edge | `Physics.Linecast(lastTip, tip, …)` per step | `Physics2D.Linecast` |

- **A cone is a sphere and an angle test**: `OverlapSphereNonAlloc` with the reach as radius,
  then keep targets where `Vector3.Angle(forward, toTarget) <= 45f`. There is no cone query.
- **A blade is a capsule between two transforms**, hilt and tip. Sweep it by casting the capsule
  along the motion of its centre.
- **Start with the box.** Change shape when a playtest shows a hit that looks wrong, not before.

## 5. Calls that do not allocate

| | 3D | 2D |
|---|---|---|
| Result storage | A `Collider[]` or `RaycastHit[]` field, sized once | A `List<Collider2D>` or `List<RaycastHit2D>` field |
| Form | The `…NonAlloc` methods, which return the count | The overloads taking a `ContactFilter2D` and a `List<>`, which return the count |
| When full | Results beyond the array are dropped, silently | The list grows — one allocation, then none |
| Order | Unspecified: pick the nearest yourself | Pick the nearest yourself as well; it costs one loop |

- **`Physics.OverlapBox` and `Physics.BoxCastAll` return a new array on every call**: an
  allocation per open hitbox per step.
- **Size the 3D buffer for the worst crowd**: 16 covers eight sentries with two hurtboxes each.
  `Hitbox3D` logs once when a query fills it.
- **Use the list overloads in 2D.** The `Physics2D` methods ending in `NonAlloc` are deprecated
  and compile with a warning; `Physics2D.OverlapCircle(point, radius, filter, list)` is the form
  to write.
- **Read only the first `count` entries.** The rest of a 3D buffer holds the previous call's
  results.

## 6. The 2D step

```csharp
// Hitbox2D.Query
var filter = new ContactFilter2D();
filter.SetLayerMask(hurtMask);
filter.useTriggers = true;                 // a fresh filter leaves triggers out

int n = Physics2D.OverlapBox(at, size, angle, filter, _overlaps);
…
int m = Physics2D.BoxCast(_last, size, angle, delta / distance, filter, _casts, distance);
```

| Differs from 3D | In 2D |
|---|---|
| Size | Full width and height, not half extents |
| Rotation | One angle in degrees: `transform.eulerAngles.z` |
| Triggers | `filter.useTriggers`, `false` by default in a filter — the overloads taking a bare layer mask follow `Physics2D.queriesHitTriggers` instead |
| Depth | Z is ignored unless the filter sets a depth range |
| Facing | A sprite flipped with a negative scale does not mirror the query: place the hitbox child at `±offset` from the facing |
| Start inside | A cast that starts overlapping reports that collider at distance 0 |

Filters, the start-inside table and the Z range: `unity-physics-2d` → `reference/queries-2d.md`.
The 3D rules — triggers, masks, the sync before a query: `unity-physics-3d` →
`reference/queries.md`.

## 7. Line of sight

A box in front of the runner reaches through a thin wall. `blockMask` adds one test per accepted
contact: a `Linecast` from the owner's chest (`owner` position plus `originOffset`, `(0, 1, 0)`
in 3D) to the contact point, against solid layers with triggers ignored.

- **Leave the floor out of trouble**: an origin at the feet runs the line along the ground and
  every hit is blocked. Keep the origin at chest height.
- **A blocked target is not listed**, so it is hit when the swing clears the obstacle.
- **Off by default.** Turn it on when the level has walls thinner than the reach.

## 8. Checks

| Check | How |
|---|---|
| The volume is where it looks | Select the hitbox in play mode: the gizmo turns red while open |
| The query sees both hurtboxes | Log `ContactsThisSwing` at close: about `colliders × steps` |
| Nothing allocates per step | Profiler, `GC Alloc` column, with a window held open — `unity-profiling` |
| A dash strike does not skip | Move the hitbox 1.2 units per step across a sentry 0.4 deep; one heart lost with `sweep` on, none with it off |
| A wall blocks | Stand the sentry behind a 0.1-unit wall inside the reach with `blockMask` set; `HitsThisSwing` stays 0 while `ContactsThisSwing` rises |
