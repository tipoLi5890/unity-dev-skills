# Routing Audio Sources into mixer groups

> Part of the `unity-audio` skill. Everything here is a **scene** edit made through a live
> Editor — `unity-debug` → `reference/editor-control.md` gets you a connection with `eval`.

## The split that decides the whole workflow

Reading a mixer and pointing an Audio Source at one of its groups is ordinary public API. **Creating
a mixer, creating a group, re-parenting a group and setting a group's volume are not** — those calls
live on `UnityEditor.Audio.AudioMixerController` and `AudioMixerGroupController`, and both types
report `IsPublic = false`. The public runtime bases they derive from,
`UnityEngine.Audio.AudioMixer` and `AudioMixerGroup`, carry every read and write below.

| Operation | Route |
|---|---|
| Find the project's mixers | `AssetDatabase.FindAssets("t:AudioMixer", …)` |
| List a mixer's groups | `AudioMixer.FindMatchingGroups(string subPath)` → `AudioMixerGroup[]` |
| Read an Audio Source's current group | `AudioSource.outputAudioMixerGroup` |
| Assign a group to an Audio Source | `AudioSource.outputAudioMixerGroup` |
| Create a mixer or a group, set a group's volume | no public route — the user does it in the Audio Mixer window |

Signatures: `FindMatchingGroups` takes one `string` and
returns `AudioMixerGroup[]`; `outputAudioMixerGroup` is typed as the public `AudioMixerGroup`
and is read **and** write, so routing needs no cast and no reflection.

**Do not work around the missing half.** Reflection onto a controller type compiles and then
fails at runtime on some future version, which reads to the user as a Unity bug rather than as
your choice. Hand-editing a `.mixer` file is worse: the structure is not safely authorable
blind. If a group is missing, the answer is a sentence asking for it, not a workaround.

The division of labour that follows is favourable anyway. Walking dozens of sources and deciding
what each one is — that is the tedious part, and it is the part that is fully automatable.

## The pass, in order

1. **Inventory.** Run the first snippet. If there is no mixer under `Assets/` at all, say so and
   stop: creating one has no public route. Ask for one (Window → Audio → Audio Mixer, then the
   **+** beside Mixers) and resume when it exists.
2. **Read the current routing.** Second snippet. Sources already pointed somewhere sensible are
   not yours to move.
3. **Classify** every source (next section) and present the proposed routing — each Audio Source
   and the group it would go to.
4. **Report, then wait.** The user revises the list; some categories will need groups that do
   not exist yet.
5. **Re-run the inventory** after they say the groups are there. Confirm the groups exist *and*
   how they are spelled. Neither is safe to assume.
6. **Route.** Third snippet, one Undo group for the whole pass.
7. **Say that the scene changed** and save only with agreement.

## Classifying a source

Read the **clip asset name first**; fall back to the GameObject name, then to the names of
adjacent components, only when the clip name says nothing.

| Clip asset name | Category |
|---|---|
| `FootStep4_Sound` | Foley |
| `Dialogue_Female_Scene4` | Vox |
| `GunShot` | SFX |
| `Menu_Theme_Variation` | Music |

Two rules that decide the argument you will have:

- **Prefer an existing group** when it genuinely covers the category, even where you would have
  named it differently. Someone else's naming is not a defect.
- **Foley is a subset of SFX, not a synonym for it.** A gunshot does not belong in a `Foley`
  group merely because one exists. Where the existing groups cover only part of your
  categories, say which fit and which need a new group, and let the user decide. When
  confidence on a source is low, propose an `Uncategorized` group rather than guessing it into
  a real one.

## Inventory the mixers and their groups

```csharp
// Scope the search to Assets. Unscoped, FindAssets also walks read-only package assets, and the
// inventory then lists mixers the user did not author and cannot edit. The only two overloads
// are (string) and (string, string[] searchInFolders); there is no search-mode parameter to
// reach for instead.
var guids = UnityEditor.AssetDatabase.FindAssets("t:AudioMixer", new[] { "Assets" });
if (guids.Length == 0) { return "no AudioMixer asset under Assets/"; }

var rows = new System.Collections.Generic.List<string>();
foreach (var guid in guids)
{
    var path = UnityEditor.AssetDatabase.GUIDToAssetPath(guid);
    var mixer = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.Audio.AudioMixer>(path);
    var groups = mixer.FindMatchingGroups("");
    var names = System.Linq.Enumerable.Select(groups, g => g.name);
    rows.Add($"{path}  ({groups.Length} groups): {string.Join(", ", names)}");
}
return string.Join("\n", rows);
```

`FindMatchingGroups("")` matches every group and hands them back as the public
`AudioMixerGroup` — exactly the type routing needs. **The list is flat.** It does not describe
the parent/child shape, and there is no public way to ask for that shape. If the hierarchy
matters to the conversation, have the user read it off the Audio Mixer window instead of
reaching for the non-public tree API.

## Read where the scene's sources currently point

```csharp
var sources = UnityEngine.Object.FindObjectsByType<UnityEngine.AudioSource>(
    UnityEngine.FindObjectsInactive.Include, UnityEngine.FindObjectsSortMode.None);

var rows = new System.Collections.Generic.List<string>();
foreach (var source in sources)
{
    var group = source.outputAudioMixerGroup;
    rows.Add($"{source.gameObject.name}: clip={(source.clip != null ? source.clip.name : "<none>")}, "
           + $"group={(group != null ? group.name : "<none — routes to Master>")}");
}
return rows.Count == 0 ? "no Audio Source in the open scene" : string.Join("\n", rows);
```

`FindObjectsInactive.Include` is deliberate: a disabled Audio Source still ships with the scene
and still needs a group.

## Assign the groups

This is the only write in the file.

**Key the mapping on the identifier you actually classified by.** Classification reads the clip
asset name first and the GameObject name second, so the mapping has to accept either — keyed on
GameObject name alone it silently drops every source you classified by its clip.

```csharp
var mixer = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.Audio.AudioMixer>(
    "Assets/Audio/GameMixer.mixer");

// A key is a clip asset name or a GameObject name — whichever the classification used.
var assignments = new System.Collections.Generic.Dictionary<string, string> {
    { "FootStep4_Sound", "Foley" },   // clip name
    { "MenuMusic",       "Music" },   // GameObject name
};

var sources = UnityEngine.Object.FindObjectsByType<UnityEngine.AudioSource>(
    UnityEngine.FindObjectsInactive.Include, UnityEngine.FindObjectsSortMode.None);

var done = new System.Collections.Generic.List<string>();
var noSuchGroup = new System.Collections.Generic.List<string>();
var unmapped = new System.Collections.Generic.List<string>();

UnityEditor.Undo.IncrementCurrentGroup();
UnityEditor.Undo.SetCurrentGroupName("Route Audio Sources to mixer groups");

foreach (var source in sources)
{
    var clipName = source.clip != null ? source.clip.name : null;
    string wanted = null;
    if (clipName != null) { assignments.TryGetValue(clipName, out wanted); }
    if (wanted == null) { assignments.TryGetValue(source.gameObject.name, out wanted); }

    if (wanted == null)
    {
        unmapped.Add($"{source.gameObject.name} (clip={clipName ?? "<none>"})");
        continue;
    }

    var group = System.Array.Find(mixer.FindMatchingGroups(""), g => g.name == wanted);
    if (group == null) { noSuchGroup.Add($"{source.gameObject.name} -> {wanted}"); continue; }

    // RegisterCompleteObjectUndo takes the snapshot now. RecordObject defers to the end of an
    // Editor event, which a snippet run by the Pipeline server is outside of.
    UnityEditor.Undo.RegisterCompleteObjectUndo(source, "Route Audio Source");
    source.outputAudioMixerGroup = group;
    UnityEditor.EditorUtility.SetDirty(source);
    done.Add($"{source.gameObject.name} -> {group.name}");
}

UnityEditor.Undo.FlushUndoRecordObjects();
UnityEditor.Undo.CollapseUndoOperations(UnityEditor.Undo.GetCurrentGroup());

var report = $"routed {done.Count}: {string.Join(", ", done)}";
if (noSuchGroup.Count > 0) { report += $"\nNO SUCH GROUP (create it first): {string.Join(", ", noSuchGroup)}"; }
if (unmapped.Count > 0) { report += $"\nNOT IN THE MAPPING (unrouted): {string.Join(", ", unmapped)}"; }
return report;
```

One Undo group for the pass, so the user backs the whole thing out with one keystroke rather
than one per source.

## Three things to report rather than swallow

- **`NO SUCH GROUP`.** A group you expected is not in the mixer — nearly always a spelling
  difference between what you asked for and what was typed. Resolve it with the user; do not
  drop the source.
- **`NOT IN THE MAPPING`.** Sources the classification missed. "Routed 4" while three sources
  were quietly skipped is the worst available outcome here, because it reads as success.
- **The scene changed, not the mixer asset.** `outputAudioMixerGroup` lives on the Audio Source,
  so nothing persists until the scene is saved
  (`UnityEditor.SceneManagement.EditorSceneManager.SaveOpenScenes()`). Say so. Save only with
  agreement when someone is at the Editor — a save from here also commits whatever else they had
  in progress in that scene.

## Handing a missing group back

There is no programmatic route, so hand it over precisely — name the mixer and the exact group
name:

> In Window → Audio → Audio Mixer, select **GameMixer**, click the **+** beside Groups, and name
> the new group **SFX**. Drag it under Master if it does not land there. Tell me when it exists
> and I will route the sources.

Then re-run the inventory. Do not assume it was done, and do not assume it was spelled the way
you asked.

## Out of this file

Volume, effects and re-parenting: no public route, so they are the user's job in the Audio Mixer
window. Group depth and the cost of an effect on a silent group is the skill's §4. What each
group *should* sound like is mixing, which the skill's Scope puts outside the library entirely.
