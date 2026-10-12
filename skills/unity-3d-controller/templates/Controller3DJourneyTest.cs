// Controller3DJourneyTest.cs — play-mode journeys over the gate room and the lane run: the runner
// walks up a 30-degree ramp grounded and stays put on it, climbs a 0.3-unit step and is stopped by
// a 0.6-unit one, jumps to the apex the numbers say, moves where the camera points; the
// first-person body yaws while only the head pitches, and the pitch clamps; a lane change lands
// on the lane centre in the configured time.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, JourneyRecorder.cs,
// Situations.cs (unity-play-harness → resources/), RunInput.cs, ScriptedRunInput.cs
// (unity-input → resources/) and this skill's resources/: CharacterMotor3D.cs,
// MovingPlatform3D.cs, ThirdPersonController.cs, FirstPersonController.cs and
// LaneRunnerController.cs.
//
// REQUIRES com.unity.test-framework and the built-in physics module.
//
// The test builds its own room from box colliders — a floor, a ramp, two steps — so it needs no
// scene asset, no prefab and no layer set-up: the room sits on Default and the runner on the
// built-in Ignore Raycast layer. The runner's transform is at the centre of its capsule
// (CharacterController.center is zero), because JourneyAsserts.NeverInside tests a sphere at the
// probe's position and a pivot at the feet touches the floor on every frame. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter Controller3DJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
// then measure the jump the game performed (jump_report.py ships with skill unity-gameplay;
// timelines go to $JOURNEY_OUT, or to <persistentDataPath>/journeys without it):
//   python3 scripts/jump_report.py "$JOURNEY_OUT/gate-room-jump/timeline.jsonl" \
//     --grounded-key grounded --apex 1.2
//
// Prove the gate can fail before trusting a pass. Each of these must turn one test red:
//   CONTROLLER3D_JOURNEY_BREAK=slope      slope limit 10: the ramp is a wall
//   CONTROLLER3D_JOURNEY_BREAK=step       step offset 0: the 0.3 step is a wall
//   CONTROLLER3D_JOURNEY_BREAK=tallstep   step offset 0.7: the 0.6 step is a stair
//   CONTROLLER3D_JOURNEY_BREAK=tap        the jump is tapped, not held: the cut lowers the apex
//   CONTROLLER3D_JOURNEY_BREAK=pitch      pitch limit 170: the head goes over the top
//   CONTROLLER3D_JOURNEY_BREAK=lane       lane change 0.45 s: three times the configured time
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

public class Controller3DJourney
{
    const float Step = 0.02f;
    const int WorldLayer = 0;            // Default
    const int RunnerLayer = 2;           // Ignore Raycast: built in, so the test needs no layer asset

    // The body the gate room is built for.
    const float Height = 1.8f;
    const float Radius = 0.4f;
    const float Skin = 0.04f;
    const float HalfHeight = Height * 0.5f;
    const float Rest = HalfHeight + 0.1f;                // where a placed runner starts, above the floor

    // The numbers under test. The controllers are set from these and the assertions compare
    // against these, so a break that changes a controller cannot move the expectation with it.
    const float RunSpeed = 5f;
    const float ApexHeight = 1.2f;
    const float TimeToApex = 0.35f;
    const float SlopeLimit = 45f;
    const float StepOffset = 0.3f;
    const float MaxPitch = 85f;
    const float LaneWidth = 1.3f;
    const float LaneChange = 0.15f;
    const float ForwardSpeed = 12f;

    // The room. Stick up is +Z; each obstacle has its own strip of floor.
    const float RampX = -8f, RampLowZ = 2f, RampAngle = 30f, RampLength = 8f;
    const float LowStepX = 0f, LowStepHeight = 0.3f;
    const float TallStepX = 8f, TallStepHeight = 0.6f;
    const float StepFaceZ = 3.5f;
    const float LaneStartX = 40f;                        // the lane run, clear of the room

    static string Break => Environment.GetEnvironmentVariable("CONTROLLER3D_JOURNEY_BREAK") ?? "";

    readonly List<GameObject> _made = new List<GameObject>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;
    SimulationMode _savedSimulationMode;

    GameObject _runner;
    Transform _view;
    CharacterController _capsule;
    CharacterMotor3D _motor;
    ScriptedRunInput _input;
    BoxCollider _floor;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();

        // One rendered frame per physics step, at a fixed length: every run of the journey
        // integrates the same steps, whatever the machine.
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        _savedSimulationMode = Physics.simulationMode;
        Time.captureDeltaTime = Step;
        Time.fixedDeltaTime = Step;
        Physics.simulationMode = SimulationMode.FixedUpdate;

        // ---- the room -----------------------------------------------------------------------
        _floor = Box("Floor", new Vector3(0f, -0.5f, 10f), new Vector3(40f, 1f, 60f), Quaternion.identity);

        // A ramp whose top face starts on the floor at RampLowZ and rises towards +Z.
        Quaternion tilt = Quaternion.Euler(-RampAngle, 0f, 0f);
        Vector3 topCentre = new Vector3(RampX, 0f, RampLowZ) + tilt * Vector3.forward * (RampLength * 0.5f);
        Box("Ramp", topCentre - tilt * Vector3.up * 0.5f, new Vector3(3f, 1f, RampLength), tilt);

        Box("LowStep", new Vector3(LowStepX, LowStepHeight * 0.5f, StepFaceZ + 3f),
            new Vector3(3f, LowStepHeight, 6f), Quaternion.identity);
        Box("TallStep", new Vector3(TallStepX, TallStepHeight * 0.5f, StepFaceZ + 3f),
            new Vector3(3f, TallStepHeight, 6f), Quaternion.identity);

        _view = Make("View").transform;
        _view.position = new Vector3(0f, 3f, -10f);
    }

    [TearDown]
    public void TearDown()
    {
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        Time.fixedDeltaTime = _savedFixedDeltaTime;
        Physics.simulationMode = _savedSimulationMode;
        foreach (GameObject go in _made) if (go != null) UnityEngine.Object.Destroy(go);
        _made.Clear();
        GameProbe.Reset();
    }

    // ---------------------------------------------------------------------------- third person

    [UnityTest]
    public IEnumerator ThirdPerson_Jump_ReachesTheConfiguredApex()
    {
        ThirdPersonController run = BuildThirdPerson();
        yield return Place(new Vector3(0f, Rest, -6f));

        using (var journey = Open("gate-room-jump"))
        {
            yield return SampleFor(journey, 0.1f);
            float groundY = _runner.transform.position.y;

            // Held, because the controller shortens a jump whose button is up on the way up.
            if (Break == "tap") _input.Tap(RunButton.Launch); else _input.Hold(RunButton.Launch);
            float pressedAt = Time.time;
            journey.Milestone("pressed");
            yield return SampleFor(journey, 0.1f);
            Assert.IsFalse(run.Grounded, "0.1 s after the press the runner is still on the floor — the press never reached the controller");
            yield return SampleUntil(journey, () => run.Grounded, 2f, "the runner to land");
            _input.Release(RunButton.Launch);
            journey.Milestone("landed");
            yield return SampleFor(journey, 0.1f);

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.AreEqual(1, run.Jumps, "one press, so one jump");

            float top = float.MinValue, topAt = 0f;
            foreach (ProbeSnapshot s in samples)
                if (s.pos.y > top) { top = s.pos.y; topAt = s.t; }
            float apex = top - groundY;

            // The controller moves by the mean of the velocity before and after each frame, which
            // is exact under constant gravity: the designed apex is the simulated one.
            TestContext.WriteLine("apex=" + apex.ToString("F3") + " designed=" + ApexHeight.ToString("F3") +
                                  " timeToApex=" + (topAt - pressedAt).ToString("F3") + " gravity=" +
                                  run.Gravity.ToString("F2") + " jumpVelocity=" + run.JumpVelocity.ToString("F2") +
                                  " timeline=" + journey.TimelinePath);
            Assert.AreEqual(ApexHeight, apex, 0.05f, "the jump peaked at " + apex.ToString("F3") +
                            " units, designed " + ApexHeight.ToString("F3"));
            Assert.AreEqual(TimeToApex, topAt - pressedAt, 0.05f, "the apex came " +
                            (topAt - pressedAt).ToString("F3") + " s after the press, designed " + TimeToApex.ToString("F2"));

            AssertNeverInside(samples);
        }
    }

    [UnityTest]
    public IEnumerator ThirdPerson_Ramp_IsClimbedGroundedAndHeld()
    {
        BuildThirdPerson();
        yield return Place(new Vector3(RampX, Rest, RampLowZ - 2f));

        using (var journey = Open("gate-room-ramp"))
        {
            _input.SetMove(Vector2.up);
            yield return SampleUntil(journey, () => _runner.transform.position.z > RampLowZ + 1f, 3f,
                                     "the runner to get one unit up the ramp");
            journey.Milestone("on-ramp");

            int airborne = 0, frames = 0;
            float worstGap = 0f;
            float until = Time.time + 0.8f;
            while (Time.time < until)
            {
                journey.Sample();
                frames++;
                if (!_motor.Grounded) airborne++;
                worstGap = Mathf.Max(worstGap, Mathf.Abs(FeetAboveRamp()));
                yield return null;
            }
            _input.SetMove(Vector2.zero);
            yield return SampleFor(journey, 0.3f);              // the stop

            Vector3 heldAt = _runner.transform.position;
            float climbed = heldAt.y - HalfHeight;
            journey.Milestone("held");
            yield return SampleFor(journey, 0.5f);
            float slid = Vector3.Distance(heldAt, _runner.transform.position);

            TestContext.WriteLine("frames=" + frames + " airborne=" + airborne + " worstGap=" + worstGap.ToString("F3") +
                                  " climbed=" + climbed.ToString("F3") + " slid=" + slid.ToString("F4") +
                                  " timeline=" + journey.TimelinePath);
            Assert.AreEqual(0, airborne, airborne + " of " + frames + " frames on a " + RampAngle +
                            "-degree ramp were not grounded");
            Assert.Less(worstGap, 0.15f, "the feet left the ramp's surface by " + worstGap.ToString("F3") + " units");
            Assert.Greater(climbed, 2f, "0.8 s of running up the ramp gained " + climbed.ToString("F2") + " units of height");
            Assert.IsTrue(_motor.Grounded, "the runner is not grounded standing on the ramp");
            Assert.Less(slid, 0.02f, "standing on the ramp with the stick at rest, the runner slid " +
                        slid.ToString("F3") + " units in 0.5 s");

            AssertNeverInside(journey.Captured);
        }
    }

    [UnityTest]
    public IEnumerator ThirdPerson_LowStep_IsClimbed()
    {
        BuildThirdPerson();
        yield return Place(new Vector3(LowStepX, Rest, 0f));

        using (var journey = Open("gate-room-step"))
        {
            _input.SetMove(Vector2.up);
            yield return SampleFor(journey, 1.2f);
            _input.SetMove(Vector2.zero);
            yield return SampleFor(journey, 0.3f);

            Vector3 p = _runner.transform.position;
            float feet = p.y - HalfHeight;
            TestContext.WriteLine("z=" + p.z.ToString("F3") + " feet=" + feet.ToString("F3") + " timeline=" + journey.TimelinePath);
            Assert.Greater(p.z, StepFaceZ + 0.7f, "the runner stopped at z " + p.z.ToString("F2") + ", in front of a " +
                           LowStepHeight + "-unit step — step offset is " + _capsule.stepOffset.ToString("F2"));
            Assert.AreEqual(LowStepHeight + Skin, feet, 0.1f, "the feet are at " + feet.ToString("F3") +
                            " on a step " + LowStepHeight + " high");
            Assert.IsTrue(_motor.Grounded, "the runner is not grounded on top of the step");

            AssertNeverInside(journey.Captured);
        }
    }

    [UnityTest]
    public IEnumerator ThirdPerson_TallStep_IsRefused()
    {
        BuildThirdPerson();
        yield return Place(new Vector3(TallStepX, Rest, 0f));

        using (var journey = Open("gate-room-wall"))
        {
            _input.SetMove(Vector2.up);
            yield return SampleFor(journey, 1.2f);
            _input.SetMove(Vector2.zero);
            yield return SampleFor(journey, 0.2f);

            Vector3 p = _runner.transform.position;
            float feet = p.y - HalfHeight;
            TestContext.WriteLine("z=" + p.z.ToString("F3") + " feet=" + feet.ToString("F3") + " timeline=" + journey.TimelinePath);
            Assert.Greater(p.z, StepFaceZ - Radius - 0.3f, "the runner never reached the step: z " + p.z.ToString("F2"));
            Assert.Less(p.z, StepFaceZ - Radius + 0.1f, "the runner walked onto a " + TallStepHeight +
                        "-unit step with a step offset of " + _motor.stepOffset.ToString("F2"));
            Assert.Less(feet, 0.15f, "the feet rose to " + feet.ToString("F3") + " against a step that is a wall");

            AssertNeverInside(journey.Captured);
        }
    }

    [UnityTest]
    public IEnumerator ThirdPerson_Stick_IsRelativeToTheView()
    {
        BuildThirdPerson();
        // The camera looks along +X and down 30 degrees: stick up must mean +X, on the ground.
        _view.rotation = Quaternion.Euler(30f, 90f, 0f);
        yield return Place(new Vector3(0f, Rest, -6f));

        using (var journey = Open("gate-room-view"))
        {
            Vector3 from = _runner.transform.position;
            _input.SetMove(Vector2.up);
            yield return SampleFor(journey, 0.6f);
            _input.SetMove(Vector2.zero);
            Vector3 moved = _runner.transform.position - from;

            Assert.Greater(moved.x, 2f, "stick up with the view facing +X moved the runner " + moved.ToString("F2"));
            Assert.Less(Mathf.Abs(moved.z), 0.1f, "the runner drifted " + moved.z.ToString("F2") + " along Z");
            Assert.Less(Vector3.Angle(_runner.transform.forward, Vector3.right), 5f,
                        "the runner faces " + _runner.transform.forward.ToString("F2") + ", not where it runs");

            AssertNeverInside(journey.Captured);
        }
    }

    // ---------------------------------------------------------------------------- first person

    [UnityTest]
    public IEnumerator FirstPerson_YawTurnsTheBody_PitchClampsOnTheHead()
    {
        FirstPersonController fp = BuildFirstPerson(out Transform head);
        yield return Place(new Vector3(0f, Rest, -6f));
        fp.SetLook(0f, 0f);

        using (var journey = Open("gate-room-look"))
        {
            // A pointer: 900 counts at 0.1 degrees per count is a quarter turn, in one frame,
            // whatever the frame's length.
            fp.AddLookDelta(new Vector2(900f, 0f));
            yield return SampleFor(journey, 0.04f);
            Assert.AreEqual(90f, Mathf.DeltaAngle(0f, fp.Yaw), 0.05f, "900 counts turned the body " + fp.Yaw.ToString("F2") + " degrees");
            Assert.AreEqual(0f, fp.Pitch, 0.001f, "a sideways look pitched the head");
            Assert.Less(Vector3.Angle(head.forward, Vector3.right), 0.1f, "the head does not look where the body faces");

            // A stick held up for 1.5 s asks for 180 degrees; the head stops at the limit.
            _input.SetAim(Vector2.up);
            yield return SampleFor(journey, 1.5f);
            TestContext.WriteLine("pitch=" + fp.Pitch.ToString("F2") + " yaw=" + fp.Yaw.ToString("F2") +
                                  " headLocalX=" + head.localEulerAngles.x.ToString("F2"));
            Assert.AreEqual(MaxPitch, fp.Pitch, 0.01f, "held up, the pitch is " + fp.Pitch.ToString("F2") + ", limit " + MaxPitch);
            Assert.AreEqual(-MaxPitch, Mathf.DeltaAngle(0f, head.localEulerAngles.x), 0.05f, "the head's local pitch is not the controller's");
            Assert.Less(Vector3.Angle(_runner.transform.up, Vector3.up), 0.01f, "the body pitched: only the head may");
            Assert.AreEqual(90f, Mathf.DeltaAngle(0f, fp.Yaw), 0.05f, "a vertical look turned the body");

            _input.SetAim(Vector2.down);
            yield return SampleFor(journey, 2f);
            Assert.AreEqual(-MaxPitch, fp.Pitch, 0.01f, "held down, the pitch is " + fp.Pitch.ToString("F2"));

            // The stick moves relative to the body, not the head: looking at the floor, forward
            // is still along the ground.
            _input.SetAim(Vector2.zero);
            Vector3 from = _runner.transform.position;
            _input.SetMove(Vector2.up);
            yield return SampleFor(journey, 0.5f);
            _input.SetMove(Vector2.zero);
            Vector3 moved = _runner.transform.position - from;
            Assert.Greater(moved.x, 1.5f, "stick up with the body facing +X moved the runner " + moved.ToString("F2"));
            Assert.Less(Mathf.Abs(moved.z), 0.05f, "the runner drifted " + moved.z.ToString("F2") + " along Z");

            AssertNeverInside(journey.Captured);
        }
    }

    // ------------------------------------------------------------------------------ lane runner

    [UnityTest]
    public IEnumerator LaneRunner_Change_LandsOnTheLaneInTheConfiguredTime()
    {
        LaneRunnerController lane = BuildLaneRunner();
        yield return null;
        yield return WaitUntilReady();
        lane.Running = true;

        using (var journey = Open("lane-run-change"))
        {
            yield return SampleFor(journey, 0.1f);
            Assert.AreEqual(1, lane.Lane, "the run does not start in the middle lane");

            // ---- one change to the right --------------------------------------------------
            _input.SetMove(Vector2.right);
            yield return new WaitForFixedUpdate();
            Assert.IsTrue(lane.Changing, "a full push to the right did not start a lane change");
            Assert.AreEqual(2, lane.Lane, "the lane index changes when the change starts");
            float startedAt = Time.fixedTime;
            _input.SetMove(Vector2.zero);
            journey.Milestone("change-started");
            yield return SampleUntil(journey, () => !lane.Changing, 1f, "the lane change to end");
            // The step that started the change already moved the runner, so it counts.
            float took = Time.fixedTime - startedAt + Step;
            yield return SampleFor(journey, 0.06f);

            float x = _runner.transform.position.x - LaneStartX;
            TestContext.WriteLine("took=" + took.ToString("F3") + " x=" + x.ToString("F4") + " speed=" +
                                  lane.Speed.ToString("F2") + " timeline=" + journey.TimelinePath);
            Assert.AreEqual(LaneWidth, x, 0.01f, "the change ended " + x.ToString("F3") + " units from the middle lane, not on " + LaneWidth);
            Assert.GreaterOrEqual(took, LaneChange - 0.001f, "the change took " + took.ToString("F3") + " s, configured " + LaneChange);
            Assert.LessOrEqual(took, LaneChange + 2f * Step + 0.005f, "the change took " + took.ToString("F3") + " s, configured " + LaneChange);

            var overshoot = JourneyAsserts.Never(journey.Captured,
                s => s.hasPlayer && Mathf.Abs(s.pos.x - LaneStartX) > LaneWidth + 0.005f, "lane-overshoot");
            Assert.IsEmpty(overshoot, JourneyAsserts.Describe(overshoot));

            // ---- two to the left, the second asked for while the first is running -----------
            _input.SetMove(Vector2.left);
            yield return new WaitForFixedUpdate();
            Assert.AreEqual(1, lane.Lane);
            _input.SetMove(Vector2.zero);
            yield return new WaitForFixedUpdate();              // the level is seen at rest: the next push is an edge
            _input.SetMove(Vector2.left);
            yield return new WaitForFixedUpdate();
            _input.SetMove(Vector2.zero);
            Assert.AreEqual(1, lane.Lane, "the second change started before the first ended");
            yield return SampleUntil(journey, () => !lane.Changing && lane.Lane == 0, 1f, "the remembered change to finish");
            yield return SampleFor(journey, 0.06f);
            x = _runner.transform.position.x - LaneStartX;
            Assert.AreEqual(-LaneWidth, x, 0.01f, "two changes left ended at " + x.ToString("F3"));
            Assert.AreEqual(3, lane.LaneChanges, "three changes were asked for and " + lane.LaneChanges + " ran");

            // ---- a third is refused at the outer lane -----------------------------------------
            _input.SetMove(Vector2.left);
            yield return new WaitForFixedUpdate();
            _input.SetMove(Vector2.zero);
            yield return SampleFor(journey, 0.2f);
            Assert.AreEqual(0, lane.Lane, "the runner left the track");
            Assert.AreEqual(1, lane.Refused, "a change past the outer lane was not counted as refused");
            Assert.AreEqual(-LaneWidth, _runner.transform.position.x - LaneStartX, 0.01f);

            Assert.AreEqual(ForwardSpeed, lane.Speed, 0.01f, "forward speed with no ramp");
            Assert.AreEqual(ForwardSpeed, lane.Velocity.z, 0.05f, "the body's forward velocity");
            Assert.Greater(lane.Distance, ForwardSpeed * 0.5f, "the runner did not advance");
        }
    }

    // ----------------------------------------------------------------------------------- rigs

    // Body, input and motor: what every on-foot rig shares. Capsule first — the motor reads it in Awake.
    void BuildBody()
    {
        _runner = Make("Runner");
        _runner.layer = RunnerLayer;
        // Above the floor before the capsule exists: a capsule created at the origin starts inside it.
        _runner.transform.position = new Vector3(0f, Rest, -6f);
        _capsule = _runner.AddComponent<CharacterController>();
        _capsule.height = Height;
        _capsule.radius = Radius;
        _capsule.center = Vector3.zero;
        _capsule.skinWidth = Skin;
        _capsule.slopeLimit = Break == "slope" ? 10f : SlopeLimit;
        _input = _runner.AddComponent<ScriptedRunInput>();
        _input.bufferSeconds = 0.12f;
        _motor = _runner.AddComponent<CharacterMotor3D>();
        _motor.ground = 1 << WorldLayer;
        _motor.stepOffset = Break == "step" ? 0f : Break == "tallstep" ? 0.7f : StepOffset;
        _motor.groundTolerance = 0.05f;
        _motor.snapDistance = 0.3f;

        GameProbe.Register("grounded", () => _motor.Grounded);      // jump_report.py cuts arcs on this
        GameProbe.Register("groundAngle", () => _motor.GroundAngle);
        GameProbe.Count("presses", () => _input.Sent(RunButton.Launch));
        GameProbe.Ready("floorCollider", () => _floor != null && _floor.enabled);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);
    }

    ThirdPersonController BuildThirdPerson()
    {
        BuildBody();
        var run = _runner.AddComponent<ThirdPersonController>();
        // Every value the assertions depend on is assigned here, so a changed default in the
        // component cannot move the expected numbers.
        run.view = _view;
        run.runSpeed = RunSpeed;
        run.speedScale = 1f;
        run.groundAccel = 33f;
        run.groundDecel = 50f;
        run.facing = FacingMode3D.Movement;
        run.turnRate = 720f;
        run.apexHeight = ApexHeight;
        run.timeToApex = TimeToApex;
        run.fallMultiplier = 1.5f;
        run.maxFallSpeed = 20f;
        run.coyoteTime = 0.1f;
        run.variableJump = true;
        run.jumpCutMultiplier = 0.5f;

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => run.Velocity);
        GameProbe.SetState(() => run.State);
        GameProbe.Count("jumps", () => run.Jumps);
        return run;
    }

    FirstPersonController BuildFirstPerson(out Transform head)
    {
        BuildBody();
        head = Make("Head").transform;
        head.SetParent(_runner.transform, false);
        var fp = _runner.AddComponent<FirstPersonController>();
        fp.head = head;
        fp.eyeHeight = 1.6f;
        fp.maxPitch = Break == "pitch" ? 170f : MaxPitch;
        fp.degreesPerCount = 0.1f;
        fp.stickYawSpeed = 180f;
        fp.stickPitchSpeed = 120f;
        fp.invertY = false;
        fp.lookFromAim = true;
        fp.runSpeed = RunSpeed;
        fp.speedScale = 1f;
        fp.apexHeight = ApexHeight;
        fp.timeToApex = TimeToApex;

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => fp.Velocity);
        GameProbe.SetState(() => fp.State);
        GameProbe.Register("pitch", () => fp.Pitch);
        GameProbe.Register("yaw", () => fp.Yaw);
        return fp;
    }

    LaneRunnerController BuildLaneRunner()
    {
        _runner = Make("LaneRunner");
        _runner.layer = RunnerLayer;
        _runner.transform.position = new Vector3(LaneStartX, HalfHeight, 0f);
        var body = _runner.AddComponent<CapsuleCollider>();
        body.height = Height;
        body.radius = Radius;
        _input = _runner.AddComponent<ScriptedRunInput>();
        var lane = _runner.AddComponent<LaneRunnerController>();
        lane.Running = false;
        lane.lanes = 3;
        lane.laneWidth = LaneWidth;
        lane.laneChangeTime = Break == "lane" ? 0.45f : LaneChange;
        lane.easeLaneChange = true;
        lane.laneThreshold = 0.5f;
        lane.forwardSpeed = ForwardSpeed;
        lane.maxForwardSpeed = 20f;
        lane.speedRamp = 0f;
        lane.ResetRun(1);
        // Samples read the simulated pose, not a pose drawn between two steps.
        _runner.GetComponent<Rigidbody>().interpolation = RigidbodyInterpolation.None;

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => lane.Velocity);
        GameProbe.SetState(() => lane.State);
        GameProbe.Register("lane", () => lane.Lane);
        GameProbe.Register("laneOffset", () => lane.LaneOffset);
        GameProbe.Count("laneChanges", () => lane.LaneChanges);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);
        return lane;
    }

    // ------------------------------------------------------------------------------- helpers

    // Height of the feet above the ramp's top face, straight up. Zero is on it; the skin is 0.04.
    float FeetAboveRamp()
    {
        Vector3 p = _runner.transform.position;
        float surface = (p.z - RampLowZ) * Mathf.Tan(RampAngle * Mathf.Deg2Rad);
        // The lowest point of a capsule on a slope is not the point that touches it.
        float touch = Radius / Mathf.Cos(RampAngle * Mathf.Deg2Rad) - Radius;
        return p.y - HalfHeight - surface - touch - Skin;
    }

    IEnumerator Place(Vector3 position)
    {
        yield return null;                                   // Awake and OnEnable have run
        _motor.Teleport(position);
        yield return WaitUntilReady();
        float until = Time.time + 2f;
        while (!_motor.Grounded)
        {
            if (Time.time > until) Assert.Fail("the runner did not land on the floor within 2 s of being placed");
            yield return null;
        }
    }

    static IEnumerator WaitUntilReady()
    {
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 10f)
                Assert.Fail("gate room not ready after 10 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
    }

    static JourneyRecorder Open(string id)
    {
        // Only this journey's directory: the other journeys of the run keep their timelines.
        string dir = Path.Combine(JourneyRecorder.DefaultRoot(), id);
        if (Directory.Exists(dir)) Directory.Delete(dir, true);
        return new JourneyRecorder(id, JourneyRecorder.DefaultRoot());
    }

    static IEnumerator SampleFor(JourneyRecorder journey, float seconds)
    {
        float until = Time.time + seconds;
        while (Time.time < until)
        {
            journey.Sample();
            yield return null;
        }
    }

    static IEnumerator SampleUntil(JourneyRecorder journey, Func<bool> done, float timeout, string what)
    {
        float until = Time.time + timeout;
        while (!done())
        {
            if (Time.time > until) Assert.Fail("timed out after " + timeout.ToString("F1") + " s of game time waiting for " + what);
            journey.Sample();
            yield return null;
        }
    }

    static void AssertNeverInside(IList<ProbeSnapshot> samples)
    {
        // The probe's position is the capsule's centre, 0.4 from its side and 0.9 from its
        // ends: a sphere of 0.2 there overlaps the room only if the capsule is well inside it.
        var inside = JourneyAsserts.NeverInside(samples, 1 << WorldLayer, 0.2f);
        Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));
    }

    BoxCollider Box(string name, Vector3 centre, Vector3 size, Quaternion rotation)
    {
        GameObject go = Make(name);
        go.layer = WorldLayer;
        go.transform.SetPositionAndRotation(centre, rotation);
        go.transform.localScale = size;
        return go.AddComponent<BoxCollider>();               // a unit box, scaled by the transform
    }

    GameObject Make(string name)
    {
        var go = new GameObject(name);
        _made.Add(go);
        return go;
    }
}
