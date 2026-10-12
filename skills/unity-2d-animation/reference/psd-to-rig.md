# PSB to rig — the import, and what a re-import keeps

> Part of the `unity-2d-animation` skill. The bones, the mesh and the weights are not in the PSB.
> They are in its `.meta`, keyed to each layer's sprite id. The artist owns one file, the rigger
> the other, and every re-import joins them again by layer — so the rule that decides whether a
> rig survives an art revision is the rule for what counts as "the same layer".

## 1. The source file

| Rule | Because |
|---|---|
| Save as **`.psb`**, not `.psd` | The PSD Importer takes `.psb` by default. A `.psd` goes to the ordinary texture importer and arrives as one flat image (§6 overrides that) |
| One layer per part that moves on its own | A layer becomes a sprite, a renderer and a `SpriteSkin`. Twelve to sixteen for a humanoid runner |
| Every layer name unique | Names become sprite names and, under name mapping, identities. *Keep Duplicate Names* (on by default) lets two sprites share a name; off, the importer renames the later one. Either way name mapping cannot tell them apart |
| Neutral pose, limbs apart, slightly bent | The pose is the bind pose. Auto weights bleed across parts that touch, and a straight limb hides which way it bends |
| Overlap at the joints | Draw the upper arm past the elbow under the forearm. The overlap is what stops a gap opening when the joint bends |
| Groups for variants, not for structure | A group can be merged into one sprite on import, or kept as a GameObject (§2) |
| Hidden layers are not imported | Unless *Include Hidden Layers* is on. A layer the artist hid before saving is a part that vanishes on re-import |
| Same canvas size and placement for every variant of a character | Skeleton sharing (§5) places the same bones over each file by document position |

Photoshop is the reference producer of `.psb`. For any other painting tool, export twice
without touching the layers and run the stability check in §4 before building on it.

**Aseprite is not this.** `com.unity.2d.aseprite` imports `.ase` and `.aseprite` as frame
animation — sprites, clips and a controller from tags. It makes no skeleton. Those files, and
every other sheet of frames, are `unity-2d-sprites` → `reference/sprite-animation.md`.

## 2. The importer settings

Select the `.psb`; the Inspector is the PSD Importer.

| Setting | Value for a rig | Notes |
|---|---|---|
| Texture Type | Sprite (2D and UI) | |
| Sprite Mode | Multiple | *Single* treats the file as one sprite |
| Pixels Per Unit | art height in pixels ÷ height in world units | A runner drawn 512 px tall that stands 1.8 units: 284 |
| Mesh Type | Tight | Overridden per sprite by geometry made in the Skinning Editor |
| Import Mode | Individual Sprites (Mosaic) | The default. Each layer is cropped and packed into one texture. *Merged* flattens the file |
| Mosaic Padding | 4 | Pixels between parts in the texture. Raise it when mipmaps or bilinear filtering bleed one part into another |
| Sprite Padding | 0 | Grows each sprite's rect; room for geometry that extends past the pixels |
| Use as Rig | on | Generates the prefab and enables the Skinning Editor's character view. Needs Mosaic and Multiple |
| Use Layer Group | off, unless the groups are structure worth animating | On: each Photoshop group becomes a GameObject between the root and the parts |
| Pivot | Bottom Center | The prefab root's origin: the feet, for anything that stands on ground |
| Main Skeleton | empty for the first file | §5 |
| Layer Mapping | *Use Layer ID* (default) or *Use Layer Name* | §4 — decide once, with the artist |
| Include Hidden Layers | off | |
| Automatic Reslice | off | On: every re-import regenerates the sprite rects from the layers and drops hand edits to them. Bones and weights survive while the regenerated rect is still valid for them |

The Layer Management tab lists the file's layers and groups. A checkbox per row imports or
skips it; the icon on a group **merges** the group into one sprite, which is how a part painted
on five layers becomes one renderer instead of five.

What a script can read and set through `UnityEditor.U2D.PSD.PSDImporter` (assembly
`Unity.2D.Psdimporter.Editor`): `useMosaicMode`, `useCharacterMode`, `mosiacPadding` (spelt that
way), `spriteSizeExpand`, `spritePixelsPerUnit`, `spriteImportMode`, `spriteMeshType`,
`filterMode` and the platform settings. A read-only line for a report:

```csharp
var imp = (UnityEditor.U2D.PSD.PSDImporter)UnityEditor.AssetImporter.GetAtPath(path);
return $"mosaic={imp.useMosaicMode} rig={imp.useCharacterMode} mode={imp.spriteImportMode} ppu={imp.spritePixelsPerUnit}";
```

Layer mapping, layer groups, hidden layers and the main skeleton have no public property. Set
them in the Inspector and read them from the `.meta`:

```bash
grep -n 'm_LayerMappingOption\|m_GenerateGOHierarchy\|m_ImportHiddenLayers\|m_SkeletonAssetReferenceID' Assets/Art/Runner/Runner.psb.meta
# m_LayerMappingOption: 0 name · 1 name, case sensitive · 2 layer id
```

## 3. What the import produces

One asset with sub-assets: the mosaic texture, a sprite per layer, a skeleton asset named
`<file> Skeleton`, and a prefab.

```
Runner_GO                     the prefab root: also every SpriteSkin's Root Bone
├─ torso                      SpriteRenderer (order in layer = layers − index), SpriteSkin
├─ arm_upper_l                …one object per imported layer, named after the layer
├─ helmet                     no bones assigned → SpriteRenderer only
└─ bone_1                     the skeleton, as plain Transforms
   └─ bone_2 …
```

- **Order in Layer follows the layer stack**: the top layer gets the highest number. Reordering
  layers in the source reorders the character on the next import. Anything further — a Sorting
  Group on the root so two characters do not interleave, a limb that passes behind the torso
  mid-clip — is `unity-2d-rendering` → `reference/sort-order.md`.
- **A part has a `SpriteSkin` only when bones are assigned to its sprite.** A fresh import has
  none; they appear after the first Skinning Editor *Apply*. A part with no bones stays where
  the import put it, under the root, and does not follow the skeleton.
- **Auto Rebind is off on every generated `SpriteSkin`.** Parts that will be swapped need it on
  (`reference/sprite-library.md` §4).
- **The prefab is generated, so it is read-only.** Do not unpack it. Make a **Prefab Variant**
  and put the Animator, `SkinSwap`, `IKManager2D`, colliders and overrides such as Auto Rebind
  there; re-imports then flow through to it. An unpacked copy never sees the next art revision.

## 4. Re-import stability

On every import the importer matches each layer in the file to a layer it has seen, using the
Layer Mapping rule. A match keeps the sprite's id, and everything keyed to that id — bones
assigned, geometry, weights, library label — stays attached. No match makes a new sprite with a
new id and nothing attached.

| The artist… | Use Layer ID | Use Layer Name |
|---|---|---|
| repaints a layer in place | kept | kept |
| renames a layer | kept | **new sprite: the rig comes off that part** |
| deletes a layer and paints it again | **new sprite** | kept, if the name is the same |
| duplicates a layer and deletes the original | **new sprite** | kept, if the copy takes the old name |
| gives two layers the same name | fine | mismapped: an error lists the duplicated identifiers |
| reorders layers | kept; order in layer changes | the same |
| adds a layer | new sprite, no bones | the same |
| hides a layer before saving | the part disappears from the prefab | the same |

Layer ID suits one artist working in one long-lived file. Layer Name suits a pipeline where
files are regenerated or assembled from pieces, as long as names are treated as frozen. Changing
the mapping mode on a rigged file re-matches every layer under the new rule: do it on a commit
of its own and run the check below straight after.

Three things a match does not protect:

- **Repainted pixels outside the old mesh.** Geometry is stored, not regenerated. A sleeve
  painted wider than before is cut off by the old outline, or sits offset inside it, until that
  sprite's geometry is regenerated and re-weighted. After an art drop, open the Skinning Editor
  and look at each changed part's outline against its pixels.
- **Clip bindings.** Clips address bones and parts by hierarchy path from the Animator. A bone
  renamed in the Skinning Editor, a layer renamed under name-keyed objects, or *Use Layer Group*
  toggled all change paths, and the affected curves go missing (yellow in the Animation
  window) without an error at runtime.
- **The `.meta`.** Delete or regenerate it and the whole rig is gone; it is not in the PSB.
  Commit the `.psb` and its `.meta` together, always.

**The check, before and after every art drop:**

```bash
unity command eval 'return SkinningAudit.Json("Assets/Art/Runner");' > before.json   # before replacing the file
unity command eval 'return SkinningAudit.Json("Assets/Art/Runner");' > after.json    # after the re-import
```

`riggedSprites` must not fall, `bonelessSpritesInRiggedAssets` must not gain a name, and every
skin's `state` must still be `Ready`. A part that came off shows up in all three.

## 5. One skeleton, several files

Each rigged PSB owns a skeleton asset. Assigning one file's skeleton to another file's **Main
Skeleton** makes the second use the first's bones:

- every clip authored on the first plays on the second;
- sprites from both carry the same bone names, so swapping one for the other through a library
  rebinds cleanly;
- the Bone tools are locked in the second file's Skinning Editor — bones are edited in the file
  that owns the skeleton, and the change reaches every file that references it. Geometry and
  weights stay per file.

The courier and night-courier skins, or three sentry ranks, are separate PSBs on one skeleton.
Draw each on the same canvas with the body in the same place; the bones are laid over the
document, not over each layer.

## 6. A `.psd` through the PSD Importer

Select the file and choose `UnityEditor.U2D.PSD.PSDImporter` in the Inspector's importer
dropdown, or from script:

```csharp
UnityEditor.AssetDatabase.SetImporterOverride<UnityEditor.U2D.PSD.PSDImporter>(path);
// UnityEditor.AssetDatabase.ClearImporterOverride(path) puts the texture importer back
```

An override is per file and lives in that file's `.meta`. Prefer renaming the source to `.psb`
when the artist can.

## 7. The rig from script

A rigged PSB answers the sprite data providers every sprite importer answers —
`ISpriteBoneDataProvider` and `ISpriteMeshDataProvider` per sprite id among them; the table and
the capability gate are `unity-2d-sprites` → `reference/data-provider.md`. The 2D Animation
package adds the character-level ones, in `UnityEditor.U2D.Animation` (assembly
`Unity.2D.Animation.Editor`), reached through the same `GetDataProvider<T>()`. The PSD Importer implements the provider
interface explicitly, so go through the factory, not through a `PSDImporter` variable:

| Provider | Members | What it holds |
|---|---|---|
| `ICharacterDataProvider` | `GetCharacterData()` / `SetCharacterData(CharacterData)` | The whole rig. `CharacterData.bones` is the skeleton as `SpriteBone[]`; `parts` is one `CharacterPart` per sprite — `spriteId`, `spritePosition` in the document, and `bones`, indices into the skeleton; `characterGroups` are the layer groups; `dimension` and `pivot` describe the document |
| `IMainSkeletonDataProvider` | `GetMainSkeletonData()` → `MainSkeletonData.bones` | The shared skeleton. The provider is `null` unless a Main Skeleton is assigned (§5), which makes it the test for "this file borrows its bones" |
| `ISpriteLibDataProvider` | marked obsolete | Nothing to use: libraries are `.spriteLib` assets now (`reference/sprite-library.md`) |

Reading is safe and is the quickest way to list which part is bound to which bones:

```csharp
var factory = new UnityEditor.U2D.Sprites.SpriteDataProviderFactories();
factory.Init();
var dp = factory.GetSpriteEditorDataProviderFromObject(UnityEditor.AssetImporter.GetAtPath(path));
if (dp == null) return "not a sprite asset";
dp.InitSpriteEditorDataProvider();
var provider = dp.GetDataProvider<UnityEditor.U2D.Animation.ICharacterDataProvider>();
if (provider == null) return "not imported as a rig";
UnityEditor.U2D.Animation.CharacterData data = provider.GetCharacterData();
var names = new System.Collections.Generic.Dictionary<string, string>();
foreach (UnityEditor.SpriteRect r in dp.GetSpriteRects()) names[r.spriteID.ToString()] = r.name;

var sb = new System.Text.StringBuilder();
foreach (UnityEditor.U2D.Animation.CharacterPart part in data.parts)
{
    names.TryGetValue(part.spriteId, out string sprite);
    sb.Append(sprite ?? part.spriteId).Append(": ");
    if (part.bones != null)
        foreach (int b in part.bones) sb.Append(data.bones[b].name).Append(' ');
    sb.AppendLine();
}
return sb.ToString();
```

Writing is a different matter. `SetCharacterData` replaces bones and bindings for every part at
once, and weights and geometry sit in the per-sprite providers keyed to the same bone indices:
change one side alone and the weights name bones that moved. Rig in the Skinning Editor; use
the providers to read, to audit, and to copy a finished rig between files that share a layout.
A write follows the same rule as any importer edit — report first, then `Apply()` and
`SaveAndReimport()`.

## Checks

- The `.psb` and its `.meta` are both tracked, and committed together.
- `grep -n 'm_LayerMappingOption' <file>.psb.meta` matches the rule written in the brief.
- The game uses a Prefab Variant of the generated prefab, never an unpacked copy. The variant
  names the PSB as its source, so this prints its path:

```bash
guid=$(grep -m1 '^guid:' Assets/Art/Runner/Runner.psb.meta | cut -d' ' -f2)
grep -rl "m_SourcePrefab: {fileID: [0-9-]*, guid: $guid" Assets --include='*.prefab'
```

- After a re-import, the audit comparison in §4 holds and the Animation window shows no yellow
  curve on the character's clips.
