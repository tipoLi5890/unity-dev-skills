// SoakTest.cs — a seeded soak over every situation: random but plausible input through the game's
// own input funnel, for a bounded number of frames per situation, with cheap invariants checked on
// every frame and the whole run recorded to a timeline that journey_report.py reads afterwards.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner, the Runtime assembly holding GameProbe.cs, Situations.cs and
// JourneyRecorder.cs (this skill → resources/), and the one holding RunInput.cs and
// ScriptedRunInput.cs (unity-input → resources/). The situations are the game's own registration
// (templates/CourierSituations.cs); the runner carries a RunInputSource, and its controller keeps
// it with RunInputSource.Resolve, so the script added here is picked up on the next fixed step.
//
// Four game facts to replace before the first run, each next to its declaration: ScenePath; Order,
// Terminal and MaxDwell (the run's states); the "Track" layer of static walls, which the run
// asserts exists so the never-inside check cannot check nothing; and custom.lane, the value whose
// change inside a lap witnesses that input landed.
//
// Run it — one seed for the whole run, printed before anything else, so a red run replays exactly:
//   SOAK_SEED=1234 SOAK_SECONDS=120 JOURNEY_OUT=/tmp/<game>_soak \
//   "$UNITY" -batchmode -projectPath . -runTests -testPlatform PlayMode \
//     -testFilter CourierSoak -testResults /tmp/<game>_soak.xml -logFile /tmp/<game>_soak.log
//   grep '\[SOAK\]' /tmp/<game>_soak.log
//   python3 scripts/journey_report.py --after /tmp/<game>_soak/soak-hazard-lane-1234/timeline.jsonl \
//     --no-null speed --no-null state --no-null cam --together laneMesh,laneCollider --min pos.y:-0.5
//
// Environment:
//   SOAK_SEED        the run's seed. Unset: a fresh one, printed with source=fresh
//   SOAK_SECONDS     game seconds per situation at the pinned frame time (default 60) — a frame count
//   SOAK_SITUATIONS  comma-separated ids to soak (default: DefaultSituations) — the replay filter
//   SOAK_EVERY       record every Nth frame (default 1); the in-loop checks still run every frame
//   SOAK_BREAK=deaf  leave the device reader enabled, so the script reaches nothing. The
//                    input-landed check must turn the run red; prove that once before trusting green.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

// Its own tier: minutes per situation and a PlayerPrefs wipe have no place in the everyday run,
// which leaves it out with -testCategory '!Perf;!Soak' (unity-debug → reference/parallel-runs.md).
[Category("Soak")]
public class CourierSoak
{
    const string ScenePath = "Assets/Scenes/Run.unity";   // replace with your game's scene

    // Wall-clock ceiling per situation. The Test Framework stops a [UnityTest] after 180 s unless
    // told otherwise, and a soak is meant to outlast that. Keep SOAK_SECONDS well inside it.
    const int TimeoutMs = 45 * 60 * 1000;

    // What a run soaks when SOAK_SITUATIONS is unset: the ids CourierSituations registers.
    static readonly string[] DefaultSituations = { "approach-gate", "runner-launch", "hazard-lane" };

    // The run's phases in the order one lap moves through them. A state outside the list is a state
    // nobody declared; a step back inside one lap is a phase re-entered.
    static readonly string[] Order = { "Idle", "Launched", "Approach", "AtGate", "Crashed", "Done" };

    // Reaching it ends the lap: the soak re-enters the same situation and keeps counting steps. A
    // game that respawns after a crash makes Crashed a lap boundary too, not a step backwards.
    const string Terminal = "Done";

    // Longest a player should sit in one state, in seconds at the pinned frame time. Every state has
    // a ceiling; one missing from the table gets the default.
    const float DefaultMaxDwell = 30f;
    static readonly Dictionary<string, float> MaxDwell = new Dictionary<string, float>
    {
        { "Idle", 2f },        // Enter launches the run: idle for longer and the launch never took
        { "Launched", 3f },
        { "AtGate", 5f },
        { "Crashed", 4f },     // the crash screen that never hands over to Done
    };

    // Live pickups plus hazards at a lap's start may exceed the first lap's by this much.
    const int LeakSlack = 2;

    enum SoakAction { Idle, SteerLeft, SteerRight, TapLaunch, HoldLaunch, TapInteract }

    // Weight, and how long the decision lasts in seconds. The minimums make the input plausible:
    // nothing shorter than a thumb can do, and no button pressed again before the funnel's 0.12 s
    // buffer has spent the last press, or the latch merges the two. Pause is left out: it stops
    // game time, and a soak that pauses spends its budget on a menu.
    static readonly (SoakAction action, int weight, float min, float max)[] Table =
    {
        (SoakAction.Idle,        3, 0.20f, 1.00f),   // reading the lane
        (SoakAction.SteerLeft,   2, 0.15f, 0.50f),   // one lane change, sometimes two
        (SoakAction.SteerRight,  2, 0.15f, 0.50f),
        (SoakAction.TapLaunch,   2, 0.15f, 0.30f),   // a tap, then hands off
        (SoakAction.HoldLaunch,  1, 0.15f, 0.60f),   // the variable launch height
        (SoakAction.TapInteract, 1, 0.15f, 0.30f),   // grab a pickup
    };

    static string JourneyDir => JourneyRecorder.DefaultRoot();   // $JOURNEY_OUT when set

    int _runSeed;
    string _seedSource;
    float _savedCaptureDeltaTime;
    float _step;
    float _seconds;
    bool _deaf;
    string _situation;
    int _lap;
    int _stepIndex;
    SoakAction _action;
    ScriptedRunInput _input;
    JourneyRecorder _journey;

    public static IEnumerable<string> SoakedSituations()
    {
        string env = Environment.GetEnvironmentVariable("SOAK_SITUATIONS");
        if (string.IsNullOrEmpty(env)) return DefaultSituations;
        var ids = new List<string>();
        foreach (string id in env.Split(','))
            if (id.Trim().Length > 0) ids.Add(id.Trim());
        return ids;
    }

    [OneTimeSetUp]
    public void PickRunSeed()
    {
        // Once per run, shared by every situation: a pinned seed replays, a fresh one explores.
        string env = Environment.GetEnvironmentVariable("SOAK_SEED");
        if (string.IsNullOrEmpty(env))
        {
            _runSeed = (int)(DateTime.UtcNow.Ticks % 1000000000L);
            _seedSource = "fresh";
        }
        else if (int.TryParse(env.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out int pinned))
        {
            _runSeed = pinned;
            _seedSource = "env";
        }
        else throw new ArgumentException("SOAK_SEED='" + env + "' is not an integer");
    }

    [SetUp]
    public void SetUp()
    {
        // A replay has to start from the same saved state. On a test lane this may reach every
        // lane's prefs as well — unity-debug → reference/parallel-runs.md.
        PlayerPrefs.DeleteAll();
        PlayerPrefs.Save();
        Situations.ClearParams();
        GameProbe.Reset();
        _input = null;
        _journey = null;
        _lap = 0;
        _stepIndex = 0;
        _action = SoakAction.Idle;

        // One rendered frame per fixed step, every frame the same length: step N is the same game
        // moment on every run, however busy the machine — or the lanes next to it — happens to be.
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _step = Time.fixedDeltaTime;
        Time.captureDeltaTime = _step;
    }

    [TearDown]
    public void TearDown()
    {
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        GameProbe.Reset();
    }

    [UnityTest, Timeout(TimeoutMs)]
    public IEnumerator Soak([ValueSource(nameof(SoakedSituations))] string situation)
    {
        _situation = situation;
        _seconds = EnvFloat("SOAK_SECONDS", 60f);
        _deaf = Environment.GetEnvironmentVariable("SOAK_BREAK") == "deaf";
        int every = Mathf.Max(1, EnvInt("SOAK_EVERY", 1));
        int steps = Mathf.Max(1, Mathf.CeilToInt(_seconds / _step));

        // First, before anything can fail: the line that makes this run replayable.
        Say(Head() + " source=" + _seedSource + " seconds=" + F(_seconds) + " steps=" + steps +
            " step=" + _step.ToString("F4", CultureInfo.InvariantCulture) + " every=" + every +
            (_deaf ? " break=deaf" : ""));

        int stream = StreamSeed(_runSeed, situation);
        var rng = new System.Random(stream);                          // inputs: (seed, step) only
        var lapRng = new System.Random(unchecked(stream * 31 + 17));  // per-lap parameters, apart
        // The game's own stream, seeded before the scene loads so a replay also replays what Awake
        // and the spawns draw. The soak never draws from it: one extra draw on either side would
        // shift every number the other gets.
        UnityEngine.Random.InitState(stream);

        yield return LoadScene();
        if (!Situations.Has(situation))
            Assert.Fail("[SOAK] " + Head() + " is not registered; registered: " + string.Join(",", Situations.Ids()));
        var unsoaked = new List<string>();
        foreach (string id in Situations.Ids())
            if (Array.IndexOf(DefaultSituations, id) < 0) unsoaked.Add(id);
        if (unsoaked.Count > 0) Say("not-in-soak-list=" + string.Join(",", unsoaked));

        _input = AttachInput();
        yield return EnterLap(lapRng);           // lap 1 before the recorder, so the meta line names it

        var clock = System.Diagnostics.Stopwatch.StartNew();
        var visits = new Dictionary<string, int>();
        var visitOrder = new List<string>();
        int steers = 0, laneMoves = 0, lastLane = int.MinValue;
        bool laneKey = false;

        using (var journey = new JourneyRecorder("soak-" + situation + "-" + _runSeed, JourneyDir, every))
        {
            _journey = journey;
            // Raised on purpose: past the cap Sample() returns null and the timeline ends early.
            journey.MaxSamples = steps / every + 1024;
            GameProbe.Register("soakStep", () => _stepIndex);
            GameProbe.Register("soakAction", () => _action.ToString());
            journey.Milestone("lap-1");

            string held = null;
            int heldSteps = 0, highest = -1, framesLeft = 0;

            for (_stepIndex = 0; _stepIndex < steps; _stepIndex++)
            {
                if (framesLeft <= 0)
                {
                    framesLeft = Decide(rng);
                    if (_action == SoakAction.SteerLeft || _action == SoakAction.SteerRight) steers++;
                }
                framesLeft--;

                yield return null;                   // the frame runs and reads the input; then look
                ProbeSnapshot s = journey.Sample() ?? GameProbe.Snapshot();

                // ---- cheap invariants, every frame, first failure stops the soak
                if (!s.hasPlayer) Fail("runner-missing", s, "the probe has no player transform");
                if (!Finite(s.pos) || !Finite(s.vel))
                    Fail("non-finite", s, "pos=" + V(s.pos) + " vel=" + V(s.vel));

                string state = s.state;
                int idx = state != null ? Array.IndexOf(Order, state) : -1;
                if (idx < 0)
                    Fail("undeclared-state", s, "state '" + (state ?? "null") + "' is not in [" + string.Join(",", Order) + "]");
                if (idx < highest)
                    Fail("state-backwards", s, "'" + state + "' after '" + Order[highest] + "' inside one lap");
                highest = idx;

                heldSteps = state == held ? heldSteps + 1 : 1;
                held = state;
                float limit = MaxDwell.TryGetValue(state, out float l) ? l : DefaultMaxDwell;
                if (heldSteps * _step > limit)
                    Fail("stuck-state", s, "'" + state + "' for " + F(heldSteps * _step) + "s, limit " + F(limit) + "s");

                if (!visits.ContainsKey(state)) { visits[state] = 0; visitOrder.Add(state); }
                visits[state]++;

                // A lane change inside a lap is the witness that input landed. Distinct lanes over
                // the whole run would not do: every lap starts in a lane drawn from lapRng.
                laneKey |= s.CustomOf("lane") != null;
                int lane = Mathf.RoundToInt(s.Number("lane", -1f));
                if (lastLane != int.MinValue && lane != lastLane) laneMoves++;
                lastLane = lane;

                if (state == Terminal)
                {
                    yield return EnterLap(lapRng);
                    journey.Milestone("lap-" + _lap);
                    held = null;
                    heldSteps = 0;
                    highest = -1;
                    lastLane = int.MinValue;
                }
            }

            // ---- over the whole recording
            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "[SOAK] " + Head() + " recorded nothing — did the drive loop run?");
            Assert.Less(samples.Count, journey.MaxSamples,
                        "[SOAK] " + Head() + " hit the sample cap; the timeline stops early");

            // The input reached the game: the script latched presses AND the runner changed lane
            // inside a lap. Without this, a controller still holding the device reader turns a soak
            // into minutes of a game nobody is playing, and every invariant above passes. A game
            // that moves the runner between lanes on its own needs a different witness here.
            int presses = _input.Sent(RunButton.Launch) + _input.Sent(RunButton.Interact);
            if (presses == 0 || laneMoves == 0)
                Fail("input-landed", samples[samples.Count - 1], "presses=" + presses + " steers=" + steers +
                     " laneMoves=" + laneMoves + " laneKey=" + (laneKey ? "yes" : "no") +
                     " — the game is not reading ScriptedRunInput");

            // Static lane walls, as in the journey: random steering is how a runner ends up in one.
            int track = LayerMask.GetMask("Track");
            Assert.AreNotEqual(0, track, "no 'Track' layer — the never-inside check would check nothing");
            Check(JourneyAsserts.NeverInside(samples, track, 0.25f), "never-inside");

            // What a lap leaves behind: live pickups and hazards at each lap's start stay near lap 1's.
            int baseline = -1;
            Check(JourneyAsserts.Never(samples, x =>
            {
                if (x.milestone == null || !x.milestone.StartsWith("lap-", StringComparison.Ordinal)) return false;
                int live = x.CountOf("pickups") + x.CountOf("hazards");
                if (baseline < 0) { baseline = live; return false; }
                return live > baseline + LeakSlack;
            }, "lap-leak"), "lap-leak");

            var unvisited = new List<string>();
            foreach (string phase in Order) if (!visits.ContainsKey(phase)) unvisited.Add(phase);
            var counted = new List<string>();
            foreach (string phase in visitOrder) counted.Add(phase + ":" + visits[phase]);

            Say("PASS " + Head() + " laps=" + _lap + " steps=" + steps + " samples=" + samples.Count +
                " presses=" + presses + " steers=" + steers + " laneMoves=" + laneMoves +
                " states=" + string.Join(",", counted) +
                " unvisited=" + (unvisited.Count > 0 ? string.Join(",", unvisited) : "-") +
                " wall=" + F((float)clock.Elapsed.TotalSeconds) + "s timeline=" + journey.TimelinePath);
        }
    }

    // ----------------------------------------------------------------- input

    // Two draws per decision, always, whatever the game did: the schedule is a function of the seed
    // and the step index alone, so a replay presses the same buttons on the same steps.
    int Decide(System.Random rng)
    {
        int total = 0;
        foreach (var row in Table) total += row.weight;
        int pick = rng.Next(total);
        int i = 0;
        while (pick >= Table[i].weight) { pick -= Table[i].weight; i++; }
        int frames = rng.Next(Frames(Table[i].min), Frames(Table[i].max) + 1);

        _action = Table[i].action;
        ApplyLevels();
        if (_action == SoakAction.TapLaunch) _input.Tap(RunButton.Launch);
        else if (_action == SoakAction.TapInteract) _input.Tap(RunButton.Interact);
        else if (_action == SoakAction.HoldLaunch) _input.Hold(RunButton.Launch);
        return frames;
    }

    // The levels the current decision holds — the part that has to come back after a lap's wait.
    void ApplyLevels()
    {
        float x = _action == SoakAction.SteerLeft ? -1f : _action == SoakAction.SteerRight ? 1f : 0f;
        _input.SetMove(new Vector2(x, 0f));
        _input.SetHeld(RunButton.Launch, _action == SoakAction.HoldLaunch);
    }

    int Frames(float seconds) => Mathf.Max(1, Mathf.RoundToInt(seconds / _step));

    // ScriptedRunInput goes on the object that holds the game's own source, and every other source
    // there is switched off, so gameplay's RunInputSource.Resolve picks the script on its next step.
    // A scene with more than one source (a menu reader) points this at the runner explicitly.
    ScriptedRunInput AttachInput()
    {
        RunInputSource found = UnityEngine.Object.FindAnyObjectByType<RunInputSource>();
        Assert.IsNotNull(found, "no RunInputSource in the scene — the soak would drive nothing");
        GameObject host = found.gameObject;
        ScriptedRunInput script = host.GetComponent<ScriptedRunInput>();
        if (script == null) script = host.AddComponent<ScriptedRunInput>();
        if (!_deaf)
            foreach (RunInputSource other in host.GetComponents<RunInputSource>())
                if (other != script) other.enabled = false;
        script.enabled = true;
        return script;
    }

    // ----------------------------------------------------------------- laps

    IEnumerator EnterLap(System.Random lapRng)
    {
        _lap++;
        // Nothing held while the moment assembles: how long a stream takes to load must not decide
        // how far the runner steers before the lap's first step.
        if (_input != null)
        {
            _input.SetMove(Vector2.zero);
            _input.Release(RunButton.Launch);
            _input.ClearPresses();
        }

        int lane = lapRng.Next(0, 3);                    // one draw per lap, always
        Situations.SetParam("lane", lane);
        Situations.SetParam("soakSeed", _runSeed);       // lands in the timeline's meta line
        SituationHandle handle = Situations.Enter(_situation);

        IEnumerator wait = handle.WaitUntilReady();
        while (true)
        {
            // C# forbids yielding inside a catch clause, so a timeout leaves the try as data.
            bool moved = false;
            string timedOut = null;
            try { moved = wait.MoveNext(); }
            catch (TimeoutException e) { timedOut = e.Message; }
            if (timedOut != null) Fail("not-ready", null, timedOut);
            if (!moved) break;
            yield return wait.Current;
        }

        if (_input == null) _input = AttachInput();      // an Enter that reloaded the scene
        ApplyLevels();                                   // the decision in force resumes
        Say("lap=" + _lap + " " + Head() + " lane=" + lane + " step=" + _stepIndex);
    }

    // ----------------------------------------------------------------- verdicts

    void Fail(string rule, ProbeSnapshot s, string detail)
    {
        if (_journey != null) _journey.Milestone("fail-" + rule);   // the row a report can find
        string line = "[SOAK] FAIL " + Head() + " lap=" + _lap + " step=" + _stepIndex +
                      " frame=" + (s != null ? s.frame : Time.frameCount) + " rule=" + rule + " " + detail +
                      " | replay: " + Replay();
        Debug.Log(line);
        Assert.Fail(line);
    }

    void Check(List<JourneyViolation> bad, string rule)
    {
        if (bad.Count == 0) return;
        string line = "[SOAK] FAIL " + Head() + " rule=" + rule + " n=" + bad[0].n + " frame=" + bad[0].frame +
                      " " + JourneyAsserts.Describe(bad) + " | replay: " + Replay();
        Debug.Log(line);
        Assert.Fail(line);
    }

    string Head() => "seed=" + _runSeed + " situation=" + _situation;

    string Replay() => "SOAK_SEED=" + _runSeed + " SOAK_SITUATIONS=" + _situation +
                       " SOAK_SECONDS=" + F(_seconds) + (_deaf ? " SOAK_BREAK=deaf" : "") +
                       " -testFilter CourierSoak";

    static void Say(string line)
    {
        Debug.Log("[SOAK] " + line);
        TestContext.WriteLine("[SOAK] " + line);
    }

    // ----------------------------------------------------------------- helpers

    // FNV-1a over the id, mixed with the seed. string.GetHashCode is not promised stable between
    // runs, and a stream that moves between runs is not a replay.
    static int StreamSeed(int seed, string id)
    {
        unchecked
        {
            uint h = 2166136261u ^ (uint)seed;
            foreach (char c in id) { h ^= c; h *= 16777619u; }
            return (int)(h & 0x7fffffffu);
        }
    }

    static bool Finite(Vector3 v) =>
        !(float.IsNaN(v.x) || float.IsNaN(v.y) || float.IsNaN(v.z) ||
          float.IsInfinity(v.x) || float.IsInfinity(v.y) || float.IsInfinity(v.z));

    static string F(float v) => v.ToString("F2", CultureInfo.InvariantCulture);

    static string V(Vector3 v) => "[" + F(v.x) + "," + F(v.y) + "," + F(v.z) + "]";

    static float EnvFloat(string name, float fallback)
    {
        string v = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrEmpty(v)) return fallback;
        if (float.TryParse(v.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out float f) && f > 0f) return f;
        throw new ArgumentException(name + "='" + v + "' is not a positive number");
    }

    static int EnvInt(string name, int fallback)
    {
        string v = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrEmpty(v)) return fallback;
        if (int.TryParse(v.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out int i) && i > 0) return i;
        throw new ArgumentException(name + "='" + v + "' is not a positive integer");
    }

    static IEnumerator LoadScene()
    {
#if UNITY_EDITOR
        // Single, never Additive: an additive load leaves the previous situation's objects alive and
        // the readiness members then read true for the wrong scene.
        yield return UnityEditor.SceneManagement.EditorSceneManager.LoadSceneAsyncInPlayMode(
            ScenePath, new LoadSceneParameters(LoadSceneMode.Single));
#else
        yield return SceneManager.LoadSceneAsync("Run", LoadSceneMode.Single);
#endif
        yield return null;   // one frame so every Awake has registered its situations
    }
}
