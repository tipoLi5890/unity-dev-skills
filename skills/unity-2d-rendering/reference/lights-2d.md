# 2D lights — three conditions, and what the first light does to the scene

> Part of the `unity-2d-rendering` skill. A `Light2D` changes a pixel only when three things
> are true at once: the 2D Renderer is the renderer in force, the sprite's material is a lit
> one, and the light targets the sprite's sorting layer. This file holds each condition, the
> light types and their numbers, blend styles, and what a light costs.

## Condition 1 — the 2D Renderer is in force

`Light2D` is a feature of URP's 2D Renderer. Under the Built-in pipeline, or under URP with
the Universal Renderer as the default renderer, a `Light2D` component exists, shows a gizmo and
lights nothing; the GameObject → Light menu entries for 2D lights are disabled.

- Which pipeline asset is in force, and why a URP asset on disk can be inert: `unity-render-urp`
  → `reference/resolve-active-pipeline.md`.
- Which renderer that asset uses: `Renderer2DSetup.Report()` prints the renderer list, the
  default index and `renderer2DInForce`. A camera can select another entry of the list on its
  Renderer drop-down, so a scene can be lit in one camera and flat in another.
- No 2D Renderer in the list: `Tools/Unity Dev/2D Rendering/Create 2D Renderer` reports what
  it would create, then creates a 2D Renderer Data asset, appends it and makes it the default.

A script that names `Light2D` or `Renderer2DData` in an assembly with an asmdef needs a
reference to `Unity.RenderPipelines.Universal.2D.Runtime` as well as
`Unity.RenderPipelines.Universal.Runtime`. Both types are in namespace
`UnityEngine.Rendering.Universal`.

## Condition 2 — the material is lit

| Shader | Reacts to `Light2D` | Secondary textures |
|---|---|---|
| `Universal Render Pipeline/2D/Sprite-Lit-Default` | Yes | `_MaskTex`, `_NormalMap` |
| `Universal Render Pipeline/2D/Sprite-Unlit-Default` | No — always full colour | none |
| `Sprites/Default` (Built-in) | No | none |
| Sprite Lit / Sprite Custom Lit Shader Graph | Yes | as authored |
| Sprite Unlit Shader Graph | No | as authored |

A new `SpriteRenderer` takes the default material of the renderer asset: its Default Material
Type is `Lit`, `Unlit` or `Custom`. A project whose renderer asset says `Unlit` produces
sprites no light can touch, one at a time, for ever. `SortingAudit.Json()` reports `lit` per
renderer and warns when lights exist and nothing lit does.

## Condition 3 — the light targets the sprite's sorting layer

Every light has Target Sorting Layers. A sprite on a layer the light does not target is not
lit by it, however close it is.

```csharp
var lamp = gateLamp.GetComponent<Light2D>();
lamp.AddTargetSortingLayer("Actors");            // false when the name is unknown or already there
int[] ids = lamp.targetSortingLayers;            // sorting layer ids, not values
```

- A light created in the Editor, or by `AddComponent<Light2D>()`, targets every sorting layer
  that exists at that moment.
- A sorting layer added **later** is appended only to lights that are loaded and enabled in
  the Editor at the time. A light inside a prefab or an unopened scene does not get it: the
  new layer renders black under that light's scene until the light is edited.
- Assigning `targetSortingLayers` silently drops ids that are not valid layers.

## What the first light does

With **no** `Light2D` anywhere in the loaded scenes, lit materials draw at full colour — a
`Sprite-Lit-Default` sprite is indistinguishable from an unlit one. The moment one enabled
`Light2D` exists, the scene counts as lit: every sorting layer that no light targets receives
black, and so does every pixel of a targeted layer that lies outside the light's shape. That is the report "I added a torch and everything else went black":

| State | Lit sprite shows |
|---|---|
| No `Light2D` in the scene | Full colour |
| A light exists, none targets this layer | Black |
| A Spot light targets this layer, the sprite is outside its radius | Black |
| A Global light targets this layer | Colour × global colour × intensity |
| Global plus a Spot light over the sprite | The above, brighter inside the Spot |

So the first light in a scene is always a **Global** light targeting every layer, at the
ambient level the scene should have — intensity 1 for daylight, 0.2–0.4 for a night depot.
Local lights come second.

Two Global lights that target the same layer with the same blend style log
`More than one global light on layer …`, and one of them wins. Split them by layer or merge them.

The Scene view has its own lighting toggle in its toolbar. With it off the Scene view draws
unlit while the Game view is lit — compare in the Game view.

## Light types

`Light2D.lightType` takes `Global`, `Freeform`, `Sprite` and `Point`. The inspector and the
create menu call `Point` a **Spot** light. `Parametric` still exists in the enum and is
deprecated: convert those to `Freeform`.

| Type | Shape | Numbers to set |
|---|---|---|
| `Global` | Every pixel of its target layers | `color`, `intensity` |
| `Point` (Spot) | Disc or cone around the transform | `pointLightInnerRadius`, `pointLightOuterRadius`, `pointLightInnerAngle`, `pointLightOuterAngle` (360 = full disc) |
| `Freeform` | A polygon | `SetShapePath(Vector3[])`, `shapeLightFalloffSize` |
| `Sprite` | A sprite used as the light's cookie | `lightCookieSprite` |

Shared settings and their defaults:

| Member | Default | Meaning |
|---|---|---|
| `intensity` | `1` | Multiplier on `color`; above 1 brightens past the sprite's own colour |
| `falloffIntensity` | `0.5` | 0–1. Shape of the fade between inner and outer edge; higher is softer |
| `blendStyleIndex` | `0` | Which of the renderer's four blend styles this light draws into |
| `lightOrder` | `0` | Order among lights of the same blend style; lower is drawn first |
| `overlapOperation` | `Additive` | `Additive` sums overlapping lights; `AlphaBlend` lets a later light replace an earlier one |
| `shadowsEnabled` / `shadowIntensity` | `true` / `0.75` | `reference/shadows-and-normals.md` |
| `volumetricEnabled` / `volumeIntensity` | `false` / `1` | Draws the light's own shape additively over the scene |

A sentry's vision cone in the depot is a Spot light with outer angle 60, inner angle 50, outer
radius equal to the sentry's sight range, on a blend style of its own so that it tints rather
than brightens.

## Blend styles

The 2D Renderer Data asset holds four blend styles; a new asset names them `Multiply`,
`Additive`, `Multiply with Mask` and `Additive with Mask` at indices 0–3. A light draws into
exactly one, chosen by `blendStyleIndex`.

- **Multiply** scales the sprite's colour by the accumulated light. Ambient and ordinary lamps.
- **Additive** adds the light on top. Glows, muzzle flashes, the launch pad's pulse.
- **With Mask** multiplies the light by the red channel of the sprite's `_MaskTex` first, so a
  light reaches only the masked parts of a sprite: `reference/shadows-and-normals.md`.

Each blend style in use on a batch of layers is one more light texture to render and one more
texture every lit sprite samples. Use one until a second is needed.

## Cost

Lights are not drawn onto sprites. Per frame, for each batch of sorting layers and each blend
style used on it, the renderer draws every visible light's mesh into a light texture, then
draws the sprites sampling those textures. Three numbers follow.

- **Light texture resolution** — Render Scale in the renderer asset's lighting section, default
  `0.5`: light textures are half the screen resolution. Lower it before removing lights.
- **Lights per batch** — each visible, enabled light targeting the batch is one draw into the
  light texture, plus its shadow passes when it casts shadows.
- **Batches of layers** — adjacent sorting layers lit by the **same set of lights and shadow
  casters** are merged into one batch that shares its light textures. A light that targets
  `Floor` and `Overhead` and skips `Actors` between them forces three batches where one would
  do: three sets of light textures instead of one.

So: target contiguous runs of layers, and prefer lights that target all layers unless the look
depends on excluding one. Window → 2D → Light Batching Debugger shows the batches of the Game
view with the lights and shadow casters on each, which is where a split shows.

Measure the effect of a change as draw calls and frame time before and after, not by eye:
`unity-profiling`.

## Ladder: the light does nothing

1. `Renderer2DSetup.Report()` → `renderer2DInForce` is `true`. Otherwise condition 1.
2. `SortingAudit.Json()` → the sprite's `lit` is `lit`. Otherwise condition 2.
3. The light's Target Sorting Layers include the sprite's `layer`. Otherwise condition 3.
4. The light is enabled, its `intensity` is above 0, and the sprite is inside its shape — for
   a Spot light, within `pointLightOuterRadius` of the light in x/y. Keep the light's z
   inside the camera's clip range; it does not dim the light.
5. The blend style index names a style that exists; the inspector shows
   `No valid blend styles are enabled` when it does not.
6. Still nothing in the Game view while the Scene view shows it: the Game camera uses another
   renderer of the list.
