# Building a Volume from a snippet, and four grades to start from

> Part of the `unity-render-urp` skill. Every snippet is written for the Editor's `eval`, which
> compiles a **statement block, not a file**: no `using` directives, and ambiguous types
> qualified. Hard stops `throw` so the call fails loudly; anything the caller needs is
> `return`ed. Run §1 of the skill first — a snippet that builds a perfect Volume on a project
> rendering built-in has changed nothing you can see. §1 as one paste-in block:
> [`preflight-snippet.md`](preflight-snippet.md).

**Three compile errors mean "this is a statement block", not "the API is wrong".** Read the code
before rewriting the call:

| Error | What `eval` is rejecting | Fix |
|---|---|---|
| `CS0210` | A `using UnityEngine;` line — the compiler reads it as the *using statement*, which wants a disposable in parentheses | Delete the directives; qualify instead |
| `CS0246` / `CS0103` | A bare type name (`AssetDatabase`, `Volume`, `Bloom`) with no namespace to resolve it against | Write `UnityEditor.AssetDatabase`, `UnityEngine.Rendering.Volume`, … |
| `CS0104` | A bare `Object`, ambiguous between `UnityEngine.Object` and `System.Object` | Say which one, every time |

A snippet written as a file — with usings, because it is going into `Assets/` — has to be
qualified before it is passed to `eval`, not pasted as-is.

**Discover the command's parameter shape rather than assuming it**: `unity command --format json`
lists what the connected Editor actually registers. The inline form is
`unity command eval --code '<snippet>'`; some Pipeline package versions also register an
`eval_file` variant — **more often than not it is simply not there**, so read the catalog before
designing a workflow around writing the snippet to a file. A command is also given **30 seconds
by default**, which means a snippet that waits on an import or a bake times out by design rather
than by failure. The CLI itself is `unity-cli`.

Two API facts the snippets lean on:

- `VolumeProfile.Add` has exactly two overloads, `Add(bool overrides = false)` and
  `Add(Type type, bool overrides = false)`. **Passing `true` switches `overrideState` on for
  every parameter of the component it adds**, which is the difference between a profile that
  grades and a profile that reads correctly and does nothing.
- `Volume.HasInstantiatedProfile()` exists and returns `bool` with no arguments. It is how you
  tell an instance clone from the asset without triggering the clone.

## Create a profile asset and a global Volume

```csharp
var urpAsset = UnityEngine.Rendering.Universal.UniversalRenderPipeline.asset;
if (urpAsset == null) { throw new System.Exception("No UniversalRenderPipelineAsset is active — resolve the pipeline first."); }
if (!urpAsset.supportsHDR) { throw new System.Exception("HDR is off on the URP Asset; Tonemapping will not run."); }

UnityEditor.Undo.IncrementCurrentGroup();
UnityEditor.Undo.SetCurrentGroupName("Create post-processing Volume");
var group = UnityEditor.Undo.GetCurrentGroup();

var profile = UnityEngine.ScriptableObject.CreateInstance<UnityEngine.Rendering.VolumeProfile>();
var assetPath = UnityEditor.AssetDatabase.GenerateUniqueAssetPath("Assets/Settings/PostProcessProfile.asset");
UnityEditor.AssetDatabase.CreateAsset(profile, assetPath);

// Add(true) enables overrideState on every parameter of the component, then set only the ones
// you mean. Without the flag each assignment below reads back correctly and contributes nothing.
var bloom = profile.Add<UnityEngine.Rendering.Universal.Bloom>(true);
bloom.threshold.value = 0.9f;
bloom.intensity.value = 1f;          // the default is 0 — this line is the whole effect
bloom.scatter.value   = 0.7f;

var tone = profile.Add<UnityEngine.Rendering.Universal.Tonemapping>(true);
tone.mode.value = UnityEngine.Rendering.Universal.TonemappingMode.ACES;

// Add creates the override object; it does NOT make it a sub-asset of the profile. Without
// these two lines the profile writes and reloads with `components: []` or `{fileID: 0}`
// entries, and nothing along the way errors.
UnityEditor.AssetDatabase.AddObjectToAsset(bloom, profile);
UnityEditor.AssetDatabase.AddObjectToAsset(tone, profile);
UnityEditor.EditorUtility.SetDirty(bloom);
UnityEditor.EditorUtility.SetDirty(tone);

var volumeObj = new UnityEngine.GameObject("Global Volume");
var volume = volumeObj.AddComponent<UnityEngine.Rendering.Volume>();
volume.isGlobal = true;
volume.sharedProfile = profile;      // sharedProfile, not profile — see below

UnityEditor.Undo.RegisterCreatedObjectUndo(volumeObj, "Create post-processing Volume");
UnityEditor.EditorUtility.SetDirty(profile);
UnityEditor.AssetDatabase.SaveAssets();       // the profile is an asset: this writes it
UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(volumeObj.scene);

UnityEditor.Undo.FlushUndoRecordObjects();
UnityEditor.Undo.CollapseUndoOperations(group);
return $"profile at {assetPath}; GameObject in scene '{volumeObj.scene.name}', which is unsaved.";
```

Two things that bite here and nowhere else:

- **`Undo.RecordObject` produces no undo entry from `eval`.** It takes a *deferred* snapshot that
  Unity flushes at the end of an Editor event, and a snippet executed by the Pipeline server runs
  outside that loop. Use `IncrementCurrentGroup` → `SetCurrentGroupName` →
  `RegisterCompleteObjectUndo` / `RegisterCreatedObjectUndo` → `FlushUndoRecordObjects` →
  `CollapseUndoOperations`, as above. That sequence does not depend on the event loop, and it
  collapses to one entry the user can read in `Edit > Undo <label>`.
- **`SetDirty` marks; it does not write.** An asset needs `AssetDatabase.SaveAssets()`. A scene
  component needs the scene saved, and `SaveAssets` does nothing for it. Either way the value
  reads back correctly for the rest of the session and is gone at session end, which is the most
  expensive way to be wrong about this.
- **Reload the profile and count its non-null components before trusting it.** `Add` plus
  `SaveAssets` alone leaves the overrides outside the asset, and the only check that catches it
  reads the profile back off disk:

  ```csharp
  UnityEditor.AssetDatabase.ImportAsset(assetPath);
  var reloaded = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.Rendering.VolumeProfile>(assetPath);
  var live = 0;
  foreach (var c in reloaded.components) if (c != null) live++;
  return "live overrides after reload: " + live + " of " + reloaded.components.Count;
  ```

  Migrating a whole profile across from the old post-processing stack, where this is the usual
  failure: `unity-urp-migration`.

## Turn post-processing on for the camera

`renderPostProcessing` defaults to `false`, so this is a required step rather than a fallback.

```csharp
var cam = UnityEngine.Camera.main;
if (cam == null) { throw new System.Exception("No camera tagged MainCamera."); }
if (!cam.TryGetComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>(out var data))
{ throw new System.Exception("No UniversalAdditionalCameraData — URP is not the active pipeline on this camera."); }

var previous = data.renderPostProcessing;     // report this: it is the one-line revert

UnityEditor.Undo.IncrementCurrentGroup();
UnityEditor.Undo.SetCurrentGroupName("Enable camera post-processing");
UnityEditor.Undo.RegisterCompleteObjectUndo(data, "Enable camera post-processing");
data.renderPostProcessing = true;
UnityEditor.EditorUtility.SetDirty(data);
UnityEditor.Undo.FlushUndoRecordObjects();
UnityEditor.Undo.CollapseUndoOperations(UnityEditor.Undo.GetCurrentGroup());

var scene = data.gameObject.scene;
UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(scene);
return $"'{cam.name}'.renderPostProcessing {previous} -> true; scene '{scene.name}' modified, not saved.";
```

Whether to save the scene depends on who is watching, and it is not a judgement to skip:

- **Someone is at the Editor** — report and let them save. Saving from here also commits whatever
  else they had in progress in that scene, which is not yours to decide.
- **Batch, CI, or a session about to end** — call
  `UnityEditor.SceneManagement.EditorSceneManager.SaveScene(scene)` and say you saved it. Nobody
  is there to act on "the scene is unsaved", so leaving it unsaved just discards the work.

Capturing `previous` is what makes a revert one line if the undo entry does not land. Scenes and
prefabs are text-serialised, so version control is the last resort here, not the first answer.

## `sharedProfile` or `profile` — the choice is Editor-time versus runtime

> **`volume.profile` clones.** Reading it is enough: the getter instantiates a copy of the asset
> and hands you that. So an Editor script that reads `volume.profile`, edits an override and
> calls `SetDirty` has dirtied a clone that is not an asset, and the edit can never reach disk.

| You are | Use | Because |
|---|---|---|
| Editing at Editor time, change should persist | `sharedProfile` | it is the asset itself |
| Changing the grade at runtime | `profile` | the clone keeps the asset on disk untouched |

Mutating `sharedProfile` while the game runs edits the **asset**, so the change survives exiting
play mode and follows the project into version control. That is the mechanism behind "the scene
looks different after I ran it once".

Editor-time edit — note that even the null check has to go through `sharedProfile`:

```csharp
var volumeObj = UnityEngine.GameObject.Find("Global Volume");
if (volumeObj == null || !volumeObj.TryGetComponent<UnityEngine.Rendering.Volume>(out var volume))
{ throw new System.Exception("No Volume named 'Global Volume' in the open scene."); }
if (volume.sharedProfile == null) { throw new System.Exception("Volume has no profile asset assigned."); }

var profile = volume.sharedProfile;
if (!profile.TryGet<UnityEngine.Rendering.Universal.Bloom>(out var bloom))
{ bloom = profile.Add<UnityEngine.Rendering.Universal.Bloom>(true); }
bloom.intensity.overrideState = true;
bloom.intensity.value = 2f;
UnityEditor.EditorUtility.SetDirty(profile);
UnityEditor.AssetDatabase.SaveAssets();
return "bloom.intensity = " + bloom.intensity.value + ", overrideState = " + bloom.intensity.overrideState;
```

Runtime edit, from a MonoBehaviour rather than from `eval` — `HasInstantiatedProfile()` tells you
whether the clone already happened, so a per-frame tween does not ask for a fresh one:

```csharp
if (!volume.HasInstantiatedProfile()) { var _ = volume.profile; }   // clone once, deliberately
if (volume.profile.TryGet<Vignette>(out var v))
{
    v.intensity.overrideState = true;
    v.intensity.value = Mathf.Lerp(0f, 0.5f, damage);
}
```

`TryGet` returns `false` when the component is not on the profile — it does not add it. Adding at
runtime allocates and is a frame-time cost in the wrong place; put every component the game will
ever tween on the profile at author time and tween its value.

## Four grades to start an argument from

Values, not opinions — paste one, look at the Game view, then move the two or three numbers that
matter for the game. Bloom is written `threshold / intensity / scatter`.

| Grade | Components and values |
|---|---|
| **Cinematic** | `Tonemapping` mode `ACES`; `ColorAdjustments` contrast 15, saturation −10; `Bloom` 0.9 / 0.5 / 0.7; `Vignette` intensity 0.3, smoothness 0.4; `FilmGrain` type `Medium1`, intensity 0.2 |
| **Stylised** | `Tonemapping` mode `Neutral`; `ColorAdjustments` saturation 20, contrast 10; `Bloom` 0.8 / 1.5 / 0.6; `SplitToning` warm highlights, cool shadows |
| **Horror** | `ColorAdjustments` postExposure −0.5, saturation −30, contrast 20; `Vignette` intensity 0.5, smoothness 0.3, dark red colour; `FilmGrain` type `Large01`, intensity 0.4; `ChromaticAberration` intensity 0.15 |
| **Mobile** | `Tonemapping` mode `Neutral`; `ColorAdjustments` postExposure 0.2; `Bloom` 1.0 / 0.3 / default, `downscale` `Quarter`, `highQualityFiltering` false, `maxIterations` below 6 |

The mobile row is the only one that is a budget rather than a look; what it omits on purpose, and
why, is the skill's §3. It assumes HDR is on: without it Tonemapping does nothing and a 1.0 Bloom
threshold selects nothing. Every number in these rows sits inside its parameter's range; check
[`effect-reference.md`](effect-reference.md) before inventing a fifth grade, because a
`Clamped*Parameter` clamps in silence.

## Report shape

After building or changing a grade, say all six of these or the report is not checkable:

```
pipeline resolved active: <asset path, or "built-in">
Volume:   <Global|Local> on "<GameObject>"  (layer N, inside camera volumeLayerMask)
profile:  <asset path>
overrides: <Component>.<param> = <value>, …   (each with overrideState true)
camera:   <name>  renderPostProcessing = true  renderType = Base
saved:    <profile asset written | scene unsaved and why>
```

"Added bloom" is not a result; verify it as in the skill's §6.
