using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>
/// AnimatorStateJourneyTest — a play-mode journey proving the Animator shows what the game says:
/// the probe value animState (the Animator's current state, by name) agrees with the game's
/// own state within a few frames of every change, for the whole run.
///
/// Copy into a PlayMode test assembly (an asmdef referencing UnityEngine.TestRunner,
/// UnityEditor.TestRunner and the assembly holding GameProbe.cs, Situations.cs and
/// JourneyRecorder.cs from the unity-play-harness skill). It runs in whatever scene is open and creates its own objects.
/// REQUIRES com.unity.test-framework.
///
/// The controller is built in memory through UnityEditor.Animations, so the test writes no
/// asset — and runs on the Editor's PlayMode platform only. In a player build of the tests it
/// reports Ignored; to run it there, load a controller asset in BuildController() instead.
///
/// Run it:
///   "$UNITY" -batchmode -projectPath . -runTests -testPlatform PlayMode \
///     -testFilter AnimatorStateJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
///   grep '\[JOURNEY\]' /tmp/tests.log        # animator-state samples=… maxLag=…
///
/// To point it at the real game, replace the three things marked REPLACE: the stub that stands
/// in for RunController, the bridge, and the state → animation-state map.
/// </summary>
public class AnimatorStateJourney
{
    // A change made by the game in frame F reaches the bridge in F+1 and the Animator later in
    // F+1, and the journey samples before the Animator evaluates — so 2 samples disagree on
    // every change by construction. 3 leaves one frame of margin and still fails a cross-fade
    // or an exit time, which hold the old state for tenths of a second.
    const int AgreeWithinFrames = 3;

    // <persistentDataPath>/journeys, or $JOURNEY_OUT when the harness set one.
    static string JourneyDir => JourneyRecorder.DefaultRoot();

    // REPLACE: the game's state → the Animator state that must be showing.
    static readonly Dictionary<string, string> Expected = new Dictionary<string, string>
    {
        { "Idle", "Idle" }, { "Run", "Run" }, { "Air", "Air" },
    };

    GameObject _runner;
    float _savedCaptureDeltaTime;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();
        // The budget is in frames, and a cross-fade is in seconds. A headless run renders
        // thousands of frames a second, so without a pinned step a 0.1 s fade is hundreds of
        // samples late on one machine and three on another.
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        Time.captureDeltaTime = 1f / 60f;
    }

    [TearDown]
    public void TearDown()
    {
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        if (_runner != null) Object.Destroy(_runner);
        GameProbe.Reset();
    }

    [UnityTest]
    public IEnumerator AnimState_FollowsGameState()
    {
        RuntimeAnimatorController controller = BuildController();
        if (controller == null)
        {
            Assert.Ignore("builds its controller through UnityEditor.Animations — Editor PlayMode platform only");
            yield break;
        }

        _runner = new GameObject("JourneyRunner");
        new GameObject("Visual").transform.SetParent(_runner.transform, false);

        var anim = _runner.AddComponent<Animator>();
        anim.runtimeAnimatorController = controller;
        // A headless run has no renderer in view; without this the Animator may skip evaluation.
        anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;

        var game = _runner.AddComponent<RunStateStub>();           // REPLACE with your RunController
        _runner.AddComponent<RunStateStubBridge>();                // REPLACE with your bridge

        var names = new AnimatorStateNames("Idle", "Run", "Air");
        GameProbe.SetState(() => game.Phase.ToString());
        // With the step pinned the probe's position-delta fallback misreads speed, so the
        // velocity is given. REPLACE Vector3.zero with your mover's own velocity.
        GameProbe.SetPlayerVelocity(() => _runner != null ? _runner.transform : null, () => Vector3.zero);
        GameProbe.Register("animState", () => names.Current(anim, 0));

        yield return null;      // one frame, so the Animator has entered its default state

        using (var journey = new JourneyRecorder("animator-state", JourneyDir))
        {
            // Idle → Run → Air → Run → Idle, with a one-frame Air in the middle: a state shorter
            // than the budget must not leave the Animator behind in it once the game has moved on.
            var script = new (RunStateStub.RunPhase phase, int frames)[]
            {
                (RunStateStub.RunPhase.Idle, 20), (RunStateStub.RunPhase.Run, 30),
                (RunStateStub.RunPhase.Air, 20), (RunStateStub.RunPhase.Run, 20),
                (RunStateStub.RunPhase.Air, 1), (RunStateStub.RunPhase.Run, 20),
                (RunStateStub.RunPhase.Idle, 20),
            };

            foreach ((RunStateStub.RunPhase phase, int frames) in script)
            {
                game.Enter(phase);
                for (int i = 0; i < frames; i++)
                {
                    journey.Sample();
                    yield return null;              // sample in Update, not at end of frame
                    Assert.Less(journey.ElapsedUnscaled, 60f, "the journey is not advancing");
                }
            }
            journey.Milestone("end");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing — did the drive loop run?");

            // 1 · the Animator never disagreed with the game for longer than the budget
            int maxLag;
            List<JourneyViolation> late = AnimatorJourneyAsserts.AgreesWithin(
                samples, "animState", Expected, AgreeWithinFrames, out maxLag);
            Assert.IsEmpty(late, JourneyAsserts.Describe(late));

            // 2 · every state the game was held in was actually shown — an Animator stuck in
            //     one state can pass rule 1 for most of a run and never play the others
            var seen = new HashSet<string>();
            foreach (ProbeSnapshot s in samples) seen.Add(s.CustomOf("animState") as string);
            foreach (string wanted in new[] { "Idle", "Run", "Air" })
                Assert.IsTrue(seen.Contains(wanted), "animState never read '" + wanted + "'; saw: " +
                                                     string.Join(",", new List<string>(seen).ToArray()));

            // 3 · no sample named a state the map does not know
            List<JourneyViolation> unknown = JourneyAsserts.Never(samples,
                s => !(s.CustomOf("animState") is string a) || a.StartsWith("#"), "anim-state-unknown");
            Assert.IsEmpty(unknown, JourneyAsserts.Describe(unknown));

            Debug.Log("[JOURNEY] animator-state samples=" + samples.Count + " maxLag=" + maxLag +
                      " budget=" + AgreeWithinFrames + " timeline=" + journey.TimelinePath);
        }
    }

    /// <summary>Idle, Run and Air on two bools, every transition instant. Null outside the Editor.</summary>
    static RuntimeAnimatorController BuildController()
    {
#if UNITY_EDITOR
        var controller = new UnityEditor.Animations.AnimatorController { name = "JourneyRunner" };
        controller.AddLayer("Base Layer");
        controller.AddParameter("Grounded", AnimatorControllerParameterType.Bool);
        controller.AddParameter("Moving", AnimatorControllerParameterType.Bool);

        UnityEditor.Animations.AnimatorStateMachine sm = controller.layers[0].stateMachine;
        UnityEditor.Animations.AnimatorState idle = sm.AddState("Idle");
        UnityEditor.Animations.AnimatorState run = sm.AddState("Run");
        UnityEditor.Animations.AnimatorState air = sm.AddState("Air");
        idle.motion = Clip("Idle", 1.00f);
        run.motion = Clip("Run", 1.05f);
        air.motion = Clip("Air", 0.95f);
        sm.defaultState = idle;

        Instant(idle.AddTransition(run), ("Grounded", true), ("Moving", true));
        Instant(run.AddTransition(idle), ("Grounded", true), ("Moving", false));
        Instant(idle.AddTransition(air), ("Grounded", false));
        Instant(run.AddTransition(air), ("Grounded", false));
        Instant(air.AddTransition(run), ("Grounded", true), ("Moving", true));
        Instant(air.AddTransition(idle), ("Grounded", true));
        return controller;
#else
        return null;
#endif
    }

#if UNITY_EDITOR
    static void Instant(UnityEditor.Animations.AnimatorStateTransition t, params (string name, bool value)[] bools)
    {
        // The two settings that make a state follow the game: no exit time, no cross-fade.
        t.hasExitTime = false;
        t.hasFixedDuration = true;
        t.duration = 0f;
        foreach ((string name, bool value) in bools)
            t.AddCondition(value ? UnityEditor.Animations.AnimatorConditionMode.If
                                 : UnityEditor.Animations.AnimatorConditionMode.IfNot, 0f, name);
    }

    // Half a second of something to play, so each state has a real length. AnimationClip.SetCurve
    // on a non-legacy clip is Editor-only, which is the other reason for the guard.
    static AnimationClip Clip(string name, float scale)
    {
        var clip = new AnimationClip { name = name, frameRate = 12f };
        foreach (string axis in new[] { "x", "y", "z" })
            clip.SetCurve("Visual", typeof(Transform), "localScale." + axis,
                          AnimationCurve.Constant(0f, 0.5f, scale));
        UnityEditor.AnimationClipSettings st = UnityEditor.AnimationUtility.GetAnimationClipSettings(clip);
        st.loopTime = true;
        UnityEditor.AnimationUtility.SetAnimationClipSettings(clip, st);
        return clip;
    }
#endif
}

/// <summary>
/// Animator state hash → name. An Animator reports hashes only; a probe value has to be a name
/// a person can read in a timeline. Lives with the game, not with the test.
/// </summary>
public sealed class AnimatorStateNames
{
    readonly Dictionary<int, string> _byHash = new Dictionary<int, string>();

    public AnimatorStateNames(params string[] stateNames)
    {
        // shortNameHash is the hash of the bare state name; fullPathHash includes the layer
        // ("Base Layer.Run") and changes when a state moves into a sub-state machine.
        foreach (string n in stateNames) _byHash[Animator.StringToHash(n)] = n;
    }

    /// <summary>The state the layer is in — or is entering: during a transition the current
    /// state is still the source, and the destination is what the game asked for.</summary>
    public string Current(Animator anim, int layer)
    {
        if (anim == null || !anim.isActiveAndEnabled || anim.runtimeAnimatorController == null) return null;
        AnimatorStateInfo info = anim.IsInTransition(layer)
            ? anim.GetNextAnimatorStateInfo(layer)
            : anim.GetCurrentAnimatorStateInfo(layer);
        string name;
        return _byHash.TryGetValue(info.shortNameHash, out name) ? name : "#" + info.shortNameHash;
    }
}

/// <summary>The invariant, kept apart from the test so another journey can reuse it.</summary>
public static class AnimatorJourneyAsserts
{
    /// <summary>
    /// For every sample, custom[animKey] equals expected[state], except for runs of at most
    /// withinFrames consecutive disagreeing samples. maxLag is the longest such run — print it,
    /// so a pass still says how close to the budget it came.
    /// </summary>
    public static List<JourneyViolation> AgreesWithin(IList<ProbeSnapshot> samples, string animKey,
                                                      IDictionary<string, string> expected,
                                                      int withinFrames, out int maxLag)
    {
        var bad = new List<JourneyViolation>();
        maxLag = 0;
        int run = 0;
        for (int i = 0; i < samples.Count; i++)
        {
            ProbeSnapshot s = samples[i];
            string want;
            if (s.state == null || !expected.TryGetValue(s.state, out want))
            {
                bad.Add(new JourneyViolation
                {
                    n = s.n, frame = s.frame, t = s.t, rule = "anim-agrees",
                    detail = "game state '" + (s.state ?? "null") + "' has no expected animation state",
                });
                continue;
            }

            string got = s.CustomOf(animKey) as string;
            if (got == want) { run = 0; continue; }

            run++;
            if (run > maxLag) maxLag = run;
            if (run == withinFrames + 1)
                bad.Add(new JourneyViolation
                {
                    n = s.n, frame = s.frame, t = s.t, rule = "anim-agrees",
                    detail = "state=" + s.state + " wants " + want + ", " + animKey + "=" + (got ?? "null") +
                             " for more than " + withinFrames + " samples",
                });
        }
        return bad;
    }
}

/// <summary>
/// REPLACE with the game's RunController. The only thing the journey needs from it is a state
/// the game owns and a way to change it that the game itself uses.
/// </summary>
public sealed class RunStateStub : MonoBehaviour
{
    public enum RunPhase { Idle, Run, Air }

    public RunPhase Phase { get; private set; }
    public bool Grounded => Phase != RunPhase.Air;
    public bool Moving => Phase == RunPhase.Run;

    public void Enter(RunPhase phase) { Phase = phase; }
}

/// <summary>
/// REPLACE with the game's bridge. The whole contract in one component: read the game's state
/// once per frame, write the parameters, and be the only script that does.
/// </summary>
public sealed class RunStateStubBridge : MonoBehaviour
{
    static readonly int GroundedId = Animator.StringToHash("Grounded");
    static readonly int MovingId = Animator.StringToHash("Moving");

    RunStateStub _run;
    Animator _anim;

    void Awake()
    {
        _run = GetComponent<RunStateStub>();
        _anim = GetComponent<Animator>();
    }

    void Update()
    {
        _anim.SetBool(GroundedId, _run.Grounded);
        _anim.SetBool(MovingId, _run.Moving);
    }
}
