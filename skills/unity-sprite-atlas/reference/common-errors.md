# Six atlas failures, and the check that settles each

## 1. A cast on `format`

`TextureImporterPlatformSettings.format` is a **property of type `UnityEditor.TextureImporterFormat`**
— reflection finds no field of that name at all. The value is stored as an integer
internally, which is why the cast looks plausible, but the property does not accept one.

```csharp
// compile error
var s = new UnityEditor.TextureImporterPlatformSettings {
    format = (int)UnityEditor.TextureImporterFormat.ASTC_6x6
};

// correct — delete the cast, do not widen it
var s = new UnityEditor.TextureImporterPlatformSettings {
    name          = "Android",
    overridden    = true,
    maxTextureSize = 2048,
    format        = UnityEditor.TextureImporterFormat.ASTC_6x6
};
```

`overridden = true` is the field that makes the rest of the struct matter. Set the platform's
settings without it and the atlas keeps the default platform entry.

## 2. `SetMasterAtlasPath` does not exist

Reflection finds no member of that name on `SpriteAtlasAsset`. Neither a path string nor
a `SpriteAtlasAsset` will do: `SetMasterAtlas` takes a **`UnityEngine.U2D.SpriteAtlas`**, the runtime
type, loaded from the already-imported master.

```csharp
var master = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.U2D.SpriteAtlas>(masterPath);
if (master == null) throw new System.Exception($"master atlas not imported yet: {masterPath}");
variant.SetMasterAtlas(master);
```

The master must exist **and be imported** first. Creating both atlases in one pass without an
`AssetDatabase.ImportAsset` between them gives a null master and a variant pointing at nothing.

## 3. A format the enum offers and the platform refuses

`TextureImporterFormat` is shared with every texture importer, so it offers far more than any one
platform accepts, and an assignment to `format` is not a request the enum can refuse. The Editor
will answer the question directly, though, and the answer is a static call away:

```csharp
UnityEditor.TextureImporter.IsPlatformTextureFormatValid(
    UnityEditor.TextureImporterType.Sprite,
    UnityEditor.BuildTarget.iOS,
    UnityEditor.TextureImporterFormat.ASTC_4x4);      // -> True
```

**PVRTC is refused on every target, including iOS.** `PVRTC_RGB4` and `PVRTC_RGBA4` both return
`False` for `iOS`, `Android`, `WebGL`, `StandaloneOSX`, `StandaloneWindows64` and
`StandaloneLinux64` — six for six, no exceptions. The
package documentation says the same thing about a V2 atlas specifically. Do not reach for a PVRTC
format on a mobile atlas; ASTC is the replacement on both mobile platforms.

The same call across the other common formats, `TextureImporterType.Sprite`:

| Target | Valid | Refused |
|---|---|---|
| Android | `ASTC_4x4`, `ASTC_6x6`, `ETC2_RGBA8`, `DXT5` | `PVRTC_*`, `BC7` |
| iOS | `ASTC_4x4`, `ASTC_6x6`, `ETC2_RGBA8` | `PVRTC_*`, `DXT5`, `BC7` |
| WebGL | `ASTC_4x4`, `ASTC_6x6`, `ETC2_RGBA8`, `DXT5`, `BC7` | `PVRTC_*` |
| macOS / Windows / Linux (`Standalone`) | `DXT5`, `BC7` | `PVRTC_*`, `ASTC_*`, `ETC2_RGBA8` |

Reach for `ASTC_6x6` on mobile and drop to `ASTC_4x4` where quality matters more than size; `DXT5`
or `BC7` on desktop.

That call validates a **sprite texture** import for a build target — the same format table the
atlas importer draws from, but not the atlas import itself. So read the setting back with
`GetPlatformSettings` after `SaveAndReimport()` and confirm the format you asked for is the format
that stuck.

## 4. `PackAtlases` takes runtime atlases

The signature — one overload, no others:

```csharp
static void PackAtlases(UnityEngine.U2D.SpriteAtlas[] atlases,
                        UnityEditor.BuildTarget target,
                        bool canCancel)
```

So an array of `SpriteAtlasAsset` — the type you just authored with — does not compile against it.
Load the runtime objects for the paths you care about:

```csharp
var atlases = UnityEditor.AssetDatabase.FindAssets("t:SpriteAtlas", new[] { "Assets" })
    .Select(UnityEditor.AssetDatabase.GUIDToAssetPath)
    .Select(UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.U2D.SpriteAtlas>)
    .Where(a => a != null)
    .ToArray();
try
{
    UnityEditor.U2D.SpriteAtlasUtility.PackAtlases(
        atlases, UnityEditor.EditorUserBuildSettings.activeBuildTarget, canCancel: false);
}
finally
{
    UnityEditor.U2D.SpriteAtlasUtility.CleanupAtlasPacking();
}
```

The `finally` matters more than it looks: a cancelled or thrown pack that skips the cleanup leaves
temporary packing state behind for the next run to trip over.

## 5. An unscoped `FindAssets` reaches into `Packages/`

`AssetDatabase.FindAssets` has **exactly two overloads**:

```csharp
string[] FindAssets(string filter)
string[] FindAssets(string filter, string[] searchInFolders)
```

There is no search-mode parameter, so a call written as if there were does not compile. The one that
*does* compile is the dangerous one — the single-argument form searches the whole asset database,
packages included, and a batch operation that then writes to what it found either fails on
read-only imports or modifies assets it had no business touching.

```csharp
// searches every installed package too
var all = UnityEditor.AssetDatabase.FindAssets("t:SpriteAtlas");

// scoped to the project's own assets
var mine = UnityEditor.AssetDatabase.FindAssets("t:SpriteAtlas", new[] { "Assets" });
```

Narrow it further where you can — `new[] { "Assets/Art" }` costs nothing and cannot surprise you.
The size of the difference depends entirely on a project's installed packages; measure it there
rather than carrying a number over.

## 6. `AssetImporter.GetAtPath` takes one argument

There is no overload accepting a type. Pass the path, cast the result, and check for null — the cast
returns null both when the path has no importer and when the importer is a different kind, and those
need the same handling anyway.

```csharp
var importer = UnityEditor.AssetImporter.GetAtPath(atlasPath)
             as UnityEditor.U2D.SpriteAtlasImporter;
if (importer == null)
    throw new System.Exception($"no SpriteAtlasImporter at {atlasPath} — was it imported?");
```

The commonest cause of null here is the missing `AssetDatabase.ImportAsset(path)` after
`SpriteAtlasAsset.Save` — the file is on disk, the asset database has not been told, and no importer
exists yet.

## And the one that is not an error

Editor code that calls `Add`, `SetTextureSettings`, `SetPackingSettings` or `SetIncludeInBuild` on a
runtime `SpriteAtlas` **compiles and runs**. Those are extension methods in
`UnityEditor.U2D.SpriteAtlasExtensions` (fifteen of them), and they are the V1 authoring
model. There is no diagnostic to catch this: the code is legal, the atlas is not configured the way
V2 reads it, and the symptom arrives later as settings that do not appear to apply. Author with
`SpriteAtlasAsset`, configure with `SpriteAtlasImporter`, and use exactly one member of that
extension class — `GetPackables`.
