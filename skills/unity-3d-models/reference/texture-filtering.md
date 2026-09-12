# Filtering, and the settings that make a good model look cheap

## Texture filtering — the setting that makes a good model look cheap

Import defaults are wrong for anything large seen at a **grazing angle**: a ground plane, a long
wall, a barrier running away down a lane. Mipmaps alone are not enough — an isotropic mip must
pick one level for two very different rates of change, and whichever it picks is wrong along one
axis. That mismatch is what people report as "the whole screen is shimmering" or "it trembles".

Two settings, both shipped wrong by default:

- **`aniso: 1`** in the texture's `.meta` — no anisotropic filtering. Raise to **8**, and set
  `filterMode: 2` (trilinear) so mip transitions do not pop.
- **`m_MSAA: 1`** in the render-pipeline asset means MSAA is **OFF**. Everything thin — lane
  markings, railings, distant edges — is sub-pixel at distance and crawls. **4×** is the cheap kind
  of AA on tile-based mobile GPUs.

Editing the `.meta` directly is deterministic and triggers a reimport:

```python
s = re.sub(r'(\n\s+)aniso: \d+',       r'\g<1>aniso: 8', s)
s = re.sub(r'(\n\s+)filterMode: [01]',  r'\g<1>filterMode: 2', s)
```

Two caveats worth knowing before you flip MSAA on: it makes `WaitForEndOfFrame` mandatory before
any texture capture, and it lengthens frames enough to tip timing-sensitive tests. Both in
`unity-debug`.

A runtime alternative when a texture is loaded from `Resources/` rather than authored:
`tex.anisoLevel = 8; tex.filterMode = FilterMode.Trilinear;`
