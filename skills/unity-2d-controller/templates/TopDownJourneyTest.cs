// TopDownJourneyTest.cs — a play-mode journey over the depot: a diagonal is no faster than a
// cardinal, the runner slides along shelving and is never inside it, and it stops within the
// distance its numbers promise.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, JourneyRecorder.cs,
// JourneyInvariants2D.cs (unity-play-harness → resources/), RunInput.cs, ScriptedRunInput.cs
// (unity-input → resources/) and TopDownMotor2D.cs (this skill → resources/).
//
// REQUIRES com.unity.test-framework and the built-in 2D physics module.
//
// The test builds its own depot — an open bay and one aisle between two shelves — so it needs no
// scene asset and no layer set-up: shelving sits on Default and the runner on the built-in
// Ignore Raycast layer. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter TopDownJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
//
// Prove the gate can fail before trusting a pass. Each of these must turn one test red:
//   TOPDOWN_JOURNEY_BREAK=kinematic   the body is kinematic: velocity carries it into the shelf
//   TOPDOWN_JOURNEY_BREAK=ice         stopping rate 5 instead of 100: the runner slides 2.5 units
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

public class TopDownJourney
{
    const float Step = 0.02f;
    const int SolidLayer = 0;            // Default
    const int RunnerLayer = 2;           // Ignore Raycast: built in, so the test needs no layer asset
    const float Radius = 0.3f;
    const float AisleHalfWidth = 1f;     // a 2-unit aisle centred on x = 0
    const float Speed = 5f;

    static string Break => Environment.GetEnvironmentVariable("TOPDOWN_JOURNEY_BREAK") ?? "";

    readonly List<GameObject> _made = new List<GameObject>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;
    SimulationMode2D _savedSimulationMode;
    PhysicsMaterial2D _slick;

    GameObject _runner;
    Rigidbody2D _body;
    TopDownMotor2D _motor;
    ScriptedRunInput _input;
    BoxCollider2D _rightShelf;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();

        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        _savedSimulationMode = Physics2D.simulationMode;
        Time.captureDeltaTime = Step;        // one rendered frame per physics step
        Time.fixedDeltaTime = Step;
        Physics2D.simulationMode = SimulationMode2D.FixedUpdate;

        // ---- the depot: shelving either side of an aisle that runs up +y from the origin.
        Shelf("LeftShelf", new Vector2(-AisleHalfWidth - 0.5f, 6f), new Vector2(1f, 12f));
        _rightShelf = Shelf("RightShelf", new Vector2(AisleHalfWidth + 0.5f, 6f), new Vector2(1f, 12f));

        // ---- the runner: a circle at the feet with no friction, so a shelf is slid along.
        // Minimum, so the runner's zero wins whatever the shelf's material says.
        _slick = new PhysicsMaterial2D("RunnerSlick")
        {
            friction = 0f, bounciness = 0f, frictionCombine = PhysicsMaterialCombine2D.Minimum,
        };
        _runner = new GameObject("Runner");
        _made.Add(_runner);
        _runner.layer = RunnerLayer;
        _runner.transform.position = new Vector3(-8f, 0f, 0f);       // the open bay, clear of shelving
        _body = _runner.AddComponent<Rigidbody2D>();
        var circle = _runner.AddComponent<CircleCollider2D>();
        circle.radius = Radius;
        circle.sharedMaterial = _slick;
        _input = _runner.AddComponent<ScriptedRunInput>();
        _motor = _runner.AddComponent<TopDownMotor2D>();
        _motor.directions = MoveDirections.Analogue;
        _motor.speed = Speed;
        _motor.accel = 62.5f;
        _motor.decel = Break == "ice" ? 5f : 100f;
        _body.interpolation = RigidbodyInterpolation2D.None;         // samples read the simulated pose
        if (Break == "kinematic") _body.bodyType = RigidbodyType2D.Kinematic;

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => (Vector3)_motor.Velocity);
        GameProbe.SetState(() => _motor.Moving ? "Moving" : "Idle");
        GameProbe.Ready("aisleWalls", () => _rightShelf != null && _rightShelf.enabled);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);
    }

    [TearDown]
    public void TearDown()
    {
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        Time.fixedDeltaTime = _savedFixedDeltaTime;
        Physics2D.simulationMode = _savedSimulationMode;
        foreach (GameObject go in _made) if (go != null) UnityEngine.Object.Destroy(go);
        _made.Clear();
        if (_slick != null) UnityEngine.Object.Destroy(_slick);
        GameProbe.Reset();
    }

    [UnityTest]
    public IEnumerator Diagonal_IsNoFasterThanACardinal()
    {
        yield return Settle();

        using (var journey = Open("depot-diagonal"))
        {
            _input.SetMove(Vector2.right);
            yield return SampleFor(journey, 0.5f);
            float straight = _motor.Velocity.magnitude;
            journey.Milestone("straight");

            _input.SetMove(Vector2.zero);
            yield return SampleFor(journey, 0.3f);

            // What a keyboard sends for up and right together, before anything clamps it.
            _input.SetMove(new Vector2(1f, 1f));
            yield return SampleFor(journey, 0.5f);
            float diagonal = _motor.Velocity.magnitude;
            journey.Milestone("diagonal");
            _input.SetMove(Vector2.zero);

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");
            TestContext.WriteLine("straight=" + straight.ToString("F3") + " diagonal=" + diagonal.ToString("F3") +
                                  " timeline=" + journey.TimelinePath);

            Assert.AreEqual(Speed, straight, 0.1f, "the runner did not reach its top speed in 0.5 s");
            Assert.AreEqual(straight, diagonal, Speed * 0.02f, "diagonal speed " + diagonal.ToString("F2") +
                            " against " + straight.ToString("F2") + " straight — 7.07 is an unclamped (1, 1)");

            // And at no sample in between: an overspeed that lasts three frames is still one.
            var fast = JourneyAsserts.Never(samples, s => s.speed > Speed * 1.02f, "overspeed");
            Assert.IsEmpty(fast, JourneyAsserts.Describe(fast));
        }
    }

    [UnityTest]
    public IEnumerator Runner_SlidesAlongShelving_AndIsNeverInsideIt()
    {
        yield return Settle();
        Place(new Vector2(0f, 1f));                      // in the aisle

        using (var journey = Open("depot-aisle"))
        {
            float startY = _runner.transform.position.y;
            _input.SetMove(new Vector2(1f, 1f));          // into the right-hand shelf and up the aisle
            yield return SampleFor(journey, 1.5f);
            _input.SetMove(Vector2.zero);
            journey.Milestone("slid");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");

            float maxX = float.MinValue;
            foreach (ProbeSnapshot s in samples) if (s.pos.x > maxX) maxX = s.pos.x;
            float advanced = _runner.transform.position.y - startY;
            TestContext.WriteLine("maxX=" + maxX.ToString("F3") + " advanced=" + advanced.ToString("F2") +
                                  " timeline=" + journey.TimelinePath);

            // It reached the shelf, or nothing below was tested.
            Assert.Greater(maxX, AisleHalfWidth - Radius - 0.1f, "the runner never reached the shelf");
            // It kept moving along it: a body that sticks to a wall has friction on its collider.
            Assert.Greater(advanced, 3f, "the runner advanced " + advanced.ToString("F2") +
                           " units up the aisle in 1.5 s — it is sticking to the shelf, not sliding along it");

            // Radius well under the body's: a runner pressed against a shelf touches it.
            var inside = JourneyInvariants2D.NeverInside2D(samples, 1 << SolidLayer, 0.15f);
            Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));
        }
    }

    [UnityTest]
    public IEnumerator Runner_StopsWithinItsStoppingDistance()
    {
        yield return Settle();

        using (var journey = Open("depot-stop"))
        {
            _input.SetMove(Vector2.right);
            yield return SampleFor(journey, 0.5f);
            float speed = _motor.Velocity.magnitude;
            Vector2 releasedAt = _runner.transform.position;
            _input.SetMove(Vector2.zero);
            journey.Milestone("released");
            yield return SampleFor(journey, 0.6f);
            journey.Milestone("stopped");

            float travelled = Vector2.Distance(releasedAt, _runner.transform.position);
            // v² / 2a from the motor's own numbers, plus the two steps that pass between the
            // release in Update and the first step that sees it.
            float designed = speed * speed / (2f * 100f);
            float allowed = designed + speed * Step * 2f;
            TestContext.WriteLine("speed=" + speed.ToString("F2") + " travelled=" + travelled.ToString("F3") +
                                  " designed=" + designed.ToString("F3") + " allowed=" + allowed.ToString("F3") +
                                  " timeline=" + journey.TimelinePath);

            Assert.Greater(speed, Speed * 0.9f, "the runner was not at speed when the stick was released");
            Assert.LessOrEqual(travelled, allowed, "the runner slid " + travelled.ToString("F2") +
                               " units after release; the numbers allow " + allowed.ToString("F2"));
            Assert.Less(_motor.Velocity.magnitude, 0.01f, "0.6 s after release the runner is still moving");
        }
    }

    // ------------------------------------------------------------------------------- helpers

    IEnumerator Settle()
    {
        yield return null;                                   // Awake and OnEnable have run
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 10f)
                Assert.Fail("depot not ready after 10 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
    }

    void Place(Vector2 position)
    {
        _body.position = position;
        _body.linearVelocity = Vector2.zero;
        _runner.transform.position = new Vector3(position.x, position.y, 0f);
        Physics2D.SyncTransforms();
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

    BoxCollider2D Shelf(string name, Vector2 centre, Vector2 size)
    {
        var go = new GameObject(name);
        _made.Add(go);
        go.layer = SolidLayer;
        go.transform.position = centre;
        var box = go.AddComponent<BoxCollider2D>();
        box.size = size;
        return box;
    }
}
