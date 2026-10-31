// SecondarySpec — the secondary/1 hand-off file (<name>.secondary.json, written beside the body FBX
// by the rig side): the chains of extra cc_ bones, their spring parameters and the body colliders.
// TryParse reads and checks it; SecondaryMotionSetup (Editor) builds the components from it.
// Runtime code, no Editor API, so a test or a runtime loader can use it too.
//
// A small JSON reader instead of JsonUtility: JsonUtility cannot read the nested `joints` arrays
// and cannot tell a missing field from a zero (inertia defaults to 1, not 0).
//
// Positions in the file (joints, parent_head, a sphere's center) are in the skeleton/1 frame:
// metres, +Z up, the character facing -Y. ToUnity converts one to the model's space. Everything the
// runtime uses hangs off bones; the positions only feed the setup's axis and scale self-check.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace UnityDev.SecondaryMotion
{
    [Serializable]
    public sealed class SecondarySpec
    {
        public const string Stamp = "secondary/1";

        public string schema, tool, character;
        public SecondaryChainSpec[] chains = new SecondaryChainSpec[0];
        public SecondaryColliderSpec[] colliders = new SecondaryColliderSpec[0];

        static readonly string[] Kinds = { "hood", "bag", "hem", "shorts_hem", "hair", "strap", "cloth", "prop" };

        /// <summary>skeleton/1 (x, y, z), +Z up and facing -Y, as Unity model space: (-x, z, -y).</summary>
        public static Vector3 ToUnity(Vector3 skeleton) => new Vector3(-skeleton.x, skeleton.z, -skeleton.y);

        /// <summary>Reads a secondary/1 file. False, with the reason, on a wrong stamp, a chain with
        /// no bones or no tip, a parameter out of range, or a collider name nobody declares. An empty
        /// chain list is valid (nothing loose on the body).</summary>
        public static bool TryParse(string json, out SecondarySpec spec, out string error)
        {
            spec = null;
            object rootObj;
            try { rootObj = MiniJson.Parse(json); }
            catch (FormatException e) { error = "not JSON: " + e.Message; return false; }
            if (!(rootObj is Dictionary<string, object> root)) { error = "not a JSON object"; return false; }

            var s = new SecondarySpec
            {
                schema = Str(root, "schema"),
                tool = Str(root, "tool"),
                character = Str(root, "character"),
            };
            if (s.schema != Stamp) { error = "schema is \"" + s.schema + "\", not \"" + Stamp + "\""; return false; }
            if (string.IsNullOrEmpty(s.character)) { error = "character is missing"; return false; }
            foreach (string key in new[] { "units", "up", "forward" })
            {
                string want = key == "units" ? "m" : key == "up" ? "+Z" : "-Y";
                string have = Str(root, key);
                if (have != null && have != want) { error = key + " is \"" + have + "\", secondary/1 is " + want; return false; }
            }

            var colliderNames = new HashSet<string>();
            var cols = new List<SecondaryColliderSpec>();
            foreach (object o in List(root, "colliders"))
            {
                if (!(o is Dictionary<string, object> d)) { error = "a collider is not an object"; return false; }
                var c = new SecondaryColliderSpec
                {
                    name = Str(d, "name"), shape = Str(d, "shape"), a = Str(d, "a"), b = Str(d, "b"),
                    aRole = Str(d, "a_role"), bRole = Str(d, "b_role"),
                    radius = Num(d, "radius", 0f), inset = Num(d, "inset", 0f),
                };
                string at = "collider " + (c.name ?? "#" + cols.Count);
                if (string.IsNullOrEmpty(c.name)) { error = at + ": no name"; return false; }
                if (!colliderNames.Add(c.name)) { error = at + ": declared twice"; return false; }
                if (c.shape != "sphere" && c.shape != "capsule") { error = at + ": shape must be sphere or capsule"; return false; }
                if (string.IsNullOrEmpty(c.a)) { error = at + ": no bone a"; return false; }
                if (c.shape == "capsule" && string.IsNullOrEmpty(c.b)) { error = at + ": a capsule needs bone b"; return false; }
                if (!(c.radius > 0f)) { error = at + ": radius must be > 0"; return false; }
                if (c.inset < 0f || c.inset > 0.5f) { error = at + ": inset must be 0..0.5"; return false; }
                if (d.ContainsKey("center"))
                {
                    if (!Vec(d["center"], out c.center)) { error = at + ": center is not [x, y, z]"; return false; }
                    c.hasCenter = true;
                }
                cols.Add(c);
            }
            s.colliders = cols.ToArray();

            var chainNames = new HashSet<string>();
            var boneOwner = new Dictionary<string, string>();
            var chains = new List<SecondaryChainSpec>();
            foreach (object o in List(root, "chains"))
            {
                if (!(o is Dictionary<string, object> d)) { error = "a chain is not an object"; return false; }
                var c = new SecondaryChainSpec
                {
                    name = Str(d, "name"), kind = Str(d, "kind"), parent = Str(d, "parent"),
                    parentRole = Str(d, "parent_role"),
                    radius = Num(d, "radius", float.NaN), stiffness = Num(d, "stiffness", float.NaN),
                    drag = Num(d, "drag", float.NaN), gravity = Num(d, "gravity", float.NaN),
                    wind = Num(d, "wind", 0f), inertia = Num(d, "inertia", 1f),
                    maxAngleDeg = Num(d, "max_angle_deg", float.NaN),
                };
                string at = "chain " + (c.name ?? "#" + chains.Count);
                if (string.IsNullOrEmpty(c.name)) { error = at + ": no name"; return false; }
                if (!chainNames.Add(c.name)) { error = at + ": declared twice"; return false; }
                if (Array.IndexOf(Kinds, c.kind) < 0) { error = at + ": kind \"" + c.kind + "\" is not one of " + string.Join(", ", Kinds); return false; }
                if (string.IsNullOrEmpty(c.parent)) { error = at + ": no parent bone"; return false; }

                var bones = new List<string>();
                foreach (object b in List(d, "bones")) bones.Add(b as string);
                c.bones = bones.ToArray();
                if (c.bones.Length == 0) { error = at + ": no bones"; return false; }
                if (c.bones.Length < 2) { error = at + ": one bone and no tip — the rig side adds an unweighted cc_<chain>_end tip"; return false; }
                foreach (string b in c.bones)
                {
                    if (string.IsNullOrEmpty(b) || !b.StartsWith("cc_", StringComparison.Ordinal))
                        { error = at + ": bone \"" + b + "\" is not a cc_ bone"; return false; }
                    if (boneOwner.TryGetValue(b, out string other)) { error = at + ": bone " + b + " is also in chain " + other; return false; }
                    boneOwner[b] = c.name;
                }
                if (c.bones[c.bones.Length - 1].IndexOf("_end", StringComparison.Ordinal) < 0)
                    { error = at + ": the last bone " + c.bones[c.bones.Length - 1] + " is not a tip (cc_<chain>_end.<side>)"; return false; }

                if (!InRange(c.stiffness, 0f, 1f)) { error = at + ": stiffness must be 0..1"; return false; }
                if (!InRange(c.drag, 0f, 1f)) { error = at + ": drag must be 0..1"; return false; }
                if (!InRange(c.inertia, 0f, 1f)) { error = at + ": inertia must be 0..1"; return false; }
                if (!(c.gravity >= 0f)) { error = at + ": gravity must be >= 0"; return false; }
                if (!(c.wind >= 0f)) { error = at + ": wind must be >= 0"; return false; }
                if (!(c.radius >= 0f)) { error = at + ": radius must be >= 0"; return false; }
                if (!(c.maxAngleDeg > 0f && c.maxAngleDeg <= 180f)) { error = at + ": max_angle_deg must be in (0, 180]"; return false; }

                if (d.ContainsKey("colliders"))
                {
                    c.hasColliders = true;
                    var names = new List<string>();
                    foreach (object n in List(d, "colliders"))
                    {
                        string cn = n as string;
                        if (!colliderNames.Contains(cn)) { error = at + ": collider \"" + cn + "\" is not declared"; return false; }
                        names.Add(cn);
                    }
                    c.colliders = names.ToArray();
                }
                if (d.ContainsKey("parent_head"))
                {
                    if (!Vec(d["parent_head"], out c.parentHead)) { error = at + ": parent_head is not [x, y, z]"; return false; }
                    c.hasParentHead = true;
                }
                if (d.ContainsKey("joints"))
                {
                    var joints = new List<Vector3>();
                    foreach (object j in List(d, "joints"))
                    {
                        if (!Vec(j, out Vector3 v)) { error = at + ": a joint is not [x, y, z]"; return false; }
                        joints.Add(v);
                    }
                    if (joints.Count != c.bones.Length) { error = at + ": " + joints.Count + " joints for " + c.bones.Length + " bones"; return false; }
                    c.joints = joints.ToArray();
                }
                chains.Add(c);
            }
            s.chains = chains.ToArray();       // empty is valid: the body has nothing loose
            spec = s;
            error = null;
            return true;
        }

        static bool InRange(float v, float lo, float hi) => v >= lo && v <= hi;   // NaN fails

        static string Str(Dictionary<string, object> d, string key) =>
            d.TryGetValue(key, out object v) ? v as string : null;

        static float Num(Dictionary<string, object> d, string key, float fallback) =>
            d.TryGetValue(key, out object v) && v is double x ? (float)x : fallback;

        static readonly List<object> Empty = new List<object>();
        static List<object> List(Dictionary<string, object> d, string key) =>
            d.TryGetValue(key, out object v) && v is List<object> l ? l : Empty;

        static bool Vec(object o, out Vector3 v)
        {
            v = Vector3.zero;
            if (!(o is List<object> l) || l.Count != 3) return false;
            for (int i = 0; i < 3; i++)
            {
                if (!(l[i] is double x)) return false;
                v[i] = (float)x;
            }
            return true;
        }
    }

    [Serializable]
    public sealed class SecondaryChainSpec
    {
        public string name, kind, parent, parentRole;
        public string[] bones = new string[0];
        public float radius, stiffness, drag, gravity, wind, inertia = 1f, maxAngleDeg;
        /// <summary>False: the chain tests every collider. True: only <see cref="colliders"/>.</summary>
        public bool hasColliders;
        public string[] colliders = new string[0];
        public bool hasParentHead;
        public Vector3 parentHead;
        /// <summary>Rest heads, skeleton/1 frame; null when the file leaves them out.</summary>
        public Vector3[] joints;
    }

    [Serializable]
    public sealed class SecondaryColliderSpec
    {
        public string name, shape, a, b, aRole, bRole;
        public float radius, inset;
        public bool hasCenter;
        public Vector3 center;
    }

    /// <summary>Just enough JSON: objects, arrays, numbers (double), strings, true/false/null.</summary>
    static class MiniJson
    {
        public static object Parse(string text)
        {
            if (text == null) throw new FormatException("empty");
            int i = 0;
            object v = Value(text, ref i);
            Ws(text, ref i);
            if (i != text.Length) throw new FormatException("trailing text at " + i);
            return v;
        }

        static void Ws(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }

        static object Value(string s, ref int i)
        {
            Ws(s, ref i);
            if (i >= s.Length) throw new FormatException("unexpected end");
            char c = s[i];
            if (c == '{') return Obj(s, ref i);
            if (c == '[') return Arr(s, ref i);
            if (c == '"') return Strng(s, ref i);
            if (Lit(s, ref i, "true")) return true;
            if (Lit(s, ref i, "false")) return false;
            if (Lit(s, ref i, "null")) return null;
            return Number(s, ref i);
        }

        static bool Lit(string s, ref int i, string word)
        {
            if (string.CompareOrdinal(s, i, word, 0, word.Length) != 0) return false;
            i += word.Length;
            return true;
        }

        static Dictionary<string, object> Obj(string s, ref int i)
        {
            var d = new Dictionary<string, object>();
            i++;
            Ws(s, ref i);
            if (i < s.Length && s[i] == '}') { i++; return d; }
            while (true)
            {
                Ws(s, ref i);
                if (i >= s.Length || s[i] != '"') throw new FormatException("expected a key at " + i);
                string key = Strng(s, ref i);
                Ws(s, ref i);
                if (i >= s.Length || s[i] != ':') throw new FormatException("expected ':' at " + i);
                i++;
                d[key] = Value(s, ref i);
                Ws(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == '}') { i++; return d; }
                throw new FormatException("expected ',' or '}' at " + i);
            }
        }

        static List<object> Arr(string s, ref int i)
        {
            var l = new List<object>();
            i++;
            Ws(s, ref i);
            if (i < s.Length && s[i] == ']') { i++; return l; }
            while (true)
            {
                l.Add(Value(s, ref i));
                Ws(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == ']') { i++; return l; }
                throw new FormatException("expected ',' or ']' at " + i);
            }
        }

        static string Strng(string s, ref int i)
        {
            var sb = new StringBuilder();
            i++;
            while (i < s.Length)
            {
                char c = s[i++];
                if (c == '"') return sb.ToString();
                if (c != '\\') { sb.Append(c); continue; }
                if (i >= s.Length) break;
                char e = s[i++];
                switch (e)
                {
                    case 'n': sb.Append('\n'); break;
                    case 't': sb.Append('\t'); break;
                    case 'r': sb.Append('\r'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'u':
                        if (i + 4 > s.Length) throw new FormatException("bad \\u escape");
                        sb.Append((char)int.Parse(s.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture));
                        i += 4;
                        break;
                    default: sb.Append(e); break;
                }
            }
            throw new FormatException("unterminated string");
        }

        static double Number(string s, ref int i)
        {
            int start = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            if (i == start) throw new FormatException("unexpected '" + s[i] + "' at " + i);
            if (!double.TryParse(s.Substring(start, i - start), NumberStyles.Float, CultureInfo.InvariantCulture, out double v))
                throw new FormatException("bad number at " + start);
            return v;
        }
    }
}
