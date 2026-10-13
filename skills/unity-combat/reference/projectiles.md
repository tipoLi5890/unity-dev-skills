# Projectiles — a cast that moves, a pool that lends it, a pattern that is data

> Part of the `unity-combat` skill. A projectile here is never a simulated body. Each fixed step
> it casts its own radius along the distance it is about to travel and stops at the first thing
> in the way; the cast is exactly as long as the step, so there is no speed at which it tunnels.

## 1. Why not a body with a trigger

| A shot built as | Fails when |
|---|---|
| A `Rigidbody` with a trigger collider and `OnTriggerEnter` | It moves further per step than the target is thick: triggers are not swept by continuous detection |
| A dynamic body with continuous detection and `OnCollisionEnter` | The target is a hurtbox, which is a trigger; and the shot now pushes what it hits |
| A kinematic `Rigidbody2D` set to `Continuous` | Always: the mode does nothing for a kinematic body |
| A transform moved in `Update` with an overlap test at the new position | The frame is long, or the wall is thin |
| A cast of `speed × dt` per fixed step | — |

| Speed | Travel per 0.02 s step | Steps over anything thinner than |
|---|---|---|
| 8 units/s (a slow bullet on a fixed screen) | 0.16 | 0.16 |
| 14 units/s (the depot's shot) | 0.28 | 0.28 |
| 30 units/s (the gate room's shot) | 0.6 | 0.6 |
| 60 units/s | 1.2 | 1.2 |

A depot shelf is 1 tile thick and survives 14 units/s by luck; a sentry's 0.5-unit hurtbox does
not survive 30. Halving the fixed step halves the numbers and removes none of them.

## 2. The step

`resources/Projectile3D.cs` (`Projectile2D.cs` is the same with a circle):

```csharp
float distance = speed * Time.fixedDeltaTime;                      // the cast is one step long
int n = Physics.SphereCastNonAlloc(from, radius, Direction, _hits, distance, hitMask,
                                   QueryTriggerInteraction.Collide);
// nearest hit that Stops(): not the owner, not the same team, not dead
transform.position = from + Direction * (hit ? nearestDistance : distance);
```

- **No collider and no body on the prefab.** A body is a second writer of the position and a
  second opinion about what was hit.
- **`hitMask` is `Hurtbox` plus the solid layers.** It never holds body layers: a shot that
  stops on the sentry's walking capsule hits air beside its shoulder.
- **Take the smallest `distance` among the hits that stop the shot**, in 3D and in 2D alike: the
  3D buffer is unordered, and the 2D file does not lean on the list's order either.
- **A collider overlapped at the start comes back at distance 0** (in 3D with `point` at the
  origin of the world). The shot is treated as having hit where it stands.
- **The position is written once per step, by the projectile.** Nothing else moves it.
- **Range is `speed × lifetime`**: 30 × 2 = 60 units, 14 × 1.2 = 16.8.

| Field | 3D default | 2D default |
|---|---|---|
| `speed` | 30 | 14 |
| `radius` | 0.1 | 0.1 |
| `lifetime` | 2 | 1.2 |
| `damage` · `knockback` · `stun` | 1 · 4 · 0.1 | 1 · 4 · 0.1 |
| `tags` | `Projectile` | `Projectile` |
| `turnRate` | 0 | 0 |

## 3. What it passes through

```csharp
bool Stops(Collider c)
{
    if (Owner != null && c.transform.IsChildOf(Owner.transform)) return false;
    IDamageable target = c.GetComponentInParent<IDamageable>();
    if (target == null) return true;                              // level geometry
    return target.IsAlive && CombatTeam.CanDamage(Team, target.Team);
}
```

- **Owner by hierarchy, team by number.** The shot leaves the runner's own hurtbox on its first
  step without a spawn offset and without `Physics.IgnoreCollision`, whose pairs a pooled object
  carries into its next flight.
- **Teammates and the dead do not stop it.** Change the last line to stop on teammates when
  blocking a friend's line of fire is part of the design.
- **A refused hit still ends the flight.** A shot that meets an invincible runner is spent; read
  `DealtDamage` to choose the impact effect.
- **Firing with the muzzle through a wall**: cast from the owner's chest to the muzzle before
  `Launch`, and launch from the hit point when something solid is between them.
- **A piercing shot** keeps flying after a receiver and owns a hit list for the flight, exactly
  as a swing does: skip listed receivers in `Stops`, stop only on geometry.

## 4. Pooled lifetime

The projectile ends its flight by raising `Finished`; with no listener it deactivates itself.
A pool listens:

```csharp
// UnityEngine.Pool. Pool size = fire rate × lifetime × shooters: 8 /s × 1.2 s × 1 = 10.
_pool = new ObjectPool<Projectile2D>(
    createFunc: () =>
    {
        Projectile2D shot = Instantiate(prefab);
        shot.Finished += s => _pool.Release(s);        // subscribed once, at creation
        return shot;
    },
    actionOnRelease: s => s.gameObject.SetActive(false),
    defaultCapacity: 10, maxSize: 20);

Projectile2D next = _pool.Get();
next.Launch(muzzle.position, motor.Aim, CombatTeam.Runner, gameObject);    // activates it
```

- **`Launch` resets everything a flight uses** — direction, age, travel, owner, team, result —
  and activates the object. A field added to the projectile is reset there or it leaks between
  flights.
- **Subscribe to `Finished` in `createFunc`, never per shot.** Per shot, the tenth flight
  releases the object ten times.
- **`Finished` is raised once per flight**, by a hit or by `lifetime`. A shot that leaves the
  screen on a fixed-screen game is ended by lifetime: set it to field height ÷ speed.
- **Trails and particles on a pooled shot** need clearing on release — `unity-game-feel` →
  `reference/trails.md`.
- Warm-up, limits, what a pool must reset: `unity-scene-flow` → `reference/pooling.md`.

## 5. Showing it

The simulated position changes 50 times a second. At 120 frames per second a fast shot visibly
steps. Assign `visual` — a child holding the mesh or sprite and the trail — and the projectile
places it between its last two simulated positions each frame:

```csharp
float alpha = Mathf.Clamp01((Time.time - Time.fixedTime) / Time.fixedDeltaTime);
visual.position = Vector3.Lerp(_previous, transform.position, alpha);
```

The root stays the truth: hits, journeys and the probe read `transform.position`.

## 6. Variants, in brief

| Variant | Change |
|---|---|
| Hitscan | One `Physics.Raycast` or `SphereCast` of the weapon's range on the step the trigger is pulled; build the `DamageInfo` at once. A tracer is presentation |
| Homing | `turnRate` in degrees/s and `homingTarget`. The direction turns by at most `turnRate × dt` per step. Turning radius is `speed ÷ turnRate` in radians: 14 units/s at 180°/s is 4.5 units — a target inside that circle is orbited, not hit. Give homing shots a lifetime |
| Arcing | Keep a velocity, add gravity to it each step, cast along `velocity × dt`. The cast is still one step long |
| Bouncing | On a geometry hit, `Vector3.Reflect(Direction, hit.normal)`, move to the hit, continue with the rest of the step's distance next step; count bounces |
| Area on impact | At the stop point, one `OverlapSphereNonAlloc` on `Hurtbox`, resolved to receivers through a hit list so two hurtboxes are one blast |
| Reflected | Relaunch from the contact with the reflector's team and owner |

## 7. Bullet patterns as data

On a fixed-screen shooter a pattern is four numbers, and a designer changes them without code:

```csharp
[System.Serializable]
public struct ShotPattern
{
    public int count;        // bullets per volley: 5
    public float arc;        // degrees covered, centred on the aim: 60; 360 is a ring
    public float rate;       // volleys per second: 2
    public float speed;      // units/s: 4
    public float spin;       // degrees the aim turns per volley: 0, or 10 for a spiral
}

// Direction of bullet i in a volley aimed along 'aim' (degrees).
static Vector2 Direction(in ShotPattern p, int i, float aim)
{
    float step = p.arc >= 360f ? 360f / p.count
               : p.count > 1 ? p.arc / (p.count - 1) : 0f;
    float a = (aim - (p.arc >= 360f ? 0f : p.arc * 0.5f) + step * i) * Mathf.Deg2Rad;
    return new Vector2(Mathf.Cos(a), Mathf.Sin(a));
}
```

| Pattern | count · arc · rate · speed · spin |
|---|---|
| Aimed burst | 3 · 20 · 1 · 6 · 0 |
| Fan | 5 · 60 · 2 · 4 · 0 |
| Ring | 16 · 360 · 1 · 3 · 0 |
| Spiral | 4 · 360 · 8 · 3 · 10 |

- **Volleys are counted in fixed steps**, not seconds: `rate` 2 is one volley every 25 steps. The
  same run then fires the same bullets, and a journey can assert on the count.
- **Gaps are the design.** At distance `d` neighbouring bullets of a fan are
  `2 · d · sin(step ÷ 2)` apart: a 60° fan of 5 at 4 units leaves 1.04 units between bullets,
  against a runner 0.4 wide. Compute it before tuning by eye.
- **Budget**: live bullets = `count × rate × (field height ÷ speed)`. The fan above on an
  8-unit field is 5 × 2 × 2 = 20; the spiral is 4 × 8 × 2.7 = 85.
- **Keep patterns in an asset**, one per attack — `unity-scene-flow` →
  `reference/scriptable-objects.md`.
- **Past a few dozen live bullets, drop the GameObject per bullet.** Hundreds of bullets are one
  array of structs stepped in a single loop, tested against the runner's hurt circle by
  distance, and drawn in one call — `unity-gameplay` → `reference/genre-2d-fixed-screen.md`.
  The hit still ends in the same `TakeDamage(in DamageInfo)`.

## 8. Checks

| Check | How |
|---|---|
| A fast shot stops at a thin wall | `templates/CombatJourneyTest.cs`, fourth test: 60 units/s against 0.1 units; `COMBAT_JOURNEY_BREAK=cast` turns it red |
| It does not hit its owner | Fire while moving forward at run speed; `runnerDamageEvents` stays 0 |
| The pool never grows | `GameProbe.Count("shots", () => _pool.CountActive)`; hold fire for 5 s and assert it never exceeds rate × lifetime |
| One release per flight | `collectionCheck` left on in the Editor: a double release throws |
| Pattern count is exact | Run 2 s of the fan at a 0.02 step: 4 volleys, 20 bullets |
