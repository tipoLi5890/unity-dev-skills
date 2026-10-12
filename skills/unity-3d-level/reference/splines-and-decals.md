# Splines and decals — paths, rails, the runner's lane, and marks on the floor

> Part of the `unity-3d-level` skill. The Splines package for anything that follows a curve — a
> road, a rail, a patrol route, the lane run's track — how to evaluate a position and a facing
> along it, extruding a road mesh, and URP's Decal Projector for markings, with what it needs
> and what it costs. Worked setting: the **lane run**, three lanes 1.3 units apart, the middle
> lane numbered 1, bent along a curve.

REQUIRES `com.unity.splines` for §1–§4 and URP for §5–§6.

## 1. What a spline is here

| Type (`UnityEngine.Splines`) | Is |
|---|---|
| `SplineContainer` | The component. Holds one or more `Spline`s; `container.Splines`, `container[0]`, `container.Spline` (the first) |
| `Spline` | A list of `BezierKnot`, open or `Closed`, in the container's **local** space |
| `BezierKnot` | Position, in and out tangents, rotation |
| `TangentMode` | `AutoSmooth` (a curve through the points), `Linear` (straight segments), and the hand-edited modes |
| `NativeSpline` | A read-only copy baked with a transform, for jobs and for thousands of evaluations a frame |

```csharp
// A track from points. AddSpline is an extension on the container (using UnityEngine.Splines).
var container = track.AddComponent<SplineContainer>();          // starts with one empty spline
container.Spline = new Spline(points, TangentMode.AutoSmooth);  // points: IEnumerable<float3>, local space
Spline siding = container.AddSpline();                          // a second spline in the same container
```

Draw one in the editor with GameObject ▸ Spline ▸ Draw Splines Tool; snap its knots to the
grid of `reference/modular-kit.md` so the track meets the kit.

## 2. Evaluating

| Call | Returns | Space |
|---|---|---|
| `container.Evaluate(splineIndex, t, out float3 position, out float3 tangent, out float3 up)` | All three at once; `false` when there is no spline | World |
| `container.EvaluatePosition(t)` · `EvaluateTangent(t)` · `EvaluateUpVector(t)` | One of them | World |
| `container.CalculateLength(splineIndex)` | Length of the curve | World |
| `spline.ConvertIndexUnit(d, PathIndexUnit.Distance, PathIndexUnit.Normalized)` | `t` for a distance | Local |
| `SplineUtility.GetNearestPoint(spline, point, out float3 nearest, out float t)` | Distance from `point` to the curve; the nearest point and its `t` | **Local** — convert the point with `container.transform.InverseTransformPoint` first |
| `spline.GetPointAtLinearDistance(fromT, distance, out float resultT)` | The point a straight-line distance further on | Local |

- **`t` is a fraction of the curve's length**, 0 at the first knot and 1 at the last. Equal
  steps of `t` are equal distances along the curve, so `t = distance / length` holds without a
  lookup of your own.
- **The tangent is not normalised.** Normalise it before building a rotation.
- **Sideways is a cross product:** `right = cross(up, forward)`. Use world up for `up` on a
  track that must stay level; use the spline's up vector on a banked rail.
- **Cache the length.** `CalculateLength` walks the curve; call it when the spline changes
  (`Spline.Changed`), not every frame.
- **Keep the container's scale uniform.** Under a non-uniform scale local distances and world
  distances stop agreeing.

## 3. The runner's lane on a curve

The lane run stores two numbers for the runner — distance along the track and lane index — and
a third while changing lane, the sideways offset it is easing towards. `resources/SplineLane.cs`
turns them into a pose:

```csharp
// In the one component that writes the runner's transform. RunController owns distance and lane.
_distance += forwardSpeed * dt;                                               // 12 units/s
_lateral = Mathf.MoveTowards(_lateral, lane.LaneOffset(_laneIndex), (1.3f / 0.15f) * dt);
if (lane.Evaluate(_distance, _lateral, out Vector3 position, out Quaternion rotation))
    _body.MovePosition(position);                                             // kinematic Rigidbody
```

| Member | Gives |
|---|---|
| `laneSpacing` 1.3 · `laneCount` 3 · `level` true | The fields; lanes stay level against world up unless `level` is off |
| `LaneOffset(lane)` | −1.3, 0, +1.3 for lanes 0, 1, 2: lane 1 is the spline itself; lane 0 is to the left of travel |
| `Evaluate(distance, lateral, out position, out rotation)` | World pose; wraps on a closed track, clamps at the ends of an open one |
| `EvaluateLane(distance, lane, …)` | The same at a lane centre — where a hazard or a pickup goes |
| `Project(worldPoint, out distance, out lateral)` · `NearestLane(lateral)` | Where on the track a world point is, and which lane that is |
| `Length` · `Rebuild()` | Cached world length; call `Rebuild` after editing the spline at runtime |

It needs a Runtime asmdef that references `Unity.Splines` and `Unity.Mathematics`. Selected, it
draws the lanes as gizmo lines.

Three rules the curve adds to the lane run's metrics (`unity-gameplay` →
`reference/level-metrics.md`, last section):

- **Place hazards and pickups by `(distance, lane)`**, through `EvaluateLane`, never by world
  position. Sight distance — 4.8 units at 12 units/s — is then a difference of distances and
  stays true round a bend.
- **Keep the bend radius at least 8.** Each lane off the spline is `1.3 / radius` shorter or
  longer than the middle one through a bend — 16% at a radius of 8 — and an offset lane folds
  over itself where the radius drops under its offset, 1.3.
- **The spline answers; it does not move anything.** `SplineAnimate` writes the transform
  itself — a second writer on a runner that already has one. Use it for a cart or a drone that
  nothing else moves, and give that a kinematic `Rigidbody` if it carries a collider.

## 4. Roads, rails and things along them

| Component | Makes | Set |
|---|---|---|
| `SplineExtrude` | A mesh swept along the spline, on its own `MeshFilter` and `MeshRenderer` | `Radius`, `Sides`, `SegmentsPerUnit`, `Capped`, `Range`; `Rebuild()` after a change from code. With a `MeshCollider` on the same object it keeps the collider's mesh up to date |
| `SplineInstantiate` | Prefab instances along the spline: fence posts, lamps, barriers | `itemsToInstantiate`, `MinSpacing` / `MaxSpacing`, `Seed`; `UpdateInstances()` |

- A tube is the default profile. The **Road** profile (`UnityEngine.Splines.ExtrusionShapes`) is
  a flat ribbon; choose it in the component's Shape setting.
- A tube is `2 × Radius` across. The Road profile's flat top is `Radius` wide, with a skirt a
  tenth of that beyond each edge. Three lanes of 1.3 need at least 3.9: set `Radius` 4.4 for a
  road with a quarter-metre shoulder each side, and read the mesh's bounds once on a straight.
- `SegmentsPerUnit` is the triangle budget: 1 on straights is plenty, 2–4 on tight bends. A
  200-unit track at 2 with a 3-sided profile is about 2,400 triangles.
- **The extruded mesh is a fine collider only for a road.** A flat ribbon as a non-convex
  `MeshCollider` on `World` is what the runner stands on; a tube rail needs a capsule chain or
  no collision at all — `reference/collision-proxies.md`.
- Without a Target Mesh the extruded mesh is not saved: it is rebuilt every time the component
  is enabled. Before lightmapping the final track, give it a mesh asset (the Inspector's Target
  Mesh field creates one).
- Instances from `SplineInstantiate` are created by the component, not placed: do not hand-edit
  them, change the spline or the seed.

## 5. Decals — the Decal Projector

Lane arrows, hazard stripes, a stain under the gate. A `DecalProjector`
(`UnityEngine.Rendering.Universal`) projects a material onto whatever is inside its box.

**It draws nothing until the active URP Renderer has the Decal renderer feature.** The
projector's Inspector says "The current renderer has no Decal Renderer Feature added"; the
Game view says nothing. Add it on the Renderer asset the active quality level uses — which
asset that is, and why changing the wrong one does nothing, is `unity-render-urp` →
`reference/resolve-active-pipeline.md`.

| `DecalProjector` member | Default | Set it to |
|---|---|---|
| `material` | — | A material on a Shader Graph whose Material is **Decal** |
| `size` | 1 × 1 × 1 | Width, height, **projection depth**. Keep depth small — 0.2–0.5 — so it marks the floor and not the crate standing on it |
| `pivot` | 0, 0, 0.5 | Half the depth, so the box starts at the transform |
| `drawDistance` | 1000 | 20–40. Beyond it the decal is not drawn; this is the main cost lever |
| `fadeScale` | 0.9 | The fraction of `drawDistance` at which fading starts |
| `startAngleFade` · `endAngleFade` | 180 · 180 | 60 · 80 to stop a floor decal smearing down a wall; needs Angle Fade enabled in the graph |
| `fadeFactor` | 1 | Animate it to fade a mark out |
| `uvScale` · `uvBias` | 1 · 0 | Pick a cell of an atlas, so many decals share one material |
| `renderingLayerMask` | Default layer | Which rendering layers it lands on (§6) |

The projector points along its local +Z: rotate it 90° about X to mark a floor.

The feature's **Technique** decides what a decal can change and what it costs:

| Technique | Needs | Fits |
|---|---|---|
| DBuffer | A depth-normals prepass over the scene | Desktop and console; decals blend colour, normal and surface properties correctly under lighting |
| Screen Space | Normals rebuilt from depth (Normal Blend Low, Medium, High) | Mobile and tile-based GPUs; drawn over the opaques afterwards, so it cannot blend each surface property separately the way DBuffer does |
| Automatic | — | Picks one of the two from the build platform. Read which one a device got before tuning for it |

On a deferred renderer the screen-space route writes into the G-buffer instead.

## 6. Decal layers, and the cost

- **Keep decals off the runner.** Turn on Use Rendering Layers in the feature, give floors and
  walls a rendering layer (`Renderer.renderingLayerMask`) and set each projector's
  `renderingLayerMask` to it. Characters and pickups are left out and walk over the marking
  instead of wearing it. These are rendering layers, not the GameObject layers of
  `reference/collision-proxies.md`.
- **One material, many projectors.** Enable GPU instancing on the decal material and pack
  markings into an atlas: projectors that share a material draw together.
- **Budget:** 20–30 projectors on screen on a phone, each with a `drawDistance` no longer than
  the camera needs. A DBuffer prepass is a second pass over the opaque scene — measure it:
  `unity-profiling` → `reference/counters.md`.
- **A marking that never moves on a flat floor does not need a projector.** A quad 0.01 above
  the surface with an alpha-blended unlit material is one cheap draw, needs no feature, and
  batches with its neighbours. Use projectors where the surface is uneven — terrain, stairs, a
  road over a hill.
- **Greybox markings are markers,** not decals: the coloured pads of `reference/greybox.md`.
  Decals arrive with the art.

## Traps

- **Evaluating with a world point in `GetNearestPoint`.** It works until the container is
  moved; then every result is offset by the container's position.
- **`container.Spline = …` on a container with no splines.** The setter replaces the first
  spline and does nothing when there is none; a container added from code has one, a container
  whose list was cleared does not — use `AddSpline`.
- **Using the knot index as progress.** Knots are unevenly spaced; `t` is by length.
- **A track far from the origin.** Past a few thousand units positions lose precision and the
  runner shimmers. Loop the spline, or recentre the track and the runner together.
- **A decal projecting through the floor** onto the room below. Shorten `size.z`.
- **Decals on transparent surfaces.** Projectors affect opaque geometry only.
- **Adding the feature to one Renderer asset when the quality level uses another.** Nothing
  draws on the device and everything draws in the Editor.

## Where each need is answered

| Need | Answer |
|---|---|
| Lane spacing, lane-change time, hazard sight distance | `unity-gameplay` → `reference/level-metrics.md` |
| The lane runner's controller and its one writer | `unity-gameplay` → `reference/genre-3d.md` |
| Swipes that change lane | `unity-input` → `reference/touch-and-on-screen.md` |
| A camera that follows the runner round the bend | `unity-camera` → `reference/follow-3d.md` |
| A patrol that follows a NavMesh, not a spline | `unity-navigation` → `reference/recipes.md` |
| Which Renderer asset is active; renderer features | `unity-render-urp` → `reference/resolve-active-pipeline.md` |
| Collision for the road and the rail | `reference/collision-proxies.md` |
| A road across terrain | `reference/terrain.md` |
| Lighting a generated track | `unity-lighting` → `reference/bake-setup.md` |
| Draw calls before and after the decals | `unity-profiling` → `reference/counters.md` |
