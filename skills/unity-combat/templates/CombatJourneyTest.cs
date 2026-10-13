// CombatJourneyTest.cs — a play-mode journey over the gate room: one swing across a sentry with
// two hurtboxes is one damage event, a second swing is a second, a hit during invincibility is
// none, and a shot that covers 1.2 units per step is stopped by a wall 0.1 units thick.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, JourneyRecorder.cs
// (unity-play-harness → resources/), RunInput.cs, ScriptedRunInput.cs (unity-input → resources/),
// DamageInfo.cs, Health.cs, Hitbox3D.cs and Projectile3D.cs (this skill → resources/).
//
// REQUIRES com.unity.test-framework and the built-in 3D physics module.
//
// The test builds its own room from colliders — a runner, a sentry, two walls — so it needs no
// scene asset and no layer set-up: walls sit on Default, bodies on the built-in Ignore Raycast
// layer and hurtboxes on the built-in Water layer. Hitboxes and shots are queries, so the layer
// collision matrix is never consulted. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter CombatJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
// Timelines go to $JOURNEY_OUT, or to <persistentDataPath>/journeys without it.
//
// Prove the gate can fail before trusting a pass. Each of these must turn at least one test red:
//   COMBAT_JOURNEY_BREAK=hitlist   no hit list: every hurtbox deals damage on every step
//   COMBAT_JOURNEY_BREAK=iframes   invincibility 0: the hit inside the window lands
//   COMBAT_JOURNEY_BREAK=cast      no cast: the shot is tested where each step ends, and tunnels
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

public class CombatJourney
{
    const float Step = 0.02f;
    const int SolidLayer = 0;            // Default
    const int BodyLayer = 2;             // Ignore Raycast: built in, so the test needs no layer asset
    const int HurtLayer = 4;             // Water: built in; stands in for a project's Hurtbox layer
    const float SentryZ = 1.3f;          // inside the runner's reach
    const float ShotSpeed = 60f;         // 1.2 units per 0.02 s step
    const float WallThickness = 0.1f;

    static string Break => Environment.GetEnvironmentVariable("COMBAT_JOURNEY_BREAK") ?? "";

    readonly List<GameObject> _made = new List<GameObject>();
    readonly List<int> _sentrySwingIds = new List<int>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;
    SimulationMode _savedSimulationMode;

    GameObject _runner;
    GateRoomCombatant _body;
    ScriptedRunInput _input;
    Health _runnerHealth;
    Hitbox3D _runnerHitbox;
    Projectile3D _shot;

    GameObject _sentry;
    Health _sentryHealth;
    Hitbox3D _sentryHitbox;

    BoxCollider _backWall;
    BoxCollider _thinWall;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();
        _sentrySwingIds.Clear();

        // One rendered frame per physics step: every sample is a state a fixed step produced.
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        _savedSimulationMode = Physics.simulationMode;
        Time.captureDeltaTime = Step;
        Time.fixedDeltaTime = Step;
        Physics.simulationMode = SimulationMode.FixedUpdate;

        // ---- the room. A wall close behind the runner, for the knock-back to push it against.
        _backWall = Wall("BackWall", new Vector3(0f, 1.25f, -1f), new Vector3(4f, 3.5f, 0.5f));

        // ---- the runner: a minimal body (this file, below), a hurtbox, a hitbox in front.
        _runner = Make("Runner", null, Vector3.zero);
        _runner.layer = BodyLayer;
        var controller = _runner.AddComponent<CharacterController>();
        controller.height = 1.8f;
        controller.radius = 0.4f;
        controller.center = new Vector3(0f, 0.9f, 0f);
        _input = _runner.AddComponent<ScriptedRunInput>();
        _runnerHealth = _runner.AddComponent<Health>();
        _runnerHealth.team = CombatTeam.Runner;
        _runnerHealth.max = 3;
        _runnerHealth.Revive();                                  // max was set after Awake
        _runnerHealth.invincibleSeconds = Break == "iframes" ? 0f : 0.6f;

        var runnerHurt = Make("Hurtbox", _runner, new Vector3(0f, 0.9f, 0f)).AddComponent<CapsuleCollider>();
        runnerHurt.gameObject.layer = HurtLayer;
        runnerHurt.isTrigger = true;
        runnerHurt.height = 1.8f;
        runnerHurt.radius = 0.4f;

        _runnerHitbox = Make("Strike", _runner, new Vector3(0f, 1f, 1f)).AddComponent<Hitbox3D>();
        Configure(_runnerHitbox, _runner, CombatTeam.Runner);

        var shotObject = Make("Shot", null, new Vector3(0f, -50f, 0f));
        _shot = shotObject.AddComponent<Projectile3D>();
        _shot.speed = ShotSpeed;
        _shot.radius = 0.1f;
        _shot.lifetime = 0.5f;
        _shot.hitMask = (1 << HurtLayer) | (1 << SolidLayer);
        _shot.sweep = Break != "cast";
        _shot.Finished += _ => { };                              // stay active: the test reads where it stopped

        _body = _runner.AddComponent<GateRoomCombatant>();
        _body.hitbox = _runnerHitbox;
        _body.shot = _shot;

        // ---- the sentry: a root with Health, TWO hurtboxes under it, a hitbox reaching back.
        _sentry = Make("Sentry", null, new Vector3(0f, 0f, SentryZ));
        _sentry.layer = BodyLayer;
        _sentryHealth = _sentry.AddComponent<Health>();
        _sentryHealth.team = CombatTeam.Sentry;
        _sentryHealth.max = 3;
        _sentryHealth.Revive();
        // No invincibility on the target: with it, a missing hit list hides behind the timer.
        _sentryHealth.invincibleSeconds = 0f;
        _sentryHealth.Damaged += info => _sentrySwingIds.Add(info.swingId);

        var torso = Make("Hurtbox.Torso", _sentry, new Vector3(0f, 1f, 0f)).AddComponent<BoxCollider>();
        torso.gameObject.layer = HurtLayer;
        torso.isTrigger = true;
        torso.size = new Vector3(0.6f, 1f, 0.4f);
        var head = Make("Hurtbox.Head", _sentry, new Vector3(0f, 1.35f, 0f)).AddComponent<SphereCollider>();
        head.gameObject.layer = HurtLayer;
        head.isTrigger = true;
        head.radius = 0.25f;

        _sentryHitbox = Make("Strike", _sentry, new Vector3(0f, 1f, -0.9f)).AddComponent<Hitbox3D>();
        Configure(_sentryHitbox, _sentry, CombatTeam.Sentry);

        GameProbe.SetPlayerVelocity(() => _runner.transform, () => controller.velocity);
        GameProbe.SetState(() => _body.State);
        GameProbe.Register("hitboxOpen", () => _runnerHitbox.IsOpen);
        GameProbe.Register("runnerHealth", () => _runnerHealth.Current);
        GameProbe.Register("sentryHealth", () => _sentryHealth.Current);
        GameProbe.Register("shotZ", () => _shot.transform.position.z);
        GameProbe.Count("swings", () => _runnerHitbox.SwingId);
        GameProbe.Count("sentryDamageEvents", () => _sentryHealth.DamageEvents);
        GameProbe.Count("runnerDamageEvents", () => _runnerHealth.DamageEvents);
        GameProbe.Count("presses", () => _input.Sent(RunButton.Launch) + _input.Sent(RunButton.Interact));
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);
        GameProbe.Ready("sentryAlive", () => _sentryHealth.IsAlive);
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

    // ------------------------------------------------------------------------------ the swing

    [UnityTest]
    public IEnumerator Swing_OverTwoHurtboxes_IsOneDamageEvent()
    {
        yield return Settle();

        using (var journey = Open("gate-room-swing"))
        {
            yield return SampleFor(journey, 0.1f);
            _input.Tap(RunButton.Launch);
            journey.Milestone("pressed");
            yield return SampleUntil(journey, () => _runnerHitbox.IsOpen, 1f);
            yield return SampleUntil(journey, () => !_runnerHitbox.IsOpen, 1f);
            journey.Milestone("swing-closed");
            yield return SampleFor(journey, 0.1f);

            TestContext.WriteLine("contacts=" + _runnerHitbox.ContactsThisSwing + " hits=" + _runnerHitbox.HitsThisSwing +
                                  " events=" + _sentryHealth.DamageEvents + " timeline=" + journey.TimelinePath);
            Assert.AreEqual(1, _runnerHitbox.SwingId, "one press, so one swing");
            // The gate is only worth something when the engine did offer the hit more than once.
            Assert.GreaterOrEqual(_runnerHitbox.ContactsThisSwing, 4,
                "the hitbox met fewer than two hurtboxes on two steps — the test is not exercising the hit list");
            Assert.AreEqual(1, _sentryHealth.DamageEvents, "one swing dealt " + _sentryHealth.DamageEvents +
                            " damage events to a sentry with two hurtboxes");
            Assert.AreEqual(2, _sentryHealth.Current, "one swing of damage 1 leaves 2 of 3 hearts");

            // And at no sample did the count run ahead of the swings.
            foreach (ProbeSnapshot s in journey.Captured)
                Assert.LessOrEqual(s.CountOf("sentryDamageEvents"), s.CountOf("swings"),
                    "sample " + s.n + ": more damage events than swings");
        }
    }

    [UnityTest]
    public IEnumerator SecondSwing_IsASecondDamageEvent()
    {
        yield return Settle();

        using (var journey = Open("gate-room-two-swings"))
        {
            for (int swing = 1; swing <= 2; swing++)
            {
                _input.Tap(RunButton.Launch);
                yield return SampleUntil(journey, () => _runnerHitbox.IsOpen, 1f);
                yield return SampleUntil(journey, () => !_runnerHitbox.IsOpen, 1f);
                journey.Milestone("swing-" + swing + "-closed");
                yield return SampleFor(journey, 0.1f);
                Assert.AreEqual(swing, _sentryHealth.DamageEvents, "after swing " + swing);
            }

            // The hit list is per swing, not per target: a new Open() offers the sentry again.
            CollectionAssert.AreEqual(new[] { 1, 2 }, _sentrySwingIds, "each event carries its own swing id");
            Assert.AreEqual(1, _sentryHealth.Current);
            TestContext.WriteLine("events=" + _sentryHealth.DamageEvents + " timeline=" + journey.TimelinePath);
        }
    }

    // -------------------------------------------------------------------- invincibility, knock-back

    [UnityTest]
    public IEnumerator HitDuringInvincibility_IsNoDamageEvent()
    {
        yield return Settle();

        using (var journey = Open("gate-room-iframes"))
        {
            float startZ = _runner.transform.position.z;

            yield return SentrySwing(journey);
            Assert.AreEqual(1, _runnerHealth.DamageEvents, "the sentry's first swing did not land");
            Assert.IsTrue(_runnerHealth.Invincible || Break == "iframes", "a hit that landed started no invincibility");
            journey.Milestone("hit");

            // The second swing starts 0.2 s after the first hit — inside 0.6 s of invincibility —
            // and overlaps the runner's hurtbox: it is refused, not missed.
            yield return SampleFor(journey, 0.06f);
            yield return SentrySwing(journey);
            Assert.Greater(_sentryHitbox.ContactsThisSwing, 0, "the second swing never touched the runner: the refusal is untested");
            Assert.AreEqual(1, _runnerHealth.DamageEvents, "a swing 0.2 s after a hit landed; invincibility is " +
                            _runnerHealth.invincibleSeconds.ToString("F2") + " s");
            Assert.GreaterOrEqual(_runnerHealth.RefusedEvents, 1);
            journey.Milestone("refused");

            // Once the timer is out, the next swing lands again.
            yield return SampleUntil(journey, () => !_runnerHealth.Invincible, 2f);
            yield return SentrySwing(journey);
            Assert.AreEqual(2, _runnerHealth.DamageEvents, "after invincibility ran out the swing still did not land");

            // The push went through the body: the runner moved away from the sentry and stopped
            // at the wall behind it, never inside.
            Assert.Less(_runner.transform.position.z, startZ - 0.1f, "the hit carried knock-back 8 and the runner did not move");
            var inside = JourneyAsserts.NeverInside(journey.Captured, 1 << SolidLayer, 0.2f);
            Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));
            TestContext.WriteLine("runnerZ=" + _runner.transform.position.z.ToString("F3") + " refused=" +
                                  _runnerHealth.RefusedEvents + " timeline=" + journey.TimelinePath);
        }
    }

    // ------------------------------------------------------------------------------- the shot

    [UnityTest]
    public IEnumerator FastShot_IsStoppedByAThinWall()
    {
        // Muzzle at z 1. Each step is 1.2 units, so step ends fall at 2.2, 3.4, 4.6, 5.8 …; the
        // wall sits between two of them and the sentry stands on a later one.
        float perStep = ShotSpeed * Step;
        float muzzleZ = _body.muzzle.z;
        float wallZ = muzzleZ + perStep * 3.5f;
        float sentryZ = muzzleZ + perStep * 6f;
        _thinWall = Wall("ThinWall", new Vector3(0f, 1.25f, wallZ), new Vector3(4f, 3.5f, WallThickness));
        _sentry.transform.position = new Vector3(0f, 0f, sentryZ);
        yield return Settle();
        Assert.Greater(perStep, WallThickness * 4f, "the shot is too slow to step over the wall: nothing is being proved");

        using (var journey = Open("gate-room-shot"))
        {
            yield return SampleFor(journey, 0.06f);
            _input.Tap(RunButton.Interact);
            journey.Milestone("fired");
            yield return SampleUntil(journey, () => _body.Shots == 1, 1f);
            yield return SampleUntil(journey, () => !_shot.Flying, 2f);
            journey.Milestone("stopped");
            yield return SampleFor(journey, 0.06f);

            float nearFace = wallZ - WallThickness * 0.5f;
            float farFace = wallZ + WallThickness * 0.5f;
            TestContext.WriteLine("stoppedAt=" + _shot.transform.position.z.ToString("F3") + " nearFace=" + nearFace.ToString("F3") +
                                  " stoppedBy=" + (_shot.StoppedBy != null ? _shot.StoppedBy.name : "nothing") +
                                  " timeline=" + journey.TimelinePath);

            foreach (ProbeSnapshot s in journey.Captured)
                Assert.LessOrEqual(s.Number("shotZ"), farFace, "sample " + s.n + ": the shot is at z " +
                                   s.Number("shotZ").ToString("F2") + ", past a wall whose far face is at " + farFace.ToString("F2"));
            Assert.AreSame(_thinWall, _shot.StoppedBy, "the shot was not stopped by the wall");
            Assert.LessOrEqual(_shot.transform.position.z, nearFace + 1e-3f, "the shot stopped inside or beyond the wall");
            Assert.AreEqual(0, _sentryHealth.DamageEvents, "the sentry behind the wall was hit");
        }
    }

    // ------------------------------------------------------------------------------- helpers

    void Configure(Hitbox3D hitbox, GameObject owner, int team)
    {
        // Every value the assertions depend on is assigned here, so a changed default in the
        // component cannot move the expected numbers.
        hitbox.owner = owner;
        hitbox.team = team;
        hitbox.damage = 1;
        hitbox.knockback = 8f;
        hitbox.stun = 0.15f;
        hitbox.halfExtents = new Vector3(0.5f, 0.5f, 0.5f);
        hitbox.hurtMask = 1 << HurtLayer;
        hitbox.blockMask = 0;
        hitbox.sweep = true;
        hitbox.oncePerSwing = Break != "hitlist";
    }

    // The sentry is not driven by input: its swing is opened and closed as its own state would.
    IEnumerator SentrySwing(JourneyRecorder journey)
    {
        _sentryHitbox.Open();
        yield return SampleFor(journey, 0.1f);
        _sentryHitbox.Close();
        yield return SampleFor(journey, 0.04f);
    }

    IEnumerator Settle()
    {
        yield return null;                                   // Awake and OnEnable have run
        Physics.SyncTransforms();                            // colliders are where the test put them
        yield return new WaitForFixedUpdate();
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 10f)
                Assert.Fail("gate room not ready after 10 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
        // A gate for the start only: under a break the sentry may die, and that is the finding.
        GameProbe.ClearReady("sentryAlive");
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

    BoxCollider Wall(string name, Vector3 centre, Vector3 size)
    {
        GameObject go = Make(name, null, centre);
        go.layer = SolidLayer;
        var box = go.AddComponent<BoxCollider>();
        box.size = size;
        return box;
    }

    GameObject Make(string name, GameObject parent, Vector3 localPosition)
    {
        var go = new GameObject(name);
        if (parent != null) go.transform.SetParent(parent.transform, false);
        go.transform.localPosition = localPosition;
        if (parent == null) _made.Add(go);
        return go;
    }
}

/// <summary>
/// The least a body can be and still take part in a fight: it reads RunInput, owns a swing as a
/// state with a length in game time, fires one shot, and applies knock-back through the one
/// component that moves it. A real game uses its own controller; this exists so the journey
/// depends on nothing but the combat files.
/// </summary>
public sealed class GateRoomCombatant : MonoBehaviour
{
    public Hitbox3D hitbox;
    public Projectile3D shot;
    public float swingSeconds = 0.2f;
    public Vector3 muzzle = new Vector3(0f, 1f, 1f);
    public float pushDecel = 50f;

    public string State => _stun > 0f ? "Stunned" : _swing > 0f ? "Swing" : "Idle";
    public int Shots { get; private set; }

    IRunInputSource _input;
    CharacterController _controller;
    Health _health;
    Vector3 _push;
    float _stun;
    float _swing;

    void Awake()
    {
        _controller = GetComponent<CharacterController>();
        _health = GetComponent<Health>();
    }

    void OnEnable() { if (_health != null) _health.Damaged += OnDamaged; }
    void OnDisable() { if (_health != null) _health.Damaged -= OnDamaged; }

    void OnDamaged(DamageInfo info)
    {
        // The hit interrupts the swing: the game closes its own window, whatever the Animator does.
        if (_swing > 0f) { _swing = 0f; hitbox.Close(); }
        _push = info.KnockbackVelocity;
        _stun = info.stun;
    }

    void FixedUpdate()
    {
        float dt = Time.fixedDeltaTime;

        if (_swing > 0f)
        {
            _swing -= dt;
            if (_swing <= 0f) hitbox.Close();
        }

        if (_push.sqrMagnitude > 0f)
        {
            _controller.Move(_push * dt);                    // stops at walls; a position write would not
            _push = Vector3.MoveTowards(_push, Vector3.zero, pushDecel * dt);
        }
        if (_stun > 0f) { _stun -= dt; return; }             // no control while stunned

        if (!RunInputSource.Resolve(gameObject, ref _input)) return;
        // Condition first, then TryUse: a press made mid-swing waits in the buffer.
        if (_swing <= 0f && _input.TryUse(RunButton.Launch))
        {
            _swing = swingSeconds;
            hitbox.Open();
        }
        if (shot != null && !shot.Flying && _input.TryUse(RunButton.Interact))
        {
            Shots++;
            shot.Launch(transform.TransformPoint(muzzle), transform.forward, CombatTeam.Runner, gameObject);
        }
    }
}
