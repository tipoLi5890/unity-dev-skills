// LaneDataPath.cs — the folder the game writes its saves and other runtime files into, with an
// Editor-only override so Editors running side by side on test lanes do not share one.
//
// Application.persistentDataPath is derived from the company and product name in Player
// Settings, and every test lane links the same ProjectSettings, so every lane's Editor resolves
// the same folder: two suites running at once read and overwrite each other's saves. lanes.sh
// exports GAME_DATA_DIR=<prefix>_data_lane<K> for clone lane K (lane 0 runs with it unset), and
// this class answers with that folder in the Editor. A player build never reads the variable.
// Method: reference/parallel-runs.md.
//
// Drop into the Runtime assembly. Every path the game builds under persistentDataPath goes
// through Root instead — the save store first (unity-scene-flow, resources/Bootstrap.cs):
//
//   Saves = new SaveStore(LaneDataPath.Root, saveFileName);          // was persistentDataPath
//   string ghost = Path.Combine(LaneDataPath.Root, "ghosts", "gate-03.json");
//
// and so does a test's [SetUp] that clears the runner's progress before a gate run:
//
//   [SetUp] public void FreshSave() { File.Delete(Path.Combine(LaneDataPath.Root, "save.json")); }
//
// PlayerPrefs are NOT redirected: they are keyed by the same company and product name, so lanes
// share them too. reference/parallel-runs.md says what to do when tests write them.
using System;
using System.IO;
using UnityEngine;

public static class LaneDataPath
{
    /// <summary>The variable lanes.sh exports. Keep it equal to lanes.sh's LANE_DATA_VAR.</summary>
    public const string EnvVar = "GAME_DATA_DIR";

#if UNITY_EDITOR
    static string _logged;
#endif

    /// <summary>
    /// The folder for saves and runtime files. In a build: Application.persistentDataPath.
    /// In the Editor: the folder named by GAME_DATA_DIR when it is set (created if missing),
    /// else persistentDataPath. Logs the choice once per domain as [LANE] data=...
    /// </summary>
    public static string Root
    {
        get
        {
#if UNITY_EDITOR
            string dir = Environment.GetEnvironmentVariable(EnvVar);
            if (!string.IsNullOrEmpty(dir))
            {
                Directory.CreateDirectory(dir);
                Announce(dir, EnvVar);
                return dir;
            }
            Announce(Application.persistentDataPath, "persistentDataPath");
#endif
            return Application.persistentDataPath;
        }
    }

#if UNITY_EDITOR
    // One line in the log says which folder this run used: a lane whose log shows
    // persistentDataPath was started without the variable, and shares its saves.
    static void Announce(string dir, string source)
    {
        if (_logged == dir) return;
        _logged = dir;
        Debug.Log("[LANE] data=" + dir + " (" + source + ", LANE=" +
                  (Environment.GetEnvironmentVariable("LANE") ?? "unset") + ")");
    }
#endif
}
