// GreyboxJourneyTest.cs — a play-mode journey over the gate-room greybox: a body-sized
// CharacterController walks the corridor, passes the door, climbs the step and the ramp and
// arrives on the ledge, without ever being inside a block. It is the check that the greybox
// holds its metrics before any art is made for it.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, Situations.cs,
// JourneyRecorder.cs (unity-play-harness → resources/), RunInput.cs and ScriptedRunInput.cs
// (unity-input → resources/).
//
// REQUIRES com.unity.test-framework and the built-in 3D physics module.
//
// The test builds its own blocks from primitives, at the numbers of reference/greybox.md, so it
// needs no scene asset, no prefab and no layer set-up: blocks sit on Default and the runner on
// the built-in Ignore Raycast layer. The walker below is the smallest body that can walk a
// greybox; replace it with the game's own controller once there is one, and keep the asserts.
// Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter GreyboxJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
// Timelines go to $JOURNEY_OUT, or to <persistentDataPath>/journeys without it.
//
// Prove the gate can fail before trusting a pass. Each of these must turn the walk red:
//   GREYBOX_JOURNEY_BREAK=door    the door is 0.7 wide: narrower than the 0.8 body
//   GREYBOX_JOURNEY_BREAK=step    the step is 1.0 high: a ledge, three times the step offset
//   GREYBOX_JOURNEY_BREAK=ramp    the ramp is 60 degrees: over the 45 degree slope limit
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>The smallest body that walks a greybox: planar input, a constant press into the
/// floor, one Move per frame. No jump, no acceleration, no camera.</summary>
[RequireComponent(typeof(CharacterController))]
public sealed class GreyboxWalker : MonoBehaviour
{
    public float runSpeed = 5f;
    public float gravity = 19.6f;

    public bool Grounded => _controller != null && _controller.isGrounded;
    public Vector3 Velocity => _controller != null ? _controller.velocity : Vector3.zero;

    CharacterController _controller;
    IRunInputSource _input;
    float _vertical;

    void Awake() => _controller = GetComponent<CharacterController>();

    void Update()
    {
        if (!RunInputSource.Resolve(gameObject, ref _input)) return;
        Vector2 move = _input.Peek().move;
        float dt = Time.deltaTime;
        // Not zero while grounded: isGrounded is only true on a frame where Move pressed down.
        _vertical = _controller.isGrounded ? -2f : _vertical - gravity * dt;
        _controller.Move((new Vector3(move.x, 0f, move.y) * runSpeed + Vector3.up * _vertical) * dt);
    }
}

public class GreyboxJourney
{
    const float Step = 0.02f;
    const int WorldLayer = 0;            // Default
    const int RunnerLayer = 2;           // Ignore Raycast: built in, so the test needs no layer asset

    // The body, and the sheet it is checked against.
    const float BodyHeight = 1.8f, BodyRadius = 0.4f, SkinWidth = 0.04f, StepOffset = 0.3f, SlopeLimit = 45f;
    const float RunSpeed = 5f;
    const float CorridorWidth = 2.4f, WallHeight = 3f, WallThickness = 0.2f, DoorHeight = 2.2f, LedgeRise = 1f;
    const float DoorZ = 6f, StepZ = 8f, RampZ = 10f, EndZ = 18f;

    static string Break => Environment.GetEnvironmentVariable("GREYBOX_JOURNEY_BREAK") ?? "";
    static float DoorWidth => Break == "door" ? 0.7f : 1.2f;
    static float StepHeight => Break == "step" ? 1f : 0.3f;
    static float RampAngle => Break == "ramp" ? 60f : 30f;
    static float RampRun => LedgeRise / Mathf.Tan(RampAngle * Mathf.Deg2Rad);

    readonly List<GameObject> _made = new List<GameObject>();
    float _savedCaptureDeltaTime;

    GameObject _runner;
    GreyboxWalker _walker;
    ScriptedRunInput _input;
    GameObject _floor;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        Time.captureDeltaTime = Step;        // every frame is 0.02 s, whatever the machine does

        // ---- the greybox: the runner starts in the corridor and walks +Z.
        _floor = Block("Floor", new Vector3(0f, -0.1f, 10f), new Vector3(12f, 0.2f, 24f));
        float wallX = (CorridorWidth + WallThickness) * 0.5f;
        Block("Wall_Corridor_L", new Vector3(-wallX, WallHeight * 0.5f, DoorZ * 0.5f), new Vector3(WallThickness, WallHeight, DoorZ));
        Block("Wall_Corridor_R", new Vector3(wallX, WallHeight * 0.5f, DoorZ * 0.5f), new Vector3(WallThickness, WallHeight, DoorZ));

        float side = (12f - DoorWidth) * 0.5f, doorWallZ = DoorZ + WallThickness * 0.5f;
        float sideX = DoorWidth * 0.5f + side * 0.5f;
        Block("Wall_Door_L", new Vector3(-sideX, WallHeight * 0.5f, doorWallZ), new Vector3(side, WallHeight, WallThickness));
        Block("Wall_Door_R", new Vector3(sideX, WallHeight * 0.5f, doorWallZ), new Vector3(side, WallHeight, WallThickness));
        Block("Lintel_Door", new Vector3(0f, (DoorHeight + WallHeight) * 0.5f, doorWallZ),
              new Vector3(DoorWidth, WallHeight - DoorHeight, WallThickness));

        // The step runs the full width, so there is no way round it.
        Block("Step", new Vector3(0f, StepHeight * 0.5f, (StepZ + EndZ) * 0.5f), new Vector3(12f, StepHeight, EndZ - StepZ));

        // The ramp is a slab whose top face is the slope; both ends sink into their neighbours.
        const float slab = 0.2f;
        Quaternion tilt = Quaternion.Euler(-RampAngle, 0f, 0f);
        var top = new Vector3(0f, StepHeight + LedgeRise * 0.5f, RampZ + RampRun * 0.5f);
        GameObject ramp = Block("Ramp", top - tilt * Vector3.up * (slab * 0.5f),
                                new Vector3(3f, slab, Mathf.Sqrt(LedgeRise * LedgeRise + RampRun * RampRun)));
        ramp.transform.rotation = tilt;

        float ledgeFrom = RampZ + RampRun;
        Block("Ledge", new Vector3(0f, StepHeight + LedgeRise * 0.5f, (ledgeFrom + EndZ) * 0.5f),
              new Vector3(3f, LedgeRise, EndZ - ledgeFrom));

        // ---- the runner: a CharacterController of the body's size, pivot at its centre.
        _runner = new GameObject("Runner");
        _made.Add(_runner);
        _runner.layer = RunnerLayer;
        _runner.transform.position = new Vector3(0f, BodyHeight * 0.5f + SkinWidth + 0.01f, 1f);
        var controller = _runner.AddComponent<CharacterController>();
        controller.height = BodyHeight;
        controller.radius = BodyRadius;
        controller.skinWidth = SkinWidth;
        controller.stepOffset = StepOffset;
        controller.slopeLimit = SlopeLimit;
        controller.minMoveDistance = 0f;      // the default 0.001 swallows a slow frame's move
        _input = _runner.AddComponent<ScriptedRunInput>();
        _walker = _runner.AddComponent<GreyboxWalker>();
        _walker.runSpeed = RunSpeed;
        Physics.SyncTransforms();

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => _walker.Velocity);
        GameProbe.Register("grounded", () => _walker.Grounded);
        GameProbe.SetState(() => Where(_runner.transform.position.z));
        GameProbe.Ready("greybox", () => _floor != null);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);
    }

    [TearDown]
    public void TearDown()
    {
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        foreach (GameObject go in _made) if (go != null) UnityEngine.Object.Destroy(go);
        _made.Clear();
        GameProbe.Reset();
    }

    [UnityTest]
    public IEnumerator Walk_PassesTheDoor_ClimbsTheStepAndTheRamp_AndArrives()
    {
        yield return Settle();
        float arriveZ = RampZ + RampRun + 1.5f;
        float ledgeY = StepHeight + LedgeRise + BodyHeight * 0.5f + SkinWidth;

        using (var journey = Open("gate-room-walk"))
        {
            _input.SetMove(Vector2.up);                       // the stick forward: +Z
            float until = Time.time + 8f;                     // 3 s at a run, with room to spare
            while (Time.time < until && _runner.transform.position.z < arriveZ)
            {
                journey.Sample();
                yield return null;
            }
            _input.SetMove(Vector2.zero);
            journey.Milestone("arrival");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");
            Vector3 at = _runner.transform.position;
            TestContext.WriteLine("at=" + at.ToString("F2") + " stopped=" + Where(at.z) +
                                  " samples=" + samples.Count + " timeline=" + journey.TimelinePath);

            Assert.GreaterOrEqual(at.z, arriveZ, "the runner stopped at " + Where(at.z) + " (z " + at.z.ToString("F2") +
                                  "): door " + DoorWidth + ", step " + StepHeight + ", ramp " + RampAngle + " degrees");
            Assert.AreEqual(ledgeY, at.y, 0.1f, "the runner arrived, and not on top of the ledge");

            // Well under the body's radius: a runner brushing a jamb touches it, and is not in it.
            var inside = JourneyAsserts.NeverInside(samples, 1 << WorldLayer, BodyRadius * 0.75f);
            Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));

            // Planar speed only: a step-up is 0.3 units of height in one frame by design.
            var fast = JourneyAsserts.Never(samples,
                s => new Vector2(s.vel.x, s.vel.z).magnitude > RunSpeed * 1.02f, "overspeed");
            Assert.IsEmpty(fast, JourneyAsserts.Describe(fast));

            // A walk never leaves the ground for long: a lip at the foot of the ramp launches it.
            int airborne = 0, longest = 0;
            foreach (ProbeSnapshot s in samples)
            {
                bool grounded = s.custom.TryGetValue("grounded", out object g) && g is bool b && b;
                airborne = grounded ? 0 : airborne + 1;
                if (airborne > longest) longest = airborne;
            }
            Assert.LessOrEqual(longest, 5, "the runner was off the ground for " + longest +
                               " samples in a row on a walk with no drop in it");
        }
    }

    [UnityTest]
    public IEnumerator Door_AdmitsOneAndAHalfBodyWidths()
    {
        yield return Settle();
        // Measured between colliders, not between pivots: a capsule 1.5 bodies wide stood in
        // the doorway overlaps nothing. 1.5 x 0.8 = 1.2, less a hair so that touching passes.
        float radius = BodyRadius * 1.5f - 0.01f;
        var foot = new Vector3(0f, radius + 0.05f, DoorZ + WallThickness * 0.5f);
        var head = new Vector3(0f, Mathf.Max(foot.y, BodyHeight - radius), foot.z);
        bool blocked = Physics.CheckCapsule(foot, head, radius, 1 << WorldLayer, QueryTriggerInteraction.Ignore);
        Assert.IsFalse(blocked, "a door " + DoorWidth + " wide does not admit 1.5 body widths (" +
                       (BodyRadius * 3f) + ")");
    }

    // ------------------------------------------------------------------------------- helpers

    static string Where(float z)
    {
        if (z < DoorZ + 1f) return "the door";
        if (z < StepZ + 0.5f) return "the step";
        if (z < RampZ + RampRun) return "the ramp";
        return "the ledge";
    }

    IEnumerator Settle()
    {
        yield return null;                                   // Awake and OnEnable have run
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 10f)
                Assert.Fail("greybox not ready after 10 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
        for (int i = 0; i < 10; i++) yield return null;      // the runner drops its 0.01 and lands
    }

    static JourneyRecorder Open(string id)
    {
        // Only this journey's directory: the other journeys of the run keep their timelines.
        string dir = Path.Combine(JourneyRecorder.DefaultRoot(), id);
        if (Directory.Exists(dir)) Directory.Delete(dir, true);
        return new JourneyRecorder(id, JourneyRecorder.DefaultRoot());
    }

    GameObject Block(string name, Vector3 centre, Vector3 size)
    {
        GameObject go = GameObject.CreatePrimitive(PrimitiveType.Cube);
        _made.Add(go);
        go.name = name;
        go.layer = WorldLayer;
        go.transform.position = centre;
        go.transform.localScale = size;
        return go;
    }
}
