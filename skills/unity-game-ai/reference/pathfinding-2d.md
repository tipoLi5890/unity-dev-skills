# Pathfinding in 2D — three routes, and how to choose

> Part of the `unity-game-ai` skill. A 2D enemy that must get round shelving has three ways to
> find its way: A* over the cells the level is already drawn on, a NavMesh laid on the XY plane,
> or no path at all — a velocity steered round obstacles. This file is how each works behind
> `IMover`, what each costs, and a check to run before committing to the second. Worked
> settings: the **depot** (aisles between shelving, from above) and the **sorting yard** (cells).

## 0. Choose

| The level is | Route | Because |
|---|---|---|
| Authored on a Tilemap; walls are whole cells; aisles 1–2 cells wide | **Grid A*** — §1 | The walkable map already exists as cells. Exact, deterministic, no bake |
| Movement is by the cell | **Grid A*** — §1 | The path *is* the list of steps |
| Free-form colliders, wide rooms, diagonal walls, many agents that must avoid each other | **NavMesh on XY** — §2, after its check passes | Any-angle paths and agent avoidance come with it; so do 3D proxy geometry and a bake |
| An open arena with a few pillars; swarms; flying things | **Steering** — §3 | Nothing to plan: head for the target and bend round what is in the way |
| A side view under gravity | None of the three. Walkers follow the roof they stand on (`reference/patrol-and-chase.md` §6); anything that must cross gaps needs links authored by hand between platforms | A walkable surface under gravity is a set of segments, not an area |

When two fit, take the earlier row. A grid path under a free-moving body is the default for a
tile-authored game and covers most of them.

## 1. Grid A*

The search itself — the heap, the heuristic per neighbour rule, corner cutting, per-unit
passability — is `unity-2d-grid` → `reference/pathfinding.md` and its
`resources/GridPathfinder.cs`. What this skill adds is the two ways to put it behind `IMover`.

### Moving by the cell

The sentry steps from cell to cell; the cell map owns its position and the transform is a tween.

```csharp
// CellSentryMover.cs — beside GridStepMover (driveFromInput off), over GridPathfinder.
[RequireComponent(typeof(GridStepMover))]
public sealed class CellSentryMover : MonoBehaviour, IMover
{
    public Grid grid;
    public GridPathfinder Finder;                         // one per board, shared
    public System.Func<Vector3Int, bool> CanEnter;        // the occupancy map's answer

    GridStepMover _stepper;
    GridPathfinder.EnterCost _cost;
    readonly List<Vector3Int> _path = new List<Vector3Int>(64);
    Vector3Int _goal;
    int _next, _stopCells;
    bool _hasGoal;

    public Vector3 Position => transform.position;
    public Vector3 Velocity => _stepper.Velocity;
    public bool Arrived => !_hasGoal || (_next >= _path.Count - _stopCells && !_stepper.Stepping);

    void Awake()
    {
        _stepper = GetComponent<GridStepMover>();
        // The goal is allowed even when occupied — it is where the runner stands; the path stops short of it.
        _cost = (from, to) => to == _goal || CanEnter == null || CanEnter(to) ? 1 : 0;
    }

    public void MoveTo(Vector3 destination, float speed, float stoppingDistance)
    {
        _stepper.stepTime = grid.cellSize.x / Mathf.Max(speed, 0.01f);
        _stopCells = Mathf.RoundToInt(stoppingDistance / grid.cellSize.x);
        Vector3Int goal = grid.WorldToCell(destination);
        if (_hasGoal && goal == _goal) return;            // same cell: keep the path
        _goal = goal;
        _hasGoal = Finder.FindPath((Vector3Int)_stepper.Cell, goal, _cost, _path);
        _next = 1;                                        // entry 0 is the cell the sentry stands on
    }

    public void Stop() => _hasGoal = false;               // a step in progress finishes: the cell is the position
    public void Face(Vector3 direction) { }

    void FixedUpdate()
    {
        if (!_hasGoal || _stepper.Stepping || _next >= _path.Count - _stopCells) return;
        Vector3Int step = _path[_next] - (Vector3Int)_stepper.Cell;
        if (_stepper.TryStep(new Vector2Int(step.x, step.y))) _next++;
        else _hasGoal = false;                            // something moved into the way: re-path on the next MoveTo
    }
}
```

- **The search runs when the goal's cell changes**, not on the re-path interval: the brain may
  call `MoveTo` four times a second, and a runner standing still costs four integer compares.
- **A blocked step drops the path** and the next `MoveTo` searches again from where the sentry
  is. Never search inside the step loop.
- **`FindPath` to an occupied goal fails** unless the cost function lets the goal through, which
  the delegate above does; `stoppingDistance` of one cell then keeps the sentry off the runner's
  cell.
- This is a Rect4 board. On a hexagonal one a step is not a `Vector2Int` difference — convert
  with `GridCoords.DirectionTo`, `unity-2d-grid` → `reference/coordinates.md`.
- The stepper, commit-then-tween and refused steps: `unity-2d-controller` →
  `reference/grid-step.md`. Who stands where: `unity-2d-grid` →
  `reference/occupancy-and-turns.md`.

### A free body following a cell path

The depot's sentry moves freely on a `TopDownMotor2D` but plans on cells: the path's cell
centres become waypoints for the straight-line adapter in `reference/patrol-and-chase.md` §6.

```csharp
// Inside the adapter's MoveTo, when the goal's cell changed:
_finder.FindPath(grid.WorldToCell(_body.position), grid.WorldToCell(destination), _cost, _cells);
_corner = 1;

// Inside its FixedUpdate, before steering at the current waypoint:
// skip ahead while the next-but-one centre is reachable in a straight line.
while (_corner + 1 < _cells.Count && Open(_body.position, grid.GetCellCenterWorld(_cells[_corner + 1])))
    _corner++;
Vector2 waypoint = _corner < _cells.Count - 1 ? (Vector2)grid.GetCellCenterWorld(_cells[_corner]) : _destination;
if (((Vector2)_body.position - waypoint).sqrMagnitude < 0.1f * 0.1f && _corner < _cells.Count - 1) _corner++;

bool Open(Vector2 from, Vector2 to)       // the body fits along the segment
    => Physics2D.CircleCast(from, bodyRadius, to - from, _filter, _hit, (to - from).magnitude) == 0;
```

- **Skipping waypoints is what removes the staircase.** A raw cell path walks in right angles;
  one circle cast per step to the next-but-one centre lets the body cut every corner it fits
  round. One cast per step per moving sentry — if the crowd is large, do it on the decision
  tick instead.
- **Use the 8-neighbour rule with corners closed** (`GridShape.Rect8`, `CutCorners` false) for
  a free body, or the path squeezes diagonally between two shelves the collider cannot pass.
- **The body's radius must be under half a cell**, or a one-cell aisle the search calls open is
  one the body cannot enter. 0.3 on a 1-unit cell is the depot's number.
- **The final waypoint is the destination itself**, not its cell's centre, so the sentry stops
  at `stoppingDistance` from the runner and not from the middle of the runner's tile.

## 2. A NavMesh on the XY plane — check before committing

What the navigation package (`com.unity.ai.navigation` 2.0) provides for this, from its source:

| Fact | Consequence |
|---|---|
| `NavMeshSurface` collects geometry in two modes — `useGeometry` is `RenderMeshes` (mesh renderers and terrains) or `PhysicsColliders` (the 3D collision representation). The build sources are meshes, terrains, 3D boxes, spheres, capsules and modifier boxes | Sprites, Tilemaps and 2D colliders are not sources. The surface bakes from **3D proxy geometry** you add for it |
| `BuildNavMesh` builds in the surface's own frame: it passes the surface transform's position and rotation to the builder | The surface's local up is the walkable normal. Rotate the surface object **(−90, 0, 0)** and its up points along world −Z, towards a default 2D camera |
| `NavMeshAgent` has `updateUpAxis` and `updateRotation` | Both must be false, or the agent tips the sprite onto its back to match the surface |
| `NavMeshModifier` has `overrideArea` and `area`; the built-in Not Walkable area always wins an overlap | Shelving proxies marked Not Walkable cut holes and get no NavMesh on top |

So the route exists, and it is a 3D NavMesh standing on its edge with a second copy of the
level's collision made for it. Whether that is worth it is a check, not an opinion.

**Set up the scratch scene:**

1. An empty object rotated (−90, 0, 0) with a `NavMeshSurface`: Collect Objects *All Game
   Objects*, Use Geometry *Physics Colliders*, Include Layers a `NavProxy` layer only.
2. On `NavProxy`: one 3D `BoxCollider` for the floor, 0.1 thick in z, covering the depot; one
   3D `BoxCollider` per run of shelving, 1 deep in z, each with a `NavMeshModifier` — Override
   Area on, Area *Not Walkable*. 3D and 2D physics never interact, so the proxies change nothing
   in the game.
3. An agent type whose radius is the sentry's 2D collider radius (0.3), set on the surface and
   on the agent.
4. A sentry sprite with a `NavMeshAgent` and **no** dynamic `Rigidbody2D`.

**Run the check** — play mode, one line in the log:

```csharp
// NavMeshXYCheck.cs — a scratch scene, play mode, one JSON line. Delete it afterwards.
// REQUIRES com.unity.ai.navigation.
using Unity.AI.Navigation;
using UnityEngine;
using UnityEngine.AI;

public sealed class NavMeshXYCheck : MonoBehaviour
{
    public NavMeshSurface surface;       // rotated (-90, 0, 0); Use Geometry: Physics Colliders
    public NavMeshAgent agent;
    public Vector2 openFloor = new Vector2(0f, 0f);
    public Vector2 insideShelf = new Vector2(3f, 0f);
    public Vector2 goal = new Vector2(8f, 4f);

    System.Collections.IEnumerator Start()
    {
        surface.BuildNavMesh();
        agent.updateRotation = false;
        agent.updateUpAxis = false;

        int vertices = NavMesh.CalculateTriangulation().vertices.Length;
        bool floor = NavMesh.SamplePosition(openFloor, out NavMeshHit onFloor, 0.5f, NavMesh.AllAreas);
        bool shelf = NavMesh.SamplePosition(insideShelf, out _, 0.2f, NavMesh.AllAreas);
        bool placed = agent.Warp(openFloor) && agent.isOnNavMesh;
        bool path = placed && agent.SetDestination(goal);

        float worstZ = 0f;
        for (float t = 0f; t < 5f; t += Time.deltaTime)
        {
            worstZ = Mathf.Max(worstZ, Mathf.Abs(agent.transform.position.z));
            yield return null;
        }

        Debug.Log("[NAVXY] {\"vertices\":" + vertices + ",\"floorSampled\":" + J(floor) +
                  ",\"floorZ\":" + onFloor.position.z.ToString("F3") + ",\"shelfSampled\":" + J(shelf) +
                  ",\"agentOnNavMesh\":" + J(placed) + ",\"pathAccepted\":" + J(path) +
                  ",\"pathStatus\":\"" + agent.pathStatus + "\",\"worstZ\":" + worstZ.ToString("F3") +
                  ",\"distanceLeft\":" + Vector2.Distance(agent.transform.position, goal).ToString("F2") +
                  ",\"rotation\":\"" + agent.transform.eulerAngles + "\"}");
    }

    static string J(bool b) => b ? "true" : "false";
}
```

| Key | Commit only if | Otherwise |
|---|---|---|
| `vertices` | Above 0 | Nothing was collected: the layer mask, or the surface is not rotated and the floor is edge-on to it |
| `floorSampled` · `floorZ` | `true` · within 0.1 of the floor proxy's face | The surface's up is not −Z |
| `shelfSampled` | `false`, with `insideShelf` at least 0.5 from the shelf's edge | The modifier is not applied: Override Area is off, or the proxy is not on a collected layer |
| `agentOnNavMesh` · `pathAccepted` | `true` · `true` | The agent type on the agent and on the surface differ |
| `pathStatus` | `PathComplete` | `PathPartial`: the goal is cut off — an aisle narrower than twice the agent radius |
| `worstZ` | Under 0.1 | The agent is being pulled along z: `baseOffset`, or the proxy floor is not at the sprites' z |
| `distanceLeft` | Under the stopping distance plus 0.1 | It did not get there in 5 s: speed, or a partial path |
| `rotation` | All zero | `updateUpAxis` or `updateRotation` was still on when the agent first moved |

Then price what the check does not show:

- **The proxies are a second level.** Every shelf moved in the Tilemap must move in `NavProxy`.
  Generate them from the collision Tilemap in an editor script — one box per rectangle of
  blocked cells — or the two drift. If that script is more work than §1, §1 was the answer.
- **The agent and a `Rigidbody2D` are two writers.** Either the agent owns the transform (a
  kinematic `Rigidbody2D` may ride along for triggers, written by nobody), or the agent only
  advises and the 2D motor moves the body:

```csharp
// AdvisedMover2D — beside TopDownMotor2D: the agent plans, the motor moves.
void Awake()
{
    agent.updatePosition = false;         // the agent plans; it does not move the body
    agent.updateRotation = false;
    agent.updateUpAxis = false;
}

void FixedUpdate()
{
    agent.nextPosition = transform.position;              // tell the agent where the body really is
    Vector3 wish = agent.desiredVelocity;
    SetMove(wish.sqrMagnitude > 0.01f ? (Vector2)wish.normalized : Vector2.zero);
}
```

  That is the arrangement `unity-navigation` → `reference/recipes.md` §5 uses for root motion,
  with a 2D motor in the Animator's place; the rule it warns about — keep `nextPosition` in
  step with the body — applies unchanged.
- **Baking, agent types, obstacles, partial paths** are all `unity-navigation`; nothing about
  them changes on this plane.

## 3. Steering — no path at all

For an arena with a few pillars, the "path" is the direction to the target, bent when something
is in the way. One circle cast along the wish; if it hits, try the same cast at widening angles
and take the first that is clear.

```csharp
// Steer2D.cs — beside the sentry's mover. REQUIRES com.unity.modules.physics2d (built in).
public sealed class Steer2D : MonoBehaviour
{
    public LayerMask obstacles = 1;
    public float bodyRadius = 0.3f;
    [Tooltip("Units ahead that must be clear. About 0.3 s of travel: 1.5 at 5 units/s.")]
    public float lookAhead = 1.5f;

    static readonly float[] Angles = { 0f, 30f, -30f, 60f, -60f, 90f, -90f };
    readonly RaycastHit2D[] _hit = new RaycastHit2D[1];
    float _side = 1f;

    /// <summary>The direction nearest to 'wish' with nothing within lookAhead, or zero when boxed in.</summary>
    public Vector2 Around(Vector2 position, Vector2 wish)
    {
        var filter = new ContactFilter2D();
        filter.SetLayerMask(obstacles);
        filter.useTriggers = false;
        for (int i = 0; i < Angles.Length; i++)
        {
            // The side that worked last time is tried first, so the sentry does not dither at a pillar.
            float angle = Angles[i] * _side;
            Vector2 direction = Quaternion.AngleAxis(angle, Vector3.forward) * wish;
            if (Physics2D.CircleCast(position, bodyRadius, direction, filter, _hit, lookAhead) > 0) continue;
            if (angle != 0f) _side = Mathf.Sign(angle);
            return direction;
        }
        return Vector2.zero;
    }
}
```

In the straight-line adapter, `SetMove(to.normalized)` becomes
`SetMove(_steer.Around(_body.position, to.normalized))`.

| Property | Number |
|---|---|
| Casts per moving sentry per step | 1 in the open; up to 7 beside an obstacle |
| Look-ahead | 0.3 s of travel. Shorter clips corners; longer avoids things that are not in the way |
| What it cannot do | Leave a dead end. A U of shelving between sentry and runner holds it for ever |

- **Remember the side.** Without `_side`, a sentry facing a pillar dead on picks left, moves,
  finds right is now nearer to the wish, picks right, and vibrates.
- **Separation between sentries** is the same idea with other sentries as the obstacles: add a
  small velocity away from any neighbour within one body width. Use a list of sentries, not a
  physics overlap per sentry per step.
- **The dead end is the limit, and the cure is the level.** Steering suits arenas whose
  obstacles are convex and apart. The first L-shaped wall is the signal to move to §1.
- A swarm of 50 steering sentries casts 50–350 times a step. Throttle it: steer on alternate
  steps per sentry and keep the last direction in between.

## 4. Checks

| Check | How |
|---|---|
| A path exists where the designer thinks one does | `Finder.FindPath` from each spawn cell to the gate cell at load, in an edit-mode test over the level data: `false` is a walled-in spawn |
| The free body can walk the path it was given | A journey with the sentry registered as the probe's player, and `JourneyInvariants2D.NeverInside2D` over the shelving layer |
| The search is not run per step | `Finder.Expanded` summed per second in the probe: flat while the runner stands still |
| The NavMesh route holds | §2's JSON line, every key in its "commit only if" column |
| Steering does not trap | Drive the runner behind each obstacle in turn; `sentryDist` must fall within 5 s each time |

## Where each need is answered

| Need | Answer |
|---|---|
| The A* itself, heuristics, corner rules, costs per unit | `unity-2d-grid` → `reference/pathfinding.md` |
| Cell coordinates on rectangular, isometric and hexagonal boards | `unity-2d-grid` → `reference/coordinates.md` |
| Occupancy and reservations so two sentries do not share a cell | `unity-2d-grid` → `reference/occupancy-and-turns.md` |
| The walkable map from Tilemap layers | `unity-2d-level` → `reference/layer-stack.md` |
| Circle casts and filters | `unity-physics-2d` → `reference/queries-2d.md` |
| Baking, agent types, links, obstacles | `unity-navigation` |
| The adapters these routes plug into | `reference/patrol-and-chase.md` |
| Paths for a turn-based unit | `reference/tactics-ai.md` |
