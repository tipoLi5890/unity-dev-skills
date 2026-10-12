// ClipEventWriter — add or replace an AnimationEvent on a clip at a normalised time, and read
// the clip back to prove where it landed.
//
// Drop into an Editor folder. Call from an Editor script or `unity command eval`:
//
//   ClipEventWriter.SetEvent(clip, "OnFootstep", 0.25f);
//   ClipEventWriter.SetEvent(clip, "OnAnimEvent", 1f, "hurt-end");   // snapped to the last frame
//   Debug.Log(ClipEventWriter.Describe(clip));
//
// Menu: Tools/Unity Dev/Animation/List Clip Events (reads the selected clips, writes nothing).
//
// Idempotent: an event is identified by functionName + stringParameter. Writing the same event
// at the same time changes nothing and returns false; writing it at a new time moves it. Events
// with other identities are left alone.
//
// Two storage paths, chosen by where the clip lives:
//   a .anim asset            events are written on the clip itself;
//   a clip inside a model    the clip is read-only — events go into the ModelImporter's clip
//                            list and the model is reimported. SetEvent then reads the clip back
//                            and logs an error when the event is not at the time asked for.
// SetEvent writes the asset, and on a model clip reimports the model. Report the clip, the
// function and the time, and wait for confirmation before calling it.
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class ClipEventWriter
{
    /// <summary>Adds the event, or moves the one with the same functionName and stringParameter.
    /// Returns true when the asset changed.</summary>
    /// <param name="normalisedTime">0 = first frame, 1 = end. Snapped to the clip's frame grid
    /// and held one frame short of the end, where an event is inside the clip on every loop.</param>
    public static bool SetEvent(AnimationClip clip, string functionName, float normalisedTime,
                                string stringParameter = "", int intParameter = 0,
                                float floatParameter = 0f)
    {
        if (clip == null) throw new System.ArgumentNullException("clip");
        if (string.IsNullOrEmpty(functionName)) throw new System.ArgumentException("functionName");
        if (clip.length <= 0f)
            throw new System.InvalidOperationException(clip.name + " has length 0; there is no time to put an event at");

        float seconds = SnapSeconds(clip, normalisedTime);
        string path = AssetDatabase.GetAssetPath(clip);
        var importer = AssetImporter.GetAtPath(path) as ModelImporter;

        if (importer == null)
        {
            var events = new List<AnimationEvent>(AnimationUtility.GetAnimationEvents(clip));
            if (!Upsert(events, functionName, stringParameter, intParameter, floatParameter,
                        seconds, 0.5f / clip.frameRate))
                return false;
            events.Sort((a, b) => a.time.CompareTo(b.time));
            Undo.RegisterCompleteObjectUndo(clip, "Set animation event");
            AnimationUtility.SetAnimationEvents(clip, events.ToArray());
            EditorUtility.SetDirty(clip);
            AssetDatabase.SaveAssetIfDirty(clip);
            return true;
        }

        return SetOnModel(importer, path, clip.name, functionName, stringParameter, intParameter,
                          floatParameter, seconds / clip.length, seconds);
    }

    /// <summary>Removes every event with this functionName (and stringParameter, when given).
    /// Returns how many went. For a .anim clip; clear a model clip's events in its importer.</summary>
    public static int RemoveEvents(AnimationClip clip, string functionName, string stringParameter = null)
    {
        if (clip == null) throw new System.ArgumentNullException("clip");
        if (AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(clip)) is ModelImporter)
            throw new System.InvalidOperationException(clip.name + " lives inside a model; edit ModelImporter.clipAnimations");

        var events = new List<AnimationEvent>(AnimationUtility.GetAnimationEvents(clip));
        int removed = events.RemoveAll(e => e.functionName == functionName &&
                                            (stringParameter == null || e.stringParameter == stringParameter));
        if (removed == 0) return 0;
        Undo.RegisterCompleteObjectUndo(clip, "Remove animation event");
        AnimationUtility.SetAnimationEvents(clip, events.ToArray());
        EditorUtility.SetDirty(clip);
        AssetDatabase.SaveAssetIfDirty(clip);
        return removed;
    }

    /// <summary>The clip's events as one JSON object: seconds, normalised time and identity.</summary>
    public static string Describe(AnimationClip clip)
    {
        var sb = new StringBuilder();
        sb.Append("{\"clip\":").Append(Str(clip.name))
          .Append(",\"path\":").Append(Str(AssetDatabase.GetAssetPath(clip)))
          .Append(",\"length\":").Append(F(clip.length))
          .Append(",\"frameRate\":").Append(F(clip.frameRate))
          .Append(",\"events\":[");
        AnimationEvent[] events = AnimationUtility.GetAnimationEvents(clip);
        for (int i = 0; i < events.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"time\":").Append(F(events[i].time))
              .Append(",\"normalised\":").Append(F(clip.length > 0f ? events[i].time / clip.length : 0f))
              .Append(",\"function\":").Append(Str(events[i].functionName))
              .Append(",\"string\":").Append(Str(events[i].stringParameter))
              .Append(",\"int\":").Append(events[i].intParameter)
              .Append(",\"float\":").Append(F(events[i].floatParameter))
              .Append('}');
        }
        return sb.Append("]}").ToString();
    }

    // ---------------------------------------------------------------- internals

    static float SnapSeconds(AnimationClip clip, float normalisedTime)
    {
        float fps = clip.frameRate > 0f ? clip.frameRate : 60f;
        float frame = Mathf.Round(Mathf.Clamp01(normalisedTime) * clip.length * fps);
        float last = Mathf.Max(0f, Mathf.Round(clip.length * fps) - 1f);
        return Mathf.Min(frame, last) / fps;
    }

    static bool Upsert(List<AnimationEvent> events, string functionName, string stringParameter,
                       int intParameter, float floatParameter, float time, float tolerance)
    {
        stringParameter = stringParameter ?? "";
        for (int i = 0; i < events.Count; i++)
        {
            AnimationEvent e = events[i];
            if (e.functionName != functionName || (e.stringParameter ?? "") != stringParameter) continue;
            if (Mathf.Abs(e.time - time) <= tolerance && e.intParameter == intParameter
                && Mathf.Approximately(e.floatParameter, floatParameter))
                return false;
            e.time = time;
            e.intParameter = intParameter;
            e.floatParameter = floatParameter;
            events[i] = e;
            return true;
        }
        events.Add(new AnimationEvent
        {
            time = time,
            functionName = functionName,
            stringParameter = stringParameter,
            intParameter = intParameter,
            floatParameter = floatParameter,
        });
        return true;
    }

    static bool SetOnModel(ModelImporter importer, string path, string clipName, string functionName,
                           string stringParameter, int intParameter, float floatParameter,
                           float normalised, float seconds)
    {
        // clipAnimations is empty until somebody edits the clip list; the importer then uses
        // defaultClipAnimations. Both getters return copies — the array has to be assigned back.
        ModelImporterClipAnimation[] clips = importer.clipAnimations;
        if (clips == null || clips.Length == 0) clips = importer.defaultClipAnimations;

        int at = -1;
        for (int i = 0; i < clips.Length; i++)
            if (clips[i].name == clipName) { at = i; break; }
        if (at < 0)
            throw new System.InvalidOperationException("no clip named '" + clipName + "' in the importer of " + path);

        // Inside the importer an event's time is a fraction of the clip, not seconds.
        var events = new List<AnimationEvent>(clips[at].events ?? new AnimationEvent[0]);
        float span = (clips[at].lastFrame - clips[at].firstFrame);
        float tolerance = span > 0f ? 0.5f / span : 0.001f;
        if (!Upsert(events, functionName, stringParameter, intParameter, floatParameter, normalised, tolerance))
            return false;
        events.Sort((a, b) => a.time.CompareTo(b.time));
        clips[at].events = events.ToArray();
        importer.clipAnimations = clips;
        importer.SaveAndReimport();

        // The reimport replaced the clip object; load the new one and check the result in seconds.
        foreach (Object o in AssetDatabase.LoadAllAssetsAtPath(path))
        {
            var reloaded = o as AnimationClip;
            if (reloaded == null || reloaded.name != clipName) continue;
            foreach (AnimationEvent e in AnimationUtility.GetAnimationEvents(reloaded))
                if (e.functionName == functionName && (e.stringParameter ?? "") == (stringParameter ?? "")
                    && Mathf.Abs(e.time - seconds) <= 1f / reloaded.frameRate)
                    return true;
            Debug.LogError("[ANIM] ClipEventWriter: " + clipName + " in " + path + " was reimported but '" +
                           functionName + "' is not at " + F(seconds) + " s. Now: " + Describe(reloaded));
            return true;
        }
        Debug.LogError("[ANIM] ClipEventWriter: " + clipName + " is missing from " + path + " after the reimport");
        return true;
    }

    static string F(float v) => v.ToString("0.####", CultureInfo.InvariantCulture);

    static string Str(string s)
    {
        if (s == null) return "null";
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }

    // ---------------------------------------------------------------- menu

    const string Menu = "Tools/Unity Dev/Animation/List Clip Events";

    [MenuItem(Menu, true)]
    static bool CanList() => Selection.GetFiltered<AnimationClip>(SelectionMode.Assets).Length > 0;

    [MenuItem(Menu)]
    static void ListSelected()
    {
        foreach (AnimationClip clip in Selection.GetFiltered<AnimationClip>(SelectionMode.Assets))
            Debug.Log("[ANIM] " + Describe(clip));
    }
}
