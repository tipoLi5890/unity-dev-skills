# Live2D Cubism — from a layered PSD to a model in Unity

This is the optional route. Route A (`reference/auto-rig-2d.md`) is automatic and free. Cubism
gives the head turns, the eye and mouth shapes and the hair physics an artist builds in
Cubism Editor, where every ArtMesh, deformer and parameter is made by hand. These skills
automate the two ends of that work: the PSD going in, and the model coming out in Unity.

## 1. Licences: Live2D's own, bought or agreed with Live2D

- **Cubism Editor** comes in FREE and PRO editions. FREE caps a model at 100 ArtMeshes and one
  texture of up to 2048 px. Buy PRO from Live2D for production work.
- **Cubism SDK for Unity** is downloaded by each user from Live2D's download page, under the
  Live2D Proprietary Software License Agreement (Cubism Core) and the Live2D Open Software
  License Agreement (the framework). Never commit the SDK or Cubism Core to a repo, a package
  or a template, and never redistribute either. Each developer installs their own copy.
- **Releasing a product** that uses the SDK: Live2D's SDK licence page exempts individuals and
  small-scale businesses, as Live2D defines them, from the licence agreement and the fee
  (expandable applications excepted). Everyone else signs a publication licence. It is needed
  only at release, not during development, and is completed at least a month before release;
  expandable applications are reviewed first. Read www.live2d.com/en/sdk/license/ before
  release. If the project needs a licence, buy it: the SDK and the Editor are the work of a
  company that lives on those licences.

## 2. The PSD that goes in

`comfyui-asset-generation` writes a Cubism-ready PSD from the same split that feeds route A
(its layered-2D reference). It follows Live2D's Editor manual (docs.live2d.com, *Cubism Editor
manual*):

| Rule | Manual page |
|---|---|
| A **PSD**, 8-bit RGB, sRGB. PSB support is not documented, so the PSD is the safe choice | precautions-for-psd-data |
| Layer masks are unsupported (apply them first); blend modes outside Cubism's list become Normal; layer names are unique | precautions-for-psd-data |
| Each layer becomes one ArtMesh with a 1 px margin; hidden layers and groups are imported too | psd-import |
| Separate the parts finely, and draw what is hidden early, on its own layer | divide-the-material |
| A re-import maps layers **by name**: a rename breaks the mapping | psd-re-import |

What the generated PSD holds:
- **Face:** a blank face (no eyes, brows or mouth); eye white, iris and lash per side; brows,
  complete under the fringe; nose; a mouth line; and the inside of the mouth, **hidden**.
- **Body:** the route-A body layers, in folders, staying under FREE's 100-ArtMesh cap.
- **Gates:** the composite against the source, unique names, no masks or effects.

Split the eyes on the 1024 px head crop, not on the full canvas, where an eye is too few
pixels for a clean white and iris. Draw the eye white whole under the iris.

## 3. In Cubism Editor (a person's work)

1. Import the PSD.
2. Use automatic mesh generation and check it on the eyes and the mouth.
3. Create the standard parameters (§5). The Editor's automatic face deformer generation gives
   the head turn a start.
4. Set up physics for the hair, hood strings and bag strap.
5. Export for embedded use: `.moc3`, `.model3.json`, `.physics3.json` when there is physics,
   and the texture folder, all in one folder.

None of this runs headless: the Editor has no command-line mode. Its External
Integration API is a WebSocket on a running Editor. It needs a per-user permission and reads
parameters; it does not build models. Do not promise automation past the PSD.

## 4. Into Unity

Follow docs.live2d.com, *Cubism SDK tutorials*, getting-started:

1. Download *Cubism SDK for Unity* from Live2D's download page. It ships as a
   `.unitypackage`. The GitHub repository has no libraries, so it is not enough to show a
   model.
2. In a 2D project, drag the package into the Project view, then restart Unity: the native
   libraries load only at startup. A `DllNotFoundException` means they did not load; check
   the platform settings under `Assets/Live2D/Cubism/Plugins/<platform>`.
3. Drag the exported model folder into the Project view, as a whole folder. The importer reads
   the `.model3.json` and generates a prefab. Place the prefab in a scene; it does not show
   until the scene runs.
4. Since Cubism 4 SDK for Unity R2, models import as *Original Workflow*, which adds its own
   components. The switch is *Live2D > Cubism > Original Workflow > Should Import As Original
   Workflow*.

Check the supported Unity versions on Live2D's SDK page for the release you download; the
tutorial pages name older Editors.

Set a parameter from a script in `LateUpdate`, after animation. A value set in `Update` is
overwritten.

```csharp
// needs the Cubism SDK installed; Live2D.Cubism.Core / Live2D.Cubism.Framework
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using UnityEngine;

public sealed class CourierLook : MonoBehaviour
{
    CubismParameter _angleX;
    public float lookX;                       // -30..30, from gameplay

    void Start() => _angleX = this.FindCubismModel().Parameters.FindById("ParamAngleX");

    void LateUpdate() => _angleX?.BlendToValue(CubismParameterBlendMode.Override, lookX);
}
```

| Effect | Components (Cubism SDK for Unity) | Where |
|---|---|---|
| Automatic blink | `CubismEyeBlinkController` (Blend Mode Override), `CubismAutoEyeBlinkInput` | Model root |
| | `CubismEyeBlinkParameter` | The `ParamEyeLOpen` and `ParamEyeROpen` objects under `Parameters/`. A model with the standard IDs may get these on import |
| Lip sync from audio | `CubismMouthController` (Override), `CubismAudioMouthInput` (its Audio Input set to an `AudioSource`) | Model root |
| | `CubismMouthParameter` | The `ParamMouthOpenY` object |
| Drawing | `CubismRenderController` | Added to the generated prefab |
| Physics from `.physics3.json` | `CubismPhysicsController`; check the SDK's own manual for the setup | Model root |

## 5. Standard parameter IDs

From docs.live2d.com, *Cubism Editor manual*, standard-parameter-list. Use these IDs: the SDK
may set up blinking on import for a model that has them, and every tutorial assumes them.

| ID | Range | Drives |
|---|---|---|
| `ParamAngleX` / `ParamAngleY` / `ParamAngleZ` | −30 … 30 | Head turn, nod, tilt |
| `ParamEyeLOpen` / `ParamEyeROpen` | 0 … 1 | Eyelids (blink) |
| `ParamMouthOpenY` | 0 … 1 | Mouth opening (lip sync) |
| `ParamBreath` | 0 … 1 | Breathing |
| `ParamBodyAngleX` / `ParamBodyAngleY` / `ParamBodyAngleZ` | −10 … 10 | Body turn and lean |

## 6. Checks

- The repo and its packages hold no `Live2D` folder and no Cubism Core library: `git ls-files |
  grep -i cubism` lists only your own scripts and model exports.
- Every model in the project has an export folder with `.moc3`, `.model3.json` and its
  textures, and a generated prefab beside it.
- The model's `Parameters/` children include the standard IDs it uses, and blink and lip sync
  move on screen when the scene runs.
- A person on the team has read the current licence terms and recorded which one applies to
  the release.

## What stays manual

- **In Cubism Editor:** ArtMeshes, deformers, parameters, physics, motions and expressions.
- **In Unity:** gameplay mapping, such as which state sets which parameter, and a capture
  looked at by a person.
- **When the art changes:** re-importing the PSD into Cubism Editor maps by name. Keep layer
  names frozen once modelling starts, as route A does.
