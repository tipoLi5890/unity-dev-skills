# The old post-processing stack, moved onto URP Volumes

> Part of the `unity-urp-migration` skill. The failure here is not a crash. It is a profile
> asset that saves, reloads with no components, and is wired into a scene that reports
> post-processing as active — while every command along the way returned success.

## Take the inventory by type name, not by grep

The legacy components are `UnityEngine.Rendering.PostProcessing.PostProcessVolume` and
`…PostProcessLayer`, and the profile asset is `…PostProcessProfile`. Enumerate the open scene
and match on `GetType().FullName`; a text search over scene YAML misses them often enough that
a clean grep proves nothing.

That also keeps the migration code compiling on a project that never had the package: nothing
here needs the assembly at build time when the names are strings.

Read the legacy profile's `settings` list the same way, by reflection, and translate only what
has a real counterpart.

## What maps, and what does not

| Legacy effect | URP |
|---|---|
| Bloom | `Bloom` |
| Color Grading | `ColorAdjustments` **plus** `Tonemapping` — and `LiftGammaGain` or `ChannelMixer` where the source used those curves |
| Vignette | `Vignette` |
| Depth Of Field | `DepthOfField` |
| Motion Blur | `MotionBlur` |
| Chromatic Aberration | `ChromaticAberration` |
| Grain | `FilmGrain` |
| Lens Distortion | `LensDistortion` |
| Auto Exposure | **No direct equivalent.** Start from a fixed `ColorAdjustments.postExposure` and say it is manual |
| Ambient Occlusion | **Not a Volume override** — it is an SSAO renderer feature on the renderer asset |
| Screen Space Reflections | **Unsupported in this form.** A renderer feature, probes, or a replacement — named as manual, never implied as migrated |

Colour grading splitting into two components is the one that quietly loses the look: moving the
exposure and saturation across without the tonemapper gives a picture that is right in every
value and wrong on screen.

## Persisting the profile

`VolumeProfile.Add<T>(true)` creates the override object and switches `overrideState` on for
every parameter. It does **not** make that object a sub-asset of the profile. Without the next
line, the profile writes, reloads with `components: []` or with `{fileID: 0}` entries, and
nothing errored:

```csharp
var component = profile.Add(type, true);        // Add<T>(true) for a known type
component.name = type.Name;
UnityEditor.AssetDatabase.AddObjectToAsset(component, profile);
UnityEditor.EditorUtility.SetDirty(component);
UnityEditor.EditorUtility.SetDirty(profile);
UnityEditor.AssetDatabase.SaveAssets();
UnityEditor.AssetDatabase.ImportAsset(profilePath);

var reloaded = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.Rendering.VolumeProfile>(profilePath);
var live = 0;
foreach (var c in reloaded.components) if (c != null) live++;
return "live overrides after reload: " + live + " of " + reloaded.components.Count;
```

Both objects get dirtied, both get saved, and the count is taken **after the reload**. Counting
`profile.components` on the object still in memory reports the number you just added whether or
not any of it reached disk.

## Wiring the scene

Put the URP `Volume` on the old post-processing GameObject, or on a new global one. Either is
fine; two global Volumes in one scene is not, because the result is a blend nobody authored.

- `isGlobal = true`, `enabled = true`, and set **`sharedProfile`** — at Editor time `profile`
  hands back a clone, so an edit through it can never reach disk. The `sharedProfile` versus
  `profile` choice, and the undo sequence that works from `eval`, are `unity-render-urp` →
  `reference/volume-templates.md`.
- The camera needs `UniversalAdditionalCameraData.renderPostProcessing = true`. It defaults to
  false, so this is a step, not a fallback.
- `MarkSceneDirty` then `SaveScene`. **`AssetDatabase.SaveAssets()` writes the profile and not
  the scene**, so a migration that only calls it has a profile on disk and a Volume reference
  that exists until the Editor closes.

> **Setting the wrong `sharedProfile`.** Reusing the old GameObject means two components with
> that property name are sitting on it. Assigning the new URP profile to the *legacy*
> component's `sharedProfile` leaves the old stack running, no URP Volume referencing anything,
> and a scene that looks wired. Add the URP `Volume` component and set that one's property.

## Switching the old stack off

Disable — do not delete — every legacy component, matched by `FullName`. Keep them until
parity is accepted or the owner approves cleanup; they are the only reference for what the
picture used to look like.

Verify two things together: every legacy component re-queried reads back disabled, **and** the
scene saved clean. `m_Enabled: 0` is what lands in the file, but searching the whole scene text
for that string proves nothing on its own — every disabled component in the scene writes the
same line, including the ones nobody touched. A component disabled in memory and never saved is
a picture that changes back on the next open.

> **Double post-processing is the first hypothesis for a blown-out capture after migration**,
> ahead of lighting and ahead of exposure. Two stacks each applying bloom and a tonemapper
> stack multiplicatively, and the result reads exactly like a bad bake.

## Before touching a single value

Run the five-switch pre-flight in `unity-render-urp` §1 — active pipeline, HDR, camera
`renderPostProcessing` and a non-null PostProcessData, the Volume's layer against the camera's
`volumeLayerMask`, and at least one override with `overrideState` true. Four of those five
default to off or narrow, and none of them warns. Tuning a parameter before they pass is
tuning something that is not on screen.

## Worked example — the courier run

The gate scene's legacy profile carries Bloom, Color Grading on an ACES tonemapper, a Vignette
and a shallow Depth Of Field that keeps the runner sharp against the far gate.

After `resources/VolumeMigration.cs`:

```
[URP-MIG] postfx status=complete profile=Assets/Settings/Migrated-PostProcess.asset
  overrides=Bloom,ColorAdjustments,Tonemapping,Vignette,DepthOfField nullEntries=0
  sceneVolume=URP Global Volume camPostProcessing=True legacyDisabled=2/2 manual=none
  scene=Assets/Scenes/GateRun.unity
```

Five overrides from four legacy effects — colour grading became two — every one of them counted
after the reload, the scene file naming the profile's GUID, and both legacy components saved as
disabled. Had the source profile also carried ambient occlusion, `manual=` would name it, and
the phase would be `Manual follow-up` rather than complete.
