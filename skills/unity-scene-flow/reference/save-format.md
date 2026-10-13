# The save format — a versioned document of facts, written so a crash cannot lose it

> Part of the `unity-scene-flow` skill. `resources/SaveStore.cs` is the file: the data classes,
> the migration chain and the atomic write. `scripts/save_check.py` reads a file from outside
> Unity; `templates/SaveRoundTripTests.cs` is the EditMode gate. Worked setting: the **gate
> room** — which room, where the runner stands, which pickups are gone, whether the gate is open.

## 1. What a save is

A save is the answer to one question: **what would have to be true for a freshly loaded scene to
look like the one the player left?** It is a list of facts. It is never a picture of the scene.

```json
{
    "version": 2,
    "savedAtUnix": 1700000100,
    "scene": "Assets/Scenes/GateRoom.unity",
    "player": {
        "lane": 2,
        "position": { "x": 1.2999999523162842, "y": 0.0, "z": 12.5 },
        "checkpoint": "5f0c2a9e41d34b7c9a6e0d1b2c3f4a55"
    },
    "flags": [
        { "id": "8c1d7e2f90a94c0fb3a6d5e4f3c2b1a0", "value": 1 },
        { "id": "sentry-alerts", "value": 3 }
    ]
}
```

| Field | Type | Rule |
|---|---|---|
| `version` | int, from 1 | First field written, first field read. Stamped by `SaveStore`, never by the caller |
| `savedAtUnix` | long, seconds UTC | **Passed in** to `Write`. The store never reads a clock, so the same data gives the same bytes |
| `scene` | string | The build path `SceneLoader.Load` takes (`reference/additive-scenes.md`) |
| `player` | object | Where to put the runner: lane, position, last checkpoint's id |
| `flags` | list of `{id, value}` | World facts by persistent id: taken, opened, thrown, counted. Absent means 0 |

`flags` is a list and not a dictionary because `JsonUtility` cannot write a dictionary (§5).
`SaveData.GetFlag(id)`, `HasFlag(id)` and `SetFlag(id, value)` hide the search.

## 2. What never goes in a save

| Never | Because | Store instead |
|---|---|---|
| A reference to a `GameObject`, component or asset | `JsonUtility` writes it as `{"instanceID": 12345}` — a number that names an object in the session that wrote it and nothing in the next | A `PersistentId` string |
| An instance id or entity id | The same number under another name | The same |
| A hierarchy path or sibling index | Moves when someone tidies the scene | The same |
| A build index | Shifts when a scene is added above it | The scene's build path |
| An asset GUID or a prefab name | Ties the save to the project's files; a renamed prefab orphans it | An id from a table the game owns (`reference/scriptable-objects.md`) |
| Anything derivable | Health bar width, the gate's rotation, a sentry's position on a fixed patrol | The fact it derives from: `gate-switch = 1` |
| Settings | Volume, bindings and language belong to the device, not to the playthrough | A separate file; bindings → `unity-input` → `reference/rebinding-and-devices.md` |
| `DateTime.Now` read inside the writer | Makes every write different and every test flaky | The caller's clock, as a parameter |

`resources/PersistentId.cs` supplies the ids: a GUID string generated in the Editor when the
component is added, regenerated when the object is duplicated, empty on the prefab asset so no
two instances start equal. A design-time id typed by hand (`sentry-alerts`) is fine for a fact
that belongs to no single object.

Run the outside check on a real file from a real session:

```bash
python3 scripts/save_check.py "$HOME/Library/Application Support/<Company>/<Product>/save.json" --indent 2
```

```json
{"file": "…/save.json", "bytes": 412, "ok": false, "version": 2, "schema": "known", "findings": [
  {"rule": "session-only-value", "path": "gate.instanceID", "detail": "this key holds a value from the session that wrote the file: store a persistent id"},
  {"rule": "duplicate-flag-id", "path": "flags[4].id", "detail": "'pickup-a' is also flags[1]: which value wins depends on read order"}]}
```

Rules it reports: `not-json` (cut off or damaged), `not-an-object`, `no-version`, `bad-version`,
`unknown-version`, `missing-key`, `wrong-type`, `session-only-value`, `empty-flag-id`,
`duplicate-flag-id`. Exit 1 on any finding. Its per-version key table sits at the top of the
script; a new version adds a block there on the day it adds a migration.

## 3. The write that cannot lose the save

Writing straight over `save.json` has a window — after the file is truncated, before the new
bytes are on the disk — in which a crash or a dead battery leaves an empty file where the
progress was. Three files close it:

| File | Is |
|---|---|
| `save.json` | The save |
| `save.json.bak` | The save before it |
| `save.json.tmp` | The write in progress. Never read |

```
1. serialise                      → text in memory
2. write save.json.tmp, Flush(true)   the bytes are on the disk, not in the OS cache
3. read save.json.tmp back, parse     a file that does not parse stops here; save.json is untouched
4. File.Replace(tmp, save, bak)       new → save.json, old save.json → save.json.bak
```

| Crash after step | On disk | `Read` returns |
|---|---|---|
| 1, or during 2 | Old `save.json`, a partial `.tmp` | The old save |
| 2 or 3 | Old `save.json`, a whole `.tmp` | The old save |
| 4 | New `save.json`, old one as `.bak` | The new save |

Three details in `SaveStore.Write` carry the guarantee:

- **`Flush(true)`.** A rename of a file whose bytes are still in the cache can survive a power
  cut as a zero-length or zero-filled file with the right name.
- **A damaged `save.json` is never moved into `.bak`.** If the main file does not parse when the
  write starts, it is deleted and the new file takes its place; the backup — the only good copy —
  stays. Without this the first write after a corruption destroys the recovery.
- **Where `File.Replace` is not available**, the fallback is copy main → backup, delete main,
  move temporary → main. After each of the three steps either the main file or the backup is
  whole.

`Read` tries the main file, then the backup, and says which it used:

```csharp
SaveReadResult r = Bootstrap.Get<SaveStore>().Read();
if (r.tooNew)                  ShowUpdateRequired();          // do not offer "new game" over it
else if (!r.Found)             StartFresh();                  // r.problem == "no save file"
else {
    if (r.source == SaveSource.Backup) Debug.LogWarning("[SAVE] recovered from backup: " + r.problem);
    Apply(r.data);
}
```

A file is damaged when it is empty, zero-filled, does not open and close as one balanced JSON
object, or has no `version`. The balance is counted by `SaveStore` itself, so detection does not
depend on how the JSON parser words its complaint.

**A file from a newer build is not damaged.** `Read` sets `tooNew` and returns no data — it does
*not* fall back to the backup — and `Write` throws rather than replace it. An older build
installed over a newer save must not eat it.

Call `Write` from the main thread at a moment that can afford a few milliseconds: a checkpoint,
a room change, `Backgrounded`. Never every frame, and never from `OnDestroy`.

## 4. Versions and the migration chain

The version is one integer. It goes up when the shape changes: a field removed, renamed, moved
or re-typed. **Adding a field with a sensible default needs no bump** — `JsonUtility` leaves a
field the file lacks at the class's initialiser.

```
file (v1) ──V1ToV2──► JSON (v2) ──V2ToV3──► JSON (v3) ──► SaveData
```

```csharp
public static class SaveMigrations
{
    // Steps[n] turns the JSON of version n into the JSON of version n + 1.
    static readonly Func<string, string>[] Steps = { null, V1ToV2 };
    public static string ToCurrent(string json, int fromVersion);
}
```

The documented change in this file, v1 → v2:

| v1 | v2 |
|---|---|
| `lane` (int) | `player.lane` |
| `distance` (float) | `player.position.z`; `player.position.x` is `(lane − 1) × 1.3`, `y` is 0 |
| `collected` (array of ids) | One `flags` entry per id, value 1 |
| — | `player.checkpoint`, empty |

To add version 3:

1. Copy the current `SaveData` to a class named `SaveDataV2`, mark it frozen, and never edit it
   again. It describes files on players' disks.
2. Change `SaveData`, set `CurrentVersion` to 3.
3. Write `V2ToV3(string json)`: deserialise as `SaveDataV2`, build a `SaveData`, serialise. Add it
   to `Steps`. Touch no earlier step.
4. Add a version 2 fixture to `templates/SaveRoundTripTests.cs` — the JSON **typed out as a
   string**, never produced by the current classes — and assert every moved field.
5. Add the version's block to `scripts/save_check.py`.

Each step reads one frozen shape and writes the next, so a version 1 file reaches version 5 by
four small functions that were each tested once and never changed. A migration that reads "the
current class" silently changes meaning with every later edit.

A migrated save is in memory only. The next `Write` puts it on disk at the current version, with
the old-version file as its backup — one step back survives in its own format.

## 5. `JsonUtility` limits

It is in the engine, allocates little and needs no package. It is also narrow:

| Limit | Consequence | Do |
|---|---|---|
| No `Dictionary` | Written as nothing at all, silently | A `List` of `{id, value}` |
| No top-level array or primitive | `ToJson(list)` gives `{}` | Wrap it in a class |
| Fields only — public, or `[SerializeField]`; no properties | A property-backed value is not saved | Public fields on `[Serializable]` plain classes |
| No polymorphism | A `List<Base>` saves the base's fields only | One concrete type per list, with a kind field |
| No `null` for a nested class | Read back as a default-constructed object | Use an empty string or a `has` flag to mean absent |
| Unknown keys are dropped, missing keys default | No error for a typo in a hand-edited file | The outside check, `save_check.py` |
| A `UnityEngine.Object` field becomes `{"instanceID": n}` | §2 | Never put one in a save class |
| Lives in `UnityEngine` | Unavailable in an assembly with no engine references | Keep the save classes in an engine-referencing assembly, or hand-write the JSON there → `unity-new-project` |

`long` round-trips. `float` is written with enough digits to read back the same value, which is
why 1.3 appears as 1.2999999523162842. Enums are written as their integer: renaming a value is
free, reordering the enum is a format change. Write no enum whose order is not frozen.

Another serialiser changes none of the above about the format: version, facts, ids, atomic
write, migrations, fixtures.

## 6. Where the file lives

`Application.persistentDataPath` — per user, per product, writable on every platform, and kept
across updates. It is derived from the company and product names: renaming either after release
moves the directory and orphans every save.

| Platform | Resolves to |
|---|---|
| macOS Editor and player | `~/Library/Application Support/<Company>/<Product>/` |
| Windows | `%USERPROFILE%\AppData\LocalLow\<Company>\<Product>\` |
| Android | The app's own files directory; removed on uninstall |
| iOS | The app's Documents directory; included in device backups |
| Web | A virtual file system backed by browser storage: a write is not durable until the page has synchronised it, and the browser may evict it. Treat a web save as a cache of a cloud save |

Print it once rather than guess: `Debug.Log(Application.persistentDataPath);`.

`PlayerPrefs` is for a handful of settings. It has no versioning, no atomic replace and, on
Windows, lives in the registry.

**Cloud.** The local file is the source of truth and the cloud is a copy of the same JSON string
under one key, uploaded after a successful local write and compared by `savedAtUnix` on sign-in.
Access classes, write locks and conflict handling → `unity-ugs` → `reference/cloud-save.md`.

## 7. The gate

`templates/SaveRoundTripTests.cs`, EditMode, in a temporary directory:

| Test | Asserts |
|---|---|
| `Write_ThenRead_ReturnsTheSameSave` | Equal after a round trip; the timestamp is the one passed in; no `.tmp` left |
| `SameData_SameTimestamp_SameBytes` | Two writes of equal data are byte-identical |
| `V1File_MigratesToV2` | Every row of the table in §4, from a hand-typed fixture |
| `MigratedSave_IsWrittenBackAtTheCurrentVersion` | The old-version file becomes the backup |
| `TruncatedFile_IsDetected_AndThePreviousSaveSurvives` | Half a file reads as the save before it; the next write keeps that backup |
| `ZeroFilledFile_IsDetected` | The other shape a crash leaves |
| `NoFiles_IsNotAnError` | A first run: nothing found, source `None`, problem "no save file", not `tooNew` |
| `FileWithNoVersion_IsRejected` | A file with no `version` field is damaged, not version 0 |
| `FileFromANewerBuild_IsNeverOverwritten` | `tooNew` is set, `Write` throws, the bytes are unchanged |

```bash
"$UNITY" -projectPath . -batchmode -runTests -testPlatform EditMode \
    -testFilter SaveRoundTrip -testResults /tmp/save.xml -logFile /tmp/save.log
```

Show it can fail before trusting it. Change `SaveMigrations.LaneSpacing` and
`V1File_MigratesToV2` turns red; remove the branch in `Write` that deletes a damaged main file
and `TruncatedFile_IsDetected_AndThePreviousSaveSurvives` turns red on its last assertion.
