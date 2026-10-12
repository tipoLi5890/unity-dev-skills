# Cinemachine 2.x ↔ 3.x — one rig, two vocabularies

> Part of the `unity-camera` skill. `SKILL.md` §0 says to read the lock before naming a
> component; this file is the table that turns one major's recipe into the other's. Every recipe
> in this skill is written in 3.x names. On a 2.x project, translate through here and keep the
> recipe.

## Which major is this project on

```bash
python3 - <<'EOF'
import json
lock = json.load(open("Packages/packages-lock.json"))["dependencies"]
print(lock.get("com.unity.cinemachine", {}).get("version", "not installed"))
EOF
```

| The lock says | The project speaks | Do |
|---|---|---|
| `2.x` | `CinemachineVirtualCamera`, `m_` fields, namespace `Cinemachine` | Use the left column below, or move to 3.x deliberately |
| `3.x` | `CinemachineCamera`, plain fields, namespace `Unity.Cinemachine` | Use the right column; the shipped C# compiles as is |
| not installed | — | Add it with an explicit version: `"com.unity.cinemachine": "3.1.7"` in `Packages/manifest.json` |

An add with no version on Unity 6 resolves 2.10.7. A 3.x project therefore always has a version
written in its manifest; a manifest line that someone "tidied" back to a bare add silently
changes every component name in the project. Read the lock again after any package change.

Moving an existing 2.x project to 3.x is a migration with its own upgrade tool, not a rename.
Decide it once, at the start of a milestone; never half way through a camera bug.

## Assemblies and namespaces

| | 2.x | 3.x |
|---|---|---|
| Runtime namespace | `Cinemachine` | `Unity.Cinemachine` |
| Other namespaces | `Cinemachine.Utility`, `Cinemachine.PostFX` | `Unity.Cinemachine.TargetTracking` |
| Runtime assembly (asmdef reference) | `Cinemachine` | `Unity.Cinemachine` |
| Timeline track and shot | `CinemachineTrack`, `CinemachineShot` in the global namespace | The same class names in `Unity.Cinemachine` |

An asmdef that references the wrong assembly name fails with `CS0246` on every Cinemachine type
at once. That error pattern means "wrong major", not "package missing".

## The camera and its targets

| | 2.x | 3.x |
|---|---|---|
| The camera component | `CinemachineVirtualCamera` | `CinemachineCamera` |
| Follow target | `m_Follow` | `Target.TrackingTarget` |
| Look-at target | `m_LookAt` | `Target.LookAtTarget`, used only while `Target.CustomLookAtTarget` is true |
| `Follow` / `LookAt` properties | Present | Present. `Follow` writes `TrackingTarget`; setting `LookAt` also switches `CustomLookAtTarget` on |
| Priority | `int m_Priority`, default 10 | `PrioritySettings Priority`, default 0, with implicit conversion to and from `int` |
| Lens | `m_Lens` | `Lens` |
| Blend hint | `m_Transitions.m_BlendHint`, `m_Transitions.m_InheritPosition` | `BlendHint`, a flags enum that includes `InheritPosition` |
| Standby update | `m_StandbyUpdate` | `StandbyUpdate` |
| Which Brain sees it | The camera object's layer against the output camera's culling mask | `OutputChannel` on the camera, `ChannelMask` on the Brain |

In 3.x one tracking target serves both position and rotation until a look-at target is set. That
is the whole lock-on recipe: the runner stays the tracking target and the sentry becomes the
look-at target.

`Priority.Value` reads 0 while `Priority.Enabled` is false, whatever number is stored. Assigning
an `int` to `Priority` sets `Enabled` as well, so assign the whole thing and not the inner field
through the inspector's debug view.

`LensSettings` keeps its field names across both majors: `FieldOfView`, `OrthographicSize`,
`NearClipPlane`, `FarClipPlane`, `Dutch`, `ModeOverride`. The lens is orthographic when the
output `Camera` is, unless `ModeOverride` says otherwise.

## Body and Aim became Position Control and Rotation Control

In 2.x the procedural components live on a hidden child object and are added with
`AddCinemachineComponent<T>()` and read with `GetCinemachineComponent<T>()` on the virtual
camera. In 3.x they are ordinary components on the camera's own GameObject: `AddComponent<T>()`
and `GetComponent<T>()`. The pipeline stages keep their names in code (`CinemachineCore.Stage.Body`,
`.Aim`, `.Noise`, `.Finalize`); the inspector calls them Position Control and Rotation Control.

| Job | 2.x | 3.x |
|---|---|---|
| Keep the target at a screen position (2D follow, top-down) | `CinemachineFramingTransposer` | `CinemachinePositionComposer` |
| Fixed offset from the target | `CinemachineTransposer` | `CinemachineFollow` |
| Orbit the target under player control | `CinemachineOrbitalTransposer`, or the `CinemachineFreeLook` camera | `CinemachineOrbitalFollow` |
| Over-the-shoulder rig | `Cinemachine3rdPersonFollow` | `CinemachineThirdPersonFollow` |
| Aim offset correction for that rig | `Cinemachine3rdPersonAim` | `CinemachineThirdPersonAim` |
| Rotate to frame the look-at target | `CinemachineComposer` | `CinemachineRotationComposer` |
| Free look from input (first person) | `CinemachinePOV` | `CinemachinePanTilt` |
| Match the target's rotation | `CinemachineSameAsFollowTarget` | `CinemachineRotateWithFollowTarget` |
| Rail | `CinemachineTrackedDolly` + `CinemachinePath` / `CinemachineSmoothPath` | `CinemachineSplineDolly` + a `SplineContainer` |
| Hard lock, hard look | `CinemachineHardLockToTarget`, `CinemachineHardLookAt` | The same names |
| Noise | `CinemachineBasicMultiChannelPerlin` (`m_NoiseProfile`, `m_AmplitudeGain`, `m_FrequencyGain`) | The same name (`NoiseProfile`, `AmplitudeGain`, `FrequencyGain`) |

Field names inside the composers changed shape, not only prefix:

| | 2.x `CinemachineFramingTransposer` | 3.x `CinemachinePositionComposer` |
|---|---|---|
| Screen position | `m_ScreenX`, `m_ScreenY`, 0.5 is the centre | `Composition.ScreenPosition`, **0 is the centre**, ±0.5 is the edge |
| Dead zone | `m_DeadZoneWidth`, `m_DeadZoneHeight` | `Composition.DeadZone.Enabled` and `.Size` |
| Outer limit | `m_SoftZoneWidth`, `m_SoftZoneHeight` | `Composition.HardLimits.Enabled` and `.Size` |
| Damping | `m_XDamping`, `m_YDamping`, `m_ZDamping` | `Damping`, a `Vector3` |
| Look-ahead | `m_LookaheadTime`, `m_LookaheadSmoothing`, `m_LookaheadIgnoreY` | `Lookahead.Enabled`, `.Time`, `.Smoothing`, `.IgnoreY` |
| Offset | `m_TrackedObjectOffset` | `TargetOffset` |
| Distance | `m_CameraDistance` | `CameraDistance` |

A screen position copied from a 2.x project lands half a screen off in 3.x: subtract 0.5.

## Extensions

| Job | 2.x | 3.x |
|---|---|---|
| Keep a 2D camera inside a shape | `CinemachineConfiner2D` (`m_BoundingShape2D`, `m_Damping`) | `CinemachineConfiner2D` (`BoundingShape2D`, `Damping`, `SlowingDistance`) |
| Rebuild its cache | `InvalidateCache()` | `InvalidateBoundingShapeCache()` for the shape, `InvalidateLensCache()` for a lens change |
| Keep a 3D camera inside a volume | `CinemachineConfiner` | `CinemachineConfiner3D` |
| Keep the target visible | `CinemachineCollider` | `CinemachineDeoccluder` |
| Keep the camera out of geometry | — | `CinemachineDecollider` |
| Frame a group | Group settings inside `CinemachineFramingTransposer`, `CinemachineGroupComposer` | `CinemachineGroupFraming` extension |
| Pixel-perfect orthographic size | `CinemachinePixelPerfect` | `CinemachinePixelPerfect` |
| Shake | `CinemachineImpulseSource`, `CinemachineImpulseListener` (`m_` fields) | The same names, plain fields |
| Shake on a non-Cinemachine object | `CinemachineIndependentImpulseListener` | `CinemachineExternalImpulseListener` |
| Offset, recompose, follow zoom | `CinemachineCameraOffset`, `CinemachineRecomposer`, `CinemachineFollowZoom` | The same names |

An extension registers itself in `Awake` by looking for a camera component **on its own
GameObject**. On any other object it is never called and nothing says so.

Two compile guards decide whether an extension exists at all. Read them as requirements:
`CinemachineConfiner2D` needs the built-in 2D physics module; `CinemachineDeoccluder`,
`CinemachineDecollider`, `CinemachineConfiner3D` and `CinemachineThirdPersonAim` need the built-in
3D physics module. A project that disabled the module loses the type, and the error names the
type, not the module.

## Managers

| Job | 2.x | 3.x |
|---|---|---|
| A fixed sequence of cameras | `CinemachineBlendListCamera` | `CinemachineSequencerCamera` |
| Animator state picks the camera | `CinemachineStateDrivenCamera` | The same name |
| Best unobstructed shot | `CinemachineClearShot` | The same name |
| Weighted mix | `CinemachineMixingCamera` | The same name |
| Several targets as one | `CinemachineTargetGroup` (`m_Targets`) | The same name (`Targets`) |

## The Brain

| | 2.x | 3.x |
|---|---|---|
| Update method | `m_UpdateMethod`, enum `CinemachineBrain.UpdateMethod` | `UpdateMethod`, enum `CinemachineBrain.UpdateMethods` |
| Its values | `FixedUpdate`, `LateUpdate`, `SmartUpdate`, `ManualUpdate` | The same four; the default is `SmartUpdate` in both |
| Blend update method | `m_BlendUpdateMethod`, enum `BrainUpdateMethod` | `BlendUpdateMethod`, enum `BrainUpdateMethods` |
| Its values | `FixedUpdate`, `LateUpdate` | The same two; the default is `LateUpdate` in both |
| Ignore time scale | `m_IgnoreTimeScale` | `IgnoreTimeScale` |
| Default blend | `m_DefaultBlend` | `DefaultBlend` |
| Per-pair blends | `m_CustomBlends` | `CustomBlends` |
| Blend definition | `m_Style` of enum `Style`, `m_Time` | `Style` of enum `Styles`, `Time` |
| Camera-cut and activation events | `m_CameraCutEvent`, `m_CameraActivatedEvent` on the Brain | `CinemachineCore.CameraActivatedEvent` (its parameter carries `IsCut`), or the `CinemachineBrainEvents` component |
| Target teleported | `CinemachineCore.Instance.OnTargetObjectWarped(target, delta)` | `CinemachineCore.OnTargetObjectWarped(target, delta)`, static |
| Forget the previous frame | `vcam.PreviousStateIsValid = false` | The same, or `CinemachineCore.ResetCameraState()` for every camera |

The enum type names differ by one letter (`UpdateMethod` → `UpdateMethods`), so code written for
one major fails on the other with `CS0426`, and the fix is the plural.

## Input

| | 2.x | 3.x |
|---|---|---|
| Axis type | `AxisState` (`m_XAxis`, `m_YAxis`, `m_HorizontalAxis`, `m_VerticalAxis`) | `InputAxis` (`HorizontalAxis`, `VerticalAxis`, `RadialAxis`, `PanAxis`, `TiltAxis`) |
| Feeding it from the Input System | `CinemachineInputProvider` beside the camera | `CinemachineInputAxisController` beside the camera |
| Without either | `CinemachineCore.GetInputAxis` delegate | Write `axis.Value` from your own code |

## 2.x names that still compile on 3.x

3.x ships the old classes in `Runtime/Deprecated/`, under the new namespace, each marked
`[Obsolete]` with the replacement in the message. They exist so an upgraded scene still loads.
They are not a second API.

| Still present in 3.x, `[Obsolete]` | The message points to |
|---|---|
| `CinemachineVirtualCamera` | `CinemachineCamera` |
| `CinemachineFreeLook` | The FreeLook camera preset built from `CinemachineCamera` |
| `CinemachineFramingTransposer` | `CinemachinePositionComposer` |
| `CinemachineTransposer` | `CinemachineFollow` |
| `CinemachineOrbitalTransposer` | `CinemachineOrbitalFollow` |
| `CinemachineComposer` | `CinemachineRotationComposer` |
| `CinemachinePOV` | `CinemachinePanTilt` |
| `CinemachineSameAsFollowTarget` | `CinemachineRotateWithFollowTarget` |
| `Cinemachine3rdPersonFollow` | `CinemachineThirdPersonFollow` |
| `CinemachineCollider` | `CinemachineDeoccluder` |
| `CinemachineConfiner` | `CinemachineConfiner2D` or `CinemachineConfiner3D` |
| `CinemachineTrackedDolly`, `CinemachineDollyCart` | `CinemachineSplineDolly`, `CinemachineSplineCart` |
| `CinemachinePath`, `CinemachineSmoothPath` | `SplineContainer` |
| `CinemachineGroupComposer` | `CinemachineRotationComposer` with `CinemachineGroupFraming` |
| `CinemachineInputProvider` | `CinemachineInputAxisController` |
| `AxisState` | `InputAxis` |
| `CinemachineConfiner2D.InvalidateCache()` | `InvalidateBoundingShapeCache()` |

Gone from 3.x entirely: `Cinemachine3rdPersonAim`, `CinemachineBlendListCamera`,
`CinemachineIndependentImpulseListener`, and the `CinemachineNewVirtualCamera` /
`CinemachineNewFreeLook` experiments.

A 3.x project with `CS0618` warnings naming any left-column type is running on the compatibility
layer. New rigs use the right column; mixing both on one camera object is the state the upgrade
tool exists to remove.

## Check a name before writing it

```bash
ls Library/PackageCache | grep cinemachine          # the resolved folder
grep -rl "class CinemachinePositionComposer" Library/PackageCache/com.unity.cinemachine@*/Runtime
grep -rn "Obsolete" Library/PackageCache/com.unity.cinemachine@*/Runtime/Deprecated | head
```

The package source is on disk in every project. A component name that the grep does not find is
not in this major, whatever a tutorial says.

## Related skills

Adding and pinning packages: `unity-new-project` → `reference/package-selection.md`. The
`CS0246` and `CS0618` families and how to read a compile log headless: `unity-debug`.
