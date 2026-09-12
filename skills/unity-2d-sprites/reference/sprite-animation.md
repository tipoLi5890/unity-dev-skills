# Frames into an AnimationClip — one ground line, one binding, one sample rate

> Part of the `unity-2d-sprites` skill. Slicing gives you rects; this file turns them into a clip
> that plays. **Unity cannot play a GIF.** A preview GIF/APNG/WebP is a review artifact; what the
> game needs is equal-canvas frames sharing a ground line, an `AnimationClip` carrying an
> object-reference curve on `m_Sprite`, and an `AnimatorController` whose default state is that
> clip.

List animatable bindings without writing to the project: call
`AnimationUtility.GetAnimatableBindings` on a transient `HideFlags.HideAndDontSave` object, and
check the scene's `isDirty` is still `False` afterwards.

## 1. The input contract — what "equal canvas" buys you

`codex-visual`'s `sheet_to_frames.py` writes a frame set plus a `frames.json` sidecar, and that
sidecar is the handoff. The fields this side reads:

| Field | Use here |
|---|---|
| `frames[].file` / `frames[].name` | import order and sprite names — `idle_000`, `idle_001`, … |
| `canvas` `[W, H]` | every frame is the same pixel size, so one rect size fits all |
| `pivot` (`bottom-center`) | the pivot to write on every rect: `(0.5, 0)` |
| `fps_hint` | the clip's `frameRate`; the preview GIF used the same number |
| `set_metrics.baseline_drift_max_px` | the bob, in pixels, before you build anything |
| `set_metrics.empty_count` / `near_duplicate_count` / `bleed_count` | reasons to send the set back, not to import it — the `empty_cells`, `near_duplicate_pairs` and `bleed_cells` lists beside them name which cells |

> **Equal canvas is not the same as a shared ground line, and only one of them is free.** Frames
> can all be 512×512 and still put the soles at a different height in each one. A generated
> 16-frame sheet can arrive with a baseline drift of several pixels, which
> `sheet_to_frames.py --align both` takes to zero. Un-repaired, 6 px of drift at 100 PPU is a
> 0.06-unit vertical twitch every frame — the character *bobs*, and it looks like a pivot bug
> because that is exactly what it is: a per-frame pivot instead of a shared one.

Fix it upstream, in the frames, not downstream in the pivots. A bottom-centre pivot on frames whose
ink sits at different heights is still a bob; a bottom-centre pivot on registered frames is a
ground line. Read `baseline_drift_max_px` from `frames.json` before importing and re-run the
alignment if it is not near zero.

> **A disagreement about the metrics is usually a disagreement about the alpha cutoff, and the
> sidecar tells you which one it used.** `frames.json` records `alpha_threshold` at the top level
> and again inside `set_metrics` — `16` by default, the alpha above which the slicer counts a pixel
> as content. It matters because a soft-matte chroma key leaves a low-alpha haze over the
> background: re-measuring the same frame at alpha > 8 can turn a zero baseline spread into
> several pixels. So compare your own cutoff against that field before you blame the frames — and
> prefer frames keyed hard, without a soft matte. The sidecar also records each frame's bare
> **`alpha > 0`** bbox beside its thresholded one (`bbox_alpha0`, with `alpha0_tail_count` and
> `baseline_drift_max_px_alpha0` in the metrics) — that is the bbox Unity's sprite auto-trim and
> an atlas packer see, and the two can disagree by whole pixels: a set whose thresholded baseline
> spread aligns to zero can still be pixels out at alpha > 0. `sheet_to_frames.py --clear-below-thr`
> removes the difference at the source.

An already-sliced sheet is the other accepted input: one texture in `Multiple` mode whose rects are
the frames, in which case §3 reads the rects instead of a folder.

## 2. Import settings that decide whether the clip is even possible

Per-frame PNGs are one sprite each, so `Single` is right for them and the importer publishes a
sprite **named after the file** — the name the clip serialises against (parent skill §1). A sliced
sheet is `Multiple` with named rects. Both need `textureType = Sprite` set explicitly; a plain PNG
imports with `spriteImportMode = None`.

All of these have public setters on `UnityEditor.TextureImporter`: `textureType`,
`spriteImportMode`, `spritePixelsPerUnit`, `filterMode`, `textureCompression`, `mipmapEnabled`,
`maxTextureSize`, `alphaIsTransparency`, `npotScale`.

| Setting | Value for a frame set | Why it matters to the animation |
|---|---|---|
| `spritePixelsPerUnit` | one number for the whole set | Per-asset. Two frames at different PPU are two different on-screen sizes, and the character pulses. |
| `filterMode` | `FilterMode.Point` for pixel art | Enum members are `Point, Bilinear, Trilinear`. Bilinear on pixel art softens edges differently per frame, which reads as flicker. |
| `textureCompression` | `TextureImporterCompression.Uncompressed` for pixel art | Members are `Uncompressed, Compressed, CompressedHQ, CompressedLQ`. Block compression puts its artifacts in different places per frame — a static area shimmers. |
| `mipmapEnabled` | `false` | A 2D frame never samples a mip; enabling it wastes memory and can pick a blurrier level per frame. |
| `maxTextureSize` | at or above the real frame size | A Max Size below the source halves every coordinate the importer reports, and the frames come out half the authored size (parent skill §5). |
| pivot | `alignment = SpriteAlignment.Custom`, `pivot = (0.5f, 0f)` | The shared ground line. `SpriteAlignment.BottomCenter` exists and is equivalent, but Custom keeps the number visible at review. |

`SpriteAlignment` members, enumerated rather than recalled:
`Center, TopLeft, TopCenter, TopRight, LeftCenter, RightCenter, BottomLeft, BottomCenter,
BottomRight, Custom`.

## 3. The clip — one object-reference curve on `m_Sprite`

The signature, read off the assembly:

```csharp
void UnityEditor.AnimationUtility.SetObjectReferenceCurve(
    UnityEngine.AnimationClip clip,
    UnityEditor.EditorCurveBinding binding,
    UnityEditor.ObjectReferenceKeyframe[] keyframes);
```

with `GetObjectReferenceCurve(clip, binding)`, `GetObjectReferenceCurveBindings(clip)` and a plural
`SetObjectReferenceCurves(clip, bindings, keyframes[][])` alongside it.

`UnityEditor.EditorCurveBinding` is a **struct**, and its three members are not all the same kind of
member: `path` and `propertyName` are public **fields**, `type` is a public **property** with a
setter, and `isPPtrCurve` / `isDiscreteCurve` / `isSerializeReferenceCurve` are read-only. Static
factories exist: `PPtrCurve(path, type, propertyName)`, `FloatCurve`, `DiscreteCurve`,
`SerializeReferenceCurve`.
`UnityEditor.ObjectReferenceKeyframe` is a struct with the fields `float time` and
`UnityEngine.Object value`.

The property name is `m_Sprite` for both renderers, and both are PPtr curves whose value type is
`UnityEngine.Sprite`:

| Target | `binding.type` | `propertyName` | Enumerated binding |
|---|---|---|---|
| `SpriteRenderer` | `UnityEngine.SpriteRenderer` | `m_Sprite` | `path="" type=UnityEngine.SpriteRenderer prop=m_Sprite isPPtrCurve=True valueType=UnityEngine.Sprite` |
| UI `Image` | `UnityEngine.UI.Image` | `m_Sprite` | same shape; the only other sprite-ish animatable member is `m_UseSpriteMesh`, a `bool` |

`path` is relative to the GameObject holding the `Animator`: `""` targets that object's own
component, `"Body/Sprite"` targets a descendant, and the path round-trips through the clip
unchanged. Get the path wrong and the clip is silently
inert — it plays, nothing moves.

```csharp
var binding = UnityEditor.EditorCurveBinding.PPtrCurve(
    "", typeof(UnityEngine.SpriteRenderer), "m_Sprite");

var keys = new UnityEditor.ObjectReferenceKeyframe[sprites.Length];
for (int i = 0; i < sprites.Length; i++)
{
    keys[i].time  = i / fps;       // one keyframe per frame, evenly spaced
    keys[i].value = sprites[i];
}
UnityEditor.AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);
```

> **Do not compare an `EditorCurveBinding` you built to one the clip hands back with `==`.**
> A hand-built `new EditorCurveBinding { path = "", propertyName = "m_Sprite", type =
> typeof(SpriteRenderer) }` reports `isPPtrCurve = False`; `PPtrCurve(...)` reports
> `isPPtrCurve = True, isDiscreteCurve = True`; the binding stored in the clip reports
> `isPPtrCurve = True, isDiscreteCurve = False` — so `==` is **false against both of them**, while
> `GetObjectReferenceCurve` returns all four keyframes for either form. Equality includes the
> internal curve-kind flags; the identity that matters is `path` + `type` + `propertyName`. Compare
> on those three.

Writing the curve with the hand-built binding works — the setter supplies the PPtr flag — so this
is not a reason to avoid the plain struct, only a reason not to assert on it.

**Clearing a curve is `null`, not an empty array.** `SetObjectReferenceCurve(clip, binding, null)`
takes the binding count from 1 to 0 and makes `clip.empty` true.

## 4. `frameRate`, and the length you get for free

```csharp
clip.frameRate = fps;              // BEFORE you decide anything about times
```

> **A new `AnimationClip` has `frameRate = 60`.** Forget
> this line and a 16-frame set authored at 10 fps still plays at whatever spacing you wrote, but
> the Animation window's grid, the Inspector's Sample Rate and every later hand-edit are on a 60
> fps ruler. Take the number from `frames.json`'s `fps_hint` so the clip and the preview GIF agree.

`frameRate` is what the Inspector calls **Sample Rate** and what the asset serialises as
`m_SampleRate`: setting `clip.frameRate = 12f` makes the serialised `m_SampleRate` read `12`. That
is also the read-back for the acceptance check in §7.

**Clip length is `N / fps`, not `(N-1) / fps`.** With N keyframes spaced `1/fps` apart, the last
keyframe sits at `(N-1)/fps` but the clip's `length` — and `AnimationClipSettings.stopTime` — comes
out at exactly `N/fps`: 6 frames give `last=0.5 length=0.6` at 10 fps, `last=0.4167 length=0.5` at
12 fps, `last=0.2083 length=0.25` at 24 fps. So the final
frame already gets a full frame of screen time, and a loop closes without a duplicate keyframe. To
*hold* the last frame longer, append duplicate keyframes at `(N+k)/fps` — the length follows the
same rule.

## 5. Loop vs one-shot

Looping is not a property on the clip; it is a field on a settings object you must write back.

```csharp
var st = UnityEditor.AnimationUtility.GetAnimationClipSettings(clip);
st.loopTime = loop;
UnityEditor.AnimationUtility.SetAnimationClipSettings(clip, st);
```

> **`GetAnimationClipSettings` returns a copy, and `AnimationClipSettings` is a class, so the
> mistake does not look like one.** After `st.loopTime = true`, re-reading the clip's settings
> still gives `False`; only after `SetAnimationClipSettings(clip, st)` does it read `True`, and the
> asset then serialises `m_LoopTime: True`.
> Mutating a struct copy would at least be a familiar bug; here the copy is a reference type, so
> nothing warns you.

`AnimationClipSettings` lives in `UnityEditor.CoreModule` and its public fields are
`additiveReferencePoseClip, additiveReferencePoseTime, startTime, stopTime, orientationOffsetY,
level, cycleOffset, hasAdditiveReferencePose, loopTime, loopBlend, loopBlendOrientation,
loopBlendPositionY, loopBlendPositionXZ, keepOriginalOrientation, keepOriginalPositionY,
keepOriginalPositionXZ, heightFromFeet, mirror`. Only
`loopTime` concerns a sprite clip — `loopBlend` and the rest are Humanoid root-motion controls, and
setting them on a sprite clip achieves nothing.

**One-shot performances** — a transformation, a hit reaction, a UI flourish — want `loopTime =
false` plus a way for gameplay to know it ended. `clip.events` is a settable `AnimationEvent[]`, and
`AnimationEvent` is a class with settable `time`, `functionName`, `stringParameter`,
`floatParameter`, `intParameter`, `objectReferenceParameter` and `messageOptions`:

```csharp
clip.events = new[] {
    new UnityEngine.AnimationEvent {
        time = (sprites.Length - 1) / fps,      // the last KEYFRAME, not clip.length
        functionName = "OnAnimationFinished"    // a method on a component on the animated object
    }
};
```

Place the terminal event on the last keyframe time, `(N-1)/fps`, which is inside the clip; if you
need one at exactly `clip.length`, test in play mode that it fires before relying on it. The
handler is a plain method on a component on the animated GameObject; a missing method is a runtime
warning, not a compile error, so name it once and grep for it.

## 6. The controller

Two statics and `AddMotion`, read off the assembly:

```csharp
static UnityEditor.Animations.AnimatorController
    CreateAnimatorControllerAtPath(string path);
static UnityEditor.Animations.AnimatorController
    CreateAnimatorControllerAtPathWithClip(string path, UnityEngine.AnimationClip clip);
UnityEditor.Animations.AnimatorState AddMotion(UnityEngine.Motion motion);
UnityEditor.Animations.AnimatorState AddMotion(UnityEngine.Motion motion, int layerIndex);
```

`AnimatorStateMachine.AddState(string)` and `AddState(string, Vector3)` both return an
`AnimatorState`; `AddState(AnimatorState, Vector3)` returns void. `AnimatorStateMachine.defaultState`
and `states`, `AnimatorControllerLayer.stateMachine`, and `AnimatorState.motion / speed / name /
writeDefaultValues` all have public setters.

> **Do not rely on the graph `CreateAnimatorControllerAtPathWithClip` builds** — which states
> exist, which one is `defaultState`. Set `defaultState` explicitly and assert on it, and the
> question stops mattering:

```csharp
var ctrl  = UnityEditor.Animations.AnimatorController
    .CreateAnimatorControllerAtPathWithClip(controllerPath, clip);
var sm    = ctrl.layers[0].stateMachine;
sm.defaultState = sm.states[0].state;      // assert on it afterwards, do not assume it
```

A single-clip controller is the whole graph for an idle or a one-shot. States, parameters and
transitions past that — blend trees, masked layers, root motion — are `unity-rigged-character`'s
subject, not this skill's.

## 7. Acceptance — four reads, and none of them is the exit code

The generator can exit 0 having wired nothing (parent skill §5), so assert on artifacts:

```csharp
// 1. the sprites exist as sub-assets, by name (parent skill §6). Which count you assert
//    depends on which of §1's two inputs you used — they publish sprites differently.

// 1a. one sliced sheet: every frame is a sub-asset of that single texture.
int nSheet = 0;
foreach (var o in UnityEditor.AssetDatabase.LoadAllAssetsAtPath(texturePath))
    if (o is UnityEngine.Sprite) nSheet++;         // must equal the frame count

// 1b. a folder of per-frame PNGs: Single mode publishes exactly one Sprite per file, so the
//     count on any one path is 1, not the frame count. Sum over the frames, asserting one
//     each: that names the file that failed, where a wrong total tells you nothing.
int nFolder = 0;
foreach (var p in framePaths)
{
    int perFile = 0;
    foreach (var o in UnityEditor.AssetDatabase.LoadAllAssetsAtPath(p))
        if (o is UnityEngine.Sprite) perFile++;
    if (perFile != 1) throw new System.Exception($"{p} published {perFile} sprites, expected 1");
    nFolder += perFile;                            // ends at framePaths.Length
}

// 2. the curve holds one keyframe per frame
var b    = UnityEditor.AnimationUtility.GetObjectReferenceCurveBindings(clip);   // == 1
var keys = UnityEditor.AnimationUtility.GetObjectReferenceCurve(clip, b[0]);     // == frame count
foreach (var k in keys) if (k.value == null) throw new System.Exception("null sprite in curve");

// 3. the sample rate and the loop flag survived the write
//    clip.frameRate == fps_hint from frames.json
//    UnityEditor.AnimationUtility.GetAnimationClipSettings(clip).loopTime == loop
//    clip.length    == frameCount / fps   (§4)
```

Then the fourth: **scrub the clip in the Editor's own Animation window preview.** It is the only
check that catches a curve bound to the wrong `path` — the numbers above all pass on an inert clip.

A `null` in the keyframe values is the ordering failure below, arriving one indirection late.

## 8. The two ordering traps

Both are written down once, in `reference/import-pipeline.md`; this is what each does to a clip.

- **Rects must exist before anything captures `Sprite` references.** (§5 there.) A clip builder, a
  ScriptableObject populator and a prefab wiring pass all capture references *at generation time*,
  so running the metadata pass second serialises `null` into every slot with no error at all.
  Slice, `Apply()`, `SaveAndReimport()`, **then** build the clip.
- **A texture in `Multiple` mode with zero rects publishes no sprite at all** — not one named after
  the file, not any (§4 there, and parent skill §1). A clip built against such a sheet is a curve
  full of nulls. Never set `Multiple` "to be safe", and slice in the same run that sets it.

## 9. UI `Image` instead of `SpriteRenderer`

Same binding name, different component and a different sizing model.

- `binding.type` is `UnityEngine.UI.Image`, which lives in the `UnityEngine.UI` assembly. In an
  asmdef, reference it; in a script that should not hard-depend on uGUI, resolve it —
  `System.Type.GetType("UnityEngine.UI.Image, UnityEngine.UI")` resolves it, and a null return is
  a missing package, not a typo.
- `Image` also carries a non-serialised `m_OverrideSprite` field beside the serialised `m_Sprite`.
  Animate `m_Sprite`, and keep code from setting `overrideSprite` at runtime: that is a second
  writer to the same visual — if something must, check in play mode which one you see.
- A `RectTransform` sizes the graphic, so PPU does nothing here. Frames of unequal aspect stretch
  to the rect instead of scaling — `preserveAspect` (a `bool` property on `Image`) letterboxes
  them instead. Equal-canvas frames make the question moot, which is one
  more reason the input contract in §1 is not negotiable.
- The animated object needs an `Animator`, and `path` is relative to it. On a UI hierarchy that is
  usually a parent panel with the `Image` some levels down, so `path` is a real path, not `""`.

`resources/SheetToAnimationClip.cs` implements all of the above end to end — a folder of frame PNGs
or one sliced texture, an output clip, fps, loop flag, target type, optional controller and optional
end event.
