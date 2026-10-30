# Slicing, pivots, borders, names — and the rules for scripts that edit them

`SKILL.md` §3 and §5 in full; the section numbers match the router's (§1 the importer mode, §2 the
capability gate, §6 the acceptance test, §7 frames into a clip).

## 3. Slicing, pivots, borders, names

The three slicing shapes and what actually decides them:

- **Grid** — fixed cell size, optional padding and offset, for a sheet authored on a grid.
  Compute the cell count from the texture size; do not assume 16 columns.
- **Automatic** — islands of non-transparent pixels, for irregular sheets; wrong where adjacent
  frames touch (they merge into one rect) or a frame has a detached element (it splits in two).
- **Isometric** — diamond cells for iso tilesets, where a grid slice cuts through neighbours.

Slice against the real dimensions from `ITextureDataProvider`: the **importer's reported size can
differ from the file's** once max-size and compression apply.

**Pivots** are normalised `(0,0)`–`(1,1)` within each rect. Use the enum and cast it; never the
raw number:

```csharp
r.alignment = UnityEngine.SpriteAlignment.Custom;   // not 9
r.pivot     = new UnityEngine.Vector2(0.5f, 0f);    // bottom-centre: feet on the ground
```

`(0.5, 0)` is the one that matters for characters — a centre pivot sinks a character into the
floor by half its height. The pivot goes wherever the sprite is anchored while it moves; other
anchors and the transparent-margin check are in `reference/sprite-geometry.md`.

**Borders** are `Vector4(left, bottom, right, top)` in pixels, and they are what 9-slice reads.
A UI panel whose corners stretch has a zero border, not a scaling bug.

**Names are the API surface of a sheet.** `Resources.Load`, Addressables and every animation
clip reference sprites by name, so `sprite_0 … sprite_37` is a sheet nobody can use. Name during
the slice, not after.

> **On Unity 2021.2+, adding or removing sprites also requires updating the name↔fileID map**
> (`SetNameFileIdPairs`), or existing references silently rebind to the wrong sprite —
> `reference/data-provider.md` §3.

**Re-slicing is not slicing.** A fresh `SpriteRect` with a fresh `GUID.Generate()` for a name that
already exists throws away the identity everything serialised against — reuse the existing rect and
replace only its `rect`, pivot and border. Where names are not stable the merge is geometric, in one
of three modes: `reference/data-provider.md` §3.

In `Single` mode there may be no rect to write to: for a pivot or a border, add one covering the
whole texture, **named after the file stem** — the asset's API surface (§1).

## 5. Style rules for generated scripts

- **Standalone snippets only.** No `AssetPostprocessor`, no `MenuItem`: a postprocessor keeps
  running against every future import, invisibly. **This rule is about scripts you write to do one
  job once.** A committed, project-owned import postprocessor is a good shape — a human decided it
  should exist forever — and `reference/import-pipeline.md` §2 covers it: it **only fires on
  import**, and it takes `Single` vs `Multiple` from one helper shared with the slicer.
- **Enums cast to their numeric type, never magic numbers.** `(int)SpriteAlignment.Center`, not
  `1`. The numbering is not stable across versions and a raw number is unreadable at review.
- **Verify afterwards** — read the rects back through a fresh provider (`SKILL.md` §6, and
  `reference/data-provider.md` §2); skip the reimport and the in-memory change evaporates.

**Ordering, when this is a project pipeline rather than one edit:** the metadata pass (reimport →
mode → pivots, borders, slices) finishes before any generator writes `Sprite` references into
ScriptableObjects, prefabs or catalogues — they capture references *at generation time*, so the
other order serialises `null` with no error. Each pass is a separate headless invocation and
**either can exit 0 having wired nothing**: assert on the artifacts, not the exit code.
`reference/import-pipeline.md` §5.

Scripts — adapt rather than rewrite. The slicers `resources/Editor/SliceSheet.cs` (grid),
`resources/Editor/AutomaticSliceSheet.cs` (islands, or a padded grid) and
`resources/Editor/IsometricSliceSheet.cs` run the checks above; `resources/SpriteToPng.cs` (pixels out)
and `resources/Editor/SheetToAnimationClip.cs` (`SKILL.md` §7) open no provider at all. What each adds is in
`reference/data-provider.md` §4.
Run the `SKILL.md` §6 acceptance test (and the four reads in `reference/sprite-animation.md` §7 for a clip)
before reporting any of them done.
Project-scale pipeline: `reference/import-pipeline.md`; margins, motion-driven pivots, stretched
borders: `reference/sprite-geometry.md`.
