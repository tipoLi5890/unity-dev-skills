# Sprite Library — a part shows a name, not a sprite

> Part of the `unity-2d-animation` skill. A `SpriteResolver` does not hold a sprite. It holds one
> integer, a hash of `category_label`, and asks the nearest `SpriteLibrary` what that means
> right now. Swap the library and every part changes without a clip or a prefab being touched —
> and rename a label and every clip that keyed it goes on running, changing nothing.

## 1. The three pieces

| Piece | Is | Lives |
|---|---|---|
| Sprite Library Asset (`.spriteLib`) | a table: category → label → sprite | in the project |
| `SpriteLibrary` | "this character uses that table", plus per-instance overrides | on the character root |
| `SpriteResolver` | "this part shows `helmet` / `courier`" | on each swappable part, beside its `SpriteRenderer` |

A resolver uses the first `SpriteLibrary` found on itself or its ancestors, inactive ones
included. Two libraries in one hierarchy is legal: the resolvers under the nearer one use it.
The resolver writes `SpriteRenderer.sprite`; nothing else about the renderer changes.

All three types are in `UnityEngine.U2D.Animation`. Resolvers run in `LateUpdate` at execution
order −20, before IK (−10) and before `SpriteSkin` (+10), so a sprite swapped this frame is
deformed this frame.

## 2. Names are ids

Courier-run layout — the category is the slot, the label is what is in it:

| Category | Labels |
|---|---|
| `helmet` | `courier`, `night`, `depot`, `none` |
| `torso` | `courier`, `night` |
| `hand` | `open`, `fist`, `point` |
| `visor` | `up`, `down` |

- **The key is the hash of the two names joined by an underscore.** `hand` + `l_open` and
  `hand_l` + `open` are the same key. Keep underscores out of one side — categories, by
  convention — or two entries answer to one hash.
- **Renaming a category or a label changes the key.** Clips and prefabs keep the old integer.
  The resolver looks it up, finds no entry, and leaves the renderer showing whatever it showed
  last. No warning. Treat names as frozen once a clip keys them, the way a serialised field name
  is frozen.
- **A label with no sprite is a valid entry, and it hides the part.** That is how `helmet` /
  `none` takes the helmet off. An unknown key does nothing; an empty label clears the sprite.
- **Every skin uses the same categories and labels.** A whole-skin swap works because
  `torso` / `courier` exists in both libraries and points at different sprites.

## 3. Building the asset

By hand: *Window → 2D → Sprite Library Editor*, or *Assets → Create → 2D → Sprite Library
Asset*, then drag sprites into the Categories column.

From a convention, with `resources/Editor/SpriteLibraryBuilder.cs`:

| Source | Convention | Command |
|---|---|---|
| A folder | `Parts/helmet/courier.png` → `helmet` / `courier`. A sheet with several sprites gives one label per sprite | *Tools → Unity Dev → 2D Animation → Build Sprite Library From Folder* |
| Sprites, or a PSB | sprite name `helmet_courier`, split at the first underscore | *… → Build Sprite Library From Sprites* |

Both print a plan and wait: the path, each category with its labels, and — when overwriting —
**the labels that would disappear**, which are exactly the keys §2 warns about. From an eval:

```csharp
var problems = new System.Collections.Generic.List<string>();
var entries  = SpriteLibraryBuilder.CollectFromFolder("Assets/Art/Runner/Parts", problems);
return SpriteLibraryBuilder.Plan(entries, problems, "Assets/Art/Runner/Runner.spriteLib", null);
// after the plan is read and agreed:
// SpriteLibraryBuilder.Build(entries, "Assets/Art/Runner/Runner.spriteLib", null);
```

The builder goes through `SpriteLibrarySourceAssetFactory.Create`, the package's public entry
point, so the result is an ordinary `.spriteLib` the Sprite Library Editor opens. Overwriting
keeps the asset's GUID: components that reference the library keep their reference.

Then, on the character's Prefab Variant: a `SpriteLibrary` on the root with the asset assigned,
and a `SpriteResolver` on each swappable part with its category and label picked. Adding a
resolver to a part whose sprite is already in the library selects that entry by itself.

## 4. Swapping at runtime

| Want | Call | Refreshes the parts |
|---|---|---|
| Another whole skin | `spriteLibrary.spriteLibraryAsset = nightLibrary;` | yes |
| One label → one sprite | `spriteLibrary.AddOverride(sprite, "helmet", "courier");` | yes |
| A whole category from another library | `spriteLibrary.AddOverride(depotLibrary, "helmet");` | **no** |
| One label from another library | `spriteLibrary.AddOverride(depotLibrary, "helmet", "courier");` | **no** |
| Undo an override | `spriteLibrary.RemoveOverride("helmet");` or `RemoveOverride("helmet", "courier")` | yes |
| A part shows another label | `resolver.SetCategoryAndLabel("visor", "down");` — returns false when there is no such entry | that part |
| Ask | `spriteLibrary.GetSprite(category, label)`, `HasOverride(category, label)`, `resolver.GetCategory()`, `resolver.GetLabel()` | — |

After either of the two overloads that take a library asset, call
`spriteLibrary.RefreshSpriteResolvers()`. Without it the data has changed and the character has
not, until something else happens to refresh it — which is why the bug comes and goes.
`RefreshSpriteResolvers()` reaches active children only; an inactive part resolves when it is
enabled.

An override is per instance and sits on top of whatever asset is assigned, so equipment survives
a skin swap. `resources/SkinSwap.cs` wraps the table:

```csharp
var swap = runner.GetComponent<SkinSwap>();
swap.SetLibrary(nightLibrary);              // a skin
swap.Equip(depotLibrary, "helmet");         // equipment: overrides the category, then refreshes
swap.Unequip("helmet");
swap.Show("visor", "down");                 // every part currently showing a visor label
```

A library asset references its sprites, and they reference their texture. Four libraries on a
serialised field are four mosaics in memory from the moment the object loads. For a wardrobe
larger than a handful, load the library asset on demand and assign it when it arrives.

### Swapping a rigged part

A sprite with bones needs a `SpriteSkin` whose Transform array fits it. Two ways to get that:

- **Same skeleton, same bone order.** Sprites from PSBs that share a skeleton
  (`reference/psd-to-rig.md` §5), each given the same Bone Influence list. The array fits both.
  The audit cannot see bone order, so it reports `swap-without-rebind` for these parts all the
  same; on this route the proof is every skin's `state` staying `Ready` after each swap, and
  the simpler course is to turn Auto Rebind on anyway.
- **Auto Rebind on.** The skin re-resolves by bone name after every sprite change
  (`reference/bones-and-weights.md` §6). The importer leaves it off; turn it on in the Prefab
  Variant for every part that carries both a resolver and a skin.

Neither in place, the new sprite is deformed by the old sprite's bone list: wrong bones, or a
part frozen in its bind pose. The audit flags it as `swap-without-rebind`, and
`SkinSwap.CheckBindings()` lists the parts that are unbound after a swap.

A part that only rotates with a bone — helmet, visor, a carried pickup — needs none of this.
Parent the renderer to the bone and swap its sprite freely.

## 5. Animating the resolver

With the Animation window recording, change a resolver's Label in the Inspector. The clip gets
one curve, *Sprite Resolver → Sprite Hash*: the serialised integer `m_SpriteHash`, evaluated
discretely, so there is no in-between value to resolve.

- **The clip stores the key, not the sprite.** The same `hand` / `fist` keyframe works on every
  skin whose library has that entry. That is the point of keying the resolver instead of the
  renderer's sprite.
- **The clip wins.** While a playing clip has a curve on a resolver, the Animator writes the key
  every frame and a `SetCategoryAndLabel` from gameplay lasts one frame. Parts gameplay swaps —
  equipment — are swapped through the *library* (§4), which the clip does not touch; parts the
  clip swaps — hands, mouth — are left to the clip.
- **Older clips keep working.** Curves on `m_SpriteKey`, or on the pair `m_CategoryHash` and
  `m_labelHash`, are still read and converted.
- **A resolver curve is not a frame clip.** For a part that plays eight frames in order, a
  sprite curve on the renderer is simpler: `unity-2d-sprites` → `reference/sprite-animation.md`.

Writing the curve from an Editor script: the hash function is not public, so read the key back
from a resolver after setting it.

```csharp
resolver.SetCategoryAndLabel("hand", "fist");
int key = new UnityEditor.SerializedObject(resolver).FindProperty("m_SpriteHash").intValue;

string path = UnityEditor.AnimationUtility.CalculateTransformPath(resolver.transform, animatorRoot);
var binding = UnityEditor.EditorCurveBinding.DiscreteCurve(
    path, typeof(UnityEngine.U2D.Animation.SpriteResolver), "m_SpriteHash");
var curve = new UnityEngine.AnimationCurve(new UnityEngine.Keyframe(0.25f, key));
UnityEditor.AnimationUtility.SetEditorCurve(clip, binding, curve);
```

Which state plays which clip, and when a transition may interrupt a swap, is
`unity-animation` → `reference/sprite-state-graph.md`.

## 6. Variant libraries

A variant names another library as its **Main Library** and inherits every category and label.
It can add labels and categories, and override the sprite of an inherited label; it cannot
rename or remove what it inherits.

| Use | Shape |
|---|---|
| A skin that changes three parts of twelve | A variant of the base library overriding `torso`, `helmet`, `visor` |
| A second character on a shared skeleton | Its own library, with the first as Main Library for the parts it reuses |
| Seasonal or rank recolours | One variant per set; the clips never change |

Create one from *Assets → Create → 2D → Sprite Library Asset Variant* with the main library
selected, or with the builder: select the main `.spriteLib` together with the folder, or pass
its path as the last argument of `Plan` and `Build`. In the plan, labels marked `*` override an
inherited one.

A variant against runtime overrides: the variant is an asset, shared by every instance that
uses it and visible in review. An override lives on one `SpriteLibrary` instance and is gone
when the object is. Skins are variants; what this runner picked up is an override.

A label removed from the main library is removed from every variant that did not override it.
The builder's plan lists disappearing labels for the file it writes, not for that file's
variants: before rebuilding a main library, run the first check below across its variants too.

## Checks

- Every clip-keyed category and label exists in **every** library the character can wear. For
  each library: `asset.GetCategoryNames()` and `asset.GetCategoryLabelNames(category)` printed
  from an eval, and the lists diffed.
- No category or label contains an underscore on both sides (§2).
- `SkinningAudit` reports no `swap-without-rebind`.
- In play mode, after each swap the game performs: `SkinSwap.CheckBindings()` is empty one
  frame later, and the Console has no `Rebind failed for`.
- A capture of each skin in the same pose, looked at by a human.
