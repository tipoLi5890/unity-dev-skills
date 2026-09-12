# Late binding: atlases the player downloads

> Run the three checks under **Verifying** after the first content build — the flow is not
> working until all three pass, whatever the Editor reported.

The built-in path is one flag — `includeInBuild = true` and the packed texture ships inside the
player. This file is the other path: `includeInBuild = false`, the atlas delivered through
Addressables, and the three pieces that have to exist together for that to work.

Reach for it when the art is optional, large or updatable — level packs, cosmetics, per-locale UI,
seasonal content. Core UI and anything on the first screen belongs in the build; an async load in
front of the first frame buys nothing and can fail.

## Why three pieces, not one

`includeInBuild = false` is a promise that something else will deliver the atlas. Set it alone and
the build does exactly as told: the atlas is excluded, nothing supplies it, and every sprite that
lived in it resolves to nothing. There is no build error, because from the build's point of view
this configuration is deliberate.

| Piece | Runs | Job |
|---|---|---|
| Prebuild generator | `IPreprocessBuildWithReport` | Author the atlases, set `includeInBuild = false`, create an Addressables entry per atlas |
| Content build | `IPostprocessBuildWithReport` | Build the Addressables content so the entries have bundles behind them |
| Runtime supplier | `MonoBehaviour`, first scene | Answer `SpriteAtlasManager.atlasRequested` by loading the atlas and invoking the callback |

Ready-made versions: `resources/AtlasBuildGenerator.cs`, `resources/AtlasContentBuild.cs` and
`resources/AtlasSupplier.cs`. Drop the first two under an `Editor` folder and the third on an object
in the first scene.

## The Editor API

Enumerate these on your Addressables version by reflection before writing against them:

| Call | Shape |
|---|---|
| `AddressableAssetSettingsDefaultObject.Settings` | static property; **null when Addressables has not been initialised in the project** |
| `settings.DefaultGroup` | property |
| `settings.FindAssetEntry(string guid)` | returns the existing entry, or null |
| `settings.CreateOrMoveEntry(string guid, AddressableAssetGroup targetParent, bool readOnly, bool postEvent)` | four arguments, in that order |
| `settings.SetDirty(AddressableAssetSettings.ModificationEvent.EntryAdded, …)` | `EntryAdded` is a real member of that enum |
| `AddressableAssetSettings.BuildPlayerContent()` | also exists as `BuildPlayerContent(out AddressablesPlayerBuildResult result)` |
| `AddressablesPlayerBuildResult` | carries `Error` and `Duration` |

Everything above lives in `Unity.Addressables.Editor`. On the runtime side,
`UnityEngine.AddressableAssets.Addressables` (assembly `Unity.Addressables`) has both
`LoadAssetAsync` and `Release`.

The null `Settings` case is the one to handle first. Installing the package does not initialise it —
a project has to create the settings asset before any of this resolves at runtime. Fail loudly in
the prebuild step rather than producing a build with unsatisfiable entries.

## Guarding the compile

Every Editor and runtime file that touches Addressables should be wrapped so the project still
compiles without the package:

```csharp
#if UNITY_ADDRESSABLES
    // …
#else
    UnityEngine.Debug.LogError("Addressables is not installed; atlases cannot be late-bound.");
#endif
```

That symbol is not defined for you. Add it as a scripting define, or swap the guard for a version
define on `com.unity.addressables` in the assembly definition. Without either, the guarded branch
is silently the `#else` one and the build looks configured while doing nothing — a second instance
of exactly the failure this whole skill is about.

## Addresses and tags

The runtime is handed a **tag** by `SpriteAtlasManager.atlasRequested`, and it has to turn that into
something Addressables can load. The simplest rule that holds: make the address equal the atlas
file's name without its extension, and let the tag match it. Then the supplier is a lookup with no
mapping table:

```csharp
var handle = Addressables.LoadAssetAsync<SpriteAtlas>(tag);
```

Any other scheme needs a mapping the runtime can reach, which means one more asset to keep in sync.
Prefer the naming rule and enforce it in the prebuild step, where a mismatch is a build-time error
rather than a blank sprite in the shipped game.

## The runtime contract

- **Subscribe in `Awake`, on an object that survives scene loads.** `atlasRequested` fires when a
  sprite first needs its atlas. A supplier that subscribes in `Start`, or that is instantiated by
  the second scene, misses requests the first scene already made, and those sprites stay unbound
  for the rest of the session.
- **Always invoke the callback.** Including on failure — pass null rather than returning without
  calling it. The request is not retried.
- **Cache the handle per tag.** A second request for a tag already loading should reuse the handle,
  not start another load.
- **Release in `OnDestroy`,** and unsubscribe from both events there. A supplier that unsubscribes
  but keeps its handles leaks the atlas textures for the process lifetime.
- **Async means a frame or more with no sprite.** Anything on screen during that window needs a
  placeholder or a gate; a UI that pops in is the cost of this delivery mode, not a bug in it.

## Verifying

Building the content and building the player are separate operations, and a stale content build is
the quiet failure here. After a build, check three things rather than one:

1. The atlas assets exist and their importers read back `includeInBuild == false`.
2. Each atlas has an Addressables entry whose address is what the runtime will ask for.
3. The content build wrote bundles **after** the atlases were regenerated — compare timestamps, not
   the presence of the folder.
