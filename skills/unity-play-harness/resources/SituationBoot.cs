// SituationBoot.cs — boots a windowed or player run into a situation named on the command line
// or in PLAY_SITUATION. Lives in the same Runtime assembly as Situations.cs; it installs itself,
// so nothing has to be placed in a scene.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;

/// <summary>
/// Boots a windowed or player run straight into a situation named on the command line or in
/// the environment, with no test framework involved:
///
///   "$UNITY" -projectPath &lt;p&gt; -situation approach-gate -situation-param angle=80
///   PLAY_SITUATION=approach-gate ./Build/Game
///   ./Build/Game -situation approach-gate -screenshotDir Shots -quit
///
/// -screenshotDir DIR  once the situation is ready, one PNG of the screen:
///                     DIR/&lt;id with / as _&gt;-ready.png, logged as "[SHOT] &lt;path&gt; WxH".
///                     A -batchmode player renders nothing; run it windowed.
/// -quit               a player quits after the probe line (and the shot): 0 ready, 2 the
///                     ready set timed out, 1 an unknown id, 3 the shot could not be written.
///                     The Editor ignores Application.Quit, so this is for built players.
///
/// Installs itself after the first scene loads. Suppressed during -runTests, because a test
/// enters its own situation and two Enters race each other.
/// </summary>
public sealed class SituationBoot : MonoBehaviour
{
    /// <summary>Set true before the first scene load to keep the boot out of a run entirely.</summary>
    public static bool Suppress;

    /// <summary>The id this run was told to enter, or null.</summary>
    public static string Requested { get; private set; }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Install()
    {
        Requested = FromCommandLine() ?? Environment.GetEnvironmentVariable("PLAY_SITUATION");
        if (string.IsNullOrEmpty(Requested) || Suppress) return;
        if (IsTestRun())
        {
            Debug.Log("[SITUATION] boot suppressed: this is a test run");
            return;
        }

        // A windowed run that loses focus stops ticking, and every wait then times out for a
        // reason that has nothing to do with the game.
        Application.runInBackground = true;

        var go = new GameObject("~SituationBoot") { hideFlags = HideFlags.HideInHierarchy };
        DontDestroyOnLoad(go);
        go.AddComponent<SituationBoot>();
    }

    static string FromCommandLine()
    {
        string[] args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == "-situation") return args[i + 1];
        return null;
    }

    static bool IsTestRun()
    {
        foreach (string a in Environment.GetCommandLineArgs())
            if (a == "-runTests" || a == "-testPlatform") return true;
        return false;
    }

    IEnumerator Start()
    {
        // One frame, so every Awake that registers a situation has run.
        yield return null;

        if (!Situations.Has(Requested))
        {
            Debug.LogError("[SITUATION] unknown id=" + Requested + " registered=" +
                           string.Join(",", Situations.Ids()));
            QuitIfAsked(1);
            yield break;
        }

        SituationHandle handle = Situations.Enter(Requested);
        IEnumerator wait = handle.WaitUntilReady();
        while (true)
        {
            // C# forbids yielding inside a catch clause, so the failure leaves the try as data.
            bool moved = false;
            string timedOut = null;
            try { moved = wait.MoveNext(); }
            catch (TimeoutException e) { timedOut = e.Message; }

            if (timedOut != null)
            {
                // A boot must not throw into nothing: name the missing members and leave the
                // window up, so the moment can still be looked at and photographed.
                Debug.LogError("[SITUATION] TIMEOUT " + timedOut);
                QuitIfAsked(2);
                yield break;
            }
            if (!moved) break;
            yield return wait.Current;
        }

        GameProbe.Log("PROBE");

        int code = 0;
        string dir = ArgValue("-screenshotDir");
        if (dir != null)
        {
            yield return new WaitForEndOfFrame();
            Texture2D shot = ScreenCapture.CaptureScreenshotAsTexture();
            try
            {
                Directory.CreateDirectory(dir);
                string path = Path.Combine(dir, Requested.Replace('/', '_') + "-ready.png");
                File.WriteAllBytes(path, shot.EncodeToPNG());
                Debug.Log(string.Format(CultureInfo.InvariantCulture, "[SHOT] {0} {1}x{2}",
                                        path, shot.width, shot.height));
            }
            catch (Exception e)
            {
                Debug.LogError("[SHOT] not written: " + e.Message);
                code = 3;
            }
            finally { Destroy(shot); }
        }
        QuitIfAsked(code);
    }

    static string ArgValue(string flag)
    {
        string[] args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == flag) return args[i + 1];
        return null;
    }

    static void QuitIfAsked(int code)
    {
        foreach (string a in Environment.GetCommandLineArgs())
            if (a == "-quit")
            {
                Application.Quit(code);
                return;
            }
    }
}
