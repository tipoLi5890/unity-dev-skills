# SpriteShape — terrain that is a curve, not a grid

> Part of the `unity-2d-level` skill. When organic ground is a spline with sprites along it
> instead of tiles: open and closed shapes, corner sprites, the collider the shape generates,
> editing the spline from code, and where a Tilemap is still the better tool.

REQUIRES `com.unity.2d.spriteshape` (part of the 2D feature set; read the resolved version off
`Packages/packages-lock.json`). Types are in `UnityEngine.U2D`, assembly
`Unity.2D.SpriteShape.Runtime`. The members named here are the same in the 13.x and 14.x lines of
the package, so one script serves both.

A Tilemap can only say "this cell is ground". A hillside, a cave wall or a rope bridge is a line
with thickness, and drawing it in tiles means stair-steps and a slope tile for every angle. A
SpriteShape is that line: a spline, a profile that says which sprite runs along which angle, and
an optional fill.

## The three parts

| Part | Is | Holds |
|---|---|---|
| **Sprite Shape Profile** | An asset (`SpriteShape`; **Assets ▸ Create ▸ 2D ▸ Sprite Shape Profile**) | `angleRanges` — which edge sprites draw at which slope; `cornerSprites` — eight corner slots; `fillTexture`; `fillOffset`; `useSpriteBorders` |
| **`SpriteShapeController`** | The component on the scene object | `spline`, `spriteShape` (the profile), `splineDetail`, `fillPixelsPerUnit`, `stretchTiling`, the collider settings |
| **`SpriteShapeRenderer`** | Added with the controller | Sorting layer and order, like any renderer |

Create one with **GameObject ▸ 2D Object ▸ Sprite Shape ▸ Open Shape** or **Closed Shape**.

**Edge sprites carry their own end caps.** With `useSpriteBorders` on, an edge sprite's left and
right 9-slice borders are used where a run of that sprite starts and stops, and the middle
repeats between them. Borders are sprite metadata: `unity-2d-sprites`.

**The fill texture's wrap mode is Repeat.** A clamped fill smears its edge pixels across the
whole interior.

## Open or closed

| | Open shape | Closed shape |
|---|---|---|
| `spline.isOpenEnded` | `true` | `false` |
| Draws | Edge sprites along the line, no fill | Edge sprites around the loop and the fill texture inside |
| Collider it drives | `EdgeCollider2D` | `PolygonCollider2D` (or an `EdgeCollider2D` for a hollow boundary) |
| Use for | A platform, a bridge, a ledge the sentry patrols, a ground surface whose underside is never seen | A hill, an island, a cave mass — anything with an inside |
| Angle ranges | One range for the top is enough | A range for each side that shows: top, walls, ceiling |

**Angle ranges follow the direction the outline is drawn in.** A closed shape whose points run
the other way round shows its top sprite on the underside. If the grass grows downwards,
reverse the point order, not the profile.

## Corners

A corner sprite replaces the two edge sprites where they meet, and it is drawn only when all of
these hold:

1. The control point's corner mode is `Corner.Automatic` — what `InsertPointAt` gives a new
   point. `Corner.Disable` switches the corner off; `Corner.Stretched` bends the edge sprite
   round the point instead of placing a corner sprite.
2. The point **and both neighbours** are in `ShapeTangentMode.Linear`.
3. The three points have the same height.
4. The angle at the point is within `cornerAngleThreshold` of a right angle (30° by default).
5. The profile has a sprite in the matching slot — `CornerType.OuterTopLeft`, `OuterTopRight`,
   `OuterBottomLeft`, `OuterBottomRight` and the four `Inner…` ones.

A smooth hillside has no corners at all: its points are `Continuous`. Corners belong to shapes
that are polygons with a tileset's look — rooftops drawn as outlines, a depot's loading dock.

## The collider

Add an `EdgeCollider2D` or a `PolygonCollider2D` to the same object and the controller writes
the shape's outline into it. `hasCollider` is true when either is present.

| Setting | Default | Meaning |
|---|---|---|
| `autoUpdateCollider` | `true` | The controller regenerates the collider's points when the shape changes. Off, the collider is yours to edit and goes stale when the spline moves |
| `colliderDetail` | 16 (`QualityDetail.High`) | Points generated per curved segment. 4 to 8 is plenty for gameplay; 16 on every hill is a physics cost with nothing to show for it |
| `colliderOffset` | 0 | Pushes the collider outwards (positive) or inwards from the visual edge. A small negative value lets feet sink into the grass by a pixel or two instead of floating on it |
| `optimizeCollider` | — | Drops collinear points |

- **Grounding on a curve needs the motor to read the surface normal.** A platformer motor that
  assumes flat tiles slides or hops on a slope — the motor side is `unity-2d-controller` →
  `reference/platformer.md`.
- **An `EdgeCollider2D` has no inside.** Nothing pushes out a body that got past it, so a
  fast body can pass through and nothing pushes it back; give the body continuous collision
  detection, or close the shape and use a polygon. Body settings: `unity-physics-2d` →
  `reference/bodies-and-simulation.md`.
- **One static body for the terrain.** Parent every terrain shape under one object with a
  `Static` `Rigidbody2D`, as the Tilemap layers are.

## Editing the spline from code

```csharp
using UnityEngine;
using UnityEngine.U2D;

// Lay an open shape along a list of surface points — a generated hillside, a bridge.
public static class SurfaceShape
{
    public static void Lay(SpriteShapeController shape, Vector3[] localPoints)
    {
        Spline spline = shape.spline;
        spline.Clear();
        spline.isOpenEnded = true;
        for (int i = 0; i < localPoints.Length; i++)
        {
            spline.InsertPointAt(i, localPoints[i]);            // throws when two points coincide
            spline.SetTangentMode(i, ShapeTangentMode.Continuous);
            Vector3 prev = localPoints[Mathf.Max(i - 1, 0)];
            Vector3 next = localPoints[Mathf.Min(i + 1, localPoints.Length - 1)];
            Vector3 tangent = (next - prev) * 0.25f;            // a quarter of the span each side
            spline.SetLeftTangent(i, -tangent);
            spline.SetRightTangent(i, tangent);
            spline.SetHeight(i, 1f);
        }
        shape.RefreshSpriteShape();                             // rebuild mesh and collider
    }
}
```

- **`InsertPointAt` and `SetPosition` throw `ArgumentException`** when the point lies within
  0.01 units of its neighbour. Generated points need a minimum spacing; half a unit is a sane
  floor.
- **Positions are in the shape's local space.** A shape that is scaled or rotated scales and
  rotates its spline; keep terrain shapes at identity and move the points.
- **`RemovePointAt` does nothing once two points remain**: a spline keeps at least two.
- **`RefreshSpriteShape()` only marks the shape**: it is generated again on the next frame, and
  only if it is visible. A shape edited off screen, or a body spawned onto it in the same frame,
  finds the old collider. When the collider is needed now, call `BakeMesh().Complete()` and then
  `BakeCollider()`, and confirm in a Play Mode test that an overlap query hits the new outline.
- **Tangents are relative to the point**, and `Continuous` mode wants the left and right
  tangents opposite. Unequal lengths are fine; unaligned ones need `ShapeTangentMode.Broken`.

## Where a Tilemap is still better

| Need | Use |
|---|---|
| Ground on a grid: rooftops, rooms, corridors, anything a level file describes cell by cell | Tilemap — `reference/layer-stack.md` |
| The level is data that a validator, a generator or an external editor reads and writes | Tilemap. A spline has no cells; `scripts/level_validate.py` cannot search it |
| Destructible or runtime-edited terrain | Tilemap: one `SetTile`. Re-tessellating a spline every change costs more and the result is not a cell |
| One-way platforms in a row | Tilemap `OneWay` layer with one effector |
| Rolling hills, cave outlines, a curved bridge, organic set dressing over a tile level | SpriteShape |
| Pixel art at a fixed pixels-per-unit | Tilemap. A curve resamples the edge sprite along its length and breaks the pixel grid — `unity-2d-pixel-perfect` |

The two mix well in one level: tiles for everything the runner's reach is held to,
shapes for the hillside behind it and the slope into the next room. When a shape **is** walkable
ground, it sits outside the level data's guarantees — cover it with a journey that runs across
it (`unity-play-harness` → `reference/journeys.md`) instead of the cell search.

## Checks

- Select the shape in play: the collider's outline follows the visible edge within
  `colliderOffset`, with far fewer points than the mesh has vertices.
- A closed shape's top sprite is on top. If not, the point order is reversed.
- Corners appear at right angles and nowhere else; a missing one fails rule 2 or 3 above more
  often than rule 5.
- After a runtime edit, a body resting on the shape stays resting on the new outline.
