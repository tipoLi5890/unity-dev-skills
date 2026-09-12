# The V2 surface, enumerated

Enumerate a type on your Editor by reflection before writing against one of its members. Members
people commonly reach for that do not exist are listed too, because an absent method and a
mistyped one produce the same compiler message.

Both `SpriteAtlasAsset` / `SpriteAtlasImporter` (`UnityEditor.CoreModule`) and `SpriteAtlas` /
`SpriteAtlasManager` (`UnityEngine.CoreModule`) are part of the Editor install. No package has to
be added for any of this to compile.

## SpriteAtlasAsset — `UnityEditor.U2D`

Editor-only. Constructed with `new`, persisted with the static pair.

| Member | Signature |
|---|---|
| Content | `void Add(Object[] objects)`, `void Remove(Object[] objects)` |
| Variant | `void SetIsVariant(bool value)`, `bool isVariant { get; }`, `void SetMasterAtlas(SpriteAtlas atlas)`, `SpriteAtlas GetMasterAtlas()` |
| Packer | `void SetScriptablePacker(ScriptablePacker obj)` |
| Persistence | `static void Save(SpriteAtlasAsset asset, string assetPath)`, `static SpriteAtlasAsset Load(string assetPath)` |

**Absent.** Reflection finds no `RemoveAt`, no `GetPacker`, no `GetPackables` and no
`SetMasterAtlasPath` on this type. Content is removed by handing `Remove` the objects, the current
packer cannot be read back, packables are read through the Editor extension on the runtime type
(below), and a master atlas is set by reference.

**Present but `[Obsolete]`.** Enumerating the declared methods and filtering on
`ObsoleteAttribute` returns **nine** of the seventeen — the whole settings surface, whose job moved
to `SpriteAtlasImporter`. The nine:

| Obsolete on the asset | Use instead on the importer |
|---|---|
| `SetVariantScale(float)` | `variantScale` |
| `SetIncludeInBuild(bool)`, `IsIncludeInBuild()` | `includeInBuild` |
| `SetTextureSettings(SpriteAtlasTextureSettings)`, `GetTextureSettings()` | `textureSettings` |
| `SetPackingSettings(SpriteAtlasPackingSettings)`, `GetPackingSettings()` | `packingSettings` |
| `SetPlatformSettings(TextureImporterPlatformSettings)`, `GetPlatformSettings(string)` | `SetPlatformSettings` / `GetPlatformSettings` |

That leaves eight live methods — the four content-and-variant calls, `SetScriptablePacker`,
`GetMasterAtlas`, and the static `Save` / `Load` — plus the `isVariant` property.

**Do not follow the deprecation message.** The attribute text names importer *methods*
(`SpriteAtlasImporter.SetVariantScale`, `.SetIncludeInBuild`, `.SetTextureSettings`,
`.GetTextureSettings`, `.SetPackingSettings`, `.GetPackingSettings`), and six of those do not exist:
the importer's declared surface is four properties plus `SetPlatformSettings` /
`GetPlatformSettings` and nothing else.
Follow the right-hand column above instead.

All nine still compile, with a warning. Code that uses them configures nothing on a V2 atlas, so
that warning is the only signal you get.

## SpriteAtlasImporter — `UnityEditor.U2D`

Derives from `UnityEditor.AssetImporter`, which is where `SaveAndReimport()` comes from.
Obtained with a single-argument `AssetImporter.GetAtPath(path)` and a cast. Nothing on this type
carries `[Obsolete]`.

| Member | Type |
|---|---|
| `variantScale` | `float`, get/set |
| `includeInBuild` | `bool`, get/set |
| `packingSettings` | `SpriteAtlasPackingSettings`, get/set |
| `textureSettings` | `SpriteAtlasTextureSettings`, get/set |
| `GetPlatformSettings(string buildTarget)` | returns `TextureImporterPlatformSettings` |
| `SetPlatformSettings(TextureImporterPlatformSettings src)` | void |

The two settings properties return **structs**, so a member assignment through the property is lost.
Local, edit, assign back — the same discipline any struct-valued importer property needs.

## The settings structs

`SpriteAtlasTextureSettings`: `maxTextureSize` (**get only**), `anisoLevel`, `filterMode`,
`generateMipMaps`, `readable`, `sRGB`.

`SpriteAtlasPackingSettings`: `blockOffset`, `padding`, `enableRotation`, `enableTightPacking`,
`enableAlphaDilation`.

Max texture size being read-only here is worth noticing: the per-platform cap is set through
`TextureImporterPlatformSettings.maxTextureSize`, not through the texture settings struct.

`TextureImporterPlatformSettings` properties, in declaration order: `name`, `overridden`,
`ignorePlatformSupport`, `maxTextureSize`, `resizeAlgorithm`, `format`, `textureCompression`,
`compressionQuality`, `crunchedCompression`, `allowsAlphaSplitting`, `androidETC2FallbackOverride`.
**`format` is a property of type `UnityEditor.TextureImporterFormat`** — see
[`common-errors.md`](common-errors.md) for the cast that does not belong there.

Platform names for `GetPlatformSettings` and for the `name` field are the Editor's build-group
strings: `Standalone`, `Android`, `iOS`, `WebGL`, `WSA`, `tvOS`, with Windows, macOS and Linux all
answering to `Standalone` rather than to one name each. Round-trip a name before trusting it —
set it, read it back with `GetPlatformSettings` and check `overridden` — above all on a platform
this list does not cover.

## SpriteAtlasUtility — `UnityEditor.U2D`

Three static methods, and no others:

```csharp
static void PackAllAtlases(BuildTarget target, bool canCancel)
static void PackAtlases(UnityEngine.U2D.SpriteAtlas[] atlases, BuildTarget target, bool canCancel)
static void CleanupAtlasPacking()
```

`PackAtlases` has exactly one overload and its element type is the **runtime** `SpriteAtlas`.
Call `CleanupAtlasPacking()` from a `finally` after either pack call.

## SpriteAtlas — `UnityEngine.U2D`

The whole declared instance surface:

| Member | Signature |
|---|---|
| `spriteCount` | `int`, get |
| `tag` | `string`, get |
| `isVariant` | `bool`, get |
| `GetSprite(string name)` | `Sprite` |
| `GetSprites(Sprite[] sprites)` | `int` — fills the array, returns the count |
| `GetSprites(Sprite[] sprites, string namePrefix)` | `int` |
| `CanBindTo(Sprite sprite)` | `bool` |

Size the array from `spriteCount` before the fill call; the method does not allocate for you.

## SpriteAtlasExtensions — `UnityEditor.U2D`

An Editor-only extension class over the runtime type. This is why some code that "scripts a
`SpriteAtlas` in the Editor" compiles at all. Fifteen methods:

```
Add, Remove, GetPackables,
GetTextureSettings, SetTextureSettings,
GetPackingSettings, SetPackingSettings,
GetPlatformSettings, SetPlatformSettings,
SetIncludeInBuild, IsIncludeInBuild,
SetIsVariant, SetMasterAtlas, SetVariantScale, GetMasterAtlas
```

`GetPackables(SpriteAtlas)` is the one worth using — it is how a variant obtains its master's
content, and there is no equivalent on `SpriteAtlasAsset`. The rest mirror the V1 authoring model
onto the runtime type; they resolve in Editor code and they are not the V2 path.

## SpriteAtlasManager — `UnityEngine.U2D`

Two static events and one static method:

```csharp
static event Action<string, Action<SpriteAtlas>> atlasRequested   // tag, reply
static event Action<SpriteAtlas> atlasRegistered
static SpriteAtlas CreateSpriteAtlas(string name, SpriteAtlasRuntimeConfig config, AtlasPage[] pages)
```

`atlasRequested` hands you a tag and a callback; invoke the callback with the atlas, or the sprites
waiting on that tag never bind. Subscribe before the first sprite is drawn — see the skill's §5.

## ScriptablePacker — `UnityEditor.U2D`

A `ScriptableObject` subclass, so instances are created with
`ScriptableObject.CreateInstance<T>()`.

```csharp
public    abstract bool Pack(SpriteAtlasPackingSettings config,
                             SpriteAtlasTextureSettings setting,
                             PackerData input);
protected virtual  bool Fit (SpriteAtlasPackingSettings config,
                             SpriteAtlasTextureSettings setting,
                             PackerData input);
```

**The two overridables do not share an access modifier** (`Pack` carries `Public`,
`Fit` carries `Family`). C# will not let an override widen access, so `public override bool Fit`
is a compile error and `protected override bool Fit` is the only form that builds — the reverse of
what the symmetry of the two signatures suggests. The type also declares a non-virtual
`public void Dispose(PackerData)`; it is not an override point.

The signature fixes the member and its accessibility, not what the importer does with `Fit`'s
answer. Return the honest arithmetic, and pack one atlas that fails `Fit` to see what `false` does
before a packer depends on it.

**Its data types are nested inside it.** `ScriptablePacker.PackerData`,
`ScriptablePacker.SpriteData`, `ScriptablePacker.SpritePack`, `ScriptablePacker.TextureData` and
`ScriptablePacker.PackTransform`. None of them is a free type in `UnityEditor.U2D`, and
qualifying them as if they were is the usual reason a custom packer fails to resolve.

| Nested type | Fields |
|---|---|
| `PackerData` | `NativeArray<Color32> colorData`, `NativeArray<SpriteData> spriteData`, `NativeArray<TextureData> textureData`, `NativeArray<int> indexData`, `NativeArray<Vector2> vertexData` |
| `SpriteData` | `int guid`, `int texIndex`, `int indexCount`, `int vertexCount`, `int indexOffset`, `int vertexOffset`, `RectInt rect`, `SpritePack output` |
| `SpritePack` | `int x`, `int y`, `int page`, `PackTransform rot` |
| `TextureData` | `int width`, `int height`, `int bufferOffset` |
| `PackTransform` | `None`, `FlipHorizontal`, `FlipVertical`, `Rotate180` |

Two of those rows contradict what the field names suggest:

- **`SpriteData.guid` is an `int`**, not a `GUID`. It is an index-like handle within the pack
  operation, so do not try to map it back to an asset with `AssetDatabase`.
- **`TextureData` has a third field, `bufferOffset`** — where that texture's pixels start inside
  `PackerData.colorData`. Reading `colorData` without it reads the wrong texture.

`NativeArray<T>` returns a copy from its indexer, so `spriteData[i].output.x = …` is a compile
error rather than a silent no-op — but the workaround people write next, copying into a local and
forgetting the write-back, *is* silent. Read the element into a local, set `output`, assign the
local back into the array.
