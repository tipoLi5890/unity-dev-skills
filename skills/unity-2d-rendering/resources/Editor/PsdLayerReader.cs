// PsdLayerReader.cs — the pixel layers of an 8-bit RGB .psd (version 1) or .psb (version 2), read
// straight from the file: name, place on the canvas, hidden flag and RGBA pixels. Groups and their
// dividers are skipped; layer masks, effects and other blend data are ignored.
//
// Enough of Adobe's "Photoshop File Formats Specification" for what an image editor saves from a
// layered scene, so the parallax rig builder needs neither Unity's PSD Importer nor the file inside
// Assets/. 16-bit, CMYK, indexed and ZIP-compressed channels are refused with a reason.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

namespace UnityDev.Rendering2D
{
    public static class PsdLayerReader
    {
        public sealed class Layer
        {
            public string name;
            public bool hidden;
            public int x, y, width, height;      // canvas pixels, origin top-left
            public Color32[] pixels;             // width * height, bottom row first (Unity's order)
        }

        // Additional-layer-info keys whose length is 8 bytes in a PSB.
        static readonly HashSet<string> LongKeys = new HashSet<string>
            { "LMsk", "Lr16", "Lr32", "Layr", "Mt16", "Mt32", "Mtrn", "Alph", "FMsk", "lnk2", "FEid", "FXid", "PxSD" };

        public static List<Layer> Read(string path, out int canvasWidth, out int canvasHeight)
        {
            byte[] b = File.ReadAllBytes(path);
            int p = 0;
            if (b.Length < 26 || Encoding.ASCII.GetString(b, 0, 4) != "8BPS") throw new Exception($"{path} is not a PSD or PSB");
            p = 4;
            int version = U16(b, ref p);
            if (version != 1 && version != 2) throw new Exception($"{path}: unknown PSD version {version}");
            bool psb = version == 2;
            p = 12;
            U16(b, ref p);                                              // channels of the merged image
            canvasHeight = (int)U32(b, ref p);
            canvasWidth = (int)U32(b, ref p);
            int depth = U16(b, ref p), mode = U16(b, ref p);
            if (depth != 8 || mode != 3) throw new Exception($"{path}: {depth}-bit colour mode {mode}; save it as 8-bit RGB");
            Skip(b, ref p);                                             // colour mode data
            Skip(b, ref p);                                             // image resources
            long lmi = psb ? (long)U64(b, ref p) : U32(b, ref p);
            var layers = new List<Layer>();
            if (lmi == 0) return layers;
            long infoLen = psb ? (long)U64(b, ref p) : U32(b, ref p);
            if (infoLen == 0) return layers;
            int count = Math.Abs((short)U16(b, ref p));

            var recs = new List<(Layer layer, int section, List<(int id, long len)> ch)>();
            for (int i = 0; i < count; i++)
            {
                int top = I32(b, ref p), left = I32(b, ref p), bottom = I32(b, ref p), right = I32(b, ref p);
                int nch = U16(b, ref p);
                var ch = new List<(int id, long len)>();
                for (int c = 0; c < nch; c++) ch.Add(((short)U16(b, ref p), psb ? (long)U64(b, ref p) : U32(b, ref p)));
                p += 4 + 4 + 1 + 1;                                     // '8BIM', blend key, opacity, clipping
                int flags = b[p]; p += 2;                               // flags, filler
                int extraEnd = (int)U32(b, ref p); extraEnd += p;
                Skip(b, ref p);                                         // layer mask data
                Skip(b, ref p);                                         // blending ranges
                int nameLen = b[p];
                var nb = new StringBuilder();
                for (int c = 0; c < nameLen; c++) nb.Append((char)b[p + 1 + c]);   // Latin-1; luni below wins
                string name = nb.ToString();
                p += (1 + nameLen + 3) / 4 * 4;
                int section = 0;
                while (p + 12 <= extraEnd)
                {
                    string sig = Encoding.ASCII.GetString(b, p, 4), key = Encoding.ASCII.GetString(b, p + 4, 4);
                    if (sig != "8BIM" && sig != "8B64") break;
                    p += 8;
                    long len = psb && LongKeys.Contains(key) ? (long)U64(b, ref p) : U32(b, ref p);
                    int q = p;
                    if (key == "luni") { int n = (int)U32(b, ref q); name = Encoding.BigEndianUnicode.GetString(b, q, n * 2); }
                    else if (key == "lsct" || key == "lsdk") section = (int)U32(b, ref q);
                    p += (int)len;
                }
                p = extraEnd;
                var layer = new Layer { name = name, hidden = (flags & 0x02) != 0, x = left, y = top, width = right - left, height = bottom - top };
                recs.Add((layer, section, ch));
            }

            // Channel image data, in record order.
            foreach (var (layer, section, ch) in recs)
            {
                int w = layer.width, h = layer.height;
                bool keep = section == 0 && w > 0 && h > 0;
                byte[][] planes = keep ? new byte[4][] : null;
                foreach (var (id, len) in ch)
                {
                    int start = p;
                    if (keep && id >= -1 && id <= 2) planes[id + 1] = Plane(b, start, w, h, psb, layer.name);
                    p = start + (int)len;
                }
                if (!keep) continue;
                layer.pixels = new Color32[w * h];
                for (int y = 0; y < h; y++)
                    for (int x = 0; x < w; x++)
                    {
                        int s = y * w + x;
                        layer.pixels[(h - 1 - y) * w + x] = new Color32(
                            At(planes[1], s, 0), At(planes[2], s, 0), At(planes[3], s, 0), At(planes[0], s, 255));
                    }
                layers.Add(layer);
            }
            return layers;
        }

        static byte[] Plane(byte[] b, int p, int w, int h, bool psb, string layer)
        {
            int comp = U16(b, ref p);
            var o = new byte[w * h];
            if (comp == 0) { Buffer.BlockCopy(b, p, o, 0, w * h); return o; }
            if (comp != 1) throw new Exception($"layer '{layer}': compression {comp} (ZIP) is not read; save without it");
            p += h * (psb ? 4 : 2);                                     // per-row byte counts
            int k = 0;
            while (k < o.Length)                                         // PackBits
            {
                int n = (sbyte)b[p++];
                if (n >= 0) { Buffer.BlockCopy(b, p, o, k, n + 1); p += n + 1; k += n + 1; }
                else if (n != -128) { byte v = b[p++]; for (int i = 0; i < 1 - n; i++) o[k++] = v; }
            }
            return o;
        }

        // A 4-byte length and that many bytes. (Not `p += U32(b, ref p)`: C# reads the left p
        // before the call advances it.)
        static void Skip(byte[] b, ref int p) { int n = (int)U32(b, ref p); p += n; }

        static byte At(byte[] plane, int i, byte fallback) => plane != null ? plane[i] : fallback;

        static int U16(byte[] b, ref int p) { int v = (b[p] << 8) | b[p + 1]; p += 2; return v; }
        static uint U32(byte[] b, ref int p) { uint v = (uint)(b[p] << 24 | b[p + 1] << 16 | b[p + 2] << 8 | b[p + 3]); p += 4; return v; }
        static int I32(byte[] b, ref int p) => (int)U32(b, ref p);
        static ulong U64(byte[] b, ref int p) { ulong hi = U32(b, ref p); return hi << 32 | U32(b, ref p); }
    }
}
