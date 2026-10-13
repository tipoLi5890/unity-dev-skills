# Trails and lines — a streak that follows, and one that must not follow a teleport

> Part of the `unity-game-feel` skill. `TrailRenderer` for a dash and a launch, `LineRenderer`
> for a projectile tracer and a beam, and the one call — `Clear` — that every respawn, lane snap
> and pool reuse needs.

## 1. TrailRenderer — what each setting does

A `TrailRenderer` drops a point each time its transform moves `minVertexDistance`, and each point
lives `time` seconds. It draws a strip through the points, widened by `widthCurve` along its
length (0 at the head, 1 at the tail).

| Setting | Dash trail | Launch streak | Why |
|---|---|---|---|
| `time` | 0.15 s | 0.3 s | How long the streak is, in seconds of history. At a 20 units/s dash, 0.15 s is 3 units |
| `widthMultiplier` | 0.6 | 0.25 | World units at the widest point |
| `widthCurve` | 1 → 0 | 1 → 0 | A taper reads as speed; a constant width reads as a ribbon |
| `colorGradient` | alpha 0.8 → 0 | alpha 1 → 0 | Fades the tail rather than cutting it |
| `minVertexDistance` | 0.1 | 0.1 | Smaller is smoother and costs vertices; larger makes curves angular |
| `emitting` | Off at rest; on during the dash | On during the launch | Stops new points; the existing ones fade out by their own time |
| `autodestruct` | Off | Off | On destroys the GameObject when the trail empties — never on a pooled or a character object |
| Material | Unlit, additive or alpha-blended | Same | URP `Particles/Unlit` works and is the default particle material |

Toggle `emitting`, not `enabled`. Disabling the renderer hides the trail at once — the streak
vanishes mid-dash — and a re-enabled renderer resumes with the points it had.

```csharp
// RunController, dash start and end. The trail sits on the Visual child.
void BeginDash() { dashTrail.Clear(); dashTrail.emitting = true; }
void EndDash()   { dashTrail.emitting = false; }          // the tail fades over trail.time
```

## 2. Clear — on every jump that is not motion

The trail cannot tell a teleport from a very fast move. When the runner respawns at a checkpoint,
snaps lanes by assignment, or comes out of a pool at a new place, the trail draws a streak from
the old position to the new one across the whole screen.

| Event | Call, in this order |
|---|---|
| Respawn, checkpoint load, scene reposition | Move the transform, then `trail.Clear()` |
| Lane snap by assignment (no interpolation) | Move, then `Clear()` — or keep the trail and tween the move instead |
| Pool get | Position the object, then `Clear()`, then `emitting = true` |
| Pool release | `emitting = false`, `Clear()` |

`Clear` removes every point now. Called before the move, the frame's move still adds a segment
from old to new; call it after. With interpolation on a rigidbody, the visual position catches up
over a frame: clear again on the next frame, or teleport through `Rigidbody.position` and clear
after the physics step.

`unity-combat` → `reference/projectiles.md` and `unity-scene-flow` → `reference/pooling.md`
both list this as part of what a pooled shot must reset; this is the call they mean.

## 3. A projectile tracer with LineRenderer

A fast shot moves several units per step; a trail on it is a dotted line of segments. A tracer
drawn from the shot's last position to its current one is exact and costs two points:

```csharp
// On the shot's visual. The shot moves by cast-per-step; this draws the step it just took.
[RequireComponent(typeof(LineRenderer))]
public sealed class Tracer : MonoBehaviour
{
    [SerializeField] float length = 1.5f;       // cap on the streak: one step's travel, at most this
    LineRenderer _line;
    readonly Vector3[] _points = new Vector3[2];

    void Awake()
    {
        _line = GetComponent<LineRenderer>();
        _line.useWorldSpace = true;
        _line.positionCount = 2;
    }

    void OnEnable() { _points[0] = _points[1] = transform.position; _line.SetPositions(_points); }

    void LateUpdate()
    {
        Vector3 head = transform.position;
        Vector3 tail = _points[1];
        Vector3 back = tail - head;
        if (back.sqrMagnitude > length * length) tail = head + back.normalized * length;
        _points[0] = tail; _points[1] = head;
        _line.SetPositions(_points);
    }
}
```

`OnEnable` collapses both points onto the head, so a pooled shot never draws from where it
died. Width 0.05–0.1, a gradient from transparent at the tail to bright at the head.

A beam (a sentry's sight line, a laser hazard across a lane) is the same `LineRenderer` with the
far point set from a raycast each frame: `_points[1] = hit ? hitInfo.point : origin + dir * range`.

## 4. 2D

`TrailRenderer` and `LineRenderer` are renderers with `sortingLayerName` and `sortingOrder`, and
sort with sprites by the same keys (`unity-2d-rendering` → `reference/sort-order.md`). Set
`alignment` to `LineAlignment.View` (the default) so the strip faces an orthographic camera, and
keep the object's z at the characters' plane. In a pixel-art game a smooth trail is out of style:
use a short sprite after-image instead — three copies of the current frame dropped at intervals
of 0.03 s, each fading over 0.12 s from a pool.

## 5. Cost

A trail rebuilds its mesh every frame it has points. Tens are free; hundreds of bullets each
with a `TrailRenderer` are not — that is the case for the two-point tracer above, or for
particles with trails off a single system. If a profiling capture names trail or line meshes,
cut `time` and raise `minVertexDistance` before anything else.
