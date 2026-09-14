# Materials: snapshot, convert, restore, verify

> Part of the `unity-urp-migration` skill. The order is not a preference. Once a material's
> shader changes, its old property values are gone — a later pass that reads `_MainTex` to
> repair `_BaseMap` is reading a default and writing it back as if it were data. Snapshot
> first or do not convert.

## What the snapshot has to carry

Written by `resources/MaterialConverter.cs` to `Library/UrpMigration/material-snapshot.json`.
Under `Library/` rather than `Assets/` so it is neither imported nor committed, and on disk
rather than in memory so it survives the domain reload that conversion triggers.

Per material: asset path and GUID · source shader name · `_MainTex` with its scale and offset ·
`_Color` · `_BumpMap` · `_MetallicGlossMap` · `_SpecGlossMap` · `_Metallic` · `_Glossiness` ·
`_SpecColor` · `_EmissionMap` · `_EmissionColor` · `_Cutoff` · `_Mode`.

Textures are stored as GUIDs, not as object references — a serialized reference does not
survive the reload, and a GUID resolves back to the same asset afterwards.

Materials under `Packages/` and `Library/PackageCache/` are counted and skipped. They are
read-only; editing them is either impossible or wiped by the next package resolve. Where one
of them genuinely has to change, make a local copy in `Assets/` and point the renderer at that.

## Converting

Preferred route is the project's own converter. Manual assignment —
`mat.shader = Shader.Find("Universal Render Pipeline/Lit")` — is the fallback, and it is
refused outright when no snapshot exists.

Restore mapping, applied after either route:

| From the snapshot | Onto the URP material |
|---|---|
| `_MainTex` + scale + offset | `_BaseMap`, with the same scale and offset |
| `_Color` | `_BaseColor` |
| `_BumpMap` | `_BumpMap`, plus `EnableKeyword("_NORMALMAP")` |
| `_MetallicGlossMap` | `_MetallicGlossMap` |
| `_EmissionMap` + `_EmissionColor` | `_EmissionMap` + `_EmissionColor`, plus `EnableKeyword("_EMISSION")` |
| `_Cutoff` | `_Cutoff` |

The keywords matter as much as the textures: a normal map assigned without `_NORMALMAP` is a
texture the shader never samples, and it reads back perfectly from script.

The manual path **throws** when the snapshot had an albedo texture and `_BaseMap` comes back
null afterwards. A conversion that quietly drops a texture is the failure this whole file
exists to prevent, so it fails loudly at the material that did it rather than at the end.

## Trap: converted, not magenta, and on the wrong shader

Both the 2D and the 3D upgrader providers claim `Standard` at the same priority. On a 3D
project a plain `Standard` material can land on
`Universal Render Pipeline/2D/Mesh2D-Lit-Default` rather than
`Universal Render Pipeline/Lit`. Nothing throws, nothing logs, and the material does not render
magenta — it renders, just flatly and wrongly.

**Detection** is one read: in a 3D project, count materials whose `shader.name` starts with
`Universal Render Pipeline/2D/`.

```csharp
var hits = new System.Collections.Generic.List<string>();
foreach (var guid in UnityEditor.AssetDatabase.FindAssets("t:Material"))
{
    var p = UnityEditor.AssetDatabase.GUIDToAssetPath(guid);
    var m = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.Material>(p);
    if (m != null && m.shader != null && m.shader.name.StartsWith("Universal Render Pipeline/2D/"))
        hits.Add(p + " -> " + m.shader.name);
}
return hits.Count + " on 2D shaders: " + string.Join(", ", hits.ToArray());
```

**Remedy**: restore the affected materials from the rollback point, then either filter the
upgrader list to the 3D providers — `MaterialUpgrader.FetchAllUpgradersForPipeline(typeof(UniversalRenderPipelineAsset))`
returns both sets, so filter by the provider's type name, and confirm the member on your
version — or convert them with the manual path, which names its target shader and therefore
cannot be claimed by anything else.

Which provider wins is observed behaviour and can change between versions. **The invariant is
not "it goes to the 2D shader"; the invariant is "read `shader.name` back after every
conversion, whatever route ran".**

## Buckets that must not become Lit

| Bucket | Names and shaders | Target |
|---|---|---|
| Effects | particle, fog, smoke, steam, additive, decal, VFX | `Universal Render Pipeline/Particles/Unlit`, or `/Particles/Lit` when the effect was genuinely lit — either way preserve the blend mode |
| Foliage | grass, tree, leaf, billboard, terrain detail, SpeedTree, anything with `_Cutoff` | Preserve alpha clip, two-sided rendering, tint and normals. Wind and billboard behaviour usually does **not** survive — that loss is partial, and it is named |
| Package-owned | anything under `Packages/` or `Library/PackageCache/` | Local copy, or manual follow-up. Never edited in place |

Forcing a transparent additive smoke card to Lit gives a grey opaque quad that reads as "the
material converted" in every check except the one where somebody looks at it. A foliage card
that becomes a solid rectangle has the same shape of failure.

## Verifying

Reload every material from disk — not the objects held in memory from the conversion — and
check two things per material:

1. `shader.name` matches the target this material's bucket maps to.
2. If the snapshot had `_MainTex`, `_BaseMap` is not null.

`on2D > 0` or `nullBaseMap > 0` makes the material phase **partial**, regardless of how many
converted cleanly, and the report names the first few offending paths rather than the count
alone. A count tells someone there is a problem; a path lets them look at it.

"No magenta in the current camera" is not a check. Off-screen particle systems, disabled
objects and prefabs that no open scene instantiates all fail silently under that test.

## Worked example — the courier run

Four materials out of sixty-one carry the interesting cases:

- **`Lane_Asphalt`** — `Standard` with an albedo, a normal map and 8× tiling. Converts to
  `Universal Render Pipeline/Lit`. The tiling is the part that is easy to lose: it lives with
  `_MainTex` in the snapshot and has to be written back onto `_BaseMap`, not just the texture.
- **`Hazard_Smoke`** — an additive particle material. Goes to
  `Universal Render Pipeline/Particles/Unlit`. Forced to Lit it turns into a grey slab across
  the middle lane, which is worse than magenta because it reads as intentional.
- **`Sentry_Cutout`** — alpha-clipped, `_Cutoff` at 0.4. The threshold restores from the
  snapshot; without it the sentry's silhouette thickens by a few pixels and nobody can say why.
- **`Pickup_Glow`** — emission map plus emission colour. Needs `_EMISSION` enabled or the
  pickups stop glowing while every property reads back correct.

Verify line after the four steps:
`[URP-MIG] materials status=complete converted=57/57 on2D=0 nullBaseMap=0 effect=9 foliage=4 skippedPackage=4 …`
— complete on the gate this line checks, with the four package-owned materials carried into the
report as named manual follow-up. The phase wording follows the gate, not the mood:
`reference/migration-phases.md`.
