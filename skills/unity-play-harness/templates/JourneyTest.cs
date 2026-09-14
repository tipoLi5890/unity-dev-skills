using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

/// <summary>
/// A journey test: enter a situation, wait on its readiness set, drive the game through the
/// project's own input funnel, sample the probe into a timeline, then assert invariants over
/// the whole recording rather than over one frame.
///
/// Copy into a PlayMode test assembly (an asmdef with "Tests" in it, referencing
/// UnityEngine.TestRunner and UnityEditor.TestRunner, and the assembly holding GameProbe).
///
/// Run it:
///   "$UNITY" -projectPath . -runTests -testPlatform PlayMode \
///     -testFilter ApproachGateJourney -testResults /tmp/results.xml -logFile /tmp/tests.log
///   python3 scripts/journey_report.py --after /tmp/journeys/approach-gate/timeline.jsonl \
///     --max speed:12 --ready-before arrival --monotonic state:Idle,Launched,Approach,AtGate
///
/// Windowed (no -batchmode) also writes the milestone PNGs; batch writes the timeline only.
/// </summary>
public class ApproachGateJourney
{
    const string ScenePath = "Assets/Scenes/Run.unity";   // replace with your game's scene
    static string JourneyDir => Path.Combine(Application.persistentDataPath, "journeys");

    [SetUp]
    public void SetUp()
    {
        // PlayerPrefs and persistent data survive between PlayMode runs, which is how the same
        // test produces two different timelines on two machines.
        PlayerPrefs.DeleteAll();
        PlayerPrefs.Save();
        Situations.ClearParams();
        GameProbe.Reset();
        if (Directory.Exists(JourneyDir)) Directory.Delete(JourneyDir, true);
    }

    [UnityTest]
    public IEnumerator ApproachGate_ArrivesReadyAndUnderSpeed()
    {
        yield return LoadScene();

        Situations.SetParam("angle", 80f);
        SituationHandle situation = Situations.Enter("approach-gate");
        yield return situation.WaitUntilReady();          // throws, naming what never arrived

        using (var journey = new JourneyRecorder("approach-gate", JourneyDir))
        {
            // Drive through the same funnel the gamepad reaches. Calling a movement method
            // directly would skip the code the complaint is actually about.
            var input = Object.FindAnyObjectByType<RunInputFunnel>();
            Assert.IsNotNull(input, "no input funnel in the scene — the drive loop would sample a "
                                    + "game nobody is playing, and every assertion would pass");
            input.PressLaunch();

            bool arrived = false;
            while (journey.ElapsedUnscaled < 14f && !arrived)
            {
                ProbeSnapshot s = journey.Sample();
                if (s != null && s.Number("gateDist", 999f) < 0.5f) arrived = true;
                yield return null;                       // sample in Update, not at end of frame
            }

            int shot = journey.Milestone("arrival");
            yield return Capture(journey.ShotPath(shot, "arrival"), "arrival");

            List<ProbeSnapshot> samples = journey.Captured;

            Assert.IsNotEmpty(samples, "the journey recorded nothing — did the drive loop run?");
            Assert.IsTrue(arrived, "never reached the gate in 14 s; last gateDist=" +
                          samples[samples.Count - 1].Number("gateDist", -1f));

            // 1 · readiness held for every frame inside the approach window, up to arrival
            var late = JourneyAsserts.ReadyBefore(samples, "arrival",
                                                  s => s.Number("gateDist", 999f) < 20f);
            Assert.IsEmpty(late, JourneyAsserts.Describe(late));

            // 2 · the state machine only moved forward
            var backwards = JourneyAsserts.Monotonic(samples,
                new[] { "Idle", "Launched", "Approach", "AtGate" });
            Assert.IsEmpty(backwards, JourneyAsserts.Describe(backwards));

            // 3 · entry speed stayed inside the budget in the last 2 units before the gate
            var tooFast = JourneyAsserts.Never(samples,
                s => s.Number("gateDist", 999f) < 2f && s.speed > 12f, "entry-speed");
            Assert.IsEmpty(tooFast, JourneyAsserts.Describe(tooFast));

            // 4 · the runner was never inside the lane walls
            var inside = JourneyAsserts.NeverInside(samples, LayerMask.GetMask("Track"), 0.25f);
            Assert.IsEmpty(inside, JourneyAsserts.Describe(inside));

            // Print what the assertions used, so the numbers keep saying why it passed.
            float maxEntry = 0f;
            foreach (ProbeSnapshot s in samples)
                if (s.Number("gateDist", 999f) < 2f && s.speed > maxEntry) maxEntry = s.speed;
            TestContext.WriteLine($"samples={samples.Count} maxEntrySpeed={maxEntry:F2} " +
                                  $"timeline={journey.TimelinePath}");
        }
    }

    static IEnumerator LoadScene()
    {
#if UNITY_EDITOR
        // Single, never Additive: an additive load leaves the previous test's objects alive and
        // the readiness members then read true for the wrong scene. A scene missing from Build
        // Settings still loads by asset path from a PlayMode test.
        yield return UnityEditor.SceneManagement.EditorSceneManager.LoadSceneAsyncInPlayMode(
            ScenePath, new LoadSceneParameters(LoadSceneMode.Single));
#else
        yield return SceneManager.LoadSceneAsync("Run", LoadSceneMode.Single);
#endif
        yield return null;   // one frame so every Awake has registered its situations
    }

    /// <summary>
    /// Screenshot at a milestone. The state goes in the log next to the file name, so a capture
    /// that photographed the wrong moment cannot pass unnoticed — and a batch run bails out of
    /// the capture rather than skipping the test, so it still verifies state and writes no PNG.
    ///
    /// Capture resolution, settle time and how to read the pixels afterwards belong to
    /// `unity-debug` → `reference/visual-checks.md`; this is the same coroutine, called at a
    /// milestone so the image and the timeline row describe the same frame.
    /// </summary>
    static IEnumerator Capture(string path, string label, float settle = 0.6f)
    {
        yield return new WaitForSeconds(settle);          // same wait in both modes, so states match
        Debug.Log($"[SHOT] {label} state={GameProbe.Snapshot().state} path={path}");
        if (Application.isBatchMode) yield break;         // no end of frame, and a fake 640x480 target
        yield return new WaitForEndOfFrame();
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        ScreenCapture.CaptureScreenshot(path);
        yield return null;
    }
}

/// <summary>
/// The project's input funnel — the one place a gamepad, a keyboard and a test all meet. Three
/// physical buttons, three commands. It is sketched here so the test above reads as a complete
/// example; in a real project it lives in the runtime assembly with the rest of the game, and
/// this class goes away. The point is that the test presses the same thing the player does.
/// </summary>
public sealed class RunInputFunnel : MonoBehaviour
{
    public RunController run;

    public void PressLaunch() { run.Launch(); }
    public void PressLaneLeft() { run.ShiftLane(-1); }
    public void PressLaneRight() { run.ShiftLane(+1); }
}
