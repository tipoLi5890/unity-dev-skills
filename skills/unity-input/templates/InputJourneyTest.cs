using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

/// <summary>
/// The input journey: a press made in Update is used by FixedUpdate exactly once — never lost
/// when a frame has no fixed step, never doubled when a frame has four — and a buffered press
/// fires inside its window and not after it.
///
/// Copy into a PlayMode test assembly that references UnityEngine.TestRunner, the assembly
/// holding GameProbe / JourneyRecorder (skill unity-play-harness) and the one holding
/// RunInput.cs / ScriptedRunInput.cs. It needs no scene asset and no Input System package: it
/// builds a host object in SetUp and drives it through ScriptedRunInput, which goes through the
/// same latch the device reader does.
///
/// Run it:
///   "$UNITY" -batchmode -projectPath . -runTests -testPlatform PlayMode \
///     -testFilter InputBufferJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
///   python3 scripts/journey_report.py --max launches:10 \
///     --after "$JOURNEY_OUT/input-fast-fixed/timeline.jsonl"
///   (journey_report.py ships with skill unity-play-harness; timelines go to $JOURNEY_OUT, or
///   to <persistentDataPath>/journeys without it, and the test prints the path)
///
/// To see the gate fail, make LaunchConsumer read Peek().launchPressed instead of TryUse — the
/// fast case then reports a double-consume on the first tap.
/// </summary>
public class InputBufferJourney
{
    const float Frame = 1f / 60f;
    const int Taps = 10;
    // 9 frames = 0.15 s: longer than the 0.12 s buffer and than the slowest fixed step below, so
    // two taps can never collapse into one pending press.
    const int Spacing = 9;

    static string JourneyDir => JourneyRecorder.DefaultRoot();

    float _savedFixedDelta;
    float _savedCaptureDelta;
    GameObject _host;
    ScriptedRunInput _input;
    LaunchConsumer _consumer;

    [SetUp]
    public void SetUp()
    {
        // No PlayerPrefs wipe: nothing here reads them, and saved rebinds live there.
        GameProbe.Reset();
        // No wipe of JourneyDir: JourneyRecorder clears its own journey's folder, and the three
        // tests here (and every other journey in the project) keep their timelines.

        _savedFixedDelta = Time.fixedDeltaTime;
        _savedCaptureDelta = Time.captureDeltaTime;
        // Every rendered frame advances game time by exactly one 60th, so the ratio of fixed
        // steps to frames is the one the test asks for and not whatever the machine managed.
        Time.captureDeltaTime = Frame;

        _host = new GameObject("InputJourneyHost");
        _input = _host.AddComponent<ScriptedRunInput>();
        _consumer = _host.AddComponent<LaunchConsumer>();

        GameProbe.SetState(() => _consumer.canLaunch ? "Grounded" : "Airborne");
        GameProbe.Ready("inputSource", () => RunInputSource.On(_host) != null);
        GameProbe.Count("presses", () => _input.Sent(RunButton.Launch));
        GameProbe.Count("launches", () => _consumer.launches);
        GameProbe.Count("polled", () => _consumer.polled);
    }

    [TearDown]
    public void TearDown()
    {
        Time.fixedDeltaTime = _savedFixedDelta;
        Time.captureDeltaTime = _savedCaptureDelta;
        if (_host != null) Object.Destroy(_host);
        GameProbe.Reset();
    }

    [UnityTest]
    public IEnumerator Tap_IsUsedOnce_WhenFixedUpdateRunsFourTimesAFrame()
    {
        yield return DriveTaps("input-fast-fixed", Frame / 4f);
    }

    [UnityTest]
    public IEnumerator Tap_IsUsedOnce_WhenFixedUpdateSkipsFrames()
    {
        yield return DriveTaps("input-slow-fixed", Frame * 6f);
    }

    IEnumerator DriveTaps(string journeyId, float fixedDelta)
    {
        Time.fixedDeltaTime = fixedDelta;
        yield return null;                                   // one frame so Awake/OnEnable have run
        Assert.IsTrue(GameProbe.AllReady, "not ready: " + string.Join(", ", GameProbe.MissingReady()));

        using (var journey = new JourneyRecorder(journeyId, JourneyDir))
        {
            for (int i = 0; i < Taps; i++) _input.TapIn(1 + i * Spacing, RunButton.Launch);

            int frames = Taps * Spacing + 12;                // the tail lets the last tap be used
            for (int f = 0; f < frames; f++)
            {
                journey.Sample();
                yield return null;                           // sample in Update, not at end of frame
            }
            journey.Milestone("done");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing — did the drive loop run?");
            Assert.AreEqual(0, _input.Queued, "taps still queued: the drive loop ended early");
            Assert.AreEqual(Taps, _input.Sent(RunButton.Launch), "the script did not send every tap");

            // 1 · never twice: at no sample has gameplay launched more often than it was asked to
            var doubled = JourneyAsserts.Never(samples,
                s => s.CountOf("launches") > s.CountOf("presses"), "double-consume");
            Assert.IsEmpty(doubled, JourneyAsserts.Describe(doubled));

            // 2 · never lost: at no sample is more than one press outstanding
            var dropped = JourneyAsserts.Never(samples,
                s => s.CountOf("presses") - s.CountOf("launches") > 1, "lost-press");
            Assert.IsEmpty(dropped, JourneyAsserts.Describe(dropped));

            // 3 · exactly once, in total
            Assert.AreEqual(Taps, _consumer.launches, "launches != presses at the end of the run");

            // What a FixedUpdate poll of the device would have counted on the same run: it prints
            // above the tap count in the fast case and below it in the slow one.
            TestContext.WriteLine($"samples={samples.Count} presses={Taps} launches={_consumer.launches} " +
                                  $"polled={_consumer.polled} fixedDelta={fixedDelta:F4} " +
                                  $"timeline={journey.TimelinePath}");
        }
    }

    [UnityTest]
    public IEnumerator BufferedPress_FiresOnceInsideTheWindow_AndNeverAfterIt()
    {
        Time.fixedDeltaTime = 0.02f;
        _input.bufferSeconds = 0.12f;
        _consumer.canLaunch = false;                         // airborne: the press has to wait
        yield return null;

        using (var journey = new JourneyRecorder("input-buffer", JourneyDir))
        {
            // Early press, landing 0.05 s later — inside the buffer.
            _input.Tap(RunButton.Launch);
            yield return SampleFor(journey, 0.05f);
            Assert.AreEqual(0, _consumer.launches, "launched while airborne");
            _consumer.canLaunch = true;
            yield return SampleFor(journey, 0.10f);
            journey.Milestone("landed-inside");
            Assert.AreEqual(1, _consumer.launches, "a press 0.05 s before landing was not honoured");

            // Early press, landing 0.30 s later — the press is stale and must not fire.
            _consumer.canLaunch = false;
            _input.Tap(RunButton.Launch);
            yield return SampleFor(journey, 0.30f);
            _consumer.canLaunch = true;
            yield return SampleFor(journey, 0.10f);
            journey.Milestone("landed-after");
            Assert.AreEqual(1, _consumer.launches, "a press 0.30 s before landing fired on landing");

            List<ProbeSnapshot> samples = journey.Captured;
            Assert.IsNotEmpty(samples, "the journey recorded nothing");

            var doubled = JourneyAsserts.Never(samples,
                s => s.CountOf("launches") > s.CountOf("presses"), "double-consume");
            Assert.IsEmpty(doubled, JourneyAsserts.Describe(doubled));

            var stale = JourneyAsserts.Never(samples, s => s.CountOf("launches") > 1, "stale-press");
            Assert.IsEmpty(stale, JourneyAsserts.Describe(stale));

            TestContext.WriteLine($"samples={samples.Count} presses={_input.Sent(RunButton.Launch)} " +
                                  $"launches={_consumer.launches} buffer={_input.bufferSeconds:F2} " +
                                  $"timeline={journey.TimelinePath}");
        }
    }

    // Waits on game time, which captureDeltaTime makes exact; a frame count would silently change
    // meaning the day someone changes Frame.
    static IEnumerator SampleFor(JourneyRecorder journey, float seconds)
    {
        float until = Time.time + seconds;
        while (Time.time < until)
        {
            journey.Sample();
            yield return null;
        }
    }
}

/// <summary>
/// The reading half of a RunController, cut down to the one decision under test. It is sketched
/// here so the journey is a complete example; in a real project the test adds ScriptedRunInput to
/// the runner, disables its RunInputReader, and the game's own controller does the consuming.
/// </summary>
public sealed class LaunchConsumer : MonoBehaviour
{
    public bool canLaunch = true;
    public int launches;
    /// <summary>What polling the device in FixedUpdate would have counted. Printed, never asserted.</summary>
    public int polled;

    IRunInputSource _source;
    ScriptedRunInput _scripted;

    void Awake() => _scripted = GetComponent<ScriptedRunInput>();

    void FixedUpdate()
    {
        // Resolve, not a cached field from Awake: the enabled source may have been swapped.
        if (!RunInputSource.Resolve(gameObject, ref _source)) return;
        if (_scripted != null && _scripted.RawPressedThisFrame(RunButton.Launch)) polled++;
        // The condition comes first: a press that cannot be acted on stays pending for the buffer.
        if (canLaunch && _source.TryUse(RunButton.Launch)) launches++;
    }
}
