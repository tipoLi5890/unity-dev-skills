# Delivery, variants and custom packing

Moved out of SKILL.md, which keeps §1–§4 (packing on, the two APIs, configure and reimport, generate on build); numbering continues it.

## 5. Delivery: inside the player, or late-bound

One importer flag decides this; the rest follows from it.

| Content | `includeInBuild` | What else is needed |
|---|---|---|
| Core UI, the first scene, anything always on screen | `true` | Nothing |
| Level packs, cosmetics, per-locale art, seasonal content | `false` | Addressables entries, a content build, and a runtime supplier |

Setting `includeInBuild = false` without the other three pieces — a prebuild step creating the
Addressables entries, a postprocess step building the content, and a runtime component answering
`SpriteAtlasManager.atlasRequested` — produces a build whose sprites resolve to nothing: the atlas
is excluded exactly as asked and nobody delivers it. Setup and the Addressables API surface:
`reference/addressables-delivery.md`.

> **The supplier has to be listening before the first sprite resolves.** `atlasRequested` fires
> once per tag, so a component that subscribes in `Start`, or lives in the second scene, leaves the
> first scene's sprites blank for the session. Subscribe in `Awake` on an object that survives the
> load, and unsubscribe in `OnDestroy`.

## 6. Variants

A variant is a second atlas reusing a master's packables at another scale — usually a
reduced-resolution build from the same source art.

```csharp
var master = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.U2D.SpriteAtlas>(masterPath);
var variant = new UnityEditor.U2D.SpriteAtlasAsset();
variant.SetIsVariant(true);
variant.Add(UnityEditor.U2D.SpriteAtlasExtensions.GetPackables(master));  // §2's extension
variant.SetMasterAtlas(master);           // takes the runtime SpriteAtlas
UnityEditor.U2D.SpriteAtlasAsset.Save(variant, variantPath);
UnityEditor.AssetDatabase.ImportAsset(variantPath);

var importer = UnityEditor.AssetImporter.GetAtPath(variantPath)
             as UnityEditor.U2D.SpriteAtlasImporter;
importer.variantScale   = 0.5f;           // on the importer, not the asset
importer.includeInBuild = true;
importer.SaveAndReimport();
```

Two signatures decide whether this compiles: `SetMasterAtlas` takes a
**`UnityEngine.U2D.SpriteAtlas`**, so a path string or a `SpriteAtlasAsset` is rejected; and there
is **no `SetMasterAtlasPath`** to fall back on. Scale lives on the importer because
`SpriteAtlasAsset.SetVariantScale` is one of the nine methods carrying `[Obsolete]`.

Add the master's packables, not sprites you collected earlier: a variant listing a different set
from its master is not a variant of it, and the mismatch shows up as missing sprites, not an error.

## 7. Custom packing

`ScriptablePacker` is a `ScriptableObject` with one abstract member, `Pack` (**public**), and one
virtual member, `Fit` (**protected** — an override cannot widen access, so `public override bool
Fit` will not compile). Attach an instance with `SpriteAtlasAsset.SetScriptablePacker`, which takes
a `ScriptablePacker`, not a plain `Object`.

Its input and output types are **nested inside `ScriptablePacker`** — `PackerData`, `SpriteData`,
`SpritePack`, `TextureData` and `PackTransform` are all `ScriptablePacker.<Name>`, not free types
in `UnityEditor.U2D`; a mis-qualified reference is the usual reason a packer will not compile.
Field lists, two of them easy to get wrong from memory: `reference/v2-api.md`.

Write to `sprite.output` and write the struct back into the array — `NativeArray<T>` hands out
copies. Never dispose the arrays inside `PackerData`; the importer owns them.

> **`Pack` returning `true` is the only report anyone downstream gets**, so check the output before
> returning it: `resources/PackerValidation.cs` rejects a negative position, an unopened page and
> an overlap, and says what landed on each page.

Three layouts: `resources/GridAtlasPacker.cs` (a fixed grid),
`resources/MultiPagePacker.cs` (shelves, spilling onto a new page) and
`resources/SizeOptimizedPacker.cs` (one page, tallest first). Padding is yours to apply — whatever
`Pack` writes is the final position.
