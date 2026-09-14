# The data-provider API — where the types live, the gate, and re-slicing

> Part of the `unity-2d-sprites` skill. `SKILL.md` §2 and §3 state the rules. This file holds the
> type table, the gate in full, the three ways to fold new rects into old ones, and what each
> runnable script adds over the grid slicer.

## 1. Where the types live

The namespaces are not where you would guess, and a wrong guess is a compile error, so use this
table rather than reasoning about it:

| Type | Fully qualified |
|---|---|
| `SpriteDataProviderFactories`, `ISpriteEditorDataProvider`, `ISpriteFrameEditCapability`, `EEditCapability`, `EditCapability`, `ITextureDataProvider`, `ISpriteNameFileIdDataProvider`, `ISpriteOutlineDataProvider` | `UnityEditor.U2D.Sprites.*` |
| `SpriteRect` | **`UnityEditor.SpriteRect`** — not under `U2D.Sprites` |
| `SpriteNameFileIdPair` | **`UnityEditor.SpriteNameFileIdPair`** — not under `U2D.Sprites` |
| `GUID` (the type of `SpriteRect.spriteID`) | **`UnityEngine.GUID`** — qualify it: other packages reference a `UnityEditor.GUID`, so a bare `GUID` resolves by whichever namespaces the file imports |

On a project without `com.unity.2d.sprite` — a URP 3D project, say — every one of
`SpriteDataProviderFactories`, `ISpriteEditorDataProvider`, `ISpriteFrameEditCapability`,
`EEditCapability`, `ITextureDataProvider`, `ISpriteNameFileIdDataProvider` and `SpriteRect`
resolves to nothing. With the package installed they all live in the **`Unity.2D.Sprite.Editor`**
assembly — the name an asmdef has to reference (`reference/import-pipeline.md` §1).

### Everything else `GetDataProvider<T>()` hands back

The rects are one provider among several on the same object. `GetDataProvider<T>()` returns
`null` where the importer does not offer that kind of data, so null-check every one of them
rather than assuming a PNG behaves like a PSB. `HasDataProvider(System.Type)` asks the same
question without materialising anything, which is the cheap way to write a report line about an
asset you are not going to edit.

| Provider | Members | What it holds |
|---|---|---|
| `ISpriteOutlineDataProvider` | `GetOutlines(GUID)` / `SetOutlines(GUID, List<Vector2[]>)`, `GetTessellationDetail(GUID)` / `SetTessellationDetail(GUID, float)` | The **render** outline — the mesh the sprite draws with, which is where overdraw is trimmed |
| `ISpritePhysicsOutlineDataProvider` | the same four, per sprite GUID | The **collider** outline, read by `PolygonCollider2D` |
| `ISpriteMeshDataProvider` | `GetVertices(GUID)` → `Vertex2DMetaData[]`, `GetIndices(GUID)` → `int[]`, `GetEdges(GUID)` → `Vector2Int[]`, plus `SetVertices` / `SetIndices` / `SetEdges` | A custom sprite mesh, vertices and triangles rather than a closed outline |
| `ISecondaryTextureDataProvider` | `textures`, a `SecondarySpriteTexture[]` property, get and set | The extra maps a Sprite-Lit material samples — a normal map or a mask packed alongside the albedo |
| `ITextureDataProvider` | `texture`, `previewTexture`, `GetReadableTexture2D()`, `GetTextureActualWidthAndHeight(out int, out int)` | The pixels. `previewTexture` is what the Sprite Editor draws, `GetReadableTexture2D()` is the one to sample from, and the two sizes differ once Max Size applies |
| `ISpriteBoneDataProvider` | `GetBones(GUID)` / `SetBones(GUID, List<SpriteBone>)` | 2D skeletal rigging. `SKILL.md`'s Scope says why nothing here drives it |

**Tessellation detail is a `0`–`1` value on both outline providers, and the right number is not
the same on each.** Finer is more triangles: worth it on a render outline that trims a lot of
transparent area, wasteful on a physics outline, where it buys an expensive `PolygonCollider2D`
and no gameplay. Coarse is correct there. The two are separate providers precisely because one
answer does not serve both.

**`SpriteRect.spriteID` is the runtime `Sprite.GetSpriteID()`.** That is the join between
importer-side configuration and a sprite the game holds at runtime, and it is why §3 guards the id
so carefully: change it and the join breaks everywhere at once, silently.

`RegisterDataChangeCallback(Action<ISpriteEditorDataProvider>)` and its `Unregister` twin exist for
an Editor window that has to react while a human edits. A one-shot script does not want them —
register in a script that then finishes, and the callback outlives the work it was for.

## 2. The capability gate, member by member

Both gates in order — the null provider, then the capability — and the write that makes it real:

```csharp
var importer = UnityEditor.AssetImporter.GetAtPath(assetPath);
var factory  = new UnityEditor.U2D.Sprites.SpriteDataProviderFactories();
factory.Init();
var dp = factory.GetSpriteEditorDataProviderFromObject(importer);
if (dp == null)
    throw new System.Exception($"{assetPath} has no sprite data provider — not a sprite asset.");
dp.InitSpriteEditorDataProvider();

var cap = dp.GetDataProvider<UnityEditor.U2D.Sprites.ISpriteFrameEditCapability>();
if (cap == null)
    throw new System.Exception("Importer exposes no edit capability — aborting.");
if (!cap.GetEditCapability().HasCapability(
        UnityEditor.U2D.Sprites.EEditCapability.CreateAndDeleteSprite))
    throw new System.Exception("Importer cannot add/remove sprites — aborting.");

var rects = dp.GetSpriteRects();
// … modify rects …
dp.SetSpriteRects(rects);
dp.Apply();
importer.SaveAndReimport();          // nothing persists without this
```

Verifying afterwards is the same call in reverse: reopen the provider on a fresh
`SpriteDataProviderFactories` and read the rects back, or look at the Project window. `Apply()`
followed by `SaveAndReimport()` is where an edit becomes real — the in-memory change evaporates
without the reimport, and the count that settles it is `SKILL.md` §6's.

`EEditCapability`, enumerated from the assembly rather than recalled:
`None, EditSpriteName, EditSpriteRect, EditBorder, EditPivot, CreateAndDeleteSprite,
SliceOnImport, All`.

| Capability | Needed for |
|---|---|
| `EditSpriteName` | Renaming |
| `EditSpriteRect` | Moving or resizing frames |
| `EditBorder` | 9-slice borders |
| `EditPivot` | Pivots |
| `CreateAndDeleteSprite` | Adding, removing, any slicing |
| `SliceOnImport` | Slicing applied by the importer itself |

`GetEditCapability()` returns a `UnityEditor.U2D.Sprites.EditCapability` struct, and
`HasCapability(EEditCapability)` is the method on it.

> **Do not rationalise past a failed check** because the API "looks like it would work". The
> check is the importer's contract, and the failure it prevents is silent data loss that shows
> up later as sprites with impossible rects.

## 3. Re-slicing without losing identity

A tool that runs over the whole art folder will hit sheets it has already cut, and a fresh
`SpriteRect` with a fresh `GUID.Generate()` for a name that already exists throws away the
identity everything serialised against. On a re-run, look the name up in the rects the provider
hands back and reuse that object — replace only its `rect` (and pivot and border) — generating an
ID only for names that are genuinely new:

```csharp
var existing = new System.Collections.Generic.Dictionary<string, UnityEditor.SpriteRect>();
foreach (var r in dp.GetSpriteRects()) existing[r.name] = r;   // before you clear anything
// per frame:
var rect = existing.TryGetValue(name, out var kept)
    ? kept                                                     // keeps spriteID: references survive
    : new UnityEditor.SpriteRect { name = name, spriteID = UnityEngine.GUID.Generate() };
```

Then write `SetNameFileIdPairs` for the whole list. On Unity 2021.2+ adding or removing sprites also
requires updating the name↔fileID map via `ISpriteNameFileIdDataProvider` (`GetNameFileIdPairs` /
`SetNameFileIdPairs`). Skip it and existing references silently rebind to the wrong sprite — the
sheet looks fine and every prefab using it is now wrong.

**Name-keyed reuse is one of three ways to fold new rects into old ones, and it is the only one
that needs the names to be stable.** When they are not — a generated tileset, a sheet whose frame
count changed — the choice is geometric, and there are exactly three modes worth implementing:
**replace all** (drop every old rect; every sprite gets a fresh `GUID`, which is the rebinding
failure above, so use it only on art nothing references yet), **update overlapping and add new**
(an existing rect that overlaps a new cell is moved onto it with its `spriteID` intact, cells that
hit nothing become new rects, and an old rect nothing lands on is dropped — the geometric
equivalent of the name lookup above), and **add only non-overlapping** (every existing rect is
left exactly as it is and only cells that touch nothing are added — the mode for a sheet someone
has hand-tuned in the Sprite Editor).

Two rules keep those modes honest, and both are easy to write the wrong way round:

- **Each existing rect may be claimed by one new cell only.** Mark the ones already moved and skip
  them on the next lookup. Without that, two cells that both overlap one old rect emit the same
  `SpriteRect` object twice — same name after the second rename, same `spriteID` — and
  `SetNameFileIdPairs` writes a duplicated pair for it.
- **Write pivot, alignment and outlines to the rects the run created or moved, not to the whole
  list.** `UnityEditor.SpriteRect` is a class, not a struct, so a loop over every rect reaches into
  the objects the provider handed you and overwrites exactly the hand-tuned pivots the preserve
  mode exists to keep. Collect the touched subset while merging.

Overlap needs a tolerance, and it is two separate numbers. An **area floor** (around `1e-5`)
below which a candidate is not a cell at all, so a degenerate rect never claims an existing
sprite; and, if you pick among several overlapping rects by best fit rather than taking the first,
a **ratio ceiling** that rejects a match which merely grazes the candidate. Taking the first
overlap is cheaper and adequate for a grid, but note that it is **order-dependent as soon as the
cells themselves overlap** — isometric rows do, by half a cell height — so say which mode a run
used in its report rather than leaving it implied.

## 4. What each runnable script adds

- `resources/SliceSheet.cs` — the grid slicer; it ends on `SKILL.md` §6's acceptance test and
  throws when the sprite count differs from the rects written.
- `resources/IsometricSliceSheet.cs` — the diamond walk: rows stepping half a cell and
  alternating a half-cell shift, alpha-sampled inside the diamond so empty cells are dropped
  rather than published, the three rect modes of §3, and a diamond render outline per tile
  through `ISpriteOutlineDataProvider`. Its signature is
  `SetOutlines(UnityEngine.GUID, List<Vector2[]>)`, and `ITextureDataProvider` does expose
  `GetTextureActualWidthAndHeight(out int, out int)` — both read off the assembly. **Slice
  against the source image's dimensions**, which that call gives you: a Max Size of 2048 on a
  4096 sheet halves every coordinate the importer reports, and the cells come out at half the
  size the artist authored.
- `resources/AutomaticSliceSheet.cs` — the same two gates, with the Sprite Editor's own rect
  generators doing the cutting: `UnityEditorInternal.InternalSpriteUtility`'s
  `GenerateAutomaticSpriteRectangles(Texture2D, int minRectSize, int extrudeSize)` for islands of
  opaque pixels, and `GenerateGridSpriteRectangles(Texture2D, Vector2 offset, Vector2 size,
  Vector2 padding, bool keepEmptyRects)` for the padded, offset grid the arithmetic in
  `SliceSheet.cs` does not cover. Both return `Rect[]` in the space of the texture handed to them,
  so it generates against the source-size copy. **`UnityEditorInternal` is not documented scripting
  API** — the file opens with a reflection check to confirm the type and both methods on your
  version, and the fallback is `SliceSheet.cs`; island detection has no substitute worth
  approximating. Detected frames arrive in no promised order, so it sorts them into reading order
  with a row tolerance **before** naming: names are the sheet's API surface (`SKILL.md` §3), and
  naming in the generator's order renames the whole sheet on the next run.
- `resources/SpriteToPng.cs` — one sprite's own pixels as PNG bytes. `GetPixels` on
  `sprite.texture` returns the whole page, so the sprite's triangles are drawn into a temporary
  `RenderTexture` the size of its `textureRect` first.
- `resources/SheetToAnimationClip.cs` — a folder of frame PNGs or one sliced sheet into a clip,
  plus an optional one-state controller (`reference/sprite-animation.md`).

`IsometricSliceSheet.cs` and `AutomaticSliceSheet.cs` compile against the Editor assemblies plus
`Unity.2D.Sprite.Editor`, and
`SheetToAnimationClip.cs` against the Editor assemblies alone. `SpriteToPng.cs` uses only
`UnityEngine` types and needs no sprite-package reference, though `Shader.Find("UI/Default")` keeps
it an Editor-side tool. A compile is not a slice: treat `SKILL.md` §6's acceptance test as the bar
the first time each runs on real art, and for a clip the four reads in
`reference/sprite-animation.md` §7.
