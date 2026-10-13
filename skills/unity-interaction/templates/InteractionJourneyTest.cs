// InteractionJourneyTest.cs — play-mode journeys over the interaction contract, in two fixtures:
//   GateRoomInteractionJourney   3D: the runner walks into reach of a switch, the probe reports
//                                the selected target, one press opens the gate once, a second
//                                press while it opens does nothing, and a switch behind the
//                                runner is not selected
//   DepotInteractionJourney      2D: a trigger sensor on the runner, two switches the same
//                                distance away, a selection that does not flicker between them,
//                                a press that reaches only the selected one, nothing out of reach
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, JourneyRecorder.cs,
// Situations.cs (unity-play-harness → resources/), RunInput.cs, ScriptedRunInput.cs (unity-input →
// resources/) and IInteractable.cs, Interactor2D.cs, Interactor3D.cs, GateSwitch.cs (this skill →
// resources/).
//
// REQUIRES com.unity.test-framework and the built-in physics and physics2d modules.
//
// Each test builds its own room from primitives — no scene asset, no prefab, no layer set-up:
// switches and gates sit on Default and the runner on the built-in Ignore Raycast layer. The
// runner's body is a few lines in this file, not a character controller. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter InteractionJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
//
// Prove the gate can fail before trusting a pass. Each of these must turn one test red:
//   INTERACTION_JOURNEY_BREAK=range     reach 20: the switch is selected, and used, from across the room
//   INTERACTION_JOURNEY_BREAK=reentry   the switch stops refusing while its gate moves: the second press reverses it
//   INTERACTION_JOURNEY_BREAK=cone      no facing cone: the switch behind the runner is selected
//   INTERACTION_JOURNEY_BREAK=flicker   switch margin 0: the selection swaps every time the runner shifts
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>The least 3D body a journey needs: kinematic, XZ plane, turns to face where it goes.</summary>
public sealed class GateRoomWalker : MonoBehaviour
{
    public float speed = 4f;
    public Vector3 Velocity { get; private set; }

    Rigidbody _body;
    IRunInputSource _input;

    void Awake() => _body = GetComponent<Rigidbody>();

    void FixedUpdate()
    {
        if (!RunInputSource.Resolve(gameObject, ref _input)) return;
        Vector2 move = _input.Peek().move;
        Velocity = new Vector3(move.x, 0f, move.y) * speed;
        _body.MovePosition(_body.position + Velocity * Time.fixedDeltaTime);
        if (Velocity.sqrMagnitude > 0.01f) _body.MoveRotation(Quaternion.LookRotation(Velocity));
    }
}

/// <summary>The least 2D body: dynamic, no gravity, velocity assigned every step.</summary>
public sealed class DepotWalker : MonoBehaviour
{
    public float speed = 1f;

    Rigidbody2D _body;
    IRunInputSource _input;

    void Awake() => _body = GetComponent<Rigidbody2D>();

    void FixedUpdate()
    {
        if (!RunInputSource.Resolve(gameObject, ref _input)) return;
        _body.linearVelocity = _input.Peek().move * speed;
    }
}

static class InteractionJourneyKit
{
    public const float Step = 0.02f;
    public const int WorldLayer = 0;            // Default
    public const int RunnerLayer = 2;           // Ignore Raycast: built in, so the test needs no layer asset

    public static string Break => Environment.GetEnvironmentVariable("INTERACTION_JOURNEY_BREAK") ?? "";

    public static string Target(ProbeSnapshot s) => s.CustomOf("target") as string ?? "";

    public static JourneyRecorder Open(string id)
    {
        // Only this journey's directory: the other journeys of the run keep their timelines.
        string dir = Path.Combine(JourneyRecorder.DefaultRoot(), id);
        if (Directory.Exists(dir)) Directory.Delete(dir, true);
        return new JourneyRecorder(id, JourneyRecorder.DefaultRoot());
    }

    public static IEnumerator SampleFor(JourneyRecorder journey, float seconds)
    {
        float until = Time.time + seconds;
        while (Time.time < until)
        {
            journey.Sample();
            yield return null;
        }
    }

    public static IEnumerator SampleUntil(JourneyRecorder journey, Func<bool> done, float timeout, string what)
    {
        float until = Time.time + timeout;
        while (!done())
        {
            if (Time.time > until) Assert.Fail("timed out after " + timeout.ToString("F1") + " s waiting for " + what);
            journey.Sample();
            yield return null;
        }
    }

    public static IEnumerator Settle(string what)
    {
        yield return null;                                   // Awake and OnEnable have run
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 10f)
                Assert.Fail(what + " not ready after 10 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
    }
}

public class GateRoomInteractionJourney
{
    const float Reach = 2f;
    const float WalkSpeed = 4f;
    const float ScanInterval = 0.1f;
    const float GateTravel = 1f;

    readonly List<GameObject> _made = new List<GameObject>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;
    SimulationMode _savedSimulationMode;

    GameObject _runner;
    Rigidbody _body;
    GateRoomWalker _walker;
    ScriptedRunInput _input;
    Interactor3D _interactor;
    GateSwitch _switch;
    Collider _switchCollider;
    GateTarget _gate;
    Collider _gateCollider;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();

        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        _savedSimulationMode = Physics.simulationMode;
        Time.captureDeltaTime = InteractionJourneyKit.Step;      // one rendered frame per physics step
        Time.fixedDeltaTime = InteractionJourneyKit.Step;
        Physics.simulationMode = SimulationMode.FixedUpdate;

        string broken = InteractionJourneyKit.Break;

        // ---- the gate: a slab across the far side of the room that lifts 3 units in 1 s.
        // Built inactive, because GateTarget reads its fields in Awake.
        GameObject gate = GameObject.CreatePrimitive(PrimitiveType.Cube);
        gate.name = "Gate";
        _made.Add(gate);
        gate.SetActive(false);
        gate.layer = InteractionJourneyKit.WorldLayer;
        gate.transform.position = new Vector3(3f, 1.5f, 8f);
        gate.transform.localScale = new Vector3(3f, 3f, 0.3f);
        _gateCollider = gate.GetComponent<Collider>();
        _gate = gate.AddComponent<GateTarget>();
        _gate.blocker = _gateCollider;
        _gate.openOffset = new Vector3(0f, 3f, 0f);
        _gate.travelSeconds = GateTravel;
        gate.SetActive(true);

        // ---- the switch: a 0.4 cube at chest height, 6 units up the room. Toggle, so a second
        // press is able to do harm and the refusal is what stops it.
        GameObject sw = GameObject.CreatePrimitive(PrimitiveType.Cube);
        sw.name = "Switch";
        _made.Add(sw);
        sw.layer = InteractionJourneyKit.WorldLayer;
        sw.transform.position = new Vector3(0f, 1f, 6f);
        sw.transform.localScale = Vector3.one * 0.4f;
        _switchCollider = sw.GetComponent<Collider>();
        _switch = sw.AddComponent<GateSwitch>();
        _switch.mode = SwitchMode.Toggle;
        _switch.targets = new[] { _gate };
        _switch.lockWhileMoving = broken != "reentry";

        // ---- the runner: a kinematic capsule that walks where the scripted input points.
        _runner = new GameObject("Runner");
        _made.Add(_runner);
        _runner.layer = InteractionJourneyKit.RunnerLayer;
        _body = _runner.AddComponent<Rigidbody>();
        _body.isKinematic = true;
        _body.interpolation = RigidbodyInterpolation.None;       // samples read the simulated pose
        var capsule = _runner.AddComponent<CapsuleCollider>();
        capsule.height = 1.8f;
        capsule.radius = 0.4f;
        capsule.center = new Vector3(0f, 0.9f, 0f);
        _input = _runner.AddComponent<ScriptedRunInput>();
        _walker = _runner.AddComponent<GateRoomWalker>();
        _walker.speed = WalkSpeed;
        _interactor = _runner.AddComponent<Interactor3D>();
        _interactor.mode = InteractDetect3D.Overlap;
        _interactor.interactable = 1 << InteractionJourneyKit.WorldLayer;
        _interactor.range = broken == "range" ? 20f : Reach;
        _interactor.halfAngle = broken == "cone" ? 180f : 60f;
        _interactor.scanInterval = ScanInterval;

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => _walker.Velocity);
        GameProbe.SetState(() => _gate.State.ToString());
        GameProbe.Register("target", () => _interactor.TargetName);
        GameProbe.Register("switchDist", () => SwitchDistance());
        GameProbe.Register("gateSolid", () => _gateCollider.enabled);
        GameProbe.Count("interactions", () => _interactor.Interactions);
        GameProbe.Count("switchUses", () => _switch.Uses);
        GameProbe.Count("gateOpens", () => _gate.OpenCount);
        GameProbe.Ready("gate", () => _gate != null && _gate.State == GateState.Closed);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);

        // Every collider above was moved after it was made. With autoSyncTransforms off, the
        // physics world still has them where they were created until the first simulation step,
        // and the interactor's first scan runs in FixedUpdate before that step: without this line
        // it selects a switch it sees at the origin.
        Physics.SyncTransforms();
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

    [UnityTest]
    public IEnumerator Runner_WalksIntoReach_AndOnlyThenIsTheSwitchSelected()
    {
        yield return InteractionJourneyKit.Settle("gate room");

        using (var journey = InteractionJourneyKit.Open("gate-room-approach"))
        {
            // 5.8 units from the switch: nothing is selected, and a press finds nothing to use.
            yield return InteractionJourneyKit.SampleFor(journey, 0.3f);
            _input.Tap(RunButton.Interact);
            yield return InteractionJourneyKit.SampleFor(journey, 0.3f);    // longer than the press buffer
            journey.Milestone("pressed-out-of-reach");
            int usedFromAfar = _interactor.Interactions;
            int opensFromAfar = _gate.OpenCount;

            _input.SetMove(Vector2.up);                                     // up the room, towards the switch
            yield return InteractionJourneyKit.SampleFor(journey, 1.2f);
            _input.SetMove(Vector2.zero);
            yield return InteractionJourneyKit.SampleFor(journey, 0.2f);
            journey.Milestone("in-reach");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");

            float firstSelectedAt = -1f;
            foreach (ProbeSnapshot s in samples)
                if (InteractionJourneyKit.Target(s) != "") { firstSelectedAt = s.Number("switchDist", -1f); break; }
            TestContext.WriteLine("firstSelectedAt=" + firstSelectedAt.ToString("F2") + " final=" +
                                  _interactor.TargetName + " dist=" + SwitchDistance().ToString("F2") +
                                  " timeline=" + journey.TimelinePath);

            Assert.AreEqual(1, _input.Sent(RunButton.Interact), "the scripted press was never sent");
            Assert.AreEqual(0, usedFromAfar, "a press 5.8 units from the switch was delivered to it");
            Assert.AreEqual(0, opensFromAfar, "the gate opened from across the room");

            var early = JourneyAsserts.Never(samples,
                s => InteractionJourneyKit.Target(s) != "" && s.Number("switchDist") > Reach + 0.01f,
                "selected-out-of-reach");
            Assert.IsEmpty(early, JourneyAsserts.Describe(early));

            Assert.AreEqual("Switch", _interactor.TargetName, "the runner stands " +
                            SwitchDistance().ToString("F2") + " units from the switch and nothing is selected");
            // Not late either: one scan interval and two steps of walking is all the lag allowed.
            float lag = WalkSpeed * (ScanInterval + 2f * InteractionJourneyKit.Step);
            Assert.Greater(firstSelectedAt, Reach - lag - 0.01f, "the switch was first selected at " +
                           firstSelectedAt.ToString("F2") + " units; reach is " + Reach.ToString("F1"));
            Assert.AreEqual(0, _gate.OpenCount, "walking into reach opened the gate with no press");
        }
    }

    [UnityTest]
    public IEnumerator Press_OpensTheGateOnce_AndASecondPressWhileItOpensDoesNothing()
    {
        yield return InteractionJourneyKit.Settle("gate room");
        Place(new Vector3(0f, 0f, 4.8f), 0f);                               // 1 unit short of the switch, facing it

        using (var journey = InteractionJourneyKit.Open("gate-room"))
        {
            yield return InteractionJourneyKit.SampleUntil(journey, () => _interactor.TargetName == "Switch",
                                                           2f, "the switch to be selected");
            journey.Milestone("selected");

            _input.Tap(RunButton.Interact);
            yield return InteractionJourneyKit.SampleFor(journey, 0.3f);
            journey.Milestone("first-press");
            string stateAtSecondPress = _gate.State.ToString();

            _input.Tap(RunButton.Interact);                                 // the gate is a third of the way up
            yield return InteractionJourneyKit.SampleFor(journey, GateTravel + 0.2f);
            journey.Milestone("settled");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");
            TestContext.WriteLine("state=" + _gate.State + " opens=" + _gate.OpenCount + " uses=" + _switch.Uses +
                                  " refusals=" + _interactor.Refusals + " timeline=" + journey.TimelinePath);

            Assert.AreEqual(2, _input.Sent(RunButton.Interact), "both presses must have been sent");
            Assert.AreEqual("Opening", stateAtSecondPress, "the second press has to land while the gate moves");

            // The gate only ever went forward. A second press that got through shows up as Closing.
            var order = JourneyAsserts.Monotonic(samples, new[] { "Closed", "Opening", "Open" });
            Assert.IsEmpty(order, JourneyAsserts.Describe(order));
            var twice = JourneyAsserts.Never(samples, s => s.CountOf("gateOpens") > 1, "opened-twice");
            Assert.IsEmpty(twice, JourneyAsserts.Describe(twice));
            // The collider follows the state: solid until Open, not solid once Open.
            var ghost = JourneyAsserts.Never(samples,
                s => s.state != "Open" && Equals(s.CustomOf("gateSolid"), false), "passable-before-open");
            Assert.IsEmpty(ghost, JourneyAsserts.Describe(ghost));

            Assert.AreEqual(GateState.Open, _gate.State, "the gate did not finish opening");
            Assert.IsFalse(_gateCollider.enabled, "the gate is open and its collider still blocks");
            Assert.AreEqual(1, _gate.OpenCount, "the gate opened " + _gate.OpenCount + " times for two presses");
            Assert.AreEqual(1, _switch.Uses, "the switch ran its effect " + _switch.Uses + " times");
            Assert.AreEqual(1, _interactor.Refusals, "the second press was not delivered as a refusal");
        }
    }

    [UnityTest]
    public IEnumerator Switch_BehindTheRunner_IsNotSelected()
    {
        yield return InteractionJourneyKit.Settle("gate room");
        Place(new Vector3(0f, 0f, 4.8f), 180f);                             // in reach, back to the switch

        using (var journey = InteractionJourneyKit.Open("gate-room-facing"))
        {
            yield return InteractionJourneyKit.SampleFor(journey, 0.4f);
            journey.Milestone("facing-away");
            int facingAway = journey.Captured.Count;

            Place(new Vector3(0f, 0f, 4.8f), 0f);
            yield return InteractionJourneyKit.SampleFor(journey, 0.4f);
            journey.Milestone("facing");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");
            TestContext.WriteLine("final=" + _interactor.TargetName + " dist=" + SwitchDistance().ToString("F2") +
                                  " timeline=" + journey.TimelinePath);

            Assert.Less(SwitchDistance(), Reach, "the runner is not in reach, so the cone was never tested");
            var behind = JourneyAsserts.Never(samples.GetRange(0, facingAway),
                s => InteractionJourneyKit.Target(s) != "", "selected-behind");
            Assert.IsEmpty(behind, JourneyAsserts.Describe(behind));
            Assert.AreEqual("Switch", _interactor.TargetName, "facing the switch at 1 unit selects nothing");
        }
    }

    // ------------------------------------------------------------------------------- helpers

    float SwitchDistance()
    {
        Vector3 origin = _runner.transform.position + Vector3.up * _interactor.originHeight;
        return Vector3.Distance(origin, _switchCollider.bounds.ClosestPoint(origin));
    }

    void Place(Vector3 position, float yaw)
    {
        Quaternion rotation = Quaternion.Euler(0f, yaw, 0f);
        _body.position = position;
        _body.rotation = rotation;
        _runner.transform.SetPositionAndRotation(position, rotation);
        Physics.SyncTransforms();
        _interactor.Rescan();                                  // a teleport: do not hold the old target for a scan
    }
}

public class DepotInteractionJourney
{
    const float SensorRadius = 2f;

    readonly List<GameObject> _made = new List<GameObject>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;
    SimulationMode2D _savedSimulationMode;

    GameObject _runner;
    Rigidbody2D _body;
    DepotWalker _walker;
    ScriptedRunInput _input;
    Interactor2D _interactor;
    GateSwitch _switchA;
    GateSwitch _switchB;
    Collider2D _switchACollider;
    GateTarget _gate;
    Collider2D _gateCollider;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();

        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        _savedSimulationMode = Physics2D.simulationMode;
        Time.captureDeltaTime = InteractionJourneyKit.Step;
        Time.fixedDeltaTime = InteractionJourneyKit.Step;
        Physics2D.simulationMode = SimulationMode2D.FixedUpdate;

        // ---- the gate at the end of the aisle: slides 3 units aside in 0.5 s.
        var gate = new GameObject("Gate");
        _made.Add(gate);
        gate.SetActive(false);                                   // GateTarget reads its fields in Awake
        gate.layer = InteractionJourneyKit.WorldLayer;
        gate.transform.position = new Vector3(5f, 0f, 0f);
        var gateBox = gate.AddComponent<BoxCollider2D>();
        gateBox.size = new Vector2(0.3f, 3f);
        _gateCollider = gateBox;
        _gate = gate.AddComponent<GateTarget>();
        _gate.blocker2D = gateBox;
        _gate.openOffset = new Vector3(0f, 3f, 0f);
        _gate.travelSeconds = 0.5f;
        gate.SetActive(true);

        // ---- two switches on the shelf ahead, mirror images about x = 0.
        _switchA = Switch("SwitchA", new Vector2(-1f, 1.2f), out _switchACollider);
        _switchA.targets = new[] { _gate };
        _switchB = Switch("SwitchB", new Vector2(1f, 1.2f), out _);

        // ---- the runner: a solid circle at the feet, and a trigger circle that is its reach.
        _runner = new GameObject("Runner");
        _made.Add(_runner);
        _runner.layer = InteractionJourneyKit.RunnerLayer;
        _runner.transform.position = new Vector3(-0.05f, 0f, 0f);   // a hair nearer to SwitchA
        _body = _runner.AddComponent<Rigidbody2D>();
        _body.gravityScale = 0f;
        _body.freezeRotation = true;
        _body.interpolation = RigidbodyInterpolation2D.None;
        _body.sleepMode = RigidbodySleepMode2D.NeverSleep;
        var feet = _runner.AddComponent<CircleCollider2D>();
        feet.radius = 0.3f;
        var sensor = _runner.AddComponent<CircleCollider2D>();
        sensor.radius = SensorRadius;
        sensor.isTrigger = true;
        _input = _runner.AddComponent<ScriptedRunInput>();
        _walker = _runner.AddComponent<DepotWalker>();
        _interactor = _runner.AddComponent<Interactor2D>();
        _interactor.mode = InteractDetect2D.TriggerList;
        _interactor.interactable = 1 << InteractionJourneyKit.WorldLayer;
        _interactor.scanInterval = 0f;                           // every step: nothing hides a flicker
        _interactor.switchMargin = InteractionJourneyKit.Break == "flicker" ? 0f : 0.15f;

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => (Vector3)_body.linearVelocity);
        GameProbe.SetState(() => _gate.State.ToString());
        GameProbe.Register("target", () => _interactor.TargetName);
        GameProbe.Register("switchDist", () => SwitchADistance());
        GameProbe.Count("interactions", () => _interactor.Interactions);
        GameProbe.Count("targetChanges", () => _interactor.TargetChanges);
        GameProbe.Count("switchUses", () => _switchA.Uses);
        GameProbe.Count("gateOpens", () => _gate.OpenCount);
        GameProbe.Ready("gate", () => _gate != null && _gate.State == GateState.Closed);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);

        Physics2D.SyncTransforms();                            // the same, for the 2D world
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
    public IEnumerator Selection_HoldsBetweenTwoEqualSwitches()
    {
        yield return InteractionJourneyKit.Settle("depot");

        using (var journey = InteractionJourneyKit.Open("depot-aisle-select"))
        {
            yield return InteractionJourneyKit.SampleUntil(journey, () => _interactor.TargetName != "",
                                                           2f, "the sensor to report a switch");
            journey.Milestone("selected");
            string first = _interactor.TargetName;
            int changesBefore = _interactor.TargetChanges;

            // Shift 0.1 units right, then left, eight times: the nearer switch changes each time
            // by 0.06 units, which is nothing a player would call a decision.
            for (int i = 0; i < 8; i++)
            {
                _input.SetMove(i % 2 == 0 ? Vector2.right : Vector2.left);
                yield return InteractionJourneyKit.SampleFor(journey, 0.1f);
            }
            _input.SetMove(Vector2.zero);
            yield return InteractionJourneyKit.SampleFor(journey, 0.1f);
            journey.Milestone("shifted");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");
            float minX = float.MaxValue, maxX = float.MinValue;
            foreach (ProbeSnapshot s in samples)
            {
                if (s.pos.x < minX) minX = s.pos.x;
                if (s.pos.x > maxX) maxX = s.pos.x;
            }
            int changes = _interactor.TargetChanges - changesBefore;
            TestContext.WriteLine("first=" + first + " changes=" + changes + " x=" + minX.ToString("F3") + ".." +
                                  maxX.ToString("F3") + " timeline=" + journey.TimelinePath);

            Assert.AreEqual("SwitchA", first, "the runner starts nearer to SwitchA");
            // It crossed the midline, or the selection was never tempted.
            Assert.Greater(maxX, 0.02f, "the runner never crossed to SwitchB's side");
            Assert.Less(minX, -0.02f, "the runner never came back to SwitchA's side");
            Assert.AreEqual(0, changes, "the selection changed " + changes +
                            " times while the runner shifted 0.1 units between two equal switches");
            Assert.AreEqual("SwitchA", _interactor.TargetName);
        }
    }

    [UnityTest]
    public IEnumerator Press_UsesOnlyTheSelectedSwitch_AndNothingOutOfReach()
    {
        yield return InteractionJourneyKit.Settle("depot");

        using (var journey = InteractionJourneyKit.Open("depot-aisle-switch"))
        {
            yield return InteractionJourneyKit.SampleUntil(journey, () => _interactor.TargetName == "SwitchA",
                                                           2f, "SwitchA to be selected");
            _input.Tap(RunButton.Interact);
            yield return InteractionJourneyKit.SampleFor(journey, 0.8f);
            journey.Milestone("pressed");
            GateState afterFirst = _gate.State;
            int usesA = _switchA.Uses, usesB = _switchB.Uses;
            // SwitchA is one-shot and spent; a usable switch beside it now outranks it.
            string afterSpent = _interactor.TargetName;

            _walker.speed = 5f;
            _input.SetMove(Vector2.down);                         // back down the aisle, out of the sensor
            yield return InteractionJourneyKit.SampleFor(journey, 1f);
            _input.SetMove(Vector2.zero);
            _input.Tap(RunButton.Interact);
            yield return InteractionJourneyKit.SampleFor(journey, 0.3f);
            journey.Milestone("out-of-reach");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");
            TestContext.WriteLine("usesA=" + _switchA.Uses + " usesB=" + _switchB.Uses + " opens=" + _gate.OpenCount +
                                  " afterSpent=" + afterSpent + " final='" + _interactor.TargetName + "' dist=" +
                                  SwitchADistance().ToString("F2") + " timeline=" + journey.TimelinePath);

            Assert.AreEqual(2, _input.Sent(RunButton.Interact), "both presses must have been sent");
            Assert.AreEqual(1, usesA, "the selected switch ran " + usesA + " times for one press");
            Assert.AreEqual(0, usesB, "the press reached the switch that was not selected");
            Assert.AreEqual(GateState.Open, afterFirst, "the gate did not open on the press");
            Assert.IsFalse(_gateCollider.enabled, "the gate is open and its collider still blocks");
            Assert.AreEqual(1, _gate.OpenCount, "the gate opened " + _gate.OpenCount + " times");
            Assert.AreEqual("SwitchB", afterSpent, "a spent switch kept the selection from the usable one beside it");

            Assert.Greater(SwitchADistance(), SensorRadius, "the runner never left the sensor's reach");
            Assert.AreEqual("", _interactor.TargetName, "a switch is still selected " +
                            SwitchADistance().ToString("F2") + " units away");
            Assert.AreEqual(1, _switchA.Uses + _switchB.Uses, "a press out of reach used a switch");
            // One step for the exit callback, one for the scan, at 0.1 units a step.
            var far = JourneyAsserts.Never(samples,
                s => InteractionJourneyKit.Target(s) != "" && s.Number("switchDist") > SensorRadius + 0.35f,
                "selected-out-of-reach");
            Assert.IsEmpty(far, JourneyAsserts.Describe(far));
        }
    }

    // ------------------------------------------------------------------------------- helpers

    float SwitchADistance()
    {
        Vector2 origin = _runner.transform.position;
        return Vector2.Distance(origin, _switchACollider.ClosestPoint(origin));
    }

    GateSwitch Switch(string name, Vector2 centre, out Collider2D collider)
    {
        var go = new GameObject(name);
        _made.Add(go);
        go.layer = InteractionJourneyKit.WorldLayer;
        go.transform.position = centre;
        var box = go.AddComponent<BoxCollider2D>();
        box.size = new Vector2(0.5f, 0.5f);
        collider = box;
        var sw = go.AddComponent<GateSwitch>();
        sw.mode = SwitchMode.OneShot;
        return sw;
    }
}
