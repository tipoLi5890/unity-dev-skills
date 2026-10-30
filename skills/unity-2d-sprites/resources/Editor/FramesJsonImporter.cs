// FramesJsonImporter.cs — import settings for a frame set, taken from its frames.json (frames/1).
//
// A PNG is handled when its folder holds a frames.json that lists it in frames[].file. Every
// other texture in the project is left alone. For a handled frame:
//
//   textureType Sprite, spriteImportMode Single, mipmaps off, alphaIsTransparency, Clamp
//   pivot        SpriteAlignment.Custom, spritePivot = pivot_norm (bottom-left origin, as Unity's)
//   PPU          register.reference_core_height_px / the character's height in world units
//   pixel set    (frames.json has a pixel block) Point filter, Uncompressed
//   other set    Bilinear; compression left to the project
//   maxTextureSize raised to the canvas when it is smaller (a smaller Max Size shrinks the frames)
//
// The schema and the PPU rule: schemas/frames-1.json and schemas/README.md in this plugin.
// This file owns import metadata only. The clip (fps_hint, loop, hold_last) is
// SheetToAnimationClip.cs's; reference/sprite-animation.md §1 has the split.
//
// The character's height in world units: -worldHeight on the command line, else what this
// importer stored on the frame's .meta last time (userData "unitydev.worldHeight=<h>"), else the
// EditorPrefs key below, else DefaultWorldHeight. Storing it on the .meta keeps a later reimport
// (a Library rebuild, a moved folder) on the same PPU. Every set of one character must end up
// on one PPU; SpriteFramesAudit's one-size test catches a character drawn at two sizes.
//
// Headless (synchronous, so -quit is safe; the method exits by itself):
//
//   "$UNITY" -batchmode -projectPath . -logFile - \
//     -executeMethod UnityDev.Sprites.FramesJsonImporter.RunFromCommandLine \
//     -framesDir Assets/Art/runner_walk [-worldHeight 1.8]
//
// It reimports every frame frames.json lists, reads each importer back, and exits:
//   0  every frame imported with the sidecar's pivot (and PPU, when the core height is known)
//   2  a frame's importer reads back different settings (another postprocessor overrode them)
//   3  nothing verified: the folder, frames.json or a listed frame is missing, or the import threw
//   1  refused: a usage error, unreadable JSON, or a frames/1 file missing a required key
// The Editor itself also exits 1 on a compile error: grep the log for `error CS` first.
//
// An unstamped frames.json (no "schema", the 0.34 dialect) is read for one release with a WARN:
// pivot_norm is applied, and the PPU only when register.reference_core_height_px is present.
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace UnityDev.Sprites
{
    public sealed class FramesJsonImporter : AssetPostprocessor
    {
        /// <summary>World units, used when nothing else names the character's height.</summary>
        public const float DefaultWorldHeight = 1.8f;

        /// <summary>EditorPrefs key: this machine's default height, when neither the command line nor the .meta names one.</summary>
        public const string WorldHeightPref = "UnityDev.Sprites.WorldHeight";

        const string Tag = "[FRAMES-IMPORT] ";
        const string UserDataKey = "unitydev.worldHeight=";

        /// <summary>Set by RunFromCommandLine for the length of one reimport; wins over everything.</summary>
        static float? worldHeightOverride;

        // ---------------------------------------------------------------- the sidecar

        [System.Serializable]
        public sealed class Register
        {
            public string mode;
            public int @ref;
            public int reference_core_height_px;
            public int foot_margin_px;
            public int margin_px;                  // the 0.34 name, read as foot_margin_px with a WARN
        }

        [System.Serializable]
        public sealed class Pixel
        {
            public int block_px;
        }

        [System.Serializable]
        public sealed class Frame
        {
            public string file;
            public bool empty;
        }

        /// <summary>
        /// The keys this side reads. JsonUtility instantiates an absent nested object with defaults
        /// rather than null, so presence is tested on values (block_px &gt; 0), and the bools JSON
        /// can omit are tested on the text (HasLoop).
        /// </summary>
        [System.Serializable]
        public sealed class Sidecar
        {
            public string schema;
            public string tool;
            public int[] canvas;
            public float[] pivot_norm;
            public string pivot;
            public float fps_hint;
            public bool loop;
            public bool hold_last;
            public Register register = new Register();
            public Pixel pixel = new Pixel();
            public Frame[] frames;

            [System.NonSerialized] public bool HasLoop;
            [System.NonSerialized] public string Path;

            public bool Stamped => schema == "frames/1";
            public bool IsPixel => pixel != null && pixel.block_px > 0;
            public int CoreHeight => register != null ? register.reference_core_height_px : 0;
        }

        /// <summary>
        /// Read and check one frames.json. Returns null and an error for unreadable JSON, a foreign
        /// stamp, or a frames/1 file missing a required key (a producer bug: refused, not warned).
        /// An unstamped file is accepted; its warnings are logged by the caller.
        /// </summary>
        public static Sidecar Read(string framesJsonPath, out string error, List<string> warnings = null)
        {
            error = null;
            string text;
            try { text = File.ReadAllText(framesJsonPath); }
            catch (System.Exception e) { error = $"{framesJsonPath}: unreadable ({e.Message})"; return null; }

            Sidecar s;
            try { s = JsonUtility.FromJson<Sidecar>(text); }
            catch (System.Exception e) { error = $"{framesJsonPath}: not JSON ({e.Message})"; return null; }
            if (s == null) { error = $"{framesJsonPath}: empty"; return null; }
            s.Path = framesJsonPath;
            if (s.register == null) s.register = new Register();
            if (s.pixel == null) s.pixel = new Pixel();

            // Presence on the whole text: no other object in frames/1 has a bool "loop" or a
            // "foot_margin_px", so the match does not depend on where the producer put the key.
            s.HasLoop = Regex.IsMatch(text, "\"loop\"\\s*:\\s*(true|false)");
            bool hasFootMargin = Regex.IsMatch(text, "\"foot_margin_px\"\\s*:");

            var problems = new List<string>();
            if (!string.IsNullOrEmpty(s.schema) && !s.Stamped)
            {
                error = $"{framesJsonPath}: schema \"{s.schema}\" is not frames/1";
                return null;
            }
            if (s.canvas == null || s.canvas.Length != 2 || s.canvas[0] < 1 || s.canvas[1] < 1)
                problems.Add("canvas [W, H]");
            if (s.pivot_norm == null || s.pivot_norm.Length != 2
                || s.pivot_norm[0] < 0f || s.pivot_norm[0] > 1f || s.pivot_norm[1] < 0f || s.pivot_norm[1] > 1f)
                problems.Add("pivot_norm [x, y] in 0..1");
            if (!(s.fps_hint > 0f)) problems.Add("fps_hint > 0");
            if (!s.HasLoop) problems.Add("loop (true|false)");
            if (s.CoreHeight < 1) problems.Add("register.reference_core_height_px >= 1");
            if (!hasFootMargin) problems.Add("register.foot_margin_px");
            if (s.frames == null || s.frames.Length == 0) problems.Add("frames[]");
            if (s.hold_last && s.loop) problems.Add("hold_last true with loop true");

            if (s.Stamped)
            {
                if (problems.Count > 0)
                {
                    error = $"{framesJsonPath}: frames/1 file missing or bad: {string.Join(", ", problems)}";
                    return null;
                }
                return s;
            }

            // The 0.34 dialect: read what is there, say what is not.
            if (warnings != null)
            {
                warnings.Add($"{framesJsonPath}: no \"schema\" — read as the 0.34 dialect for one release");
                if (!hasFootMargin && s.register.margin_px > 0)
                    warnings.Add($"{framesJsonPath}: register.margin_px read as foot_margin_px");
                if (s.CoreHeight < 1)
                    warnings.Add($"{framesJsonPath}: no register.reference_core_height_px — PPU not set");
            }
            if (s.pivot_norm == null || s.pivot_norm.Length != 2)
            {
                if (s.pivot == "center") s.pivot_norm = new[] { 0.5f, 0.5f };
                else if (s.pivot == "bottom-center") s.pivot_norm = new[] { 0.5f, 0f };
                if (warnings != null)
                    warnings.Add($"{framesJsonPath}: no pivot_norm — " +
                                 (s.pivot_norm != null ? $"pivot \"{s.pivot}\" used" : "pivot left as it is"));
            }
            if (s.frames == null || s.frames.Length == 0)
            {
                error = $"{framesJsonPath}: frames[] is empty";
                return null;
            }
            return s;
        }

        /// <summary>PPU for this set, or 0 when the core height is unknown.</summary>
        public static float PixelsPerUnit(Sidecar s, float worldHeight) =>
            s.CoreHeight > 0 && worldHeight > 0f ? s.CoreHeight / worldHeight : 0f;

        // ---------------------------------------------------------------- the postprocessor

        static readonly Dictionary<string, (System.DateTime stamp, Sidecar doc)> cache =
            new Dictionary<string, (System.DateTime, Sidecar)>();
        static readonly HashSet<string> warned = new HashSet<string>();

        void OnPreprocessTexture()
        {
            string path = assetPath.Replace('\\', '/');
            if (!path.EndsWith(".png", System.StringComparison.OrdinalIgnoreCase)) return;
            string dir = System.IO.Path.GetDirectoryName(path)?.Replace('\\', '/');
            if (string.IsNullOrEmpty(dir)) return;
            string json = dir + "/frames.json";
            if (!File.Exists(json)) return;

            // A sidecar that cannot be read must not break the import of anything else.
            Sidecar s = Cached(json);
            if (s == null) return;
            string file = System.IO.Path.GetFileName(path);
            bool listed = false;
            foreach (Frame f in s.frames)
                if (f != null && f.file == file) { listed = true; break; }
            if (!listed) return;

            var ti = (TextureImporter)assetImporter;
            float height = WorldHeightFor(ti);
            Apply(ti, s, height);
        }

        static Sidecar Cached(string json)
        {
            System.DateTime stamp = File.GetLastWriteTimeUtc(json);
            if (cache.TryGetValue(json, out var hit) && hit.stamp == stamp) return hit.doc;
            var warnings = new List<string>();
            Sidecar s = Read(json, out string error, warnings);
            if (error != null) Debug.LogError(Tag + error + " — frames in this folder keep their settings");
            foreach (string w in warnings)
                if (warned.Add(w)) Debug.LogWarning(Tag + "WARN " + w);
            cache[json] = (stamp, s);
            return s;
        }

        static float WorldHeightFor(TextureImporter ti)
        {
            if (worldHeightOverride.HasValue) return worldHeightOverride.Value;
            string ud = ti.userData ?? "";
            if (ud.StartsWith(UserDataKey)
                && float.TryParse(ud.Substring(UserDataKey.Length), NumberStyles.Float,
                                  CultureInfo.InvariantCulture, out float stored) && stored > 0f)
                return stored;
            float pref = EditorPrefs.GetFloat(WorldHeightPref, DefaultWorldHeight);
            return pref > 0f ? pref : DefaultWorldHeight;
        }

        /// <summary>Write the sidecar's settings onto one frame's importer (used by the postprocessor).</summary>
        public static void Apply(TextureImporter ti, Sidecar s, float worldHeight)
        {
            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Single;
            ti.mipmapEnabled = false;
            ti.alphaIsTransparency = true;
            ti.sRGBTexture = true;
            ti.wrapMode = TextureWrapMode.Clamp;
            if (s.IsPixel)
            {
                ti.filterMode = FilterMode.Point;
                ti.textureCompression = TextureImporterCompression.Uncompressed;
            }
            else
            {
                ti.filterMode = FilterMode.Bilinear;
            }
            if (s.canvas != null && s.canvas.Length == 2)
            {
                int need = Mathf.NextPowerOfTwo(Mathf.Max(s.canvas[0], s.canvas[1]));
                if (ti.maxTextureSize < need) ti.maxTextureSize = Mathf.Min(need, 16384);
            }

            var st = new TextureImporterSettings();
            ti.ReadTextureSettings(st);
            st.spriteMeshType = SpriteMeshType.FullRect;     // frames swap; a tight mesh per frame adds nothing
            float ppu = PixelsPerUnit(s, worldHeight);
            if (s.pivot_norm != null && s.pivot_norm.Length == 2)
            {
                st.spriteAlignment = (int)SpriteAlignment.Custom;
                st.spritePivot = new Vector2(s.pivot_norm[0], s.pivot_norm[1]);
            }
            if (ppu > 0f) st.spritePixelsPerUnit = ppu;
            ti.SetTextureSettings(st);
            // The importer's own properties too: some Editor versions read these, not the settings.
            if (s.pivot_norm != null && s.pivot_norm.Length == 2) ti.spritePivot = st.spritePivot;
            if (ppu > 0f)
            {
                ti.spritePixelsPerUnit = ppu;
                // userData belongs to whoever set it first: write ours only into an empty or our own.
                if (string.IsNullOrEmpty(ti.userData) || ti.userData.StartsWith(UserDataKey))
                    ti.userData = UserDataKey + worldHeight.ToString("0.####", CultureInfo.InvariantCulture);
                if (s.IsPixel)
                {
                    float artPpu = ppu / s.pixel.block_px;
                    if (Mathf.Abs(artPpu - Mathf.Round(artPpu)) > 1e-3f && warned.Add(s.Path + "#artppu"))
                        Debug.LogWarning(Tag + $"WARN {s.Path}: PPU {ppu:0.###} / block_px {s.pixel.block_px} = " +
                                         $"{artPpu:0.###} art px per unit, not whole — choose a world height " +
                                         "that makes it whole (schemas/README.md, PPU rule)");
                }
            }
        }

        // ---------------------------------------------------------------- headless entry

        /// <summary>
        /// -executeMethod UnityDev.Sprites.FramesJsonImporter.RunFromCommandLine
        ///   -framesDir &lt;Assets/... folder holding frames.json&gt; [-worldHeight 1.8]
        /// Exit codes are in the file header.
        /// </summary>
        public static void RunFromCommandLine()
        {
            int code;
            try { code = Reimport(System.Environment.GetCommandLineArgs()); }
            catch (System.Exception e)
            {
                Debug.LogError(Tag + "harness error: " + e);
                code = 3;
            }
            finally { worldHeightOverride = null; }
            EditorApplication.Exit(code);
        }

        static int Reimport(string[] args)
        {
            string dir = null;
            float? height = null;
            for (int i = 0; i < args.Length; i++)
            {
                bool hasValue = i + 1 < args.Length;
                if (args[i] == "-framesDir")
                {
                    if (!hasValue) return Usage("-framesDir needs a folder");
                    dir = args[++i].Replace('\\', '/').TrimEnd('/');
                }
                else if (args[i] == "-worldHeight")
                {
                    if (!hasValue || !float.TryParse(args[++i], NumberStyles.Float, CultureInfo.InvariantCulture,
                                                     out float h) || !(h > 0f))
                        return Usage("-worldHeight needs a positive number of world units");
                    height = h;
                }
            }
            if (string.IsNullOrEmpty(dir)) return Usage("-framesDir is required");
            if (!dir.StartsWith("Assets/") && dir != "Assets")
                return Usage($"-framesDir \"{dir}\" is not a project path under Assets/");

            if (!AssetDatabase.IsValidFolder(dir))
            {
                Debug.LogError(Tag + $"{dir}: no such project folder");
                return 3;
            }
            string json = dir + "/frames.json";
            if (!File.Exists(json))
            {
                Debug.LogError(Tag + $"{json}: missing");
                return 3;
            }

            var warnings = new List<string>();
            Sidecar s = Read(json, out string error, warnings);
            if (s == null)
            {
                Debug.LogError(Tag + "refused: " + error);
                return 1;
            }
            foreach (string w in warnings) Debug.LogWarning(Tag + "WARN " + w);
            cache.Remove(json);

            worldHeightOverride = height;
            var paths = new List<string>();
            foreach (Frame f in s.frames)
            {
                if (f == null || string.IsNullOrEmpty(f.file)) continue;
                string p = dir + "/" + f.file;
                if (!File.Exists(p))
                {
                    Debug.LogError(Tag + $"{p}: listed in frames.json and not on disk");
                    return 3;
                }
                paths.Add(p);
            }
            AssetDatabase.StartAssetEditing();
            try
            {
                foreach (string p in paths) AssetDatabase.ImportAsset(p, ImportAssetOptions.ForceUpdate);
            }
            finally { AssetDatabase.StopAssetEditing(); }
            AssetDatabase.Refresh();

            // Read every importer back: a later postprocessor can overwrite what Apply set.
            var bad = new List<string>();
            float expectPpu = 0f;
            foreach (string p in paths)
            {
                var ti = AssetImporter.GetAtPath(p) as TextureImporter;
                if (ti == null) { bad.Add($"{p}: no TextureImporter"); continue; }
                var st = new TextureImporterSettings();
                ti.ReadTextureSettings(st);
                if (ti.textureType != TextureImporterType.Sprite) bad.Add($"{p}: textureType {ti.textureType}");
                if (s.pivot_norm != null && s.pivot_norm.Length == 2)
                {
                    var want = new Vector2(s.pivot_norm[0], s.pivot_norm[1]);
                    if (st.spriteAlignment != (int)SpriteAlignment.Custom || (st.spritePivot - want).magnitude > 1e-4f)
                        bad.Add($"{p}: pivot ({st.spritePivot.x:0.####}, {st.spritePivot.y:0.####}) " +
                                $"alignment {(SpriteAlignment)st.spriteAlignment}, frames.json pivot_norm " +
                                $"({want.x:0.####}, {want.y:0.####})");
                }
                float ppu = PixelsPerUnit(s, WorldHeightFor(ti));
                if (ppu > 0f)
                {
                    if (expectPpu == 0f) expectPpu = ppu;
                    if (Mathf.Abs(st.spritePixelsPerUnit - ppu) > 1e-3f)
                        bad.Add($"{p}: PPU {st.spritePixelsPerUnit:0.###}, expected {ppu:0.###}");
                }
                if (s.IsPixel && ti.filterMode != FilterMode.Point) bad.Add($"{p}: filterMode {ti.filterMode} on a pixel set");
            }

            Debug.Log(Tag + $"{dir}: {paths.Count} frames, pivot " +
                      (s.pivot_norm != null ? $"({s.pivot_norm[0]:0.####}, {s.pivot_norm[1]:0.####})" : "unchanged") +
                      ", PPU " + (expectPpu > 0f ? expectPpu.ToString("0.###", CultureInfo.InvariantCulture) : "unchanged") +
                      $", loop {s.loop}, hold_last {s.hold_last}" + (s.IsPixel ? $", pixel F={s.pixel.block_px}" : ""));
            if (bad.Count > 0)
            {
                foreach (string b in bad) Debug.LogError(Tag + "FAIL " + b);
                return 2;
            }
            Debug.Log(Tag + "PASS");
            return 0;
        }

        static int Usage(string message)
        {
            Debug.LogError(Tag + "usage: " + message + "\n  -executeMethod UnityDev.Sprites.FramesJsonImporter." +
                           "RunFromCommandLine -framesDir Assets/<set> [-worldHeight 1.8]");
            return 1;
        }
    }
}
