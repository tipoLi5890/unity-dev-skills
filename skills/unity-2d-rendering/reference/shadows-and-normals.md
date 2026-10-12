# Shadows, normal maps and mask maps

> Part of the `unity-2d-rendering` skill. All three sit on top of a working light: if the
> light itself does nothing, start at `reference/lights-2d.md`. Each needs a setting on the
> **light** and a matching piece on the **sprite**, and each fails silently when only one side
> is present.

## Shadows — a light that allows them, a caster that makes them

| Side | Needs |
|---|---|
| Light | `shadowsEnabled` true (default), `shadowIntensity` above 0 (default `0.75`), a type other than `Global` |
| Object | A `ShadowCaster2D` (Add Component → Rendering → 2D → Shadow Caster 2D) with Casts Shadows on |
| Both | The caster's Target Sorting Layers include the layer the shadow should fall **on**, and the light targets that layer too |

A Global light has no position and casts nothing. A shadow falls only on layers that both the
light and the caster target: a shelf whose caster targets `Floor` and `Actors` shades the floor
and the runner, and leaves `Overhead` alone.

### Where the shape comes from

**Casting Source** on the component is either the Shape Editor — a polygon edited by hand — or
a component on the same GameObject that can supply an outline:

| Source component | Outline |
|---|---|
| `SpriteRenderer` | The sprite's outline |
| Any `Collider2D` | The collider's shapes: box, circle, polygon, composite, tilemap |
| `SpriteShapeController` | The shape's edge |
| `SpriteSkin` | The deformed sprite, following the bones |

In the Editor a new caster picks one of these automatically when the GameObject has one.
**A caster added from script in a player build does not**: it falls back to the Shape Editor
source with a rectangle the size of the renderer's bounds. Author casters on prefabs; do not
`AddComponent<ShadowCaster2D>()` at runtime and expect the sprite's silhouette.

Trim Edge (`trimEdge`) pulls the outline inwards, which hides the gap between a sprite's
visible edge and its collider.

### Casting options and self-shadowing

`ShadowCaster2D.castingOption` is one of four values; `castsShadows` and `selfShadows` are the
two booleans it decomposes into.

| `ShadowCastingOptions` | Casts on others | Own renderer is shadowed |
|---|---|---|
| `CastShadow` (default) | Yes | No — the object stays lit inside its own shadow |
| `CastAndSelfShadow` | Yes | Yes |
| `SelfShadow` | No | Yes |
| `NoShadow` | No | No |

Leave walls and shelves on `CastShadow`: a top-down wall that shadows itself goes black on the
side facing away from every lamp. Use `CastAndSelfShadow` for an object that should read as a
silhouette — the sentry seen against the gate lamp.

### One caster per group of sprites

Several casters under one parent shadow each other: the crates of a stack each throw a shadow
across their neighbours. A `CompositeShadowCaster2D` on the parent merges every
`ShadowCaster2D` below it into one shape with one outline. The topmost composite in the
hierarchy owns the group.

### Shadows from a Tilemap

A Tilemap has no outline of its own; its collider does.

1. On the wall Tilemap: `TilemapCollider2D`, a `CompositeCollider2D` to merge the cells into
   outlines, and the static `Rigidbody2D` the composite needs. Building that collider stack
   correctly is `unity-physics-2d` → `reference/tilemap-colliders.md`.
2. On the same GameObject: `ShadowCaster2D`, Casting Source set to the `CompositeCollider2D`.
3. Paint a wall, enter play mode, move a Spot light past it and read the frame.

The caster follows the collider: tiles painted or removed at runtime update the shadow when
the collider regenerates. Only the Tilemap that blocks light gets a caster — floor and
decoration Tilemaps get none.

### What shadows cost

Each light that casts onto a batch of layers adds a shadow pass before its light draw, and the
renderer asset caps the shadow render textures it keeps (Max Shadow Render Textures, default 1)
and the light textures (Max Light Render Textures, default 16). The cheap levers, in order:

- Turn `shadowsEnabled` off on fill lights and on anything that does not move near a wall.
- Merge casters with a composite, or with a composite collider, so the outline is one polygon
  and not one per tile.
- Lower the light textures' Render Scale on the renderer asset.

## Normal maps — a secondary texture and a light quality

| Side | Needs |
|---|---|
| Sprite | A secondary texture named exactly `_NormalMap` on the sprite's texture, imported with Texture Type `Normal map` |
| Material | A lit shader that samples it — `Sprite-Lit-Default` does |
| Light | Normal Maps → Quality set to `Fast` or `Accurate`. The default is `Disabled` |

With Quality `Disabled` on every light the normal map is never sampled, whatever the sprite
carries. A Global light has no direction, so normal maps show only under Spot, Freeform and
Sprite lights.

**Adding the secondary texture.** In the Sprite Editor, the Secondary Textures module: add an
entry, name it `_NormalMap`, assign the texture. From script it is
`ISecondaryTextureDataProvider.textures` — `unity-2d-sprites` → `reference/data-provider.md`
for the provider, the apply and the reimport. Check it reached the sprite:

```csharp
var maps = new SecondarySpriteTexture[runnerSprite.GetSecondaryTextureCount()];
runnerSprite.GetSecondaryTextures(maps);
foreach (SecondarySpriteTexture m in maps) Debug.Log(m.name + " -> " + m.texture.name);
```

The secondary texture must be laid out exactly like the main texture — same size, same frame
positions — because it is sampled with the sprite's own UVs.

**Setting the light from script.** `Light2D.normalMapQuality` and `normalMapDistance` are
read-only. In the Editor, write the serialised fields:

```csharp
var so = new SerializedObject(gateLamp);
// The enum's numeric values are Fast 0, Accurate 1, Disabled 2 — assign by cast, never by index.
so.FindProperty("m_NormalMapQuality").intValue = (int)Light2D.NormalMapQuality.Fast;
so.FindProperty("m_NormalMapDistance").floatValue = 3f;
so.ApplyModifiedProperties();
```

Distance is the light's simulated height above the sprite plane, default `3`. It does not move
the light. A low value gives raking light and strong relief; a high value flattens it.

**Cost.** One light with normal maps enabled on a batch of layers makes the renderer draw
every sprite of that batch a second time into a normals texture. Enable it on the two or three
lights that carry the look, not on all of them. `Accurate` costs more per lit pixel than
`Fast`; start with `Fast`.

### Ladder: the normal map does nothing

1. The light's Normal Maps → Quality is not `Disabled`.
2. The light is not a Global light.
3. `GetSecondaryTextures` lists `_NormalMap` on the sprite actually being drawn — an animation
   that swaps to frames from another texture needs the map on that texture too.
4. The normal texture's import type is `Normal map`.
5. The material is lit: `SortingAudit.Json()` → `lit`.
6. The sprite is packed in an atlas: check the atlas carries the secondary texture as well —
   `unity-sprite-atlas`.

## Mask maps — where on the sprite a light is allowed

A second secondary texture, `_MaskTex`, lets a light reach only part of a sprite.

- The sprite carries `_MaskTex`, added the same way as `_NormalMap`.
- A blend style on the renderer asset has a Mask Texture Channel other than `None`. A new
  renderer asset ships two: `Multiply with Mask` (index 2) and `Additive with Mask` (index 3),
  both reading the red channel. The channel can also be inverted (One Minus R, and so on).
- A light with `blendStyleIndex` 2 or 3 is multiplied by that channel of the sprite's mask
  before it is applied.

Uses in the courier run: a red-channel mask over the runner's reflective strip so only the
strip catches the sentry's torch (`Additive with Mask`); a mask over the gate's indicator
panel so the gate lamp tints the panel and not the frame.

A sprite with no `_MaskTex` samples white: every masked light reaches all of it. A masked
blend style is one more light texture on each batch that uses it.
