// Re-measure shipped animation frames IN THE ENGINE, from their own bytes.
//
// The slicer that wrote a frame set also wrote numbers about it into frames.json, and a number
// produced by the tool that made the file has a conflict of interest. This fixture decodes every
// PNG a sequence ships and measures again — the faults it looks for all photograph as "art":
//
//   * frames sliced at their in-cell position: one idle pose 65-120 px apart sideways, which at
//     6 fps is a character teleporting, and which a contact sheet of single frames cannot show;
//   * a binary chroma key: 25-40% of the rim still the key's colour, opaque;
//   * feet on a different line in every frame; a frame cut by its canvas; one character drawn at
//     two sizes by two sheets; an importer pivot that is not the one the frames were seated on.
//
// Drop it into an EditMode test assembly (it needs nunit and, for the pivot test, UnityEditor),
// set the four constants under CONFIGURE, and run the suite. Every definition here is the one
// `codex-visual`'s scripts/sprite_ops.py states and audit_frames.py gates on. The two
// engine-independent classes below were run outside Unity: FrameMeasure against that script on
// 210 frames of 29 sequences — four of them out of register and binary-keyed — giving the same
// feet row, cut flag, fringe, tint and rim pixel counts and the same slip on every frame; and
// FrameSidecar on six real sidecars (seated, effect, kept, an older slicer's, another tool's, one
// with an empty cell). The NUnit half was compiled against the 6000.3 and 6000.4 reference
// assemblies, with and without UNITY_EDITOR, and has NOT been run in an Editor: run it once on
// your own art, and read the numbers it prints, before trusting a green.
//
// A sequence is a folder holding frames.json. Folders sliced by an older tool carry no
// `register` block; they fail Every_sequence_was_seated_on_purpose, which is the point.
using System;
using System.Collections.Generic;

/// <summary>Engine-independent measurements over one RGBA32 frame, row 0 = TOP.</summary>
public static class FrameMeasure
{
    public const int Solid = 127;          // alpha above this is the silhouette
    public const int OpenPx = 4;           // the core is the silhouette opened by this many px
    public const int RimPx = 2;            // the rim: this many px (4-connected) from transparency
    public const float FringeDist = 150f;  // RGB distance to the key under which a rim pixel is "mostly key"
    public const float TintShare = 0.25f;  // this far along the interior -> key line is "partly key"
    public const float TintOffLine = 0.35f;
    public const float SlipGain = 0.02f;   // an IoU gain under this is a flat optimum, not a slip

    /// <summary>The solid silhouette opened by OpenPx: anything thinner than ~8 px (a bat, a tail, a
    /// waving arm) drops out. A subject too thin to survive falls back to the plain silhouette.</summary>
    public static bool[] Core(byte[] rgba, int w, int h)
    {
        var m = new bool[w * h];
        int solid = 0;
        for (int i = 0; i < m.Length; i++) if (rgba[i * 4 + 3] > Solid) { m[i] = true; solid++; }
        bool[] c = Box(Box(m, w, h, OpenPx, true), w, h, OpenPx, false);
        int kept = 0;
        for (int i = 0; i < c.Length; i++) if (c[i]) kept++;
        return kept > 0.2f * solid ? c : m;
    }

    // Erosion (all) or dilation (any) by a (2r+1) square, separably. Outside the image is empty.
    static bool[] Box(bool[] src, int w, int h, int r, bool erode)
    {
        var tmp = new bool[w * h];
        var dst = new bool[w * h];
        for (int y = 0; y < h; y++)
        {
            int run = 0;                                   // set pixels inside the sliding window
            for (int x = -r; x < w + r; x++)
            {
                int add = x + r, drop = x - r - 1;
                if (add < w && src[y * w + add]) run++;
                if (drop >= 0 && drop < w && src[y * w + drop]) run--;
                if (x < 0 || x >= w) continue;
                tmp[y * w + x] = erode ? (run == 2 * r + 1) : (run > 0);
            }
        }
        for (int x = 0; x < w; x++)
        {
            int run = 0;
            for (int y = -r; y < h + r; y++)
            {
                int add = y + r, drop = y - r - 1;
                if (add < h && tmp[add * w + x]) run++;
                if (drop >= 0 && drop < h && tmp[drop * w + x]) run--;
                if (y < 0 || y >= h) continue;
                dst[y * w + x] = erode ? (run == 2 * r + 1) : (run > 0);
            }
        }
        return dst;
    }

    /// <summary>The feet line: the lowest row of a mask (top-down y), -1 when the mask is empty.</summary>
    public static int Bottom(bool[] mask, int w, int h)
    {
        for (int y = h - 1; y >= 0; y--)
            for (int x = 0; x < w; x++)
                if (mask[y * w + x]) return y;
        return -1;
    }

    public static int Top(bool[] mask, int w, int h)
    {
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                if (mask[y * w + x]) return y;
        return -1;
    }

    /// <summary>A solid pixel on the canvas border: the frame is cut off, not posed.</summary>
    public static bool CutByCanvas(byte[] rgba, int w, int h)
    {
        for (int x = 0; x < w; x++)
            if (rgba[x * 4 + 3] > Solid || rgba[((h - 1) * w + x) * 4 + 3] > Solid) return true;
        for (int y = 0; y < h; y++)
            if (rgba[(y * w) * 4 + 3] > Solid || rgba[(y * w + w - 1) * 4 + 3] > Solid) return true;
        return false;
    }

    /// <summary>
    /// The rim — visible pixels within RimPx (4-connected) of a fully transparent one — and how
    /// much of it the key still owns. fringe: within FringeDist of the key (mostly key).
    /// tint: on the straight line from the interior colour beside it to the key, TintShare of the
    /// way along or further (partly key). A rim that merely differs from the interior is off that
    /// line and is not counted.
    /// </summary>
    public static void Rim(byte[] rgba, int w, int h, byte kr, byte kg, byte kb,
                           out int fringe, out int tint, out int rim)
    {
        int n = w * h;
        var isRim = new bool[n];
        var known = new bool[n];                            // interior: visible and not rim
        fringe = tint = rim = 0;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                int i = y * w + x;
                if (rgba[i * 4 + 3] == 0) continue;
                bool near = false;
                for (int dy = -RimPx; dy <= RimPx && !near; dy++)
                {
                    int span = RimPx - Math.Abs(dy);
                    int yy = y + dy;
                    if (yy < 0 || yy >= h) continue;
                    for (int dx = -span; dx <= span; dx++)
                    {
                        int xx = x + dx;
                        if (xx < 0 || xx >= w) continue;
                        if (rgba[(yy * w + xx) * 4 + 3] == 0) { near = true; break; }
                    }
                }
                if (near) { isRim[i] = true; rim++; } else known[i] = true;
            }
        if (rim == 0) return;

        var col = new float[n * 3];
        for (int i = 0; i < n; i++)
        {
            col[i * 3] = rgba[i * 4]; col[i * 3 + 1] = rgba[i * 4 + 1]; col[i * 3 + 2] = rgba[i * 4 + 2];
        }
        // the interior colour beside each rim pixel: rings grown one pixel at a time, each new
        // pixel taking the mean of its already-known 8-neighbours (at most 8 rings)
        var fill = (float[])col.Clone();
        var todo = new List<int>();
        for (int i = 0; i < n; i++) if (isRim[i]) todo.Add(i);
        for (int pass = 0; pass < 8 && todo.Count > 0; pass++)
        {
            var got = new List<int>();
            var val = new List<float>();
            var rest = new List<int>();
            foreach (int i in todo)
            {
                int x = i % w, y = i / w, cnt = 0;
                float r = 0, g = 0, b = 0;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++)
                    {
                        if (dx == 0 && dy == 0) continue;
                        int xx = x + dx, yy = y + dy;
                        if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
                        int j = yy * w + xx;
                        if (!known[j]) continue;
                        r += fill[j * 3]; g += fill[j * 3 + 1]; b += fill[j * 3 + 2]; cnt++;
                    }
                if (cnt == 0) { rest.Add(i); continue; }
                got.Add(i); val.Add(r / cnt); val.Add(g / cnt); val.Add(b / cnt);
            }
            if (got.Count == 0) break;
            for (int k = 0; k < got.Count; k++)             // applied together: a ring reads the previous ring only
            {
                int i = got[k];
                fill[i * 3] = val[k * 3]; fill[i * 3 + 1] = val[k * 3 + 1]; fill[i * 3 + 2] = val[k * 3 + 2];
                known[i] = true;
            }
            todo = rest;
        }

        for (int i = 0; i < n; i++)
        {
            if (!isRim[i]) continue;
            float r = col[i * 3], g = col[i * 3 + 1], b = col[i * 3 + 2];
            float dr = r - kr, dg = g - kg, db = b - kb;
            if (Math.Sqrt(dr * dr + dg * dg + db * db) < FringeDist) fringe++;
            if (!known[i]) continue;                         // no interior near it: nothing to compare with
            float fr = fill[i * 3], fg = fill[i * 3 + 1], fb = fill[i * 3 + 2];
            float tr = kr - fr, tg = kg - fg, tb = kb - fb;  // from the interior colour toward the key
            float sr = r - fr, sg = g - fg, sb = b - fb;     // from the interior colour to this pixel
            float span = Math.Max(tr * tr + tg * tg + tb * tb, 1f);
            float share = (sr * tr + sg * tg + sb * tb) / span;
            float along = share * (float)Math.Sqrt(span);
            float off = (float)Math.Sqrt(Math.Max(sr * sr + sg * sg + sb * sb - along * along, 0f));
            if (share >= TintShare && off <= TintOffLine * along + 10f) tint++;
        }
    }

    /// <summary>Intersection over union of two masks as they sit.</summary>
    public static float IoU(bool[] a, bool[] b)
    {
        int inter = 0, union = 0;
        for (int i = 0; i < a.Length; i++)
        {
            if (a[i] && b[i]) inter++;
            if (a[i] || b[i]) union++;
        }
        return union == 0 ? 0f : (float)inter / union;
    }

    /// <summary>
    /// How far `frame` sits from where its core best overlaps `reference`, in px: the whole-frame
    /// move with the highest IoU inside ±reach, or (0, 0) when that move would gain less than
    /// SlipGain. Grounded frames are only tested sideways. Seated frames read 0-2 px; frames
    /// sliced at their in-cell position read tens.
    /// </summary>
    public static void Slip(bool[] reference, bool[] frame, int w, int h, bool grounded, int reach,
                            out int dx, out int dy)
    {
        dx = dy = 0;
        int words = (w + 63) / 64;
        ulong[] a = Pack(reference, w, h, words), b = Pack(frame, w, h, words);
        int na = 0, nb = 0;
        for (int i = 0; i < reference.Length; i++) { if (reference[i]) na++; if (frame[i]) nb++; }
        if (na == 0 || nb == 0) return;
        float here = Overlap(a, b, words, h, 0, 0, na, nb), best = -1f;
        int bx = 0, by = 0;
        int ry = grounded ? 0 : reach;
        for (int sy = -ry; sy <= ry; sy++)
            for (int sx = -reach; sx <= reach; sx++)
            {
                float v = Overlap(a, b, words, h, sx, sy, na, nb);
                if (v > best) { best = v; bx = sx; by = sy; }
            }
        if (best - here >= SlipGain) { dx = bx; dy = by; }
    }

    static ulong[] Pack(bool[] m, int w, int h, int words)
    {
        var p = new ulong[words * h];
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                if (m[y * w + x]) p[y * words + (x >> 6)] |= 1UL << (x & 63);
        return p;
    }

    // IoU with `b` moved by (sx, sy). The union counts every pixel of b wherever it lands.
    static float Overlap(ulong[] a, ulong[] b, int words, int h, int sx, int sy, int na, int nb)
    {
        long inter = 0;
        for (int y = 0; y < h; y++)
        {
            int src = y - sy;
            if (src < 0 || src >= h) continue;
            for (int i = 0; i < words; i++)
            {
                ulong av = a[y * words + i];
                if (av == 0) continue;
                long bit = (long)i * 64 - sx;               // first bit of b that lands in this word
                long j = bit >= 0 ? bit / 64 : -((-bit + 63) / 64);
                int r = (int)(bit - j * 64);
                ulong bv = 0;
                if (j >= 0 && j < words) bv = b[src * words + j] >> r;
                if (r > 0 && j + 1 >= 0 && j + 1 < words) bv |= b[src * words + j + 1] << (64 - r);
                inter += PopCount(av & bv);
            }
        }
        long union = na + nb - inter;
        return union <= 0 ? 0f : (float)inter / union;
    }

    static int PopCount(ulong v)
    {
        v -= (v >> 1) & 0x5555555555555555UL;
        v = (v & 0x3333333333333333UL) + ((v >> 2) & 0x3333333333333333UL);
        return (int)((((v + (v >> 4)) & 0x0F0F0F0F0F0F0F0FUL) * 0x0101010101010101UL) >> 56);
    }
}

/// <summary>
/// The few facts this fixture needs out of frames.json, read with patterns rather than with
/// JsonUtility: the sidecar carries nested arrays and JSON nulls (an empty cell's bbox, an
/// undefined statistic) that a typed mapper is not promised to accept, and one sidecar it cannot
/// read would take the whole fixture down. Every top-level fact is looked for BEFORE the "frames"
/// array, so a per-frame "register" block is never mistaken for the set's.
/// </summary>
public sealed class FrameSidecar
{
    public string Mode;                    // ground | free | centroid | keep, or null when the slicer did not say
    public int Ref;
    public float ReferenceCoreHeight;      // 0 when not recorded
    public bool HasVerdict, VerdictOk = true;
    public float[] PivotNorm;              // [x, y] from the bottom-left, or null
    public List<string> Files = new List<string>();    // frames with content, in play order

    static readonly System.Globalization.CultureInfo Inv = System.Globalization.CultureInfo.InvariantCulture;

    public static FrameSidecar Parse(string json)
    {
        var s = new FrameSidecar();
        // the frames ARRAY — set_metrics carries a "frames" count of its own, earlier in the file
        var arr = System.Text.RegularExpressions.Regex.Match(json, "\"frames\"\\s*:\\s*\\[");
        string head = arr.Success ? json.Substring(0, arr.Index) : json;
        string tail = arr.Success ? json.Substring(arr.Index) : "";

        var reg = System.Text.RegularExpressions.Regex.Match(head, "\"register\"\\s*:\\s*\\{([^{}]*)\\}");
        if (reg.Success)
        {
            string body = reg.Groups[1].Value;
            var m = System.Text.RegularExpressions.Regex.Match(body, "\"mode\"\\s*:\\s*\"([a-z]+)\"");
            if (m.Success) s.Mode = m.Groups[1].Value;
            m = System.Text.RegularExpressions.Regex.Match(body, "\"ref\"\\s*:\\s*(\\d+)");
            if (m.Success) s.Ref = int.Parse(m.Groups[1].Value, Inv);
            m = System.Text.RegularExpressions.Regex.Match(body, "\"reference_core_height_px\"\\s*:\\s*([0-9.]+)");
            if (m.Success) s.ReferenceCoreHeight = float.Parse(m.Groups[1].Value, Inv);
        }
        var v = System.Text.RegularExpressions.Regex.Match(head, "\"verdict\"\\s*:\\s*\\{\\s*\"ok\"\\s*:\\s*(true|false)");
        if (v.Success) { s.HasVerdict = true; s.VerdictOk = v.Groups[1].Value == "true"; }
        var pv = System.Text.RegularExpressions.Regex.Match(
            head, "\"pivot_norm\"\\s*:\\s*\\[\\s*([0-9.eE+-]+)\\s*,\\s*([0-9.eE+-]+)\\s*\\]");
        if (pv.Success)
            s.PivotNorm = new[] { float.Parse(pv.Groups[1].Value, Inv), float.Parse(pv.Groups[2].Value, Inv) };

        // one "file" per frame object; a frame is skipped when the same object says "empty": true
        var files = System.Text.RegularExpressions.Regex.Matches(tail, "\"file\"\\s*:\\s*\"([^\"]+)\"");
        for (int i = 0; i < files.Count; i++)
        {
            int from = files[i].Index;
            int to = i + 1 < files.Count ? files[i + 1].Index : tail.Length;
            string obj = tail.Substring(from, to - from);
            if (System.Text.RegularExpressions.Regex.IsMatch(obj, "\"empty\"\\s*:\\s*true")) continue;
            s.Files.Add(files[i].Groups[1].Value);
        }
        return s;
    }
}

#if !SPRITE_FRAMES_KERNEL_ONLY
namespace SpriteFrames.Tests
{
    using System.IO;
    using System.Linq;
    using NUnit.Framework;
    using UnityEngine;

    public class SpriteFramesAudit
    {
        // ---- CONFIGURE ------------------------------------------------------------------------
        /// <summary>Every frames.json under here is one sequence.</summary>
        const string ArtRoot = "Assets/Art";
        /// <summary>The scan must find at least this many: a gate that read nothing is not a pass.</summary>
        const int MinSequences = 1;
        /// <summary>The key colour ART_DIRECTION.md records — the one the sheets were generated on.</summary>
        static readonly Color32 Key = new Color32(255, 0, 255, 255);
        /// <summary>Which sequences are ONE character: by default the folder name up to its first '_'.</summary>
        static string CharacterOf(string sequence) =>
            sequence.Contains("_") ? sequence.Substring(0, sequence.IndexOf('_')) : sequence;

        const float FringeMaxPct = 0.5f, TintMaxPct = 2f;
        const int FeetMaxPx = 3;
        // ---------------------------------------------------------------------------------------

        class Seq
        {
            public string dir, name, mode;
            public FrameSidecar doc;
            public List<string> files = new List<string>();
            public HashSet<string> sizes = new HashSet<string>();
            public List<int> feet = new List<int>();
            public List<string> cut = new List<string>();
            public long fringe, tint, rim;
            public int slip, refCoreHeight, refAt;
        }

        static List<Seq> all;

        // Measured once for the fixture: decoding every frame per test would cost the suite minutes.
        static List<Seq> Sequences()
        {
            if (all != null) return all;
            all = new List<Seq>();
            if (!Directory.Exists(ArtRoot)) return all;
            foreach (string side in Directory.GetFiles(ArtRoot, "frames.json", SearchOption.AllDirectories).OrderBy(p => p))
            {
                var s = new Seq { dir = Path.GetDirectoryName(side) };
                s.name = Path.GetFileName(s.dir);
                s.doc = FrameSidecar.Parse(File.ReadAllText(side));
                s.mode = s.doc.Mode;
                bool body = s.mode == "ground" || s.mode == "free";
                var cores = new List<bool[]>();
                int w = 0, h = 0;
                string refName = null;
                foreach (string file in s.doc.Files)
                {
                    string path = Path.Combine(s.dir, file);
                    if (!File.Exists(path)) continue;
                    // the reference is frame `Ref` of the sheet: its file name ends in that index
                    if (refName == null && System.Text.RegularExpressions.Regex.IsMatch(
                            Path.GetFileNameWithoutExtension(file), "_0*" + s.doc.Ref + "$")) refName = file;
                    s.files.Add(path);
                    var t = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                    Assert.IsTrue(t.LoadImage(File.ReadAllBytes(path)), "unreadable " + path);
                    w = t.width; h = t.height;
                    s.sizes.Add(w + "x" + h);
                    byte[] rgba = TopDown(t.GetPixels32(), w, h);
                    UnityEngine.Object.DestroyImmediate(t);

                    if (FrameMeasure.CutByCanvas(rgba, w, h)) s.cut.Add(file);
                    FrameMeasure.Rim(rgba, w, h, Key.r, Key.g, Key.b, out int fr, out int ti, out int rim);
                    s.fringe += fr; s.tint += ti; s.rim += rim;
                    if (!body) continue;
                    bool[] core = FrameMeasure.Core(rgba, w, h);
                    s.feet.Add(FrameMeasure.Bottom(core, w, h));
                    if (file == refName) s.refAt = cores.Count;
                    cores.Add(core);
                }
                if (body && cores.Count > 1 && s.sizes.Count == 1)         // unequal canvases are reported on their own
                {
                    bool[] refCore = cores[s.refAt];
                    s.refCoreHeight = FrameMeasure.Bottom(refCore, w, h) - FrameMeasure.Top(refCore, w, h) + 1;
                    foreach (bool[] core in cores)
                    {
                        if (ReferenceEquals(core, refCore)) continue;
                        // a grounded frame is only tested sideways; a free one in both axes, on a shorter reach
                        FrameMeasure.Slip(refCore, core, w, h, s.mode == "ground", s.mode == "ground" ? 128 : 64,
                                          out int dx, out int dy);
                        s.slip = Math.Max(s.slip, Math.Max(Math.Abs(dx), Math.Abs(dy)));
                    }
                }
                all.Add(s);
            }
            return all;
        }

        // Unity hands pixels bottom row first; every measurement here is top-down.
        static byte[] TopDown(Color32[] px, int w, int h)
        {
            var o = new byte[w * h * 4];
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                {
                    Color32 c = px[(h - 1 - y) * w + x];
                    int i = (y * w + x) * 4;
                    o[i] = c.r; o[i + 1] = c.g; o[i + 2] = c.b; o[i + 3] = c.a;
                }
            return o;
        }

        [Test]
        public void The_scan_found_the_sequences()
        {
            Assert.GreaterOrEqual(Sequences().Count, MinSequences,
                $"{ArtRoot} holds {Sequences().Count} frames.json — every other test here would pass on nothing");
            TestContext.WriteLine($"sequences {Sequences().Count} frames {Sequences().Sum(s => s.files.Count)}");
        }

        /// <summary>The slicer was told where a frame sits, and its own gate passed.</summary>
        [Test]
        public void Every_sequence_was_seated_on_purpose()
        {
            var bad = new List<string>();
            foreach (Seq s in Sequences())
            {
                if (s.mode == null)
                    bad.Add($"{s.name}: frames.json has no register.mode — sliced by a tool that does not say " +
                            "where a frame sits (re-slice with sheet_to_frames.py --register …)");
                else if (s.doc.HasVerdict && !s.doc.VerdictOk)
                    bad.Add($"{s.name}: the slicer's own gate failed (frames.json verdict.ok = false)");
            }
            Assert.IsEmpty(bad, string.Join("\n", bad));
        }

        [Test]
        public void Frames_are_one_canvas_and_nothing_is_cut_by_it()
        {
            var bad = new List<string>();
            foreach (Seq s in Sequences())
            {
                if (s.sizes.Count > 1) bad.Add($"{s.name}: frames of {string.Join(", ", s.sizes)}");
                if (s.cut.Count > 0) bad.Add($"{s.name}: solid pixels on the canvas border in {string.Join(", ", s.cut)} — cut off");
            }
            Assert.IsEmpty(bad, string.Join("\n", bad));
        }

        [Test]
        public void No_frame_keeps_the_key_on_its_rim()
        {
            var bad = new List<string>();
            foreach (Seq s in Sequences())
            {
                double fr = 100.0 * s.fringe / Math.Max(s.rim, 1), ti = 100.0 * s.tint / Math.Max(s.rim, 1);
                TestContext.WriteLine($"{s.name} rim {s.rim} fringe {fr:F2}% tint {ti:F2}%");
                if (fr > FringeMaxPct || ti > TintMaxPct)
                    bad.Add($"{s.name}: fringe {fr:F2}% tint {ti:F2}% of {s.rim} rim px (max {FringeMaxPct} / {TintMaxPct}) — re-key the sheet (key_unmix.py)");
            }
            Assert.IsEmpty(bad, string.Join("\n", bad));
        }

        [Test]
        public void Grounded_frames_share_one_foot_line()
        {
            var bad = new List<string>();
            foreach (Seq s in Sequences().Where(q => q.mode == "ground" && q.feet.Count > 1))
            {
                int spread = s.feet.Max() - s.feet.Min();
                TestContext.WriteLine($"{s.name} feet spread {spread} px");
                if (spread > FeetMaxPx) bad.Add($"{s.name}: the feet line wanders {spread} px between frames");
            }
            Assert.IsEmpty(bad, string.Join("\n", bad));
        }

        /// <summary>No seated frame would overlap its reference better somewhere else.</summary>
        [Test]
        public void Seated_frames_are_in_register()
        {
            var bad = new List<string>();
            foreach (Seq s in Sequences().Where(q => q.mode == "ground" || q.mode == "free"))
            {
                float limit = Math.Max(3f, 0.01f * s.refCoreHeight);
                TestContext.WriteLine($"{s.name} slip {s.slip} px (max {limit:F0})");
                if (s.slip > limit) bad.Add($"{s.name}: a frame sits {s.slip} px from its best overlap with the reference — it jumps");
            }
            Assert.IsEmpty(bad, string.Join("\n", bad));
        }

        /// <summary>One character, one size: every seated sequence of it was placed at one reference height.</summary>
        [Test]
        public void A_character_is_one_size_across_its_sequences()
        {
            var byChar = new Dictionary<string, List<string>>();
            foreach (Seq s in Sequences().Where(q => (q.mode == "ground" || q.mode == "free") && q.doc.ReferenceCoreHeight > 0))
            {
                string who = CharacterOf(s.name);
                if (!byChar.TryGetValue(who, out var l)) byChar[who] = l = new List<string>();
                l.Add($"{s.name}={s.doc.ReferenceCoreHeight:F0}");
            }
            var bad = byChar.Where(kv => kv.Value.Select(v => v.Split('=')[1]).Distinct().Count() > 1)
                            .Select(kv => $"{kv.Key} is drawn at {string.Join(", ", kv.Value)} px").ToList();
            Assert.IsEmpty(bad, string.Join("\n", bad) + "\n(slice every sheet of a character with the same --subject-px)");
        }

#if UNITY_EDITOR
        /// <summary>
        /// The pivot the importer applies is the one the frames were seated on. With a foot margin the
        /// feet line is NOT the canvas floor: a (0.5, 0) pivot floats the character by the margin.
        /// </summary>
        [Test]
        public void The_importer_pivot_is_the_sidecars_pivot()
        {
            var bad = new List<string>();
            foreach (Seq s in Sequences().Where(q => q.doc.PivotNorm != null))
                foreach (string path in s.files)
                {
                    var ti = UnityEditor.AssetImporter.GetAtPath(path.Replace('\\', '/')) as UnityEditor.TextureImporter;
                    if (ti == null || ti.textureType != UnityEditor.TextureImporterType.Sprite) continue;
                    var st = new UnityEditor.TextureImporterSettings();
                    ti.ReadTextureSettings(st);
                    Vector2 want = new Vector2(s.doc.PivotNorm[0], s.doc.PivotNorm[1]);
                    Vector2 got = st.spriteAlignment == (int)SpriteAlignment.Custom ? st.spritePivot
                        : st.spriteAlignment == (int)SpriteAlignment.BottomCenter ? new Vector2(0.5f, 0f)
                        : st.spriteAlignment == (int)SpriteAlignment.Center ? new Vector2(0.5f, 0.5f)
                        : new Vector2(-1f, -1f);
                    if ((got - want).magnitude > 0.002f)
                    {
                        bad.Add($"{s.name}: importer pivot ({got.x:F3}, {got.y:F3}) is not frames.json pivot_norm ({want.x:F3}, {want.y:F3})");
                        break;                                      // one line per sequence
                    }
                }
            Assert.IsEmpty(bad, string.Join("\n", bad));
        }
#endif
    }
}
#endif
