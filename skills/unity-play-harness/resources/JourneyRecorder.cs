using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEngine;

/// <summary>
/// Samples GameProbe into one JSONL timeline per journey, so a run leaves a file that can be
/// asserted on inside the test AND compared against another run afterwards.
///
///   using (var rec = new JourneyRecorder("approach-gate", JourneyDir))
///   {
///       while (rec.ElapsedUnscaled &lt; 12f) { rec.Sample(); yield return null; }
///       int shot = rec.Milestone("arrival");
///       // capture rec.ShotPath(shot, "arrival")
///   }
///
/// The directory is deleted and recreated in the constructor: a half-overwritten timeline
/// sitting next to last run's screenshots reads as one run and describes neither.
///
/// Needs GameProbe.cs, and Situations.cs for the meta line's situation and parameters.
/// </summary>
public sealed class JourneyRecorder : IDisposable
{
    public const int Schema = 1;

    public string JourneyId { get; private set; }
    public string OutputDirectory { get; private set; }
    public string TimelinePath { get; private set; }

    /// <summary>Every sample taken, in order — what JourneyAsserts reads.</summary>
    public List<ProbeSnapshot> Captured { get; private set; }

    public int Samples => Captured.Count;
    public IList<string> Milestones => _milestones;

    /// <summary>Unscaled seconds since the recorder was created. Use this to time a drive,
    /// never Time.time — a journey that pauses the game would otherwise never end.</summary>
    public float ElapsedUnscaled => Time.unscaledTime - _startUnscaled;

    readonly int _everyNFrames;
    readonly List<string> _milestones = new List<string>();
    readonly float _startUnscaled;
    StreamWriter _writer;
    int _maxSamples = 20000;

    public JourneyRecorder(string journeyId, string outDir, int everyNFrames = 1)
    {
        if (string.IsNullOrEmpty(journeyId)) throw new ArgumentException("journeyId");
        JourneyId = journeyId;
        _everyNFrames = Mathf.Max(1, everyNFrames);
        _startUnscaled = Time.unscaledTime;
        Captured = new List<ProbeSnapshot>(256);

        OutputDirectory = Path.Combine(outDir ?? DefaultRoot(), journeyId);
        if (Directory.Exists(OutputDirectory)) Directory.Delete(OutputDirectory, true);
        Directory.CreateDirectory(OutputDirectory);
        TimelinePath = Path.Combine(OutputDirectory, "timeline.jsonl");

        // AutoFlush, because a run that crashes half way through still has to leave the samples
        // it took — that is usually the run whose timeline matters most.
        _writer = new StreamWriter(TimelinePath, false, new UTF8Encoding(false)) { AutoFlush = true };
        _writer.WriteLine(MetaLine());
    }

    /// <summary>&lt;persistentDataPath&gt;/journeys, or $JOURNEY_OUT when the harness set one.</summary>
    public static string DefaultRoot()
    {
        string env = Environment.GetEnvironmentVariable("JOURNEY_OUT");
        return string.IsNullOrEmpty(env) ? Path.Combine(Application.persistentDataPath, "journeys") : env;
    }

    /// <summary>Cap on samples held in memory and written. Raise it deliberately.</summary>
    public int MaxSamples
    {
        get => _maxSamples;
        set => _maxSamples = Mathf.Max(1, value);
    }

    /// <summary>
    /// Take one sample. Call it every frame from the drive loop: the frame filter lives here,
    /// so a milestone sample is written even on a frame the filter would have skipped.
    /// Returns the snapshot that was written, or null when the frame was skipped.
    /// </summary>
    public ProbeSnapshot Sample(string milestone = null)
    {
        if (_writer == null) return null;
        if (milestone == null && _everyNFrames > 1 && Time.frameCount % _everyNFrames != 0) return null;
        if (Captured.Count >= _maxSamples) return null;

        ProbeSnapshot s = GameProbe.Snapshot();
        s.n = Captured.Count;
        s.milestone = milestone;
        Captured.Add(s);
        _writer.WriteLine(s.ToJson());
        return s;
    }

    /// <summary>
    /// Tag this frame and return the milestone's 1-based index, for the screenshot name.
    /// Tag and capture in the same frame, or the image and the row describe different moments.
    /// </summary>
    public int Milestone(string name)
    {
        _milestones.Add(name);
        ProbeSnapshot s = Sample(name);
        Debug.Log("[JOURNEY] milestone=" + name + " n=" + (s != null ? s.n : -1) +
                  " state=" + (s != null ? (s.state ?? "-") : "-"));
        return _milestones.Count;
    }

    /// <summary>Path for a milestone screenshot: &lt;dir&gt;/01_arrival.png</summary>
    public string ShotPath(int milestoneIndex, string name)
        => Path.Combine(OutputDirectory, milestoneIndex.ToString("00", CultureInfo.InvariantCulture) + "_" + name + ".png");

    public void Dispose()
    {
        if (_writer == null) return;
        var sb = new StringBuilder(96);
        sb.Append("{\"end\":true,\"samples\":").Append(Captured.Count).Append(",\"milestones\":[");
        for (int i = 0; i < _milestones.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(Json(_milestones[i]));
        }
        sb.Append("]}");
        _writer.WriteLine(sb.ToString());
        _writer.Dispose();
        _writer = null;

        Debug.Log("[JOURNEY] " + JourneyId + " samples=" + Captured.Count +
                  " milestones=" + _milestones.Count +
                  " seconds=" + ElapsedUnscaled.ToString("F2", CultureInfo.InvariantCulture) +
                  " path=" + TimelinePath);
    }

    string MetaLine()
    {
        var sb = new StringBuilder(256);
        sb.Append("{\"meta\":true,\"schema\":").Append(Schema)
          .Append(",\"journey\":").Append(Json(JourneyId))
          .Append(",\"situation\":").Append(Json(Situations.Current))
          .Append(",\"params\":{");
        bool first = true;
        foreach (KeyValuePair<string, string> p in Situations.AllParams())
        {
            if (!first) sb.Append(',');
            first = false;
            sb.Append(Json(p.Key)).Append(':').Append(Json(p.Value));
        }
        sb.Append("},\"startedUtc\":")
          .Append(Json(DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture)))
          .Append(",\"batch\":").Append(Application.isBatchMode ? "true" : "false")
          .Append(",\"unity\":").Append(Json(Application.unityVersion))
          .Append('}');
        return sb.ToString();
    }

    static string Json(string s)
    {
        if (s == null) return "null";
        var sb = new StringBuilder(s.Length + 2).Append('"');
        foreach (char c in s)
        {
            if (c == '"' || c == '\\') sb.Append('\\').Append(c);
            else if (c == '\n') sb.Append("\\n");
            else if (c < 0x20) sb.Append(' ');
            else sb.Append(c);
        }
        return sb.Append('"').ToString();
    }
}

/// <summary>One broken invariant, with the sample it broke on.</summary>
public struct JourneyViolation
{
    public int n;
    public int frame;
    public float t;
    public string rule;
    public string detail;

    public override string ToString()
        => "n=" + n + " frame=" + frame + " t=" + t.ToString("F3", CultureInfo.InvariantCulture) +
           " " + rule + ": " + detail;
}

/// <summary>
/// Invariants over a recorded journey. These return violations rather than asserting, so the
/// recorder stays in a Runtime assembly with no test-framework reference; the test does the
/// asserting and prints the list.
/// </summary>
public static class JourneyAsserts
{
    /// <summary>Join a violation list into one assertion message.</summary>
    public static string Describe(List<JourneyViolation> violations, int show = 5)
    {
        if (violations.Count == 0) return "none";
        var sb = new StringBuilder();
        sb.Append(violations.Count).Append(" violation(s):");
        for (int i = 0; i < violations.Count && i < show; i++) sb.Append("\n  ").Append(violations[i]);
        if (violations.Count > show) sb.Append("\n  … ").Append(violations.Count - show).Append(" more");
        return sb.ToString();
    }

    /// <summary>
    /// The player was never inside solid geometry. Evaluated against the colliders present when
    /// this runs, so it is an invariant about STATIC geometry — lane walls, the gate frame.
    /// For anything that moves, sample an overlap flag per frame into custom{} instead.
    /// </summary>
    public static List<JourneyViolation> NeverInside(IList<ProbeSnapshot> samples, LayerMask mask, float radius)
    {
        var bad = new List<JourneyViolation>();
        for (int i = 0; i < samples.Count; i++)
        {
            ProbeSnapshot s = samples[i];
            if (!s.hasPlayer) continue;
            if (Physics.CheckSphere(s.pos, radius, mask, QueryTriggerInteraction.Ignore))
                bad.Add(new JourneyViolation
                {
                    n = s.n, frame = s.frame, t = s.t, rule = "never-inside",
                    detail = "pos " + s.pos.ToString("F2") + " overlaps layers " + mask.value +
                             " at radius " + radius.ToString("F2", CultureInfo.InvariantCulture),
                });
        }
        return bad;
    }

    /// <summary>
    /// State only ever moves forward through the declared order. Catches a state machine that
    /// re-enters an earlier phase, and a state nobody declared.
    /// </summary>
    public static List<JourneyViolation> Monotonic(IList<ProbeSnapshot> samples, string[] order)
    {
        var bad = new List<JourneyViolation>();
        int highest = -1;
        for (int i = 0; i < samples.Count; i++)
        {
            ProbeSnapshot s = samples[i];
            if (s.state == null) continue;
            int idx = Array.IndexOf(order, s.state);
            if (idx < 0)
            {
                bad.Add(new JourneyViolation
                {
                    n = s.n, frame = s.frame, t = s.t, rule = "monotonic",
                    detail = "state '" + s.state + "' is not in [" + string.Join(",", order) + "]",
                });
                continue;
            }
            if (idx < highest)
                bad.Add(new JourneyViolation
                {
                    n = s.n, frame = s.frame, t = s.t, rule = "monotonic",
                    detail = "state went back to '" + s.state + "' after '" + order[highest] + "'",
                });
            else highest = idx;
        }
        return bad;
    }

    /// <summary>
    /// Everything was ready before the game reached a moment. window narrows which samples have
    /// to satisfy it (pass null for "every sample up to the milestone"); a milestone that never
    /// happened is itself a violation.
    /// </summary>
    public static List<JourneyViolation> ReadyBefore(IList<ProbeSnapshot> samples, string milestone,
                                                     Func<ProbeSnapshot, bool> window = null)
    {
        var bad = new List<JourneyViolation>();
        int at = -1;
        for (int i = 0; i < samples.Count; i++)
            if (samples[i].milestone == milestone) { at = i; break; }

        if (at < 0)
        {
            bad.Add(new JourneyViolation
            {
                n = -1, frame = -1, t = 0f, rule = "ready-before",
                detail = "milestone '" + milestone + "' never happened in " + samples.Count + " samples",
            });
            return bad;
        }

        for (int i = 0; i <= at; i++)
        {
            ProbeSnapshot s = samples[i];
            if (window != null && !window(s)) continue;
            if (s.allReady) continue;
            var missing = new List<string>();
            for (int k = 0; k < s.readyOrder.Length; k++)
                if (!s.ready[s.readyOrder[k]]) missing.Add(s.readyOrder[k]);
            bad.Add(new JourneyViolation
            {
                n = s.n, frame = s.frame, t = s.t, rule = "ready-before",
                detail = "missing " + string.Join(",", missing.ToArray()) + " before '" + milestone + "'",
            });
        }
        return bad;
    }

    /// <summary>
    /// A predicate that must never be true — the general form behind "speed at the gate stays
    /// under the budget": Never(s, x =&gt; x.Number("gateDist") &lt; 2f &amp;&amp; x.speed &gt; 12f, "entry-speed").
    /// </summary>
    public static List<JourneyViolation> Never(IList<ProbeSnapshot> samples,
                                               Func<ProbeSnapshot, bool> predicate, string rule)
    {
        var bad = new List<JourneyViolation>();
        for (int i = 0; i < samples.Count; i++)
        {
            ProbeSnapshot s = samples[i];
            if (!predicate(s)) continue;
            bad.Add(new JourneyViolation
            {
                n = s.n, frame = s.frame, t = s.t, rule = rule,
                // The whole sample line, because the predicate is the caller's and there is no
                // way to know from here which of its values is the one worth printing.
                detail = "held on " + GameProbe.ToLine(s),
            });
        }
        return bad;
    }
}
