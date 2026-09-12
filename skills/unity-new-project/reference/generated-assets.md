# Editor scripts that generate project state — settings, ScriptableObjects, scenes

> Part of the `unity-new-project` skill. Applies the moment a project has *any* Editor script
> that writes assets or Player Settings: that output stops being something a human edits.

## 1. Make project settings a re-runnable method, not a checklist

Put the day-one Player Settings in one idempotent `static` method exposed **both** as a
`[MenuItem]` and to `-executeMethod`. It is synchronous, so unlike a package install it is
safe with `-quit` (see `reference/package-bootstrap.md` for why that distinction matters).

```csharp
[MenuItem("Project/Setup/Configure Android")]
public static void ConfigureAndroid() {
    var android = NamedBuildTarget.Android;
    PlayerSettings.companyName = CompanyName;
    PlayerSettings.productName = ProductName;
    PlayerSettings.SetApplicationIdentifier(android, "com.<org>.<app>");
    PlayerSettings.SetScriptingBackend(android, ScriptingImplementation.IL2CPP);
    PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
    // Unity 6000.4 clamps to 25 — read yours back after setting it (SKILL.md §4)
    PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel25;
    PlayerSettings.stripEngineCode = true;
    PlayerSettings.colorSpace = ColorSpace.Linear;

    // The two settings the repo's .gitattributes and every reviewable diff depend on:
    EditorSettings.serializationMode = SerializationMode.ForceText;
    VersionControlSettings.mode      = "Visible Meta Files";

    AssetDatabase.SaveAssets();
    if (Application.isBatchMode) EditorApplication.Exit(0);
}
```

(A full version usually also sets orientation and app icons.)

Why the last two lines are in *this* method rather than a README: they are the assumptions the
whole version-control setup rests on, and they quietly disappear whenever someone recreates the
project from a template. Anything a teammate can re-establish by running one menu item is a
procedure; anything written in prose is a checklist nobody re-runs.

## 2. A generated `.asset` is build output — edit the generator

If a scaffolding script creates ScriptableObjects with a "replace on every run" flag, then
**anything typed into the Inspector is silently lost at the next run.**

When a generated table has to change, make it a single commit touching all four places:

1. the C# factory method that builds the asset,
2. the default field initialiser on the class (so a hand-made instance agrees),
3. the generated `.asset` files (regenerated, not hand-edited),
4. the test that pins the values.

Rule: **treat generated assets like compiled output** — change the generator, rerun it, and keep
a test asserting the values so a regression in the generator is a red test rather than a silent
data change.

## 3. Two traps inside the generator itself

Both bite a batch scaffolder that creates ScriptableObjects and then scenes.

### `EditorSceneManager.NewScene` invalidates unsaved ScriptableObjects

Objects created in memory but never written to disk are **destroyed** by the scene change; the
next line that touches them throws `MissingReferenceException` (reported as "the catalog object
has been destroyed"), far from the actual cause.

```csharp
AssetDatabase.SaveAssets();                 // flush BEFORE any NewScene
foreach (var spec in specs) CreateGameScene(spec);
// after every NewScene, re-acquire — never reuse the C# reference you were holding
catalog = AssetDatabase.LoadAssetAtPath<Catalog>(DataDir + "/Catalog.asset");
```

### `EditorUtility.CopySerialized` wipes `m_Name`

The idiomatic "refresh an existing asset in place" call copies the *fresh* instance's empty name
over the asset's name. Everything still loads, and then `Resources.Load<T>(path).name` comes back
`""` — which breaks any runtime code that identifies an asset by its name. Restore it in the
helper:

```csharp
static T Asset<T>(string path, Func<T> create, bool replace = false) where T : ScriptableObject {
    var existing = AssetDatabase.LoadAssetAtPath<T>(path);
    if (existing != null && !replace) return existing;
    var fresh = create();
    var name  = Path.GetFileNameWithoutExtension(path);
    if (existing != null) {
        EditorUtility.CopySerialized(fresh, existing);
        existing.name = name;                       // CopySerialized just cleared it
        Object.DestroyImmediate(fresh);
        EditorUtility.SetDirty(existing);
        return existing;
    }
    fresh.name = name;
    AssetDatabase.CreateAsset(fresh, path);
    return fresh;
}
```

## 4. Commit the `.meta` with the asset

Anything a generator writes — `.cs`, `.asset`, `.unity` — is committed together with the `.meta`
Unity produced for it. A generated asset whose `.meta` is missing from the commit gives every
other clone a broken reference with no obvious cause. Headless `.meta` generation after a script
writes files is `AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate)` + `SaveAssets()`
(synchronous — see `reference/package-bootstrap.md`).
