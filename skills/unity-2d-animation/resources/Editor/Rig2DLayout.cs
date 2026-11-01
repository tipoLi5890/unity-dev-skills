// Rig2DLayout.cs — the geometry half of AutoRig2D, with no importer in it: a skeleton from layer
// names and positions, a grid mesh per layer, two-bone distance weights, and a reader for the
// nested rig.json a layer splitter writes. AutoRig2D feeds it the layers and writes the result
// through the data providers; the EditMode tests drive it the same way.
//
// Space: document pixels, origin bottom-left, y up (the space CharacterData uses). rig.json is
// in image pixels, y down; ReadRigJson flips it.
//
// Naming convention. Layers are matched case-insensitively; the side is `_L` / `_R` (front view,
// the character's own sides) or `_near` / `_far` (side view), and bones keep it. Bones are
// named for the joint they turn at, so no bone shares a layer's name (the importer renames a
// bone that does, to head_1, and nothing that looks for "head" finds it).
//   layer                                    bones it is weighted to
//   torso | body                             hips → chest (hips sits in the pelvis if any)
//   pelvis                                   hips
//   head                                     neck (from the neck to the top of head and hair)
//   eyes_* eye_* mouth_* brow* nose* blush*  face, a child of neck
//   arm_X  or  upperarm_X + forearm_X        shoulder_X → elbow_X (shoulder at the end nearer
//                                            the neck)
//   hand_X                                   elbow_X, wrist_X
//   leg_X  or  thigh_X + shin_X               hip_X → knee_X (hip at the end nearer hips)
//   foot_X                                   knee_X, ankle_X
//   hair* bag* tail* scarf* cape* ponytail* ribbon*   <layer>_pivot, hung from the item's top
//                                            (hair from neck, the rest from hips/chest/neck)
//   anything else                            rigid to the nearest bone
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using UnityEngine;

namespace UnityDev.Rig2D
{
    /// <summary>One layer: its document rectangle and its alpha, row 0 at the bottom.</summary>
    public sealed class Layer2D
    {
        public string name;
        public RectInt rect;          // document pixels, y up
        public bool[] mask;           // rect.width * rect.height, any visible alpha (the mesh covers these)
        public bool[] solid;          // alpha at least half (what a mesh must not cut off); null: mask

        int _count = -1;
        Vector2 _centroid, _axis;

        public bool At(int x, int y) => x >= 0 && y >= 0 && x < rect.width && y < rect.height && mask[y * rect.width + x];

        public int Count { get { Stats(); return _count; } }
        public Vector2 Centroid { get { Stats(); return _centroid; } }
        /// <summary>Unit principal axis of the opaque pixels.</summary>
        public Vector2 Axis { get { Stats(); return _axis; } }

        void Stats()
        {
            if (_count >= 0) return;
            double sx = 0, sy = 0; int n = 0;
            for (int y = 0; y < rect.height; y++)
                for (int x = 0; x < rect.width; x++)
                    if (mask[y * rect.width + x]) { sx += x; sy += y; n++; }
            _count = n;
            if (n == 0) { _centroid = rect.center; _axis = Vector2.up; return; }
            double mx = sx / n, my = sy / n, cxx = 0, cyy = 0, cxy = 0;
            for (int y = 0; y < rect.height; y++)
                for (int x = 0; x < rect.width; x++)
                    if (mask[y * rect.width + x]) { double dx = x - mx, dy = y - my; cxx += dx * dx; cyy += dy * dy; cxy += dx * dy; }
            double ang = 0.5 * Math.Atan2(2 * cxy, cxx - cyy);
            _axis = new Vector2((float)Math.Cos(ang), (float)Math.Sin(ang));
            _centroid = new Vector2(rect.x + (float)mx + 0.5f, rect.y + (float)my + 0.5f);
        }

        public float MinY => rect.y;
        public float MaxY => rect.y + rect.height;

        /// <summary>Opaque pixels as document points (pixel centres).</summary>
        public IEnumerable<Vector2> Points()
        {
            for (int y = 0; y < rect.height; y++)
                for (int x = 0; x < rect.width; x++)
                    if (mask[y * rect.width + x]) yield return new Vector2(rect.x + x + 0.5f, rect.y + y + 0.5f);
        }
    }

    public sealed class Bone2D
    {
        public string name, parent;   // parent "" or null: a root
        public Vector2 head, tail;    // document pixels, y up
        public Bone2D(string name, string parent, Vector2 head, Vector2 tail) { this.name = name; this.parent = parent; this.head = head; this.tail = tail; }
    }

    /// <summary>A layer's mesh: document-pixel vertices, triangles, and up to two weights per
    /// vertex as indices into <see cref="bones"/>.</summary>
    public sealed class Part2D
    {
        public string name;
        public string[] bones;
        public Vector2[] vertices;
        public int[] indices;
        public BoneWeight[] weights;
    }

    public static class Rig2DLayout
    {
        static readonly string[] FaceHeads = { "eyes", "eye", "mouth", "brow", "brows", "nose", "blush", "face" };
        static readonly string[] SpringHeads = { "hair", "bag", "tail", "scarf", "cape", "ponytail", "ribbon" };
        static readonly string[] SideTokens = { "l", "r", "front", "back", "near", "far", "upper", "lower" };

        public static string Lower(string s) => (s ?? "").Trim().ToLowerInvariant();
        static string Head(string name) { string n = Lower(name); int i = n.IndexOf('_'); return i < 0 ? n : n.Substring(0, i); }

        /// <summary>The side suffix as bones spell it: "L", "R" (a front view: the character's
        /// own left and right), "near", "far" (a side view), or "".</summary>
        public static string Side(string name)
        {
            string n = Lower(name);
            if (n.EndsWith("_l")) return "L";
            if (n.EndsWith("_r")) return "R";
            if (n.EndsWith("_near")) return "near";
            if (n.EndsWith("_far")) return "far";
            return "";
        }

        public static bool IsFace(string name) => FaceHeads.Contains(Head(name));
        public static string PivotName(string layer) => Lower(layer) + "_pivot";

        // The first layer splitter named bones after the parts; the importer renames a bone that
        // shares a layer's name, so those names are mapped to the joint names here.
        static readonly (string from, string to)[] Legacy =
        {
            ("head", "neck"), ("hair", "hair_front_pivot"), ("upperarm_", "shoulder_"), ("forearm_", "elbow_"),
            ("hand_", "wrist_"), ("thigh_", "hip_"), ("shin_", "knee_"), ("foot_", "ankle_"),
        };

        /// <summary>Maps the old part-named bones to joint names, then gives any bone that still
        /// shares a layer's name a `_bone` suffix. Part bone lists follow. Notes list each rename.</summary>
        public static void NormalizeBoneNames(List<Bone2D> bones, Dictionary<string, Part2D> parts, ICollection<string> layers, List<string> notes)
        {
            var layerSet = new HashSet<string>(layers, StringComparer.Ordinal);
            var map = new Dictionary<string, string>();
            foreach (Bone2D b in bones)
            {
                string to = b.name;
                foreach (var (from, rename) in Legacy)
                    if (from.EndsWith("_") ? b.name.StartsWith(from) && Side(b.name) != "" : b.name == from) { to = from.EndsWith("_") ? rename + b.name.Substring(from.Length) : rename; break; }
                if (layerSet.Contains(to)) to += "_bone";
                if (to != b.name) { map[b.name] = to; notes.Add($"bone {b.name} renamed {to}"); }
            }
            if (map.Count == 0) return;
            string M(string x) => x != null && map.TryGetValue(x, out string y) ? y : x;
            foreach (Bone2D b in bones) { b.name = M(b.name); b.parent = M(b.parent); }
            foreach (Part2D p in parts.Values) p.bones = p.bones.Select(M).ToArray();
        }
        public static bool IsSpring(string name) => SpringHeads.Any(h => Lower(name).StartsWith(h));

        /// <summary>Face layers that are states of one swappable part: `prefix_state` where another
        /// layer shares the prefix, the prefix is a face part and the last token is not a side
        /// (eyes_open / eyes_closed, mouth_closed / mouth_open, eye_L_open …). Category = prefix,
        /// label = last token. Body layers never swap: bag_strap and bag_body are two parts.</summary>
        public static SortedDictionary<string, List<(string label, string layer)>> SwapGroups(IEnumerable<string> layerNames)
        {
            var g = new SortedDictionary<string, List<(string, string)>>(StringComparer.Ordinal);
            foreach (string name in layerNames)
            {
                int i = name.LastIndexOf('_');
                if (i <= 0 || i == name.Length - 1) continue;
                string label = name.Substring(i + 1);
                if (SideTokens.Contains(Lower(label))) continue;
                string cat = name.Substring(0, i);
                if (!IsFace(cat)) continue;
                if (!g.TryGetValue(cat, out var list)) g[cat] = list = new List<(string, string)>();
                list.Add((label, name));
            }
            foreach (string k in g.Keys.ToList()) if (g[k].Count < 2) g.Remove(k);
            return g;
        }

        // ------------------------------------------------------------------ skeleton

        static Layer2D Find(IList<Layer2D> layers, params string[] names)
        {
            foreach (string n in names)
                foreach (Layer2D l in layers)
                    if (Lower(l.name) == n) return l;
            return null;
        }

        /// <summary>Centroid of the pixels whose position along the limb, 0 at `from`'s end and
        /// 1 at the other, lies within ±band of s. Follows a bent limb where the axis would not.</summary>
        static Vector2 Along(Layer2D l, Vector2 from, float s, float band = 0.05f)
        {
            Vector2 u = l.Axis, c = l.Centroid;
            float t0 = float.MaxValue, t1 = float.MinValue;
            foreach (Vector2 p in l.Points()) { float t = Vector2.Dot(p - c, u); t0 = Mathf.Min(t0, t); t1 = Mathf.Max(t1, t); }
            if (t0 > t1) return c;
            // orient so s = 0 is the end nearer `from`
            bool flip = Vector2.Distance(c + u * t1, from) < Vector2.Distance(c + u * t0, from);
            float len = Mathf.Max(t1 - t0, 1e-3f);
            Vector2 sum = Vector2.zero; int n = 0;
            foreach (Vector2 p in l.Points())
            {
                float t = (Vector2.Dot(p - c, u) - t0) / len;
                if (flip) t = 1f - t;
                if (Mathf.Abs(t - s) <= band) { sum += p; n++; }
            }
            if (n > 0) return sum / n;
            float tt = flip ? t1 - s * len : t0 + s * len;
            return c + u * tt;
        }

        static float Length(Layer2D l)
        {
            Vector2 u = l.Axis, c = l.Centroid;
            float t0 = float.MaxValue, t1 = float.MinValue;
            foreach (Vector2 p in l.Points()) { float t = Vector2.Dot(p - c, u); t0 = Mathf.Min(t0, t); t1 = Mathf.Max(t1, t); }
            return Mathf.Max(t1 - t0, 1f);
        }

        static float Width(Layer2D l) => l.Count / Length(l);

        /// <summary>Centroid of the 5 % of pixels farthest from `from`: a hand's fingertips, a toe.</summary>
        static Vector2 FarTip(Layer2D l, Vector2 from)
        {
            var d = l.Points().Select(p => (p, (p - from).sqrMagnitude)).OrderByDescending(x => x.Item2).ToList();
            if (d.Count == 0) return l.Centroid;
            int k = Mathf.Max(1, d.Count / 20);
            Vector2 s = Vector2.zero;
            for (int i = 0; i < k; i++) s += d[i].p;
            return s / k;
        }

        /// <summary>Skeleton from layer names and positions. Notes say what was guessed or missing;
        /// a null return means there is no torso to hang a skeleton from.</summary>
        public static List<Bone2D> InferBones(IList<Layer2D> layers, List<string> notes)
        {
            var bones = new List<Bone2D>();
            Layer2D torso = Find(layers, "torso", "body");
            if (torso == null) { notes.Add("no torso layer (torso or body): nothing to hang a skeleton from"); return null; }
            Layer2D pelvis = Find(layers, "pelvis");
            Layer2D head = Find(layers, "head");
            float th = torso.MaxY - torso.MinY;
            float cx = torso.Centroid.x;

            Vector2 neck = head != null
                ? new Vector2(head.Centroid.x, head.MinY + 0.08f * (head.MaxY - head.MinY))
                : new Vector2(cx, torso.MaxY);
            Vector2 chestHead = new Vector2(cx, torso.MinY + (pelvis != null ? 0.40f : 0.45f) * th);
            Vector2 hipsHead = pelvis != null ? pelvis.Centroid : new Vector2(cx, torso.MinY + 0.1f * th);
            bones.Add(new Bone2D("hips", "", hipsHead, chestHead));
            bones.Add(new Bone2D("chest", "hips", chestHead, neck));

            if (head != null)
            {
                float top = head.MaxY;
                foreach (Layer2D l in layers) if (IsSpring(l.name) && Lower(l.name).StartsWith("hair")) top = Mathf.Max(top, l.MaxY);
                bones.Add(new Bone2D("neck", "chest", neck, new Vector2(head.Centroid.x, top)));
                var face = layers.Where(l => IsFace(l.name)).ToList();
                if (face.Count > 0)
                {
                    Vector2 c = Vector2.zero;
                    foreach (Layer2D l in face) c += l.Centroid;
                    c /= face.Count;
                    bones.Add(new Bone2D("face", "neck", c, c + Vector2.up * 0.1f * (head.MaxY - head.MinY)));
                }
            }
            else notes.Add("no head layer: no head or face bone");

            foreach (string side in new[] { "L", "R", "near", "far" })
                if (layers.Any(l => Side(l.name) == side))
                {
                    Limb(layers, bones, notes, side, true);
                    Limb(layers, bones, notes, side, false);
                }

            // spring items hang from their top: hair from the head, the rest from the nearest of
            // hips, chest and head (a bag beside the hand still rides on the body)
            var trunk = bones.Where(b => b.name == "hips" || b.name == "chest" || b.name == "neck").ToList();
            foreach (Layer2D l in layers)
            {
                if (!IsSpring(l.name) || l.Count == 0) continue;
                float h = l.MaxY - l.MinY;
                var pivot = new Vector2(l.Centroid.x, l.MaxY - 0.15f * h);
                var tip = new Vector2(l.Centroid.x, l.MinY + 0.05f * h);
                string parent = Lower(l.name).StartsWith("hair") && trunk.Any(b => b.name == "neck") ? "neck" : Nearest(trunk, pivot).name;
                bones.Add(new Bone2D(PivotName(l.name), parent, pivot, tip));
            }
            return bones;
        }

        static void Limb(IList<Layer2D> layers, List<Bone2D> bones, List<string> notes, string s, bool arm)
        {
            string up = arm ? "shoulder_" + s : "hip_" + s, lo = arm ? "elbow_" + s : "knee_" + s, end = arm ? "wrist_" + s : "ankle_" + s;
            Layer2D whole = arm ? Find(layers, "arm_" + Lower(s)) : Find(layers, "leg_" + Lower(s));
            Layer2D upper = arm ? Find(layers, "upperarm_" + Lower(s), "upper_arm_" + Lower(s)) : Find(layers, "thigh_" + Lower(s), "upperleg_" + Lower(s));
            Layer2D lower = arm ? Find(layers, "forearm_" + Lower(s), "lowerarm_" + Lower(s)) : Find(layers, "shin_" + Lower(s), "lowerleg_" + Lower(s), "calf_" + Lower(s));
            Layer2D tipL = Find(layers, (arm ? "hand_" : "foot_") + Lower(s));
            string parent = arm ? "chest" : "hips";
            Bone2D anchorBone = bones.First(b => b.name == parent);
            Vector2 anchor = arm ? anchorBone.tail : anchorBone.head;
            Vector2 j0, j1, j2;
            if (whole != null)
            {
                float L = Length(whole), w = Width(whole);
                float fi = Mathf.Min(0.5f * w, 0.2f * L) / L, fd = Mathf.Min(0.4f * w, 0.15f * L) / L;
                j0 = Along(whole, anchor, fi);
                j2 = Along(whole, anchor, 1f - fd);
                j1 = Along(whole, anchor, 0.5f * (fi + 1f - fd));
            }
            else if (upper != null && lower != null)
            {
                float Lu = Length(upper), wu = Width(upper), Ll = Length(lower), wl = Width(lower);
                j0 = Along(upper, anchor, Mathf.Min(0.5f * wu, 0.2f * Lu) / Lu);
                Vector2 uEnd = Along(upper, anchor, 1f - Mathf.Min(0.4f * wu, 0.15f * Lu) / Lu);
                Vector2 lStart = Along(lower, uEnd, Mathf.Min(0.4f * wl, 0.15f * Ll) / Ll);
                j1 = 0.5f * (uEnd + lStart);
                j2 = Along(lower, j1, 1f - Mathf.Min(0.4f * wl, 0.15f * Ll) / Ll);
            }
            else
            {
                if (tipL != null) bones.Add(new Bone2D(end, parent, Along(tipL, anchor, 0.1f), FarTip(tipL, anchor)));
                if (upper != null || lower != null) notes.Add($"{(arm ? "arm" : "leg")} {s}: upper and lower layers must both exist; the one present is rigid");
                return;
            }
            bones.Add(new Bone2D(up, parent, j0, j1));
            bones.Add(new Bone2D(lo, up, j1, j2));
            if (tipL != null) bones.Add(new Bone2D(end, lo, j2, FarTip(tipL, j2)));
        }

        static Bone2D Nearest(IEnumerable<Bone2D> bones, Vector2 p) =>
            bones.OrderBy(b => SegmentDistance(p, b.head, b.tail)).First();

        /// <summary>Which bones a layer is weighted to. Every name returned exists in `bones`.</summary>
        public static string[] PartBones(Layer2D layer, IDictionary<string, Bone2D> bones)
        {
            string n = Lower(layer.name), s = Side(layer.name), pivot = PivotName(layer.name);
            var want = new List<string>();
            if (n == "torso" || n == "body") want.AddRange(new[] { "hips", "chest" });
            else if (n == "pelvis") want.Add("hips");
            else if (n == "head") want.Add("neck");
            else if (IsFace(n)) want.Add(bones.ContainsKey("face") ? "face" : "neck");
            else if (IsSpring(n) && bones.ContainsKey(pivot)) { want.Add(bones[pivot].parent); want.Add(pivot); }
            else if (s != "" && (n.StartsWith("arm_") || n.StartsWith("upperarm") || n.StartsWith("upper_arm") || n.StartsWith("forearm") || n.StartsWith("lowerarm")))
                want.AddRange(new[] { "shoulder_" + s, "elbow_" + s });
            else if (s != "" && n.StartsWith("hand_")) want.AddRange(new[] { "elbow_" + s, "wrist_" + s });
            else if (s != "" && (n.StartsWith("leg_") || n.StartsWith("thigh") || n.StartsWith("upperleg") || n.StartsWith("shin") || n.StartsWith("lowerleg") || n.StartsWith("calf")))
                want.AddRange(new[] { "hip_" + s, "knee_" + s });
            else if (s != "" && n.StartsWith("foot_")) want.AddRange(new[] { "knee_" + s, "ankle_" + s });
            var have = want.Where(b => !string.IsNullOrEmpty(b) && bones.ContainsKey(b)).Distinct().ToList();
            if (have.Count == 0) have.Add(Nearest(bones.Values, layer.Centroid).name);
            return have.ToArray();
        }

        // ------------------------------------------------------------------ mesh and weights

        /// <summary>A grid over the layer, one quad per cell that holds any opaque pixel. The cell
        /// is about a quarter of the part's width, so a limb bends over four rows of vertices.</summary>
        public static Part2D GridMesh(Layer2D l, string[] partBones, int cell = 0)
        {
            int w = l.rect.width, h = l.rect.height;
            if (cell <= 0) cell = Mathf.Clamp(Mathf.RoundToInt(Mathf.Sqrt(Mathf.Max(l.Count, 1)) / 12f), 4, 48);
            int gw = (w + cell - 1) / cell, gh = (h + cell - 1) / cell;
            var vid = new Dictionary<int, int>();
            var verts = new List<Vector2>();
            var tris = new List<int>();
            int V(int gx, int gy)
            {
                int key = gy * (gw + 1) + gx;
                if (vid.TryGetValue(key, out int i)) return i;
                vid[key] = verts.Count;
                verts.Add(new Vector2(l.rect.x + Mathf.Min(gx * cell, w), l.rect.y + Mathf.Min(gy * cell, h)));
                return verts.Count - 1;
            }
            for (int gy = 0; gy < gh; gy++)
                for (int gx = 0; gx < gw; gx++)
                {
                    bool any = false;
                    for (int y = gy * cell; y < Mathf.Min(h, (gy + 1) * cell) && !any; y++)
                        for (int x = gx * cell; x < Mathf.Min(w, (gx + 1) * cell); x++)
                            if (l.mask[y * w + x]) { any = true; break; }
                    if (!any) continue;
                    int a = V(gx, gy), b = V(gx + 1, gy), c = V(gx + 1, gy + 1), d = V(gx, gy + 1);
                    tris.AddRange(new[] { a, c, b, a, d, c });
                }
            return new Part2D { name = l.name, bones = partBones, vertices = verts.ToArray(), indices = tris.ToArray() };
        }

        /// <summary>Share of the layer's solid pixels within a pixel of the part's triangles. A
        /// mesh cuts off what it does not cover, so a rig file's mesh below 0.98 is replaced.</summary>
        public static float Coverage(Layer2D l, Part2D part)
        {
            int w = l.rect.width, h = l.rect.height;
            var hit = new bool[w * h];
            for (int t = 0; t + 2 < part.indices.Length; t += 3)
            {
                Vector2 a = part.vertices[part.indices[t]] - (Vector2)l.rect.position, b = part.vertices[part.indices[t + 1]] - (Vector2)l.rect.position,
                        c = part.vertices[part.indices[t + 2]] - (Vector2)l.rect.position;
                float den = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y);
                if (Mathf.Abs(den) < 1e-9f) continue;
                int x0 = Mathf.Max(0, Mathf.FloorToInt(Mathf.Min(a.x, Mathf.Min(b.x, c.x)))), x1 = Mathf.Min(w - 1, Mathf.CeilToInt(Mathf.Max(a.x, Mathf.Max(b.x, c.x))));
                int y0 = Mathf.Max(0, Mathf.FloorToInt(Mathf.Min(a.y, Mathf.Min(b.y, c.y)))), y1 = Mathf.Min(h - 1, Mathf.CeilToInt(Mathf.Max(a.y, Mathf.Max(b.y, c.y))));
                for (int y = y0; y <= y1; y++)
                    for (int x = x0; x <= x1; x++)
                    {
                        float px = x + 0.5f, py = y + 0.5f;
                        float l1 = ((b.y - c.y) * (px - c.x) + (c.x - b.x) * (py - c.y)) / den;
                        float l2 = ((c.y - a.y) * (px - c.x) + (a.x - c.x) * (py - c.y)) / den;
                        if (l1 >= -0.02f && l2 >= -0.02f && 1f - l1 - l2 >= -0.02f) hit[y * w + x] = true;
                    }
            }
            // solid pixels, with a pixel of slack for a mesh drawn along the edge
            bool[] solid = l.solid ?? l.mask;
            int on = 0, covered = 0;
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                {
                    if (!solid[y * w + x]) continue;
                    on++;
                    bool near = false;
                    for (int dy = -1; dy <= 1 && !near; dy++)
                        for (int dx = -1; dx <= 1; dx++)
                        {
                            int xx = x + dx, yy = y + dy;
                            if (xx >= 0 && yy >= 0 && xx < w && yy < h && hit[yy * w + xx]) { near = true; break; }
                        }
                    if (near) covered++;
                }
            return on == 0 ? 1f : covered / (float)on;
        }

        public static float SegmentDistance(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a;
            float t = ab.sqrMagnitude < 1e-9f ? 0f : Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude);
            return Vector2.Distance(p, a + ab * t);
        }

        /// <summary>Two-bone weights from the distance to each bone's segment, w ∝ 1/(d² + r²)²,
        /// the two largest kept and normalised. r is a fifth of the part's shortest side, so the
        /// blend across a joint is about as wide as the limb.</summary>
        public static void DistanceWeights(Part2D part, IDictionary<string, Bone2D> bones, float softness)
        {
            var bw = new BoneWeight[part.vertices.Length];
            float r2 = Mathf.Max(softness * softness, 1f);
            for (int v = 0; v < part.vertices.Length; v++)
            {
                int i0 = 0, i1 = 0; float w0 = -1, w1 = -1;
                for (int k = 0; k < part.bones.Length; k++)
                {
                    Bone2D b = bones[part.bones[k]];
                    float d = SegmentDistance(part.vertices[v], b.head, b.tail);
                    float q = d * d + r2;
                    float w = 1f / (q * q);
                    if (w > w0) { i1 = i0; w1 = w0; i0 = k; w0 = w; }
                    else if (w > w1) { i1 = k; w1 = w; }
                }
                if (w1 < 0) { w1 = 0; i1 = i0; }
                float sum = w0 + w1;
                float a = w0 / sum, c = w1 / sum;
                if (c < 0.02f) { a = 1f; c = 0f; i1 = i0; }
                bw[v] = new BoneWeight { boneIndex0 = i0, weight0 = a, boneIndex1 = i1, weight1 = c };
            }
            part.weights = bw;
        }

        public static Vector2Int[] BoundaryEdges(int[] tri)
        {
            var count = new Dictionary<(int, int), int>();
            for (int t = 0; t + 2 < tri.Length; t += 3)
                for (int e = 0; e < 3; e++)
                {
                    int a = tri[t + e], b = tri[t + (e + 1) % 3];
                    var key = a < b ? (a, b) : (b, a);
                    count[key] = count.TryGetValue(key, out int c) ? c + 1 : 1;
                }
            return count.Where(kv => kv.Value == 1).Select(kv => new Vector2Int(kv.Key.Item1, kv.Key.Item2)).ToArray();
        }

        // ------------------------------------------------------------------ rig.json

        /// <summary>What a rig file holds. View and facing are "" when it does not say.</summary>
        public sealed class RigFile
        {
            public List<Bone2D> bones = new List<Bone2D>();
            public Dictionary<string, Part2D> parts = new Dictionary<string, Part2D>(StringComparer.OrdinalIgnoreCase);
            public string view = "", facing = "";
        }

        /// <summary>Reads a layer splitter's rig file, in image pixels with y down, flipped here.
        /// rig2d/1 (layer_split.py): {"schema":"rig2d/1", "width", "height", "view", "facing",
        /// "bones":[{name, parent, hx, hy, tx, ty}], "parts":[{name, bones, verts:[x0,y0,..],
        /// indices, bw:[i0,w0,i1,w1 per vertex]}]}. The older nested form, {"canvas":[W,H],
        /// "bones":[{name, parent, head:[x,y], tail:[x,y]}], "parts":{layer:{bones, vertices:[[x,y]],
        /// indices, weights:[[[i,w],..]]}}}, is read too. Parts are optional; a layer they leave
        /// out is meshed here. Returns false with the reason in problems.</summary>
        public static bool ReadRigJson(string json, out RigFile rig, List<string> problems)
        {
            rig = new RigFile();
            object root;
            try { root = new MiniJson(json).Value(); }
            catch (Exception e) { problems.Add("rig.json: " + e.Message); return false; }
            if (!(root is Dictionary<string, object> o)) { problems.Add("rig.json: not an object"); return false; }
            float H;
            if (o.TryGetValue("height", out object hv) && hv is double) H = Num(hv);
            else if (o.TryGetValue("canvas", out object cv) && cv is List<object> canvas && canvas.Count == 2) H = Num(canvas[1]);
            else { problems.Add("rig.json: no height (rig2d/1) or canvas [W, H]"); return false; }
            if (o.TryGetValue("y_down", out object yd) && yd is bool down && !down) H = float.NaN;
            Vector2 P(float x, float y) => float.IsNaN(H) ? new Vector2(x, y) : new Vector2(x, H - y);
            Vector2 Pair(object xy) { var a = (List<object>)xy; return P(Num(a[0]), Num(a[1])); }
            if (o.TryGetValue("view", out object vw) && vw is string vs) rig.view = vs;
            if (o.TryGetValue("facing", out object fc) && fc is string fs) rig.facing = fs;
            var bones = rig.bones;
            try
            {
                foreach (object bo in (List<object>)o["bones"])
                {
                    var b = (Dictionary<string, object>)bo;
                    string parent = b.TryGetValue("parent", out object pa) ? pa as string ?? "" : "";
                    bones.Add(b.ContainsKey("hx")
                        ? new Bone2D((string)b["name"], parent, P(Num(b["hx"]), Num(b["hy"])), P(Num(b["tx"]), Num(b["ty"])))
                        : new Bone2D((string)b["name"], parent, Pair(b["head"]), Pair(b["tail"])));
                }
                var raw = new List<(string name, Dictionary<string, object> p)>();
                if (o.TryGetValue("parts", out object po) && po is Dictionary<string, object> pd)
                    foreach (var kv in pd) raw.Add((kv.Key, (Dictionary<string, object>)kv.Value));
                else if (po is List<object> pl)
                    foreach (object x in pl) { var d = (Dictionary<string, object>)x; raw.Add(((string)d["name"], d)); }
                foreach (var (name, p) in raw)
                {
                    var part = new Part2D { name = name, bones = ((List<object>)p["bones"]).Select(x => (string)x).ToArray() };
                    var pairs = new List<List<(int, float)>>();
                    if (p.ContainsKey("verts"))
                    {
                        var v = ((List<object>)p["verts"]).Select(Num).ToList();
                        part.vertices = Enumerable.Range(0, v.Count / 2).Select(i => P(v[2 * i], v[2 * i + 1])).ToArray();
                        var bw = ((List<object>)p["bw"]).Select(Num).ToList();
                        for (int i = 0; i + 3 < bw.Count; i += 4)
                            pairs.Add(new List<(int, float)> { ((int)bw[i], bw[i + 1]), ((int)bw[i + 2], bw[i + 3]) });
                    }
                    else
                    {
                        part.vertices = ((List<object>)p["vertices"]).Select(Pair).ToArray();
                        foreach (object w in (List<object>)p["weights"])
                            pairs.Add(((List<object>)w).Cast<List<object>>().Select(q => ((int)Num(q[0]), Num(q[1]))).ToList());
                    }
                    part.indices = ((List<object>)p["indices"]).Select(x => (int)Num(x)).ToArray();
                    if (part.vertices.Length == 0) continue;            // an empty part: meshed here
                    if (pairs.Count != part.vertices.Length) { problems.Add($"rig.json: {name}: {pairs.Count} weights for {part.vertices.Length} vertices"); return false; }
                    part.weights = new BoneWeight[pairs.Count];
                    for (int v = 0; v < pairs.Count; v++)
                    {
                        var two = pairs[v].OrderByDescending(q => q.Item2).Take(2).ToList();
                        if (two.Count == 1) two.Add((two[0].Item1, 0f));
                        float sum = two[0].Item2 + two[1].Item2;
                        if (sum <= 1e-6f) two[0] = (two[0].Item1, sum = 1f);
                        part.weights[v] = new BoneWeight { boneIndex0 = two[0].Item1, weight0 = two[0].Item2 / sum, boneIndex1 = two[1].Item1, weight1 = two[1].Item2 / sum };
                        if (two[0].Item1 >= part.bones.Length || two[1].Item1 >= part.bones.Length) { problems.Add($"rig.json: {name}: a weight names bone {Mathf.Max(two[0].Item1, two[1].Item1)} of {part.bones.Length}"); return false; }
                    }
                    rig.parts[name] = part;
                }
            }
            catch (Exception e) when (e is KeyNotFoundException || e is InvalidCastException || e is ArgumentOutOfRangeException || e is NullReferenceException)
            { problems.Add("rig.json: unexpected shape (" + e.GetType().Name + ")"); return false; }
            var names = new HashSet<string>(bones.Select(b => b.name));
            foreach (Bone2D b in bones)
                if (!string.IsNullOrEmpty(b.parent) && !names.Contains(b.parent)) problems.Add($"rig.json: bone {b.name} names a missing parent {b.parent}");
            foreach (Part2D p in rig.parts.Values)
                foreach (string b in p.bones) if (!names.Contains(b)) problems.Add($"rig.json: part {p.name} names a missing bone {b}");
            return problems.Count == 0;
        }

        static float Num(object o) => Convert.ToSingle(o, CultureInfo.InvariantCulture);

        /// <summary>Just enough JSON: objects, arrays, strings, numbers, true, false, null.</summary>
        sealed class MiniJson
        {
            readonly string s; int i;
            public MiniJson(string text) { s = text; }
            public object Value()
            {
                Ws();
                if (i >= s.Length) throw new FormatException("unexpected end");
                char c = s[i];
                if (c == '{')
                {
                    i++; var d = new Dictionary<string, object>();
                    Ws(); if (s[i] == '}') { i++; return d; }
                    while (true)
                    {
                        Ws(); string k = Str(); Ws(); Expect(':'); d[k] = Value(); Ws();
                        if (s[i] == ',') { i++; continue; }
                        Expect('}'); return d;
                    }
                }
                if (c == '[')
                {
                    i++; var a = new List<object>();
                    Ws(); if (s[i] == ']') { i++; return a; }
                    while (true)
                    {
                        a.Add(Value()); Ws();
                        if (s[i] == ',') { i++; continue; }
                        Expect(']'); return a;
                    }
                }
                if (c == '"') return Str();
                if (s.Length - i >= 4 && string.CompareOrdinal(s, i, "true", 0, 4) == 0) { i += 4; return true; }
                if (s.Length - i >= 5 && string.CompareOrdinal(s, i, "false", 0, 5) == 0) { i += 5; return false; }
                if (s.Length - i >= 4 && string.CompareOrdinal(s, i, "null", 0, 4) == 0) { i += 4; return null; }
                int st = i;
                while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
                if (st == i) throw new FormatException($"unexpected '{c}' at {i}");
                return double.Parse(s.Substring(st, i - st), CultureInfo.InvariantCulture);
            }
            void Ws() { while (i < s.Length && char.IsWhiteSpace(s[i])) i++; }
            void Expect(char c) { if (i >= s.Length || s[i] != c) throw new FormatException($"expected '{c}' at {i}"); i++; }
            string Str()
            {
                Expect('"'); var sb = new StringBuilder();
                while (i < s.Length && s[i] != '"')
                {
                    char c = s[i++];
                    if (c != '\\') { sb.Append(c); continue; }
                    char e = s[i++];
                    switch (e)
                    {
                        case 'n': sb.Append('\n'); break;
                        case 't': sb.Append('\t'); break;
                        case 'r': sb.Append('\r'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'u': sb.Append((char)Convert.ToInt32(s.Substring(i, 4), 16)); i += 4; break;
                        default: sb.Append(e); break;
                    }
                }
                Expect('"'); return sb.ToString();
            }
        }
    }
}
