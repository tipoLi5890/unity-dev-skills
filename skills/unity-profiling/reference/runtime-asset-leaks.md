# Runtime-made materials and meshes that never go away

> Part of the `unity-profiling` skill. Memory that grows by a fixed step every time a screen is
> rebuilt, with no frame-time symptom at all. Worked setting: a tennis game that rebuilds its match
> screen (court lines, ball, effects, HUD) at the start of every match.

## Why it leaks

`new Material(...)`, `new Mesh()`, `new Texture2D(...)`, `Renderer.material` (the getter makes a
copy) and TextMeshPro's `fontMaterial` getter and `outlineWidth` / `outlineColor` setters (each copies
the font material for that label) create assets that belong to nobody. Destroying
the GameObject that used them does not destroy them. They stay until
`Resources.UnloadUnusedAssets` runs, and a game that rebuilds a screen without a scene load may
never run it.

In the tennis game every match left behind its court-line meshes, effect materials, particle
materials, and **sixteen copies of the HUD font material**: the outline on each timing-grade label
was set with `outlineWidth` and `outlineColor`, which copy the font's material per label.

## The fix: an owner for every runtime asset

`resources/OwnedAssets.cs`: register each created asset with the component that made it, and the
asset is destroyed in that object's `OnDestroy`.

```csharp
var ring = OwnedAssets.Own(this, new Material(lineMaterial) { name = "HitRing" });
var lines = OwnedAssets.Own(this, new Mesh { name = "CourtLines" });
```

- Name every runtime asset; the soak test reports growth by name.
- For TextMeshPro outlines, build one material per (source material, outline width) once, cache
  it in a static dictionary cleared on `RuntimeInitializeLoadType.SubsystemRegistration`, and assign
  it to `fontSharedMaterial` (`unity-ui-ugui` → `reference/text-and-image-traps.md`).
- Prefer `sharedMaterial` plus a `MaterialPropertyBlock` over `Renderer.material` for per-object
  colour.

## The proof: a soak test

`templates/AssetLeakSoakTest.cs`: cycle the situations three times (the tennis game used three
situations, so nine matches), take the counts of `Material` and `Mesh` after round one as the
baseline, and fail if round three exceeds it by more than 4. On failure it logs what grew, by name.
Do not call `Resources.UnloadUnusedAssets` in the test; it would hide the leak.

Run it in the smoke category. A leak of a few materials per match is invisible in any single
session a person plays, and it only grows.
