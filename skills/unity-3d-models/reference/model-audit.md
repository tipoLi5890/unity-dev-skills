# Model audit and first-import policy

> Part of the `unity-3d-models` skill. Two Editor scripts in `resources/Editor/`:
> `ModelAudit.cs` reads what each imported model costs and checks it against its class's budget
> row; `ModelImportPolicy.cs` sets a folder's import settings on a model's first import. Worked
> setting: the courier run's `pickup` class.

The numbers come from the class's row of the `3D budgets` table — its columns, its default rows
and how a person picks them: `reference/budgets.md`. This file is how they are checked after
import. The row used below, as it would sit in a project's `ART_DIRECTION.md` (e.g. values; the
same table is the test fixture for `inspect_glb.py --budgets`):

### 3D budgets

| class | preset | target_tris | ceiling_tris | target_tex_px | ceiling_tex_px | max_materials | max_mb | calibrated | note |
|---|---|---|---|---|---|---|---|---|---|
| pickup | Medium | 7900 | 12000 | 1024 | 2048 | 2 | 3 | 2026-10-12 | e.g. values, ladder run on `ParcelToken` |

A column the project leaves out is not set, the same as `-`.

## 1. Run the audit

Drop `ModelAudit.cs` into any Editor folder. It changes nothing: no import setting, no asset.

| Way in | What it does |
|---|---|
| `Tools/Unity Dev/3D Models/Audit Folder` | The selected folder, or one picked in a dialog. Report only: no budget, no gate |
| `ModelAudit.Audit(folder, …)` | Returns the JSON and logs it; writes it to `outPath` when given |
| `-executeMethod ModelAudit.AuditBatch` | The same, numbers from `MODEL_AUDIT_*`; exits with the verdict |

```csharp
string report = ModelAudit.Audit("Assets/Models/Pickup");                     // report only
string gated  = ModelAudit.Audit("Assets/Models/Pickup", 7900, 12000, 1024, 2048, 2, 0, 3f,
                                 "/tmp/model-audit/pickup.json");
//  target tris, ceiling tris, target tex px, ceiling tex px, max materials, max bones, max MB
```

```bash
UNITY="/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity"
OUT=/tmp/model-audit; mkdir -p "$OUT"            # never the project's Temp/: deleted on exit
MODEL_AUDIT_FOLDER=Assets/Models/Pickup MODEL_AUDIT_OUT="$OUT/pickup.json" \
MODEL_AUDIT_TARGET_TRIS=7900 MODEL_AUDIT_CEILING_TRIS=12000 MODEL_AUDIT_MAX_MATERIALS=2 \
MODEL_AUDIT_TARGET_TEX_PX=1024 MODEL_AUDIT_CEILING_TEX_PX=2048 MODEL_AUDIT_MAX_MB=3 \
"$UNITY" -batchmode -nographics -projectPath . -logFile "$OUT/pickup.log" \
         -executeMethod ModelAudit.AuditBatch
echo "exit=$?"
grep -o '\[MODEL-AUDIT\] {.*' "$OUT/pickup.log"
```

| Variable | `3D budgets` column | Kind |
|---|---|---|
| `MODEL_AUDIT_TARGET_TRIS` | `target_tris` | warning past target × 1.25 |
| `MODEL_AUDIT_CEILING_TRIS` | `ceiling_tris` | gate |
| `MODEL_AUDIT_TARGET_TEX_PX` | `target_tex_px` | warning past target × 1.25 |
| `MODEL_AUDIT_CEILING_TEX_PX` | `ceiling_tex_px` | gate |
| `MODEL_AUDIT_MAX_MATERIALS` | `max_materials` | gate |
| `MODEL_AUDIT_MAX_BONES` | `max_bones` | gate |
| `MODEL_AUDIT_MAX_MB` | `max_mb` | gate |
| `MODEL_AUDIT_FOLDER` | — | default `Assets` |
| `MODEL_AUDIT_OUT` | — | the JSON is also written here — never under `Temp/` |

An empty cell or `-` in the table is `0`, and `0` is not checked. A value that is not a number
is a harness error, not a zero.

| Exit | Means |
|---|---|
| `0` | Every model passed every gate that was set |
| `2` | At least one gate failed — a verdict, not a crash |
| `3` | Harness: the folder is not in the project, a variable is not a number, the out file was not written |
| `1` | Unity's own: a compile error in any assembly stopped the method — `unity-cli` → `reference/editor-binary.md` |

The method ends the Editor itself, so the line needs no `-quit`. Take the verdict from the JSON;
the exit code only says which branch to read.

## 2. What each row reads, and the gates

Every `.fbx .glb .gltf .prefab` under the folder, recursively, is one row.

| Field | Read from |
|---|---|
| `tris` | LOD0 triangles over the `MeshFilter` and `SkinnedMeshRenderer` meshes, from the index count — readable with Read/Write off; lower LOD levels are not added |
| `materials` / `slots` | Distinct materials on the renderers / LOD0 material slots in total |
| `texPx` / `texPath` | Longest side of the largest `Texture2D` the model uses — on its materials, in its dependencies, embedded as sub-assets — **as imported**: after Max Size, on the active build target. A 4096 source under Max Size 1024 reads 1024; the source file's own size is `inspect_glb.py` on the GLB before import |
| `bones` | The most bones one skinned mesh is bound to; its bind poses when Optimize Game Objects stripped the transforms |
| `mb` | The asset file on disk, MB of 2^20 bytes |
| `animationType`, `humanBones`, `clips`, `import` | The `ModelImporter`; empty or `null` for a prefab or a glTF |

| Gate `name` | `value` | `limit` | Fails when |
|---|---|---|---|
| `ceiling_tris` | `tris` | `ceiling_tris` | `value > limit` |
| `ceiling_tex_px` | `texPx` | `ceiling_tex_px` | `value > limit` |
| `max_materials` | `materials` | `max_materials` | `value > limit` |
| `max_bones` | `bones` | `max_bones` | `value > limit` |
| `max_mb` | `mb` | `max_mb` | `value > limit` |

- **A gate is written only when its limit is above zero.** No gates and no warnings is what a
  class with no budget yet looks like: the audit adds the top-level warning `no budget given` and
  reports green. It never fails a model against a number nobody set.
- **A target is never a gate.** Past `target × 1.25` the row gets a `warnings` entry and keeps
  its verdict. A person picked the target from the ladder; the ceiling is the only hard stop.
- **Unread is not green.** A `.glb` in a project without glTFast loads as no GameObject: the row
  says `"loaded": false`, and a `ceiling_tris`, `max_materials` or `max_bones` gate on it fails
  with `"value": null`.

## 3. The JSON contract

One line in the log, prefixed `[MODEL-AUDIT] `, and the same object in `MODEL_AUDIT_OUT`. One row
of a run on `Assets/Models/Pickup` with the row above, wrapped (e.g. output, numbers invented):

```json
{"schema":1,"tool":"ModelAudit","unity":"<editor version>","folder":"Assets/Models/Pickup",
 "budget":{"target_tris":7900,"ceiling_tris":12000,"target_tex_px":1024,"ceiling_tex_px":2048,
           "max_materials":2,"max_bones":0,"max_mb":3},
 "models":[
  {"path":"Assets/Models/Pickup/ParcelToken/ParcelToken.fbx","importer":"ModelImporter","loaded":true,
   "tris":13100,"lodLevels":0,"materials":1,"slots":1,"texPx":1024,
   "texPath":"Assets/Models/Pickup/ParcelToken/ParcelToken_BaseColor.png","bones":0,
   "humanBones":0,"mb":1.204,"animationType":"None","clips":[],
   "import":{"globalScale":1,"meshCompression":"Medium","readWrite":false,"importBlendShapes":false,
             "materialImportMode":"ImportStandard","optimizeGameObjects":false},
   "gates":[{"name":"ceiling_tris","value":13100,"limit":12000,"pass":false},
            {"name":"ceiling_tex_px","value":1024,"limit":2048,"pass":true},
            {"name":"max_materials","value":1,"limit":2,"pass":true},
            {"name":"max_mb","value":1.204,"limit":3,"pass":true}],
   "warnings":["tris 13100 is over target 7900 x 1.25"],"verdict":"failed",
   "record":{"kind":"mesh","files":[{"path":"Assets/Models/Pickup/ParcelToken/ParcelToken.fbx","role":"shipped"}],
             "tool":{"skill":"unity-3d-models","script":"ModelAudit.cs"},
             "gates":[{"name":"ceiling_tris","value":13100,"limit":12000,"pass":false},
                      {"name":"ceiling_tex_px","value":1024,"limit":2048,"pass":true},
                      {"name":"max_materials","value":1,"limit":2,"pass":true},
                      {"name":"max_mb","value":1.204,"limit":3,"pass":true}],
             "warnings":["tris 13100 is over target 7900 x 1.25"],"verdict":"failed"}}],
 "count":1,"warnings":[],"verdict":"failed"}
```

- `schema` is `1`. Keys may be added; a reader ignores the ones it does not know.
- Paths are project-relative with forward slashes (`Assets/…`).
- Each gate is `{name, value, limit, pass}`, the ledger's gate shape; `warnings` is a list of
  strings; a row's `verdict` is `green` or `failed`.
- The top-level `verdict` is `failed` when any row failed, `harness` with an `error` string when
  the run itself could not happen, else `green`. `count` is the rows; `models: []` with a
  `no … under` warning is an empty folder.

**Into the ledger** (skill `art-asset-registry`): each row carries `record`, its partial ledger
record — the model file as `shipped`, the tool, and the row's `gates`, `warnings` and `verdict`.
Hand each row's record to the registry's `ingest`, adding what the audit cannot know:

```bash
python3 -c 'import json,sys; [print(json.dumps({"record": m["record"]})) for m in json.load(open(sys.argv[1]))["models"]]' \
  /tmp/model-audit/pickup.json | while read -r rec; do
  printf '%s\n' "$rec" > /tmp/model-audit/row.json
  python3 <art-asset-registry>/scripts/registry.py ingest --json /tmp/model-audit/row.json \
          --class pickup --source generated --write
done
```

## 4. The first-import policy

`ModelImportPolicy.cs` is an `AssetPostprocessor`. A folder opts in with a file named
`.modelpolicy.json`; Unity skips names that start with a dot, so the file is not an asset and
gets no `.meta`. The courier run's parcel token ships with a compressed mesh and no CPU copy:

`Assets/Models/Pickup/ParcelToken/.modelpolicy.json`

```json
{
  "meshCompression": "medium",
  "readWriteEnabled": false,
  "importBlendShapes": false,
  "materialImportMode": "importStandard"
}
```

| Key | Values | Sets |
|---|---|---|
| `importBlendShapes` | `true` / `false` | `ModelImporter.importBlendShapes` |
| `globalScale` | a number > 0 | `globalScale` |
| `animationType` | `none` / `generic` / `humanoid` | `animationType` |
| `materialImportMode` | `none` / `importStandard` | `materialImportMode` |
| `meshCompression` | `off` / `low` / `medium` / `high` | `meshCompression` |
| `readWriteEnabled` | `true` / `false` | `isReadable` |

Each model it touches logs one line, and the audit's `import` block reads the result back; the
second line is what a file with a bad `globalScale` adds:

```
[MODEL-POLICY] Assets/Models/Pickup/ParcelToken/ParcelToken.fbx applied importBlendShapes=false materialImportMode=importStandard
               meshCompression=medium readWriteEnabled=false (Assets/Models/Pickup/ParcelToken/.modelpolicy.json)
[MODEL-POLICY] WARN Assets/Models/Pickup/ParcelToken/.modelpolicy.json: globalScale is not a number > 0; skipped
```

- **First import only.** It acts when the model arrives without a `.meta`
  (`importSettingsMissing`). A reimport, a hand edit in the Inspector, or a model copied in with
  its `.meta` is left alone, and it never forces a reimport. Changing the policy file changes the
  next new model, not the ones already there.
- **Per folder.** The file applies to its own folder, not to subfolders.
- **The file is the only input.** Unknown keys are ignored; an invalid value logs
  `[MODEL-POLICY] WARN …` and is skipped; a file that does not parse is skipped whole.
- **Do not delete a `.meta` to re-trigger it.** A new `.meta` is a new GUID, and every prefab and
  scene that referenced the model loses it. Set an imported model's values in its Inspector.
- **FBX, OBJ and the other `ModelImporter` formats only.** A `.glb` imported by glTFast never
  reaches `OnPreprocessModel`.

## 5. Limits

- The audit reads the importer and the built meshes, not runtime state: a LOD the game
  switches, a material instanced or a texture swapped at runtime, a mip the streamer drops —
  none of it shows.
- `texPx` is the size imported for the active build target. Switch to the target platform
  first; a per-platform Max Size override changes the number.
- The policy runs only on a model's first import; everything after it is the Inspector's.
