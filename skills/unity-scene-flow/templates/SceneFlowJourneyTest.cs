// SceneFlowJourneyTest.cs — a play-mode journey over the gate room's flow: the Boot scene
// survives the level that unloads under it, the game phase only ever moves along a legal
// transition (Boot → Loading → Playing → Paused → Playing → Won), a transition the table does
// not allow is refused, and pickups respawned after the level is replaced are the same objects.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, JourneyRecorder.cs,
// Situations.cs (unity-play-harness → resources/), RunInput.cs, ScriptedRunInput.cs
// (unity-input → resources/), Bootstrap.cs, SceneLoader.cs, GameState.cs, SaveStore.cs and
// PickupObjectPool.cs (this skill → resources/).
//
// REQUIRES com.unity.test-framework.
//
// The test builds everything it needs: scenes made with SceneManager.CreateScene stand in for
// the Boot scene and two content scenes, the runner is a bare object that moves along the middle
// lane, and pickups are primitives. No scene asset, no prefab, no layer, no build-list entry.
// What that leaves untested is the read from disk — SceneLoader.Load needs scenes in the build's
// scene list; Adopt and Unload, the phase machine and the pool are the real ones. Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter SceneFlowJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
// Timelines go to $JOURNEY_OUT, or to <persistentDataPath>/journeys without it.
//
// Prove the gate can fail before trusting a pass. Each of these must turn one test red:
//   SCENEFLOW_JOURNEY_BREAK=illegal   the transition table allows everything: Paused → Won is performed
//   SCENEFLOW_JOURNEY_BREAK=boot      the Bootstrap object sits in the level's scene and unloads with it
//   SCENEFLOW_JOURNEY_BREAK=pool      the pool keeps one idle instance: a respawn creates new objects
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

/// <summary>
/// The smallest runner the flow needs: walks where the input says on the fixed step while the
/// phase is Playing, collects pickups it reaches, wins at the gate, and spends the Pause press.
/// </summary>
public sealed class GateRoomRunner : MonoBehaviour
{
    public GameState state;
    public List<PooledPickup> pickups = new List<PooledPickup>();
    public float speed = 4f;
    public float gateZ = 7f;
    public float reach = 0.3f;

    public int Collected { get; private set; }
    public Vector3 Velocity { get; private set; }

    IRunInputSource _input;

    void Update()
    {
        // Pause is spent on the frame: at timeScale 0 there is no fixed step to spend it.
        if (state == null || !RunInputSource.Resolve(gameObject, ref _input)) return;
        if (!_input.TryUse(RunButton.Pause)) return;
        if (state.TogglePause() && state.IsPlaying) _input.ClearPresses();
    }

    void FixedUpdate()
    {
        Velocity = Vector3.zero;
        // The phase gates the simulation, not the time scale: a pause that only zeroed the scale
        // would let this run again the moment anything else touched Time.timeScale.
        if (state == null || !state.IsPlaying) return;
        if (!RunInputSource.Resolve(gameObject, ref _input)) return;

        Vector2 move = _input.Peek().move;
        Velocity = new Vector3(move.x, 0f, move.y) * speed;
        transform.position += Velocity * Time.fixedDeltaTime;

        foreach (PooledPickup pickup in pickups)
        {
            if (pickup == null || !pickup.InUse) continue;
            if ((pickup.transform.position - transform.position).sqrMagnitude > reach * reach) continue;
            pickup.Release();
            Collected++;
        }
        if (transform.position.z >= gateZ) state.TryGo(GamePhase.Won);
    }
}

public class SceneFlowJourney
{
    const float Step = 0.02f;
    const float LaneSpacing = 1.3f;      // three lanes; the middle lane, 1, is at x = 0
    static readonly float[] PickupZ = { 1.5f, 3f, 4.5f };

    static string Break => Environment.GetEnvironmentVariable("SCENEFLOW_JOURNEY_BREAK") ?? "";

    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;
    float _savedTimeScale;

    Scene _bootScene;
    Scene _contentA;
    Scene _contentB;

    Bootstrap _boot;
    GameState _state;
    SceneLoader _loader;
    PickupObjectPool _pool;

    GameObject _runner;
    GateRoomRunner _run;
    ScriptedRunInput _input;
    readonly List<GameObject> _loose = new List<GameObject>();

    [UnitySetUp]
    public IEnumerator SetUp()
    {
        GameProbe.Reset();

        // One rendered frame per fixed step, so every sample is a step the runner took.
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        _savedTimeScale = Time.timeScale;
        Time.captureDeltaTime = Step;
        Time.fixedDeltaTime = Step;
        Time.timeScale = 1f;

        // A project whose Boot scene is already loaded would answer for the one built here.
        if (Bootstrap.Instance != null) UnityEngine.Object.DestroyImmediate(Bootstrap.Instance.gameObject);

        _bootScene = SceneManager.CreateScene(Bootstrap.BootSceneName);
        _contentA = SceneManager.CreateScene("gate-room");

        // ---- Boot: the root that must outlive every level, with the pool under it.
        var bootRoot = new GameObject("Boot");
        var poolObject = new GameObject("PickupObjectPool");
        poolObject.transform.SetParent(bootRoot.transform, false);
        // The break puts the root where a level lives. Nothing complains until the level goes.
        SceneManager.MoveGameObjectToScene(bootRoot, Break == "boot" ? _contentA : _bootScene);

        _boot = bootRoot.AddComponent<Bootstrap>();           // Awake: services, registry, probe state
        _state = _boot.State;
        _loader = _boot.Loader;
        if (Break == "illegal") _state.Rule = (from, to) => from != to;

        _pool = poolObject.AddComponent<PickupObjectPool>();
        _pool.Configure(MakePickup, 16, Break == "pool" ? 1 : 16);

        BuildContent(_contentA);

        GameProbe.SetPlayerVelocity(() => _runner != null ? _runner.transform : null,
                                    () => _run != null ? _run.Velocity : Vector3.zero);
        GameProbe.Register("bootAlive", () => Bootstrap.Instance != null);
        GameProbe.Register("content", () => _loader != null && _loader.HasContent ? _loader.Content.name : "");
        GameProbe.Count("collected", () => _run != null ? _run.Collected : 0);
        GameProbe.Count("poolAll", () => _pool != null ? _pool.CountAll : 0);
        GameProbe.Count("poolActive", () => _pool != null ? _pool.CountActive : 0);
        GameProbe.Count("refusals", () => _state.Refusals);
        GameProbe.Count("pausePresses", () => _input != null ? _input.Sent(RunButton.Pause) : 0);
        GameProbe.Ready("boot", () => Bootstrap.Ready);
        GameProbe.Ready("runner", () => _runner != null);

        yield return null;                                    // Start has run everywhere
    }

    [UnityTearDown]
    public IEnumerator TearDown()
    {
        Time.timeScale = _savedTimeScale;
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        Time.fixedDeltaTime = _savedFixedDeltaTime;

        if (_boot != null) UnityEngine.Object.Destroy(_boot.gameObject);
        foreach (GameObject go in _loose) if (go != null) UnityEngine.Object.Destroy(go);
        _loose.Clear();
        yield return null;

        // Unloaded and waited for: the next test creates scenes with the same names.
        foreach (Scene scene in new[] { _contentA, _contentB, _bootScene })
        {
            if (!scene.IsValid() || !scene.isLoaded) continue;
            AsyncOperation unload = SceneManager.UnloadSceneAsync(scene);
            if (unload != null) yield return unload;
        }
        _contentA = default;
        _contentB = default;
        _bootScene = default;
        GameProbe.Reset();
    }

    // ------------------------------------------------------------------------------ the flow

    [UnityTest]
    public IEnumerator GateRoom_PhaseMovesOnlyAlongLegalTransitions()
    {
        using (JourneyRecorder journey = Open("gate-room-flow"))
        {
            Assert.IsTrue(GameProbe.AllReady, "not ready: " + string.Join(", ", GameProbe.MissingReady()));
            Assert.AreEqual("Boot", GameProbe.Snapshot().state,
                            "the phase did not reach the probe: GameState.RegisterOnProbe found no GameProbe.SetState");
            yield return SampleFrames(journey, 3);

            // ---- Boot → Loading → Playing
            Assert.IsTrue(_state.TryGo(GamePhase.Loading), _state.LastRefusal);
            journey.Milestone("loading");
            yield return SampleFrames(journey, 3);

            Assert.IsTrue(_boot.AdoptContent(_contentA), "the content scene was not adopted");
            journey.Milestone("playing");
            Assert.AreEqual(GamePhase.Playing, _state.Phase);
            Assert.AreEqual("gate-room", SceneManager.GetActiveScene().name, "the level is not the active scene");

            // ---- play: up the middle lane, through two pickups
            _input.SetMove(Vector2.up);
            yield return SampleUntil(journey, () => _run.Collected >= 2, 300);

            // ---- Playing → Paused, by the Pause press and nothing else
            _input.Tap(RunButton.Pause);
            yield return SampleUntil(journey, () => _state.IsPaused, 10);
            journey.Milestone("paused");
            Assert.AreEqual(0f, Time.timeScale, "paused, and time still runs");
            Vector3 heldAt = _runner.transform.position;
            float gameTime = Time.time;
            yield return SampleFrames(journey, 15);
            Assert.AreEqual(heldAt, _runner.transform.position, "the runner moved while paused");
            Assert.AreEqual(gameTime, Time.time, "game time advanced while paused");

            // ---- the illegal move: a paused game cannot be won
            bool accepted = _state.TryGo(GamePhase.Won);
            yield return SampleFrames(journey, 2);
            Assert.IsFalse(accepted, "Paused → Won was performed: the transition table refuses nothing");
            Assert.AreEqual(GamePhase.Paused, _state.Phase);
            Assert.AreEqual(1, _state.Refusals);
            Assert.AreEqual("Paused → Won", _state.LastRefusal);

            // ---- Paused → Playing → Won
            _input.Tap(RunButton.Pause);
            yield return SampleUntil(journey, () => _state.IsPlaying, 10);
            journey.Milestone("resumed");
            Assert.AreEqual(1f, Time.timeScale, "resumed, and time is still stopped");

            yield return SampleUntil(journey, () => _state.Phase == GamePhase.Won, 400);
            journey.Milestone("won");
            yield return SampleFrames(journey, 2);

            Assert.IsFalse(_state.TryGo(GamePhase.Playing), "Won → Playing was performed");
            Assert.AreEqual(2, _input.Sent(RunButton.Pause), "the pauses did not come from the input source");
            Assert.AreEqual(3, _run.Collected);

            List<ProbeSnapshot> samples = journey.Captured;
            List<string> phases = DistinctStates(samples);
            TestContext.WriteLine("samples=" + samples.Count + " phases=" + string.Join(">", phases.ToArray()) +
                                  " timeline=" + journey.TimelinePath);
            CollectionAssert.AreEqual(new[] { "Boot", "Loading", "Playing", "Paused", "Playing", "Won" }, phases);

            // Every change between two samples is in the table — the table as shipped, not the
            // one this run may have swapped in.
            var illegal = new List<string>();
            for (int i = 1; i < samples.Count; i++)
            {
                if (samples[i].state == samples[i - 1].state) continue;
                var from = (GamePhase)Enum.Parse(typeof(GamePhase), samples[i - 1].state);
                var to = (GamePhase)Enum.Parse(typeof(GamePhase), samples[i].state);
                if (!GameState.DefaultRule(from, to)) illegal.Add(from + " → " + to + " at n=" + samples[i].n);
            }
            Assert.IsEmpty(illegal, string.Join("; ", illegal.ToArray()));

            // Boot was alive in every sample.
            List<JourneyViolation> bootGone = JourneyAsserts.Never(samples, s => !Equals(s.CustomOf("bootAlive"), true), "boot-alive");
            Assert.IsEmpty(bootGone, JourneyAsserts.Describe(bootGone));
        }
    }

    // ------------------------------------------------------------------ what survives a load

    [UnityTest]
    public IEnumerator Boot_SurvivesTheLevel_AndThePoolHandsBackTheSameObjects()
    {
        using (JourneyRecorder journey = Open("gate-room-reload"))
        {
            Assert.IsTrue(_state.TryGo(GamePhase.Loading), _state.LastRefusal);
            Assert.IsTrue(_boot.AdoptContent(_contentA), "the content scene was not adopted");
            journey.Milestone("playing");

            var firstUse = new List<PooledPickup>(_run.pickups);
            Assert.AreEqual(3, _pool.Created);

            _input.SetMove(Vector2.up);
            yield return SampleUntil(journey, () => _run.Collected >= 3, 300);
            _input.SetMove(Vector2.zero);
            Assert.AreEqual(0, _pool.CountActive, "a collected pickup is still out of the pool");

            // ---- the level goes
            Assert.IsTrue(_state.TryGo(GamePhase.Loading), _state.LastRefusal);
            Assert.IsTrue(_loader.Unload(), "nothing to unload");
            Assert.IsFalse(_loader.Unload(), "a second unload was accepted while the first was in flight");
            Assert.AreEqual(1, _loader.Refused);
            journey.Milestone("unloading");
            yield return SampleUntil(journey, () => _loader == null || !_loader.IsBusy, 600);
            journey.Milestone("unloaded");

            Assert.IsFalse(_contentA.isLoaded, "the level is still loaded");
            Assert.IsTrue(_runner == null, "the runner outlived its scene");
            Assert.IsTrue(_boot != null && Bootstrap.Instance == _boot,
                          "Boot did not survive the unload: it was in the scene that went");
            Assert.AreEqual(Bootstrap.BootSceneName, _boot.gameObject.scene.name);
            Assert.AreEqual(GamePhase.Loading, _state.Phase);
            Assert.AreEqual(3, _pool.CountAll, "the pool does not hold the three instances it made");

            // ---- the next level arrives: same pool, same objects
            _contentB = SceneManager.CreateScene("gate-room-b");
            BuildContent(_contentB);
            Assert.IsTrue(_boot.AdoptContent(_contentB), "the second content scene was not adopted");
            journey.Milestone("playing-again");
            yield return SampleFrames(journey, 3);

            Assert.AreEqual(GamePhase.Playing, _state.Phase);
            CollectionAssert.AreEquivalent(firstUse, _run.pickups,
                                           "the respawned pickups are new objects: the pool did not hand back the ones it had");
            Assert.AreEqual(3, _pool.Created, "the pool created instances for the respawn");
            foreach (PooledPickup pickup in _run.pickups) Assert.AreEqual(2, pickup.Uses);

            // The active scene decides where a new object lands. Left on Boot, everything the
            // level spawns would outlive the level.
            var spawned = new GameObject("spawned-in-play");
            Assert.AreEqual("gate-room-b", spawned.scene.name, "a new object did not land in the level");

            List<ProbeSnapshot> samples = journey.Captured;
            TestContext.WriteLine("samples=" + samples.Count + " timeline=" + journey.TimelinePath);
            List<JourneyViolation> bootGone = JourneyAsserts.Never(samples, s => !Equals(s.CustomOf("bootAlive"), true), "boot-alive");
            Assert.IsEmpty(bootGone, JourneyAsserts.Describe(bootGone));
        }
    }

    // ------------------------------------------------------------------------------- helpers

    // A level as a loaded scene has it: a runner at the start of the middle lane and three
    // pickups along it. The pickups come from the pool in Boot, never from the scene.
    void BuildContent(Scene scene)
    {
        _runner = new GameObject("Runner");
        SceneManager.MoveGameObjectToScene(_runner, scene);
        _runner.transform.position = new Vector3((1 - 1) * LaneSpacing, 0f, 0f);
        _input = _runner.AddComponent<ScriptedRunInput>();
        _run = _runner.AddComponent<GateRoomRunner>();
        _run.state = _state;
        for (int i = 0; i < PickupZ.Length; i++)
            _run.pickups.Add(_pool.Spawn(new Vector3(0f, 0f, PickupZ[i]), "pickup-" + i));
    }

    static GameObject MakePickup()
    {
        GameObject go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        go.name = "Pickup";
        go.transform.localScale = Vector3.one * 0.4f;
        // Collection is a distance test in the runner, so the journey needs no layer and no
        // physics step: the collider would only be something to configure.
        UnityEngine.Object.Destroy(go.GetComponent<Collider>());
        return go;
    }

    static List<string> DistinctStates(IList<ProbeSnapshot> samples)
    {
        var states = new List<string>();
        foreach (ProbeSnapshot s in samples)
            if (s.state != null && (states.Count == 0 || states[states.Count - 1] != s.state)) states.Add(s.state);
        return states;
    }

    static JourneyRecorder Open(string id)
    {
        // Only this journey's directory: the other journeys of the run keep their timelines.
        string dir = Path.Combine(JourneyRecorder.DefaultRoot(), id);
        if (Directory.Exists(dir)) Directory.Delete(dir, true);
        return new JourneyRecorder(id, JourneyRecorder.DefaultRoot());
    }

    // Frames, never seconds of game time: a journey that pauses the game would wait for ever.
    static IEnumerator SampleFrames(JourneyRecorder journey, int frames)
    {
        for (int i = 0; i < frames; i++)
        {
            journey.Sample();
            yield return null;
        }
    }

    static IEnumerator SampleUntil(JourneyRecorder journey, Func<bool> done, int maxFrames)
    {
        int waited = 0;
        while (!done())
        {
            if (waited++ > maxFrames) Assert.Fail("gave up after " + maxFrames + " frames waiting on the journey");
            journey.Sample();
            yield return null;
        }
    }
}
