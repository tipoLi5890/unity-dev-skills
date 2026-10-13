using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Boot-scene registration for a 2D game: three situations and every probe hook, in one place.
/// The 2D sibling of CourierSituations.cs — Rigidbody2D and Collider2D, the x/y plane, and
/// velocity through GameProbe.SetPlayerVelocity.
///
/// Copy into a Runtime folder next to GameProbe.cs and Situations.cs, attach to an object in the
/// boot scene, and replace each call marked "replace with your game's method". Nothing here is
/// game logic — every line either reads a value the game already owns or calls a method the
/// player's input already reaches.
/// REQUIRES com.unity.modules.physics2d (built in; read Packages/manifest.json).
///
/// Each situation belongs to one view of the same courier run. Keep the one your game is and
/// delete the other two with their probe block:
///   ledge-drop    side run      the runner at a rooftop edge, a gap below
///   depot-aisle   top-down      the runner in an aisle, a sentry's vision cone ahead
///   yard-step     sorting yard  the runner one cell from a pickup that goes onto a gate cell
///
/// After wiring it up, prove it from the outside before writing a single test:
///   unity command eval 'return string.Join(",", Situations.Ids());'
///   unity command situation_enter -- --id ledge-drop
///   unity command probe
/// </summary>
public sealed class CourierSituations2D : MonoBehaviour
{
    [Header("Scene references")]
    public Transform runner;
    public Rigidbody2D runnerBody;
    public Collider2D runnerCollider;
    public Transform gate;

    // ---- Replace these with your game's own components. -----------------------------------
    // RunController: owns the run's state machine and the commands the input funnel sends.
    // RooftopTrack, DepotLayout, YardGrid: own the level's visuals AND its 2D colliders.
    // SentryController, PickupPool: the two things the moment needs to be complete.
    // The real ones: unity-game-ai's SentryBrain, unity-scene-flow's PickupObjectPool; swap them in.
    RunController _run;
    RooftopTrack _rooftops;
    DepotLayout _depot;
    YardGrid _yard;
    SentryController _sentry;
    PickupPool _pickups;

    void Awake()
    {
        _run = FindAnyObjectByType<RunController>();            // replace with your game's lookup
        _rooftops = FindAnyObjectByType<RooftopTrack>();
        _depot = FindAnyObjectByType<DepotLayout>();
        _yard = FindAnyObjectByType<YardGrid>();
        _sentry = FindAnyObjectByType<SentryController>();
        _pickups = FindAnyObjectByType<PickupPool>();

        RegisterProbe();
        RegisterSituations();
    }

    // ----------------------------------------------------------------- probe

    void RegisterProbe()
    {
        // state: the game's own machine, converted to a string. Never a copy.
        GameProbe.SetState(() => _run.Phase.ToString());        // replace with your game's state

        // vel and speed come from one delegate, so the probe never names a 2D type. Return
        // whatever moves the runner: Rigidbody2D.linearVelocity here, CharacterController.velocity,
        // a kinematic motor's own Velocity, or a grid mover's step velocity. The null check is
        // inside the delegate because a destroyed body would otherwise throw on every sample.
        GameProbe.SetPlayerVelocity(() => runner,
            () => runnerBody != null ? (Vector3)runnerBody.linearVelocity : Vector3.zero);

        // A runner drawn without its collider falls through the first rooftop it lands on.
        GameProbe.Ready("runner", () => runner != null && runner.gameObject.activeInHierarchy);
        GameProbe.Ready("runnerCollider", () => runnerCollider != null && runnerCollider.enabled
                                                && runnerBody != null && runnerBody.simulated);

        // A member registered here is part of allReady for the whole session, so each view
        // registers only when its level object is in the scene.
        if (_rooftops != null) RegisterSideRun();
        if (_depot != null) RegisterDepot();
        if (_yard != null) RegisterYard();
    }

    void RegisterSideRun()
    {
        // The pair that must arrive in the same pass: the rooftop you can see, and the
        // collider under it. Split them and the runner is drawn on a roof it falls through.
        GameProbe.Ready("rooftopMesh", () => _rooftops.Built);
        GameProbe.Ready("rooftopCollider", () => _rooftops.Ground != null && _rooftops.Ground.enabled);
        GameProbe.Ready("gapHazard", () => _rooftops.GapHazard != null && _rooftops.GapHazard.enabled);

        GameProbe.Register("ledgeDist", () => runner != null ? _rooftops.LedgeX - runner.position.x : -1f);
        GameProbe.Register("height", () => runner != null ? runner.position.y - _rooftops.RoofY : 0f);
        GameProbe.Register("grounded", () => _run.Grounded);
    }

    void RegisterDepot()
    {
        GameProbe.Ready("aisleFloor", () => _depot.Built);
        GameProbe.Ready("aisleWalls", () => _depot.Walls != null && _depot.Walls.enabled);
        GameProbe.Ready("pickups", () => _pickups != null && _pickups.Warm);

        GameProbe.Count("pickups", () => _pickups != null ? _pickups.ActiveCount : 0);
        GameProbe.Register("lane", () => _run.Lane);
        GameProbe.Register("laneOffset", () => runner != null ? runner.position.x : 0f);
        GameProbe.Register("sentryDist", () => _sentry != null && runner != null
            ? Vector2.Distance(runner.position, _sentry.transform.position) : -1f);
        GameProbe.Register("seen", () => _sentry != null && _sentry.SeesRunner);
    }

    void RegisterYard()
    {
        GameProbe.Ready("yardCells", () => _yard.Built);
        GameProbe.Ready("yardWalls", () => _yard.Walls != null && _yard.Walls.enabled);

        // The cell is the fact; pos is only where the step animation has got to.
        GameProbe.Register("cellX", () => _run.Cell.x);
        GameProbe.Register("cellY", () => _run.Cell.y);
        GameProbe.Register("pickupToGate", () => YardGrid.Steps(_yard.PickupCell, _yard.GateCell));
        GameProbe.Register("stepping", () => _run.Stepping);
    }

    // ----------------------------------------------------------------- situations

    void RegisterSituations()
    {
        Situations.Register(new Situation("ledge-drop", EnterLedgeDrop, 15f)
            .Needs("runnerCollider")
            .Needs("rooftopMesh")
            .Needs("rooftopCollider")
            .Needs("gapHazard"));

        // Three aisles, 1.3 units apart, middle aisle is 1.
        Situations.Register(new Situation("depot-aisle", EnterDepotAisle, 15f)
            .Needs("runnerCollider")
            .Needs("aisleFloor")
            .Needs("aisleWalls")
            .Needs("sentry", () => _sentry != null && _sentry.Patrolling)
            .Needs("visionCone", () => _sentry != null && _sentry.VisionCone != null
                                       && _sentry.VisionCone.enabled && _sentry.VisionCone.isTrigger));

        Situations.Register(new Situation("yard-step", EnterYardStep, 12f)
            .Needs("runnerCollider")
            .Needs("yardCells")
            .Needs("yardWalls")
            .Needs("pickup", () => _yard != null && _yard.PickupCollider != null
                                   && _yard.PickupCollider.enabled)
            .Needs("gateCell", () => _yard != null && _yard.GateCollider != null
                                     && _yard.GateCollider.enabled));
    }

    /// <summary>Side run: on the rooftop, inset units short of the edge, already running at it.</summary>
    void EnterLedgeDrop()
    {
        float inset = Situations.Param("inset", 1.5f);
        bool cold = Situations.Param("cold", false);

        if (cold) _rooftops.DropStreamedSections();             // replace with your game's method
        _run.ResetRun(1);
        _run.PlaceAt(_rooftops.PointBeforeLedge(inset), Vector2.right);
        _run.Launch();
    }

    /// <summary>Top-down depot: in an aisle, the sentry posted ahead and facing back down it.</summary>
    void EnterDepotAisle()
    {
        int lane = Situations.Param("lane", 1);
        float distance = Situations.Param("distance", 6f);

        _run.ResetRun(lane);                                    // replace with your game's method
        _sentry.Post(_depot.SentryPost(lane), Vector2.down);
        _run.PlaceAt(_depot.SentryPost(lane) + Vector2.down * distance, Vector2.up);
        _run.Launch();
    }

    /// <summary>
    /// Sorting yard: the pickup one cell short of the gate cell, the runner one cell behind the
    /// pickup, so a single step in dir pushes it home. Nothing moves until that step.
    /// </summary>
    void EnterYardStep()
    {
        int dx = Situations.Param("dx", 1);
        int dy = Situations.Param("dy", 0);
        var dir = new Vector2Int(dx, dy);

        _yard.ResetCells();                                     // replace with your game's method
        _yard.PlacePickup(_yard.GateCell - dir);
        _run.ResetRun(1);
        _run.PlaceAtCell(_yard.GateCell - dir - dir, _yard.CellCentre(_yard.GateCell - dir - dir));
        _run.Launch();
    }

    // -----------------------------------------------------------------------------------------
    // The shapes this template assumes. Delete this block and the names above resolve to the
    // real components; it is here so the file reads as a complete example rather than as a
    // sketch. They are nested so this file and CourierSituations.cs, which declares its own
    // RunController, SentryController and PickupPool, compile side by side. Until the block is
    // deleted a nested name shadows a game type of the same name: the lookups in Awake then
    // find nothing and every hook logs "[PROBE] hook threw".
    // -----------------------------------------------------------------------------------------

    public enum RunPhase { Idle, Launched, Approach, AtGate, Crashed, Done }

    public sealed class RunController : MonoBehaviour
    {
        public RunPhase Phase { get; private set; }
        public int Lane { get; private set; }
        public Vector2Int Cell { get; private set; }
        public Vector2 Facing { get; private set; }
        public bool Grounded { get; private set; }
        public bool Stepping { get; private set; }

        public void ResetRun(int lane) { Lane = lane; Phase = RunPhase.Idle; }

        public void PlaceAt(Vector2 point, Vector2 facing)
        {
            // z is the sorting depth in a 2D scene; a placement must leave it alone.
            transform.position = new Vector3(point.x, point.y, transform.position.z);
            Facing = facing;
        }

        public void PlaceAtCell(Vector2Int cell, Vector2 centre)
        {
            Cell = cell;
            PlaceAt(centre, Facing);
        }

        public void Launch() { Phase = RunPhase.Launched; }
    }

    /// <summary>Side run: rooftops along +x, gravity on -y, a gap after LedgeX.</summary>
    public sealed class RooftopTrack : MonoBehaviour
    {
        public bool Built { get; private set; }
        public Collider2D Ground;       // a CompositeCollider2D over the rooftop tiles, or a box
        public Collider2D GapHazard;    // the trigger under the gap that ends the run
        public float LedgeX = 40f;
        public float RoofY = 6f;
        public float GapWidth = 3f;

        public Vector2 PointBeforeLedge(float inset) => new Vector2(LedgeX - inset, RoofY);
        public void DropStreamedSections() { Built = false; }
    }

    /// <summary>Top-down depot: aisles run along +y, three of them 1.3 units apart on x.</summary>
    public sealed class DepotLayout : MonoBehaviour
    {
        public bool Built { get; private set; }
        public Collider2D Walls;        // the shelving between aisles
        public float SentryY = 12f;

        public Vector2 SentryPost(int lane) => new Vector2((lane - 1) * 1.3f, SentryY);
    }

    /// <summary>Sorting yard: a rectangular board; swap CellCentre for an iso or hex mapping.</summary>
    public sealed class YardGrid : MonoBehaviour
    {
        public bool Built { get; private set; }
        public Collider2D Walls;
        public Collider2D PickupCollider;
        public Collider2D GateCollider;
        public Vector2Int GateCell = new Vector2Int(5, 3);
        public Vector2Int PickupCell { get; private set; }
        public float CellSize = 1f;

        public Vector2 CellCentre(Vector2Int cell)
            => (Vector2)transform.position + new Vector2((cell.x + 0.5f) * CellSize, (cell.y + 0.5f) * CellSize);

        public static int Steps(Vector2Int a, Vector2Int b) => Mathf.Abs(a.x - b.x) + Mathf.Abs(a.y - b.y);

        public void ResetCells() { PickupCell = GateCell; }

        public void PlacePickup(Vector2Int cell)
        {
            PickupCell = cell;
            if (PickupCollider == null) return;
            Vector2 c = CellCentre(cell);
            Transform t = PickupCollider.transform;
            t.position = new Vector3(c.x, c.y, t.position.z);
        }
    }

    public sealed class SentryController : MonoBehaviour
    {
        public bool Patrolling { get; private set; }
        public bool SeesRunner { get; private set; }
        public Collider2D VisionCone;   // a PolygonCollider2D marked Is Trigger

        public void Post(Vector2 point, Vector2 facing)
        {
            transform.position = new Vector3(point.x, point.y, transform.position.z);
            transform.up = facing;
        }
    }

    public sealed class PickupPool : MonoBehaviour
    {
        public bool Warm { get; private set; }
        public int ActiveCount => _live.Count;
        readonly List<GameObject> _live = new List<GameObject>();
    }
}
