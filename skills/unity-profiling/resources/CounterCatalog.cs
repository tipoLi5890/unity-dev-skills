using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Unity.Profiling;
using Unity.Profiling.LowLevel;
using Unity.Profiling.LowLevel.Unsafe;
using UnityEngine;

namespace UnityDev.Perf
{
    /// <summary>
    /// One row of the counter catalogue the running Editor or player actually exposes.
    /// </summary>
    public struct CounterInfo
    {
        public string Category;
        public string Name;
        public string Unit;
        public string DataType;
        public string Flags;

        /// <summary>"Render/Draw Calls Count" — the key used everywhere else in this skill.</summary>
        public string Key { get { return Category + "/" + Name; } }

        public override string ToString()
        {
            return Key + "  unit=" + Unit + " type=" + DataType + " flags=" + Flags;
        }
    }

    /// <summary>
    /// CounterCatalog — list the ProfilerRecorder counters this build exposes, never recall them.
    ///
    /// Counter names differ between render pipelines, platforms, graphics backends and Unity
    /// versions. A name typed from memory produces a recorder whose Valid is false and whose
    /// LastValue is 0, which reads exactly like "this build does no draw calls".
    ///
    /// Drop into Assets/ (Runtime, no package needed). Then:
    ///   unity command eval 'return UnityDev.Perf.CounterCatalog.Grep("Draw");'
    ///   unity command eval 'return UnityDev.Perf.CounterCatalog.WriteCsv();'
    /// </summary>
    public static class CounterCatalog
    {
        /// <summary>Every counter currently available, sorted by category then name.</summary>
        public static List<CounterInfo> All()
        {
            var handles = new List<ProfilerRecorderHandle>();
            ProfilerRecorderHandle.GetAvailable(handles);

            var rows = new List<CounterInfo>(handles.Count);
            for (int i = 0; i < handles.Count; i++)
            {
                if (!handles[i].Valid) continue;
                ProfilerRecorderDescription d = ProfilerRecorderHandle.GetDescription(handles[i]);
                rows.Add(new CounterInfo
                {
                    Category = d.Category.Name,
                    Name = d.Name,
                    Unit = d.UnitType.ToString(),
                    DataType = d.DataType.ToString(),
                    Flags = d.Flags.ToString()
                });
            }

            rows.Sort(delegate (CounterInfo a, CounterInfo b)
            {
                int c = string.Compare(a.Category, b.Category, StringComparison.Ordinal);
                return c != 0 ? c : string.Compare(a.Name, b.Name, StringComparison.Ordinal);
            });
            return rows;
        }

        /// <summary>True when this exact category/name pair is available right now.</summary>
        public static bool Exists(string category, string name)
        {
            if (string.IsNullOrEmpty(name)) return false;
            List<CounterInfo> rows = All();
            for (int i = 0; i < rows.Count; i++)
            {
                bool categoryOk = string.IsNullOrEmpty(category) ||
                                  string.Equals(rows[i].Category, category, StringComparison.Ordinal);
                if (categoryOk && string.Equals(rows[i].Name, name, StringComparison.Ordinal))
                    return true;
            }
            return false;
        }

        /// <summary>
        /// Case-insensitive substring search over "Category/Name", returned as one printable
        /// string so it survives a round trip through `unity command eval`.
        /// </summary>
        public static string Grep(string substring)
        {
            List<CounterInfo> rows = All();
            var sb = new StringBuilder();
            int hits = 0;
            for (int i = 0; i < rows.Count; i++)
            {
                if (!string.IsNullOrEmpty(substring) &&
                    rows[i].Key.IndexOf(substring, StringComparison.OrdinalIgnoreCase) < 0)
                    continue;
                if (hits > 0) sb.Append('\n');
                sb.Append(rows[i].ToString());
                hits++;
            }
            if (hits == 0) return "no counter matches " + (substring ?? "(null)") +
                                  " in " + rows.Count + " available counters";
            return sb.ToString();
        }

        /// <summary>
        /// Write the whole catalogue as CSV and return the path. Default location is
        /// &lt;persistentDataPath&gt;/perf/counters.csv, which exists in the Editor and in a player.
        /// </summary>
        public static string WriteCsv(string path = null)
        {
            if (string.IsNullOrEmpty(path))
                path = Path.Combine(Application.persistentDataPath, "perf/counters.csv");

            string dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            List<CounterInfo> rows = All();
            var sb = new StringBuilder();
            sb.Append("category,name,unit,dataType,flags\n");
            for (int i = 0; i < rows.Count; i++)
            {
                sb.Append(Csv(rows[i].Category)).Append(',');
                sb.Append(Csv(rows[i].Name)).Append(',');
                sb.Append(Csv(rows[i].Unit)).Append(',');
                sb.Append(Csv(rows[i].DataType)).Append(',');
                sb.Append(Csv(rows[i].Flags)).Append('\n');
            }
            File.WriteAllText(path, sb.ToString());
            Debug.Log("[PERF] catalog counters=" + rows.Count + " path=" + path);
            return path;
        }

        /// <summary>
        /// Start a recorder and report whether it produced a real value, in one call. Use this
        /// before trusting a name: a counter that exists can still be flat zero on this
        /// instrument (a null graphics device has no draw calls to report).
        /// </summary>
        public static string Probe(string category, string name, int frames = 1)
        {
            if (frames < 1) frames = 1;
            using (ProfilerRecorder r = ProfilerRecorder.StartNew(
                       new ProfilerCategory(category), name, frames, ProfilerRecorderOptions.Default))
            {
                if (!r.Valid)
                    return category + "/" + name + " INVALID — not exposed on this build";
                return category + "/" + name + " valid unit=" + r.UnitType +
                       " lastValue=" + r.LastValue + " (0 on the first frame is normal)";
            }
        }

        private static string Csv(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            if (s.IndexOf(',') < 0 && s.IndexOf('"') < 0 && s.IndexOf('\n') < 0) return s;
            return "\"" + s.Replace("\"", "\"\"") + "\"";
        }
    }
}
