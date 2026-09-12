# Character reference art brief

A ready-to-send specification for the T-pose reference images that feed image-to-3D. Hand it to an
artist verbatim, or paste it into an image-generation prompt.

Everything here exists because breaking it costs a re-generation. The requirements are split into
two tiers: **the first tier fails the pipeline outright**, the second only decides how good the
result is. If you have to negotiate, negotiate on the second.

---

## Tier 1 — non-negotiable

Break any of these and the model is unusable; no downstream setting recovers it.

**1. A true 90° T-pose.** Standing upright, both arms fully horizontal, clearly separated from the
torso. Legs apart with a visible gap between them — hip width, feet not touching.
*Why:* auto-riggers infer joint positions from the silhouette. Arms resting near the body make the
rigger weld arm and torso skin weights together, and nothing downstream unpicks that.

**2. One character per image. Nothing else in frame.** No text, labels, view names, borders, colour
swatches, callouts, close-up insets, or ground shadows.
*Why:* image-to-3D builds whatever it sees. Letterforms become extruded geometry. Ground shadows
become floating slabs — and worse, they enlarge the bounding box the auto-rigger uses to locate the
skeleton. A turnaround sheet fed as one image returns a single fused blob of four figures.

**3. Consistent design across all views.** Identical clothing, hairstyle, accessories, proportions
and colours. Same height in frame, same horizontal centring, same foot baseline.
*Why:* multi-view reconstruction assumes the views describe one object. Any drift is resolved as
geometry — a jacket that changes length between front and back becomes a deformed torso.

**4. Orthographic, or as close as possible.** No perspective distortion, no three-quarter angles, no
body tilt, no weight shifted onto one leg, no contrapposto.
*Why:* the reconstruction solves for a shape consistent with all views at once. Perspective in one
view and not another is an unsolvable contradiction, and it resolves as distortion.

**5. Square aspect ratio, 1024 × 1024 px minimum.** The character occupies 80–90% of image height,
with hands, hair and feet fully inside the frame — nothing cropped at any edge.
*Why:* see the resolution note below — this is a floor, not a target.

---

## Tier 2 — quality

**6. Resolution: aim well above the floor.** Reconstruction detail is capped by how many pixels the
*face* occupies, not by the image dimensions.

| Image size | Character at 85% | Face height (~⅛ of body) | Result |
|---|---|---|---|
| 340 × 930 crop | — | ~80 px | face melts, features unrecoverable |
| 1024 × 1024 | ~870 px | ~110 px | marginal |
| 1536 × 1536 | ~1300 px | ~165 px | comfortable |
| 2048 × 2048 | ~1740 px | ~220 px | ample |

**When a face comes out broken, raise input resolution before switching tools** — it is cheaper and
it is usually the actual cause.

**7. Long hair hangs straight down.** No windblown, floating or flared hair. It must not cross or
obscure the body silhouette, and must not merge with the arms in the side view.
*Two separate costs here.* Reconstruction: hair overlapping the torso fuses into it. And downstream:
**standard auto-rig skeletons contain no hair bones**, so a ponytail ends up rigidly parented to the
head and does not move at all while running. If the camera sits behind the character, that dead
ponytail is centre-frame the whole game. Long hair is a design decision with a cost — decide
knowingly.

**8. Loose clothing pieces behave the same way.** Skirts, capes, belt ends, ribbons, loose straps.
They reconstruct as stray shells and, having no bones, intersect the legs during animation. Keep
them close to the body or design them out.

**9. Hands flat, fingers slightly spread.** Palms facing down, fingers not overlapping each other.
Overlapping fingers fuse into a mitten.

**10. Symmetrical design where possible.** Most tools expose a symmetry option (`is_symmetric`,
`symmetry_mode`) that measurably cleans up topology. Asymmetric accessories force you to leave it
off. If the design has a one-sided element, know that you are trading topology quality for it.

**11. Backgrounds must be flat.** Pure white `#FFFFFF` — no gradient, vignette, texture or paper
grain. Background separation is done by the tool; anything non-uniform leaks into the silhouette.

---

## Deliverables

Three views per character: **front, left, back**. Right is optional — with a symmetric design it
adds little, and most endpoints accept 2–4 views.

**"Left view" means the camera stands to the character's left**, so the character faces the right
edge of the frame. State this explicitly when commissioning: the convention is genuinely ambiguous
in the wild, and getting it backwards mirrors the model — which shows up as one-sided logos, numbers
and accessories landing on the wrong side.

Two background variants of every image:

| Variant | Suffix | Used when |
|---|---|---|
| Pure white background | *(none)* | the endpoint has no alpha-aware option |
| Transparent background | `_transparent` | the endpoint exposes something like `use_original_alpha` |

Supplying both means the tool choice is made later, not baked into the art order. Transparent PNGs
carry a real alpha channel — **verify it exists** (`sips -g hasAlpha file.png`) rather than trusting
the file name; "transparent" exports that are silently flattened to white are common.

---

## Naming — encode the upload order

Multi-view endpoints identify views **by array position, not by file name**. The Tripo
`multiview-to-3d` order is `front, left, back, right`, with front mandatory.

Plain descriptive names sort into the wrong order. `girl_front` / `girl_back` / `girl_left` sorts
alphabetically as **back → front → left**, so a multi-select drag drops `back` into slot 2 — the
`left` slot — and the model reconstructs the back of the head as a profile. Number the files so
alphabetical order *is* array order:

```
girl_1_front.png          boy_1_front.png
girl_2_left.png           boy_2_left.png
girl_3_back.png           boy_3_back.png
```

Transparent variants take the same index plus the suffix:

```
girl_1_front_transparent.png
girl_2_left_transparent.png
girl_3_back_transparent.png
```

Substitute any character identifier for `girl` / `boy`; only the `_<n>_<view>` part carries meaning.

---

## Acceptance check — run this before paying for a 3D generation

Cheap to check, expensive to discover later.

```bash
# 1. Square, and at or above the resolution floor
sips -g pixelWidth -g pixelHeight <file>.png

# 2. Transparent variants really have an alpha channel
sips -g hasAlpha <file>_transparent.png

# 3. Backgrounds on the white variants are actually pure white,
#    and the three views share a character height.
#    (Scale to 1×1 to read the average colour: near-white = clean background.)
ffmpeg -i <file>.png -vf scale=1:1 -f rawvideo -pix_fmt rgb24 - 2>/dev/null | xxd -p
```

Then eyeball, in this order — each of these has caused a re-do:

- [ ] Arms exactly horizontal, with daylight between arm and torso
- [ ] Legs apart, feet not touching
- [ ] No text, border, colour bar, inset, or ground shadow anywhere in frame
- [ ] Nothing clipped at any edge — fingertips, hair tips, toes all inside
- [ ] Front / left / back overlay to the same character height and foot line
- [ ] Side view faces the correct direction for the "left" convention above
- [ ] Hair hangs down and does not cross the body outline
- [ ] Clothing, colours and accessories identical across all three views

A view that fails any line is worth re-requesting. Regenerating art costs a prompt; regenerating a
3D model, re-rigging it, and re-authoring the animation set costs an afternoon.
