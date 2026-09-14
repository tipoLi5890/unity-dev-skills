# Which render pipeline is actually in force

> Part of the `unity-render-urp` skill. Everything in §1 of `SKILL.md` — Volumes, HDR,
> `renderPostProcessing`, renderer features — assumes URP is the pipeline the project renders
> with. That assumption is worth thirty seconds to check, because when it is wrong nothing
> reports it.

## The trap

A project created from a URP template ships `Assets/Settings/UniversalRP.asset` and a renderer
asset next to it. **Those files are inert unless something points at them.** If the assignment
was never made, or was cleared by a merge, the project renders with the built-in pipeline while
looking exactly like a URP project on disk: the assets are there, the package is in
`manifest.json`, the URP inspectors all open and let you change values.

A project in this state shows, in `ProjectSettings/GraphicsSettings.asset`,

```yaml
  m_CustomRenderPipeline: {fileID: 0}
```

and no quality level in `QualitySettings.asset` carrying a `renderPipeline` override: the URP
assets are dormant. `Assets/Settings/UniversalRP.asset` and `Assets/Settings/Renderer2D.asset`
sit there unused, and the project builds and ships on the built-in pipeline without anyone
noticing.

Nothing surfaces this in a flat-coloured uGUI project — there is no 2D light, no Shader Graph
material, no post-processing, so there is no pixel that differs. It surfaces later, as *"I
changed the setting and nothing happened"*, on the day someone adds the first effect. Resolve
the pipeline **before** you start debugging why an effect will not appear.

## Where the assignment can live

Two places it can be assigned, plus the setting that decides which of them a given build
consults. A tier override wins over the project default:

| Place | YAML | Meaning |
|---|---|---|
| Project default | `ProjectSettings/GraphicsSettings.asset` → `m_CustomRenderPipeline` | `{fileID: 0}` = no SRP = **built-in**. Otherwise a `guid:` naming an RP asset. |
| Quality tier override | `ProjectSettings/QualitySettings.asset` → a level's `renderPipeline: {fileID: 11400000, guid: …}` | Overrides the project default **for that tier only**. |
| Which tier a platform boots into | `QualitySettings.asset` → `m_PerPlatformDefaultQuality:` | e.g. `Android: 2` = the third level in the list. A tier override only bites on the platforms that select that tier. |

So "there is a URP asset in `QualitySettings`" and "the Android build uses URP" are different
claims. Check the mapping, not just the presence.

## Resolver — text only, no Editor needed

Run from the project root. Requires text serialization
(`ProjectSettings/EditorSettings.asset` → `m_SerializationMode: 2`, Force Text — what a
version-controlled project should be on anyway; a binary or mixed project returns nothing from
these greps, which is why the script aborts there rather than reporting built-in, and needs the
Editor-side check below instead).

```bash
#!/usr/bin/env bash
# Resolve the render pipeline in force, rather than assuming it from a file's presence.
set -uo pipefail
GS=ProjectSettings/GraphicsSettings.asset
QS=ProjectSettings/QualitySettings.asset

# Refuse rather than answer. Run from the wrong directory, or against a binary/mixed-serialized
# project, and every grep below comes back empty -- which reads identically to "no SRP assigned".
for f in "$GS" "$QS"; do
  [[ -f "$f" ]] || { echo "ABORT: $f not found -- run this from the project root"; exit 2; }
done
grep -q 'm_CustomRenderPipeline:' "$GS" \
  || { echo "ABORT: no m_CustomRenderPipeline line in $GS -- not text-serialized; use the Editor-side check"; exit 2; }

RP_GUID="$(grep -m1 'm_CustomRenderPipeline:' "$GS" | sed -n 's/.*guid: \([a-f0-9]*\).*/\1/p')"
if [[ -n "$RP_GUID" ]]; then
  # A guid means nothing until a .meta claims it: resolve guid -> asset path.
  RP_META="$(grep -rl "^guid: $RP_GUID" --include='*.meta' Assets Packages 2>/dev/null | head -1)"
  if [[ -n "$RP_META" ]]; then
    echo "project default pipeline: ${RP_META%.meta}"
  else
    echo "WARNING: GraphicsSettings points at guid $RP_GUID but no .meta matches it (missing asset)"
  fi
else
  echo "project default pipeline: NONE — built-in renderer"
fi

# `grep -c` exits 1 when the count is zero, so assign on failure; never `|| echo 0` (that
# appends a second line and every later comparison fails).
OVERRIDES="$(grep -c 'renderPipeline: {fileID: 11400000' "$QS" 2>/dev/null)" || OVERRIDES=0
LEVELS="$(grep -c '^    name:' "$QS" 2>/dev/null)" || LEVELS=0
if [[ "$OVERRIDES" == "0" && -z "$RP_GUID" ]]; then
  echo "no quality level ($LEVELS levels) overrides that — every RP asset in this project is DORMANT"
elif [[ "$OVERRIDES" == "0" ]]; then
  echo "no quality level ($LEVELS levels) overrides it — the project default above is what every tier uses"
else
  echo "$OVERRIDES of $LEVELS quality levels override the pipeline; tier per platform:"
  grep -n 'm_PerPlatformDefaultQuality' -A12 "$QS" | sed 's/^/    /'
fi
```

On such a project the resolver prints:

```
project default pipeline: NONE — built-in renderer
no quality level (6 levels) overrides that — every RP asset in this project is DORMANT
```

Run it as one section of a build doctor, so every build prints which pipeline it was made with
instead of inheriting an assumption.

## Reading it back from inside the Editor

The text check answers "what is assigned". If you also want "what is live in this session",
`UnityEngine.Rendering.GraphicsSettings` exposes the assignment and `QualitySettings` the tier
override — but **the exact member names on your version are worth enumerating rather than
recalling**, in the same spirit as §2 of `SKILL.md`:

```csharp
foreach (var p in typeof(UnityEngine.Rendering.GraphicsSettings).GetProperties())
    UnityEngine.Debug.Log(p.Name + " : " + p.PropertyType.Name);
```

Print what the dump gives you before quoting a member name in a bug report.

## After it resolves to URP

Resolving the pipeline is the first indirection, not the last. The URP asset then names its
renderer(s):

```yaml
  m_RendererDataList:
  - {fileID: 11400000, guid: 424799608f7334c24bf367e4bbfa7f9a, type: 2}   # an example guid; yours differs
  m_DefaultRendererIndex: 0
```

so "URP is active" still does not tell you **which renderer** — 2D vs Universal, and which
renderer features are on it. Resolve that guid the same way (find the `.meta` that declares it)
when a renderer feature is the thing that is not appearing, and note that a camera can override
the default renderer index per-camera.

## What this does not cover

Whether URP is the *right* choice for the project, migrating a built-in project to URP
(materials, shaders and lighting all move — that one is `unity-urp-migration`), and HDRP.
Assigning the asset is a project-settings
change with real consequences for every existing material — resolve first, report what you
found, and let the owner decide before you assign anything.
