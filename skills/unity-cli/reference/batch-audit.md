# Running an Editor audit headless — `BatchAudit.Run`

> Part of the `unity-cli` skill. `-executeMethod` calls only a `static void` method with no
> parameters. The audits in the other skills return their report as a string from a method such
> as `KitAudit.Audit("Assets/Kit")`, behind a menu item, so `-executeMethod` cannot call them.
> `resources/Editor/BatchAudit.cs` is the one entry that can.

## The command

```bash
# UNITY = the project's Editor binary. Synchronous: -quit is harmless, the method exits itself.
"$UNITY" -batchmode -projectPath . -logFile Logs/kit-audit.log \
  -executeMethod UnityDev.Cli.BatchAudit.Run \
  -audit KitAudit -folder Assets/Kit -grid 2 -out Logs/kit-audit.json
echo "exit $?"
```

- `-audit <Type>` or `<Type.Method>`. The type is found by name at run time, so `BatchAudit.cs`
  compiles in a project that holds none of the audits. A simple name that matches two types is
  refused with both full names listed. Pass the full name in that case.
- Each parameter of the audit method is a flag of the same name: `-folder`, `-root`, `-grid`,
  `-wallThickness`. A parameter typed as an asset (`AnimatorController`) takes an asset path and is
  loaded as that type. A parameter you leave out takes its default value.
- `-scene Assets/Levels/route.unity` opens that scene first. Use it for the audits that read the
  open scene.
- `-out file.json` writes the report to that file. Without `-out`, the report goes to the log after
  `[BATCH-AUDIT] `.

## The exit code is the report's own verdict

BatchAudit reads the report's top-level field, in this order: `pass` (a `gate/1` report), then
`ok`, then `verdict` (`"green"` / `"failed"`). It never reads a nested field.

| Exit | Meaning |
|---|---|
| `0` | the verdict passed (or `-census` was given and the report has no verdict) |
| `2` | the verdict failed, or the report has no verdict field and `-census` was not given |
| `3` | nothing was verified: the scene or an asset did not load, or the audit threw or returned nothing |
| `1` | refused: a usage error, an unknown or ambiguous `-audit`, or a required parameter not given |

The Editor binary also exits `1` on a compile error in any assembly (`reference/editor-binary.md`
§1). Run `grep -E 'error CS' Logs/kit-audit.log` before you read a `1` as a usage error.

**A report with no verdict never passes.** Some audits count things and do not judge them. They
are censuses, not gates. Pass `-census` to say you only want the JSON, and then read it.

## Which audits carry a verdict

| Audit (skill) | Call | Verdict |
|---|---|---|
| `KitAudit` (`unity-3d-level`) | `-audit KitAudit -folder Assets/Kit [-grid 2 -wallThickness 0.2 -heightStep 1]` | `ok` |
| `PrefabOverrideAudit` (`unity-3d-level`) | `-audit PrefabOverrideAudit -scene …` | `ok` |
| `Physics2DAudit` (`unity-physics-2d`) | `-audit Physics2DAudit -scene …` | `ok` |
| `LightingAudit` (`unity-lighting`) | `-audit LightingAudit -scene …` | `ok` |
| `ModelAudit` (`unity-3d-models`) | its own `-executeMethod ModelAudit.AuditBatch`, set through `MODEL_AUDIT_*` environment variables | `verdict` |
| `SceneCostAudit` (`unity-scene-optimisation`) | `-audit SceneCostAudit -scene … -census` | none (census) |
| `SortingAudit` (`unity-2d-rendering`) | `-audit SortingAudit -scene … -census` | none: read `ties[]` |
| `SkinningAudit` (`unity-2d-animation`) | `-audit SkinningAudit -root Assets/Art/Runner -census` | none: read `issues` |
| `AnimatorParamAudit` (`unity-animation`) | `-audit AnimatorParamAudit -controller Assets/Animations/Runner.controller -census` | none: read each parameter's `verdict` |
| `UrpMaterialValidation` (`unity-render-urp`) | `-audit UrpMaterialValidation -folder Assets/Art -census` | none |
| `MigrationAudit` (`unity-urp-migration`) | `-audit UnityDev.UrpMigration.MigrationAudit -census` | none (inventory) |

The builders (`SpriteStateGraphBuilder`, `TilemapLayerStackBuilder`, `CameraRigBuilder`,
`CharacterAnimatorBuilder`, `OcclusionBake`) are not audits. Most of them take a scene object
(a `Grid`, a `Transform`) or change the project, so run them from the menu or from
`unity command eval`.

## In CI

```bash
"$UNITY" -batchmode -projectPath . -logFile Logs/lighting.log \
  -executeMethod UnityDev.Cli.BatchAudit.Run \
  -audit LightingAudit -scene Assets/Levels/route.unity -out Logs/lighting.json
code=$?
case $code in
  0) ;;                                            # passed
  2) echo "lighting audit failed: Logs/lighting.json"; exit 2 ;;
  *) grep -E 'error CS|\[BATCH-AUDIT\]' Logs/lighting.log | head; exit 3 ;;
esac
```

One Editor per project at a time (`reference/editor-binary.md` §6). To run several audits, put
them one after another in one job. Do not run them in parallel against the same project.
