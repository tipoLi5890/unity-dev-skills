// Build a sprite-frame AnimationClip (and optionally a one-state AnimatorController)
// from either a folder of equal-canvas frame PNGs or one already-sliced sheet.
//
// Unity cannot play a GIF. The preview GIF/APNG/WebP that came with the frames is a
// review artifact; this file produces the thing the game plays.
//
// The reasoning behind each call, and the traps, are in reference/sprite-animation.md — the
// comments below name the section rather than repeating it.
//
// A clean compile is not a clip: reference/sprite-animation.md §7 is the acceptance bar; run
// it before reporting a clip done.
//
// Order matters, and getting it wrong is silent: sprite rects must exist before anything
// captures Sprite references, or every keyframe serialises null with no error. Slice first —
// resources/SliceSheet.cs — then run this.
//
// Two ways in:
//   * from a live Editor via `unity command eval` (strip the usings, fully qualify, and
//     call SheetToAnimationClip.Run(new SheetToAnimationClip.Options { ... }));
//   * headless: -executeMethod SheetToAnimationClip.RunFromCommandLine with the flags
//     documented on that method.
//
// UnityEngine.UI is resolved by name rather than referenced, so this file compiles in a
// project without uGUI. If the Image target is asked for and the type does not resolve,
// that is a missing package and the exception says so.
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public static class SheetToAnimationClip
{
    public enum Target
    {
        SpriteRenderer,
        UiImage,
    }

    public class Options
    {
        /// <summary>Folder of frame PNGs (one sprite each) OR one sliced texture asset path.</summary>
        public string source;

        /// <summary>Output clip, e.g. "Assets/Animation/hero_idle.anim".</summary>
        public string clipPath;

        /// <summary>Frames per second. Take it from frames.json's fps_hint — see ReadFpsHint.</summary>
        public float fps = 10f;

        /// <summary>loopTime on the clip's AnimationClipSettings. false for a one-shot.</summary>
        public bool loop = true;

        public Target target = Target.SpriteRenderer;

        /// <summary>
        /// Curve path, relative to the GameObject that holds the Animator. "" is that object's
        /// own component; a UI Image is usually some levels down, so this is usually a real path.
        /// Wrong path == a clip that plays and animates nothing.
        /// </summary>
        public string bindingPath = "";

        /// <summary>Optional controller asset path, e.g. "Assets/Animation/hero.controller".</summary>
        public string controllerPath;

        /// <summary>Optional AnimationEvent method name, fired on the last keyframe. One-shots want this.</summary>
        public string endEventFunction;

        /// <summary>Extra duplicate keyframes of the last sprite — holds the final pose k frames longer.</summary>
        public int holdLastFrames = 0;

        /// <summary>Sprite name prefix filter, for a folder that holds more than one animation.</summary>
        public string namePrefix;
    }

    public static AnimationClip Run(Options o)
    {
        if (o == null || string.IsNullOrEmpty(o.source) || string.IsNullOrEmpty(o.clipPath))
            throw new System.ArgumentException("source and clipPath are both required");
        if (o.fps <= 0f) throw new System.ArgumentException($"fps must be positive, got {o.fps}");
        if (o.holdLastFrames < 0) throw new System.ArgumentException("holdLastFrames cannot be negative");

        var sprites = CollectSprites(o.source, o.namePrefix);
        if (sprites.Count == 0)
            throw new System.Exception(
                $"{o.source} yielded no sprites. A texture in Multiple mode with zero rects publishes " +
                "none at all, and the Project window looks entirely normal — slice it first. " +
                "See reference/sprite-animation.md §8.");

        WarnOnUnpaddedNames(sprites);

        var clip = new AnimationClip();

        // A fresh AnimationClip reports frameRate 60.
        // Set it before anything reads a time, so the Animation window's ruler matches the frames.
        clip.frameRate = o.fps;

        // path + type + propertyName is the whole identity of the binding. m_Sprite is the
        // serialised name on BOTH SpriteRenderer and UI Image, and both are PPtr curves whose
        // value type is UnityEngine.Sprite.
        var binding = EditorCurveBinding.PPtrCurve(o.bindingPath ?? "", ResolveTargetType(o.target), "m_Sprite");

        int total = sprites.Count + o.holdLastFrames;
        var keys = new ObjectReferenceKeyframe[total];
        for (int i = 0; i < total; i++)
        {
            keys[i].time = i / o.fps;
            keys[i].value = sprites[Mathf.Min(i, sprites.Count - 1)];
        }
        AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);

        // Length comes out at total/fps, not (total-1)/fps — the last frame already gets a full
        // frame of screen time, so a loop closes without a duplicate keyframe.

        // AnimationClipSettings is a CLASS and GetAnimationClipSettings hands back a copy:
        // mutating it changes nothing until SetAnimationClipSettings writes it back.
        // Nothing warns you.
        var settings = AnimationUtility.GetAnimationClipSettings(clip);
        settings.loopTime = o.loop;
        AnimationUtility.SetAnimationClipSettings(clip, settings);

        if (!string.IsNullOrEmpty(o.endEventFunction))
        {
            // On the last KEYFRAME, (total-1)/fps, which is inside the clip. An event at exactly
            // clip.length needs a play-mode test before you rely on it — do not place it there.
            clip.events = new[]
            {
                new AnimationEvent
                {
                    time = (total - 1) / o.fps,
                    functionName = o.endEventFunction,
                },
            };
        }

        var dir = Path.GetDirectoryName(o.clipPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            throw new System.Exception($"{dir} does not exist — CreateAsset will not make it for you");

        AssetDatabase.CreateAsset(clip, o.clipPath);
        AssetDatabase.SaveAssets();

        Verify(clip, binding, total, o);

        if (!string.IsNullOrEmpty(o.controllerPath))
            CreateController(o.controllerPath, clip);

        Debug.Log($"{o.clipPath}: {total} keyframes ({sprites.Count} frames + {o.holdLastFrames} held), " +
                  $"frameRate {clip.frameRate}, length {clip.length}, loopTime {o.loop}, " +
                  $"binding \"{o.bindingPath}\" {ResolveTargetType(o.target).Name}.m_Sprite");
        return clip;
    }

    /// <summary>
    /// Read fps_hint out of the frames.json that came with the frames. Regex rather than
    /// JsonUtility on purpose: the sidecar's nested arrays are not a shape JsonUtility maps,
    /// and this needs exactly one number out of it.
    /// </summary>
    public static float ReadFpsHint(string framesJsonPath, float fallback = 10f)
    {
        if (!File.Exists(framesJsonPath)) return fallback;
        var m = Regex.Match(File.ReadAllText(framesJsonPath), "\"fps_hint\"\\s*:\\s*([0-9]+(?:\\.[0-9]+)?)");
        float v;
        // InvariantCulture, not the machine's: frames.json always writes an invariant decimal
        // point ("fps_hint": 10.0), and on a machine whose culture uses ',' as the decimal
        // separator the current-culture parse reads "10.0" as 100 — the '.' becomes a group
        // separator (e.g. under de-DE: current-culture TryParse gives 100, invariant gives 10).
        // A clip at 100 fps passes every read in Verify, because Verify compares the clip
        // against the same mis-parsed number.
        return m.Success
               && float.TryParse(m.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out v)
               && v > 0f
            ? v
            : fallback;
    }

    // ---------------------------------------------------------------- internals

    static System.Type ResolveTargetType(Target target)
    {
        if (target == Target.SpriteRenderer) return typeof(UnityEngine.SpriteRenderer);

        // Resolved by name so this file compiles without uGUI referenced. This exact
        // assembly-qualified name resolves whenever com.unity.ugui is installed.
        var t = System.Type.GetType("UnityEngine.UI.Image, UnityEngine.UI");
        if (t == null)
            throw new System.Exception(
                "UnityEngine.UI.Image did not resolve — com.unity.ugui is absent, not misspelled.");
        return t;
    }

    /// <summary>
    /// Sprites in play order. A folder gives every .png's sprites; one texture path gives that
    /// texture's. Order comes from CompareFrameNames, which reads the trailing number as a number
    /// rather than as text — see there for why ordinal alone is not safe on this input.
    /// </summary>
    static List<Sprite> CollectSprites(string source, string namePrefix)
    {
        var paths = new List<string>();
        if (AssetDatabase.IsValidFolder(source))
        {
            foreach (var f in Directory.GetFiles(source, "*.png", SearchOption.TopDirectoryOnly))
                paths.Add(f.Replace('\\', '/'));
            paths.Sort((a, b) => CompareFrameNames(
                Path.GetFileNameWithoutExtension(a), Path.GetFileNameWithoutExtension(b)));
        }
        else if (File.Exists(source))
        {
            paths.Add(source);
        }
        else
        {
            throw new System.Exception($"{source} is neither a project folder nor a file");
        }

        var sprites = new List<Sprite>();
        foreach (var p in paths)
        {
            var found = new List<Sprite>();
            foreach (var o in AssetDatabase.LoadAllAssetsAtPath(p))
            {
                var s = o as Sprite;
                if (s == null) continue;
                if (!string.IsNullOrEmpty(namePrefix) && !s.name.StartsWith(namePrefix)) continue;
                found.Add(s);
            }

            // Rects in the provider are not sprites. If a file that should carry frames carries
            // none, the slice never landed — say which file, not "no sprites found".
            if (found.Count == 0 && paths.Count == 1)
                throw new System.Exception(
                    $"{p} publishes no Sprite sub-asset. textureType must be Sprite and the sheet " +
                    "must actually be sliced — reference/sprite-animation.md §2 and §8.");

            found.Sort((a, b) => CompareFrameNames(a.name, b.name));
            sprites.AddRange(found);
        }
        return sprites;
    }

    static readonly Regex TrailingNumber = new Regex("^(.*?)([0-9]+)$", RegexOptions.Compiled);

    /// <summary>
    /// Play order for frame names. `sheet_10` sorts before `sheet_2` under any string comparison,
    /// and Unity's own Sprite Editor auto-slice names rects exactly that way — unpadded — so an
    /// ordinal sort plays the clip scrambled while every read in Verify passes and the process
    /// exits 0. When both names end in digits, the digits decide, after an ordinal comparison of
    /// what precedes them (so a folder holding two animations still groups). Ordinal otherwise.
    /// resources/SliceSheet.cs pads with {index:D3}, so in-family frames sort the same either way.
    /// </summary>
    static int CompareFrameNames(string a, string b)
    {
        var ma = TrailingNumber.Match(a ?? "");
        var mb = TrailingNumber.Match(b ?? "");
        if (ma.Success && mb.Success)
        {
            int prefix = System.StringComparer.Ordinal.Compare(ma.Groups[1].Value, mb.Groups[1].Value);
            if (prefix != 0) return prefix;

            // TryParse, not Parse: a digit run too long for a long is not worth throwing over,
            // and the ordinal fall-through below is the right answer for it anyway.
            long na, nb;
            if (long.TryParse(ma.Groups[2].Value, NumberStyles.None, CultureInfo.InvariantCulture, out na)
                && long.TryParse(mb.Groups[2].Value, NumberStyles.None, CultureInfo.InvariantCulture, out nb)
                && na != nb)
                return na < nb ? -1 : 1;
        }
        return System.StringComparer.Ordinal.Compare(a, b);
    }

    /// <summary>
    /// This clip is ordered numerically, so unpadded names still play right here. Everything else
    /// that touches the set sorts as text, so say so once rather than let the next tool re-order it.
    /// </summary>
    static void WarnOnUnpaddedNames(List<Sprite> sprites)
    {
        var widths = new HashSet<int>();
        foreach (var s in sprites)
        {
            var m = Regex.Match(s.name, "([0-9]+)$");
            if (m.Success) widths.Add(m.Groups[1].Value.Length);
        }
        if (widths.Count > 1)
            Debug.LogWarning(
                "Frame names end in numbers of differing width (e.g. _2 and _10). This clip ordered " +
                "them numerically, but an ordinal sort — the Project window, the next importer — " +
                "puts _10 before _2. Re-name them zero-padded.");
    }

    static void Verify(AnimationClip clip, EditorCurveBinding wrote, int expected, Options o)
    {
        var bindings = AnimationUtility.GetObjectReferenceCurveBindings(clip);
        if (bindings.Length != 1)
            throw new System.Exception($"expected 1 object-reference curve, clip holds {bindings.Length}");

        // Never compare bindings with ==. The stored binding's curve-kind flags match neither a
        // hand-built EditorCurveBinding nor PPtrCurve's, so equality is false on a curve that
        // is perfectly correct. Compare the identity.
        var got = bindings[0];
        if (got.path != wrote.path || got.type != wrote.type || got.propertyName != wrote.propertyName)
            throw new System.Exception(
                $"binding drifted: wrote \"{wrote.path}\" {wrote.type.Name}.{wrote.propertyName}, " +
                $"clip holds \"{got.path}\" {got.type.Name}.{got.propertyName}");

        var keys = AnimationUtility.GetObjectReferenceCurve(clip, got);
        if (keys == null || keys.Length != expected)
            throw new System.Exception($"expected {expected} keyframes, read back {(keys == null ? 0 : keys.Length)}");
        foreach (var k in keys)
            if (k.value == null)
                throw new System.Exception(
                    $"keyframe at t={k.time} holds a null sprite — the reference was captured before " +
                    "the rects existed (reference/sprite-animation.md §8)");

        if (!Mathf.Approximately(clip.frameRate, o.fps))
            throw new System.Exception($"frameRate read back as {clip.frameRate}, asked for {o.fps}");
        if (AnimationUtility.GetAnimationClipSettings(clip).loopTime != o.loop)
            throw new System.Exception($"loopTime did not persist — asked for {o.loop}");

        // The reads above all pass on a clip bound to the wrong path. Scrubbing the clip in the
        // Animation window is the check that catches that one; nothing here can.
    }

    static void CreateController(string controllerPath, AnimationClip clip)
    {
        var ctrl = AnimatorController.CreateAnimatorControllerAtPathWithClip(controllerPath, clip);
        if (ctrl == null) throw new System.Exception($"no controller was created at {controllerPath}");

        // Do not rely on the graph the WithClip overload builds: assert rather than assume,
        // and set defaultState explicitly.
        var sm = ctrl.layers[0].stateMachine;
        if (sm.states.Length == 0)
        {
            var st = sm.AddState(clip.name);
            st.motion = clip;
            sm.defaultState = st;
        }
        else
        {
            sm.defaultState = sm.states[0].state;
        }
        EditorUtility.SetDirty(ctrl);
        AssetDatabase.SaveAssets();
        Debug.Log($"{controllerPath}: default state \"{sm.defaultState.name}\" -> {clip.name}");
    }

    // ---------------------------------------------------------------- headless entry

    /// <summary>
    /// -executeMethod SheetToAnimationClip.RunFromCommandLine
    ///   -source &lt;folder|texture&gt; -clip &lt;Assets/....anim&gt;
    ///   [-fps 10 | -framesJson &lt;path/frames.json&gt;] [-loop true|false]
    ///   [-target spriterenderer|image] [-path Body/Sprite] [-controller Assets/x.controller]
    ///   [-endEvent OnAnimationFinished] [-holdLast 4] [-namePrefix idle]
    /// -target takes spriterenderer/sprite/renderer or image/uiimage/ui, and throws on anything
    /// else: a typo must not quietly bind a UI object to SpriteRenderer.
    /// Exits non-zero on any failure, because a headless run that exits 0 having wired nothing
    /// is this pipeline's characteristic failure.
    /// </summary>
    public static void RunFromCommandLine()
    {
        // Argument parsing lives inside the try as well: a bad -fps or -target has to exit 1 like
        // any other failure, not escape RunFromCommandLine and leave the exit code to Unity.
        try
        {
            var args = System.Environment.GetCommandLineArgs();
            var o = new Options();
            string framesJson = null;
            for (int i = 0; i < args.Length - 1; i++)
            {
                var v = args[i + 1];
                switch (args[i])
                {
                    case "-source": o.source = v; break;
                    case "-clip": o.clipPath = v; break;
                    // InvariantCulture on both parses, for the reason in ReadFpsHint.
                    case "-fps": o.fps = float.Parse(v, CultureInfo.InvariantCulture); break;
                    case "-framesJson": framesJson = v; break;
                    case "-loop": o.loop = ParseLoop(v); break;
                    case "-target": o.target = ParseTarget(v); break;
                    case "-path": o.bindingPath = v; break;
                    case "-controller": o.controllerPath = v; break;
                    case "-endEvent": o.endEventFunction = v; break;
                    case "-holdLast": o.holdLastFrames = int.Parse(v, CultureInfo.InvariantCulture); break;
                    case "-namePrefix": o.namePrefix = v; break;
                }
            }
            if (framesJson != null) o.fps = ReadFpsHint(framesJson, o.fps);

            Run(o);
            EditorApplication.Exit(0);
        }
        catch (System.Exception e)
        {
            Debug.LogError(e);
            EditorApplication.Exit(1);
        }
    }

    /// <summary>
    /// Known spellings only. Mapping everything that is not "image" to SpriteRenderer means
    /// `-target uiimage` or `-target imgae` builds a clip bound to UnityEngine.SpriteRenderer on a
    /// UI object — the wrong-type binding that only scrubbing the clip by hand catches
    /// (reference/sprite-animation.md §7). Bad input throws here like it does everywhere else.
    /// </summary>
    static Target ParseTarget(string v)
    {
        switch ((v ?? "").Trim().ToLowerInvariant())
        {
            case "spriterenderer":
            case "sprite":
            case "renderer":
                return Target.SpriteRenderer;
            case "image":
            case "uiimage":
            case "ui":
            case "ui.image":
                return Target.UiImage;
            default:
                throw new System.ArgumentException(
                    $"-target \"{v}\" is not a target. Use spriterenderer (or sprite/renderer) " +
                    "for a SpriteRenderer, image (or uiimage/ui) for a UI Image.");
        }
    }

    /// <summary>
    /// Known spellings only, for the same reason as ParseTarget. Treating everything that is not
    /// "true" as false means `-loop True` or `-loop ture` builds a clip that silently does not
    /// loop, and Verify cannot catch it: it compares the clip against the same mis-parsed value.
    /// </summary>
    static bool ParseLoop(string v)
    {
        switch ((v ?? "").Trim().ToLowerInvariant())
        {
            case "true":
            case "1":
            case "yes":
                return true;
            case "false":
            case "0":
            case "no":
                return false;
            default:
                throw new System.ArgumentException(
                    $"-loop \"{v}\" is not a boolean. Use true (or 1/yes) for a looping clip, " +
                    "false (or 0/no) for a one-shot.");
        }
    }
}
