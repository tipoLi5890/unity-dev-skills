# The pre-flight as one eval call

> Part of the `unity-render-urp` skill. This is §1 of the skill turned into a single block you
> paste into the Editor's `eval`: five checks in order, a report string back, and no mutation of
> anything. Run it **before** touching a Volume parameter — four of the five switches default to
> off or to a narrow default and none of them warns. Connecting to a live Editor is
> `unity-debug` → `reference/editor-control.md`.

What `eval` accepts is a block of statements rather than a source file, so the code below carries
no `using` directives and spells every type out in full. The findings come back as the returned
string rather than as console noise. It reads state and returns; nothing in it writes.

## The block

```csharp
// Five checks, in the order of §1. Check 1 is a hard stop — nothing below it means anything on a
// project that is not rendering URP — so it returns early. The rest accumulate.
var findings = new System.Collections.Generic.List<string>();

// 1 · Which pipeline is actually in force, resolved rather than inferred from the files.
var active = UnityEngine.Rendering.GraphicsSettings.currentRenderPipeline;
var urp = active as UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset;
if (urp == null)
{
    return "1 STOP · active pipeline is "
        + (active == null ? "the built-in renderer" : active.GetType().Name)
        + " — a URP asset in Assets/ is dormant until Graphics settings or a quality tier "
        + "points at it. Nothing below this line applies.";
}
findings.Add("1 ok · URP active, asset=" + urp.name);

// 2 · HDR. Tonemapping needs it; in SDR a Bloom threshold of 1 selects nothing.
findings.Add(urp.supportsHDR
    ? "2 ok · HDR on"
    : "2 WARN · HDR off — Tonemapping contributes nothing and Bloom needs threshold below 1");

// 3 · The camera. renderPostProcessing defaults to false, and Overlay cameras composite onto a
//     Base camera rather than running the stack themselves.
var viewCam = UnityEngine.Camera.main;
UnityEngine.Rendering.Universal.UniversalAdditionalCameraData camExtra = null;
if (viewCam == null)
{
    findings.Add("3 STOP · no enabled camera tagged MainCamera — point the rest of this at the "
        + "camera you actually render with");
}
else if (!viewCam.TryGetComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>(out camExtra))
{
    findings.Add("3 STOP · camera '" + viewCam.name + "' has no UniversalAdditionalCameraData");
}
else
{
    findings.Add((camExtra.renderPostProcessing ? "3 ok · " : "3 FAIL · ")
        + "camera=" + viewCam.name
        + " renderPostProcessing=" + camExtra.renderPostProcessing
        + " renderType=" + camExtra.renderType
        + " volumeLayerMask=" + camExtra.volumeLayerMask.value
        + " antialiasing=" + camExtra.antialiasing);
}

// 4 and 5 · Every Volume in the loaded scenes: is it enabled, is its layer inside the mask the
//           camera actually uses, does it have a profile, and does any parameter override anything.
var sceneVolumes = UnityEngine.Object.FindObjectsByType<UnityEngine.Rendering.Volume>(
    UnityEngine.FindObjectsInactive.Include, UnityEngine.FindObjectsSortMode.None);
if (sceneVolumes.Length == 0) { findings.Add("4 FAIL · no Volume component in the loaded scenes"); }

foreach (var v in sceneVolumes)
{
    var faults = new System.Collections.Generic.List<string>();
    if (!v.isActiveAndEnabled) { faults.Add("component or GameObject disabled"); }
    if (camExtra != null && (camExtra.volumeLayerMask.value & (1 << v.gameObject.layer)) == 0)
    {
        faults.Add("layer " + v.gameObject.layer + " outside the camera's volumeLayerMask");
    }

    // sharedProfile, never profile: reading `profile` clones the asset into an instance, which is
    // a mutation dressed up as a read.
    var profile = v.sharedProfile;
    if (profile == null) { faults.Add("no profile assigned"); }

    var components = 0;
    var overriding = 0;
    if (profile != null)
    {
        components = profile.components.Count;
        foreach (var c in profile.components)
        {
            // `parameters` is the flat list the Volume system walks. Confirm on your version that
            // it is public and enumerable before relying on this count in a report.
            foreach (var p in c.parameters) { if (p.overrideState) { overriding++; break; } }
        }
        if (components == 0) { faults.Add("profile holds no overrides"); }
        else if (overriding == 0) { faults.Add("every override has overrideState=false"); }
    }

    findings.Add((faults.Count == 0 ? "4-5 ok · " : "4-5 FAIL · ")
        + "Volume '" + v.name + "' isGlobal=" + v.isGlobal
        + " weight=" + v.weight + " priority=" + v.priority
        + " components=" + components + " contributing=" + overriding
        + (faults.Count == 0 ? "" : " — " + string.Join("; ", faults)));
}

return string.Join("\n", findings);
```

## Reading the result

- **`1 STOP`** ends the conversation about parameters. The project renders built-in, and every
  other line would be describing an inert asset → `reference/resolve-active-pipeline.md`.
- **`3 FAIL`** with `renderType=Overlay` is not a camera-data bug: only the Base camera (or the
  last Overlay in the stack) carries post-processing.
- **`every override has overrideState=false`** is the scripting error the skill warns about
  twice, and it is the one that reads as correct in the inspector.
- **All five clean and still nothing on screen** — you are looking at the Scene view, which has
  its own post-processing toggle, or at a screenshot taken before the change. Take the screenshot
  yourself: `unity-debug`.

## The check this block deliberately does not make

The renderer's **PostProcessData asset must not be null**, or the post-process pass does not
exist at all — but the field lives on the renderer data asset and its accessibility has moved
between URP versions. Read it off the renderer asset in the Inspector, or confirm on your version
that the field is public before adding it here. A `null` reference exception from the pre-flight
is worse than a missing line in the report.

## When it comes back with a compile error rather than a report

That is `eval` rejecting the block, not URP rejecting the setup — the error codes and what each
one means are at the top of [`volume-templates.md`](volume-templates.md).
