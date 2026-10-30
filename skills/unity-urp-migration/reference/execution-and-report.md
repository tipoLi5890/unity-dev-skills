# Execution path and report wording

Moved out of SKILL.md §4–§5; same numbering. The phases themselves: [`reference/migration-phases.md`](migration-phases.md).

## 4. Execution path

Getting to a connected Editor, the command catalog, and telling an absent Editor from one in
Safe Mode is `unity-cli`. Every script here goes under `Assets/Editor/`, compiles, and is then
called with one line:

```bash
unity command eval --code 'return UnityDev.UrpMigration.MigrationAudit.Run();'
```

`unity command` defaults to a 30-second timeout. A package install or a bake outrunning it is a
**phase boundary**, not a reason to raise the timeout. Each script returns a single `[URP-MIG]`
line assembled from re-read saved state, and logs the same line so it also lands in the console.

> **Floor trap.** The `com.unity.pipeline` package's manifest allows an Editor line older than
> the one it compiles on: it uses build-callback types that the earlier line never shipped, so
> the resolve succeeds and the compilation right after it does not. The symptom is misleading — `unity status`
> shows no row **and no error**, so it reads as a CLI problem. The check is the Editor log:
>
> ```bash
> grep -c 'error CS0246' <Editor.log>
> ```
>
> with hits naming `IPreprocessBuildWithContext` or `BuildCallbackContext`. That is an Editor
> too old for the package, not a broken CLI. Confirm the floor on your version by reading the
> package changelog. **This bites here more than anywhere else**: a project still on the
> built-in pipeline is often on an older Editor by the same history.

## 5. Report wording

- **`Complete`** only when every Phase 4 gate is true. Not one of them, not most of them.
- **`Partial migration`** when the pipeline and materials landed but post-processing
  persistence, legacy disablement, the bake, the probes or a saved-state check is still open.
- **`Manual follow-up`** names the items precisely: the old stack's screen-space reflections, a
  specific custom shader, a `GrabPass`, a replacement shader, a package-owned shader.

> **A report whose next steps include "rebake lighting" or "refresh probes" is partial by
> definition.** Those are the phase, not a suggestion after it. Do not pair them with
> "complete", and do not open the answer with "successfully migrated" while any gate is false.
