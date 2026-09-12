# Mixamo: upload, markers, export

## 7. Mixamo export settings

- **Format: `FBX for Unity(.fbx)`** — not plain `FBX(.fbx)`.
- **First download:** search the `T-Pose` animation → **With Skin**. This is the body; it
  owns the Avatar.
- **Every other animation: Without Skin.** Size is the fast check — With Skin ≈ 3 MB,
  Without Skin ≈ 0.3–0.4 MB. A 3 MB "animation" means the wrong toggle.
- **In Place: required.** Translation belongs to the Rigidbody / CharacterController; a
  clip that also translates fights it every frame.
- **Trim: keep the full range** — cutting either end of a loop makes the seam pop.
- **FPS 30** is enough for mobile (Unity interpolates between keys). **Keyframe Reduction:
  none** — a loop is a dozen-odd frames already, so reduction costs quality and saves nothing.
- Leave **Overdrive / Arm-Space** neutral; speed variation is a runtime concern (§9).

**File naming contract** — the one thing to get right by hand, since the Editor automation
keys off it:

| File | Meaning |
|---|---|
| `<character>.fbx` | The **With Skin** export. Carries the mesh, owns the Avatar. **No clip keyword in the name.** |
| `<character>@RunSlow.fbx` | Animation only. Keyword `runslow` → clip `RunSlow`. |
| `<character>@RunFast.fbx` | Animation only. Keyword `runfast` → clip `RunFast`. |
| `<character>@Jump.fbx` | Animation only. Keyword `jump`. |
| `<character>@Hurt.fbx` | Animation only. Keyword `hurt` / `hit`. |
