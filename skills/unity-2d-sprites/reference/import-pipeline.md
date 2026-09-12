# Sprite metadata inside a real project — asmdefs, import rules, and the order the passes run in

> Part of the `unity-2d-sprites` skill. The parent file covers the data-provider API for a one-off
> edit driven through a live Editor. This file is what changes once the same work lives in the
> project as committed Editor code that runs over a whole art folder — the three places it fails
> are the assembly reference, the import mode, and the order of the passes.

## 1. Editor code in an asmdef needs `Unity.2D.Sprite.Editor` spelled out

An `eval` statement compiles in the Editor's own context and sees the sprite types with nothing
declared. **Editor code inside your own assembly definition does not.** Until
`"Unity.2D.Sprite.Editor"` is appended to that asmdef's `references`, `ISpriteEditorDataProvider`,
`SpriteDataProviderFactories`, `EEditCapability` and friends do not resolve — and the compiler
error is the ordinary *type or namespace could not be found*, which reads like the package being
absent (the parent skill's §0 covers that case). That collision is the whole trap:
people go and re-add a package the project already has.

```jsonc
{
  "name": "YourProject.Editor",
  "references": [ /* … */ "Unity.2D.Sprite.Editor" ],
  "includePlatforms": ["Editor"]
}
```

Diagnose in this order, and stop at the first thing that is false:

1. `Packages/manifest.json` contains `"com.unity.2d.sprite"` (e.g.
   `"com.unity.2d.sprite": "1.0.0"`).
2. Your Editor asmdef references `Unity.2D.Sprite.Editor`.
3. Only then is it your code.

**The package is built into the Editor installation, not downloaded.** On macOS the assembly
definition lives at
`/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/Resources/PackageManager/BuiltInPackages/com.unity.2d.sprite/Editor/Unity.2D.Sprite.Editor.asmdef`;
on Windows or Linux, look for the same `BuiltInPackages` directory under the Editor install. So on
an offline machine the manifest line still resolves — it is a manifest edit, not a fetch.

## 2. Import settings live in one committed `AssetPostprocessor` — which only fires on import

The parent skill's rule ("standalone snippets, no `AssetPostprocessor`") is about **a script an
agent writes to do one job once**: a postprocessor left behind from a one-off keeps rewriting every
future import invisibly. That rule does not apply to a project that *deliberately* owns its import
settings in one committed postprocessor — which is the right shape once a whole `Assets/Art` tree
has to import consistently. Both are true; the distinguishing question is whether a human decided
the file should exist forever.

When it is that committed file, two consequences follow.

**Assets already in the project keep their old settings.** `OnPreprocessTexture` runs on import,
so writing the rule changes nothing that is already imported: the settings you are reading in the
Inspector are whatever was in effect the day the file landed. Retrofit by forcing a recursive
reimport, and make that the *first statement* of the metadata tool so the two can never disagree:

```csharp
AssetDatabase.ImportAsset("Assets/Art",
    ImportAssetOptions.ImportRecursive | ImportAssetOptions.ForceUpdate);
// …now walk the textures and write pivots / borders / slices through the data provider
```

**The postprocessor and the slicer must agree on which files are `Multiple`.** Have both call one
shared helper (`FrameCount(file, out stem)`, §3), so the decision exists once. Two independent
guesses at the same question is how a texture ends up in `Multiple` mode with no rects — see §4,
which is the worst failure in this file.

What one such postprocessor sets, as an example of the shape rather than a set of numbers to
copy — the load-bearing part is that they are in one file, not their values (a 2D game targeting
Android, sprites drawn in UI space):

| Setting | Value | Why pin it |
|---|---|---|
| `textureType` | `Sprite` | Nothing else gives sprite data at all |
| `spriteImportMode` | from the filename rule | §4 |
| `sRGBTexture` | `true` | Colour art, not data |
| `spritePixelsPerUnit` | 100 | Per-asset; the default is rarely what a project means |
| `mipmapEnabled` | `false` | 2D drawn at ~1:1; mipmaps only blur it and cost memory |
| `filterMode` | `Bilinear` | Not pixel art. A pixel-art project wants `Point` |
| `wrapMode` | `Clamp`, `Repeat` for the one tiling background | Clamp stops edge bleed |
| `alphaIsTransparency` | `true` | Otherwise the fringe of every cut-out darkens |
| `isReadable` | `false` | A readable texture keeps a second CPU copy resident |
| `maxTextureSize` | 1024, 2048 for `bg_`/`hero_` | Filename prefix decides |
| Android override | `overridden = true`, `ASTC_6x6`, compressed | An override that is not `overridden` does nothing |

## 3. Let the filename decide, in one helper

A `_N` suffix where `N` is 2..16 means "an N-frame horizontal strip"; everything else is a single
sprite. One helper returns the frame count and the stem, and both passes call it:

```csharp
public static int FrameCount(string file, out string stem)
{
    stem = file;
    int us = file.LastIndexOf('_');
    if (us > 0 && int.TryParse(file.Substring(us + 1), out int n) && n >= 2 && n <= 16)
        { stem = file.Substring(0, us); return n; }
    return 1;
}
```

The upper bound matters: without it, art named `hero_2048` or `bg_1024` reads as a frame count.

## 4. `Multiple` with no slice data publishes **no sprite named after the file**

> Symptom: an EditMode test fails with `sprite '<filename>' not found` while the texture sits in
> the Project window looking perfectly normal, and every `Resources.Load<Sprite>` /
> `AssetDatabase` lookup by filename returns `null`.

Cause: in `Single` mode the importer publishes one `Sprite` sub-asset named after the file. In
`Multiple` mode it publishes **exactly the rects the sprite data holds** — and a texture that was
flipped to `Multiple` but never sliced holds none, so the asset contains a `Texture2D` and nothing
else. The name every lookup depends on is simply gone, with no error anywhere.

The usual cause is an import rule that *preserves* whatever `spriteImportMode` a texture already
had. State the mode from the filename rule instead, so it is always derived and never inherited:

```csharp
ti.spriteImportMode = FrameCount(file, out _) > 1
    ? SpriteImportMode.Multiple                     // a real strip, which the slicer will cut
    : SpriteImportMode.Single;                      // sprite name == file name, which code loads by
```

Two corollaries:

- **`Multiple` is a promise to slice.** Never set it "to be safe". If a pass sets it, the same run
  must write rects, or the asset ships nameless.
- **In `Single` mode there may be nothing to write to.** To set a pivot or a border you need a
  `SpriteRect`; when the provider hands back an empty list, add one covering the whole texture,
  named after the file stem. Whether or not the provider returns zero rects there, the guard
  costs one line and removes the question.

Verify by loading the name, not by counting rects — same acceptance test as the parent skill's §6:

```csharp
var names = new System.Collections.Generic.List<string>();
foreach (var o in UnityEditor.AssetDatabase.LoadAllAssetsAtPath(path))
    if (o is UnityEngine.Sprite s) names.Add(s.name);
return string.Join(", ", names);          // the file's own name must be in here
```

## 5. Two passes, and the wiring pass runs second

Dropping PNGs into the art folder does not put them in the game. There are two passes and they are
not commutative:

```
1. metadata pass   reimport (§2) → textureType/mode → pivots, borders, slices
2. wiring pass     the generator that writes Sprite references into ScriptableObjects,
                   prefabs, catalogues, theme assets …
```

The wiring pass captures `Sprite` references **at generation time**. Run it before the metadata
pass and it captures what exists then: nothing for an unsliced strip, `null` for a texture that is
still `Multiple`-with-no-rects, and the whole set of fields serialises as null. There is no error —
the game is just missing its art at runtime, one indirection away from the actual mistake.

Each pass is a separate headless invocation, and **a pass that wired nothing still exits 0**, so
assert on artifacts rather than exit codes (`unity-debug` covers reading the log back). The entry
points are whatever the project calls them — there is no standard pair:

```bash
"$UNITY" -batchmode -quit -projectPath . -logFile - -executeMethod <Ns>.<SpriteMetaTool>.Apply
"$UNITY" -batchmode -quit -projectPath . -logFile - -executeMethod <Ns>.<AssetWiringTool>.Run
```

The failure mode is silent, and re-running the generator is the fix nobody thinks of because the
files are visibly on disk.
