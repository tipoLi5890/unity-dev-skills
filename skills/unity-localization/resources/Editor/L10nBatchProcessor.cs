// Batch-attach LocalizeStringEvent to the labels in every scene, and report what it
// could not match.
//
// REQUIRES com.unity.localization and TextMeshPro. Without them these types do not
// exist and this file does not compile — that is not a runtime failure you can catch.
// Editor-only: put it under an Editor/ folder, or run it through `unity command eval`.
// eval takes no using directives, so strip them and qualify the names its host does
// not already have in scope — TMPro, UnityEditor.SceneManagement, UnityEditor.Events
// and UnityEngine.Localization.Components. Qualifying every type is unnecessary
// (see unity-debug -> reference/editor-control.md).
//
// Destructive. LocalizeAll opens every scene under Assets/ and saves the ones it
// changed, and there is no automatic undo. Report the scene count and the mapping
// first, then wait for the user to confirm before calling it.
//
// LocalizeAll returns the labels that matched no mapping entry, as
// "scene :: object :: text". Print that list. A run that wires 20 labels and quietly
// leaves 9 alone is indistinguishable from a complete one otherwise. The list covers
// authored text only — code-composed strings are invisible to any scene walk; the grep
// for those is in reference/string-tables.md section 6.9.
//
// The mapping is matched longest key first, on purpose. `Contains` on unordered keys
// lets a two-character key win inside a whole sentence, and the label then holds a
// plausible string from the wrong entry — everything wires, nothing throws, and the
// failure is only visible by reading the screen. For a mapping of
// { "NO", "NOT NOW, THANKS" } and a label reading "NOT NOW, THANKS", dictionary order
// returns the "NO" entry and the sort returns the right one. Keep the sort. Matching
// is case-sensitive; if the caller's source text is inconsistently cased, normalise
// both sides at the call site rather than loosening the comparison here.
//
// API surface this relies on: set_text is public on both TMPro.TMP_Text and
// UnityEngine.UI.Text; UnityEventBase.SetPersistentListenerState(int,
// UnityEventCallState) is public and UnityEventCallState is exactly
// { Off, EditorAndRuntime, RuntimeOnly }.
using System.Collections.Generic;
using System.Linq;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.Localization.Components;
using UnityEngine.UI;

public static class L10nBatchProcessor
{
    /// <summary>
    /// Wires every scene under Assets/. Returns the labels that matched no mapping entry.
    /// </summary>
    /// <param name="mapping">source text fragment -> table entry key</param>
    /// <param name="table">the String Table collection name, e.g. "UIStrings"</param>
    public static List<string> LocalizeAll(Dictionary<string, string> mapping, string table)
    {
        var unmatched = new List<string>();

        // Longest key first, once, rather than per label. See the header.
        var ordered = mapping.OrderByDescending(p => p.Key.Length).ToList();

        // Scope the search. FindAssets has two overloads and the one-argument form covers
        // the whole project including read-only packages, so this loop would try to open
        // and save assets it must not touch — unscoped, "t:Scene" also returns package
        // scenes, such as the test fixtures Addressables ships.
        var scenes = AssetDatabase.FindAssets("t:Scene", new[] { "Assets" });

        foreach (var guid in scenes)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Single);
            unmatched.AddRange(LocalizeOpenScene(ordered, table, path, out var wired));

            // Save only what changed. A dynamic font atlas already rewrites its own asset
            // on every Editor run (SKILL.md section 3); a pass that also rewrites every
            // scene file whether or not it touched them buries its own diff.
            if (wired == 0) continue;
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
        }

        return unmatched;
    }

    /// <summary>
    /// Wires the scene that is currently open. Returns "scene :: object :: text" for each
    /// label found but not covered by the mapping, and reports how many it wired.
    /// </summary>
    static List<string> LocalizeOpenScene(
        List<KeyValuePair<string, string>> ordered, string table, string scenePath, out int wired)
    {
        var unmatched = new List<string>();
        wired = 0;

        // Both families, always. TMP_Text is the abstract base of TextMeshProUGUI and
        // TextMeshPro; walking only the legacy family is the usual mistake and it fails
        // quietly, because a project can have a handful of legacy labels and dozens of TMP
        // ones and the pass still reports success.
        var labels = new List<Component>();
        labels.AddRange(Object.FindObjectsByType<Text>(
            FindObjectsInactive.Include, FindObjectsSortMode.None));
        labels.AddRange(Object.FindObjectsByType<TMP_Text>(
            FindObjectsInactive.Include, FindObjectsSortMode.None));

        foreach (var label in labels)
        {
            var current = label is Text legacy ? legacy.text : ((TMP_Text)label).text;
            if (string.IsNullOrEmpty(current)) continue;

            var matched = false;
            foreach (var pair in ordered)
            {
                if (!current.Contains(pair.Key)) continue;

                var lse = label.gameObject.GetComponent<LocalizeStringEvent>()
                          ?? label.gameObject.AddComponent<LocalizeStringEvent>();
                lse.StringReference =
                    new UnityEngine.Localization.LocalizedString(table, pair.Value);

                // The `text` setter has no C# method-group name, so the delegate is built by
                // name. That is reflection over a public member; reaching for the private
                // m_PersistentCalls / m_MethodName serialized fields instead would not be, and
                // is unnecessary — AddPersistentListener writes the same serialized call.
                var setText = (UnityAction<string>)System.Delegate.CreateDelegate(
                    typeof(UnityAction<string>), label, "set_text");

                // Clear first. Re-running the pass otherwise stacks a duplicate call on the
                // same event and the label is assigned twice per update.
                for (var i = lse.OnUpdateString.GetPersistentEventCount() - 1; i >= 0; i--)
                    UnityEventTools.RemovePersistentListener(lse.OnUpdateString, i);

                UnityEventTools.AddPersistentListener(lse.OnUpdateString, setText);

                // AddPersistentListener leaves the call at RuntimeOnly: correct in a build,
                // dormant while authoring, so switching locale in the Editor appears to do
                // nothing and the binding reads as broken. Set the state explicitly.
                var index = lse.OnUpdateString.GetPersistentEventCount() - 1;
                lse.OnUpdateString.SetPersistentListenerState(
                    index, UnityEventCallState.EditorAndRuntime);

                EditorUtility.SetDirty(lse);
                matched = true;
                wired++;
                break;
            }

            if (!matched)
                unmatched.Add($"{scenePath} :: {label.gameObject.name} :: \"{current}\"");
        }

        return unmatched;
    }
}
