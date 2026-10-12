# Shadows — one texture stretched over a distance

Part of the `unity-lighting` skill. SKILL.md §4 states the rules in a line; this file holds the
URP asset's shadow fields, the per-light settings, additional-light shadows, the screen-space
feature and what each artefact means.

A realtime shadow is a depth texture rendered from the light and stretched over everything
inside Shadow Distance. Every artefact is that texture having too few texels where the camera is
looking, or a bias that is wrong for the texel size. Tune distance first, then cascades, then
bias; resolution last.

## The URP asset

Shadows are configured on the URP asset the active quality tier uses, not in Quality settings.
Each tier can point at a different asset; read the one in force
(`GraphicsSettings.currentRenderPipeline`) — the audit prints it with its tier.

| Inspector | Property on `UniversalRenderPipelineAsset` | Default | Range |
|---|---|---|---|
| Main Light → Cast Shadows | `supportsMainLightShadows` | on | — |
| Main Light → Shadow Resolution | `mainLightShadowmapResolution` | 2048 | 256, 512, 1024, 2048, 4096 |
| Additional Lights → Cast Shadows | `supportsAdditionalLightShadows` | off | — |
| Additional Lights → Shadow Atlas Resolution | `additionalLightsShadowmapResolution` | 2048 | 256 … 4096 |
| Additional Lights → Shadow Resolution Tiers | `additionalLightsShadowResolutionTierLow` / `Medium` / `High` | 256 / 512 / 1024 | — |
| Shadows → Max Distance | `shadowDistance` | 50 | ≥ 0 |
| Shadows → Cascade Count | `shadowCascadeCount` | 1 | 1 – 4; a value outside throws |
| Shadows → splits | `cascade2Split`, `cascade3Split`, `cascade4Split` | 0.25 · (0.1, 0.3) · (0.067, 0.2, 0.467) | Fractions of Max Distance |
| Shadows → Last Border | `cascadeBorder` | 0.2 | Fraction of the last cascade over which shadows fade out |
| Shadows → Depth Bias | `shadowDepthBias` | 1 | 0 – 10 |
| Shadows → Normal Bias | `shadowNormalBias` | 1 | 0 – 10 |
| Shadows → Soft Shadows | `supportsSoftShadows` | off | — |
| Shadows → Quality | internal; field `m_SoftShadowQuality` through `SerializedObject` | Medium | Low, Medium, High |
| Shadows → Conservative Enclosing Sphere | `conservativeEnclosingSphere` | on in an asset made from the Create menu | Tighter cascades; keep on |

Writable from script: `shadowDistance`, `shadowCascadeCount`, the splits, `cascadeBorder`,
both biases and both resolutions. The `supports…` switches are get-only — tick them in the
inspector. The defaults above are the class's; an asset from a project template is usually
already different, so read the asset.

### Distance and cascades

Texel size on the ground ≈ distance covered ÷ resolution. One cascade of 2048 over 50 units
gives a 2.4 cm texel across the whole range. Over 150 units it is 7 cm, and every shadow edge
crawls.

- **Set Max Distance to how far a shadow matters, not how far the camera sees.** Gate room: 25.
  Lane run with a fixed camera: 40. Third-person outdoors: 60 to 80.
- **Cascades split that distance so texels are spent near the camera.** Two cascades at
  `cascade2Split` 0.25 give the first quarter of the distance half the texture. Four cascades
  cost four shadow passes over the scene's casters.
- **A fixed or top-down camera needs one cascade.** Everything visible is at roughly one
  distance; cascades buy nothing.
- `cascadeBorder` 0.2 fades the last fifth of the distance. At 0 shadows end on a hard line.

## Per light

| Field | API | Notes |
|---|---|---|
| Shadow Type | `Light.shadows`: `LightShadows.None`, `Hard`, `Soft` | Soft also needs Soft Shadows on the asset |
| Strength | `Light.shadowStrength` | 0 – 1. At 0 URP skips the light's shadow map entirely |
| Bias | `Light.shadowBias`, `Light.shadowNormalBias` | Used only when the light's Bias is Custom: `UniversalAdditionalLightData.usePipelineSettings == false` |
| Near Plane | `Light.shadowNearPlane` | Point and spot lights; raise it when a caster right at the light smears |
| Resolution tier | `UniversalAdditionalLightData.additionalLightsShadowResolutionTier` | Additional lights: Low, Medium, High, or Custom |
| Soft quality | `UniversalAdditionalLightData.softShadowQuality` | `SoftShadowQuality.UsePipelineSettings`, `Low`, `Medium`, `High` |

`light.GetUniversalAdditionalLightData()` returns the component, adding it when missing.

Per renderer: `Renderer.shadowCastingMode` (`ShadowCastingMode.Off`, `On`, `TwoSided`,
`ShadowsOnly`) and `Renderer.receiveShadows`. Per camera:
`UniversalAdditionalCameraData.renderShadows`.

## Additional-light shadows

Point and spot lights. Three conditions, all on the asset:

1. Additional Lights is **Per Pixel**, or the renderer is Forward+. Per Vertex lights cast none.
2. Additional Lights → **Cast Shadows** is ticked (`supportsAdditionalLightShadows`, off by
   default).
3. The light's Shadow Type is not None and its Strength is above 0.

The audit raises `additional-shadows-off` when a light asks and the asset refuses.

**A second directional light never casts shadows.** Only the main light has cascades
(`second-directional-shadowless`); make the sun the Sun Source — `reference/environment.md`.

All additional shadows share **one atlas** of `additionalLightsShadowmapResolution`. A spot light
takes one slice of its tier's size; a point light takes six. Four point lights on the High tier
ask for 24 slices of 1024 from a 2048 atlas, which holds four. URP then scales every slice down
and logs `Reduced additional punctual light shadows resolution by …`, and past a limit drops
shadows and logs `Too many additional punctual lights shadows`. Read the Console; then, in order:

1. Turn shadows off on lights whose shadow nobody reads.
2. Move point lights to spot lights where the fitting is directional anyway.
3. Drop decorative lights to the Low tier.
4. Raise the atlas to 4096.

## The Screen Space Shadows renderer feature

Universal Renderer Data → Add Renderer Feature → Screen Space Shadows. It resolves the main
light's shadows into one screen-sized texture before opaques are drawn; materials then sample
that texture.

- It needs a depth prepass, so it adds one where the renderer had none.
- It covers opaque geometry and the main light only. Transparents still sample the shadow map.
- It pays off with many cascades and soft shadows on desktop. On a phone it is an extra
  full-screen pass: leave it out.

The feature's class is internal; the audit detects it by name as
`pipeline.shadows.screenSpaceShadowsFeature`.

## What each artefact means

| You see | It is | Fix |
|---|---|---|
| No shadow at all | A switch | The ladder below |
| Stripes or a moiré on lit surfaces (acne) | The surface shadows itself: bias smaller than a texel | Raise Normal Bias first (1 → 1.5), then Depth Bias. Or shrink the texel: less distance, more cascades |
| The shadow starts away from the object's feet (peter-panning) | Bias pushed the shadow off the caster | Lower Depth Bias (1 → 0.5). Thin casters need real thickness; a plane has no back face to anchor it |
| Light leaking along the base of a wall | Normal Bias shrank the caster | Lower Normal Bias, or thicken the wall. Walls as single planes always leak |
| Edges crawl as the camera moves or turns (swimming) | Texels too large for the distance | Lower Max Distance; add a cascade; only then raise resolution |
| A visible line where shadow quality changes | A cascade boundary | Move the split so it falls where the camera rarely looks; Soft Shadows hide it |
| Shadows vanish beyond a distance | Max Distance and Last Border | Raise Max Distance, or bake far shadows with Shadowmask — `reference/light-modes.md` |
| Blocky edges | Hard shadows at this texel size | Soft Shadows on the asset and on the light; quality Low is enough on a phone |
| Shadows flicker on thin moving casters | A caster narrower than a texel | A simpler shadow proxy mesh with `ShadowCastingMode.ShadowsOnly` |
| Static shadows correct, the runner casts none | The light is Baked; or Subtractive with a light that is not the main directional; or the runner's renderer has casting off | `reference/light-modes.md`; `Renderer.shadowCastingMode` |

### No shadow at all — in order

1. The light's Shadow Type is None, or its Mode is Baked (a baked light casts no realtime shadow).
2. The URP asset in force has Cast Shadows off for that kind of light — and the tier in force
   is the one being edited.
3. The caster is beyond Max Distance from the camera.
4. `Renderer.shadowCastingMode` is Off on the caster, or `receiveShadows` is off on the floor.
5. The caster's material has no shadow pass: a transparent surface type with Cast Shadows off, or
   a custom shader with no `ShadowCaster` pass.
6. The receiver is transparent and Universal Renderer Data → Transparent Receive Shadows
   (`UniversalRendererData.shadowTransparentReceive`) is off.
7. The camera has Render Shadows unticked.
8. The light is a second directional, or a Per Vertex additional light.

## Related skills

What stays realtime under each Lighting Mode: `reference/light-modes.md`. A phone's starting
numbers: `reference/mobile-subset.md`. The count of shadow casters and the cost of the shadow
passes are measured with `unity-profiling`; reducing casters with LOD and culling is
`unity-scene-optimisation` → `reference/lod.md`. Shadows cast by 2D lights are
`unity-2d-rendering` → `reference/shadows-and-normals.md`.
