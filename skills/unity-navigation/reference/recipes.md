# Agent recipes, animation coupling, and the bake knobs worth turning

> The package half — `Unity.AI.Navigation.NavMeshSurface`, its advanced properties and
> `NavMeshModifierVolume` — needs `com.unity.ai.navigation`. Confirm it is installed first:
> `System.Type.GetType("Unity.AI.Navigation.NavMeshSurface, Unity.AI.Navigation")` returns null
> without it. The Inspector is the authority on every label in §7.

Part of the `unity-navigation` skill. SKILL.md decides *who owns the transform* and *why a path is
partial*; this file is the other half: seven scripts for the jobs people actually ask for, the
Animator coupling on either side of `updatePosition` that stops the character sliding, and the
`NavMeshSurface` settings that decide what gets baked.

## 1. Walk to a target

The smallest thing that works, and the one to fall back to when a more elaborate controller
misbehaves.

```csharp
using UnityEngine;
using UnityEngine.AI;

[RequireComponent(typeof(NavMeshAgent))]
public class SeekTarget : MonoBehaviour
{
    [SerializeField] Transform goal;

    NavMeshAgent agent;

    void Awake() => agent = GetComponent<NavMeshAgent>();

    void Start()
    {
        if (goal != null) agent.destination = goal.position;
    }
}
```

Set the destination once, not every frame, unless the goal actually moves. Re-issuing the same
destination each frame throws away the corridor and re-plans, which is the usual cause of an
agent that pauses fractionally at every corner. If the goal *does* move, gate the re-issue on a
distance threshold:

```csharp
if ((goal.position - lastIssued).sqrMagnitude > 0.25f)
{
    lastIssued = goal.position;
    agent.destination = lastIssued;
}
```

## 2. Click to move

Paste this together with **one** of the two `ClickedThisFrame` bodies below — the class calls that
method and does not compile on its own.

```csharp
using UnityEngine;
using UnityEngine.AI;

[RequireComponent(typeof(NavMeshAgent))]
public class ClickDestination : MonoBehaviour
{
    [SerializeField] Camera view;
    [SerializeField] LayerMask groundMask = ~0;
    [SerializeField] float maxPickDistance = 200f;

    NavMeshAgent agent;

    void Awake()
    {
        agent = GetComponent<NavMeshAgent>();
        if (view == null) view = Camera.main;
    }

    void Update()
    {
        if (!ClickedThisFrame(out Vector2 screenPos)) return;

        Ray ray = view.ScreenPointToRay(screenPos);
        if (!Physics.Raycast(ray, out RaycastHit hit, maxPickDistance, groundMask)) return;

        // The collider you clicked is not necessarily on the NavMesh — a table top, a ramp
        // too steep to bake. Snap to the nearest navigable point before committing.
        if (NavMesh.SamplePosition(hit.point, out NavMeshHit nav, 1.5f, NavMesh.AllAreas))
            agent.destination = nav.position;
    }
}
```

`ClickedThisFrame` is the part that depends on which input backend the project is on, and getting
it wrong is a **runtime** failure, not a compile error:

```csharp
// Input Manager (old). Compiles everywhere.
bool ClickedThisFrame(out Vector2 screenPos)
{
    screenPos = Input.mousePosition;
    return Input.GetMouseButtonDown(0);
}
```

```csharp
// Input System package. using UnityEngine.InputSystem;
bool ClickedThisFrame(out Vector2 screenPos)
{
    var mouse = Mouse.current;
    screenPos = mouse != null ? mouse.position.ReadValue() : Vector2.zero;
    return mouse != null && mouse.leftButton.wasPressedThisFrame;
}
```

> **Read the project's Active Input Handling before pasting either one.**
> `Project Settings → Player → Active Input Handling` has three values, and the old
> `UnityEngine.Input` class keeps compiling under all of them. Under **Input System Package
> (New)** it throws at the first read instead — an exception from a line that looks fine and
> compiled clean. Before pasting the second variant, check that `UnityEngine.InputSystem.Mouse`
> resolves: it lives in the `Unity.InputSystem` assembly that `com.unity.inputsystem` provides.
> Pick **Both** if a project genuinely needs the two, and expect double-fired clicks
> if you then wire up both paths.

Screen-point picking is `Physics.Raycast` against colliders, never `GraphicRaycaster` — see
`unity-physics-3d` §3 for the split, and remember that a UI panel over the cursor does not block
this ray by itself.

## 3. Patrol

Two details separate a patrol that flows from one that stutters at every waypoint.

```csharp
using UnityEngine;
using UnityEngine.AI;

[RequireComponent(typeof(NavMeshAgent))]
public class WaypointPatrol : MonoBehaviour
{
    [SerializeField] Transform[] waypoints;
    [SerializeField] float arriveWithin = 0.5f;

    NavMeshAgent agent;
    int next;

    void Start()
    {
        agent = GetComponent<NavMeshAgent>();

        // Braking is for a destination you stop at. A waypoint is not one.
        agent.autoBraking = false;

        Advance();
    }

    void Update()
    {
        // remainingDistance is Infinity while the path is still being planned, and 0 before
        // planning starts — both read as "arrived" if pathPending is not checked first.
        if (agent.pathPending) return;
        if (agent.remainingDistance > arriveWithin) return;

        Advance();
    }

    void Advance()
    {
        if (waypoints == null || waypoints.Length == 0) return;
        agent.destination = waypoints[next].position;
        next = (next + 1) % waypoints.Length;
    }
}
```

`autoBraking` defaults to **true** (the rest of the agent defaults are in
[`agent-api.md`](agent-api.md) §3), so a patrol written without that one line decelerates into every
corner and accelerates back out. Leave it on for a character that walks to a spot and stands there.

The `pathPending` guard is the same guard as the arrival check in SKILL.md §2, and it is the
reason a freshly started patrol does not skip its whole route on frame one.

## 4. Slow down for sharp corners

Steering will take a corner at full speed and swing wide. Reading the next two corners of the
corridor and scaling `speed` by how sharp the turn is costs one dot product per frame.

```csharp
using UnityEngine;
using UnityEngine.AI;

[RequireComponent(typeof(NavMeshAgent))]
public class CornerSpeedLimiter : MonoBehaviour
{
    [SerializeField] float cornerSpeed = 1.0f;   // speed used on the sharpest turn
    [SerializeField] float slowWithin  = 2.0f;   // start easing off this far from the corner

    NavMeshAgent agent;
    float straightSpeed;

    // Reused every frame — GetCornersNonAlloc writes into this instead of allocating
    // a fresh corner array, which is what reading path.corners would do.
    readonly Vector3[] corners = new Vector3[3];

    void Awake()
    {
        agent = GetComponent<NavMeshAgent>();

        // Cached once, and not in OnEnable: re-enabling mid-corner would otherwise cache the
        // lowered speed this script just wrote and cap every straight run from then on.
        straightSpeed = agent.speed;
    }

    void OnDisable()
    {
        // Hand the tuned speed back, or the next system to read it inherits a corner value.
        if (agent != null) agent.speed = straightSpeed;
    }

    void Update()
    {
        int count = agent.path.GetCornersNonAlloc(corners);
        if (count < 3)
        {
            agent.speed = straightSpeed;      // straight run, or already on the last leg
            return;
        }

        Vector3 legIn  = (corners[1] - corners[0]).normalized;
        Vector3 legOut = (corners[2] - corners[1]).normalized;

        // 1 = straight ahead, 0 = right angle, negative = doubling back.
        float straightness = Mathf.Clamp01(Vector3.Dot(legIn, legOut));
        float atCorner = Mathf.Lerp(cornerSpeed, straightSpeed, straightness);

        // Only apply the limit as the corner approaches.
        float approach = Mathf.Clamp01(Vector3.Distance(corners[0], corners[1]) / slowWithin);
        agent.speed = Mathf.Lerp(atCorner, straightSpeed, approach);
    }
}
```

`path.corners` allocates a fresh `Vector3[]` on every read; `GetCornersNonAlloc` fills a buffer
you own and returns how many it wrote — a method on `NavMeshPath`.

**That is not the same as an allocation-free `Update`, and it is worth being exact about which
half you bought.** `NavMeshAgent.path`'s getter is a copy, not the agent's own object, so the
loop above still costs one `NavMeshPath` per agent per frame; `GetCornersNonAlloc` removes the
corner array inside it, not the object around it. Treat "one object per agent per frame" as the
number to budget for, and confirm it in the Profiler, with a live agent on a baked surface, if a
crowd makes it matter.

If it does, own the path instead of reading the agent's: fill a `NavMeshPath` field of your own
with `agent.CalculatePath(destination, myPath)` and hand it over with `agent.SetPath(myPath)`
(both public on `NavMeshAgent`), then read corners off the field you kept. The trade is that
you are reading the corridor *you* computed rather than whatever the agent re-planned since, so
re-issue it on the same distance threshold as §1.

`OnDisable` restores `agent.speed`. Without it the next system to read the speed inherits a
corner value, and re-enabling the script mid-corner would cache that value as the new straight
speed.

## 5. Coupling the agent to the animation

Both rows of the table in SKILL.md §3, written out. Row 1 first, because it is the default and
most characters never need row 2.

### Agent drives, animation follows (the default)

`updatePosition` and `updateRotation` stay `true`, the agent moves the transform, and the
Animator only reports what happened. One float is the whole coupling.

```csharp
using UnityEngine;
using UnityEngine.AI;

[RequireComponent(typeof(NavMeshAgent))]
[RequireComponent(typeof(Animator))]
public class AgentSpeedToAnimator : MonoBehaviour
{
    static readonly int SpeedHash = Animator.StringToHash("speed");

    NavMeshAgent agent;
    Animator anim;

    void Start()
    {
        agent = GetComponent<NavMeshAgent>();
        anim = GetComponent<Animator>();
    }

    // agent.velocity is the post-avoidance velocity — what the character is actually doing.
    // Divide by agent.speed and the blend tree parameter is 0..1 whatever the tuning.
    void Update() => anim.SetFloat(SpeedHash, agent.velocity.magnitude / Mathf.Max(0.01f, agent.speed));
}
```

That is a one-dimensional blend tree on `speed`: idle at 0, walk around 0.5, run at 1. Feed it
`agent.desiredVelocity` instead and the character animates the movement it *intended*, including
avoidance it is not performing — which is the bug SKILL.md §3 warns about. Accept some foot
sliding in exchange for the simplicity; the arrangement below is what removes it.

### Animation drives, agent advises (root motion)

This variant hands the transform to the Animator while the agent keeps planning — it removes the
sliding, at the cost of one rule you must not forget.

```csharp
using UnityEngine;
using UnityEngine.AI;

[RequireComponent(typeof(NavMeshAgent))]
[RequireComponent(typeof(Animator))]
public class AgentLocomotion : MonoBehaviour
{
    [SerializeField] float smoothing = 0.15f;
    [SerializeField] float moveThreshold = 0.5f;

    static readonly int MoveHash = Animator.StringToHash("move");
    static readonly int VelXHash = Animator.StringToHash("velx");
    static readonly int VelYHash = Animator.StringToHash("vely");

    NavMeshAgent agent;
    Animator anim;
    Vector2 smoothed;
    Vector2 localVelocity;

    void Start()
    {
        agent = GetComponent<NavMeshAgent>();
        anim = GetComponent<Animator>();

        // The Animator owns the transform's position from here on. The agent keeps steering
        // and keeps its own internal position, which is what nextPosition reports.
        agent.updatePosition = false;

        // updateRotation stays true on purpose: facing is still the agent's, so the character
        // turns toward its corridor while the Animator supplies the stride. Turn it off only
        // when something else writes transform.rotation — nothing here does.
    }

    void Update()
    {
        Vector3 drift = agent.nextPosition - transform.position;

        // Project the agent's intent into the character's own frame: x is strafe, y is forward.
        Vector2 step = new Vector2(Vector3.Dot(transform.right, drift),
                                   Vector3.Dot(transform.forward, drift));

        smoothed = Vector2.Lerp(smoothed, step, Mathf.Min(1f, Time.deltaTime / smoothing));
        if (Time.deltaTime > 1e-5f) localVelocity = smoothed / Time.deltaTime;

        bool moving = localVelocity.magnitude > moveThreshold
                   && agent.remainingDistance > agent.radius;

        anim.SetBool(MoveHash, moving);
        anim.SetFloat(VelXHash, localVelocity.x);
        anim.SetFloat(VelYHash, localVelocity.y);
    }

    void OnAnimatorMove()
    {
        // Snap the visible character onto the agent's internal position. Skip this and the
        // agent advances forever while nothing on screen moves.
        transform.position = agent.nextPosition;
    }
}
```

> **`updatePosition = false` without a write-back is a silent hang.** The agent's internal
> position keeps advancing along the corridor, the transform never follows, and the character
> plays a walk cycle on the spot while `remainingDistance` counts down to a place it never
> reaches. The write-back is the `OnAnimatorMove` body above. SKILL.md §3 states the same
> contract from the other direction: whoever does not own the transform must be told where it
> went.
>
> **Before concluding the write-back is missing, check that it is being called at all.** An
> `OnAnimatorMove` that never runs — check **Apply Root Motion** on the Animator first — produces
> the identical hang with the write-back already written, and reading the script tells you
> nothing. Log from inside `OnAnimatorMove`, in a live Editor with the real rig, and see whether
> the line appears.

To let root motion supply the horizontal instead — higher animation quality, more drift to
manage — keep the vertical from the agent, take the rest from `Animator.rootPosition`
(a read-write `Vector3`), and pull the character
back if it strays further than its own radius:

```csharp
void OnAnimatorMove()
{
    Vector3 p = anim.rootPosition;
    p.y = agent.nextPosition.y;          // the NavMesh still decides the height
    transform.position = p;
}

// at the end of Update():
if (drift.magnitude > agent.radius)
    transform.position = agent.nextPosition - 0.9f * drift;
```

### The blend tree the second arrangement expects

`AgentLocomotion` writes `velx` / `vely`, not one `speed` float, so it needs a directional tree
rather than the 1D one the default arrangement uses.

| Setting | Value |
|---|---|
| Blend type | **2D Simple Directional** |
| Compute positions | **Velocity XZ** |
| Parameters | `velx`, `vely` — both `float` |
| Motions | **seven directional clips** (forward, the two diagonals, the two strafes, the two backwards) plus a **run-in-place** clip at the origin |
| Idle → Move | driven by the `move` bool, **Has Exit Time off**, transition ~0.1 s |

The run-in-place clip at (0, 0) is not decoration: 2D Simple Directional blends between the
nearest motions, and with nothing at the origin a slow agent blends two opposing directional
clips against each other, which reads on screen as feet skating. **Has Exit Time off** matters
for the same class of reason — with it on, the character finishes the current idle cycle before
starting to walk, and the agent has already left.

Set the agent's `speed` to roughly the clip's own locomotion speed. Everything the blend tree
does is proportional; a `speed` of 6 against clips authored at 3 makes the character run at
double rate no matter how the tree is tuned. Building the controller and its parameters is
`unity-rigged-character`.

### Look where you are going

`agent.steeringTarget` is the next corner of the corridor — the point the agent is actually
steering toward, which is not the destination and is usually the more natural thing for a head
to track.

```csharp
void OnAnimatorIK(int layerIndex)
{
    // weight, bodyWeight, headWeight, eyesWeight, clampWeight
    anim.SetLookAtWeight(1f, 0.2f, 0.7f, 0f, 0.5f);
    anim.SetLookAtPosition(agent.steeringTarget + Vector3.up * 1.5f);
}
```

`OnAnimatorIK` is only called on a layer with **IK Pass** enabled, and only on a Humanoid rig — a
Generic rig gets nothing and no warning. `SetLookAtWeight` has five overloads, one argument through
five, and the shorter ones default the weights you omit. Raise the target by roughly eye height, or
the character stares at its own feet.

## 6. Baking at runtime

```csharp
using UnityEngine;
using Unity.AI.Navigation;

[RequireComponent(typeof(NavMeshSurface))]
public class RuntimeSurface : MonoBehaviour
{
    NavMeshSurface surface;

    void Awake() => surface = GetComponent<NavMeshSurface>();

    // First bake: allocates the NavMeshData and registers it.
    public void BakeFresh() => surface.BuildNavMesh();

    // Subsequent bakes: reuses the existing NavMeshData in place. Cheaper, and agents
    // standing on the mesh keep their footing instead of falling off a null surface.
    public void Rebake() => surface.UpdateNavMesh(surface.navMeshData);
}
```

Call `BuildNavMesh()` once, after the level geometry exists and before any agent is enabled.
Everything after that is `UpdateNavMesh(surface.navMeshData)` — for a streamed chunk, a
generated room, a bridge that just extended. The bake is fast enough to be a real automated
test: SKILL.md §7 has the headless bake and the shape of the assertion.

A rebake does not repair agents that were left standing on nothing. Sequence it: bake, then
`NavMesh.SamplePosition` + `agent.Warp` for anything that needs re-seating.

**The headless bake-and-query test** SKILL.md §7 describes, written out. It runs in a batch-mode
Editor in milliseconds over a couple of primitives, and the assertion is on the status:

```csharp
var surf = root.AddComponent<Unity.AI.Navigation.NavMeshSurface>();
surf.collectObjects = Unity.AI.Navigation.CollectObjects.Children;
surf.BuildNavMesh();
var p = new UnityEngine.AI.NavMeshPath();
UnityEngine.AI.NavMesh.CalculatePath(from, to, UnityEngine.AI.NavMesh.AllAreas, p);
return p.status;              // assert on status, NOT on CalculatePath's bool
```

## 7. The bake knobs

`NavMeshSurface` advanced settings, all from the `com.unity.ai.navigation` package. The Inspector
is the authority on each exact label.

**Voxel size, expressed as voxels per agent radius.** Baking rasterises the scene into a voxel
grid; the voxel size decides what survives. The default is **3 voxels per agent radius**, which
is a doorway-and-corridor number and correct for most scenes.

| Scene | Voxels per radius | Why |
|---|---|---|
| Wide open terrain, few pinch points | 1–2 | Bakes faster, uses less memory, loses detail nobody walks into |
| General case | **3** (default) | Doorways and gaps resolve correctly |
| Tight interiors, thin ledges, cluttered props | 4–6 | Narrow gaps stop being rounded shut |
| Anything | more than 8 | Bake time and memory keep climbing; the mesh stops improving |

The failure this setting produces is one-directional and easy to misread: too coarse a voxel
rounds a passage closed, and the report arrives as "the agent refuses to go through the door".
The mesh is not broken — that surface was never generated.

**Override Tile Size.** The bake is tiled, 256 voxels a tile by default, and a carving obstacle
re-bakes the tiles it touches. In a scene with many carving obstacles, dropping the tile size to
**64–128** makes each re-carve cheap because each tile is small. It is a trade, not a free win:
more tiles means more seams, more fragmentation, and more per-tile overhead in a scene that
carves rarely. Turn it down when carving is the cost; leave it alone otherwise. §4 of SKILL.md
decides *whether* an obstacle should carve at all — settle that first, because the cheapest
re-carve is the one that does not happen.

**Minimum Region Area.** Discards baked islands smaller than the threshold. It is the tool for a
scene that bakes a scatter of unreachable postage stamps on top of crates, window sills and
prop clutter — each of which is a place `SamplePosition` can snap an agent to, stranding it
somewhere with no path out. Raise it until the litter disappears; raise it too far and you delete
a small platform that was meant to be reachable.

**Build Height Mesh.** Stores extra vertical detail so agents are placed on the real surface
rather than on the flat polygon that approximates it. Stairs are the case that needs it: without
it, a character climbing steps floats and sinks against the visual mesh. It costs bake time and
memory, so it is a per-surface decision, not a project default.

**Drop Height and Jump Distance belong to the agent type, not the surface.** They are edited in
`Window → AI → Navigation → Agents`, alongside radius, height, step height and max slope, and
they are what **Generate Links** on the surface uses to decide where an automatic link may be
created: a ledge within Drop Height gets a drop-down, a gap within Jump Distance gets a
jump-across. Both default to 0, which means Generate Links produces nothing and reads as
"link generation is broken". Set the agent type first, then bake.

A surface bakes for exactly one agent type. Two character sizes means two surfaces, and an agent
whose type does not match any baked surface finds no mesh at all — with no error, because from
its point of view nothing was ever baked.

**Modifier Volume overlap.** `NavMeshModifierVolume` stamps an area type over a region of space,
whatever happens to be in it — the tool for "agents may not walk here" when there is no object
to mark. Where two volumes overlap, the **highest area index wins**, with one exception that
overrides everything: **Not Walkable (index 1) always takes precedence**, regardless of index or
ordering. That asymmetry is deliberate and it is what makes a blocking volume dependable — you
can drop one over a hazard without auditing every custom area a designer added since.

## 8. Areas, costs and masks

SKILL.md §5 says areas express preference rather than possibility. This section is the arithmetic
and the bitmask behind that sentence.

**The three built-in areas have fixed indices**, and code that assumes otherwise breaks on the
first project that added its own:

| Area | Index | What it is |
|---|---|---|
| Walkable | 0 | Everything a surface bakes by default |
| Not Walkable | 1 | Blocks pathing, and wins every overlap (§7) |
| Jump | 2 | What **Generate Links** stamps on the links it creates |

Indices **3–31** are yours, named in `Window → AI → Navigation → Areas`. Twenty-nine of them,
which is far more than a level needs — name them for what the agent thinks about them (`Hazard`,
`GateLane`), not for what the art is.

**Cost is a distance multiplier.** The path cost of a stretch is `distance × area cost`, so A\*
treats a costly area as a longer one. Costs are above `1.0`; below that the pathfinder can
prefer a detour to a shortcut and the routes stop making sense. A hazard lane at cost `3.0`
prices 10 units of hazard the same as 30 units of clear lane — so a runner with a clear lane
within 30 units goes around, and **a runner with no clear lane still runs straight through it**.
Cost never forbids. If the hazard must be impassable, it is `Not Walkable` or a modifier volume,
not a large number.

Per-agent overrides live on the agent (`agent.SetAreaCost(3, 5.0f)`, SKILL.md §5) and leave every
other agent's view of the level alone — one timid courier without a second bake.

**A mask forbids.** `areaMask` is a bitfield of area indices, and an agent plans only inside it:

```csharp
// This runner may use plain ground and the gate lane (custom area 3), nothing else.
agent.areaMask = (1 << 0) | (1 << 3);

// A sentry gets the same level without the gate lane, so it patrols around the gate
// rather than through it — no second NavMesh, no extra collider, no scripting at the door.
sentry.areaMask = 1 << 0;
```

Two traps: **leave area 0 out and the agent has almost nothing to stand on**, which reads exactly
like a failed bake; and the mask is planning-only, so an agent already standing inside an excluded
area finds no path out of it — put the spawn on a permitted area.

**`agent.Raycast` is a line-of-walk test, not a physics query.** It walks the NavMesh from the
agent to a point and reports the first edge it runs into:

```csharp
if (agent.Raycast(pickup.position, out var hit))
{
    // Blocked: hit.position is where the walkable surface ends, hit.distance how far that is.
    // A gap with no link reads as blocked here, which is the point.
}
```

It costs a fraction of a full path request, so it is the cheap pre-check before a chase commits —
and it answers about the *mesh*, so a collider added after the bake is invisible to it, exactly as
it is to pathing (SKILL.md §4). Colliders are `unity-physics-3d`.

## Related

- SKILL.md §2 — path status, `SamplePosition`, and why the `CalculatePath` bool lies
- SKILL.md §3 — who owns the transform; [`agent-api.md`](agent-api.md) §3 — the agent defaults
- SKILL.md §4 — carve or avoid, before you tune tile size
- `unity-rigged-character` — Animator controllers, Avatars, IK Pass and the rig itself
- `unity-physics-3d` — colliders, `Physics.Raycast` and the raycaster split
- AI Navigation package manual: <https://docs.unity3d.com/Packages/com.unity.ai.navigation@latest>
