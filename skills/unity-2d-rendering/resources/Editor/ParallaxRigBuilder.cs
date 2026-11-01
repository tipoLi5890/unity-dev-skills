// ParallaxRigBuilder.cs — builds a parallax rig prefab from a scene split into depth layers:
// comfyui-asset-generation scene_layers.py's scene.json with its canvas-sized PNGs, or the same
// layers read by name from a layered .psd/.psb (after an artist repainted them). One child per
// layer with ParallaxLayer (factor = 1 - scroll) and ParallaxTiles; the tile sprites are written
// and imported beside the prefab, and the first view is baked in so the prefab shows the scene.
//
// Per layer the tiling comes from the JSON (`tiling`), else from the layer itself:
//   props on transparency (a layer with tile: false, role "props", or columns of empty space
//     between its pixels) -> Shuffle: each prop is its own tile, drawn from a seeded bag with
//     gaps, so no prop stands beside its own copy. A prop cut by the canvas edge is left out while
//     another prop remains (a cut prop shows its straight edge).
//   anything continuous (sky, skyline, shopfronts, road) -> Mirror: the whole layer, every other
//     copy flipped, so a strip that was never drawn to tile has no seam.
//
// `scroll` per layer is required — in the JSON or as an option — because depth order alone does
// not say which layer is the play line: scene_layers.py splits sky and road out of one layer.
//
// Menu: Tools > Unity Dev > 2D Rendering > Build Parallax Rig From Scene JSON...
// Batch: Unity -batchmode -projectPath P -executeMethod UnityDev.Rendering2D.ParallaxRigBuilder.BuildFromCommandLine
//          -sceneJson PATH/scene.json -scroll sky=0.04,skyline=0.15,shops=0.45,road=1,props=1.35
//          [-out Assets/Parallax] [-name street] [-psd PATH] [-ppu 100] [-groundPx 470]
//          [-pixelSnap] [-sortingLayer Default] [-seed 1] [-viewWidth 20]
//        prints `parallax-rig: {report}` and exits 0 built, 2 refused (with the reason), 1 usage error.
//
// The JSON, PNGs and PSD may sit outside Assets/: they are read from disk, not imported.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace UnityDev.Rendering2D
{
    public static class ParallaxRigBuilder
    {
        public sealed class Options
        {
            public Dictionary<string, float> scroll = new Dictionary<string, float>();  // wins over the JSON's
            public string name;                   // prefab name; default: the JSON's folder for scene.json
            public string psd;                    // read the layers from this .psd/.psb by name instead of PNGs
            public float pixelsPerUnit;           // 0 = the JSON's pixels_per_unit, else 100
            public float groundPx = -1f;          // canvas row (from the top) put on world y = 0; < 0 = the JSON's ground_px, else the middle
            public bool pixelSnap;                // ParallaxLayer.pixelsPerUnit + point-filtered, uncompressed tiles
            public string sortingLayer = "Default";
            public int seed = 1;
            public float viewWidth;               // world width baked into the prefab; 0 = 1.5 canvas widths
        }

        [Serializable]
        public sealed class LayerReport
        {
            public string name;
            public string tiling;
            public int variants;
            public int droppedEdgeProps;
            public float factorX, factorY;
            public int sortingOrder;
            public string[] tiles;
        }

        [Serializable]
        public sealed class Report
        {
            public bool ok;
            public string error;
            public string prefab;
            public float pixelsPerUnit;
            public List<LayerReport> layers = new List<LayerReport>();
        }

        const byte AlphaCut = 8;         // a column with no alpha above this is empty
        const int SpeckPx = 3;           // narrower runs of filled columns are noise
        const int PadPx = 2;             // transparent margin kept around a cut prop

        [MenuItem("Tools/Unity Dev/2D Rendering/Build Parallax Rig From Scene JSON…")]
        static void Menu()
        {
            string json = EditorUtility.OpenFilePanel("scene.json (scene_layers.py)", Application.dataPath, "json");
            if (string.IsNullOrEmpty(json)) return;
            string asset = ToAssetPath(json);
            string outFolder = asset != null ? Path.GetDirectoryName(asset).Replace('\\', '/') : "Assets/Parallax";
            Report r = Build(json, outFolder, new Options());
            if (r.ok) Selection.activeObject = AssetDatabase.LoadAssetAtPath<GameObject>(r.prefab);
            Debug.Log("parallax-rig: " + JsonUtility.ToJson(r, true));
        }

        public static void BuildFromCommandLine()
        {
            string[] args = Environment.GetCommandLineArgs();
            string Arg(string k) { int i = Array.IndexOf(args, k); return i >= 0 && i + 1 < args.Length ? args[i + 1] : null; }
            string json = Arg("-sceneJson");
            if (string.IsNullOrEmpty(json))
            {
                Debug.LogError("parallax-rig: usage: -sceneJson PATH [-scroll name=S,...] [-out Assets/...] [-name N] [-psd PATH] [-ppu N] [-groundPx Y] [-pixelSnap] [-sortingLayer NAME] [-seed N] [-viewWidth W]");
                EditorApplication.Exit(1);
                return;
            }
            var o = new Options { pixelSnap = Array.IndexOf(args, "-pixelSnap") >= 0 };
            if (Arg("-ppu") != null) o.pixelsPerUnit = float.Parse(Arg("-ppu"), CultureInfo.InvariantCulture);
            if (Arg("-seed") != null) o.seed = int.Parse(Arg("-seed"), CultureInfo.InvariantCulture);
            if (Arg("-viewWidth") != null) o.viewWidth = float.Parse(Arg("-viewWidth"), CultureInfo.InvariantCulture);
            if (Arg("-sortingLayer") != null) o.sortingLayer = Arg("-sortingLayer");
            if (Arg("-groundPx") != null) o.groundPx = float.Parse(Arg("-groundPx"), CultureInfo.InvariantCulture);
            o.name = Arg("-name");
            o.psd = Arg("-psd");
            foreach (string kv in (Arg("-scroll") ?? "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries))
            {
                string[] parts = kv.Split('=');
                if (parts.Length != 2 || !float.TryParse(parts[1], NumberStyles.Float, CultureInfo.InvariantCulture, out float v))
                {
                    Debug.LogError($"parallax-rig: -scroll wants name=value pairs, got '{kv}'");
                    EditorApplication.Exit(1);
                    return;
                }
                o.scroll[parts[0].Trim()] = v;
            }
            Report r = Build(json, Arg("-out") ?? "Assets/Parallax", o);
            Debug.Log("parallax-rig: " + JsonUtility.ToJson(r));
            EditorApplication.Exit(r.ok ? 0 : 2);
        }

        /// <summary>Build (or rebuild in place) the rig prefab. Never throws on bad input: the
        /// report carries ok = false and the reason.</summary>
        public static Report Build(string jsonPath, string outFolder, Options o)
        {
            var report = new Report();
            try { BuildInto(report, jsonPath, outFolder.TrimEnd('/'), o ?? new Options()); }
            catch (Exception e) { report.ok = false; report.error = e.Message; }
            return report;
        }

        static void BuildInto(Report report, string jsonPath, string outFolder, Options o)
        {
            if (!outFolder.StartsWith("Assets", StringComparison.Ordinal)) throw new Exception($"out folder must be under Assets/: {outFolder}");
            var doc = MiniJson.Parse(File.ReadAllText(jsonPath)) as Dictionary<string, object>
                      ?? throw new Exception("the scene JSON is not an object");
            string order = Str(doc, "order");
            if (order != null && order != "back_to_front") throw new Exception($"order is '{order}'; the layers must be listed back_to_front");
            int W = (int)(Num(doc, "width") ?? 0f), H = (int)(Num(doc, "height") ?? 0f);
            if (W <= 0 || H <= 0) throw new Exception("width and height (the canvas, in pixels) are required");
            var layers = (doc.TryGetValue("layers", out object lo) ? lo as List<object> : null) ?? throw new Exception("no layers");
            if (layers.Count == 0) throw new Exception("no layers");

            float ppu = o.pixelsPerUnit > 0f ? o.pixelsPerUnit : (Num(doc, "pixels_per_unit") ?? 100f);
            report.pixelsPerUnit = ppu;
            string dir = Path.GetDirectoryName(Path.GetFullPath(jsonPath));
            string scene = o.name;
            if (string.IsNullOrEmpty(scene))
            {
                scene = Path.GetFileNameWithoutExtension(jsonPath);
                if (scene == "scene") scene = Path.GetFileName(dir);
                else if (scene.EndsWith(".scene", StringComparison.Ordinal)) scene = scene.Substring(0, scene.Length - 6);
            }
            scene = Safe(scene);
            string psdPath = o.psd ?? (Str(doc, "psd") is string rel ? Path.Combine(dir, rel) : null);
            List<PsdLayerReader.Layer> psd = null;
            if (psdPath != null)
            {
                psd = PsdLayerReader.Read(psdPath, out int pw, out int ph);
                if (pw != W || ph != H) throw new Exception($"{Path.GetFileName(psdPath)} is {pw}x{ph}, the scene {W}x{H}");
            }

            float groundPx = o.groundPx >= 0f ? o.groundPx : Num(doc, "ground_px") ?? H * 0.5f;
            float baseY = -(H - groundPx) / ppu;           // canvas bottom; the ground row lands on y = 0
            float view = o.viewWidth > 0f ? o.viewWidth : 1.5f * W / ppu;

            string tileDir = $"{outFolder}/{scene}_tiles";
            EnsureFolder(tileDir);
            var names = new HashSet<string>();
            var root = new GameObject(scene);
            try
            {
                for (int li = 0; li < layers.Count; li++)
                {
                    var L = layers[li] as Dictionary<string, object> ?? throw new Exception($"layer {li} is not an object");
                    string name = Str(L, "name") ?? throw new Exception($"layer {li} has no name");
                    if (!names.Add(name)) throw new Exception($"two layers are named '{name}'");
                    float scroll = o.scroll.TryGetValue(name, out float sv) ? sv : Num(L, "scroll")
                        ?? throw new Exception($"layer '{name}' has no scroll: add \"scroll\" to the JSON or pass -scroll {name}=S (1 = the play line, 0 = fixed to the camera)");
                    float scrollY = Num(L, "scroll_y") ?? 1f;

                    Color32[] px = LayerPixels(L, name, dir, psd, W, H);
                    List<(int x0, int x1)> runs = ColumnRuns(px, W, H);
                    if (runs.Count == 0) throw new Exception($"layer '{name}' is empty");
                    int filled = runs.Sum(r => r.x1 - r.x0 + 1);
                    string tiling = (Str(L, "tiling") ?? "auto").ToLowerInvariant();
                    // scene_layers.py marks its props layer tile: false, role "props".
                    bool props = (L.TryGetValue("tile", out object t) && t is bool tb && !tb) || Str(L, "role") == "props";
                    if (tiling == "auto") tiling = props || filled <= 0.85f * W ? "shuffle" : "mirror";

                    var lr = new LayerReport { name = name, tiling = tiling };
                    var spans = new List<(int x0, int x1)>();
                    if (tiling == "shuffle")
                    {
                        var inner = runs.Where(r => r.x0 > 0 && r.x1 < W - 1).ToList();
                        if (inner.Count > 0) { lr.droppedEdgeProps = runs.Count - inner.Count; runs = inner; }
                        foreach (var r in runs) spans.Add((Math.Max(0, r.x0 - PadPx), Math.Min(W - 1, r.x1 + PadPx)));
                    }
                    else if (tiling == "mirror" || tiling == "repeat") spans.Add((0, W - 1));
                    else throw new Exception($"layer '{name}': unknown tiling '{tiling}'");

                    float[] gapPx = Nums(L, "gap") ?? (tiling == "shuffle" ? new[] { 0.25f * W, 1f * W } : new[] { 0f, 0f });
                    if (gapPx.Length != 2) throw new Exception($"layer '{name}': gap must be [least, most]");

                    var sprites = new List<Sprite>();
                    var tileNames = new List<string>();
                    for (int k = 0; k < spans.Count; k++)
                    {
                        string path = $"{tileDir}/{Safe(name)}_{k}.png";
                        WriteTile(px, W, H, spans[k].x0, spans[k].x1, path);
                        sprites.Add(ImportTile(path, ppu, o.pixelSnap, tiling != "shuffle"));
                        tileNames.Add(path);
                    }
                    // Tiles of an earlier build with more props than this one.
                    for (int k = spans.Count; File.Exists($"{tileDir}/{Safe(name)}_{k}.png"); k++)
                        AssetDatabase.DeleteAsset($"{tileDir}/{Safe(name)}_{k}.png");
                    lr.variants = sprites.Count;
                    lr.tiles = tileNames.ToArray();

                    var go = new GameObject(name);
                    go.transform.SetParent(root.transform, false);
                    // Tile 0 is centred on x = 0, where the camera starts, so a continuous layer's
                    // first view is the source picture.
                    go.transform.localPosition = new Vector3(-0.5f * W / ppu, baseY, 0f);
                    var layer = go.AddComponent<ParallaxLayer>();
                    layer.factor = new Vector2(1f - scroll, 1f - scrollY);
                    layer.wrapWidth = 0f;
                    layer.pixelsPerUnit = o.pixelSnap ? ppu : 0f;
                    var tiles = go.AddComponent<ParallaxTiles>();
                    tiles.variants = sprites.ToArray();
                    tiles.tiling = tiling == "shuffle" ? ParallaxTiling.Shuffle : tiling == "repeat" ? ParallaxTiling.Repeat : ParallaxTiling.Mirror;
                    tiles.seed = o.seed * 7919 + StableHash(name);
                    tiles.gap = new Vector2(gapPx[0], gapPx[1]) / ppu;
                    tiles.sortingLayerName = o.sortingLayer;
                    // Back to front. The play line (scroll 1) and everything behind it sit below
                    // order 0; layers faster than the world pass in front of the runner.
                    tiles.sortingOrder = (scroll > 1f ? 1000 : -1000) + 10 * li;
                    tiles.Rebuild();
                    tiles.Refresh(-0.5f * view, 0.5f * view);

                    lr.factorX = layer.factor.x;
                    lr.factorY = layer.factor.y;
                    lr.sortingOrder = tiles.sortingOrder;
                    report.layers.Add(lr);
                }

                string prefabPath = $"{outFolder}/{scene}.prefab";
                PrefabUtility.SaveAsPrefabAsset(root, prefabPath, out bool saved);
                if (!saved) throw new Exception($"could not save {prefabPath}");
                report.prefab = prefabPath;
                report.ok = true;
            }
            finally { UnityEngine.Object.DestroyImmediate(root); }
        }

        // The layer's pixels on the full canvas, bottom row first (Unity's order): a canvas-sized
        // PNG (`png`), or the PSD layer of the same name placed where the file puts it.
        static Color32[] LayerPixels(Dictionary<string, object> L, string name, string dir, List<PsdLayerReader.Layer> psd, int W, int H)
        {
            var dst = new Color32[W * H];
            if (psd != null)
            {
                PsdLayerReader.Layer pl = psd.FirstOrDefault(l => l.name == name)
                    ?? throw new Exception($"the PSD has no layer named '{name}' (a renamed layer is a new layer)");
                for (int y = 0; y < pl.height; y++)
                {
                    int cy = H - 1 - (pl.y + pl.height - 1 - y);      // pl.pixels is bottom row first
                    if (cy < 0 || cy >= H) continue;
                    for (int x = 0; x < pl.width; x++)
                    {
                        int cx = pl.x + x;
                        if (cx >= 0 && cx < W) dst[cy * W + cx] = pl.pixels[y * pl.width + x];
                    }
                }
                return dst;
            }
            string file = Str(L, "png") ?? throw new Exception($"layer '{name}' has no png");
            string p = Path.Combine(dir, file);
            if (!File.Exists(p)) throw new Exception($"layer '{name}': {file} not found");
            var src = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                if (!src.LoadImage(File.ReadAllBytes(p))) throw new Exception($"layer '{name}': {file} is not a PNG");
                if (src.width != W || src.height != H)
                    throw new Exception($"layer '{name}': {file} is {src.width}x{src.height}, expected the canvas {W}x{H}");
                return src.GetPixels32();
            }
            finally { UnityEngine.Object.DestroyImmediate(src); }
        }

        // Runs of columns that hold any pixel, with specks dropped and runs closer than a few
        // pixels merged (a prop's own thin gaps do not split it).
        internal static List<(int x0, int x1)> ColumnRuns(Color32[] px, int W, int H)
        {
            var filled = new bool[W];
            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++)
                    if (px[y * W + x].a > AlphaCut) filled[x] = true;
            var runs = new List<(int x0, int x1)>();
            int merge = Math.Max(4, W / 128);
            for (int x = 0; x < W;)
            {
                if (!filled[x]) { x++; continue; }
                int s = x;
                while (x < W && filled[x]) x++;
                if (runs.Count > 0 && s - runs[runs.Count - 1].x1 - 1 < merge) runs[runs.Count - 1] = (runs[runs.Count - 1].x0, x - 1);
                else runs.Add((s, x - 1));
            }
            runs.RemoveAll(r => r.x1 - r.x0 + 1 < SpeckPx);
            return runs;
        }

        static void WriteTile(Color32[] px, int W, int H, int x0, int x1, string path)
        {
            int w = x1 - x0 + 1;
            var t = new Texture2D(w, H, TextureFormat.RGBA32, false);
            var buf = new Color32[w * H];
            for (int y = 0; y < H; y++) Array.Copy(px, y * W + x0, buf, y * w, w);
            t.SetPixels32(buf);
            File.WriteAllBytes(path, t.EncodeToPNG());
            UnityEngine.Object.DestroyImmediate(t);
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
        }

        static Sprite ImportTile(string path, float ppu, bool pixelSnap, bool contiguous)
        {
            var ti = (TextureImporter)AssetImporter.GetAtPath(path);
            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Single;
            var s = new TextureImporterSettings();
            ti.ReadTextureSettings(s);
            s.spriteAlignment = (int)SpriteAlignment.BottomLeft;
            // A strip that touches its neighbours needs its full quad; a tight outline leaves
            // hairline gaps at the edge. Props keep the tight mesh (less overdraw).
            s.spriteMeshType = contiguous ? SpriteMeshType.FullRect : SpriteMeshType.Tight;
            s.spriteGenerateFallbackPhysicsShape = false;
            ti.SetTextureSettings(s);
            ti.spritePixelsPerUnit = ppu;
            ti.alphaIsTransparency = true;
            ti.mipmapEnabled = false;
            ti.wrapMode = TextureWrapMode.Clamp;
            ti.npotScale = TextureImporterNPOTScale.None;
            if (pixelSnap)
            {
                // The import unity-2d-pixel-perfect's SpriteImportFix applies.
                ti.filterMode = FilterMode.Point;
                ti.textureCompression = TextureImporterCompression.Uncompressed;
            }
            ti.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<Sprite>(path) ?? throw new Exception($"{path} did not import as a sprite");
        }

        static void EnsureFolder(string assetFolder)
        {
            string parent = "Assets";
            foreach (string part in assetFolder.Split('/').Skip(1))
            {
                string next = parent + "/" + part;
                if (!AssetDatabase.IsValidFolder(next)) AssetDatabase.CreateFolder(parent, part);
                parent = next;
            }
        }

        static string ToAssetPath(string path)
        {
            string full = Path.GetFullPath(path).Replace('\\', '/');
            string assets = Path.GetFullPath(Application.dataPath).Replace('\\', '/');
            if (full == assets) return "Assets";
            return full.StartsWith(assets + "/", StringComparison.Ordinal) ? "Assets" + full.Substring(assets.Length) : null;
        }

        static string Safe(string s)
        {
            var b = new StringBuilder();
            foreach (char c in s) b.Append(char.IsLetterOrDigit(c) || c == '_' || c == '-' ? c : '_');
            return b.ToString();
        }

        static int StableHash(string s)
        {
            unchecked
            {
                int h = (int)2166136261;
                foreach (char c in s) h = (h ^ c) * 16777619;
                return h & 0x7fffffff;
            }
        }

        static string Str(Dictionary<string, object> d, string k) => d.TryGetValue(k, out object v) ? v as string : null;
        static float? Num(Dictionary<string, object> d, string k) => d.TryGetValue(k, out object v) && v is double n ? (float)n : (float?)null;
        static float[] Nums(Dictionary<string, object> d, string k) =>
            d.TryGetValue(k, out object v) && v is List<object> l && l.All(e => e is double) ? l.Select(e => (float)(double)e).ToArray() : null;

        // Just enough JSON: objects, arrays, strings, numbers, true/false/null. JsonUtility cannot
        // tell a missing key from a zero, and every optional key here has a non-zero default.
        static class MiniJson
        {
            public static object Parse(string s) { int i = 0; object v = Value(s, ref i); Ws(s, ref i); if (i != s.Length) throw new Exception("trailing text in JSON"); return v; }

            static void Ws(string s, ref int i) { while (i < s.Length && char.IsWhiteSpace(s[i])) i++; }

            static object Value(string s, ref int i)
            {
                Ws(s, ref i);
                if (i >= s.Length) throw new Exception("unexpected end of JSON");
                char c = s[i];
                if (c == '{')
                {
                    var d = new Dictionary<string, object>(); i++; Ws(s, ref i);
                    if (s[i] == '}') { i++; return d; }
                    while (true)
                    {
                        Ws(s, ref i);
                        string k = (string)Value(s, ref i); Ws(s, ref i);
                        if (s[i++] != ':') throw new Exception("expected ':' in JSON");
                        d[k] = Value(s, ref i); Ws(s, ref i);
                        if (s[i] == ',') { i++; continue; }
                        if (s[i++] == '}') return d;
                        throw new Exception("expected ',' or '}' in JSON");
                    }
                }
                if (c == '[')
                {
                    var l = new List<object>(); i++; Ws(s, ref i);
                    if (s[i] == ']') { i++; return l; }
                    while (true)
                    {
                        l.Add(Value(s, ref i)); Ws(s, ref i);
                        if (s[i] == ',') { i++; continue; }
                        if (s[i++] == ']') return l;
                        throw new Exception("expected ',' or ']' in JSON");
                    }
                }
                if (c == '"')
                {
                    var b = new StringBuilder(); i++;
                    while (s[i] != '"')
                    {
                        if (s[i] == '\\')
                        {
                            char e = s[++i];
                            if (e == 'u') { b.Append((char)Convert.ToInt32(s.Substring(i + 1, 4), 16)); i += 4; }
                            else b.Append(e == 'n' ? '\n' : e == 't' ? '\t' : e == 'r' ? '\r' : e == 'b' ? '\b' : e == 'f' ? '\f' : e);
                        }
                        else b.Append(s[i]);
                        i++;
                    }
                    i++;
                    return b.ToString();
                }
                if (s.Length - i >= 4 && string.CompareOrdinal(s, i, "true", 0, 4) == 0) { i += 4; return true; }
                if (s.Length - i >= 5 && string.CompareOrdinal(s, i, "false", 0, 5) == 0) { i += 5; return false; }
                if (s.Length - i >= 4 && string.CompareOrdinal(s, i, "null", 0, 4) == 0) { i += 4; return null; }
                int st = i;
                while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
                if (st == i) throw new Exception($"unexpected '{c}' in JSON");
                return double.Parse(s.Substring(st, i - st), NumberStyles.Float, CultureInfo.InvariantCulture);
            }
        }
    }
}
