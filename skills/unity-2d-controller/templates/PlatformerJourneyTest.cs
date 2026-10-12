// PlatformerJourneyTest.cs — a play-mode journey over the side run: the jump reaches the apex
// the numbers say it should, a press just after the ledge still jumps, a press just before
// landing jumps on landing, and the runner is never inside a rooftop.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, JourneyRecorder.cs,
// JourneyInvariants2D.cs (unity-play-harness → resources/), RunInput.cs, ScriptedRunInput.cs
// (unity-input → resources/), PlatformerMotor2D.cs, PlatformerController2D.cs and
// MovingPlatform2D.cs (this skill → resources/).
//
// REQUIRES com.unity.test-framework and the built-in 2D physics module.
//
// The test builds its own strip — two BoxCollider2D rooftops with a 3-unit ledge between them
// and a runner — so it needs no scene asset and no layer set-up: rooftops sit on Default and the
// runner on the built-in Ignore Raycast layer. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter PlatformerJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
// then measure the jump the game performed (jump_report.py ships with skill unity-gameplay;
// timelines go to $JOURNEY_OUT, or to <persistentDataPath>/journeys without it):
//   python3 scripts/jump_report.py "$JOURNEY_OUT/side-run-jump/timeline.jsonl" \
//     --grounded-key grounded --apex 2.85 --air-time 0.72
//
// Prove the gate can fail before trusting a pass. Each of these must turn one test red:
//   PLATFORMER_JOURNEY_BREAK=coyote   coyote time 0: the press after the ledge is refused
//   PLATFORMER_JOURNEY_BREAK=buffer   buffer 0: the press before landing is forgotten
//   PLATFORMER_JOURNEY_BREAK=tap      the jump is tapped, not held: the cut halves the apex
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

public class PlatformerJourney
{
    const float Step = 0.02f;
    const int SolidLayer = 0;            // Default
    const int RunnerLayer = 2;           // Ignore Raycast: built in, so the test needs no layer asset
    const float RoofTop = 0f;            // the upper rooftop's surface
    const float LedgeX = 10f;            // where it ends
    const float LowerTop = -3f;          // the rooftop the ledge drops to
    const float HalfHeight = 0.9f;

    static string Break => Environment.GetEnvironmentVariable("PLATFORMER_JOURNEY_BREAK") ?? "";

    readonly List<GameObject> _made = new List<GameObject>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;
    SimulationMode2D _savedSimulationMode;

    GameObject _runner;
    PlatformerMotor2D _motor;
    PlatformerController2D _run;
    ScriptedRunInput _input;
    BoxCollider2D _upperRoof;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();

        // One rendered frame per physics step: every sample is a position the motor produced,
        // so the apex in the timeline is the apex of the simulation and not of an interpolation.
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        _savedSimulationMode = Physics2D.simulationMode;
        Time.captureDeltaTime = Step;
        Time.fixedDeltaTime = Step;
        Physics2D.simulationMode = SimulationMode2D.FixedUpdate;

        // ---- the strip: an upper rooftop from x -10 to 10, then a 3-unit drop to a lower one.
        _upperRoof = Roof("UpperRoof", new Vector2(0f, RoofTop - 0.5f), new Vector2(LedgeX * 2f, 1f));
        Roof("LowerRoof", new Vector2(LedgeX + 15f, LowerTop - 0.5f), new Vector2(30f, 1f));

        // ---- the runner. Body and collider first: the motor reads them in Awake.
        _runner = Make("Runner");
        _runner.layer = RunnerLayer;
        // Above the roof before the body exists: a body created at the origin starts inside it.
        _runner.transform.position = new Vector3(-6f, RoofTop + HalfHeight + 0.05f, 0f);
        var body = _runner.AddComponent<Rigidbody2D>();
        body.interpolation = RigidbodyInterpolation2D.None;      // samples read the simulated pose
        var box = _runner.AddComponent<BoxCollider2D>();
        box.size = new Vector2(0.8f, HalfHeight * 2f);
        _input = _runner.AddComponent<ScriptedRunInput>();
        _motor = _runner.AddComponent<PlatformerMotor2D>();
        _motor.solid = 1 << SolidLayer;
        _motor.Configure();                                      // the mask was set after Awake
        _run = _runner.AddComponent<PlatformerController2D>();
        // Every value the assertions depend on is assigned here, so a changed default in the
        // component cannot move the expected numbers.
        _run.abilities = RunAbility.Jump | RunAbility.VariableJump;
        _run.runSpeed = 8f;
        _run.apexHeight = 3f;
        _run.timeToApex = 0.4f;
        _run.fallMultiplier = 1.5f;
        _run.maxFallSpeed = 20f;
        _run.coyoteTime = Break == "coyote" ? 0f : 0.1f;
        _run.apexHangSpeed = 0f;
        _input.bufferSeconds = 0.12f;

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => (Vector3)_run.Velocity);
        GameProbe.SetState(() => _run.State);
        GameProbe.Register("grounded", () => _run.Grounded);     // jump_report.py cuts arcs on this
        GameProbe.Count("jumps", () => _run.Jumps);
        GameProbe.Count("presses", () => _input.Sent(RunButton.Launch));
        GameProbe.Ready("rooftopCollider", () => _upperRoof != null && _upperRoof.enabled);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);
        GameProbe.Ready("landed", () => _run.Grounded);
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

    // ------------------------------------------------------------------------------- the jump

    [UnityTest]
    public IEnumerator Jump_ReachesTheConfiguredApex()
    {
        yield return PlaceAndSettle(new Vector2(-6f, RoofTop + HalfHeight + 0.05f));

        using (var journey = Open("side-run-jump"))
        {
            float groundY = _runner.transform.position.y;
            yield return SampleFor(journey, 0.1f);

            // Held, because the controller shortens a jump whose button is up on the way up.
            if (Break == "tap") _input.Tap(RunButton.Launch); else _input.Hold(RunButton.Launch);
            journey.Milestone("pressed");
            yield return SampleFor(journey, 0.2f);
            Assert.IsFalse(_run.Grounded, "0.2 s after the press the runner is still on the roof — the press never reached the controller");
            yield return SampleUntil(journey, () => _run.Grounded, 2f);
            _input.Release(RunButton.Launch);
            journey.Milestone("landed");
            yield return SampleFor(journey, 0.1f);

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");
            Assert.AreEqual(1, _run.Jumps, "one press, so one jump");

            float top = float.MinValue;
            foreach (ProbeSnapshot s in samples) if (s.pos.y > top) top = s.pos.y;
            float apex = top - groundY;

            // Velocity first, then position: the simulated apex sits v0 * dt / 2 under the
            // designed one. 3.0 designed, 15 * 0.02 / 2 = 0.15 lower, so 2.85.
            float expected = _run.apexHeight - _run.JumpVelocity * Step * 0.5f;
            TestContext.WriteLine("apex=" + apex.ToString("F3") + " expected=" + expected.ToString("F3") +
                                  " gravity=" + _run.Gravity.ToString("F2") + " jumpVelocity=" +
                                  _run.JumpVelocity.ToString("F2") + " timeline=" + journey.TimelinePath);
            Assert.AreEqual(expected, apex, 0.05f, "the jump peaked at " + apex.ToString("F3") +
                            " units, designed " + expected.ToString("F3"));

            AssertNeverInside(samples);
        }
    }

    // ----------------------------------------------------------------------------- the ledge

    [UnityTest]
    public IEnumerator Press_JustAfterTheLedge_StillJumps()
    {
        yield return PlaceAndSettle(new Vector2(LedgeX - 4f, RoofTop + HalfHeight + 0.05f));

        using (var journey = Open("side-run-coyote"))
        {
            _input.SetMove(Vector2.right);
            yield return SampleUntil(journey, () => !_run.Grounded, 3f);
            journey.Milestone("left-ledge");
            Assert.AreEqual(0, _run.Jumps, "the runner jumped before any press");

            // The controller counts from its last grounded step. A press made once that count
            // shows 0.06 s is spent on the next step, at 0.08 s — inside a 0.10 s coyote window.
            yield return SampleUntil(journey, () => _run.TimeSinceGrounded >= 0.06f - 1e-4f, 1f);
            Assert.LessOrEqual(_run.TimeSinceGrounded, 0.08f + 1e-4f, "the frame was longer than the step: the press is later than 0.08 s");
            float pressedAtY = _runner.transform.position.y;
            _input.Hold(RunButton.Launch);
            journey.Milestone("pressed");
            yield return SampleFor(journey, 0.3f);
            _input.Release(RunButton.Launch);

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.AreEqual(1, _run.Jumps, "a press 0.08 s after the ledge was refused — coyote time is " +
                            _run.coyoteTime.ToString("F2") + " s");
            Assert.Greater(_runner.transform.position.y, pressedAtY + 1f, "the jump counted and the runner did not rise");
            TestContext.WriteLine("samples=" + samples.Count + " jumps=" + _run.Jumps + " timeline=" + journey.TimelinePath);

            AssertNeverInside(samples);
        }
    }

    [UnityTest]
    public IEnumerator Press_LongAfterTheLedge_IsRefused()
    {
        yield return PlaceAndSettle(new Vector2(LedgeX - 4f, RoofTop + HalfHeight + 0.05f));
        // Short, so this press has aged out long before the lower roof: nothing here may jump.
        _input.bufferSeconds = 0.05f;

        using (var journey = Open("side-run-late"))
        {
            _input.SetMove(Vector2.right);
            yield return SampleUntil(journey, () => !_run.Grounded && _run.TimeSinceGrounded >= 0.16f, 3f);
            _input.Tap(RunButton.Launch);
            journey.Milestone("pressed");
            yield return SampleUntil(journey, () => _run.Grounded, 2f);
            journey.Milestone("landed");
            yield return SampleFor(journey, 0.2f);

            Assert.AreEqual(0, _run.Jumps, "a press 0.16 s after the ledge jumped — coyote time is not a double jump");
            AssertNeverInside(journey.Captured);
        }
    }

    // --------------------------------------------------------------------------- the landing

    [UnityTest]
    public IEnumerator Press_JustBeforeLanding_JumpsOnLanding()
    {
        yield return PlaceAndSettle(new Vector2(LedgeX - 4f, RoofTop + HalfHeight + 0.05f));
        // The feet touch 0.10 s after the press and the motor reports the landing on that step;
        // the controller spends the press on the next one. A window that honours a press 0.10 s
        // early is therefore 0.10 s plus two steps. The source's default 0.12 honours 0.08 s.
        _input.bufferSeconds = Break == "buffer" ? 0f : 0.15f;

        using (var journey = Open("side-run-buffer"))
        {
            _input.SetMove(Vector2.right);
            yield return SampleUntil(journey, () => !_run.Grounded, 3f);
            journey.Milestone("left-ledge");

            yield return SampleUntil(journey, () => TimeToLand(LowerTop) <= 0.10f, 2f);
            Assert.IsFalse(_run.Grounded, "the runner landed before the press could be made early");
            Assert.Greater(_run.TimeSinceGrounded, _run.coyoteTime, "the press is inside coyote time: it would test the wrong rule");
            float early = TimeToLand(LowerTop);
            _input.Hold(RunButton.Launch);
            journey.Milestone("pressed-early");
            Assert.AreEqual(0, _run.Jumps);

            yield return SampleFor(journey, 0.4f);
            _input.Release(RunButton.Launch);

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.AreEqual(1, _run.Jumps, "a press " + early.ToString("F2") + " s before landing did not jump on landing — buffer is " +
                            _input.bufferSeconds.ToString("F2") + " s");

            // It jumped from the lower roof, not out of the air: the first sample that counts the
            // jump has the feet within one step's travel of that roof.
            foreach (ProbeSnapshot s in samples)
            {
                if (s.CountOf("jumps") == 0) continue;
                Assert.Less(s.pos.y - HalfHeight - LowerTop, 0.5f, "the jump started " +
                            (s.pos.y - HalfHeight - LowerTop).ToString("F2") + " units above the roof");
                break;
            }
            TestContext.WriteLine("samples=" + samples.Count + " early=" + early.ToString("F3") +
                                  " timeline=" + journey.TimelinePath);

            AssertNeverInside(samples);
        }
    }

    // ------------------------------------------------------------------------------- helpers

    // Seconds until the feet reach a roof at 'top', from the current height and fall speed.
    float TimeToLand(float top)
    {
        float height = _runner.transform.position.y - HalfHeight - top;
        float speed = -_run.Velocity.y;
        if (speed <= 0f || height <= 0f) return float.MaxValue;         // still rising or level
        float g = _run.Gravity * _run.fallMultiplier;
        return (-speed + Mathf.Sqrt(speed * speed + 2f * g * height)) / g;
    }

    IEnumerator PlaceAndSettle(Vector2 position)
    {
        yield return null;                                   // Awake and OnEnable have run
        _motor.Teleport(position);
        _run.ResetMotion();
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 10f)
                Assert.Fail("side run not ready after 10 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
        // "landed" was a gate for the start only; in the air it would read as not ready.
        GameProbe.ClearReady("landed");
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

    static IEnumerator SampleUntil(JourneyRecorder journey, Func<bool> done, float timeout)
    {
        float until = Time.time + timeout;
        while (!done())
        {
            if (Time.time > until) Assert.Fail("timed out after " + timeout.ToString("F1") + " s of game time waiting on the journey");
            journey.Sample();
            yield return null;
        }
    }

    static void AssertNeverInside(IList<ProbeSnapshot> samples)
    {
        // Radius well under the body's half-width: a runner standing on a roof touches it.
        var inside = JourneyInvariants2D.NeverInside2D(samples, 1 << SolidLayer, 0.2f);
        Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));
    }

    BoxCollider2D Roof(string name, Vector2 centre, Vector2 size)
    {
        GameObject go = Make(name);
        go.layer = SolidLayer;
        go.transform.position = centre;
        var box = go.AddComponent<BoxCollider2D>();
        box.size = size;
        return box;
    }

    GameObject Make(string name)
    {
        var go = new GameObject(name);
        _made.Add(go);
        return go;
    }
}
