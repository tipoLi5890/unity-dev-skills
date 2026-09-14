// ProbeCommands — exposes the probe and the situation registry to a live Editor, so an agent
// can read state and jump to a moment without a test run and without a domain reload.
//
// Put this file in an EDITOR assembly (Assets/Editor/, or an asmdef with includePlatforms:
// ["Editor"]). Gate the file on a define rather than on the package being present, so a
// project that does not have the CLI package still compiles:
//
//   asmdef → "versionDefines": [
//     { "name": "com.unity.pipeline", "expression": "", "define": "HAS_UNITY_PIPELINE" }
//   ]
//   and reference the package's Editor assembly in the same asmdef.
//
// An empty "expression" means "any version". Confirm the package name and the assembly name
// on your version — list them, do not recall them.
//
// After editing this file:
//   unity command recompile
//   unity command recompile_status        # poll until completed
//   unity list --format json              # confirm probe / situation_list / situation_enter registered
//
// Never assume the name you wrote is the name that registered.
#if HAS_UNITY_PIPELINE
using System.Text;
using Unity.Pipeline.Commands;
using UnityEditor;
using UnityEngine;

public static class ProbeCommands
{
    /// <summary>unity command probe — one JSON line, the same one GameProbe.Json() returns.</summary>
    [CliCommand("probe", "One-line GameProbe snapshot of the running game", MainThreadRequired = true)]
    public static string Probe() => GameProbe.Json();

    /// <summary>unity command situation_list — the ids this project actually registered.</summary>
    [CliCommand("situation_list", "Every registered situation id", MainThreadRequired = true)]
    public static string SituationList()
    {
        var sb = new StringBuilder(128);
        sb.Append("{\"playing\":").Append(EditorApplication.isPlaying ? "true" : "false")
          .Append(",\"current\":").Append(Quote(Situations.Current))
          .Append(",\"ids\":").Append(IdArray());
        return sb.Append('}').ToString();
    }

    /// <summary>Just the ids, as a JSON array — so it can be embedded in another answer.</summary>
    static string IdArray()
    {
        var sb = new StringBuilder(96).Append('[');
        string[] ids = Situations.Ids();
        for (int i = 0; i < ids.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(Quote(ids[i]));
        }
        return sb.Append(']').ToString();
    }

    /// <summary>
    /// unity command situation_enter -- --id approach-gate --params "angle=80,cold=true"
    ///
    /// Outside Play mode there is nothing to enter, so this starts Play mode and answers
    /// retry:true. Entering Play mode reloads the domain; the caller re-issues the command
    /// once `probe` reports playing:true.
    /// </summary>
    [CliCommand("situation_enter", "Enter a named situation in the running game", MainThreadRequired = true)]
    public static string SituationEnter(
        [CliArg("id", "Situation id, e.g. approach-gate")] string id,
        [CliArg("params", "Comma-separated name=value pairs")] string parameters = "")
    {
        if (!EditorApplication.isPlaying)
        {
            EditorApplication.EnterPlaymode();
            return "{\"entered\":false,\"retry\":true,\"reason\":\"entering play mode; re-issue when probe reports playing:true\"}";
        }

        if (!Situations.Has(id))
            return "{\"entered\":false,\"retry\":false,\"reason\":\"unknown id\",\"ids\":" +
                   IdArray() + "}";

        if (!string.IsNullOrEmpty(parameters))
            foreach (string pair in parameters.Split(','))
            {
                int eq = pair.IndexOf('=');
                if (eq > 0) Situations.SetParam(pair.Substring(0, eq).Trim(), pair.Substring(eq + 1).Trim());
            }

        SituationHandle handle = Situations.Enter(id);

        // Enter returns on the frame it was called: readiness is a wait, not a result. Report
        // what is missing right now and let the caller poll `probe` for allReady.
        var sb = new StringBuilder(160);
        sb.Append("{\"entered\":true,\"id\":").Append(Quote(id))
          .Append(",\"ready\":").Append(handle.IsReady ? "true" : "false")
          .Append(",\"missing\":[");
        string[] missing = handle.Missing();
        for (int i = 0; i < missing.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(Quote(missing[i]));
        }
        sb.Append("],\"timeoutSeconds\":").Append(handle.TimeoutSeconds.ToString("F1",
            System.Globalization.CultureInfo.InvariantCulture));
        return sb.Append('}').ToString();
    }

    /// <summary>unity command probe_ready — poll target for a wait loop in the shell.</summary>
    [CliCommand("probe_ready", "Readiness only: allReady plus the missing members", MainThreadRequired = true)]
    public static string ProbeReady()
    {
        if (!Application.isPlaying) return "{\"playing\":false,\"allReady\":false,\"missing\":[]}";
        var sb = new StringBuilder(120);
        sb.Append("{\"playing\":true,\"allReady\":").Append(GameProbe.AllReady ? "true" : "false")
          .Append(",\"missing\":[");
        string[] missing = GameProbe.MissingReady();
        for (int i = 0; i < missing.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(Quote(missing[i]));
        }
        return sb.Append("]}").ToString();
    }

    static string Quote(string s)
    {
        if (s == null) return "null";
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }
}
#endif
