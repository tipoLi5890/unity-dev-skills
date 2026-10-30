# The API renamed almost everything

Moved out of SKILL.md §2: the post-processing stack v2 names against the URP Volume names, and what a value that does not take means.

## 2. The API renamed almost everything

| Wrong — old Post Processing Stack | Correct — URP Volume framework |
|---|---|
| `PostProcessVolume` | `Volume` (`UnityEngine.Rendering`) |
| `PostProcessLayer` | `UniversalAdditionalCameraData.renderPostProcessing` (bool) |
| `profile.GetSetting<T>()` | `profile.TryGet<T>(out var t)` |
| `profile.AddSettings<T>()` | `profile.Add<T>()` — throws if present, so `Has<T>()` first |
| `VolumeManager.instance.stack.GetComponent<T>()` | `volume.profile.TryGet<T>(…)` |
| Mutating `sharedProfile` at runtime | `volume.profile` — it clones to an instance for you |

> **`VolumeProfile` exposes**
> `Add · Remove · Has · HasSubclassOf · TryGet · TryGetSubclassOf · TryGetAllSubclassOf`.
> There is **no `GetSetting`** and no `AddSettings` — code using them is from the pre-URP stack
> and will not compile. Enumerate the type rather than trusting a snippet:
> `foreach (var m in typeof(UnityEngine.Rendering.VolumeProfile).GetMethods()) …`

The component names moved too: **the class is `ColorAdjustments`;
`UnityEngine.Rendering.Universal.ColorGrading` does not resolve at all**. All sixteen
`VolumeComponent` types, every parameter with its type, default and range:
→ [`reference/effect-reference.md`](effect-reference.md).

`Add` takes an `overrides` flag (`Add(bool overrides = false)`, `Add(Type, bool overrides =
false)`), so `Add<T>(true)` is the shortest route past the `overrideState` trap above. Building a
profile and a Volume from a snippet, the `sharedProfile` versus `profile` choice (mutating
`sharedProfile` at runtime edits the asset on disk), and why `Undo.RecordObject` produces no undo
entry from `eval`: → [`reference/volume-templates.md`](volume-templates.md).

Local Volumes have three parameters worth knowing: `priority` (higher wins where they overlap),
`blendDistance` (world units of falloff outside the collider; 0 means a hard switch at the
boundary), and `weight` (0–1 overall influence).
