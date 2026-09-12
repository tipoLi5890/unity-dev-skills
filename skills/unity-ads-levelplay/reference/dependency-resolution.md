# Native dependency resolution

The Ads Mediation package delivers C#. The ad networks themselves are native Android and iOS
libraries, and UPM does not fetch those — a dependency manager does. This file is the procedure for
§4 of the skill, and the first thing to read when a build fails on ad dependencies after the Editor
compiled cleanly.

The failure signature is specific and worth recognising on sight: **no compile errors anywhere, and
a Gradle or CocoaPods error the moment you build for a device.** Nothing in the Editor foreshadows
it.

## Which manager is installed

Three are in circulation, and any one of them is enough:

| Manager | Folder under `Assets/` |
|---|---|
| Mobile Dependency Resolver (MDR) | `Mobile Dependency Resolver` |
| Unity External Dependency Manager (UEDM) | its own folder |
| External Dependency Manager for Unity (EDM4U) | `External Dependency Manager` or `EDM4U` |

Look for the folder rather than asking. If one is there, the manager is installed; its menu appears
under **Assets** with the same name.

Unity is moving toward UEDM. Given a choice on a Unity version that offers it, prefer it over MDR.

## Resolving, per platform

**Android.** Recent Mobile Dependency Resolver versions — the ones shipped inside the Ads Mediation
package — resolve automatically as part of the build, so there is nothing to click. If a build fails
anyway, force it: **Assets > Mobile Dependency Resolver > Android Resolver > Resolve** (or the same
path under whichever manager is installed, e.g. **Assets > External Dependency Manager > Android
Resolver > Resolve**). Menu wording drifts between versions; the item to find is **Android Resolver**.

**iOS.** No manager resolves iOS automatically. CocoaPods installation is always a manual step:
**Assets > [dependency manager] > iOS Resolver > Install Cocoapods**.

**Shipping both platforms means running both**, before anything else in the integration continues.

## Nothing installed

The Ads Mediation install offers Mobile Dependency Resolver in a prompt. If that prompt was dismissed
or never appeared, restart the Editor — it often shows up on the next launch. Still nothing, and no
manager folder in `Assets/`, means one has to be installed deliberately: accept the prompt's
**Import**, or install EDM4U from its own documentation.

## Confirming it worked

| Platform | What to look for |
|---|---|
| Android | Gradle dependency files under `Assets/Plugins/Android/` |
| iOS | a `Podfile`, or the CocoaPods confirmation line in the console |

If resolution reports errors, the console message names the conflict — read it rather than retrying.
[`troubleshooting.md`](troubleshooting.md) covers the recurring Gradle and CocoaPods shapes.

## Custom Main Gradle Template, on older package versions

Newer package versions switch this on themselves. Older ones need it enabled by hand:

**Edit > Project Settings > Player** → Android tab → **Publishing Settings** → under **Build**, tick
**Custom Main Gradle Template**.

If the tick box is already on, leave it alone; toggling it rewrites the template file.

## Android API 33+

Targeting API level 33 or higher, the advertising identifier needs an explicit permission:

```xml
<uses-permission android:name="com.google.android.gms.permission.AD_ID"/>
```

Without it, advertising-ID access fails on Android 13 and later devices. This permission also has to
be declared to the store, and it arrives in the merged manifest whether or not you wrote it —
`unity-monetization` owns that half, and reading the merged manifest back off the built artifact is
`unity-android-release`.
