# Masks and materials — who is hidden, who is tinted, and what it costs in draw calls

> Part of the `unity-2d-rendering` skill. A `SpriteMask` hides or reveals other renderers; a
> material decides whether a sprite is lit and how it is tinted. Both are common ways to turn
> one draw call into forty. This file holds the mask rules, the three sprite materials in
> brief, and per-renderer colour without breaking batches.

## SpriteMask

A `SpriteMask` draws no colour. Its sprite's alpha, above `alphaCutoff`, marks an area in the
stencil buffer; other renderers opt in to reading it.

| Side | Setting |
|---|---|
| Mask | `sprite` (the shape), `alphaCutoff`, optionally a custom range |
| Masked renderer | `maskInteraction`: `None` (default), `VisibleInsideMask`, `VisibleOutsideMask` |

`maskInteraction` exists on `SpriteRenderer`, `TilemapRenderer`, `ParticleSystemRenderer` and
`SpriteShapeRenderer`. A renderer left on `None` ignores every mask, which is the first thing
to check when a mask "does nothing".

```csharp
// The depot's dark aisle: the runner is visible only inside the sentry's torch shape.
runnerBody.maskInteraction = SpriteMaskInteraction.VisibleInsideMask;
```

### Which renderers a mask reaches

By default a mask reaches **every** renderer in the scene whose `maskInteraction` is not
`None`, on every sorting layer. Two ways to narrow it:

**A custom range.** `isCustomRangeActive` limits the mask to renderers whose sorting layer and
Order in Layer fall between a back and a front bound:

```csharp
SpriteMask torch = sentryTorch.GetComponent<SpriteMask>();
torch.isCustomRangeActive = true;
torch.backSortingLayerID  = SortingLayer.NameToID("Actors");
torch.backSortingOrder    = -1;      // one below the lowest order that should be masked
torch.frontSortingLayerID = SortingLayer.NameToID("Actors");
torch.frontSortingOrder   = 100;     // at or above the highest
```

The range is in the same units as keys 1 and 2 of `reference/sort-order.md`: layer value
first, then order. Leave a margin of one order at each end and read the frame — a renderer
sitting exactly on a bound is the one that surprises.

**A SortingGroup.** A mask that is a child of a `SortingGroup` reaches only the renderers of
that group. This is how a character carries its own mask — a dissolve, a window cut into a
shield — without hiding its neighbours.

`SpriteMask.maskSource` chooses what supplies the shape: `Sprite`, or `SupportedRenderers` to
use a renderer on the same GameObject.

### When a mask does nothing

1. The masked renderer's `maskInteraction` is `None`.
2. A custom range is active and the renderer is outside it — compare with the audit's
   `layerValue` and `order`.
3. The mask is inside a `SortingGroup` the renderer is not part of, or the reverse.
4. The 2D Renderer Data asset has Depth/Stencil Buffer unticked: masks need the stencil.
5. The renderer uses a hand-written shader with no stencil block. Shader Graph sprite targets
   and the default sprite materials handle masking; a custom ShaderLab shader must add it.
6. The mask's sprite is fully below `alphaCutoff`.

Masks cost batches: masked and unmasked sprites do not share a draw call, and each mask draws
twice, once to mark the stencil and once to clear it. A scene with one mask per pickup is a
scene with no batching; use one mask for the area.

## The three sprite materials

| Material | Lit by `Light2D` | Use |
|---|---|---|
| `Sprite-Lit-Default` | Yes | Everything in a lit scene |
| `Sprite-Unlit-Default` | No | UI in the world, effects that must stay at full brightness, a scene with no lights at all |
| A Sprite Shader Graph | As its target says | A look the two defaults cannot give: hit flash, dissolve, outline, palette swap |

Under the Universal Renderer `Sprite-Lit-Default` still draws, through its forward pass, at
full colour: it is lit only under the 2D Renderer.

A Sprite Shader Graph is created from Assets → Create → Shader Graph → URP, as Sprite Lit,
Sprite Unlit or Sprite Custom Lit. Three reference names matter, because the `SpriteRenderer`
fills them from the sprite and not from the material:

| Texture property reference | Filled with |
|---|---|
| `_MainTex` | The sprite's texture |
| `_NormalMap` | The secondary texture of that name |
| `_MaskTex` | The secondary texture of that name |

A graph whose main texture is named anything else shows the material's own texture — usually
white — on every sprite. Authoring the graph itself is outside this skill; a custom HLSL
function node is `unity-render-urp` → `reference/shader-graph-custom-node.md`.

## Per-renderer colour, in order of cost

| Method | Cost | Use |
|---|---|---|
| `SpriteRenderer.color` | None — it is vertex colour; the batch is kept | Tint and fade. Multiplies the texture, so it can darken and never whiten |
| `MaterialPropertyBlock` | The renderer leaves the SRP Batcher; renderers with different blocks do not share a draw call | A per-renderer shader value on a handful of objects: flash amount, dissolve threshold |
| `renderer.material` | A new material instance per renderer, never batched with the original, and it must be destroyed | Avoid |
| A second shared material | One extra batch for everything using it | A state many objects share: every hazard that is armed |

A hit flash cannot be done with `color` — white times the texture is the texture. It needs a
shader with a flash property, driven per renderer:

```csharp
static readonly int FlashId = Shader.PropertyToID("_Flash");
MaterialPropertyBlock _block;

void SetFlash(SpriteRenderer sr, float amount)
{
    _block ??= new MaterialPropertyBlock();
    sr.GetPropertyBlock(_block);       // keep what the SpriteRenderer already put there
    _block.SetFloat(FlashId, amount);
    sr.SetPropertyBlock(_block);
}
```

Read the block before writing it: the block is replaced as a whole, and a fresh one drops
values set earlier. For a property that most renderers leave at zero, clear the block again
(`sr.SetPropertyBlock(null)`) when the flash ends so the renderer batches once more.

## What breaks a batch between two sprites

Two sprites share a draw call only when they are **consecutive in the sorted order** and agree
on everything the draw call fixes:

- **Material.** Lit next to unlit, or a material instance next to its original.
- **Texture.** Two sprites from different textures. Packing them together is
  `unity-sprite-atlas`.
- **Interleaving.** Runner (atlas A), pickup (atlas B), sentry (atlas A), sorted in that
  order by y, is three draw calls although only two textures exist. Y-sorted scenes interleave
  constantly; one atlas for everything on the `Actors` layer is what restores the batch.
- **Property block, mask interaction, a `SortingGroup` boundary, a different renderer type**
  sorting in between.

The Frame Debugger states the reason on each draw event — select the event and read why it
could not be batched with the previous one. Count draw calls before and after a change as
numbers: `unity-profiling`.
