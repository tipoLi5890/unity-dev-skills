// BatchAudit.cs — one headless entry for the Editor audits that ship with only a menu item and a
// `public static string` method returning JSON (KitAudit.Audit, SortingAudit.Json, …).
// -executeMethod can only call a `static void` with no parameters; this is that method.
//
// Drop into any Editor folder. It references no audit: the audit is found by name at run time,
// so this file compiles in a project that holds none, some or all of them.
//
//   "$UNITY" -batchmode -projectPath . -logFile - \
//     -executeMethod UnityDev.Cli.BatchAudit.Run \
//     -audit KitAudit -folder Assets/Kit -grid 2 -out Logs/kit-audit.json
//
//   -audit <Type> or <Type.Method>   simple or full type name; the method defaults to the first
//                                    public static string method named Audit, Json or Run
//   -<parameter> <value>             each method parameter by its own name: -folder, -root, -grid,
//                                    -controller (an asset path, loaded as the parameter's type);
//                                    a parameter not given takes its default
//   -scene <Assets/….unity>          open this scene first, for the audits that read the open scene
//   -out <file.json>                 write the JSON there (else it is logged after "[BATCH-AUDIT] ")
//   -census                          accept a report that carries no verdict (exit 0 once written)
//
// The verdict is the report's own top-level field, read in this order: `pass` (gate/1),
// `ok`, then `verdict` ("green" / "failed" / anything else). Exit codes:
//   0  the verdict passed (or -census and the report has no verdict)
//   2  the verdict failed, or the report carries no verdict and -census was not given
//   3  nothing verified: the scene or an asset did not load, the audit threw or returned nothing
//   1  refused: a usage error, an unknown or ambiguous -audit, a required parameter not given
// The Editor itself also exits 1 on a compile error: grep the log for `error CS` first.
// Synchronous, so -quit is harmless; the method exits the Editor itself.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace UnityDev.Cli
{
    public static class BatchAudit
    {
        const string Tag = "[BATCH-AUDIT] ";
        static readonly string[] DefaultMethods = { "Audit", "Json", "Run" };

        /// <summary>-executeMethod UnityDev.Cli.BatchAudit.Run — flags and exit codes in the file header.</summary>
        public static void Run()
        {
            int code;
            try { code = Execute(Environment.GetCommandLineArgs()); }
            catch (Exception e)
            {
                Debug.LogError(Tag + "harness error: " + e);
                code = 3;
            }
            EditorApplication.Exit(code);
        }

        /// <summary>The same run without exiting, for a test or an eval. Returns the exit code.</summary>
        public static int Execute(string[] argv)
        {
            var flags = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            bool census = false;
            for (int i = 0; i < argv.Length; i++)
            {
                string a = argv[i];
                if (a == "-census") { census = true; continue; }
                if (a.Length > 1 && a[0] == '-' && i + 1 < argv.Length && !argv[i + 1].StartsWith("-"))
                    flags[a.Substring(1)] = argv[++i];
            }
            if (!flags.TryGetValue("audit", out string audit) || string.IsNullOrEmpty(audit))
                return Usage("-audit <Type> or <Type.Method> is required");

            if (!Resolve(audit, out Type type, out string methodName, out string why)) return Usage(why);
            MethodInfo method = Pick(type, methodName, flags, out why);
            if (method == null) return Usage(why);

            if (flags.TryGetValue("scene", out string scene))
            {
                if (!File.Exists(scene))
                {
                    Debug.LogError(Tag + $"-scene {scene}: no such file");
                    return 3;
                }
                EditorSceneManager.OpenScene(scene, OpenSceneMode.Single);
            }

            object[] values = new object[method.GetParameters().Length];
            foreach (ParameterInfo p in method.GetParameters())
            {
                if (!flags.TryGetValue(p.Name, out string raw))
                {
                    values[p.Position] = p.DefaultValue;
                    continue;
                }
                if (!Convert(raw, p.ParameterType, out object v, out bool notLoaded, out why))
                {
                    if (notLoaded) { Debug.LogError(Tag + $"-{p.Name}: {why}"); return 3; }
                    return Usage($"-{p.Name}: {why}");
                }
                values[p.Position] = v;
            }

            string label = type.FullName + "." + method.Name;
            string json;
            try { json = method.Invoke(null, values) as string; }
            catch (TargetInvocationException e)
            {
                Debug.LogError(Tag + $"{label} threw: {e.InnerException}");
                return 3;
            }
            if (string.IsNullOrWhiteSpace(json))
            {
                Debug.LogError(Tag + $"{label} returned nothing");
                return 3;
            }

            if (flags.TryGetValue("out", out string outPath))
            {
                string dir = Path.GetDirectoryName(outPath);
                if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                File.WriteAllText(outPath, json, new UTF8Encoding(false));
                Debug.Log(Tag + $"wrote {outPath}");
            }
            else
            {
                Debug.Log(Tag + json);
            }

            Dictionary<string, string> top = TopLevel(json);
            if (top == null)
            {
                Debug.LogError(Tag + $"{label} returned text that is not one JSON object");
                return 3;
            }
            string verdict;
            int code;
            if (top.TryGetValue("pass", out verdict) && (verdict == "true" || verdict == "false"))
                code = verdict == "true" ? 0 : 2;
            else if (top.TryGetValue("ok", out verdict) && (verdict == "true" || verdict == "false"))
                code = verdict == "true" ? 0 : 2;
            else if (top.TryGetValue("verdict", out verdict) && verdict.StartsWith("\""))
                code = verdict == "\"green\"" ? 0 : verdict == "\"failed\"" ? 2 : 3;
            else
            {
                verdict = "none";
                code = census ? 0 : 2;
                if (!census)
                    Debug.LogError(Tag + $"{label}: the report has no pass, ok or verdict field. It is a census, " +
                                   "not a gate: read the JSON, or pass -census to accept it unjudged");
            }
            Debug.Log(Tag + $"{label} verdict {verdict} exit {code}");
            return code;
        }

        // ---------------------------------------------------------------- resolution

        static bool Resolve(string audit, out Type type, out string method, out string why)
        {
            type = null;
            method = null;
            why = null;
            string typeName = audit;
            Type found = Find(audit, out string ambiguous);
            if (found == null && ambiguous == null && audit.Contains("."))
            {
                int dot = audit.LastIndexOf('.');
                typeName = audit.Substring(0, dot);
                method = audit.Substring(dot + 1);
                found = Find(typeName, out ambiguous);
            }
            if (ambiguous != null)
            {
                why = $"-audit {typeName} matches more than one type: {ambiguous} — give the full name";
                return false;
            }
            if (found == null)
            {
                why = $"-audit {audit}: no such type in this project — is the audit's .cs under an Editor folder?";
                return false;
            }
            type = found;
            return true;
        }

        static Type Find(string name, out string ambiguous)
        {
            ambiguous = null;
            var hits = new List<Type>();
            foreach (Assembly asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type[] types;
                try { types = asm.GetTypes(); }
                catch (ReflectionTypeLoadException e) { types = e.Types; }
                foreach (Type t in types)
                    if (t != null && (t.FullName == name || (t.Name == name && !t.IsNested)))
                        hits.Add(t);
            }
            if (hits.Count > 1)
            {
                var names = new List<string>();
                foreach (Type t in hits) names.Add(t.FullName);
                ambiguous = string.Join(", ", names);
                return null;
            }
            return hits.Count == 1 ? hits[0] : null;
        }

        static MethodInfo Pick(Type type, string name, Dictionary<string, string> flags, out string why)
        {
            why = null;
            var candidates = new List<MethodInfo>();
            foreach (MethodInfo m in type.GetMethods(BindingFlags.Public | BindingFlags.Static))
            {
                if (m.ReturnType != typeof(string) || m.IsGenericMethodDefinition) continue;
                if (name != null ? m.Name == name : Array.IndexOf(DefaultMethods, m.Name) >= 0)
                    candidates.Add(m);
            }
            // Audit before Json before Run; among overloads, the first whose required parameters are all given.
            candidates.Sort((a, b) => Array.IndexOf(DefaultMethods, a.Name).CompareTo(Array.IndexOf(DefaultMethods, b.Name)));
            string missing = null;
            foreach (MethodInfo m in candidates)
            {
                bool ok = true;
                foreach (ParameterInfo p in m.GetParameters())
                    if (!p.HasDefaultValue && !flags.ContainsKey(p.Name)) { ok = false; missing = $"-{p.Name}"; break; }
                if (ok) return m;
            }
            why = candidates.Count == 0
                ? $"{type.FullName} has no public static string {(name ?? string.Join("/", DefaultMethods))}(…)"
                : $"{type.FullName}.{candidates[0].Name} needs {missing} ({Signature(candidates[0])})";
            return null;
        }

        static string Signature(MethodInfo m)
        {
            var parts = new List<string>();
            foreach (ParameterInfo p in m.GetParameters())
                parts.Add($"-{p.Name} <{p.ParameterType.Name}>" + (p.HasDefaultValue ? " optional" : ""));
            return string.Join(" ", parts);
        }

        /// <summary>A flag's text as the parameter's type. notLoaded: an asset path that did not load (exit 3).</summary>
        static bool Convert(string raw, Type t, out object value, out bool notLoaded, out string why)
        {
            value = null;
            notLoaded = false;
            why = null;
            CultureInfo inv = CultureInfo.InvariantCulture;
            if (t == typeof(string)) { value = raw; return true; }
            if (t == typeof(float) && float.TryParse(raw, NumberStyles.Float, inv, out float f)) { value = f; return true; }
            if (t == typeof(double) && double.TryParse(raw, NumberStyles.Float, inv, out double d)) { value = d; return true; }
            if (t == typeof(int) && int.TryParse(raw, NumberStyles.Integer, inv, out int i)) { value = i; return true; }
            if (t == typeof(bool) && bool.TryParse(raw, out bool b)) { value = b; return true; }
            if (t.IsEnum)
            {
                try { value = Enum.Parse(t, raw, true); return true; }
                catch (ArgumentException) { why = $"\"{raw}\" is not one of {string.Join(", ", Enum.GetNames(t))}"; return false; }
            }
            if (typeof(UnityEngine.Object).IsAssignableFrom(t))
            {
                value = AssetDatabase.LoadAssetAtPath(raw, t);
                if (value != null) return true;
                why = $"{raw} does not load as a {t.Name}";
                notLoaded = true;
                return false;
            }
            why = $"\"{raw}\" is not a {t.Name} (BatchAudit passes string, number, bool, enum and asset-path parameters)";
            return false;
        }

        // ---------------------------------------------------------------- the report

        /// <summary>
        /// The top-level members of one JSON object, each as its raw text ("true", "\"green\"",
        /// "{…}"). Null when the text is not one object. Strings and nesting are skipped, so a
        /// nested "ok" never reads as the report's.
        /// </summary>
        public static Dictionary<string, string> TopLevel(string json)
        {
            string s = json.Trim();
            if (s.Length < 2 || s[0] != '{' || s[s.Length - 1] != '}') return null;
            var top = new Dictionary<string, string>();
            int i = 1;
            while (i < s.Length - 1)
            {
                i = SkipSpace(s, i);
                if (s[i] == ',') { i++; continue; }
                if (s[i] == '}') break;
                if (s[i] != '"') return null;
                int keyEnd = EndOfString(s, i);
                if (keyEnd < 0) return null;
                string key = s.Substring(i + 1, keyEnd - i - 1);
                i = SkipSpace(s, keyEnd + 1);
                if (i >= s.Length || s[i] != ':') return null;
                i = SkipSpace(s, i + 1);
                int start = i, depth = 0;
                for (; i < s.Length; i++)
                {
                    char c = s[i];
                    if (c == '"') { i = EndOfString(s, i); if (i < 0) return null; continue; }
                    if (c == '{' || c == '[') depth++;
                    else if (c == '}' || c == ']')
                    {
                        if (depth == 0) break;
                        depth--;
                    }
                    else if (c == ',' && depth == 0) break;
                }
                top[key] = s.Substring(start, i - start).Trim();
            }
            return top;
        }

        static int SkipSpace(string s, int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
            return i;
        }

        static int EndOfString(string s, int open)
        {
            for (int i = open + 1; i < s.Length; i++)
            {
                if (s[i] == '\\') { i++; continue; }
                if (s[i] == '"') return i;
            }
            return -1;
        }

        static int Usage(string message)
        {
            Debug.LogError(Tag + "usage: " + message +
                           "\n  -executeMethod UnityDev.Cli.BatchAudit.Run -audit <Type[.Method]> " +
                           "[-<parameter> <value> …] [-scene Assets/x.unity] [-out report.json] [-census]");
            return 1;
        }
    }
}
