# Troubleshooting

Five failure shapes, in the order they occur during an integration. Each one has a root cause that
looks nothing like its symptom.

## `CS0246` — the namespace `Unity.Services.LevelPlay` is not found

Every LevelPlay symbol red, `The type or namespace name 'LevelPlay' could not be found`, the whole
file underlined. **The package is not resolved.** No amount of code fixing helps.

1. Stop producing code.
2. Read `Packages/packages-lock.json` and look for `com.unity.services.levelplay` — the id behind the
   **Ads Mediation** display name. This is the same question as "is it installed in Package Manager",
   answered from the project instead of from a window, which makes it both faster and trustworthy.
3. Missing → install it (skill §3).
4. **Restart the Editor after installing.** Skipping this is why a correct install still shows errors.
5. Confirm by watching `using Unity.Services.LevelPlay;` stop erroring, then resume.

Preventing it is the §7 checkpoint: re-read the lock file before writing initialization code, every
time, regardless of what an earlier turn concluded.

## Android Gradle or iOS CocoaPods build fails

Compiles perfectly in the Editor, fails at build, or builds and dies immediately on launch. **Native
dependencies were never resolved.**

1. Check `Assets/` for a dependency manager folder (MDR, UEDM, EDM4U).
2. Run resolution for the target platform — Android auto-resolves on newer MDR versions, iOS never
   does. Paths in [`dependency-resolution.md`](dependency-resolution.md).
3. Verify the output: Gradle files in `Assets/Plugins/Android/` for Android, a `Podfile` or a console
   confirmation for iOS.
4. No manager at all → restart the Editor and accept the Mobile Dependency Resolver prompt.
5. Rebuild.

A Gradle failure that names a *class* rather than a dependency, in a project with a second SDK
installed, is usually two SDKs pulling different versions of the same transitive library — that is
`unity-monetization`, not this file.

If the failure is specifically `com.ironsource.sdk` artifacts no longer resolving from
`android-sdk.is.com`, the repository is gone: [`migration-sdk-9.md`](migration-sdk-9.md) §D.

## Ads never load

Candidates, roughly in order of likelihood:

- The ad object was constructed before `OnInitSuccess` fired.
- The App Key does not match the dashboard.
- `Init()` succeeded but no adapter has fill in the test region.
- No connectivity.

What to check: that `OnInitSuccess` genuinely fires *before* any `new LevelPlay*Ad(...)` runs; that
the App Key is the one from **Apps** in the dashboard; that the test is on a real device with a real
connection. Dashboard test mode is a separate thing from Editor mock ads — it serves real test ads
on device.

## Callbacks never fire

- Events subscribed after `Init()` rather than before it.
- One or more subscriptions simply missing.
- The `MonoBehaviour` holding the subscriptions was destroyed — a scene change with no
  `DontDestroyOnLoad`.

Subscribe before `Init()`, log every callback while diagnosing so you can see which ones arrive, and
keep the manager on a persistent GameObject.

One case that is not a bug: **in the Editor, `LevelPlay.OnInitSuccess` does not always fire.** If the
callback never logs in-Editor and ads therefore never get created, create them directly in `Start()`
after `Init()` — mock ads appear without `OnInitSuccess`. On device the callback is the correct gate.

## Build errors that belong to one platform

**iOS** — SKAdNetwork ids missing from `Info.plist`, ATT wired incorrectly, or a framework Xcode
expects and cannot find. [`ios-setup.md`](ios-setup.md).

**Android** — Google Play Services missing, a manifest permission absent, Gradle dependencies
unresolved. Start from [`dependency-resolution.md`](dependency-resolution.md); anything that turns
out to be about the merged manifest or the store listing belongs to `unity-monetization`.
