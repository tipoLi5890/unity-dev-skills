# Lighting and probes after the pipeline changes

> Part of the `unity-urp-migration` skill. Baked data from the old pipeline is not history.
> It is live data: lightmaps keep being sampled and the lighting data asset keeps being loaded
> until something clears them. A scene that blows out after the switch is usually being lit by
> a bake that no longer matches the pipeline rendering it.

## Three states, and what each one needs as evidence

| State | What it means | Evidence |
|---|---|---|
| **Preserved reference** | The old lighting data, lightmaps and probe files are still assigned and unchanged | Nothing was run — say so plainly |
| **Partial** | A URP lighting settings asset exists or is assigned, but the old bake output is still active | The scene references the new `.lighting`, and the old data is still there |
| **Rebaked / refreshed** | A bake or probe render completed under the final URP setup | Changed lighting data, changed probe files, and a capture taken after saving and reloading |

Nothing moves a report up this table except saved state. "Probes refreshed" said from intent is
the single most common false claim in this phase.

## Diagnosing a stale bake

Symptom: the representative scene is blown out or badly mismatched, and the post-processing
wiring already checks out.

Test: clear the baked data and look again. **If the overexposure goes away, the old lightmaps
were live data**, not scenery. Keep them as rollback evidence, clear them, and rebake — but
rebake *afterwards*, under the final URP asset, renderer, Volume and tier settings. Baking
against a half-finished setup means baking twice.

`Lightmapping.Clear()` and `ClearLightingDataAsset()` change the scene, so they are not done
until the scene is saved and re-read. Until then the clear is a claim like any other.

## Assigning lighting settings so the scene keeps them

The active lighting settings reference is **scene state**. The sequence that actually persists:

1. Create or load the `.lighting` asset.
2. `Lightmapping.lightingSettings = settings`.
3. `EditorUtility.SetDirty` on the settings asset, then `AssetDatabase.SaveAssets()`.
4. `EditorSceneManager.MarkSceneDirty(scene)` then `EditorSceneManager.SaveScene(scene)`.
5. Read the saved scene text back: an `m_LightingSettings:` line naming the new GUID, and
   `m_LightingDataAsset: {fileID: 0}` if the old bake was cleared.

Step 4 is the one that gets skipped, and `SaveAssets()` alone looks like it worked because the
asset really did get written — just not the reference to it.

> **Read the settings with `Lightmapping.TryGetLightingSettings(out var s)`, not the plain
> getter.** The getter throws when the scene has no settings asset assigned, which is precisely
> the state of a project about to be migrated. Confirm the member on your version; an inspection
> pass that throws on the projects it exists for is worse than no inspection pass.

## Baking

`Lightmapping.BakeAsync()` starts the work and returns. Poll `Lightmapping.isRunning` while the
turn's budget lasts. **Still running at the end of the turn is a phase boundary**, reported as
`bake=running`, resumed next turn. It is not a failure, and it is not a rebaked scene.

## Reflection probes

Two separate questions that get answered as one:

**Is the pipeline allowed to blend and box-project probes?** `reflectionProbeBlending` and
`reflectionProbeBoxProjection` on the URP asset are get-only, so the write goes through
`SerializedObject` and the private fields `m_ReflectionProbeBlending` and
`m_ReflectionProbeBoxProjection`. Those names carry no compatibility guarantee, so the write
fails loudly:

- Field missing → report `status=blocked reason=field-not-found` and ask for the two boxes to be
  ticked on the URP asset under Lighting → Reflection Probes. Never report success.
- Write present → `ApplyModifiedProperties` → `SetDirty` → `SaveAssets` → **read the asset text**
  and look for `m_ReflectionProbeBlending: 1`. A read of the in-memory property cannot tell
  "applied" from "written", and only one of those survives the session.
- No `m_ReflectionProbeBlending:` line in the file at all → throw. The project is not on Force
  Text serialization, so nothing in this phase can be read back, and that is worth stopping for.

**Were the probes actually re-rendered?** A different question with a different answer.
`Lightmapping.BakeAllReflectionProbesSnapshots()` returns a bool — confirm it on your version —
and that bool is a claim. The evidence is the probe `.exr` files changing timestamp. Unchanged
files mean the probes were preserved, not refreshed, however the call returned.

That count is written to `Library/UrpMigration/probe-refresh.txt`, beside the material snapshot
and for the same reason: a later read-only pass and the Phase 4 gate have to be able to report
what was observed without re-running anything, and a field in memory does not survive the domain
reload a bake causes. Clearing the bake deletes the file, because it no longer describes
anything that is on disk. With no file, the report reads `probesRefreshed=unproven` — and a
scene with no reflection probes in it owes no such evidence at all.

## Balancing exposure — wiring before values

When the capture is too dark, too bright or too contrasty, fix the plumbing first:

1. The renderer's `postProcessData` is not null.
2. The camera's `renderPostProcessing` is true.
3. The Volume's layer is inside the camera's `volumeLayerMask`.
4. The Volume's weight, priority and layer are what you think they are, and it has a profile
   with live overrides.

All four are `unity-render-urp` §1, and three of them default to a state that renders nothing.

Only then tune, in bounded steps, starting from the source grade's values rather than from
extremes: `ColorAdjustments.postExposure`, contrast, saturation, the tonemapper, bloom
threshold and intensity, ambient sky colour and intensity.

> **If the scene needs extreme values to be visible, the bake is partial.** Exposure that is
> compensating for missing bounce light is a diagnostic, not a result — say the lighting is
> partial rather than saving a +3 exposure and calling it parity.

## 2D lighting

Sprites only respond to 2D lights when their materials are on the lit sprite family
(`Sprite-Lit-Default` and its relatives). Dragging a fresh sprite into the scene gets that
automatically, which is why "the new one works" is not evidence that the project's existing
sprite materials were upgraded. Check the materials the project already has.

## Worked example — the courier run

The gate scene bakes its lane markings and the sentry's cast shadow. After the pipeline switch
the lanes read as white bands with no edge.

- Post-processing wiring checks out and one stack is running, so double post-processing is
  ruled out first.
- `ClearStaleBake()`, save, reopen: the bands resolve. The old lightmaps were live data.
- A `.lighting` asset is created and assigned, the scene saved, and the saved file re-read —
  `settings=<guid> lightingData=0`.
- `EnableProbeSettings()` on the tier asset returns `probeBlending=1 probeBoxProjection=1`, read
  out of the asset text.
- `StartBake()`, then `bake=running` at the end of the turn.

Reported: `Partial migration`, one open item (the bake), probes recorded as
`probesRefreshed=unproven` because no `.exr` timestamp has moved yet.
