using System;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEngine;
using UnityEngine.Profiling;

namespace UnityDev.Perf
{
    /// <summary>
    /// PerfRawCapture — write a binary Profiler capture from a driven run.
    ///
    /// Use this only when the counters are not enough: a hitch whose cause is a marker you
    /// cannot name in advance. A window tells you the frame cost 41 ms; a raw capture tells you
    /// which marker inside that frame owned the time.
    ///
    /// The cost is real. Captures are large (tens of MB for a few hundred frames), loading one
    /// in the Editor replaces whatever the Profiler window is holding, and deep profiling
    /// changes the numbers it is measuring. Capture a named situation for a bounded number of
    /// frames, never "the whole session".
    /// </summary>
    public static class PerfRawCapture
    {
        public static string Path { get; private set; }
        public static bool Capturing { get; private set; }

        /// <summary>
        /// Begin writing. Default path is &lt;persistentDataPath&gt;/perf/capture.raw.
        /// Set the path BEFORE enabling the profiler — assigning logFile while it is enabled is
        /// how you get an empty file with no error.
        /// </summary>
        public static string Start(string path = null)
        {
            if (Capturing) return "already capturing to " + Path;

            if (string.IsNullOrEmpty(path))
                path = System.IO.Path.Combine(Application.persistentDataPath, "perf/capture");
            if (path.EndsWith(".raw", StringComparison.OrdinalIgnoreCase))
                path = path.Substring(0, path.Length - 4);

            string dir = System.IO.Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            Profiler.logFile = path;
            Profiler.enableBinaryLog = true;
            Profiler.enabled = true;

            Path = path + ".raw";
            Capturing = true;
            Debug.Log("[PERF] rawCapture start path=" + Path);
            return Path;
        }

        /// <summary>Stop and flush. The file is only complete after this returns; reading it
        /// while the run is still going gives a truncated capture that loads as zero frames.</summary>
        public static string Stop()
        {
            if (!Capturing) return "not capturing";
            Profiler.enabled = false;
            Profiler.enableBinaryLog = false;
            Profiler.logFile = "";
            Capturing = false;
            long bytes = 0;
            try { if (File.Exists(Path)) bytes = new FileInfo(Path).Length; }
            catch (Exception) { bytes = -1; }
            Debug.Log("[PERF] rawCapture stop path=" + Path + " bytes=" + bytes);
            return Path;
        }
    }

#if UNITY_EDITOR
    /// <summary>
    /// PerfRawExtract — turn a .raw capture into a CSV an agent can read, without opening the
    /// Profiler window.
    ///
    /// Every Editor type it needs is resolved by reflection and every step reports what it
    /// could not find, because these are internal-facing APIs whose shapes move between
    /// versions. Confirm on your version before building a loop on it: the extract prints the
    /// member it failed on rather than throwing.
    /// </summary>
    public static class PerfRawExtract
    {
        /// <summary>
        /// Load a capture and write one CSV row per frame: frame, frameTimeMs, frameGpuTimeMs,
        /// then one column per requested counter and one per requested marker (self time in ms,
        /// summed over the thread's samples). Returns a status string.
        /// </summary>
        public static string ToCsv(string rawPath, string csvPath,
                                   string[] counterNames = null, string[] markerNames = null)
        {
            counterNames = counterNames ?? new string[0];
            markerNames = markerNames ?? new string[0];

            if (!File.Exists(rawPath)) return "no such capture: " + rawPath;

            Type driver = Type.GetType("UnityEditorInternal.ProfilerDriver, UnityEditor");
            if (driver == null) return "ProfilerDriver not found on this version";

            MethodInfo load = driver.GetMethod("LoadProfile",
                BindingFlags.Public | BindingFlags.Static,
                null, new[] { typeof(string), typeof(bool) }, null);
            if (load == null) return "ProfilerDriver.LoadProfile(string,bool) not found";

            var loaded = load.Invoke(null, new object[] { rawPath, false });
            if (loaded is bool && !(bool)loaded) return "LoadProfile returned false for " + rawPath;

            PropertyInfo firstProp = driver.GetProperty("firstFrameIndex",
                BindingFlags.Public | BindingFlags.Static);
            PropertyInfo lastProp = driver.GetProperty("lastFrameIndex",
                BindingFlags.Public | BindingFlags.Static);
            if (firstProp == null || lastProp == null)
                return "ProfilerDriver.firstFrameIndex/lastFrameIndex not found";

            MethodInfo getView = driver.GetMethod("GetRawFrameDataView",
                BindingFlags.Public | BindingFlags.Static,
                null, new[] { typeof(int), typeof(int) }, null);
            if (getView == null) return "ProfilerDriver.GetRawFrameDataView(int,int) not found";

            int first = (int)firstProp.GetValue(null);
            int last = (int)lastProp.GetValue(null);
            if (last < first) return "capture loaded but holds no frames: " + rawPath;

            var sb = new StringBuilder();
            sb.Append("frame,frameTimeMs,frameGpuTimeMs");
            for (int i = 0; i < counterNames.Length; i++) sb.Append(",counter:").Append(Csv(counterNames[i]));
            for (int i = 0; i < markerNames.Length; i++) sb.Append(",marker:").Append(Csv(markerNames[i]));
            sb.Append('\n');

            int rows = 0;
            string firstError = null;
            for (int frame = first; frame <= last; frame++)
            {
                object view = getView.Invoke(null, new object[] { frame, 0 });
                if (view == null) continue;
                using (view as IDisposable)
                {
                    Type vt = view.GetType();
                    if (!GetBool(vt, view, "valid", true)) continue;

                    sb.Append(frame).Append(',');
                    sb.Append(Num(GetFloat(vt, view, "frameTimeMs"))).Append(',');
                    sb.Append(Num(GetFloat(vt, view, "frameGpuTimeMs")));

                    MethodInfo counterAsLong = vt.GetMethod("GetCounterValueAsLong",
                        BindingFlags.Public | BindingFlags.Instance, null, new[] { typeof(int) }, null);
                    MethodInfo markerId = vt.GetMethod("GetMarkerId",
                        BindingFlags.Public | BindingFlags.Instance, null, new[] { typeof(string) }, null);

                    for (int i = 0; i < counterNames.Length; i++)
                    {
                        sb.Append(',');
                        if (markerId == null || counterAsLong == null) { firstError = firstError ?? "GetMarkerId/GetCounterValueAsLong not found"; continue; }
                        int id = (int)markerId.Invoke(view, new object[] { counterNames[i] });
                        if (id < 0) continue;
                        sb.Append((long)counterAsLong.Invoke(view, new object[] { id }));
                    }

                    for (int i = 0; i < markerNames.Length; i++)
                    {
                        sb.Append(',');
                        double ms = MarkerSelfMs(vt, view, markerId, markerNames[i], ref firstError);
                        if (ms >= 0) sb.Append(Num((float)ms));
                    }

                    sb.Append('\n');
                    rows++;
                }
            }

            string outDir = System.IO.Path.GetDirectoryName(csvPath);
            if (!string.IsNullOrEmpty(outDir)) Directory.CreateDirectory(outDir);
            File.WriteAllText(csvPath, sb.ToString());

            string status = "[PERF] rawExtract frames=" + rows + " path=" + csvPath;
            if (firstError != null) status += " partial=" + firstError;
            Debug.Log(status);
            return status;
        }

        private static double MarkerSelfMs(Type vt, object view, MethodInfo markerId,
                                           string marker, ref string firstError)
        {
            if (markerId == null) { firstError = firstError ?? "GetMarkerId not found"; return -1; }
            int id = (int)markerId.Invoke(view, new object[] { marker });
            if (id < 0) return -1;

            PropertyInfo sampleCount = vt.GetProperty("sampleCount",
                BindingFlags.Public | BindingFlags.Instance);
            MethodInfo sampleMarkerId = vt.GetMethod("GetSampleMarkerId",
                BindingFlags.Public | BindingFlags.Instance, null, new[] { typeof(int) }, null);
            MethodInfo sampleTimeMs = vt.GetMethod("GetSampleTimeMs",
                BindingFlags.Public | BindingFlags.Instance, null, new[] { typeof(int) }, null);
            if (sampleCount == null || sampleMarkerId == null || sampleTimeMs == null)
            {
                firstError = firstError ?? "sampleCount/GetSampleMarkerId/GetSampleTimeMs not found";
                return -1;
            }

            int n = (int)sampleCount.GetValue(view);
            double total = 0;
            for (int i = 0; i < n; i++)
            {
                if ((int)sampleMarkerId.Invoke(view, new object[] { i }) != id) continue;
                total += Convert.ToDouble(sampleTimeMs.Invoke(view, new object[] { i }));
            }
            return total;
        }

        private static bool GetBool(Type t, object o, string name, bool fallback)
        {
            PropertyInfo p = t.GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            if (p == null) return fallback;
            return Convert.ToBoolean(p.GetValue(o));
        }

        private static float GetFloat(Type t, object o, string name)
        {
            PropertyInfo p = t.GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            if (p == null) return 0f;
            return Convert.ToSingle(p.GetValue(o));
        }

        private static string Num(float v)
        {
            return v.ToString("0.###", CultureInfo.InvariantCulture);
        }

        private static string Csv(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            if (s.IndexOf(',') < 0 && s.IndexOf('"') < 0) return s;
            return "\"" + s.Replace("\"", "\"\"") + "\"";
        }
    }
#endif
}
