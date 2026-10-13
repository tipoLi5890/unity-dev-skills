// SentryJourneyTest.cs — a play-mode journey over the gate room: the sentry does not react to a
// runner outside its cone or behind a wall, notices within one decision tick of real sight and
// chases after its reaction time, and walks back to its post once the runner has been out of
// sight for the memory time.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, JourneyRecorder.cs,
// Situations.cs (unity-play-harness → resources/), RunInput.cs, ScriptedRunInput.cs (unity-input → resources/)
// and StateMachine.cs, Perception.cs, SentryBrain.cs (this skill → resources/).
//
// REQUIRES com.unity.test-framework and the built-in 3D physics module. No NavMesh and no
// navigation package: the sentry moves through SentryJourneyMover, a stand-in IMover at the foot
// of this file, because the journey is about what the sentry decides, not how it paths.
//
// The test builds its own room from primitives — a post, one wall, a runner — so it needs no
// scene asset and no layer set-up: the wall sits on Default, the runner and the sentry on the
// built-in Ignore Raycast layer. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter SentryJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
//
// Prove the gate can fail before trusting a pass. Each of these must turn tests red:
//   SENTRY_JOURNEY_BREAK=los      the line-of-sight cast is skipped: the sentry sees through the
//                                 wall — the first test, and the second (it reacts before sight)
//   SENTRY_JOURNEY_BREAK=cone     the cone is 360°: the sentry sees behind itself — the first test
//   SENTRY_JOURNEY_BREAK=memory   memory lasts 30 s: the sentry never gives the chase up — the third
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

public class SentryJourney
{
    const float Step = 0.02f;
    const int WallLayer = 0;             // Default
    const int ActorLayer = 2;            // Ignore Raycast: built in, so the test needs no layer asset
    const float RunnerSpeed = 5f;

    // The room, on the XZ plane. The sentry stands at the origin looking up +z; a wall 2 wide
    // crosses its view at z = 3; the runner's lane behind the wall is z = 4.5.
    static readonly Vector3 Post = Vector3.zero;
    static readonly Vector3 BehindWall = new Vector3(0f, 0f, 4.5f);
    static readonly Vector3 BehindSentry = new Vector3(0f, 0f, -3f);
    static readonly Vector3 FarAway = new Vector3(0f, 0f, -40f);
    // The designed memory. The third test holds the sentry to this number, never to whatever its
    // field says at run time: a sentry configured to remember for 30 s has to fail it.
    const float MemorySeconds = 3f;

    static string Break => Environment.GetEnvironmentVariable("SENTRY_JOURNEY_BREAK") ?? "";

    readonly List<GameObject> _made = new List<GameObject>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;

    GameObject _runner;
    SentryJourneyRunner _body;
    ScriptedRunInput _input;
    SentryBrain _sentry;
    SentryJourneyMover _mover;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();
        PerceptionBudget.Reset();

        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        Time.captureDeltaTime = Step;        // one rendered frame per physics step
        Time.fixedDeltaTime = Step;

        // ---- the wall: 2 wide, 2 high, half a unit thick, between the post and the runner's lane.
        GameObject wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
        wall.name = "Wall";
        _made.Add(wall);
        wall.layer = WallLayer;
        wall.transform.position = new Vector3(0f, 1f, 3f);
        wall.transform.localScale = new Vector3(2f, 2f, 0.5f);

        // ---- the runner: a minimal body that reads RunInput and nothing else.
        _runner = new GameObject("Runner");
        _made.Add(_runner);
        _runner.layer = ActorLayer;
        _runner.transform.position = BehindSentry;
        _input = _runner.AddComponent<ScriptedRunInput>();
        _body = _runner.AddComponent<SentryJourneyRunner>();
        _body.speed = RunnerSpeed;

        // ---- the sentry: holds its post, looks up +z, moves through the stand-in mover.
        var sentry = new GameObject("Sentry");
        _made.Add(sentry);
        sentry.layer = ActorLayer;
        sentry.transform.position = Post;
        _mover = sentry.AddComponent<SentryJourneyMover>();
        _sentry = sentry.AddComponent<SentryBrain>();
        _sentry.target = _runner.transform;
        _sentry.blockers = 1 << WallLayer;
        if (Break == "cone") { _sentry.sight.angle = 360f; _sentry.sight.keepAngle = 360f; }
        _sentry.memorySeconds = Break == "memory" ? 30f : MemorySeconds;
        if (Break == "los") _sentry.LineOfSight = new NoCover();

        Physics.SyncTransforms();            // the wall's collider is where the casts expect it

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => _body.Velocity);
        GameProbe.SetState(() => _sentry.StateName);
        GameProbe.Register("sentry", () => _sentry.StateName);
        GameProbe.Register("alert", () => _sentry.Alert);
        // The ground truth, computed by the test from the room and never by the sentry.
        GameProbe.Register("visible", () => Visible());
        GameProbe.Register("sentryDist", () => Vector3.Distance(_mover.Position, _runner.transform.position));
        GameProbe.Ready("sentry", () => _sentry.StateName != null);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);
    }

    [TearDown]
    public void TearDown()
    {
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        Time.fixedDeltaTime = _savedFixedDeltaTime;
        foreach (GameObject go in _made) if (go != null) UnityEngine.Object.Destroy(go);
        _made.Clear();
        GameProbe.Reset();
    }

    [UnityTest]
    public IEnumerator Sentry_DoesNotReact_OutsideTheConeOrBehindAWall()
    {
        yield return Settle();

        using (var journey = Open("gate-room-unseen"))
        {
            // Behind the sentry: well inside its range, outside its cone.
            Place(BehindSentry);
            _input.SetMove(Vector2.right);
            yield return SampleFor(journey, 0.3f);
            _input.SetMove(Vector2.left);
            yield return SampleFor(journey, 0.6f);
            _input.SetMove(Vector2.zero);
            journey.Milestone("behind-the-sentry");

            // Behind the wall: inside range and cone, hidden by cover.
            Place(BehindWall);
            _input.SetMove(Vector2.right);
            yield return SampleFor(journey, 0.1f);
            _input.SetMove(Vector2.left);
            yield return SampleFor(journey, 0.2f);
            _input.SetMove(Vector2.zero);
            yield return SampleFor(journey, 0.7f);
            journey.Milestone("behind-the-wall");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");
            TestContext.WriteLine("samples=" + samples.Count + " decisions=" + _sentry.Decisions +
                                  " timeline=" + journey.TimelinePath);

            var reacted = JourneyAsserts.Never(samples, s => StateOf(s) != SentryBrain.Patrol, "reacted-unseen");
            Assert.IsEmpty(reacted, "the sentry left Patrol with the runner out of sight: " + JourneyAsserts.Describe(reacted));
            var alerted = JourneyAsserts.Never(samples, s => s.Number("alert") > 0f, "alert-unseen");
            Assert.IsEmpty(alerted, JourneyAsserts.Describe(alerted));

            // And the runner was close enough to be seen the whole time, or nothing above was tested.
            var tooFar = JourneyAsserts.Never(samples, s => s.Number("sentryDist") > _sentry.sight.range, "out-of-range");
            Assert.IsEmpty(tooFar, JourneyAsserts.Describe(tooFar));
            var visible = JourneyAsserts.Never(samples, s => IsTrue(s, "visible"), "runner-was-visible");
            Assert.IsEmpty(visible, "the journey's own path put the runner in view: " + JourneyAsserts.Describe(visible));
            Assert.Greater(_sentry.Decisions, 10, "the sentry made no decisions: it is not running");

            var inside = JourneyAsserts.NeverInside(samples, 1 << WallLayer, 0.2f);
            Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));
        }
    }

    [UnityTest]
    public IEnumerator Sentry_NoticesWithinOneDecisionTick_AndChasesAfterItsReactionTime()
    {
        yield return Settle();
        Place(BehindWall);

        using (var journey = Open("gate-room-seen"))
        {
            yield return SampleFor(journey, 0.3f);
            journey.Milestone("hidden");

            // Out from behind the wall: 2 units along the lane, into the cone with nothing in the way.
            _input.SetMove(Vector2.right);
            yield return SampleFor(journey, 0.4f);
            _input.SetMove(Vector2.zero);
            journey.Milestone("stepped-out");
            yield return SampleFor(journey, 2.0f);
            journey.Milestone("chased");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");

            float seenAt = FirstTime(samples, s => IsTrue(s, "visible"));
            float noticedAt = FirstTime(samples, s => StateOf(s) != SentryBrain.Patrol);
            float chasedAt = FirstTime(samples, s => StateOf(s) == SentryBrain.Chase);
            float endDistance = samples[samples.Count - 1].Number("sentryDist");
            TestContext.WriteLine("seenAt=" + seenAt.ToString("F2") + " noticedAt=" + noticedAt.ToString("F2") +
                                  " chasedAt=" + chasedAt.ToString("F2") + " endDistance=" + endDistance.ToString("F2") +
                                  " timeline=" + journey.TimelinePath);

            Assert.GreaterOrEqual(seenAt, 0f, "the runner never came into view: the journey tested nothing");
            Assert.GreaterOrEqual(noticedAt, 0f, "the runner stood in plain view and the sentry never left Patrol");

            // Never before: a sentry that reacts to a runner it cannot see is reading the game's state.
            var early = JourneyAsserts.Never(samples, s => s.t < seenAt && StateOf(s) != SentryBrain.Patrol, "reacted-before-sight");
            Assert.IsEmpty(early, JourneyAsserts.Describe(early));

            // One decision interval, plus the two steps between a sample and the step that acts on it.
            float slack = Step * 2f;
            Assert.LessOrEqual(noticedAt - seenAt, _sentry.decisionInterval + slack,
                "the sentry took " + (noticedAt - seenAt).ToString("F2") + " s to notice a runner in plain view");

            Assert.GreaterOrEqual(chasedAt, 0f, "the sentry noticed the runner and never chased");
            float reaction = chasedAt - seenAt;
            Assert.GreaterOrEqual(reaction, _sentry.reactionSeconds - _sentry.decisionInterval - slack,
                "the sentry chased " + reaction.ToString("F2") + " s after sight: there is no reaction time");
            Assert.LessOrEqual(reaction, _sentry.reactionSeconds + _sentry.decisionInterval + slack,
                "the sentry took " + reaction.ToString("F2") + " s to start the chase");

            // And the chase is a chase: it closes to the stopping distance and holds there.
            Assert.LessOrEqual(endDistance, _sentry.stoppingDistance + 0.2f, "the sentry did not close on the runner");
            var onTop = JourneyAsserts.Never(samples, s => s.Number("sentryDist") < _sentry.stoppingDistance - 0.2f, "ran-into-the-runner");
            Assert.IsEmpty(onTop, JourneyAsserts.Describe(onTop));
            Assert.IsTrue(_sentry.InAttackRange, "the sentry stands at its stopping distance and does not report attack range");
        }
    }

    [UnityTest]
    public IEnumerator Sentry_ReturnsToPatrol_AfterLosingTheRunnerForTheMemoryTime()
    {
        yield return Settle();
        Place(BehindWall);

        using (var journey = Open("gate-room-lost"))
        {
            _input.SetMove(Vector2.right);
            yield return SampleFor(journey, 0.4f);
            _input.SetMove(Vector2.zero);

            float waitedFrom = Time.time;
            while (_sentry.StateName != SentryBrain.Chase)
            {
                if (Time.time - waitedFrom > 3f) Assert.Fail("the sentry never chased, so there is no chase to give up");
                journey.Sample();
                yield return null;
            }
            yield return SampleFor(journey, 0.3f);

            // The runner is gone: out of range, in one step.
            Place(FarAway);
            float lostAt = Time.time;
            journey.Milestone("lost");

            // Memory, then the walk home at patrol speed from wherever the chase ended.
            float budget = MemorySeconds + 6f / _sentry.patrolSpeed + 2f;
            yield return SampleFor(journey, budget);
            journey.Milestone("home");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");

            float returnAt = FirstTime(samples, s => s.t > lostAt && StateOf(s) == SentryBrain.Return);
            float patrolAt = FirstTime(samples, s => s.t > lostAt && StateOf(s) == SentryBrain.Patrol);
            float fromPost = Vector3.Distance(_mover.Position, Post);
            TestContext.WriteLine("lostAt=" + lostAt.ToString("F2") + " returnAt=" + returnAt.ToString("F2") +
                                  " patrolAt=" + patrolAt.ToString("F2") + " fromPost=" + fromPost.ToString("F2") +
                                  " timeline=" + journey.TimelinePath);

            Assert.GreaterOrEqual(returnAt, 0f, "the sentry never gave the chase up: " + _sentry.StateName +
                                  " " + budget.ToString("F1") + " s after the runner left");
            float slack = _sentry.decisionInterval * 2f + Step * 2f;
            float held = returnAt - lostAt;
            Assert.GreaterOrEqual(held, MemorySeconds - slack,
                "the sentry gave up after " + held.ToString("F2") + " s: it forgot the runner at once");
            Assert.LessOrEqual(held, MemorySeconds + slack,
                "the sentry held the chase " + held.ToString("F2") + " s after losing the runner");

            Assert.GreaterOrEqual(patrolAt, returnAt, "the sentry never went back on patrol");
            Assert.AreEqual(SentryBrain.Patrol, _sentry.StateName, "the sentry did not stay on patrol");
            Assert.LessOrEqual(fromPost, 0.3f, "the sentry is on patrol " + fromPost.ToString("F2") + " units from its post");
        }
    }

    // ------------------------------------------------------------------------------- helpers

    /// <summary>What the room says: in range, in the cone, nothing in the way. The sentry is not asked.</summary>
    bool Visible()
    {
        Vector3 eye = _mover.Position + Vector3.up * _sentry.eyeHeight;
        Vector3 point = _runner.transform.position + Vector3.up * _sentry.targetHeight;
        Vector3 flat = point - eye;
        flat.y = 0f;
        if (flat.magnitude > 6f) return false;
        if (Vector3.Angle(_sentry.Facing, flat) > 35f) return false;
        return !Physics.Linecast(eye, point, 1 << WallLayer, QueryTriggerInteraction.Ignore);
    }

    static string StateOf(ProbeSnapshot s) => s.CustomOf("sentry") as string;

    static bool IsTrue(ProbeSnapshot s, string key) => s.CustomOf(key) is bool b && b;

    /// <summary>Time of the first sample the predicate holds on, or -1.</summary>
    static float FirstTime(IList<ProbeSnapshot> samples, Func<ProbeSnapshot, bool> predicate)
    {
        for (int i = 0; i < samples.Count; i++)
            if (predicate(samples[i])) return samples[i].t;
        return -1f;
    }

    IEnumerator Settle()
    {
        yield return null;                                   // Awake, OnEnable and Start have run
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 10f)
                Assert.Fail("gate room not ready after 10 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
    }

    void Place(Vector3 position)
    {
        _runner.transform.position = position;
        _body.Halt();
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

    /// <summary>The break switch 'los': cover that hides nothing.</summary>
    sealed class NoCover : ILineOfSight
    {
        public bool Clear(Vector3 from, Vector3 to) => true;
    }
}

/// <summary>
/// The least a runner can be: RunInput in, a position on the XZ plane out. No collider and no
/// gravity — the journey steers it round the wall, and NeverInside says so.
/// </summary>
public sealed class SentryJourneyRunner : MonoBehaviour
{
    public float speed = 5f;
    public Vector3 Velocity { get; private set; }

    IRunInputSource _input;

    public void Halt() => Velocity = Vector3.zero;

    void FixedUpdate()
    {
        Vector2 move = RunInputSource.Resolve(gameObject, ref _input) ? _input.Peek().move : Vector2.zero;
        Velocity = new Vector3(move.x, 0f, move.y) * speed;
        transform.position += Velocity * Time.fixedDeltaTime;
    }
}

/// <summary>
/// A stand-in IMover for a room with no NavMesh: straight at the destination, through anything.
/// It is the one writer of the sentry's transform, which is all the sentry asks of a mover.
/// </summary>
public sealed class SentryJourneyMover : MonoBehaviour, IMover
{
    Vector3 _destination;
    float _speed;
    float _stoppingDistance;
    bool _moving;

    public Vector3 Position => transform.position;
    public Vector3 Velocity { get; private set; }
    public bool Arrived => !_moving;

    public void MoveTo(Vector3 destination, float speed, float stoppingDistance)
    {
        _destination = destination;
        _speed = speed;
        _stoppingDistance = stoppingDistance;
        _moving = (destination - transform.position).magnitude > Mathf.Max(stoppingDistance, 0.01f);
    }

    public void Stop()
    {
        _moving = false;
        Velocity = Vector3.zero;
    }

    public void Face(Vector3 direction) { }

    void FixedUpdate()
    {
        if (!_moving) { Velocity = Vector3.zero; return; }
        Vector3 to = _destination - transform.position;
        float distance = to.magnitude;
        float reach = Mathf.Max(_stoppingDistance, 0.01f);
        if (distance <= reach) { Stop(); return; }
        float step = Mathf.Min(_speed * Time.fixedDeltaTime, distance - reach);
        transform.position += to / distance * step;
        Velocity = to / distance * (step / Time.fixedDeltaTime);
    }
}
