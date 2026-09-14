using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using Unity.Profiling;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Scripting;
using Stopwatch = System.Diagnostics.Stopwatch;

namespace UnityDev.Perf
{
    /// <summary>How a counter's per-frame readings turn into numbers you can compare.</summary>
    public enum CounterKind
    {
        /// <summary>Produced fresh every frame (draw calls, bytes allocated this frame).
        /// Summarised, and summed across the window.</summary>
        PerFrame,
        /// <summary>A level that persists between frames (total used memory). Summarised;
        /// never summed, because summing a level counts the same bytes ninety times.</summary>
        Level,
        /// <summary>A monotonic total (a WorkCounter). Reported as start, end and delta.</summary>
        Cumulative,
        /// <summary>A thread time in nanoseconds; converted to milliseconds.</summary>
        MarkerNs
    }

    public struct CounterSpec
    {
        public string Category;
        public string Name;
        public CounterKind Kind;

        public CounterSpec(string category, string name, CounterKind kind)
        {
            Category = category;
            Name = name;
            Kind = kind;
        }

        public string Key { get { return Category + "/" + Name; } }
    }

    /// <summary>mean / median / p90 / p95 / p99 / max / min over one window.</summary>
    public struct Summary
    {
        public double Mean, Median, P90, P95, P99, Max, Min;
        public int N;

        public static Summary Of(double[] values, int count)
        {
            var s = new Summary();
            s.N = count;
            if (count <= 0) return s;

            var sorted = new double[count];
            Array.Copy(values, sorted, count);
            Array.Sort(sorted);

            double total = 0;
            for (int i = 0; i < count; i++) total += sorted[i];

            s.Mean = total / count;
            s.Min = sorted[0];
            s.Max = sorted[count - 1];
            s.Median = Percentile(sorted, 50);
            s.P90 = Percentile(sorted, 90);
            s.P95 = Percentile(sorted, 95);
            s.P99 = Percentile(sorted, 99);
            return s;
        }

        /// <summary>Nearest-rank percentile on an already-sorted array. Ninety frames is a small
        /// sample: p99 is one frame, so read it as "the worst one", not as a tail estimate.</summary>
        public static double Percentile(double[] sorted, double p)
        {
            if (sorted.Length == 0) return 0;
            int rank = (int)Math.Ceiling(p / 100.0 * sorted.Length) - 1;
            if (rank < 0) rank = 0;
            if (rank >= sorted.Length) rank = sorted.Length - 1;
            return sorted[rank];
        }
    }

    /// <summary>Which instrument produced the window. Two windows from different instruments
    /// are two different measurements and must not be subtracted from each other.</summary>
    public sealed class RunInfo
    {
        public string Mode = "unknown";
        public bool Batchmode, Editor, DevBuild, NullGraphics, FrameTimingStats, ProfilerEnabled;
        public string GraphicsDevice = "", Pipeline = "", Unity = "", Platform = "", Screen = "", GcMode = "";
        public int Vsync, TargetFrameRate;

        public static RunInfo Detect()
        {
            var r = new RunInfo();
            r.Batchmode = Application.isBatchMode;
            r.Editor = Application.isEditor;
            r.DevBuild = Debug.isDebugBuild;
            r.GraphicsDevice = SystemInfo.graphicsDeviceType.ToString();
            r.NullGraphics = SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null;
            RenderPipelineAsset rp = GraphicsSettings.currentRenderPipeline;
            r.Pipeline = rp != null ? rp.GetType().Name : "built-in";
            r.Unity = Application.unityVersion;
            r.Platform = Application.platform.ToString();
            r.Vsync = QualitySettings.vSyncCount;
            r.TargetFrameRate = Application.targetFrameRate;
            r.Screen = UnityEngine.Screen.width + "x" + UnityEngine.Screen.height;
            r.GcMode = GarbageCollector.GCMode.ToString();
            r.ProfilerEnabled = UnityEngine.Profiling.Profiler.enabled;

            if (r.Editor)
                r.Mode = r.Batchmode ? (r.NullGraphics ? "batchmode-nographics" : "batchmode")
                                     : "editor-windowed";
            else
                r.Mode = r.DevBuild ? "player-dev" : "player-release";
            return r;
        }
    }

    internal sealed class CounterResult
    {
        public string Key, Unit;
        public CounterKind Kind;
        public Summary Stats;
        public double Sum;
        public long Start, End;
    }

    /// <summary>One finished window: the frame times, the counters, and what was not there.</summary>
    public sealed class WindowResult
    {
        public string Label = "", Utc = "", SituationName = "", OutPath = "";
        public int SituationSeed = -1;
        public int Frames, Warmup, FirstFrame, LastFrame, Hitches;
        public RunInfo Run = new RunInfo();
        public Summary FrameTime;
        public Summary CpuFrame, CpuMain, CpuRender, Gpu;
        public bool FrameTimingAvailable;
        internal List<CounterResult> Counters = new List<CounterResult>();

        /// <summary>Counters asked for whose recorder was not valid on this build.</summary>
        public List<string> Missing = new List<string>();
        /// <summary>Counters that were valid and read zero on every frame of the window.
        /// An absence, not a measurement of nothing.</summary>
        public List<string> ZeroAll = new List<string>();

        public double CounterMedian(string key)
        {
            for (int i = 0; i < Counters.Count; i++)
                if (Counters[i].Key == key) return Counters[i].Stats.Median;
            return double.NaN;
        }

        public string ToJson()
        {
            var sb = new StringBuilder(2048);
            sb.Append("{\"schema\":\"perf-window/1\"");
            sb.Append(",\"label\":").Append(Str(Label));
            sb.Append(",\"utc\":").Append(Str(Utc));
            sb.Append(",\"frames\":").Append(Frames);
            sb.Append(",\"warmup\":").Append(Warmup);
            sb.Append(",\"firstFrame\":").Append(FirstFrame);
            sb.Append(",\"lastFrame\":").Append(LastFrame);

            sb.Append(",\"run\":{\"mode\":").Append(Str(Run.Mode));
            sb.Append(",\"batchmode\":").Append(Bool(Run.Batchmode));
            sb.Append(",\"editor\":").Append(Bool(Run.Editor));
            sb.Append(",\"devBuild\":").Append(Bool(Run.DevBuild));
            sb.Append(",\"graphicsDevice\":").Append(Str(Run.GraphicsDevice));
            sb.Append(",\"nullGraphics\":").Append(Bool(Run.NullGraphics));
            sb.Append(",\"pipeline\":").Append(Str(Run.Pipeline));
            sb.Append(",\"unity\":").Append(Str(Run.Unity));
            sb.Append(",\"platform\":").Append(Str(Run.Platform));
            sb.Append(",\"vsync\":").Append(Run.Vsync);
            sb.Append(",\"targetFrameRate\":").Append(Run.TargetFrameRate);
            sb.Append(",\"screen\":").Append(Str(Run.Screen));
            sb.Append(",\"gcMode\":").Append(Str(Run.GcMode));
            sb.Append(",\"frameTimingStats\":").Append(Bool(FrameTimingAvailable));
            sb.Append(",\"profilerEnabled\":").Append(Bool(Run.ProfilerEnabled)).Append('}');

            sb.Append(",\"situation\":{\"name\":").Append(Str(SituationName));
            sb.Append(",\"seed\":").Append(SituationSeed).Append('}');

            sb.Append(",\"frameTime\":{\"unit\":\"ms\"");
            AppendSummary(sb, FrameTime);
            sb.Append(",\"hitches\":").Append(Hitches).Append('}');

            sb.Append(",\"frameTiming\":");
            if (!FrameTimingAvailable)
            {
                sb.Append("\"unavailable\"");
            }
            else
            {
                sb.Append("{\"unit\":\"ms\",\"cpu\":{");
                AppendSummaryBody(sb, CpuFrame);
                sb.Append("},\"cpuMain\":{");
                AppendSummaryBody(sb, CpuMain);
                sb.Append("},\"cpuRender\":{");
                AppendSummaryBody(sb, CpuRender);
                sb.Append("},\"gpu\":{");
                AppendSummaryBody(sb, Gpu);
                sb.Append("}}");
            }

            sb.Append(",\"counters\":{");
            for (int i = 0; i < Counters.Count; i++)
            {
                CounterResult c = Counters[i];
                if (i > 0) sb.Append(',');
                sb.Append(Str(c.Key)).Append(":{\"unit\":").Append(Str(c.Unit));
                sb.Append(",\"kind\":").Append(Str(KindName(c.Kind)));
                if (c.Kind == CounterKind.Cumulative)
                {
                    sb.Append(",\"start\":").Append(c.Start);
                    sb.Append(",\"end\":").Append(c.End);
                    sb.Append(",\"delta\":").Append(c.End - c.Start);
                }
                else
                {
                    sb.Append(",\"median\":").Append(Num(c.Stats.Median));
                    sb.Append(",\"p95\":").Append(Num(c.Stats.P95));
                    sb.Append(",\"max\":").Append(Num(c.Stats.Max));
                    sb.Append(",\"min\":").Append(Num(c.Stats.Min));
                    sb.Append(",\"mean\":").Append(Num(c.Stats.Mean));
                    if (c.Kind == CounterKind.PerFrame)
                        sb.Append(",\"sum\":").Append(Num(c.Sum));
                }
                sb.Append('}');
            }
            sb.Append('}');

            sb.Append(",\"missing\":").Append(Arr(Missing));
            sb.Append(",\"zeroAll\":").Append(Arr(ZeroAll));
            sb.Append('}');
            return sb.ToString();
        }

        /// <summary>The one line to grep out of Editor.log or a player log.</summary>
        public string ToLogLine()
        {
            var sb = new StringBuilder(220);
            sb.Append("[PERF] window=").Append(Label);
            sb.Append(" mode=").Append(Run.Mode);
            sb.Append(" frames=").Append(Frames);
            sb.Append(" ft_med=").Append(Fixed2(FrameTime.Median));
            sb.Append(" ft_p95=").Append(Fixed2(FrameTime.P95));
            sb.Append(" ft_max=").Append(Fixed2(FrameTime.Max));
            sb.Append(" hitches=").Append(Hitches);

            double draw = CounterMedian("Render/Draw Calls Count");
            if (!double.IsNaN(draw)) sb.Append(" draw_med=").Append(Num(draw));
            double tris = CounterMedian("Render/Triangles Count");
            if (!double.IsNaN(tris)) sb.Append(" tris_med=").Append(Num(tris));

            for (int i = 0; i < Counters.Count; i++)
                if (Counters[i].Key == "Memory/GC Allocated In Frame")
                    sb.Append(" gc_sum=").Append(Num(Counters[i].Sum));

            for (int i = 0; i < Counters.Count; i++)
            {
                CounterResult c = Counters[i];
                if (c.Kind != CounterKind.Cumulative) continue;
                if (!c.Key.EndsWith(".discarded", StringComparison.Ordinal)) continue;
                long delta = c.End - c.Start;
                if (delta <= 0) continue;
                string system = c.Key.Substring("Game/".Length);
                system = system.Substring(0, system.Length - ".discarded".Length);
                sb.Append(" disc[").Append(system).Append("]=").Append(delta);
            }

            sb.Append(" missing=").Append(Missing.Count);
            sb.Append(" zero=").Append(ZeroAll.Count);
            sb.Append(" path=").Append(OutPath);
            return sb.ToString();
        }

        private static string KindName(CounterKind k)
        {
            switch (k)
            {
                case CounterKind.PerFrame: return "perFrame";
                case CounterKind.Level: return "level";
                case CounterKind.Cumulative: return "cumulative";
                default: return "markerMs";
            }
        }

        private static void AppendSummary(StringBuilder sb, Summary s)
        {
            sb.Append(',');
            AppendSummaryBody(sb, s);
        }

        private static void AppendSummaryBody(StringBuilder sb, Summary s)
        {
            sb.Append("\"mean\":").Append(Num(s.Mean));
            sb.Append(",\"median\":").Append(Num(s.Median));
            sb.Append(",\"p90\":").Append(Num(s.P90));
            sb.Append(",\"p95\":").Append(Num(s.P95));
            sb.Append(",\"p99\":").Append(Num(s.P99));
            sb.Append(",\"max\":").Append(Num(s.Max));
            sb.Append(",\"min\":").Append(Num(s.Min));
            sb.Append(",\"n\":").Append(s.N);
        }

        private static string Num(double v)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) return "0";
            return v.ToString("0.####", CultureInfo.InvariantCulture);
        }

        private static string Fixed2(double v)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) return "0.00";
            return v.ToString("0.00", CultureInfo.InvariantCulture);
        }

        private static string Bool(bool b) { return b ? "true" : "false"; }

        private static string Arr(List<string> items)
        {
            var sb = new StringBuilder("[");
            for (int i = 0; i < items.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(Str(items[i]));
            }
            return sb.Append(']').ToString();
        }

        private static string Str(string s)
        {
            if (s == null) return "\"\"";
            var sb = new StringBuilder(s.Length + 2);
            sb.Append('"');
            foreach (char ch in s)
            {
                switch (ch)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (ch < ' ') sb.Append("\\u").Append(((int)ch).ToString("x4", CultureInfo.InvariantCulture));
                        else sb.Append(ch);
                        break;
                }
            }
            return sb.Append('"').ToString();
        }
    }

    /// <summary>
    /// FrameSampler — a fixed window of frames, summarised into one JSONL record and one log line.
    ///
    /// Drop into Assets/ (Runtime, no package needed). It samples in LateUpdate at execution
    /// order int.MaxValue, so it runs after everything else in the frame, and it measures the
    /// interval with a Stopwatch rather than deltaTime, which is scaled and smoothed.
    ///
    ///   yield return FrameSampler.Sample("approach-gate", frames: 90, warmup: 30);
    ///   unity command eval 'return UnityDev.Perf.PerfProbe.Begin("hazard-lane");'
    ///   &lt;player&gt; -perf-window hazard-lane -perf-frames 90 -perf-out /tmp/perf/windows.jsonl
    ///
    /// A driven run measures the work your change made, on this instrument. It is not a
    /// hardware benchmark and its absolute milliseconds mean nothing off this instrument.
    /// </summary>
    [DefaultExecutionOrder(int.MaxValue)]
    public class FrameSampler : MonoBehaviour
    {
        /// <summary>Counters sampled by default. Every name here is a guess until the catalogue
        /// confirms it: run CounterCatalog.Grep("Draw") on the build you are measuring, and read
        /// the window's "missing" list before believing a zero.</summary>
        public static readonly List<CounterSpec> Counters = new List<CounterSpec>
        {
            new CounterSpec("Render", "Draw Calls Count", CounterKind.PerFrame),
            new CounterSpec("Render", "SetPass Calls Count", CounterKind.PerFrame),
            new CounterSpec("Render", "Batches Count", CounterKind.PerFrame),
            new CounterSpec("Render", "Triangles Count", CounterKind.PerFrame),
            new CounterSpec("Render", "Vertices Count", CounterKind.PerFrame),
            new CounterSpec("Render", "Shadow Casters Count", CounterKind.PerFrame),
            new CounterSpec("Render", "Vertex Buffer Upload In Frame Bytes", CounterKind.PerFrame),
            new CounterSpec("Render", "Index Buffer Upload In Frame Bytes", CounterKind.PerFrame),
            new CounterSpec("Render", "Used Buffers Bytes", CounterKind.Level),
            new CounterSpec("Render", "Used Textures Bytes", CounterKind.Level),
            new CounterSpec("Memory", "GC Allocated In Frame", CounterKind.PerFrame),
            new CounterSpec("Memory", "GC Allocation In Frame Count", CounterKind.PerFrame),
            new CounterSpec("Memory", "GC Used Memory", CounterKind.Level),
            new CounterSpec("Memory", "Total Used Memory", CounterKind.Level),
            new CounterSpec("Memory", "Texture Memory", CounterKind.Level),
            new CounterSpec("Memory", "Mesh Memory", CounterKind.Level),
            new CounterSpec("Internal", "Main Thread", CounterKind.MarkerNs),
            new CounterSpec("Internal", "Render Thread", CounterKind.MarkerNs)
        };

        /// <summary>Ask FrameTimingManager for CPU/GPU split as well. Needs Frame Timing Stats
        /// enabled in Player Settings; the window records whether readings actually arrived.</summary>
        public static bool UseFrameTiming = true;

        /// <summary>Write the [PERF] line to the log when a window finishes.</summary>
        public static bool LogLine = true;

        /// <summary>Name and seed of the situation being measured, so a window says what it
        /// was measuring. Set these when you enter the situation.</summary>
        public static string SituationName = "";
        public static int SituationSeed = -1;

        private static string _outPath;

        /// <summary>Where windows are appended. $UNITY_PERF_OUT wins, then
        /// &lt;persistentDataPath&gt;/perf/windows.jsonl. Delete the file before a run —
        /// a stale window compared against a fresh one is the quietest wrong answer there is.</summary>
        public static string OutputPath
        {
            get
            {
                if (!string.IsNullOrEmpty(_outPath)) return _outPath;
                string env = Environment.GetEnvironmentVariable("UNITY_PERF_OUT");
                if (!string.IsNullOrEmpty(env)) return env;
                return Path.Combine(Application.persistentDataPath, "perf/windows.jsonl");
            }
            set { _outPath = value; }
        }

        public static bool Running { get; private set; }
        public static WindowResult Last { get; private set; }
        public static bool WindowCompleted { get; private set; }

        private static FrameSampler _instance;

        private readonly List<ProfilerRecorder> _recorders = new List<ProfilerRecorder>();
        private readonly List<CounterSpec> _specs = new List<CounterSpec>();
        private double[][] _series;
        private double[] _frameMs;
        private double[] _cpu, _cpuMain, _cpuRender, _gpu;
        private long[] _workStart;
        private List<WorkCounter> _workCounters = new List<WorkCounter>();
        private readonly Stopwatch _watch = new Stopwatch();
        private FrameTiming[] _timingBuf = new FrameTiming[1];

        private string _label;
        private int _frames, _warmupLeft, _warmup, _samples, _timingSamples, _firstFrame, _lastFrame;

        /// <summary>Create the hidden sampler object if it is not there yet.</summary>
        public static FrameSampler Ensure()
        {
            if (_instance != null) return _instance;
            var go = new GameObject("~FrameSampler");
            go.hideFlags = HideFlags.HideAndDontSave;
            DontDestroyOnLoad(go);
            _instance = go.AddComponent<FrameSampler>();
            return _instance;
        }

        /// <summary>Run one window from a coroutine — a journey test, or any driver that can
        /// yield. Returns when the window is written.</summary>
        public static IEnumerator Sample(string label, int frames = 90, int warmup = 30,
                                         string outPath = null)
        {
            Begin(label, frames, warmup, outPath);
            while (Running) yield return null;
        }

        /// <summary>Start a window and return immediately. Poll Running / WindowCompleted, or
        /// read PerfProbe.LastLine() from a live Editor.</summary>
        public static string Begin(string label, int frames = 90, int warmup = 30,
                                   string outPath = null)
        {
            if (Running) return "busy: window '" + Ensure()._label + "' still running";
            if (frames < 1) frames = 1;
            if (warmup < 0) warmup = 0;
            if (!string.IsNullOrEmpty(outPath)) OutputPath = outPath;

            FrameSampler s = Ensure();
            s.StartWindow(label, frames, warmup);
            return "started label=" + label + " frames=" + frames + " warmup=" + warmup +
                   " out=" + OutputPath;
        }

        private void StartWindow(string label, int frames, int warmup)
        {
            _label = string.IsNullOrEmpty(label) ? "window" : label;
            _frames = frames;
            _warmup = warmup;
            _warmupLeft = warmup;
            _samples = 0;
            _timingSamples = 0;
            _firstFrame = Time.frameCount;
            _lastFrame = Time.frameCount;

            _frameMs = new double[frames];
            _cpu = new double[frames];
            _cpuMain = new double[frames];
            _cpuRender = new double[frames];
            _gpu = new double[frames];

            _specs.Clear();
            _recorders.Clear();
            for (int i = 0; i < Counters.Count; i++)
            {
                CounterSpec spec = Counters[i];
                ProfilerRecorder r = ProfilerRecorder.StartNew(
                    new ProfilerCategory(spec.Category), spec.Name, 1,
                    ProfilerRecorderOptions.Default);
                _specs.Add(spec);
                _recorders.Add(r);
            }
            _series = new double[_specs.Count][];
            for (int i = 0; i < _specs.Count; i++) _series[i] = new double[frames];

            _workCounters = new List<WorkCounter>(WorkCounter.All);
            _workStart = new long[_workCounters.Count * 3];

            WindowCompleted = false;
            Running = true;
            _watch.Reset();
            _watch.Start();
        }

        private void LateUpdate()
        {
            if (!Running) return;

            double ms = _watch.Elapsed.TotalMilliseconds;
            _watch.Reset();
            _watch.Start();

            if (_warmupLeft > 0) { _warmupLeft--; return; }

            if (_samples == 0)
            {
                _firstFrame = Time.frameCount;
                CaptureWorkStart();
            }

            _frameMs[_samples] = ms;
            for (int i = 0; i < _recorders.Count; i++)
            {
                ProfilerRecorder r = _recorders[i];
                _series[i][_samples] = r.Valid ? r.LastValueAsDouble : 0.0;
            }

            if (UseFrameTiming) SampleFrameTiming();

            _lastFrame = Time.frameCount;
            _samples++;
            if (_samples >= _frames) Finish();
        }

        private void SampleFrameTiming()
        {
            FrameTimingManager.CaptureFrameTimings();
            uint got = FrameTimingManager.GetLatestTimings(1, _timingBuf);
            if (got == 0) return;
            FrameTiming t = _timingBuf[0];
            int i = _timingSamples;
            if (i >= _cpu.Length) return;
            _cpu[i] = t.cpuFrameTime;
            _cpuMain[i] = t.cpuMainThreadFrameTime;
            _cpuRender[i] = t.cpuRenderThreadFrameTime;
            _gpu[i] = t.gpuFrameTime;
            _timingSamples++;
        }

        private void CaptureWorkStart()
        {
            for (int i = 0; i < _workCounters.Count; i++)
            {
                WorkCounter w = _workCounters[i];
                _workStart[i * 3 + 0] = w.ScheduledTotal;
                _workStart[i * 3 + 1] = w.CompletedTotal;
                _workStart[i * 3 + 2] = w.DiscardedTotal;
            }
        }

        private void Finish()
        {
            Running = false;
            _watch.Stop();

            var w = new WindowResult();
            w.Label = _label;
            w.Utc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
            w.Frames = _samples;
            w.Warmup = _warmup;
            w.FirstFrame = _firstFrame;
            w.LastFrame = _lastFrame;
            w.Run = RunInfo.Detect();
            w.SituationName = SituationName ?? "";
            w.SituationSeed = SituationSeed;
            w.FrameTime = Summary.Of(_frameMs, _samples);

            int hitches = 0;
            double threshold = w.FrameTime.Median * 2.0;
            for (int i = 0; i < _samples; i++) if (_frameMs[i] > threshold) hitches++;
            w.Hitches = hitches;

            w.FrameTimingAvailable = _timingSamples > 0 && AnyNonZero(_cpu, _timingSamples);
            if (w.FrameTimingAvailable)
            {
                w.CpuFrame = Summary.Of(_cpu, _timingSamples);
                w.CpuMain = Summary.Of(_cpuMain, _timingSamples);
                w.CpuRender = Summary.Of(_cpuRender, _timingSamples);
                w.Gpu = Summary.Of(_gpu, _timingSamples);
            }

            for (int i = 0; i < _specs.Count; i++)
            {
                CounterSpec spec = _specs[i];
                ProfilerRecorder r = _recorders[i];
                if (!r.Valid)
                {
                    w.Missing.Add(spec.Key);
                    r.Dispose();
                    continue;
                }

                double scale = spec.Kind == CounterKind.MarkerNs ? 1e-6 : 1.0;
                double[] values = _series[i];
                double sum = 0;
                bool anyNonZero = false;
                for (int f = 0; f < _samples; f++)
                {
                    values[f] *= scale;
                    sum += values[f];
                    if (values[f] != 0.0) anyNonZero = true;
                }

                var cr = new CounterResult();
                cr.Key = spec.Key;
                cr.Kind = spec.Kind;
                cr.Unit = spec.Kind == CounterKind.MarkerNs ? "ms" : r.UnitType.ToString();
                cr.Stats = Summary.Of(values, _samples);
                cr.Sum = sum;
                w.Counters.Add(cr);
                if (!anyNonZero) w.ZeroAll.Add(spec.Key);
                r.Dispose();
            }
            _recorders.Clear();

            for (int i = 0; i < _workCounters.Count; i++)
            {
                WorkCounter c = _workCounters[i];
                AddWork(w, "Game/" + c.System + ".scheduled", _workStart[i * 3 + 0], c.ScheduledTotal);
                AddWork(w, "Game/" + c.System + ".completed", _workStart[i * 3 + 1], c.CompletedTotal);
                AddWork(w, "Game/" + c.System + ".discarded", _workStart[i * 3 + 2], c.DiscardedTotal);
            }

            w.OutPath = OutputPath;
            Append(w);
            Last = w;
            WindowCompleted = true;
            if (LogLine) Debug.Log(w.ToLogLine());
        }

        private static void AddWork(WindowResult w, string key, long start, long end)
        {
            var cr = new CounterResult();
            cr.Key = key;
            cr.Kind = CounterKind.Cumulative;
            cr.Unit = "Count";
            cr.Start = start;
            cr.End = end;
            w.Counters.Add(cr);
        }

        private static bool AnyNonZero(double[] values, int count)
        {
            for (int i = 0; i < count; i++) if (values[i] != 0.0) return true;
            return false;
        }

        private static void Append(WindowResult w)
        {
            try
            {
                string dir = Path.GetDirectoryName(w.OutPath);
                if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                File.AppendAllText(w.OutPath, w.ToJson() + "\n");
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PERF] could not write " + w.OutPath + ": " + e.Message);
            }
        }

        // ---- player entry point: -perf-window <label> [-perf-frames N] [-perf-warmup N] ----

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void AutoStartFromCommandLine()
        {
            string[] args = Environment.GetCommandLineArgs();
            string label = null, outPath = null;
            int frames = 90, warmup = 30;
            for (int i = 0; i < args.Length - 1; i++)
            {
                switch (args[i])
                {
                    case "-perf-window": label = args[i + 1]; break;
                    case "-perf-out": outPath = args[i + 1]; break;
                    case "-perf-frames": int.TryParse(args[i + 1], out frames); break;
                    case "-perf-warmup": int.TryParse(args[i + 1], out warmup); break;
                    case "-situation": SituationName = args[i + 1]; break;
                }
            }
            if (string.IsNullOrEmpty(label)) return;
            Debug.Log(Begin(label, frames, warmup, outPath));
        }
    }

    /// <summary>
    /// PerfProbe — the three calls an `eval` against a live Editor needs. Keep them returning
    /// strings: an eval result comes back at data.result.result and a string survives the trip.
    /// </summary>
    public static class PerfProbe
    {
        public static string Begin(string label, int frames = 90, int warmup = 30)
        {
            return FrameSampler.Begin(label, frames, warmup);
        }

        /// <summary>The finished window's [PERF] line, or what it is still waiting for.</summary>
        public static string LastLine()
        {
            if (FrameSampler.Running) return "running";
            WindowResult w = FrameSampler.Last;
            return w == null ? "no window yet" : w.ToLogLine();
        }

        /// <summary>The finished window as the same JSON that went into the JSONL file.</summary>
        public static string LastJson()
        {
            if (FrameSampler.Running) return "{\"running\":true}";
            WindowResult w = FrameSampler.Last;
            return w == null ? "{\"empty\":true}" : w.ToJson();
        }
    }
}
