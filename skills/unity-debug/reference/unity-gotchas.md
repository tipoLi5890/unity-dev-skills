# Gotchas that have actually cost a session

Check these before theorising. Each one has been paid for.

## Colliders and physics

1. **A child trigger fires the PARENT's handlers.** A child collider with no Rigidbody of its own
   shares the parent's, so its `OnTriggerEnter` is delivered to the parent's MonoBehaviours. A
   100×100×100 trigger on a post-process "Effect" child made the player's handler fire for every
   obstacle within ~50 units → instant game over. Disable trigger colliders on child objects.

2. **A duplicate instance at identical coordinates reads as an invisible wall.** Two overlapping
   bodies jam: lateral nudges work, forward is blocked. Disable the ghost in its own `Awake`,
   before physics, and identify it by a unique component rather than by name.

3. **Solid vs trigger decides which callback fires.** A solid collider delivers
   `OnCollisionEnter`, not `OnTriggerEnter`. Handle both when the prefab is not under your control.

4. **`GetComponentsInChildren<T>()` returns empty for an inactive hierarchy.** Pass
   `includeInactive: true` — pooled objects are configured while still deactivated, and without the
   flag the setup silently does nothing.

5. **A `SkinnedMeshRenderer`'s bounds are its BIND POSE.** The bind pose is a T-pose, so
   `Renderer.bounds` on a character is **arm-span wide**. Deriving a gameplay hitbox from it gives a
   box nearly as wide as the character is tall — against 1.3-unit lane spacing that meant runners
   were hit by hazards they had already dodged past. Author humanoid hitboxes as explicit
   constants (~0.5 × 1.0 × 0.6) and regression-test the world-space width against the lane pitch.

6. **Collider values are LOCAL.** They scale with the root, so divide the intended world size by
   the root scale, or the box silently changes size whenever the prefab is normalised.

7. **`[RequireComponent(typeof(Animator))]` can break an imported character.** It adds an empty
   Animator to the prefab ROOT, and `GetComponent<Animator>()` then finds that one instead of the
   model child's — every `SetTrigger` logs "Animator is not playing an AnimatorController". Search
   for the first Animator that actually has a controller bound.

## Scene and prefab data

8. **Prefab-instance colliders do not appear when grepping scene YAML.** Instances inherit from the
   prefab, so grepping `SampleScene.unity` for `BoxCollider` misses them. Check the `.prefab` too.

9. **Orphaned serialized fields are harmless.** After renaming a public field the old value stays
   in the YAML and is ignored; new fields take their code default until re-saved.

10. **A singleton MonoBehaviour on the wrong GameObject fails silently.** A camera-shake component
    living on an empty manager shook *its own* transform — invisible. Resolve the real target.

11. **Layer 0 is excluded by many culling masks.** Anything created at runtime
    (`CreatePrimitive`, glTFast imports) lands on layer 0 and is then visible in the Scene view and
    invisible in Game. A scene object can sit on the wrong layer for months without anyone noticing
    it was never drawn. Set the layer recursively to match the prefab root.

## Rendering

12. **`error CS0246: GUID` from com.unity.shadergraph is benign** import-time noise. Do not chase.

13. **`m_MSAA: 1` in the render-pipeline asset means MSAA is OFF**, and `aniso: 1` in a texture
    `.meta` means no anisotropic filtering. Together they produce severe shimmer on any large
    surface seen at a grazing angle. See `motion-and-timing.md` for the diagnosis and the fix.

14. **Linear colour space changes what your constants mean.** `GUI.color`, scrim alphas and tint
    multipliers are all treated as linear values in a linear-space project, so an sRGB hex typed in
    literally renders several stops too light. Covered in depth by the `unity-game-ui` skill.

15. **`nPOTScale` defaults to ToNearest.** A non-power-of-two texture is silently rescaled on
    import — a 1920×1081 image became 2048×1024 and its aspect changed from 1.776 to 2.00, which
    looks exactly like a UI cropping bug. Set `npotScale: None` for UI art.

16. **A named settings asset may be a decoy.** Quality levels with `renderPipeline: none` fall
    through to `GraphicsSettings.m_CustomRenderPipeline`, so `Mobile_RPAsset.asset` can be dormant
    while a default-named asset in the project root is the one in force. Resolve the guid before
    editing anything. Covered in `harness-trust.md`.

17. **Post-processing arrives from TWO places, and one ignores layers.** Scene volumes are filtered
    by the camera's `m_VolumeLayerMask`; the pipeline's global default profile
    (`UniversalRenderPipelineGlobalSettings.m_DefaultVolumeProfile`) applies to **every** camera
    regardless. A camera whose mask is layer 0 never applies a scene volume sitting on layer 3 —
    its Bloom/Vignette/Tonemapping silently does nothing — while a template's global default can
    carry dozens of active components, including Unity's own `CopyPasteTestComponent` and
    `TestVolume`. URP bakes the colour-grading ones among them into one 32³ LUT: neutral grading
    still routes every pixel through a lookup table, and a driver that samples it without
    interpolation collapses smooth gradients into 32 steps. If nothing wants post-processing, turn
    it off at the camera — and verify the claim by diffing screenshots with it on and off.

18. **On macOS, `[Assert] m_Shader == nullptr` is the machine, not the game.** When the Editor's own
    UI Toolkit cannot compile its shader variants — e.g. on a Mac whose Xcode lacks the Metal
    Toolchain component — the console fills with that
    assert and the test framework turns it into red PlayMode tests, while every state assertion in
    those same tests holds. The second symptom is visual: **anything needing the uGUI clipping
    shader variant (`RectMask2D`, `Mask`) screenshots as solid cyan with blank contents.** The
    project-side survival kit is `LogAssert.ignoreFailingMessages = true` in `[SetUp]` (read the
    cost of that in `test-verdicts.md`) and avoiding masks in new UI; the real resolution is a
    machine-provisioning matter, not a project one. Related noise: exception greps on the run log
    return `UnityEngine.UIElements.UIR.RenderChainCommand:ExecuteNonDrawMesh` and
    `UIRenderDevice:EvaluateChain` frames from the same cause — filter `UnityEngine.UIElements` out
    before chasing them.

## Editor scripts that generate assets

19. **`EditorUtility.CopySerialized` copies the source's empty `name` over the target's.** An
    idempotent generator that refreshes an asset in place without changing its GUID
    (`var fresh = CreateInstance<T>(); … EditorUtility.CopySerialized(fresh, existing);`) leaves
    every regenerated `.asset` with `m_Name:` blank, because `CreateInstance<T>()` has no name.
    It reaches users as a label that reads empty — a report like "the setting will not switch" when
    the switch works and only its name is blank. Set the name on both sides
    (`existing.name = Path.GetFileNameWithoutExtension(path);`). Cheap detector across a folder:
    `grep -c "m_Name: $" <generated asset folder>/*.asset | grep -v ":0"`.

20. **`EditorSceneManager.NewScene` invalidates ScriptableObjects that are not on disk yet.** A batch
    `-executeMethod` scaffolder that creates assets and then builds scenes throws
    `MissingReferenceException` mid-run. Order it: `AssetDatabase.SaveAssets()` before creating any
    scene, and after that re-acquire every reference with `AssetDatabase.LoadAssetAtPath` rather
    than holding objects across the scene operation. Same family as a stale `TextureImporter` after
    `SaveAndReimport()`.

## Project settings

21. **A runtime `Screen.autorotate*` assignment overrides ProjectSettings.** Locking an orientation
    needs both changed, or the runtime call quietly re-enables what the asset forbids.
