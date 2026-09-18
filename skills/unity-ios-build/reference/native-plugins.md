# A native Objective-C++ plugin, and iterating on it in 30 seconds

On iOS a plugin ships as **source**. Unity copies the `.mm` into the generated Xcode project and
it is compiled there, statically, into `UnityFramework`. That has three consequences: the first
compiler to see your code is `xcodebuild`, not Unity; the flags come from the `.meta`; and you can
recompile it without Unity.

## The four files

```
Runtime/Plugins/iOS/MyPlugin.mm          the code, C ABI at the bottom
Runtime/Plugins/iOS/MyPlugin.mm.meta     platform = iOS only, compile flags, frameworks
Runtime/MyPluginNative.cs                DllImport("__Internal") + stubs
Editor/IosPostprocess.cs                 plist keys, frameworks again (headless-build.md)
```

**The `.meta` is part of the plugin.** Without it the file is imported for every platform and the
Android build tries to compile Objective-C.

```yaml
PluginImporter:
  platformData:
  - first: { Any: }
    second: { enabled: 0 }
  - first: { Editor: Editor }
    second: { enabled: 0 }
  - first: { iPhone: iOS }
    second:
      enabled: 1
      settings:
        CompileFlags: -fobjc-arc -std=c++17
        FrameworkDependencies: CoreMotion;CoreBluetooth;
```

`-fobjc-arc` is per file — Unity's own sources are not ARC, so it cannot be a project setting.

## The C# side

```csharp
internal static class MyPluginNative
{
#if UNITY_IOS && !UNITY_EDITOR
    [DllImport("__Internal")] static extern int  myplugin_open(int rate);
    [DllImport("__Internal")] static extern int  myplugin_read(int h, [Out] short[] dst, int max);
    [DllImport("__Internal")] static extern int  myplugin_json(byte[] buf, int cap);   // returns needed size
    public static int Open(int rate) => myplugin_open(rate);
#else
    public static int Open(int rate) => -1;            // same surface, inert everywhere else
#endif
}
```

- `"__Internal"` because the code is linked into the same binary. `!UNITY_EDITOR` because the
  Editor on a Mac defines `UNITY_IOS` when iOS is the active target and has no such symbol.
- **Stub every member in the `#else`.** Callers then need no `#if`, EditMode tests run, and the
  Android build compiles the same files.
- **Any asmdef on the path needs `"iOS"` in `includePlatforms`** (or an empty list). An asmdef
  that lists only `Android` and `Editor` compiles to nothing on iOS, and the error appears far
  away — a missing type in the assembly that references it.
- Strings out of native code: pass a `byte[]` and a capacity, return the size needed, retry once
  when it did not fit. Returning `char*` makes ownership a guess.
- Export with `extern "C"` and plain ints/pointers. Keep one process-wide handle if the resource
  is process-wide (a camera or motion session is), and make `open` report "already open" rather than leak.

## Things that compile everywhere except here

> **Unity builds with Objective-C exceptions disabled.** `@try` / `@catch` is a hard error:
> *"cannot use '@try' with Objective-C exceptions disabled"*. APIs that throw when misused
> (`removeTapOnBus:` on a bus with no tap, KVO removal) must be guarded by **your own state flag**
> — `if (tapInstalled) { [node removeTapOnBus:0]; tapInstalled = false; }`.

| Pattern | Why |
|---|---|
| Callback blocks capture `std::weak_ptr<State>`, lock it inside | A realtime callback can fire during or after `close`. A raw pointer there is a use-after-free that shows up once a week |
| `std::recursive_mutex` if you ever pump the run loop while holding the lock | Notifications delivered on the main queue during the pump re-enter your handlers **on the same thread**; a plain mutex deadlocks itself |
| Notification observers on `[NSOperationQueue mainQueue]` | Unity's player loop is the main thread; your C# poll and your observer then never interleave |
| Poll from C#, do not call back into it | No `UnitySendMessage`, no function-pointer callbacks across IL2CPP. Native code queues; C# reads a generation counter once per frame and drains when it changed. **Enqueue first, bump the counter last** — the reader treats the bump as "data is ready" |
| `NSLog` with one fixed prefix | It reaches the `devicectl --console` stream next to `Debug.Log`, and one `grep` reads both |
| Log what you negotiated, not what you asked for | Resolutions, formats, update rates: the OS chooses. Print the value read back after activation |

## The 30-second loop

A Unity iOS build is minutes. A one-line change to a `.mm` does not need one:

```bash
SRC=Packages/com.you.pkg/Runtime/Plugins/iOS/MyPlugin.mm          # the source of truth
DST=$(find Builds/ios/Libraries -name MyPlugin.mm | head -1)      # Unity's copy
cp "$SRC" "$DST"
xcodebuild … build        # incremental: recompiles that file, relinks, re-signs
```

`templates/ios-run.sh native-sync` does this for every plugin source under the roots you list,
reports which files changed, and rebuilds.

**Rules that keep this honest:**

- **Edit the package source, copy outward. Never edit the copy.** The next Unity build overwrites
  it, and your fix silently disappears with a green build.
- **`diff -q "$SRC" "$DST"` before believing a device result.** If they differ, you tested
  something that is not in the repo.
- It only covers native sources. **Any C# change, a new file, a changed `.meta` flag or framework
  needs the Unity build** — new files are not in the `.pbxproj` until Unity regenerates it.
- The first build after a Unity regeneration recompiles all of IL2CPP's output; only the ones
  after that are fast. Keep `-derivedDataPath` stable so the cache survives.
