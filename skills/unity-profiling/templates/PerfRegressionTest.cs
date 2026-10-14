// PerfRegressionTest.cs — a regression gate over the courier run's hazard lane: enter the
// situation, measure 120 frames and the hazard system's own ProfilerMarker, and fail when either
// median rises past the baseline recorded for this instrument plus a tolerance.
//
// Copy into a PlayMode test assembly: an asmdef that references UnityEngine.TestRunner,
// Unity.PerformanceTesting and the Runtime assembly holding GameProbe.cs and Situations.cs
// (unity-play-harness → resources/) with the game's situation registration
// (unity-play-harness → templates/CourierSituations.cs is the courier one).
//
// REQUIRES com.unity.test-framework.performance in Packages/manifest.json. Every call here exists
// in package 3.4; on another version read
// Library/PackageCache/com.unity.test-framework.performance*/Runtime/Measure.cs before trusting one.
//
// The game owns the marker, inside the hazard system's per-frame work:
//   static readonly ProfilerMarker s_HazardUpdate = new ProfilerMarker("Courier.HazardUpdate");
//   void Update() { using (s_HazardUpdate.Auto()) { /* move hazards, test the sentry */ } }
//
// A perf test owns the machine: no other Editor, build or test lane while it runs.
//   pgrep -fl "Contents/MacOS/Unity( -|$)"              # must print nothing
//   mkdir -p /tmp/perf && rm -f /tmp/perf/results.xml
//   "$UNITY" -projectPath . -batchmode -nographics -runTests -testPlatform PlayMode \
//     -testCategory Perf -testResults /tmp/perf/results.xml -logFile /tmp/perf/tests.log
//   grep '\[PERFGATE\]' /tmp/perf/tests.log
// Every other run of the suite leaves the category out: -testCategory '!Perf' (single quotes).
//
// The first run on a new instrument does not judge: it ends Inconclusive, and its [PERFGATE] line
// ends in record=, the Baselines row to paste. Inconclusive is not green.
//
// Once a row is recorded, prove the gate can fail before trusting a pass (a break run never records):
//   PERF_GATE_BREAK=stall   4 ms of busy work in every frame: the frame-time gate must turn red
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using NUnit.Framework;
using Unity.PerformanceTesting;
using Unity.Profiling;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Stopwatch = System.Diagnostics.Stopwatch;

[Category("Perf")]
public class HazardLanePerf
{
    const string ScenePath = "Assets/Scenes/Run.unity";        // replace with your game's scene
    const string SituationId = "hazard-lane";
    const string HazardMarker = "Courier.HazardUpdate";        // the game's own ProfilerMarker
    const int WarmupFrames = 30;                               // entering the lane is starting, not playing
    const int MeasureFrames = 120;
    const int MinSamples = 60;                                 // a median of fewer frames is not a gate

    // limit = baseline + max(baseline × RelTolerance, floor). RelTolerance comes from the gate
    // machine's own run-to-run spread, not from a wish: reference/perf-tests.md has the method. The
    // floors keep a 0.3 ms marker from failing on a 0.04 ms wobble.
    const double RelTolerance = 0.15;
    const double FrameFloorMs = 0.25;
    const double MarkerFloorMs = 0.05;

    /// <summary>
    /// One row per instrument: run mode, processor and editor version. A row is recorded, never
    /// typed — paste the record= text a first run prints, and commit it alone with the numbers in
    /// the message. An editor upgrade or a new gate machine is a new instrument and a new row.
    /// </summary>
    static readonly Baseline[] Baselines =
    {
        // The shape of a row. Its machine field matches no processor, so this file never judges
        // against numbers that were not recorded on your machine.
        new Baseline("batchmode-nographics", "<processorType>", "<unityVersion>", frameMs: 2.40, markerMs: 0.31),
    };

    static string Break => System.Environment.GetEnvironmentVariable("PERF_GATE_BREAK") ?? "";

    int _savedVsync;
    int _savedTargetFrameRate;
    GameObject _stall;

    [SetUp]
    public void SetUp()
    {
        // No PlayerPrefs.DeleteAll() here, nor in any test that runs before this one: in the Editor
        // the package keeps its run metadata in PlayerPrefs, written once per run and read back
        // when a perf test ends. Delete the game's keys by name.
        Situations.ClearParams();
        GameProbe.Reset();

        // A frame-time floor at 16.67 or 8.33 ms is the display, and a regression hides under it.
        // Restored in TearDown; a run that dies first can leave it changed — git status after.
        _savedVsync = QualitySettings.vSyncCount;
        _savedTargetFrameRate = Application.targetFrameRate;
        QualitySettings.vSyncCount = 0;
        Application.targetFrameRate = -1;
    }

    [TearDown]
    public void TearDown()
    {
        QualitySettings.vSyncCount = _savedVsync;
        Application.targetFrameRate = _savedTargetFrameRate;
        if (_stall != null) Object.Destroy(_stall);
        GameProbe.Reset();
    }

    [UnityTest, Performance, Version("1")]                      // bump Version and re-record together
    public IEnumerator HazardLane_MediansStayInsideBaseline()
    {
        yield return LoadScene();

        Situations.SetParam("cold", false);                     // a warm lane: playing, not streaming in
        SituationHandle situation = Situations.Enter(SituationId);
        yield return situation.WaitUntilReady();                 // throws, naming what never arrived

        if (Break == "stall") _stall = new GameObject("~PerfStall", typeof(PerfStall));

        // The package creates its marker recorder when measuring starts, and logs an error for a
        // name that does not exist yet. A few frames of the lane create it; checking here turns a
        // wrong name into a harness message instead of a perf number.
        for (int i = 0; i < 3; i++) yield return null;
        Assert.IsTrue(MarkerExists(HazardMarker), "HARNESS: no ProfilerMarker named " + HazardMarker +
            " after three frames of " + SituationId + " — declare it in the hazard system (see the header) or fix the name");

        ProbeSnapshot before = GameProbe.Snapshot();

        yield return Measure.Frames()
            .WarmupCount(WarmupFrames)
            .MeasurementCount(MeasureFrames)
            .SampleGroup(new SampleGroup(SituationId + ".frame", SampleUnit.Millisecond))
            .ProfilerMarkers(new SampleGroup(HazardMarker, SampleUnit.Millisecond))
            .Run();

        ProbeSnapshot after = GameProbe.Snapshot();

        // ---- the harness first: did these frames measure the lane at all?
        List<double> frames = SamplesOf(SituationId + ".frame");
        List<double> marker = SamplesOf(HazardMarker);
        Assert.GreaterOrEqual(frames.Count, MinSamples, "HARNESS: " + frames.Count + " frame samples, asked for " +
            MeasureFrames + " — WarmupCount without MeasurementCount, or a measurement-count override on the command line");
        Assert.IsTrue(AnyNonZero(marker), "HARNESS: " + HazardMarker + " read zero on all " + marker.Count +
            " frames — the hazard system never ran, so nothing was measured");
        Assert.Greater(before.CountOf("hazards"), 0, "HARNESS: no hazards when measuring began — an empty lane is cheap");
        Assert.Greater(after.CountOf("hazards"), 0, "HARNESS: no hazards when measuring ended");
        // replace with your game's terminal states: frames after the run stopped measure a menu
        Assert.IsFalse(after.state == "Crashed" || after.state == "Done",
            "HARNESS: the run ended (" + after.state + ") inside the window; the frames measured a stopped game");

        // ---- the gate: medians against this instrument's row
        Instrument here = Instrument.Detect();
        double frameMed = Median(frames);
        double markerMed = Median(marker);
        string record = here.Record(frameMed, markerMed);
        Baseline b = Find(here);

        if (b == null && Break.Length > 0)
        {
            // A broken run's medians carry the break. Offering them as a row would bake it in.
            Report(Line(here, frames.Count, frameMed, double.NaN, markerMed, double.NaN, "no-baseline"));
            Assert.Fail("HARNESS: a break run cannot record a baseline for " + here + "; record first, then break");
        }
        if (b == null)
        {
            Report(Line(here, frames.Count, frameMed, double.NaN, markerMed, double.NaN, "no-baseline") + " record=" + record);
            Assert.Inconclusive("no baseline for " + here + "; recorded rows: " + Rows() + ". Paste into Baselines: " + record);
            yield break;
        }

        double frameLimit = Limit(b.FrameMs, FrameFloorMs);
        double markerLimit = Limit(b.MarkerMs, MarkerFloorMs);
        bool frameOk = frameMed <= frameLimit;
        bool markerOk = markerMed <= markerLimit;
        // Faster by more than the band passes, and is a question: a lane doing less work is faster
        // too. Re-record once the work it did is confirmed the same.
        bool faster = frameMed < b.FrameMs - (frameLimit - b.FrameMs);
        string verdict = !(frameOk && markerOk) ? "REGRESSION" : faster ? "pass-faster" : "pass";
        Report(Line(here, frames.Count, frameMed, frameLimit, markerMed, markerLimit, verdict) +
               (faster && Break.Length == 0 ? " record=" + record : ""));

        Assert.IsTrue(frameOk, "frame median " + F(frameMed) + " ms > limit " + F(frameLimit) + " (baseline " +
            F(b.FrameMs) + ", n=" + frames.Count + ", " + here.Mode + ")");
        Assert.IsTrue(markerOk, HazardMarker + " median " + F(markerMed) + " ms > limit " + F(markerLimit) +
            " (baseline " + F(b.MarkerMs) + ", n=" + marker.Count + ", " + here.Mode + ")");
    }

    // ------------------------------------------------------------------------------ helpers

    static IEnumerator LoadScene()
    {
#if UNITY_EDITOR
        // Single, never Additive: the previous test's objects would otherwise be measured too.
        yield return UnityEditor.SceneManagement.EditorSceneManager.LoadSceneAsyncInPlayMode(
            ScenePath, new LoadSceneParameters(LoadSceneMode.Single));
#else
        yield return SceneManager.LoadSceneAsync("Run", LoadSceneMode.Single);
#endif
        yield return null;   // one frame so every Awake has registered its situations
    }

    /// <summary>SampleGroup.Median and the other statistics are filled in after the test body
    /// ends, so they read 0 here. The samples themselves are already there.</summary>
    static List<double> SamplesOf(string group)
    {
        SampleGroup g = PerformanceTest.GetSampleGroup(group);
        if (g != null) return g.Samples;
        var names = new List<string>();
        foreach (SampleGroup s in PerformanceTest.Active.SampleGroups) names.Add(s.Name);
        Assert.Fail("HARNESS: no sample group " + group + "; the test recorded: " + string.Join(", ", names));
        return null;
    }

    static bool MarkerExists(string name)
    {
        using (var probe = new ProfilerRecorder(name, 1, ProfilerRecorderOptions.Default))
            return probe.Valid;
    }

    static double Median(List<double> values)
    {
        var sorted = new List<double>(values);
        sorted.Sort();
        int mid = sorted.Count / 2;
        return sorted.Count % 2 == 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2.0;
    }

    static double Limit(double baseline, double floor) =>
        baseline + System.Math.Max(baseline * RelTolerance, floor);

    static bool AnyNonZero(List<double> values)
    {
        foreach (double v in values) if (v != 0.0) return true;
        return false;
    }

    static Baseline Find(Instrument here)
    {
        foreach (Baseline b in Baselines) if (b.Matches(here)) return b;
        return null;
    }

    static string Rows()
    {
        var rows = new List<string>();
        foreach (Baseline b in Baselines) rows.Add(b.Mode + " on " + b.Machine + " with " + b.Unity);
        return rows.Count == 0 ? "none" : string.Join(" | ", rows);
    }

    static string Line(Instrument here, int n, double frameMed, double frameLimit,
                       double markerMed, double markerLimit, string verdict)
    {
        return "[PERFGATE] test=" + SituationId + " mode=" + here.Mode + " n=" + n +
               " frame_med=" + F(frameMed) + " frame_limit=" + F(frameLimit) +
               " marker_med=" + F(markerMed) + " marker_limit=" + F(markerLimit) +
               " vsync=" + QualitySettings.vSyncCount + " fps_cap=" + Application.targetFrameRate +
               " break=" + (Break.Length == 0 ? "none" : Break) + " verdict=" + verdict;
    }

    // The log for grep, the results XML for whoever reads the verdict later.
    static void Report(string line)
    {
        Debug.Log(line);
        TestContext.WriteLine(line);
    }

    static string F(double v) =>
        double.IsNaN(v) ? "-" : v.ToString("0.###", CultureInfo.InvariantCulture);

    // ------------------------------------------------------------------------------ instrument

    sealed class Instrument
    {
        public string Mode, Machine, Unity;

        /// <summary>The mode names FrameSampler writes as run.mode, so a gate and a window name
        /// one instrument the same way.</summary>
        public static Instrument Detect()
        {
            bool nullGraphics = SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null;
            return new Instrument
            {
                Mode = Application.isEditor
                    ? (Application.isBatchMode ? (nullGraphics ? "batchmode-nographics" : "batchmode") : "editor-windowed")
                    : (Debug.isDebugBuild ? "player-dev" : "player-release"),
                Machine = SystemInfo.processorType,
                Unity = Application.unityVersion
            };
        }

        public string Record(double frameMs, double markerMs) =>
            "new Baseline(\"" + Mode + "\", \"" + Machine.Replace("\"", "\\\"") + "\", \"" + Unity +
            "\", frameMs: " + F(frameMs) + ", markerMs: " + F(markerMs) + "),";

        public override string ToString() => Mode + " on " + Machine + " with " + Unity;
    }

    sealed class Baseline
    {
        public readonly string Mode, Machine, Unity;
        public readonly double FrameMs, MarkerMs;

        public Baseline(string mode, string machine, string unity, double frameMs, double markerMs)
        {
            Mode = mode;
            Machine = machine;
            Unity = unity;
            FrameMs = frameMs;
            MarkerMs = markerMs;
        }

        public bool Matches(Instrument i) => Mode == i.Mode && Machine == i.Machine && Unity == i.Unity;
    }
}

/// <summary>
/// PERF_GATE_BREAK=stall: busy work in every frame, inside no marker. Under it the frame-time gate
/// must turn red; one that stays green is measuring something other than the frame. Keep the
/// stall above the tolerance band, or the break proves nothing.
/// </summary>
public sealed class PerfStall : MonoBehaviour
{
    public double milliseconds = 4.0;

    void Update()
    {
        var watch = Stopwatch.StartNew();
        while (watch.Elapsed.TotalMilliseconds < milliseconds) { }
    }
}
