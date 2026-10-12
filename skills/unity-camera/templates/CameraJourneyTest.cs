// CameraJourneyTest.cs — a play-mode journey over a 2D follow camera: the runner never
// leaves the viewport, the camera never leaves the room, and the camera-to-runner offset
// does not flip direction frame to frame.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner, Unity.Cinemachine and the Runtime assembly holding GameProbe.cs,
// Situations.cs, JourneyRecorder.cs (unity-play-harness → resources/) and CameraProbe.cs.
//
// REQUIRES com.unity.cinemachine 3.x (written against 3.1.7), com.unity.test-framework and
// the built-in 2D physics module. For 2.x names: reference/version-and-names.md.
//
// The test builds its own scene — a side-run room, a runner, a Brain and a follow camera —
// so it needs no scene asset. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter CameraJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
//   python3 scripts/camera_jitter.py <journeys>/camera-side-run/timeline.jsonl --axis x
//
// Prove the gate can fail before trusting a pass. Each of these must turn the test red:
//   CAMERA_JOURNEY_BREAK=confiner   no confiner: the view leaves the room at the far wall
//   CAMERA_JOURNEY_BREAK=clocks     Rigidbody2D interpolation off under a LateUpdate Brain
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using Unity.Cinemachine;
using UnityEngine;
using UnityEngine.TestTools;

public class CameraJourney
{
    const string JourneyId = "camera-side-run";
    const float RoomHalfWidth = 20f;
    const float RoomHalfHeight = 6f;
    const float OrthoSize = 5f;
    const float RunSpeed = 8f;
    const float TurnAt = 17f;          // inside the room, past where the confiner stops the camera
    const int Frames = 600;            // 10 s at the pinned frame time: out, back, out again
    const float MaxFlipRate = 0.1f;    // a damped follow measures about 0.01; two clocks about 0.3

    static string Break => Environment.GetEnvironmentVariable("CAMERA_JOURNEY_BREAK") ?? "";

    readonly List<GameObject> _made = new List<GameObject>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;
    SimulationMode2D _savedSimulationMode;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();
        Situations.ClearParams();
        // Only this journey's directory: other journeys in the same run keep their timelines.
        string dir = Path.Combine(JourneyRecorder.DefaultRoot(), JourneyId);
        if (Directory.Exists(dir)) Directory.Delete(dir, true);

        // Pin both clocks: 60 rendered frames against 50 physics steps a second, so one frame
        // in six has no step on every machine. That beat is the bug this journey looks for.
        // With the project's own values it could be absent — physics at 60 Hz, or stepped per
        // frame — and the broken run would then pass.
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        _savedSimulationMode = Physics2D.simulationMode;
        Time.captureDeltaTime = 1f / 60f;
        Time.fixedDeltaTime = 0.02f;
        Physics2D.simulationMode = SimulationMode2D.FixedUpdate;
    }

    [TearDown]
    public void TearDown()
    {
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        Time.fixedDeltaTime = _savedFixedDeltaTime;
        Physics2D.simulationMode = _savedSimulationMode;
        foreach (GameObject go in _made) if (go != null) UnityEngine.Object.Destroy(go);
        _made.Clear();
        GameProbe.Reset();
    }

    [UnityTest]
    public IEnumerator SideRun_CameraHoldsRunnerStaysInRoomAndDoesNotJitter()
    {
        bool withConfiner = Break != "confiner";
        bool interpolate = Break != "clocks";

        // ---- the room: a box the camera must stay inside. A trigger, so it is not a wall.
        var roomRect = new Rect(-RoomHalfWidth, -RoomHalfHeight, RoomHalfWidth * 2f, RoomHalfHeight * 2f);
        var room = Make("Room").AddComponent<BoxCollider2D>();
        room.isTrigger = true;
        room.size = roomRect.size;

        // ---- the runner: a body driven in FixedUpdate, the way a platformer runner is.
        GameObject runnerGo = Make("Runner");
        runnerGo.transform.position = new Vector3(-8f, 0f, 0f);
        var body = runnerGo.AddComponent<Rigidbody2D>();
        body.gravityScale = 0f;
        body.interpolation = interpolate ? RigidbodyInterpolation2D.Interpolate : RigidbodyInterpolation2D.None;
        var motor = runnerGo.AddComponent<SideRunMotor>();
        motor.speed = RunSpeed;
        motor.turnAt = TurnAt;
        motor.enabled = false;                       // starts when the camera is ready

        // ---- the output camera and its Brain.
        GameObject camGo = Make("Main Camera");
        camGo.tag = "MainCamera";                    // GameProbe reads Camera.main
        camGo.transform.position = new Vector3(-8f, 0f, -10f);
        var cam = camGo.AddComponent<Camera>();
        cam.orthographic = true;
        cam.orthographicSize = OrthoSize;
        var brain = camGo.AddComponent<CinemachineBrain>();
        // Pinned, so interpolation is the only variable between the passing and the broken run.
        brain.UpdateMethod = CinemachineBrain.UpdateMethods.LateUpdate;
        brain.BlendUpdateMethod = CinemachineBrain.BrainUpdateMethods.LateUpdate;

        // ---- the follow camera. Every value is assigned: Reset() does not run in play mode.
        GameObject vcamGo = Make("CM Follow 2D");
        vcamGo.transform.position = camGo.transform.position;
        var vcam = vcamGo.AddComponent<CinemachineCamera>();
        vcam.Target.TrackingTarget = runnerGo.transform;
        vcam.Priority = 10;
        LensSettings lens = vcam.Lens;
        lens.OrthographicSize = OrthoSize;
        vcam.Lens = lens;

        var composer = vcamGo.AddComponent<CinemachinePositionComposer>();
        composer.CameraDistance = 10f;
        composer.Damping = new Vector3(0.5f, 0.5f, 0f);
        composer.Composition = ScreenComposerSettings.Default;       // centred, no dead zone
        composer.Lookahead = new LookaheadSettings();                // off: one cause at a time

        CinemachineConfiner2D confiner = null;
        if (withConfiner)
        {
            confiner = vcamGo.AddComponent<CinemachineConfiner2D>();
            confiner.BoundingShape2D = room;
            confiner.Damping = 0f;
            confiner.SlowingDistance = 0f;
        }

        // ---- the probe.
        var probe = Make("CameraProbe").AddComponent<CameraProbe>();
        probe.player = runnerGo.transform;
        probe.outputCamera = cam;
        probe.SetBounds(p => roomRect.Contains(new Vector2(p.x, p.y)));

        // A 2D body: its own velocity, not the probe's position-delta fallback, which divides by
        // unscaled time and reads thousands of units a second once captureDeltaTime is pinned.
        GameProbe.SetPlayerVelocity(() => runnerGo.transform,
                                    () => body != null ? (Vector3)body.linearVelocity : Vector3.zero);
        GameProbe.SetState(() => motor.Phase);
        GameProbe.Ready("camera", () => Camera.main != null);
        GameProbe.Ready("brainLive", () => brain.ActiveVirtualCamera != null);
        if (confiner != null)
            GameProbe.Ready("confinerBaked", () => confiner.BoundingShapeIsBaked);

        // ---- wait on the set, on a clock the pinned frame time cannot stretch.
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 15f)
                Assert.Fail("camera rig not ready after 15 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
        for (int i = 0; i < 5; i++) yield return null;   // the first live frames centre the view

        using (var journey = new JourneyRecorder(JourneyId, JourneyRecorder.DefaultRoot()))
        {
            motor.enabled = true;
            for (int f = 0; f < Frames; f++)
            {
                journey.Sample();
                yield return null;                   // sample in Update; the probe latched in LateUpdate
            }
            journey.Milestone("end");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");

            // A runner that never ran makes every camera assertion pass on a still image.
            float minX = float.MaxValue, maxX = float.MinValue;
            foreach (ProbeSnapshot s in samples)
            {
                if (s.pos.x < minX) minX = s.pos.x;
                if (s.pos.x > maxX) maxX = s.pos.x;
            }
            Assert.Greater(maxX - minX, TurnAt, "the runner covered " + (maxX - minX).ToString("F1") +
                           " units — the drive did not run, so nothing below was tested");

            // 1 · the runner was on screen in every sample
            var offscreen = CameraAsserts.AlwaysTrue(samples, "camViewport");
            Assert.IsEmpty(offscreen, JourneyAsserts.Describe(offscreen));

            // 2 · the view never showed anything outside the room
            var outside = CameraAsserts.AlwaysTrue(samples, "camInBounds");
            Assert.IsEmpty(outside, JourneyAsserts.Describe(outside));

            // 3 · the offset eased; it did not beat
            float rate = CameraAsserts.FlipRate(samples, 0, out int flips, out int moving);
            TestContext.WriteLine("samples=" + samples.Count + " flips=" + flips + " moving=" + moving +
                                  " flipRate=" + rate.ToString("F3") + " timeline=" + journey.TimelinePath);
            Assert.LessOrEqual(rate, MaxFlipRate, "camOffset.x changed direction on " + flips + " of " +
                               moving + " moving frames — the camera and the runner are on different clocks");
        }
    }

    GameObject Make(string name)
    {
        var go = new GameObject(name);
        _made.Add(go);
        return go;
    }
}

/// <summary>
/// The side-run runner reduced to what a camera cares about: a body that runs along x at a
/// constant speed and turns round near each wall. It stands in for RunController so the
/// journey has no dependency on the game; in a real project the journey drives the game's
/// own runner through its input funnel and this class goes away.
/// </summary>
public sealed class SideRunMotor : MonoBehaviour
{
    public float speed = 8f;
    public float turnAt = 17f;

    public string Phase => _direction > 0f ? "Outbound" : "Return";

    Rigidbody2D _body;
    float _direction = 1f;

    void Awake() { _body = GetComponent<Rigidbody2D>(); }

    void FixedUpdate()
    {
        float x = _body.position.x;
        if (x > turnAt) _direction = -1f;
        else if (x < -turnAt) _direction = 1f;
        _body.linearVelocity = new Vector2(_direction * speed, 0f);
    }

    void OnDisable() { if (_body != null) _body.linearVelocity = Vector2.zero; }
}
