// FeelJourneyTest.cs — a play-mode journey over the gate room's feedback: after a hit stop
// time is back at its earlier scale inside the window, when two stops overlap and when the
// requester dies mid-stop; a flash gives the renderer back the look it had; and thirty pickups
// inside 0.1 s start no more sounds than the voice cap.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// UnityEditor.TestRunner and the Runtime assembly holding GameProbe.cs, JourneyRecorder.cs
// (unity-play-harness → resources/), RunInput.cs, ScriptedRunInput.cs (unity-input →
// resources/), Feedback.cs, HitStop.cs, RendererFlash.cs, Tween.cs and SfxPlayer.cs (this
// skill → resources/).
//
// REQUIRES com.unity.test-framework and the built-in Audio module.
//
// The test builds its own room — a cube runner, a second cube, a sprite, thirty pickup
// positions down the middle lane, a silent clip — so it needs no scene asset, no layer and no
// audio file. Nothing is asserted on pixels or on what the speakers did: batch mode has
// neither. It reads Time.timeScale, the renderer's property block and the player's counters.
// Run it:
//   "$UNITY" -projectPath . -batchmode -runTests -testPlatform PlayMode \
//     -testFilter FeelJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
// Timelines go to $JOURNEY_OUT, or to <persistentDataPath>/journeys without it; every sample
// carries timeScale, so the dip is a column in timeline.jsonl.
//
// Prove the gate can fail before trusting a pass. Each of these must turn tests red:
//   FEEL_JOURNEY_BREAK=restore   (or 1) the stop is the coroutine everyone writes first, on the thing
//                                that was hit: the restore is skipped when that thing is
//                                destroyed and restores the wrong value when two overlap
//                                (OverlappingStops…, RequesterDestroyed…)
//   FEEL_JOURNEY_BREAK=flash     the flash captures "the original" on every call, so the
//                                second of two overlapping flashes restores the flash colour
//                                (OverlappingFlashes…)
//   FEEL_JOURNEY_BREAK=voices    voice cap 64: thirty pickups are thirty sounds (ThirtyPickups…)
using System;
using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

public class FeelJourney
{
    const float Step = 0.02f;
    const float LaneX = 0f;              // the middle lane; lanes sit 1.3 apart
    const float StopSeconds = 0.10f;
    const float FlashSeconds = 0.08f;
    const int VoiceCap = 8;
    const int Pickups = 30;
    // One rendered frame of grace either side: the owner acts on the first frame at or past
    // the end time, and a frame has no upper bound on a busy machine.
    const float Slack = 0.10f;
    const float Early = 0.02f;

    static string Break => Environment.GetEnvironmentVariable("FEEL_JOURNEY_BREAK") ?? "";

    readonly List<UnityEngine.Object> _made = new List<UnityEngine.Object>();
    float _savedCaptureDeltaTime;
    float _savedFixedDeltaTime;

    GameObject _runner;
    FeelJourneyRunner _run;
    ScriptedRunInput _input;
    Feedback _feedback;
    SfxPlayer _sfx;
    RendererFlash _flash;
    MeshRenderer _runnerRenderer;

    [SetUp]
    public void SetUp()
    {
        GameProbe.Reset();
        HitStop.Clear();
        Feedback.ResetBudget();
        FeelSettings.reduceMotion = false;
        FeelSettings.reduceFlash = false;
        Time.timeScale = 1f;

        // One rendered frame per physics step, so the runner's sweep through the pickups is
        // the same five steps on every machine.
        _savedCaptureDeltaTime = Time.captureDeltaTime;
        _savedFixedDeltaTime = Time.fixedDeltaTime;
        Time.captureDeltaTime = Step;
        Time.fixedDeltaTime = Step;

        if (UnityEngine.Object.FindAnyObjectByType<AudioListener>() == null)
            Make("Listener").AddComponent<AudioListener>();

        // ---- the sound side: one silent half-second clip, one event, a pool of eight.
        AudioClip clip = AudioClip.Create("pickup", 22050, 1, 44100, false);
        _made.Add(clip);
        _sfx = Make("Sfx").AddComponent<SfxPlayer>();
        _sfx.voiceCap = Break == "voices" ? 64 : VoiceCap;
        _sfx.events = new[]
        {
            new SfxEvent
            {
                name = "pickup", clips = new[] { clip },
                // Cooldown off and the per-event limit out of the way: this test is about the
                // cap. With the default 0.05 s cooldown the answer would be one or two sounds
                // and the cap would never be reached.
                cooldownSeconds = 0f, maxVoices = 64,
            },
            new SfxEvent { name = "hit", clips = new[] { clip }, priority = 1 },
        };
        _sfx.Index();

        // ---- the runner: a cube that reads RunInput, runs up the middle lane and takes a hit
        // on Launch. It stands in for whatever the game's own controller and combat are.
        _runner = GameObject.CreatePrimitive(PrimitiveType.Cube);
        _runner.name = "Runner";
        _made.Add(_runner);
        _runner.transform.position = new Vector3(LaneX, 0.5f, 0f);
        _runnerRenderer = _runner.GetComponent<MeshRenderer>();
        _input = _runner.AddComponent<ScriptedRunInput>();
        _flash = _runner.AddComponent<RendererFlash>();
        _flash.mode = FlashMode.PropertyBlock;
        _flash.Collect();

        _feedback = _runner.AddComponent<Feedback>();
        _feedback.sfx = _sfx;
        // Every number the assertions depend on is assigned here, so a changed default in a
        // component cannot move them.
        _feedback.rows = new[]
        {
            new FeedbackRow
            {
                id = "hit", priority = 1,
                flash = new FlashChannel { on = true, target = _flash, colour = Color.white, ms = (int)(FlashSeconds * 1000f) },
                time = new TimeChannel { on = true, ms = (int)(StopSeconds * 1000f), scale = 0.05f },
                sound = new SoundChannel { on = true, sfxEvent = "hit" },
            },
            new FeedbackRow
            {
                id = "pickup", priority = 0,
                sound = new SoundChannel { on = true, sfxEvent = "pickup" },
            },
        };

        _run = _runner.AddComponent<FeelJourneyRunner>();
        _run.feedback = _feedback;
        // Thirty pickups 0.2 apart from z 1: at 60 units a second the runner covers 1.2 a step,
        // six pickups, and all thirty in five steps — 0.1 s of game time.
        _run.speed = 60f;
        _run.pickupZ = new float[Pickups];
        for (int i = 0; i < Pickups; i++) _run.pickupZ[i] = 1f + 0.2f * i;

        GameProbe.SetPlayer(() => _runner != null ? _runner.transform : null);
        GameProbe.Count("hits", () => _run.Hits);
        GameProbe.Count("pickups", () => _run.Collected);
        GameProbe.Count("presses", () => _input.Sent(RunButton.Launch));
        GameProbe.Count("sfxPlayed", () => _sfx.Played);
        GameProbe.Count("sfxDropped", () => _sfx.Dropped);
        GameProbe.Count("stopsAccepted", () => HitStop.Accepted);
        GameProbe.Register("flashing", () => _flash != null && _flash.IsFlashing);
        GameProbe.Register("stopActive", () => HitStop.Active);
        GameProbe.Ready("inputSource", () => RunInputSource.On(_runner) != null);
        GameProbe.Ready("feedback", () => _feedback != null && _feedback.Find("hit") != null);
    }

    [TearDown]
    public void TearDown()
    {
        HitStop.Clear();
        // Unconditional: a broken run leaves time dipped, and every later test would crawl.
        Time.timeScale = 1f;
        Time.captureDeltaTime = _savedCaptureDeltaTime;
        Time.fixedDeltaTime = _savedFixedDeltaTime;
        foreach (UnityEngine.Object o in _made) if (o != null) UnityEngine.Object.Destroy(o);
        _made.Clear();
        Feedback.ResetBudget();
        GameProbe.Reset();
    }

    // ---------------------------------------------------------------------------- the hit

    [UnityTest]
    public IEnumerator Hit_DipsTime_Flashes_AndBothComeBack()
    {
        yield return WaitReady();

        using (var journey = Open("gate-room-hit"))
        {
            yield return SampleForUnscaled(journey, 0.05f);
            Assert.AreEqual(1f, Time.timeScale, "time is not at 1 before the hit");
            Assert.IsFalse(_runnerRenderer.HasPropertyBlock(), "the runner starts with a property block; the flash assertion would prove nothing");

            _input.Tap(RunButton.Launch);
            journey.Milestone("pressed");
            yield return SampleUntil(journey, () => _run.Hits == 1, 2f);
            float hitAt = Time.unscaledTime;
            journey.Milestone("hit");

            Assert.Less(Time.timeScale, 1f, "the hit row has a time channel and time did not dip");
            Assert.IsTrue(_flash.IsFlashing, "the hit row has a flash channel and the runner is not flashing");
            var block = new MaterialPropertyBlock();
            _runnerRenderer.GetPropertyBlock(block);
            Assert.AreEqual(Color.white, block.GetColor(_flash.PropertyIdFor(_runnerRenderer)), "the flash did not write its colour");

            yield return SampleUntil(journey, () => Time.unscaledTime >= hitAt + StopSeconds + 2f * Slack, 3f);
            journey.Milestone("after");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.AreEqual(1, _input.Sent(RunButton.Launch), "the script pressed once");
            Assert.AreEqual(1, _run.Hits, "one press, one hit");
            AssertRestored(samples, hitAt, StopSeconds, 1f);
            Assert.IsFalse(_flash.IsFlashing, "the flash is still showing " + (2f * Slack).ToString("F2") + " s after it should have ended");
            Assert.IsFalse(_runnerRenderer.HasPropertyBlock(), "the flash left a property block on the runner: its colour is back and its batching is not");
            TestContext.WriteLine("samples=" + samples.Count + " timeline=" + journey.TimelinePath);
        }
    }

    // --------------------------------------------------------------------------- the stop

    [UnityTest]
    public IEnumerator OverlappingStops_EndWithTheLast_AndRestoreOnce()
    {
        yield return WaitReady();

        using (var journey = Open("gate-room-overlap"))
        {
            GameObject first = Make("Sentry A"), second = Make("Sentry B");
            float startedAt = Time.unscaledTime;
            Stop(first, StopSeconds);
            journey.Milestone("first");
            yield return SampleUntil(journey, () => Time.unscaledTime >= startedAt + 0.05f, 2f);
            float secondAt = Time.unscaledTime;
            Stop(second, StopSeconds);
            journey.Milestone("second");

            // The stop as a whole runs from the first request to the end of the second.
            float total = secondAt - startedAt + StopSeconds;
            yield return SampleUntil(journey, () => Time.unscaledTime >= startedAt + total + 2f * Slack, 3f);

            List<ProbeSnapshot> samples = journey.Captured;
            TestContext.WriteLine("total=" + total.ToString("F3") + " samples=" + samples.Count + " timeline=" + journey.TimelinePath);

            // Not early: the first request ending must not end the second one's stop.
            var early = JourneyAsserts.Never(samples,
                s => s.ut > startedAt && s.ut < startedAt + total - Early && s.timeScale >= 1f, "restored-early");
            Assert.IsEmpty(early, JourneyAsserts.Describe(early));
            AssertRestored(samples, startedAt, total, 1f);
        }
    }

    [UnityTest]
    public IEnumerator RequesterDestroyedMidStop_TimeStillComesBack()
    {
        yield return WaitReady();

        using (var journey = Open("gate-room-destroyed"))
        {
            GameObject hazard = Make("Hazard");
            float startedAt = Time.unscaledTime;
            Stop(hazard, StopSeconds);
            journey.Milestone("requested");
            yield return SampleUntil(journey, () => Time.unscaledTime >= startedAt + 0.03f, 2f);
            Assert.Less(Time.timeScale, 1f, "time did not dip");

            // The hit that froze the game is usually the hit that removes what was hit.
            UnityEngine.Object.Destroy(hazard);
            journey.Milestone("destroyed");
            yield return SampleUntil(journey, () => Time.unscaledTime >= startedAt + StopSeconds + 2f * Slack, 3f);

            AssertRestored(journey.Captured, startedAt, StopSeconds, 1f);
        }
    }

    [UnityTest]
    public IEnumerator Stop_InsideSlowMotion_ReturnsToTheSlowMotion()
    {
        yield return WaitReady();

        using (var journey = Open("gate-room-slow"))
        {
            Time.timeScale = 0.5f;                       // a slow field the runner is standing in
            yield return SampleForUnscaled(journey, 0.03f);
            float startedAt = Time.unscaledTime;
            Stop(Make("Sentry"), StopSeconds);
            Assert.Less(Time.timeScale, 0.5f, "time did not dip under the slow motion");
            yield return SampleUntil(journey, () => Time.unscaledTime >= startedAt + StopSeconds + 2f * Slack, 3f);

            AssertRestored(journey.Captured, startedAt, StopSeconds, 0.5f);
        }
    }

    // -------------------------------------------------------------------------- the flash

    [UnityTest]
    public IEnumerator OverlappingFlashes_ReturnTheOriginalLook()
    {
        yield return WaitReady();

        // A second cube that already carries a per-instance tint, and a sprite with its own colour.
        GameObject tinted = GameObject.CreatePrimitive(PrimitiveType.Cube);
        tinted.name = "Sentry";
        _made.Add(tinted);
        tinted.transform.position = new Vector3(1.3f, 0.5f, 4f);
        var tintedRenderer = tinted.GetComponent<MeshRenderer>();
        var tintedFlash = tinted.AddComponent<RendererFlash>();
        tintedFlash.Collect();
        int id = tintedFlash.PropertyIdFor(tintedRenderer);
        var tint = new MaterialPropertyBlock();
        tint.SetColor(id, Color.green);
        tintedRenderer.SetPropertyBlock(tint);

        GameObject pickup = Make("Pickup");
        var sprite = pickup.AddComponent<SpriteRenderer>();
        var spriteColour = new Color(0.5f, 0.6f, 0.7f, 1f);
        sprite.color = spriteColour;
        var spriteFlash = pickup.AddComponent<RendererFlash>();
        spriteFlash.mode = FlashMode.SpriteTint;
        spriteFlash.Collect();

        using (var journey = Open("gate-room-flash"))
        {
            float startedAt = Time.unscaledTime;
            FlashAll(tintedRenderer, tintedFlash, sprite, spriteFlash, id);
            journey.Milestone("first");
            yield return SampleUntil(journey, () => Time.unscaledTime >= startedAt + FlashSeconds * 0.5f, 2f);

            var read = new MaterialPropertyBlock();
            tintedRenderer.GetPropertyBlock(read);
            Assert.AreEqual(Color.white, read.GetColor(id), "the flash is not showing on the tinted cube");
            Assert.AreEqual(Color.white, sprite.color, "the flash is not showing on the sprite");

            // Again while the first is showing — a second hit inside the first one's flash.
            float secondAt = Time.unscaledTime;
            FlashAll(tintedRenderer, tintedFlash, sprite, spriteFlash, id);
            journey.Milestone("second");
            yield return SampleUntil(journey, () => Time.unscaledTime >= secondAt + FlashSeconds + 2f * Slack, 3f);

            Assert.IsFalse(_runnerRenderer.HasPropertyBlock(), "the runner kept a property block after the flash");
            tintedRenderer.GetPropertyBlock(read);
            Assert.AreEqual(Color.green, read.GetColor(id), "the tinted cube came back " + read.GetColor(id) + ", not the tint it had");
            Assert.AreEqual(spriteColour, sprite.color, "the sprite came back " + sprite.color + ", not the colour it had");
        }
    }

    // ------------------------------------------------------------------------ the pickups

    [UnityTest]
    public IEnumerator ThirtyPickups_StartNoMoreSoundsThanTheVoiceCap()
    {
        yield return WaitReady();

        using (var journey = Open("gate-room-pickups"))
        {
            _input.SetMove(Vector2.up);                  // up the lane
            journey.Milestone("run");
            yield return SampleUntil(journey, () => _run.Collected == Pickups, 5f);
            _input.SetMove(Vector2.zero);
            journey.Milestone("collected");
            yield return SampleForUnscaled(journey, 0.05f);

            float window = _run.LastPickupAt - _run.FirstPickupAt;
            TestContext.WriteLine("pickups=" + _run.Collected + " window=" + window.ToString("F3") + " requested=" + _sfx.Requested +
                                  " played=" + _sfx.Played + " dropped=" + _sfx.Dropped + " timeline=" + journey.TimelinePath);

            Assert.LessOrEqual(window, 0.1f + 1e-3f, "the thirty pickups took " + window.ToString("F3") + " s of game time: the sweep is not the burst this test is about");
            Assert.AreEqual(Pickups, _sfx.Requested, "every pickup asks for its sound; the player decides");
            Assert.AreEqual(0, _sfx.Unknown, "an event name did not resolve");
            Assert.Greater(_sfx.Played, 0, "no pickup sounded at all");
            Assert.LessOrEqual(_sfx.Played, VoiceCap, _sfx.Played + " sounds started for thirty pickups; the voice cap is " + VoiceCap);
            Assert.AreEqual(Pickups - _sfx.Played, _sfx.Dropped, "requests that neither played nor were counted as dropped");

            var over = JourneyAsserts.Never(journey.Captured, s => s.CountOf("sfxPlayed") > VoiceCap, "voice-cap");
            Assert.IsEmpty(over, JourneyAsserts.Describe(over));
        }
    }

    // ---------------------------------------------------------------------------- helpers

    // The guarded behaviour and, under the break switch, what it replaces.
    static void Stop(GameObject requester, float seconds)
    {
        if (Break == "restore" || Break == "1") requester.AddComponent<FeelJourneyNaiveStop>().Begin(seconds, 0.05f);
        else HitStop.Request(seconds, 0.05f);
    }

    void FlashAll(MeshRenderer tintedRenderer, RendererFlash tintedFlash, SpriteRenderer sprite, RendererFlash spriteFlash, int id)
    {
        if (Break == "flash")
        {
            _runner.AddComponent<FeelJourneyNaiveFlash>().Begin(_runnerRenderer, null, id, FlashSeconds);
            tintedRenderer.gameObject.AddComponent<FeelJourneyNaiveFlash>().Begin(tintedRenderer, null, id, FlashSeconds);
            sprite.gameObject.AddComponent<FeelJourneyNaiveFlash>().Begin(null, sprite, id, FlashSeconds);
            return;
        }
        _flash.Flash(Color.white, FlashSeconds);
        tintedFlash.Flash(Color.white, FlashSeconds);
        spriteFlash.Flash(Color.white, FlashSeconds);
    }

    // Time is at 'scale' on every sample later than the window plus the slack, and on the last.
    static void AssertRestored(IList<ProbeSnapshot> samples, float startedAt, float window, float scale)
    {
        Assert.IsNotEmpty(samples, "the journey recorded nothing");
        var late = JourneyAsserts.Never(samples,
            s => s.ut > startedAt + window + Slack && Mathf.Abs(s.timeScale - scale) > 1e-4f, "restored-inside-the-window");
        Assert.IsEmpty(late, "requested " + window.ToString("F2") + " s, time not back at " + scale.ToString("F2") + " within " +
                             (window + Slack).ToString("F2") + " s — " + JourneyAsserts.Describe(late));
        Assert.AreEqual(scale, Time.timeScale, 1e-4f, "time ended the journey at " + Time.timeScale.ToString("F2"));
    }

    IEnumerator WaitReady()
    {
        yield return null;                                   // Awake and OnEnable have run
        float waitedFrom = Time.realtimeSinceStartup;
        while (!GameProbe.AllReady)
        {
            if (Time.realtimeSinceStartup - waitedFrom > 10f)
                Assert.Fail("gate room not ready after 10 s: " + string.Join(", ", GameProbe.MissingReady()));
            yield return null;
        }
    }

    static JourneyRecorder Open(string id) => new JourneyRecorder(id, JourneyRecorder.DefaultRoot());

    // Unscaled, both of them: game time stops in a hit stop, and a wait on Time.time would wait
    // for the stop it is trying to observe.
    static IEnumerator SampleForUnscaled(JourneyRecorder journey, float seconds)
    {
        float until = Time.unscaledTime + seconds;
        while (Time.unscaledTime < until)
        {
            journey.Sample();
            yield return null;
        }
        journey.Sample();
    }

    static IEnumerator SampleUntil(JourneyRecorder journey, Func<bool> done, float timeoutUnscaled)
    {
        float from = Time.realtimeSinceStartup;
        while (!done())
        {
            if (Time.realtimeSinceStartup - from > timeoutUnscaled + 10f)
                Assert.Fail("timed out waiting on the journey; time scale is " + Time.timeScale.ToString("F2"));
            journey.Sample();
            yield return null;
        }
        journey.Sample();
    }

    GameObject Make(string name)
    {
        var go = new GameObject(name);
        _made.Add(go);
        return go;
    }
}

/// <summary>
/// The smallest runner the journey can drive: it reads RunInput through the source on its own
/// object, runs up the lane, collects what it passes and takes a hit on Launch. Gameplay raises
/// the event; the Feedback row decides everything the player perceives.
/// </summary>
public sealed class FeelJourneyRunner : MonoBehaviour
{
    public Feedback feedback;
    public float speed = 60f;
    public float[] pickupZ = new float[0];

    public int Hits { get; private set; }
    public int Collected { get; private set; }
    public float FirstPickupAt { get; private set; }
    public float LastPickupAt { get; private set; }

    IRunInputSource _input;
    int _next;

    void FixedUpdate()
    {
        if (!RunInputSource.Resolve(gameObject, ref _input)) return;
        RunInput levels = _input.Peek();

        Vector3 p = transform.position;
        p.z += levels.move.y * speed * Time.fixedDeltaTime;
        transform.position = p;

        while (_next < pickupZ.Length && pickupZ[_next] <= p.z)
        {
            if (Collected == 0) FirstPickupAt = Time.time;
            LastPickupAt = Time.time;
            Collected++;
            feedback.Play("pickup", new Vector3(p.x, p.y, pickupZ[_next]), Vector3.zero);
            _next++;
        }

        if (_input.TryUse(RunButton.Launch))
        {
            Hits++;
            feedback.Play("hit", p, Vector3.back);
        }
    }
}

/// <summary>
/// FEEL_JOURNEY_BREAK=restore. The hit stop written on the thing that was hit: it remembers
/// the scale it found, and puts it back from a coroutine that dies with the object.
/// </summary>
public sealed class FeelJourneyNaiveStop : MonoBehaviour
{
    public void Begin(float seconds, float scale) => StartCoroutine(Run(seconds, scale));

    IEnumerator Run(float seconds, float scale)
    {
        float before = Time.timeScale;              // during another stop, this is that stop's dip
        Time.timeScale = scale;
        float until = Time.unscaledTime + seconds;
        while (Time.unscaledTime < until) yield return null;
        Time.timeScale = before;
    }
}

/// <summary>
/// FEEL_JOURNEY_BREAK=flash. The flash that reads "the original colour" every time it starts,
/// including while an earlier flash is showing.
/// </summary>
public sealed class FeelJourneyNaiveFlash : MonoBehaviour
{
    public void Begin(Renderer target, SpriteRenderer sprite, int propertyId, float seconds)
        => StartCoroutine(Run(target, sprite, propertyId, seconds));

    IEnumerator Run(Renderer target, SpriteRenderer sprite, int propertyId, float seconds)
    {
        var block = new MaterialPropertyBlock();
        Color before = Color.white;
        if (sprite != null)
        {
            before = sprite.color;
            sprite.color = Color.white;
        }
        else
        {
            target.GetPropertyBlock(block);
            if (block.HasColor(propertyId)) before = block.GetColor(propertyId);
            block.SetColor(propertyId, Color.white);
            target.SetPropertyBlock(block);
        }

        float until = Time.unscaledTime + seconds;
        while (Time.unscaledTime < until) yield return null;

        if (sprite != null) sprite.color = before;
        else
        {
            block.SetColor(propertyId, before);
            target.SetPropertyBlock(block);
        }
    }
}
