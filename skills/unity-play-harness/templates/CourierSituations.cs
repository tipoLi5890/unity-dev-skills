using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Boot-scene registration: three situations and every probe hook, in one place.
///
/// Copy into a Runtime folder next to GameProbe.cs and Situations.cs, attach to an object in the
/// boot scene, and replace each call marked "replace with your game's method". Nothing here is
/// game logic — every line either reads a value the game already owns or calls a method the
/// player's input already reaches.
///
/// After wiring it up, prove it from the outside before writing a single test:
///   unity command eval 'return string.Join(",", Situations.Ids());'
///   unity command situation_enter -- --id approach-gate
///   unity command probe
/// </summary>
public sealed class CourierSituations : MonoBehaviour
{
    [Header("Scene references")]
    public Transform runner;
    public Rigidbody runnerBody;
    public Transform gate;

    // ---- Replace these four with your game's own components. ------------------------------
    // RunController: owns the run's state machine and the three commands the gamepad sends.
    // TrackStreamer: owns the lane mesh, its collider and the hazard volume.
    // SentryController, PickupPool: the two things the moment needs to be complete.
    RunController _run;
    TrackStreamer _track;
    SentryController _sentry;
    PickupPool _pickups;

    void Awake()
    {
        _run = FindAnyObjectByType<RunController>();            // replace with your game's lookup
        _track = FindAnyObjectByType<TrackStreamer>();
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
        GameProbe.SetPlayer(() => runner, () => runnerBody);

        // Readiness members the game owns. A situation can then name them without re-deriving
        // them, and the same members answer "is this moment assembled" from every entry point.
        GameProbe.Ready("laneMesh", () => _track != null && _track.LaneMeshBuilt);
        GameProbe.Ready("laneCollider", () => _track != null && _track.LaneCollider != null
                                                             && _track.LaneCollider.enabled);
        GameProbe.Ready("hazardVolume", () => _track != null && _track.HazardVolumeReady);
        GameProbe.Ready("runner", () => runner != null && runner.gameObject.activeInHierarchy);
        GameProbe.Ready("pickups", () => _pickups != null && _pickups.Warm);

        GameProbe.Count("hazards", () => _track != null ? _track.ActiveHazardCount : 0);
        GameProbe.Count("pickups", () => _pickups != null ? _pickups.ActiveCount : 0);

        // custom{}: the handful of numbers a complaint will end up being about.
        GameProbe.Register("lane", () => _run.Lane);
        GameProbe.Register("gateDist", () => gate != null && runner != null
            ? Vector3.Distance(runner.position, gate.position) : -1f);
        GameProbe.Register("laneOffset", () => runner != null ? runner.position.x : 0f);
        GameProbe.Register("lodLevel", () => _track != null ? _track.CurrentLodLevel : -1);
    }

    // ----------------------------------------------------------------- situations

    void RegisterSituations()
    {
        // Three lanes, 1.3 units apart, middle lane is 1.
        Situations.Register(new Situation("approach-gate", EnterApproachGate, 15f)
            .Needs("laneMesh")
            .Needs("laneCollider")
            .Needs("gate", () => gate != null && gate.gameObject.activeInHierarchy)
            .Needs("sentry", () => _sentry != null && _sentry.Patrolling));

        Situations.Register(new Situation("runner-launch", EnterRunnerLaunch, 12f)
            .Needs("laneMesh")
            .Needs("laneCollider")
            .Needs("runner")
            .Needs("pickups"));

        Situations.Register(new Situation("hazard-lane", EnterHazardLane, 20f)
            .Needs("laneMesh")
            .Needs("laneCollider")
            .Needs("hazardVolume"));
    }

    /// <summary>Runner 12 units short of the gate, already moving, optional entry angle.</summary>
    void EnterApproachGate()
    {
        int lane = Situations.Param("lane", 1);
        float angle = Situations.Param("angle", 0f);
        float distance = Situations.Param("distance", 12f);

        _run.ResetRun(lane);                                    // replace with your game's method
        _run.PlaceAt(_track.PointBeforeGate(distance), angle);
        _run.Launch();
    }

    /// <summary>The first two seconds: at the start line, launched, nothing else touched.</summary>
    void EnterRunnerLaunch()
    {
        int lane = Situations.Param("lane", 1);
        _run.ResetRun(lane);
        _run.PlaceAt(_track.StartLine(lane), 0f);
        _run.Launch();
    }

    /// <summary>
    /// Mid-track in the middle lane. cold=true forces the streamer to drop and rebuild the
    /// section, which is the only way the late-lane complaint reproduces on demand.
    /// </summary>
    void EnterHazardLane()
    {
        bool cold = Situations.Param("cold", false);
        int lane = Situations.Param("lane", 1);
        float distance = Situations.Param("distance", 40f);

        if (cold) _track.DropStreamedSections();                // replace with your game's method
        _run.ResetRun(lane);
        _run.PlaceAt(_track.PointAlongTrack(distance), 0f);
        _run.Launch();
    }
}

// ---------------------------------------------------------------------------------------------
// The four shapes this template assumes. Delete this block and point the fields above at the
// real components; it is here so the file reads as a complete example rather than as a sketch.
// ---------------------------------------------------------------------------------------------

public enum RunPhase { Idle, Launched, Approach, AtGate, Crashed, Done }

public sealed class RunController : MonoBehaviour
{
    public RunPhase Phase { get; private set; }
    public int Lane { get; private set; }

    public void ResetRun(int lane) { Lane = lane; Phase = RunPhase.Idle; }
    public void ShiftLane(int delta) { Lane = Mathf.Clamp(Lane + delta, 0, 2); }
    public void PlaceAt(Vector3 point, float yawDegrees)
    {
        transform.SetPositionAndRotation(point, Quaternion.Euler(0f, yawDegrees, 0f));
    }
    public void Launch() { Phase = RunPhase.Launched; }
}

public sealed class TrackStreamer : MonoBehaviour
{
    public bool LaneMeshBuilt { get; private set; }
    public BoxCollider LaneCollider;
    public bool HazardVolumeReady { get; private set; }
    public int ActiveHazardCount { get; private set; }
    public int CurrentLodLevel { get; private set; }

    public Vector3 StartLine(int lane) => new Vector3((lane - 1) * 1.3f, 0f, 0f);
    public Vector3 PointAlongTrack(float distance) => new Vector3(0f, 0f, distance);
    public Vector3 PointBeforeGate(float distance) => new Vector3(0f, 0f, GateZ - distance);
    public float GateZ = 120f;

    public void DropStreamedSections()
    {
        LaneMeshBuilt = false;
        HazardVolumeReady = false;
    }
}

public sealed class SentryController : MonoBehaviour
{
    public bool Patrolling { get; private set; }
}

public sealed class PickupPool : MonoBehaviour
{
    public bool Warm { get; private set; }
    public int ActiveCount => _live.Count;
    readonly List<GameObject> _live = new List<GameObject>();
}
