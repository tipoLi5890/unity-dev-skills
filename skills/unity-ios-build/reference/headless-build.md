# The Unity half: an Xcode project you can regenerate

Unity's iOS "build" writes a folder: `Unity-iPhone.xcodeproj`, generated C++ from IL2CPP, your
plugin sources copied under `Libraries/`, and an `Info.plist`. It compiles nothing for the device.
Treat the folder as a disposable intermediate — never hand-edit it, because the next build
regenerates it.

## The entry point

`templates/IosBuildScript.cs` is a static method for `-executeMethod`. What it pins, and why:

| It does | Because |
|---|---|
| Takes scenes from `EditorBuildSettings.scenes` (enabled only), refuses when there are none | A build with zero scenes succeeds and boots to a black screen |
| Deletes the output folder first | A stale project from yesterday is indistinguishable from today's |
| Reads the team from `IOS_TEAM_ID`, the bundle id from `IOS_BUNDLE_ID` | Identifiers stay out of the repo; an unset team is fine for the compile gate |
| Sets `appleEnableAutomaticSigning = true` when a team is given | Matches the signing mode that works from a terminal — `signing-from-the-terminal.md` |
| Pins `targetOSVersionString` and IL2CPP | The floor is a product decision; do not inherit it from whoever last opened the dialog |
| `EditorApplication.Exit(1)` on any failure, including `BuildResult != Succeeded` | In batchmode an exception inside `-executeMethod` can still leave exit 0 |

```bash
UNITY="/Applications/Unity/Hub/Editor/$(sed -n 's/^m_EditorVersion: //p' ProjectSettings/ProjectVersion.txt)/Unity.app/Contents/MacOS/Unity"
IOS_TEAM_ID=<team> IOS_BUNDLE_ID=<com.you.app> "$UNITY" -batchmode -quit -projectPath . \
  -buildTarget iOS -executeMethod IosBuildScript.Build -logFile /tmp/ios-unity.log
```

`-buildTarget iOS` on the command line matters: without it the Editor opens on the project's last
platform and **reimports everything twice** — once on open, once when the script switches target.

## Check the result — three reads, not one exit code

```bash
OUT=Builds/ios
test -d "$OUT/Unity-iPhone.xcodeproj"                      || echo "no project — read the log"
grep -E "error CS|Build (succeeded|failed)|Exiting batchmode" /tmp/ios-unity.log | tail -5
/usr/libexec/PlistBuddy -c 'Print :NSCameraUsageDescription' "$OUT/Info.plist"   # your plist keys
```

| The log says | It means |
|---|---|
| `No valid Unity Editor license` / exit 198 | Licence, not your project — skill `unity-cli` |
| `It looks like another Unity instance is running with this project open` | Close the Editor, or build from a copy. One Unity per project |
| `error CS…` only under `UNITY_IOS` | Code that was never compiled on the Android/Editor target. The compile gate for C# is this build |
| Nothing after `Refreshing native plugins` for minutes | First iOS import of a large project. It is working; the second build is fast |

## Info.plist keys and frameworks belong in a post-process step

Anything the generated project needs beyond Player Settings — a usage description, a linked
framework, a capability — goes in `[PostProcessBuild]`, because the project is regenerated.
`templates/IosPostprocess.cs` is **idempotent** (it only adds what is missing) and has two tables
to edit:

```csharp
static readonly (string key, string text)[] UsageStrings = {
    ("NSCameraUsageDescription", "Explains to the player why the camera is needed."),
};
static readonly string[] Frameworks = { "CoreMotion.framework", "CoreBluetooth.framework" };
```

- **A missing usage string is not a warning.** The first call into the guarded API kills the
  process with no managed exception — the app just disappears, and the console shows a TCC line.
- Frameworks go on **`GetUnityFrameworkTargetGuid()`**, not the main target: your plugin code is
  compiled into `UnityFramework`. Adding them to `Unity-iPhone` links nothing you use.
- Declare the same frameworks in the plugin's `.meta` as well (`native-plugins.md`). The
  post-process is the belt; projects that override plugin import settings lose the braces.
- Wrap the file in `#if UNITY_IOS` — `UnityEditor.iOS.Xcode` does not exist when the iOS module is
  not installed, and an Editor assembly that fails to compile takes every menu item with it.
- In a package, the asmdef holding this file needs `includePlatforms: ["Editor"]`.

## The build edits your project

After a headless iOS build, `git diff ProjectSettings/ProjectSettings.asset` typically shows
`applicationIdentifier`, `appleDeveloperTeamID`, `appleEnableAutomaticSigning` and the iOS target
version. They came from the build method. Two honest options:

- **Commit them** if they are the project's real values.
- **Keep them out** if they are one developer's: read them from the environment (as the template
  does) and restore the lines afterwards. Restore lines, not the file —
  `git checkout -- ProjectSettings.asset` discards every other Player Setting written since the
  last commit.

Also gitignore the output folder. A generated Xcode project is thousands of files and will be
swept up by the next `git add -A`.
